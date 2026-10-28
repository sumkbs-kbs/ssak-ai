import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast
from unittest.mock import MagicMock

import pytest

from antigravity_k.api import dependencies
from antigravity_k.engine.benchmark_harness import BenchmarkHarness
from antigravity_k.engine.model_calibration import TaskBenchmarkMetrics
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.task_runner import BackgroundTask, BackgroundTaskRunner


class _Orchestrator:
    vault_engine: object = None

    # WS-03: _build_project_slash_registry reads these off the orchestrator —
    # None values keep SlashCommandRegistry construction lazy-friendly.
    tool_registry: object = None
    context_shaper: object = None
    ctx: object = SimpleNamespace(skill_loader=None, slash_commands=SimpleNamespace(bind_runtime=lambda _rt: None))

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
    ):
        assert messages[0]["role"] == "user"
        assert target_model == "qwen3.6:latest"
        assert max_steps == 15
        assert ephemeral_message is None
        return iter(['<tool_call>{"name":"read_file","arguments":{"file_path":"README.md"}}</tool_call>done'])


def _install_stub_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    model_manager: object | None = None,
) -> None:
    """WS-03: the project runtime factory builds OrchestratorAgent directly —
    patch the class symbol so acquire_project_runtime() wires the stub in.

    model_manager이 주어지면 get_model_manager가 그 인스턴스를 반환하게 유지한다 —
    테스트가 자체 manager mock을 설치한 뒤 이 헬퍼를 호출해도 덮어쓰지 않는다
    (덮어쓰면 harness updater와 테스트 단언 대상 mock이 달라진다).
    """
    monkeypatch.setattr(dependencies, "OrchestratorAgent", lambda **_kw: _Orchestrator())
    if model_manager is not None:
        monkeypatch.setattr(dependencies, "get_model_manager", lambda: model_manager, raising=False)
    else:
        monkeypatch.setattr(dependencies, "get_model_manager", lambda: MagicMock())
    monkeypatch.setattr(dependencies, "_build_project_vault", lambda _root: None)
    monkeypatch.setattr(dependencies, "_attach_project_rag_indexer", lambda _o, _root, *, embedding_binding=None: None)


class _CalibrationMock(Protocol):
    def assert_called_once(self) -> None: ...

    @property
    def call_args(self) -> object: ...


class _RouterMock(Protocol):
    set_task_calibration: _CalibrationMock


def test_canonical_runtime_records_background_task_outcomes_for_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from antigravity_k.engine import task_runner

    manager = cast(ModelManager, MagicMock())
    registry = cast(object, getattr(manager, "_registry"))
    setattr(registry, "_raw", {})
    harness = BenchmarkHarness(manager, db_path=tmp_path / "benchmark.json")
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))

    monkeypatch.setattr(dependencies, "_benchmark_harness", harness, raising=False)
    monkeypatch.setattr(task_runner, "get_task_runner", lambda: runner)
    _install_stub_orchestrator(monkeypatch, model_manager=manager)
    dependencies.reset_runtime_dependencies()

    # WS-03: get_agent_runtime builds through the project runtime factory; pass the
    # tmp project_root so the cache key does not hit the shared registry default.
    task_id = dependencies.get_agent_runtime(project_root=str(tmp_path)).submit_task(
        "inspect README",
        context={"expected_tools": ["read_file"]},
    )
    tasks = cast(dict[str, BackgroundTask], getattr(runner, "_tasks"))
    thread = cast(threading.Thread | None, getattr(tasks[task_id], "_thread"))
    assert thread is not None
    thread.join(timeout=2)

    report = harness.task_report("qwen3.6:latest")
    assert len(report.outcomes) == 1
    assert report.task_success_rate == 1.0
    assert report.tool_accuracy == 1.0


def test_canonical_runtime_records_direct_task_outcomes_for_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from antigravity_k.engine import task_runner

    manager = cast(ModelManager, MagicMock())
    registry = cast(object, getattr(manager, "_registry"))
    setattr(registry, "_raw", {})
    harness = BenchmarkHarness(manager, db_path=tmp_path / "benchmark.json")
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))

    monkeypatch.setattr(dependencies, "_benchmark_harness", harness, raising=False)
    monkeypatch.setattr(task_runner, "get_task_runner", lambda: runner)
    _install_stub_orchestrator(monkeypatch, model_manager=manager)
    dependencies.reset_runtime_dependencies()

    tracked = dependencies.get_agent_runtime(project_root=str(tmp_path)).start_stream(
        [{"role": "user", "content": "inspect README"}],
    )

    assert tracked.task_id is not None
    assert list(tracked.chunks)
    report = harness.task_report("qwen3.6:latest")
    assert len(report.outcomes) == 1
    assert report.outcomes[0].case_id == tracked.task_id
    assert report.task_success_rate == 1.0


def test_canonical_runtime_syncs_task_metrics_to_the_model_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from antigravity_k.engine import task_runner

    manager = cast(ModelManager, MagicMock())
    registry = cast(object, getattr(manager, "_registry"))
    setattr(registry, "_raw", {})
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    harnesses: list[BenchmarkHarness] = []

    def create_harness(
        manager: ModelManager,
        task_calibration_updater: Callable[[str, TaskBenchmarkMetrics | None], None] | None,
    ) -> BenchmarkHarness:
        harness = BenchmarkHarness(
            manager,
            db_path=tmp_path / "benchmark.json",
            task_calibration_updater=task_calibration_updater,
        )
        harnesses.append(harness)
        return harness

    monkeypatch.setattr(dependencies, "_benchmark_harness", None)
    monkeypatch.setattr(dependencies, "BenchmarkHarness", create_harness)
    monkeypatch.setattr(dependencies, "get_model_manager", lambda: manager)
    monkeypatch.setattr(task_runner, "get_task_runner", lambda: runner)
    _install_stub_orchestrator(monkeypatch, model_manager=manager)
    dependencies.reset_runtime_dependencies()

    task_id = dependencies.get_agent_runtime(project_root=str(tmp_path)).submit_task(
        "inspect README",
        context={"benchmark_case_id": "tool-001", "expected_tools": ["read_file"]},
    )
    tasks = cast(dict[str, BackgroundTask], getattr(runner, "_tasks"))
    thread = cast(threading.Thread | None, getattr(tasks[task_id], "_thread"))
    assert thread is not None
    thread.join(timeout=2)

    assert len(harnesses) == 1
    router = cast(_RouterMock, cast(object, manager.router))
    router.set_task_calibration.assert_called_once()
    call_args = router.set_task_calibration.call_args
    assert call_args is not None
    call_values = cast(tuple[object, ...], getattr(call_args, "args"))
    model_name = cast(str, call_values[0])
    metrics = cast(TaskBenchmarkMetrics, call_values[1])
    assert model_name == "qwen3.6:latest"
    assert metrics.outcome_count == 1
    assert metrics.task_success_rate == 1.0
    assert metrics.tool_accuracy == 1.0
