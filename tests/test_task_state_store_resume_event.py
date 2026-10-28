"""prepare_resume 은 상태·버전 변경과 대응 `task.status` 이벤트를 같은 트랜잭션에 남긴다 (CR-14 recovery4).

합성 시험 DB 만 쓴다. 과거 저장소의 누락 이벤트를 채우지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from antigravity_k.engine import task_state_store as store_module
from antigravity_k.engine.task_state_store import TaskStateStore

_DEAD_PID = 2**22 + 12345  # 합성: 살아 있지 않은 소유자


def _orphaned_running(tmp_path: Path) -> TaskStateStore:
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    _ = store.create_task("t", "prompt", "pending", "2026-01-01T00:00:00")
    assert store.transition("t", "running", record_event=True) is True
    with sqlite3.connect(store.db_path) as connection:
        _ = connection.execute("UPDATE task_history SET owner_pid = ? WHERE task_id = 't'", (_DEAD_PID,))
    return store


def _status_events(store: TaskStateStore) -> list[dict[str, object]]:
    events = store.list_execution_events("t")
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1)), "순번은 끊기거나 겹치지 않는다"
    return [json.loads(str(event["payload_json"])) for event in events if event["event_type"] == "task.status"]


def test_resume_transitions_are_recorded_without_gaps_and_match_the_row(tmp_path: Path) -> None:
    store = _orphaned_running(tmp_path)
    assert store.prepare_resume("t") is True
    record = store.get_task("t")
    assert record is not None and record["status"] == "resuming"
    assert store.transition("t", "running", record_event=True) is True

    transitions = [
        (e["from_status"], e["from_version"], e["to_status"], e["to_version"], e["terminal"])
        for e in _status_events(store)
    ]
    assert transitions == [
        ("pending", 0, "running", 1, False),
        ("running", 1, "resuming", 2, False),
        ("resuming", 2, "running", 3, False),
    ]
    final = store.get_task("t")
    assert final is not None and final["status"] == "running"
    assert int(final["version"]) == transitions[-1][3]


def test_event_save_failure_rolls_back_the_state_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _orphaned_running(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("synthetic event write failure")

    monkeypatch.setattr(store_module, "append_execution_event", broken)
    with pytest.raises(sqlite3.OperationalError):
        _ = store.prepare_resume("t")
    record = store.get_task("t")
    assert record is not None
    assert (record["status"], int(record["version"])) == ("running", 1), "상태 변경도 함께 롤백된다"
    assert len(_status_events(store)) == 1


def test_state_update_miss_writes_no_event_and_repeat_calls_do_not_duplicate(tmp_path: Path) -> None:
    store = _orphaned_running(tmp_path)
    assert store.prepare_resume("t") is True
    assert store.prepare_resume("t") is False, "이미 resuming — 실제 전이가 없다"
    assert store.prepare_resume("missing") is False
    assert len(_status_events(store)) == 2


def test_concurrent_resume_requests_have_one_winner_and_one_event(tmp_path: Path) -> None:
    store = _orphaned_running(tmp_path)
    results: list[bool] = []
    barrier = threading.Barrier(4)

    def attempt() -> None:
        barrier.wait()
        results.append(store.prepare_resume("t"))

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == [False, False, False, True]
    events = _status_events(store)
    assert [(e["from_version"], e["to_version"]) for e in events] == [(0, 1), (1, 2)]


def test_prepare_resume_update_exception_rolls_back_everything(tmp_path: Path) -> None:
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    _ = store.create_task("t", "prompt", "pending", "2026-01-01T00:00:00")
    assert store.transition("t", "running", record_event=True) is True
    with sqlite3.connect(store.db_path) as connection:
        _ = connection.execute("UPDATE task_history SET owner_pid = ? WHERE task_id = 't'", (_DEAD_PID,))
        # 시험 계층의 통제된 DB 오류: resuming 으로 바꾸는 UPDATE 자체가 실패한다(행이 없어 False 인 경우와 다름).
        _ = connection.execute(
            "CREATE TRIGGER fail_resume BEFORE UPDATE OF status ON task_history "
            "WHEN NEW.status = 'resuming' BEGIN SELECT RAISE(ABORT, 'synthetic update failure'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="synthetic update failure"):
        _ = store.prepare_resume("t")

    # 새 연결(닫고 다시 연 상태)에서 부분 반영이 없다
    reopened = TaskStateStore(store.db_path)
    record = reopened.get_task("t")
    assert record is not None
    assert (record["status"], int(record["version"])) == ("running", 1)
    events = reopened.list_execution_events("t")
    assert [event["event_type"] for event in events] == ["task.status"]
    with sqlite3.connect(store.db_path) as connection:
        assert connection.in_transaction is False
        _ = connection.execute("DROP TRIGGER fail_resume")
    # 열린 트랜잭션·잠금이 남지 않았다: 이후 정상 작업이 된다
    assert reopened.prepare_resume("t") is True
    payloads = [json.loads(str(event["payload_json"])) for event in reopened.list_execution_events("t")]
    assert [(p["from_version"], p["to_version"]) for p in payloads] == [(0, 1), (1, 2)]
