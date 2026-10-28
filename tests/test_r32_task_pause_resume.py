"""r32: user pause is not cancel — running -> checkpoint -> paused -> resume -> restart -> resume."""

import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast, final

from antigravity_k.engine.task_runner import BackgroundTask, BackgroundTaskRunner

TOTAL = 12
_RESUME = re.compile(r"\[RESUMING FROM CHECKPOINT at step (\d+)\]")


@final
class _StepOrchestrator:
    """Deterministic fake transport: emits step i as 'sI;' and records a side effect per step.

    On resume it reads the checkpoint step from the prompt and continues from there, like a
    well-behaved agent would. Each emitted chunk waits on ``gate`` so the test controls timing.
    """

    vault_engine: object | None = None

    def __init__(self, effects: list[int]) -> None:
        self.effects = effects
        self.gate = threading.Semaphore(0)

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        _ = target_model
        text = "\n".join(m["content"] for m in messages)
        match = _RESUME.search(text)
        start = int(match.group(1)) if match else 0
        for i in range(start, TOTAL):
            assert self.gate.acquire(timeout=5)
            self.effects.append(i)
            yield f"s{i};"

    def release(self, n: int) -> None:
        for _ in range(n):
            self.gate.release()


def _prefix(step: int) -> str:
    return "".join(f"s{i};" for i in range(step))


def _task(runner: BackgroundTaskRunner, task_id: str) -> BackgroundTask:
    return cast(dict[str, BackgroundTask], getattr(runner, "_tasks"))[task_id]


def _wait(predicate, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def _status(runner: BackgroundTaskRunner, task_id: str) -> str:
    record = runner.state_store.get_task(task_id)
    assert record is not None
    return record["status"]


def _pause_after(runner: BackgroundTaskRunner, orch: _StepOrchestrator, task_id: str, n: int) -> None:
    base = len(orch.effects)
    orch.release(n)
    _wait(lambda: len(orch.effects) >= base + n)
    assert runner.pause_task(task_id) == "pausing"
    orch.release(1)  # one more chunk boundary lets the runner observe the pause
    _wait(lambda: _status(runner, task_id) == "paused")


def test_pause_is_not_cancel_and_resume_survives_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    effects: list[int] = []
    orch = _StepOrchestrator(effects)
    runner = BackgroundTaskRunner(db_path=db)
    task_id = runner.submit_task("synthetic r32 step task", orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")

    _pause_after(runner, orch, task_id, 3)
    checkpoint = runner.state_store.get_last_checkpoint(task_id)
    assert checkpoint is not None and checkpoint["step"] >= 3
    assert checkpoint["output_so_far"] == _prefix(checkpoint["step"])
    assert effects == list(range(checkpoint["step"]))  # nothing produced beyond the checkpoint
    info = runner.get_status(task_id)
    assert info is not None and info["checkpoint_count"] >= 1
    assert _task(runner, task_id).status == "paused"
    assert not _task(runner, task_id).cancel_event.is_set()

    # resume #1 in the same process, then pause again
    assert runner.resume_task(task_id, orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")
    _pause_after(runner, orch, task_id, 2)
    cp2 = runner.state_store.get_last_checkpoint(task_id)
    assert cp2 is not None and cp2["step"] > checkpoint["step"]
    assert cp2["output_so_far"] == _prefix(cp2["step"])
    assert effects == list(range(cp2["step"]))

    # "server restart": a brand-new runner on the same DB resumes the paused task
    runner2 = BackgroundTaskRunner(db_path=db)
    orch2 = _StepOrchestrator(effects)
    assert runner2.resume_task(task_id, orchestrator=orch2, target_model="fake")
    orch2.release(TOTAL)
    _wait(lambda: _status(runner2, task_id) == "done")

    final = runner2.state_store.get_task(task_id)
    assert final is not None
    assert final["output"] == "".join(f"s{i};" for i in range(TOTAL))
    assert effects == list(range(TOTAL))  # each step's side effect exactly once, in order
    kinds = [e["event_type"] for e in runner2.state_store.list_execution_events(task_id)]
    assert kinds.count("task.paused") == 2
    seqs = [e["sequence"] for e in runner2.state_store.list_execution_events(task_id)]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_crash_while_running_resumes_from_pause_checkpoint(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    effects: list[int] = []
    orch = _StepOrchestrator(effects)
    runner = BackgroundTaskRunner(db_path=db)
    task_id = runner.submit_task("synthetic r32 crash task", orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")
    _pause_after(runner, orch, task_id, 1)
    assert runner.resume_task(task_id, orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")
    version_before = runner.state_store.get_task(task_id)["version"]  # type: ignore[index]
    # simulate the owning process dying: dead pid owns a running row
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE task_history SET owner_pid = ? WHERE task_id = ?", (2**22 + 12345, task_id))
    runner2 = BackgroundTaskRunner(db_path=db)
    orch2 = _StepOrchestrator(effects)
    assert runner2.resume_task(task_id, orchestrator=orch2, target_model="fake")
    orch2.release(TOTAL)
    _wait(lambda: _status(runner2, task_id) == "done")
    assert runner2.state_store.get_task(task_id)["version"] > version_before  # type: ignore[index]
    assert runner2.state_store.get_task(task_id)["output"] == "".join(f"s{i};" for i in range(TOTAL))  # type: ignore[index]


def test_pause_unknown_or_terminal_is_not_active(tmp_path: Path) -> None:
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    assert runner.pause_task("task_missing") == "not_active"


def test_approval_pause_with_few_chunks_leaves_a_checkpoint(tmp_path: Path) -> None:
    """Root cause of checkpoint_count=0: <10 chunks never checkpointed, so resume had nothing."""
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))

    @final
    class _ApprovalOrch:
        vault_engine: object | None = None

        def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
            _ = (messages, target_model)
            yield "partial;"
            runner.state_store.transition(task_id_box[0], "paused", expected_status="running")  # approval flow pauses

    task_id_box: list[str] = []
    orch = _ApprovalOrch()
    task_id_box.append(runner.submit_task("synthetic approval task", orchestrator=orch, target_model="fake"))
    _wait(lambda: _status(runner, task_id_box[0]) == "paused")
    _task(runner, task_id_box[0]).join(timeout=2)
    cp = runner.state_store.get_last_checkpoint(task_id_box[0])
    assert cp is not None and cp["output_so_far"] == "partial;"
