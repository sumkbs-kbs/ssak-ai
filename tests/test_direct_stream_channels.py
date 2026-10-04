from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from antigravity_k.engine.chat_stream_events import FinalChunk, ProgressChunk

if TYPE_CHECKING:
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.benchmark_harness import TaskOutcome
    from antigravity_k.engine.task_state_store import TaskExecutionContext, TaskStateStore


class _BoundOrchestrator:
    max_engine: None = None

    def __init__(self) -> None:
        self.chunks: tuple[str, ...] = (
            ProgressChunk("stage"),
            "시간复",
            "杂度 draft",
            FinalChunk("resolved-final" * 6),
            ProgressChunk("cleanup"),
        )
        self._last_agent_output = "initial-shared-output"
        self.shared_output_after = "unrelated-shared-output"
        self.error: RuntimeError | None = None
        self._context: ContextVar[TaskExecutionContext | None] = ContextVar("direct_channel_task", default=None)

    @property
    def task_execution_context(self) -> TaskExecutionContext | None:
        return self._context.get()

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore) -> Iterator[None]:
        from antigravity_k.engine.task_state_store import TaskExecutionContext

        token = self._context.set(TaskExecutionContext(task_id, state_store))
        try:
            yield
        finally:
            self._context.reset(token)

    def get_model_for_role(self, role: str) -> str:
        return "test-model"

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        assert self.task_execution_context is not None
        yield from self.chunks
        self._last_agent_output = self.shared_output_after
        if self.error is not None:
            raise self.error


@dataclass(frozen=True, slots=True)
class _Case:
    runtime: AgentRuntime
    store: TaskStateStore
    orchestrator: _BoundOrchestrator
    outcomes: list[TaskOutcome]


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Case:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.task_runner import BackgroundTaskRunner

    orchestrator = _BoundOrchestrator()
    outcomes: list[TaskOutcome] = []
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    runtime = AgentRuntime(orchestrator, task_runner=runner, task_outcome_recorder=outcomes.append)
    return _Case(runtime, runner.state_store, orchestrator, outcomes)


def test_agent_runtime_preserves_typed_stream_chunks_through_direct_execution(case: _Case) -> None:
    tracked = case.runtime.start_stream([{"role": "user", "content": "inspect this input"}])

    chunks = list(tracked.chunks)

    assert chunks[0] is case.orchestrator.chunks[0]
    assert chunks[-2] is case.orchestrator.chunks[-2]
    assert chunks[-1] is case.orchestrator.chunks[-1]
    assert "".join(chunk for chunk in chunks if type(chunk) is str) == "시간복잡도 draft"
    assert case.orchestrator.task_execution_context is None


@pytest.mark.parametrize("shared_output_after", ["initial-shared-output", "unrelated-shared-output", ""])
def test_typed_final_is_authoritative_over_draft_status_and_shared_output(
    case: _Case, shared_output_after: str
) -> None:
    case.orchestrator.shared_output_after = shared_output_after
    tracked = case.runtime.start_stream([{"role": "user", "content": "inspect this input"}])

    list(tracked.chunks)

    assert tracked.task_id is not None
    record = case.store.get_task(tracked.task_id)
    assert record is not None
    assert record["status"] == "done"
    assert record["output"] == "resolved-final" * 6
    assert len(case.outcomes) == 1
    assert case.outcomes[0].success is True
    assert case.outcomes[0].tokens_out == len("resolved-final" * 6) // 4


def test_error_after_final_keeps_failed_status_and_clean_checkpoint(case: _Case) -> None:
    case.orchestrator.error = RuntimeError("stream-failure")
    tracked = case.runtime.start_stream([{"role": "user", "content": "inspect this input"}])

    with pytest.raises(RuntimeError, match="stream-failure"):
        list(tracked.chunks)

    assert tracked.task_id is not None
    record = case.store.get_task(tracked.task_id)
    checkpoint = case.store.get_last_checkpoint(tracked.task_id)
    assert record is not None
    assert checkpoint is not None
    assert record["status"] == "failed"
    assert record["output"] == "resolved-final" * 6
    assert checkpoint["output_so_far"] == "resolved-final" * 6
    assert len(case.outcomes) == 1
    assert case.outcomes[0].success is False
    assert case.outcomes[0].completion_reason == "failed"
    assert case.outcomes[0].tokens_out == len("resolved-final" * 6) // 4


def test_legacy_string_stream_retains_canonical_side_channel_behavior(case: _Case) -> None:
    case.orchestrator.chunks = ("draft", "tail")
    case.orchestrator.shared_output_after = "legacy-final"
    tracked = case.runtime.start_stream([{"role": "user", "content": "inspect this input"}])

    chunks = list(tracked.chunks)

    assert chunks == ["draft", "tail"]
    assert tracked.task_id is not None
    record = case.store.get_task(tracked.task_id)
    assert record is not None
    assert record["status"] == "done"
    assert record["output"] == "legacy-final"
