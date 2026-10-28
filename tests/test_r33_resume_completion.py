"""r33: pause -> restart -> resume -> *normal completion* without repeated banners, steps or effects.

Fake transport only. The orchestrator emits the real banner shapes before content, like the
production stream, and continues from the assistant turn (prior output) that resume supplies.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast, final

from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.preflight_validator import PreflightValidator
from antigravity_k.engine.task_runner import BackgroundTask, BackgroundTaskRunner, is_orchestrator_banner_chunk

TOTAL = 10
BANNERS = (ProgressChunk("🛡️ **[정밀 엔지니어링 모드]**\n\n"), "🏢 ", "**[CEO]** 👨‍💻 **WORKER** 위임 (`coding-swarm`)\n\n")


def _line(i: int) -> str:
    return f"{i + 1}. synthetic item {i + 1}\n"


@final
class _BannerOrchestrator:
    vault_engine: object | None = None

    def __init__(self, effects: list[int]) -> None:
        self.effects = effects
        self.gate = threading.Semaphore(0)
        self.seen_messages: list[list[dict[str, str]]] = []
        self.preflight_inputs: list[str] = []

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        _ = target_model
        self.seen_messages.append([dict(m) for m in messages])
        user_text = [m["content"] for m in messages if m["role"] == "user"][-1]
        self.preflight_inputs.append(user_text)
        ok, reason, _ = PreflightValidator().validate(user_text)
        if not ok:
            yield f"✈️ [Preflight 거부]\n{reason}"
            return
        prior = "".join(m["content"] for m in messages if m["role"] == "assistant")
        start = prior.count(". synthetic item ")
        yield from BANNERS
        for i in range(start, TOTAL):
            assert self.gate.acquire(timeout=5)
            self.effects.append(i)
            yield _line(i)

    def release(self, n: int) -> None:
        for _ in range(n):
            self.gate.release()


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


def _db_checkpoints(db: str, task_id: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM task_checkpoints WHERE task_id=?", (task_id,)).fetchone()[0])


def _pause_after(runner: BackgroundTaskRunner, orch: _BannerOrchestrator, task_id: str, n: int) -> None:
    base = len(orch.effects)
    orch.release(n)
    _wait(lambda: len(orch.effects) >= base + n)
    assert runner.pause_task(task_id) == "pausing"
    orch.release(1)
    _wait(lambda: _status(runner, task_id) == "paused")


def test_restart_resume_completes_without_duplicates(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    effects: list[int] = []
    orch = _BannerOrchestrator(effects)
    runner = BackgroundTaskRunner(db_path=db)
    # the item text deliberately contains "format" — r32's preflight false-positive trigger
    prompt = "Synthetic r33 task: write 10 numbered items; keep a consistent format for each line."
    task_id = runner.submit_task(prompt, orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")
    _pause_after(runner, orch, task_id, 4)
    paused_checkpoint = runner.state_store.get_last_checkpoint(task_id)
    assert paused_checkpoint is not None
    assert "[정밀 엔지니어링 모드]" not in paused_checkpoint["output_so_far"]

    # restart: new runner, same DB
    runner2 = BackgroundTaskRunner(db_path=db)
    info = runner2.get_status(task_id)
    assert info is not None and info["checkpoint_count"] == _db_checkpoints(db, task_id) >= 1
    assert info["resumable"] is True
    orch2 = _BannerOrchestrator(effects)
    assert runner2.resume_task(task_id, orchestrator=orch2, target_model="fake")
    orch2.release(TOTAL)
    _wait(lambda: _status(runner2, task_id) == "done")

    output = runner2.state_store.get_task(task_id)["output"]  # type: ignore[index]
    body = output
    assert body.count("[정밀 엔지니어링 모드]") == 0
    assert body.count("WORKER** 위임") == 1
    assert body.count("🏢") == 1
    assert body == "".join(BANNERS[1:]) + "".join(_line(i) for i in range(TOTAL))
    # Typed status is preserved once per execution, outside both body and resume cursor.
    progress = [
        json.loads(event["payload_json"])
        for event in runner2.state_store.list_execution_events(task_id)
        if event["event_type"] == "task.stream.progress"
    ]
    assert progress == [
        {"kind": "progress", "source": "ProgressChunk", "text": str(BANNERS[0]), "step": 0, "resumed": False},
        {
            "kind": "progress",
            "source": "ProgressChunk",
            "text": str(BANNERS[0]),
            "step": paused_checkpoint["step"],
            "resumed": True,
        },
    ]
    items = [line for line in output.splitlines() if ". synthetic item " in line]
    assert items == [_line(i).rstrip("\n") for i in range(TOTAL)]  # nothing missing, nothing repeated
    assert effects == list(range(TOTAL))  # each side effect exactly once
    assert "Preflight 거부" not in output
    # the resumed user text is the user's request + fixed instruction, never the model's prior output
    resumed_user = orch2.preflight_inputs[0]
    assert ". synthetic item" not in resumed_user
    assert orch2.seen_messages[0][0]["role"] == "assistant"
    final = runner2.get_status(task_id)
    assert final is not None and final["checkpoint_count"] == _db_checkpoints(db, task_id)


def test_list_tasks_reports_stored_checkpoint_count(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    orch = _BannerOrchestrator([])
    runner = BackgroundTaskRunner(db_path=db)
    task_id = runner.submit_task("Synthetic r33 list task", orchestrator=orch, target_model="fake")
    _wait(lambda: _status(runner, task_id) == "running")
    _pause_after(runner, orch, task_id, 2)
    runner2 = BackgroundTaskRunner(db_path=db)
    rows = [r for r in runner2.list_tasks() if r["task_id"] == task_id]
    assert rows and rows[0]["checkpoint_count"] == _db_checkpoints(db, task_id) >= 1
    assert runner2.get_status("task_absent_r33") is None


def test_cancel_during_approval_wait_is_final(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    runner = BackgroundTaskRunner(db_path=db)
    box: list[str] = []

    @final
    class _ApprovalOrch:
        vault_engine: object | None = None

        def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
            _ = (messages, target_model)
            yield "partial;"
            runner.state_store.transition(box[0], "paused", expected_status="running")

    box.append(runner.submit_task("Synthetic r33 approval task", orchestrator=_ApprovalOrch(), target_model="fake"))
    _wait(lambda: _status(runner, box[0]) == "paused")
    cast(dict[str, BackgroundTask], getattr(runner, "_tasks"))[box[0]].join(timeout=2)
    assert runner.cancel_verdict(box[0]) == "cancelled"
    assert _status(runner, box[0]) == "cancelled"
    # never resurrected: neither this runner nor a restarted one may resume it
    assert runner.resume_task(box[0], orchestrator=_ApprovalOrch(), target_model="fake") is False
    runner2 = BackgroundTaskRunner(db_path=db)
    assert runner2.resume_task(box[0], orchestrator=_ApprovalOrch(), target_model="fake") is False
    assert _status(runner2, box[0]) == "cancelled"
    assert runner2.pause_task(box[0]) == "not_active"


def test_banner_detector_does_not_eat_content() -> None:
    assert is_orchestrator_banner_chunk("🏢 ")
    assert is_orchestrator_banner_chunk("**[CEO]** 👨‍💻 **WORKER** 위임 (`coding-swarm`)\n\n")
    assert not is_orchestrator_banner_chunk("1. 🛡️ 안전한 하루 보내세요\n")
    assert not is_orchestrator_banner_chunk("CEO가 위임한 내용을 설명합니다.")
