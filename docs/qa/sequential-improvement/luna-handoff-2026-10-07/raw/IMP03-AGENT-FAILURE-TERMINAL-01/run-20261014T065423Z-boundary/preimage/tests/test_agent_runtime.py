from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast, override
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request as StarletteRequest

from antigravity_k.api.task_models import TaskSubmitRequest
from antigravity_k.engine.agent_runtime import (
    AgentRuntime as _AgentRuntime,
)
from antigravity_k.engine.agent_runtime import (
    GoalRunnerPort,
    OrchestratorPort,
    TaskRunnerPort,
    TrackedStream,
)
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.persistent_agency import AgencyConfig, PersistentAgencyController
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskExecutionContext, TaskStateStore


class _ThreadLike(Protocol):
    def join(self, timeout: float | None = None) -> None: ...


class _ResumedTask(Protocol):
    output: str


class _StreamingResponse(Protocol):
    body_iterator: AsyncIterator[object]


def _mock_method(mock: MagicMock, name: str) -> MagicMock:
    return cast(MagicMock, getattr(mock, name))


def _assert_called_once_with(mock: MagicMock, name: str, *args: object, **kwargs: object) -> None:
    callback = cast(Callable[..., object], getattr(_mock_method(mock, name), "assert_called_once_with"))
    _ = callback(*args, **kwargs)


def _assert_awaited_once_with(mock: MagicMock, name: str, *args: object, **kwargs: object) -> None:
    callback = cast(Callable[..., object], getattr(_mock_method(mock, name), "assert_awaited_once_with"))
    _ = callback(*args, **kwargs)


def AgentRuntime(
    orchestrator: object,
    task_runner: object | None = None,
    goal_runner: object | None = None,
) -> _AgentRuntime:
    return _AgentRuntime(
        cast(OrchestratorPort, orchestrator),
        task_runner=cast(TaskRunnerPort | None, task_runner),
        goal_runner=cast(GoalRunnerPort | None, goal_runner),
    )


class FakeOrchestrator:
    def __init__(self) -> None:
        self.stream_calls: list[dict[str, object]] = []
        self.agent_runtime: object | None = None
        self.max_engine: object | None = None
        self.tool_registry: object | None = None

    def _get_model_for_role(self, role: str) -> str:
        assert role == "default"
        return "qwen3.6:latest"

    def get_model_for_role(self, role: str) -> str:
        return self._get_model_for_role(role)

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        self.stream_calls.append(
            {
                "messages": messages,
                "target_model": target_model,
                "max_steps": max_steps,
                "ephemeral_message": ephemeral_message,
            },
        )
        yield "first"
        yield "second"


class FakeTaskRunner:
    def __init__(self) -> None:
        self.submit_calls: list[dict[str, object]] = []
        self.cancel_calls: list[str] = []

    def submit_task(self, **kwargs: object) -> str:
        self.submit_calls.append(kwargs)
        return "task_runtime_001"

    def resume_task(self, **kwargs: object) -> bool:
        self.submit_calls.append(kwargs)
        return True

    def cancel_task(self, task_id: str, owner_subject: str | None = None) -> bool:
        _ = owner_subject
        self.cancel_calls.append(task_id)
        return True

    def get_status(self, task_id: str, owner_subject: str | None = None) -> dict[str, object] | None:
        _ = owner_subject
        return {"task_id": task_id, "status": "done"}

    def list_tasks(self, limit: int = 20, owner_subject: str | None = None) -> list[dict[str, object]]:
        _ = owner_subject
        task: dict[str, object] = {"task_id": "task_runtime_001", "status": "done"}
        return [task][:limit]

    def get_output(self, task_id: str, owner_subject: str | None = None) -> str | None:
        _ = owner_subject
        return "runtime-output" if task_id == "task_runtime_001" else None

    def wait_task(self, task_id: str, timeout: float | None = None) -> dict[str, object] | None:
        return {"task_id": task_id, "status": "done", "timeout": timeout}


class BoundOrchestrator(FakeOrchestrator):
    def __init__(self) -> None:
        super().__init__()
        self._execution_context: ContextVar[TaskExecutionContext | None] = ContextVar(
            "runtime_test_execution_context",
            default=None,
        )

    @property
    def task_execution_context(self) -> TaskExecutionContext | None:
        return self._execution_context.get()

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore):
        token = self._execution_context.set(TaskExecutionContext(task_id, state_store))
        try:
            yield
        finally:
            self._execution_context.reset(token)

    @override
    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        assert self.task_execution_context is not None
        yield from super().run_stream(messages, target_model, max_steps, ephemeral_message)


def test_runtime_stream_resolves_default_model_and_preserves_execution_options():
    orchestrator = FakeOrchestrator()
    runtime = AgentRuntime(orchestrator)
    messages = [{"role": "user", "content": "hello"}]

    chunks = list(runtime.stream(messages, max_steps=7, ephemeral_message="context"))

    assert chunks == ["first", "second"]
    assert orchestrator.stream_calls == [
        {
            "messages": messages,
            "target_model": "qwen3.6:latest",
            "max_steps": 7,
            "ephemeral_message": "context",
        },
    ]


def test_runtime_complete_uses_explicit_model():
    orchestrator = FakeOrchestrator()
    runtime = AgentRuntime(orchestrator)

    result = runtime.complete([{"role": "user", "content": "hello"}], target_model="local-test")

    assert result == "firstsecond"
    assert orchestrator.stream_calls[0]["target_model"] == "local-test"


def test_runtime_cancels_background_task_through_runner():
    runner = FakeTaskRunner()
    runtime = AgentRuntime(FakeOrchestrator(), task_runner=runner)

    assert runtime.cancel_task("task_runtime_001") is True
    assert runner.cancel_calls == ["task_runtime_001"]


def test_runtime_records_background_task_lifecycle_in_persistent_agency(tmp_path: Path):
    orchestrator = FakeOrchestrator()
    agency = PersistentAgencyController(str(tmp_path), AgencyConfig(enabled=True))
    setattr(orchestrator, "persistent_agency", agency)
    runner = FakeTaskRunner()
    runtime = AgentRuntime(orchestrator, task_runner=runner)

    task_id = runtime.submit_task("index the changed files", context={"trajectory_id": "main"})
    assert task_id == "task_runtime_001"
    assert runtime.resume_task(task_id) is True
    assert runtime.cancel_task(task_id) is True

    events = agency.store.list_events(agency.project_id, "main")
    assert [event.payload["status"] for event in events] == ["submitted", "resumed", "cancelled"]
    assert "index the changed files" in str(events[0].payload["text"])


def test_runtime_submits_next_objective_and_reconciles_completion(tmp_path: Path):
    orchestrator = FakeOrchestrator()
    controller = PersistentAgencyController(str(tmp_path), AgencyConfig(enabled=True))
    setattr(orchestrator, "persistent_agency", controller)
    objective = controller.enqueue_objective("demo", "Run the next indexed check", "Check files")
    runtime = AgentRuntime(orchestrator, task_runner=FakeTaskRunner())

    task_id = runtime.submit_next_objective("demo")
    assert task_id == "task_runtime_001"
    status = runtime.get_task_status(task_id)
    assert status is not None
    assert status["status"] == "done"
    stored = controller.get_objective(objective.objective_id)
    assert stored is not None
    assert stored.status.value == "done"


def test_runtime_projects_durable_context_into_next_objective(tmp_path: Path):
    orchestrator = FakeOrchestrator()
    controller = PersistentAgencyController(str(tmp_path), AgencyConfig(enabled=True))
    setattr(orchestrator, "persistent_agency", controller)
    _ = controller.record_observation(controller.project_id, "main", "The parser cache must be rebuilt first")
    _ = controller.enqueue_objective(controller.project_id, "Rebuild parser cache")
    runner = FakeTaskRunner()
    runtime = AgentRuntime(orchestrator, task_runner=runner)

    _ = runtime.submit_next_objective(controller.project_id)

    submitted = runner.submit_calls[0]
    assert "The parser cache must be rebuilt first" in str(submitted["prompt"])
    context = submitted["context"]
    assert isinstance(context, dict)
    assert context["persistent_context_event_ids"]


def test_runtime_reconciles_all_claimed_objective_tasks(tmp_path: Path):
    orchestrator = FakeOrchestrator()
    controller = PersistentAgencyController(str(tmp_path), AgencyConfig(enabled=True))
    setattr(orchestrator, "persistent_agency", controller)
    objective = controller.enqueue_objective(controller.project_id, "Reconcile me")
    _ = controller.claim_next_objective(controller.project_id)
    controller.bind_objective_task("task_runtime_001", objective.objective_id, controller.project_id, "main")
    runtime = AgentRuntime(orchestrator, task_runner=FakeTaskRunner())

    assert runtime.reconcile_persistent_objectives(controller.project_id) == 1
    stored = controller.get_objective(objective.objective_id)
    assert stored is not None
    assert stored.status.value == "done"

    summaries = controller.project_context(controller.project_id, "main").text
    assert "task_runtime_001 done" in summaries


def test_runtime_exposes_durable_task_queries_and_wait_through_runner():
    # Given: the canonical runtime owns a durable task runner.
    runtime = AgentRuntime(FakeOrchestrator(), task_runner=FakeTaskRunner())

    # When: a CLI or API consumer queries one task and waits for it.
    status = runtime.get_task_status("task_runtime_001")
    tasks = runtime.list_tasks(limit=1)
    output = runtime.get_task_output("task_runtime_001")
    waited = runtime.wait_task("task_runtime_001", timeout=3)

    # Then: every view comes from the same runner-owned task record.
    assert status == {"task_id": "task_runtime_001", "status": "done"}
    assert tasks == [{"task_id": "task_runtime_001", "status": "done"}]
    assert output == "runtime-output"
    assert waited == {"task_id": "task_runtime_001", "status": "done", "timeout": 3}


def test_runtime_start_stream_persists_direct_execution_and_exposes_task_id(tmp_path: Path):
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    runtime = AgentRuntime(BoundOrchestrator(), task_runner=SimpleNamespace(state_store=store))

    tracked = runtime.start_stream([{"role": "user", "content": "hello"}])

    assert tracked.task_id is not None
    assert list(tracked.chunks) == ["first", "second"]
    task_id = tracked.task_id
    assert task_id is not None
    record = store.get_task(task_id)
    assert record is not None
    assert record["status"] == "done"
    assert record["output"] == "firstsecond"
    assert [event["event_type"] for event in store.list_execution_events(tracked.task_id)] == [
        "interactive_registered",
        "context_snapshot",
        "interactive_started",
        "interactive_completed",
    ]


def test_runtime_direct_stream_persists_normalized_language_output(tmp_path: Path):
    # Given: a direct qwen stream splits a known Chinese false friend across chunks.
    class ContaminatedOrchestrator(BoundOrchestrator):
        @override
        def run_stream(
            self,
            messages: list[dict[str, str]],
            target_model: str,
            max_steps: int = 15,
            ephemeral_message: str | None = None,
        ) -> Iterator[str]:
            assert self.task_execution_context is not None
            yield "시간复"
            yield "杂도와 공간複雜度"

    store = TaskStateStore(str(tmp_path / "tasks.db"))
    runtime = AgentRuntime(ContaminatedOrchestrator(), task_runner=SimpleNamespace(state_store=store))

    # When: the durable direct stream completes.
    tracked = runtime.start_stream([{"role": "user", "content": "복잡도를 설명해줘"}])
    chunks = list(tracked.chunks)

    # Then: both the user stream and durable output contain Korean terms only.
    normalized = "시간복잡도와 공간복잡도"
    assert "".join(chunks) == normalized
    task_id = tracked.task_id
    assert task_id is not None
    record = store.get_task(task_id)
    assert record is not None
    assert record["output"] == normalized


def test_runtime_direct_task_stores_canonical_final_output(tmp_path: Path):
    # Given: the user stream shows a rejected draft and then a quality revision.
    class RevisingOrchestrator(BoundOrchestrator):
        _last_agent_output: str = ""

        @override
        def run_stream(
            self,
            messages: list[dict[str, str]],
            target_model: str,
            max_steps: int = 15,
            ephemeral_message: str | None = None,
        ) -> Iterator[str]:
            assert self.task_execution_context is not None
            yield "draft with syntax error\n"
            yield "revision notice\n"
            yield "corrected final answer"
            self._last_agent_output = "corrected final answer"

    store = TaskStateStore(str(tmp_path / "tasks.db"))
    orchestrator = RevisingOrchestrator()
    runtime = AgentRuntime(orchestrator, task_runner=SimpleNamespace(state_store=store))

    # When: the durable direct stream completes.
    tracked = runtime.start_stream([{"role": "user", "content": "코드를 작성해줘"}])
    chunks = list(tracked.chunks)

    # Then: the user saw the full stream, but the task record stores only the final answer.
    assert "".join(chunks) == "draft with syntax error\nrevision notice\ncorrected final answer"
    task_id = tracked.task_id
    assert task_id is not None
    record = store.get_task(task_id)
    assert record is not None
    assert record["status"] == "done"
    assert record["output"] == "corrected final answer"


def test_runtime_records_an_explicitly_named_tool_as_a_durable_contract(tmp_path: Path):
    # Given: the user explicitly requires one registered tool in a direct task.
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    orchestrator = BoundOrchestrator()
    orchestrator.tool_registry = SimpleNamespace(get_names=lambda: ["read_file", "web_search"])
    runtime = AgentRuntime(orchestrator, task_runner=SimpleNamespace(state_store=store))

    # When: the direct runtime creates its tracked execution.
    tracked = runtime.start_stream([{"role": "user", "content": "read_file 도구로 README를 읽어줘"}])

    # Then: the checkpoint exposes the exact tool requirement to the tool loop.
    assert tracked.task_id is not None
    checkpoint = store.get_last_checkpoint(tracked.task_id)
    assert checkpoint is not None
    assert checkpoint["context_json"] == '{"expected_tools": ["read_file"]}'


def test_runtime_records_execution_intent_tool_named_with_korean_particle(tmp_path: Path):
    # Given: a coding prompt that asks the model to write code AND execute it via run_bash_command.
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    orchestrator = BoundOrchestrator()
    orchestrator.tool_registry = SimpleNamespace(
        get_names=lambda: ["read_file", "web_search", "run_bash_command", "write_file"]
    )
    runtime = AgentRuntime(orchestrator, task_runner=SimpleNamespace(state_store=store))

    # When: the user names the tool with a Korean dative particle and an execution verb
    # (the realistic phrasing a Korean speaker uses, not the stilted "run_bash_command 도구" form).
    tracked = runtime.start_stream(
        [
            {
                "role": "user",
                "content": "sum_to(n) 함수를 작성하고 run_bash_command로 실행해서 결과가 5050인지 검증해줘.",
            }
        ]
    )

    # Then: the checkpoint exposes run_bash_command as a required tool so the loop forces
    # real execution instead of letting the model narrate the result.
    assert tracked.task_id is not None
    checkpoint = store.get_last_checkpoint(tracked.task_id)
    assert checkpoint is not None
    import json

    payload = cast(dict[str, list[str]], json.loads(checkpoint["context_json"]))
    assert payload["expected_tools"] == ["run_bash_command"]


def test_runtime_preserves_inner_quality_failure_without_terminal_transition_conflict(tmp_path: Path):
    class QualityRejectedOrchestrator(BoundOrchestrator):
        @override
        def run_stream(
            self,
            messages: list[dict[str, str]],
            target_model: str,
            max_steps: int = 15,
            ephemeral_message: str | None = None,
        ) -> Iterator[str]:
            # Given: the bound tool loop has already rejected its own durable task outcome.
            execution_context = self.task_execution_context
            assert execution_context is not None
            _ = execution_context.state_store.transition(
                execution_context.task_id,
                "failed",
                output="quality rejected",
                error="quality_gate_failed: unsupported answer",
            )

            # When: the direct runtime consumes the completed stream.
            yield "quality rejected"

    store = TaskStateStore(str(tmp_path / "tasks.db"))
    runtime = AgentRuntime(QualityRejectedOrchestrator(), task_runner=SimpleNamespace(state_store=store))
    tracked = runtime.start_stream([{"role": "user", "content": "verify this"}])

    # Then: it keeps the inner failure rather than incorrectly forcing the task to done.
    assert tracked.task_id is not None
    assert list(tracked.chunks) == ["quality rejected"]
    record = store.get_task(tracked.task_id)
    assert record is not None
    assert record["status"] == "failed"
    assert record["error"] == "quality_gate_failed: unsupported answer"
    checkpoint = store.get_last_checkpoint(tracked.task_id)
    assert checkpoint is not None
    assert checkpoint["output_so_far"] == "quality rejected"
    assert [event["event_type"] for event in store.list_execution_events(tracked.task_id)] == [
        "interactive_registered",
        "context_snapshot",
        "interactive_started",
        "interactive_failed",
    ]


def test_runtime_resumes_failed_direct_task_with_messages_and_partial_output(tmp_path: Path) -> None:
    class RecoveringDirectOrchestrator(BoundOrchestrator):
        def __init__(self) -> None:
            super().__init__()
            self.calls: int = 0
            self.resumed_messages: list[dict[str, str]] = []

        @override
        def run_stream(
            self,
            messages: list[dict[str, str]],
            target_model: str,
            max_steps: int = 15,
            ephemeral_message: str | None = None,
        ) -> Iterator[str]:
            self.calls += 1
            if self.calls == 1:
                yield "partial-output\n"
                raise RuntimeError("temporary provider outage")
            self.resumed_messages = messages
            yield "DIRECT_RESUME_OK"

    # Given: a canonical direct task fails after emitting partial output.
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    orchestrator = RecoveringDirectOrchestrator()
    runtime = AgentRuntime(orchestrator, task_runner=runner)
    messages = [
        {"role": "system", "content": "PROJECT_CONTEXT_ALPHA"},
        {"role": "user", "content": "Finish this interactive task"},
    ]
    tracked = runtime.start_stream(messages, target_model="qwen3.6:latest")
    assert tracked.task_id is not None
    with pytest.raises(RuntimeError, match="temporary provider outage"):
        _ = list(tracked.chunks)

    # When: the caller resumes the returned direct task ID.
    assert runtime.resume_task(tracked.task_id, target_model="qwen3.6:latest") is True
    tasks = cast(dict[str, _ResumedTask], getattr(runner, "_tasks"))
    resumed = tasks[tracked.task_id]
    thread = cast(_ThreadLike | None, getattr(resumed, "_thread"))
    assert thread is not None
    thread.join(timeout=2)

    # Then: original context and partial output reach the resumed completion.
    restored = "\n".join(message["content"] for message in orchestrator.resumed_messages)
    record = runner.state_store.get_task(tracked.task_id)
    assert "PROJECT_CONTEXT_ALPHA" in restored
    assert "partial-output" in restored
    assert resumed.output == "partial-output\nDIRECT_RESUME_OK"
    assert record is not None
    assert record["status"] == "done"


def test_runtime_binds_itself_to_orchestrator():
    orchestrator = FakeOrchestrator()

    runtime = AgentRuntime(orchestrator)

    assert orchestrator.agent_runtime is runtime


def test_runtime_run_max_uses_orchestrator_engine():
    orchestrator = FakeOrchestrator()
    engine = MagicMock()
    _mock_method(engine, "run").return_value = "max-result"
    orchestrator.max_engine = engine
    runtime = AgentRuntime(orchestrator)

    task_spec: dict[str, object] = {"prompt": "inspect"}

    assert runtime.run_max(task_spec) == "max-result"
    _assert_called_once_with(engine, "run", task_spec, orchestrator=orchestrator)


def test_runtime_run_max_persists_a_direct_execution_without_nesting_bound_tasks(tmp_path: Path):
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    orchestrator = BoundOrchestrator()
    result = SimpleNamespace(final_output="max-result", error=None)
    engine = MagicMock()
    _mock_method(engine, "run").return_value = result
    orchestrator.max_engine = engine
    runtime = AgentRuntime(orchestrator, task_runner=SimpleNamespace(state_store=store))

    assert runtime.run_max({"prompt": "inspect"}) is result

    tasks = store.list_tasks(10)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "done"
    assert tasks[0]["output"] == "max-result"
    assert [event["event_type"] for event in store.list_execution_events(tasks[0]["task_id"])] == [
        "max_execution_registered",
        "max_execution_started",
        "max_execution_completed",
    ]
    _assert_called_once_with(engine, "run", {"prompt": "inspect"}, orchestrator=orchestrator)


def test_runtime_run_max_reuses_an_existing_state_graph_task_binding(tmp_path: Path):
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    _ = store.create_task("task-bound", "inspect", "pending", "2026-01-01T00:00:00")
    _ = store.transition("task-bound", "running")
    orchestrator = BoundOrchestrator()
    result = SimpleNamespace(final_output="max-result", error=None)
    engine = MagicMock()
    _mock_method(engine, "run").return_value = result
    orchestrator.max_engine = engine
    runtime = AgentRuntime(orchestrator, task_runner=SimpleNamespace(state_store=store))

    with orchestrator.bind_task_execution("task-bound", store):
        assert runtime.run_max({"prompt": "inspect"}) is result

    tasks = store.list_tasks(10)
    assert [task["task_id"] for task in tasks] == ["task-bound"]
    assert store.list_execution_events("task-bound") == []
    _assert_called_once_with(engine, "run", {"prompt": "inspect"}, orchestrator=orchestrator)


@pytest.mark.asyncio
async def test_runtime_run_parallel_goals_constructs_bound_multiplexer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import antigravity_k.engine.multiplexer as multiplexer_module

    orchestrator = FakeOrchestrator()
    runtime = AgentRuntime(orchestrator)
    fake_multiplexer = MagicMock()
    fake_multiplexer.run_parallel_goals = AsyncMock(return_value=[{"status": "success"}])
    multiplexer_class = MagicMock(return_value=fake_multiplexer)
    monkeypatch.setattr(multiplexer_module, "Multiplexer", multiplexer_class)

    result = await runtime.run_parallel_goals(
        [{"task_id": "task-1", "instruction": "inspect"}],
        project_root=str(tmp_path),
    )

    assert result == [{"status": "success"}]
    multiplexer_class.assert_called_once_with(str(tmp_path), agent_runtime=runtime)
    _assert_awaited_once_with(
        fake_multiplexer,
        "run_parallel_goals",
        [{"task_id": "task-1", "instruction": "inspect"}],
        base_branch="main",
    )


def test_runtime_goal_contract_uses_injected_goal_runner():
    class GoalRunner:
        def run(self, objective: str, context: Mapping[str, object] | None = None) -> dict[str, object]:
            return {"objective": objective, "context": context}

        def render_markdown(self, report: Mapping[str, object]) -> str:
            return f"contract:{report['objective']}"

    runtime = AgentRuntime(FakeOrchestrator(), goal_runner=GoalRunner())

    assert runtime.goal_contract("ship the feature", context={"tool_count": 4}) == "contract:ship the feature"


def test_slash_goal_uses_bound_agent_runtime():
    from antigravity_k.engine.slash_commands import SlashCommandRegistry

    class Runtime:
        def goal_contract(self, objective: str, context: Mapping[str, object] | None = None) -> str:
            tool_count = context["tool_count"] if context is not None else 0
            return f"runtime-goal:{objective}:{tool_count}"

    registry = SlashCommandRegistry(tool_registry=["tool"], agent_runtime=Runtime())

    assert registry.execute("/goal ship the feature") == "runtime-goal:ship the feature:1"


def test_slash_natural_language_uses_bound_agent_runtime():
    from antigravity_k.engine.slash_commands import SlashCommandRegistry

    calls: list[dict[str, object]] = []

    class ModelManager:
        def get_model_info(self):
            return {"active_model": "qwen3.6:latest"}

    class Runtime:
        def complete(self, messages: list[dict[str, str]], target_model: str) -> str:
            calls.append({"messages": messages, "target_model": target_model})
            return "runtime-complete"

    registry = SlashCommandRegistry(model_manager=ModelManager(), agent_runtime=Runtime())

    assert registry.execute("summarize the project") == "runtime-complete"
    assert calls == [
        {
            "messages": [{"role": "user", "content": "summarize the project"}],
            "target_model": "qwen3.6:latest",
        },
    ]


def test_legacy_slash_registry_receives_bound_agent_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WS-03 F3: slash registry is project-scoped and tracks that project's agent_runtime."""
    from antigravity_k.api import dependencies
    from antigravity_k.api.contracts.execution_context import RequestExecutionContext
    from antigravity_k.api.project_binding import (
        reset_bound_request_execution_context,
        set_bound_request_execution_context,
    )
    from antigravity_k.engine.project_registry import ProjectRegistry

    storage = tmp_path / "projects.json"
    monkeypatch.setattr(
        "antigravity_k.engine.project_registry._DEFAULT_STORAGE_PATH",
        storage,
    )
    import antigravity_k.engine.project_registry as preg

    monkeypatch.setattr(preg, "_global_registry", None)
    from antigravity_k.config import config

    monkeypatch.setattr(config.paths, "project_root", tmp_path.resolve())
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)

    dependencies.reset_runtime_dependencies()
    reset_bound_request_execution_context()

    project = tmp_path / "proj"
    project.mkdir()
    registry = ProjectRegistry(storage_path=storage)
    monkeypatch.setattr(preg, "_global_registry", registry)
    rec = registry.add_project("proj", str(project))

    set_bound_request_execution_context(
        RequestExecutionContext(
            schema_version=1,
            request_id="req",
            task_id=None,
            project_id=rec.id,
            canonical_project_root=str(project.resolve()),
            conversation_id="conv",
            conversation_revision=0,
            actor_subject="test",
            session_id="sess",
            model_id="m1",
            correlation_id="",
            project_name="n",
        )
    )

    from antigravity_k.api.dependencies import acquire_project_runtime, get_slash_registry

    runtime_handle = acquire_project_runtime()
    registry_obj = get_slash_registry()
    assert getattr(registry_obj, "_agent_runtime") is runtime_handle.agent_runtime

    dependencies.reset_runtime_dependencies()
    reset_bound_request_execution_context()


def test_runtime_submits_background_work_through_same_orchestrator_and_model():
    orchestrator = FakeOrchestrator()
    runner = FakeTaskRunner()
    runtime = AgentRuntime(orchestrator, task_runner=runner)

    task_id = runtime.submit_task(
        "inspect the project",
        context={"expected_tools": ["read_file"]},
        idempotency_key="request-001",
    )

    assert task_id == "task_runtime_001"
    assert len(runner.submit_calls) == 1
    submitted = runner.submit_calls[0]
    assert submitted["prompt"] == "inspect the project"
    assert submitted["orchestrator"] is orchestrator
    assert submitted["target_model"] == "qwen3.6:latest"
    assert submitted["use_worktree"] is False
    assert submitted["idempotency_key"] == "request-001"
    assert submitted["owner_subject"] == "loopback"
    context = submitted["context"]
    assert isinstance(context, dict)
    assert context["expected_tools"] == ["read_file"]
    plan = cast(dict[str, object], context["task_plan"])
    assert isinstance(plan, dict)
    assert plan["objective"] == "inspect the project"
    assert plan["steps"]
    judgment = cast(dict[str, object], plan["judgment"])
    assert judgment["decision"] in {"plan_first", "execute_with_verification"}


def test_runtime_requires_task_runner_for_background_work():
    runtime = AgentRuntime(FakeOrchestrator())

    with pytest.raises(RuntimeError, match="task runner"):
        _ = runtime.submit_task("run later")


def test_runtime_resumes_background_work_through_same_orchestrator():
    orchestrator = FakeOrchestrator()
    runner = FakeTaskRunner()
    runtime = AgentRuntime(orchestrator, task_runner=runner)

    assert runtime.resume_task("task_runtime_001") is True
    assert runner.submit_calls == [
        {
            "task_id": "task_runtime_001",
            "orchestrator": orchestrator,
            "target_model": "qwen3.6:latest",
            "owner_subject": None,
        },
    ]


def test_background_task_route_uses_canonical_runtime(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    calls: list[dict[str, object]] = []

    class Runtime:
        def submit_task(self, **kwargs: object) -> str:
            calls.append(kwargs)
            return "task_route_001"

    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: Runtime())

    result = task_api.submit_background_task(
        TaskSubmitRequest(
            prompt="inspect the project",
            context={"expected_tools": ["read_file"]},
            model="",
            idempotency_key="route-001",
        ),
        StarletteRequest({"type": "http", "method": "POST", "path": "/api/tasks/submit", "headers": []}),
    )

    assert result.model_dump() == {"status": "submitted", "task_id": "task_route_001"}
    # WS-01: submit context는 immutable project binding 필드가 merge된다.
    assert len(calls) == 1
    call = calls[0]
    assert call["prompt"] == "inspect the project"
    assert call["target_model"] == ""
    assert call["use_worktree"] is False
    assert call["idempotency_key"] == "route-001"
    assert call["owner_subject"] == "anonymous"
    assert call["context"]["expected_tools"] == ["read_file"]
    assert call["context"]["project_id"] == "default"
    assert call["context"]["actor_subject"] == "anonymous"


def test_task_api_resume_route_uses_canonical_runtime(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    resumed_task_ids: list[str] = []

    class Runtime:
        def resume_task(self, task_id: str, owner_subject: str | None = None) -> bool:
            _ = owner_subject
            resumed_task_ids.append(task_id)
            return True

    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: Runtime())

    result = task_api.resume_task(
        "task_runtime_001",
        StarletteRequest(
            {"type": "http", "method": "POST", "path": "/api/tasks/task_runtime_001/resume", "headers": []}
        ),
    )

    assert result.model_dump() == {"status": "resumed", "task_id": "task_runtime_001"}
    assert resumed_task_ids == ["task_runtime_001"]


def test_task_api_views_use_canonical_runtime(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    class Runtime:
        def get_task_status(self, task_id: str, owner_subject: str | None = None) -> dict[str, object] | None:
            _ = owner_subject
            return {"task_id": task_id, "status": "failed"}

        def list_tasks(self, limit: int, owner_subject: str | None = None) -> list[dict[str, object]]:
            _ = owner_subject
            task: dict[str, object] = {"task_id": "direct_001", "status": "failed"}
            return [task][:limit]

        def get_task_output(self, task_id: str, owner_subject: str | None = None) -> str | None:
            _ = owner_subject
            return "partial-output" if task_id == "direct_001" else None

    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: Runtime())

    request = StarletteRequest({"type": "http", "method": "GET", "path": "/", "headers": []})
    status = task_api.get_task_status("direct_001", request)
    tasks = task_api.list_tasks(request, limit=1)
    output = task_api.get_task_output("direct_001", request)

    assert status.data == {"task_id": "direct_001", "status": "failed"}
    assert tasks.data == [{"task_id": "direct_001", "status": "failed"}]
    assert output.model_dump() == {"status": "ok", "task_id": "direct_001", "output": "partial-output"}


@pytest.mark.asyncio
async def test_agent_stream_route_emits_direct_task_id_before_chunks(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import agent_stream_api as legacy

    class Runtime:
        orchestrator: object | None = None

        def resolve_model(self) -> str:
            return "qwen3-test"

        def start_stream(self, messages: list[dict[str, str]], target_model: str = "") -> TrackedStream:
            assert messages == [{"role": "user", "content": "track this"}]
            assert target_model == "qwen3-test"
            return TrackedStream(task_id="direct_001", chunks=iter(["runtime-response"]))

    monkeypatch.setattr(legacy, "get_agent_runtime", lambda: Runtime())

    response = await legacy.stream_agent(q="track this")
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else str(chunk) for chunk in chunks)

    assert '"task_id": "direct_001"' in body
    assert "runtime-response" in body


@pytest.mark.asyncio
async def test_chat_stream_route_uses_canonical_runtime(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import chat
    from antigravity_k.engine.protocol_translator import ProtocolTranslator

    calls: list[dict[str, object]] = []

    class Runtime:
        def stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
            calls.append({"messages": messages, "target_model": target_model})
            yield "runtime-response"

    class Request:
        # WS-01: route는 request.state(auth_subject/execution_context)와 headers를 읽는다.
        state = SimpleNamespace()
        headers = {}

        async def json(self) -> dict[str, object]:
            return {
                "model": "test-combo",
                "messages": [{"role": "user", "content": "Explain the runtime"}],
                "stream": True,
                "agent_mode": True,
            }

    manager = MagicMock()
    _mock_method(manager, "generate").return_value = "GENERAL"
    monkeypatch.setattr(chat, "get_agent_runtime", lambda: Runtime())

    response = await chat.chat_completions(
        cast(StarletteRequest, cast(object, Request())),
        cast(ModelManager, cast(object, manager)),
        ProtocolTranslator(),
    )
    chunks = [chunk async for chunk in cast(_StreamingResponse, cast(object, response)).body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else str(chunk) for chunk in chunks)

    assert "runtime-response" in body
    assert len(calls) == 1
    messages = calls[0]["messages"]
    assert isinstance(messages, list)
    assert messages[-1] == {"role": "user", "content": "Explain the runtime"}
    assert calls[0]["target_model"] == "test-combo"


@pytest.mark.asyncio
async def test_chat_stream_keeps_generator_context_across_threadpool(monkeypatch: pytest.MonkeyPatch):
    import contextvars

    from antigravity_k.api.routes import chat
    from antigravity_k.engine.protocol_translator import ProtocolTranslator

    marker = contextvars.ContextVar("chat_stream_marker", default="unset")

    class Runtime:
        def stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
            del messages, target_model
            token = marker.set("active")
            try:
                yield "runtime-response"
            finally:
                marker.reset(token)

    class Request:
        # WS-01: route는 request.state(auth_subject/execution_context)와 headers를 읽는다.
        state = SimpleNamespace()
        headers = {}

        async def json(self) -> dict[str, object]:
            return {
                "model": "test-combo",
                "messages": [{"role": "user", "content": "Explain the runtime"}],
                "stream": True,
                "agent_mode": True,
            }

    manager = MagicMock()
    _mock_method(manager, "generate").return_value = "GENERAL"
    monkeypatch.setattr(chat, "get_agent_runtime", lambda: Runtime())

    response = await chat.chat_completions(
        cast(StarletteRequest, cast(object, Request())),
        cast(ModelManager, cast(object, manager)),
        ProtocolTranslator(),
    )
    chunks = [chunk async for chunk in cast(_StreamingResponse, cast(object, response)).body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else str(chunk) for chunk in chunks)

    assert "runtime-response" in body
    assert "different Context" not in body
