import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import final

from pydantic import TypeAdapter

from antigravity_k.engine.benchmark_harness import TaskOutcome
from antigravity_k.engine.task_runner import BackgroundTask, BackgroundTaskRunner

_SQL_COUNT_ADAPTER: TypeAdapter[tuple[int]] = TypeAdapter(tuple[int])


@final
class _BlockingOrchestrator:
    vault_engine: None = None

    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self._entered = entered
        self._release = release
        self.calls = 0

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.calls += 1
        self._entered.set()
        assert self._release.wait(timeout=2)
        return iter(str(index) for index in range(10))


@final
class _CountingOrchestrator:
    vault_engine: None = None

    def __init__(self) -> None:
        self.calls = 0

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.calls += 1
        return iter(str(index) for index in range(10))


def test_only_one_runner_executes_when_same_pending_task_is_started_twice(tmp_path: Path) -> None:
    # Given: two runner instances target the same durable pending task.
    db_path = tmp_path / "tasks.db"
    outcomes: list[TaskOutcome] = []
    first = BackgroundTaskRunner(db_path=str(db_path), outcome_recorder=outcomes.append)
    second = BackgroundTaskRunner(db_path=str(db_path), outcome_recorder=outcomes.append)
    task_id = "task-shared-claim"
    _ = first.state_store.create_task(task_id, "perform once", "pending", "2026-01-01T00:00:00")
    _ = first.state_store.save_checkpoint(task_id, 0, "{}", "")
    first_task = BackgroundTask(task_id, "perform once")
    second_task = BackgroundTask(task_id, "perform once")
    entered = threading.Event()
    release = threading.Event()
    first_orchestrator = _BlockingOrchestrator(entered, release)
    second_orchestrator = _CountingOrchestrator()

    # When: the second runner starts while the first runner still owns execution.
    first_thread = threading.Thread(
        target=first._run_task,
        args=(first_task, first_orchestrator, "model"),
    )
    first_thread.start()
    assert entered.wait(timeout=2)
    second_thread = threading.Thread(
        target=second._run_task,
        args=(second_task, second_orchestrator, "model"),
    )
    second_thread.start()
    second_thread.join(timeout=2)
    assert not second_thread.is_alive()
    release.set()
    first_thread.join(timeout=2)
    assert not first_thread.is_alive()

    # Then: only the claim winner executes, checkpoints, and records an outcome.
    record = first.state_store.get_task(task_id)
    assert record is not None
    assert record["status"] == "done"
    assert first_orchestrator.calls == 1
    assert second_orchestrator.calls == 0
    with sqlite3.connect(db_path) as connection:
        checkpoint_count = _SQL_COUNT_ADAPTER.validate_python(
            connection.execute(
                "SELECT COUNT(*) FROM task_checkpoints WHERE task_id = ? AND step = 10",
                (task_id,),
            ).fetchone()
        )
    assert checkpoint_count == (1,)
    assert len(outcomes) == 1
    assert outcomes[0].completion_reason == "done"


def test_only_one_runner_resumes_same_durable_task(tmp_path: Path) -> None:
    # Given: two runner instances can observe the same resumable checkpoint.
    db_path = tmp_path / "tasks.db"
    outcomes: list[TaskOutcome] = []
    first = BackgroundTaskRunner(db_path=str(db_path), outcome_recorder=outcomes.append)
    second = BackgroundTaskRunner(db_path=str(db_path), outcome_recorder=outcomes.append)
    task_id = "task-shared-resume"
    _ = first.state_store.create_task(task_id, "resume once", "paused", "2026-01-01T00:00:00")
    _ = first.state_store.save_checkpoint(task_id, 0, "{}", "")
    orchestrator = _CountingOrchestrator()
    start = threading.Barrier(2)
    results: list[tuple[BackgroundTaskRunner, bool]] = []
    results_lock = threading.Lock()

    def resume(runner: BackgroundTaskRunner) -> None:
        _ = start.wait(timeout=2)
        result = runner.resume_task(task_id, orchestrator=orchestrator, target_model="model")
        with results_lock:
            results.append((runner, result))

    # When: both runners request resume concurrently.
    first_thread = threading.Thread(target=resume, args=(first,))
    second_thread = threading.Thread(target=resume, args=(second,))
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    winner = next(runner for runner, resumed in results if resumed)
    status = winner.wait_task(task_id, timeout=2)

    # Then: the resume CAS admits one execution and one terminal outcome.
    assert sorted(resumed for _, resumed in results) == [False, True]
    assert status is not None
    assert status["status"] == "done"
    assert orchestrator.calls == 1
    assert len(outcomes) == 1
    assert outcomes[0].completion_reason == "done"
