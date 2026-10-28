import json
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.orchestrator.stream import run_stream as production_stream
from antigravity_k.engine.quality_gate import QualityGate
from antigravity_k.engine.task_execution_context import TaskExecutionContext, bind_task_execution_context
from antigravity_k.engine.task_runner import BackgroundTaskRunner, TaskStatus
from antigravity_k.engine.task_state_store import TaskStateStore

QUALITY = "\n📊 *품질: excellent (100%)*\n"
LIST_WITH_LF = "".join(f"{n:02d}. R48-DELIVERY-{n:02d} 합성 인사말 {n:02d} 끝입니다.\n" for n in range(1, 31))


class ScriptedStream:
    """Expose real str subtypes with a deterministic boundary before delivery."""

    def __init__(self, chunks: tuple[str, ...], *, gated: bool = False) -> None:
        self.chunks = chunks
        self.started = Event()
        self.release = Event()
        self.gated = gated
        self.delivered = 0

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.started.set()
        if self.gated:
            assert self.release.wait(3)
        for chunk in self.chunks:
            self.delivered += 1
            yield chunk


class ScriptedProvider:
    """Return synthetic complete responses; never load or invoke a model."""

    def __init__(self, responses: tuple[str, ...]) -> None:
        self.responses = deque(responses)
        self.requests: list[str] = []
        self.started = Event()
        self.release = Event()

    def generate(self, **kwargs: JsonValue) -> str:
        self.requests.append(str(kwargs.get("prompt", "")))
        if len(self.requests) == 1:
            self.started.set()
            assert self.release.wait(3)
        return ModelManager._strip_hidden_reasoning(self.responses.popleft())


class ProductionDirectStream:
    """Use production routing, ToolLoop, quality emitter and task binding."""

    def __init__(self, provider: ScriptedProvider, root: Path) -> None:
        manager = MagicMock()
        manager.is_loaded.return_value = True
        manager.router.get_combo.return_value = None
        manager.generate.side_effect = provider.generate
        self.manager = manager
        self.delegate = SimpleNamespace(
            config={},
            project_root=root,
            manager=manager,
            task_execution_context=None,
            task_outcome_recorder=None,
            expected_tools=(),
            context_shaper=None,
            _capacity_checkpoint=None,
            _latest_user_text=lambda messages: next(
                message["content"] for message in reversed(messages) if message["role"] == "user"
            ),
            ctx=SimpleNamespace(
                cognitive_loop=None, quality_gate=QualityGate(max_retries=0), decision_anchor=None, expected_tools=()
            ),
        )

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore) -> Iterator[None]:
        previous = self.delegate.task_execution_context
        context = TaskExecutionContext(task_id, state_store)
        self.delegate.task_execution_context = context
        try:
            with bind_task_execution_context(context):
                yield
        finally:
            self.delegate.task_execution_context = previous

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        yield from production_stream(self.delegate, messages, target_model)


class ToolCheckpointStream:
    """Create the same durable ordering as completed tool rounds, without running tools."""

    def __init__(self, checkpoint_step: int) -> None:
        self.context: TaskExecutionContext | None = None
        self.checkpoint_step = checkpoint_step
        self.ready = Event()
        self.release = Event()

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore) -> Iterator[None]:
        self.context = TaskExecutionContext(task_id, state_store)
        try:
            yield
        finally:
            self.context = None

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        assert self.context is not None
        self.context.state_store.save_checkpoint(
            self.context.task_id,
            self.checkpoint_step,
            json.dumps(
                {
                    "direct_response": True,
                    "tool_loop": {
                        "step": self.checkpoint_step,
                        "used_tools": ["read_file"],
                        "tool_evidence_context": "synthetic completed tool evidence",
                    },
                }
            ),
            "old internal tool-round output",
        )
        yield "new actual body"
        self.ready.set()
        assert self.release.wait(3)
        yield ProgressChunk(QUALITY)


def join_task(runner: BackgroundTaskRunner, task_id: str) -> None:
    thread = runner._tasks[task_id]._thread
    assert thread is not None
    thread.join(5)
    assert not thread.is_alive()


def progress_events(runner: BackgroundTaskRunner, task_id: str) -> list[dict[str, JsonValue]]:
    return [
        json.loads(event["payload_json"])
        for event in runner.state_store.list_execution_events(task_id)
        if event["event_type"] == "task.stream.progress"
    ]


@pytest.mark.parametrize("body", [LIST_WITH_LF, LIST_WITH_LF[:-1]], ids=["with_final_lf", "without_final_lf"])
def test_typed_status_is_recorded_separately_and_exact_content_is_preserved(tmp_path: Path, body: str) -> None:
    # Given: status text matches the actual r49 quality emitter, with either content EOF form.
    stream = ScriptedStream((ProgressChunk("준비 상태"), body, ProgressChunk(QUALITY)))
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    # When: the production runner consumes typed status and ordinary content.
    task_id = runner.submit_task("synthetic answer only", orchestrator=stream, target_model="fake")
    join_task(runner, task_id)
    # Then: no whitespace or status is added to the exact body; status remains inspectable.
    record = runner.state_store.get_task(task_id)
    assert record is not None and record["status"] == TaskStatus.DONE
    assert record["output"] == runner.get_output(task_id) == body
    assert [event["text"] for event in progress_events(runner, task_id)] == ["준비 상태", QUALITY]


def test_same_quality_phrase_as_ordinary_content_survives_pause_and_restart(tmp_path: Path) -> None:
    # Given: a paused body cursor and literal content identical to a quality display message.
    db = str(tmp_path / "tasks.db")
    first = ScriptedStream(("고유 항목의 중",), gated=True)
    runner = BackgroundTaskRunner(db_path=db)
    task_id = runner.submit_task("synthetic answer only", orchestrator=first, target_model="fake")
    assert first.started.wait(3)
    assert runner.pause_task(task_id) == "pausing"
    first.release.set()
    join_task(runner, task_id)
    checkpoint = runner.state_store.get_last_checkpoint(task_id)
    assert checkpoint is not None and checkpoint["output_so_far"] == "고유 항목의 중" and checkpoint["step"] == 1
    restarted = BackgroundTaskRunner(db_path=db)
    continuation = ScriptedStream((ProgressChunk(QUALITY), "간 내용\n", QUALITY, ProgressChunk(QUALITY)))
    # When: a new runner resumes through status before and after the real continuation.
    assert restarted.resume_task(task_id, orchestrator=continuation, target_model="fake")
    join_task(restarted, task_id)
    # Then: only actual status types are excluded; identical user content remains verbatim once.
    assert restarted.get_output(task_id) == "고유 항목의 중간 내용\n" + QUALITY
    assert restarted._tasks[task_id].status == TaskStatus.DONE
    events = progress_events(restarted, task_id)
    assert [event["text"] for event in events] == [QUALITY, QUALITY]
    assert [event["step"] for event in events] == [1, 3]
    assert all(event["resumed"] is True for event in events)


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_status_boundary_still_observes_user_pause_or_cancel(tmp_path: Path, action: str) -> None:
    # Given: the next producer item is status, and consuming the following body would be unwanted.
    stream = ScriptedStream((ProgressChunk(QUALITY), "must not be consumed"), gated=True)
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    task_id = runner.submit_task("synthetic answer only", orchestrator=stream, target_model="fake")
    assert stream.started.wait(3)
    # When: the user signal precedes the next typed status item.
    if action == "pause":
        assert runner.pause_task(task_id) == "pausing"
    else:
        assert runner.cancel_task(task_id)
    stream.release.set()
    join_task(runner, task_id)
    # Then: signal handling is not skipped when the status is kept out of the body.
    assert stream.delivered == 1
    assert runner.get_output(task_id) == ""
    assert runner._tasks[task_id].status == (TaskStatus.PAUSED if action == "pause" else TaskStatus.CANCELLED)
    assert [event["text"] for event in progress_events(runner, task_id)] == [QUALITY]
    if action == "pause":
        checkpoint = runner.state_store.get_last_checkpoint(task_id)
        assert checkpoint is not None and checkpoint["step"] == 0 and checkpoint["output_so_far"] == ""


def test_captured_r49_shape_through_production_direct_stream_and_store(tmp_path: Path) -> None:
    # Given: the actual r49 list/pause shape, with production generate's existing strip semantics.
    # The original wire EOF is not claimed; the normalized body is 1079 chars and cursor 1067.
    body = LIST_WITH_LF[:-1]
    assert len(LIST_WITH_LF) == 1080 and len(body) == 1079 and len(QUALITY) == 26
    provider = ScriptedProvider((LIST_WITH_LF, body[1067:]))
    stream = ProductionDirectStream(provider, tmp_path)
    db = str(tmp_path / "tasks.db")
    runner = BackgroundTaskRunner(db_path=db)
    task_id = runner.submit_task(
        "합성 목록을 설명 없이 순서대로 출력하세요.",
        context={"direct_response": True, "allowed_tools": []},
        orchestrator=stream,
        target_model="qwen3.8:latest",
        owner_subject="synthetic-owner",
    )
    assert provider.started.wait(3)
    assert runner.pause_task(task_id, owner_subject="synthetic-owner") == "pausing"
    provider.release.set()
    join_task(runner, task_id)
    paused = runner.state_store.get_last_checkpoint(task_id)
    assert paused is not None and paused["output_so_far"] == body[:1067] and paused["step"] == 1
    assert runner._tasks[task_id].status == TaskStatus.PAUSED
    # When: a new production runner resumes the same database using the second fake response.
    restarted = BackgroundTaskRunner(db_path=db)
    assert restarted.resume_task(
        task_id, orchestrator=stream, target_model="qwen3.8:latest", owner_subject="synthetic-owner"
    )
    join_task(restarted, task_id)
    # Then: body continuity is exact, quality is an event, and two logical generations suffice.
    final = restarted.state_store.get_task(task_id, owner_subject="synthetic-owner")
    assert final is not None and final["status"] == TaskStatus.DONE
    assert final["output"] == restarted.get_output(task_id, owner_subject="synthetic-owner") == body
    assert [event["text"] for event in progress_events(restarted, task_id)] == [QUALITY]
    assert len(provider.requests) == 2 and not provider.responses
    stream.manager.stream_generate.assert_not_called()


@pytest.mark.parametrize("resumed_with_prior_tools", [False, True], ids=["fresh", "stale_resumed"])
@pytest.mark.parametrize("tool_checkpoint_step", [2, 4], ids=["equal_resumed_step", "higher_step"])
def test_pause_after_higher_tool_checkpoint_keeps_latest_body_and_known_step(
    tmp_path: Path, resumed_with_prior_tools: bool, tool_checkpoint_step: int
) -> None:
    # Given: completed tool progress has a higher durable step than streamed body chunks.
    db = str(tmp_path / "tasks.db")
    stream = ToolCheckpointStream(tool_checkpoint_step)
    runner = BackgroundTaskRunner(db_path=db)
    context = {"direct_response": True, "working_memory": "preserve original working memory"}
    if resumed_with_prior_tools:
        task_id = "synthetic-old-tool-context"
        runner.state_store.create_task(task_id, "synthetic answer only", TaskStatus.PAUSED, "2026-10-28T00:00:00Z")
        prior_context = {
            **context,
            "tool_loop": {"step": 1, "used_tools": ["old_tool"], "tool_evidence_context": "old evidence"},
        }
        runner.state_store.save_checkpoint(task_id, 1, json.dumps(prior_context), "")
        assert runner.resume_task(task_id, orchestrator=stream, target_model="fake")
    else:
        task_id = runner.submit_task("synthetic answer only", context=context, orchestrator=stream, target_model="fake")
    assert stream.ready.wait(3)
    # When: the user pauses on typed status after that tool progress and one body chunk.
    assert runner.pause_task(task_id) == "pausing"
    stream.release.set()
    join_task(runner, task_id)
    # Then: the latest checkpoint cannot be hidden behind the older higher-step tool row.
    checkpoint = runner.state_store.get_last_checkpoint(task_id)
    assert checkpoint is not None and checkpoint["output_so_far"] == "new actual body"
    assert checkpoint["step"] == tool_checkpoint_step  # reuse known progress; never invent another step
    saved_context = json.loads(checkpoint["context_json"])
    assert saved_context["tool_loop"] == {
        "step": tool_checkpoint_step,
        "used_tools": ["read_file"],
        "tool_evidence_context": "synthetic completed tool evidence",
    }
    assert saved_context["working_memory"] == "preserve original working memory"
    paused_events = [
        json.loads(event["payload_json"])
        for event in runner.state_store.list_execution_events(task_id)
        if event["event_type"] == "task.paused"
    ]
    assert paused_events[-1]["step"] == checkpoint["step"]
    restarted = BackgroundTaskRunner(db_path=db)
    assert restarted.resume_task(task_id, orchestrator=ScriptedStream((" continues",)), target_model="fake")
    join_task(restarted, task_id)
    assert restarted.get_output(task_id) == "new actual body continues"
