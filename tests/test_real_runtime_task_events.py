from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from tests.real_runtime_task_event_helpers import ExecutionLane, make_lane

if TYPE_CHECKING:
    from antigravity_k.engine.task_state_types import TaskStatusName


class LifecyclePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
    from_status: str
    from_version: int
    terminal: bool
    to_status: str
    to_version: int


@pytest.fixture
def lane_root(tmp_path: Path) -> Iterator[Path]:
    with TemporaryDirectory(prefix="ssak-real-runtime-", dir=tmp_path) as directory:
        yield Path(directory)


def assert_terminal(lane: ExecutionLane, task_id: str, expected: TaskStatusName) -> None:
    store = lane.runner.state_store
    record = store.get_task(task_id)
    assert record is not None and record["status"] == expected
    events = store.list_execution_events(task_id)
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    lifecycle = [
        LifecyclePayload.model_validate_json(e["payload_json"]) for e in events if e["event_type"] == "task.status"
    ]
    assert [event.to_status for event in lifecycle] == ["running", "running", expected]
    for previous, current in zip(lifecycle, lifecycle[1:], strict=False):
        assert current.from_status == previous.to_status
        assert current.from_version == previous.to_version
    for event in lifecycle:
        assert event.to_version == event.from_version + 1
    terminal = [event for event in lifecycle if event.terminal]
    assert len(terminal) == 1
    assert terminal[0].from_status == "running"
    assert terminal[0].to_status == expected
    assert terminal[0].to_version == terminal[0].from_version + 1
    assert lifecycle[0].from_status == "pending" and lifecycle[0].to_status == "running"
    assert record["version"] == terminal[0].to_version
    cursor = events[len(events) // 2]["sequence"]
    assert store.list_execution_events(task_id, after_sequence=cursor) == [e for e in events if e["sequence"] > cursor]
    assert store.transition(task_id, expected, record_event=True) is True
    assert store.list_execution_events(task_id) == events
    assert store.get_task(task_id) == record
    from antigravity_k.engine.task_state_types import InvalidTaskTransitionError

    with pytest.raises(InvalidTaskTransitionError):
        _ = store.transition(task_id, "done", output="QA forbidden overwrite", record_event=True)
    assert store.list_execution_events(task_id) == events
    assert store.get_task(task_id) == record


def submit_and_wait(lane: ExecutionLane) -> str:
    task_id = lane.runtime.submit_task(
        "도구 없이 13+29의 숫자 하나", target_model="qa-local", idempotency_key="qa-real-terminal"
    )
    result = lane.runtime.wait_task(task_id, timeout=10)
    assert result is not None and result["status"] in {"done", "failed", "cancelled"}
    assert lane.model.entered.is_set(), "actual ToolLoop reached the substituted model port"
    return task_id


def test_real_graph_success_has_one_terminal_event_and_successful_handoff(
    lane_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = make_lane(lane_root, monkeypatch)
    task_id = submit_and_wait(lane)
    assert_terminal(lane, task_id, "done")
    assert lane.runtime.get_task_output(task_id) == "42"
    record = lane.runner.state_store.get_task(task_id)
    assert record is not None and record["output"] == "42"
    from antigravity_k.engine.task_state_store import TaskStateStore

    reopened = TaskStateStore(str(lane_root / "tasks.db"))
    assert reopened.get_task(task_id) == record
    assert reopened.list_execution_events(task_id) == lane.runner.state_store.list_execution_events(task_id)
    assert len(lane.outcomes) == 1
    assert lane.outcomes[0].success is True and lane.outcomes[0].completion_reason == "done"
    transitions = [
        e for e in lane.runner.state_store.list_execution_events(task_id) if e["event_type"] == "state_transition"
    ]
    to_states = [TypeAdapter(dict[str, JsonValue]).validate_json(e["payload_json"])["to_state"] for e in transitions]
    assert "agent_execute" in to_states and to_states[-1] == "complete"
    requests = list(lane.model.requests)
    assert (
        lane.runtime.submit_task("ignored retry", target_model="qa-local", idempotency_key="qa-real-terminal")
        == task_id
    )
    assert lane.model.requests == requests
    assert len(lane.outcomes) == 1
    assert_terminal(lane, task_id, "done")


def test_real_graph_generation_failure_has_one_terminal_event(lane_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lane = make_lane(lane_root, monkeypatch, fail=True)
    task_id = submit_and_wait(lane)
    assert_terminal(lane, task_id, "failed")
    assert len(lane.outcomes) == 1
    assert lane.outcomes[0].success is False and lane.outcomes[0].completion_reason == "failed"


def test_real_graph_cancel_cannot_be_overwritten_by_late_model_result(
    lane_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = make_lane(lane_root, monkeypatch, block=True)
    task_id = lane.runtime.submit_task("도구 없이 13+29의 숫자 하나", target_model="qa-local")
    try:
        assert lane.model.entered.wait(timeout=10)
        assert lane.runtime.cancel_task(task_id) is True
    finally:
        lane.model.release.set()
        result = lane.runtime.wait_task(task_id, timeout=10)
    assert result is not None and result["status"] == "cancelled"
    assert_terminal(lane, task_id, "cancelled")
    assert len(lane.outcomes) == 1
    assert lane.outcomes[0].success is False and lane.outcomes[0].completion_reason == "cancelled"


def test_real_graph_terminal_event_insert_failure_rolls_back_status(
    lane_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = make_lane(lane_root, monkeypatch)
    with sqlite3.connect(lane_root / "tasks.db") as connection:
        _ = connection.execute(
            "CREATE TRIGGER qa_terminal_event_reject BEFORE INSERT ON task_execution_events "
            + "WHEN NEW.event_type = 'task.status' AND json_extract(NEW.payload_json, '$.to_status') = 'done' "
            + "BEGIN SELECT RAISE(ABORT, 'QA terminal event reject'); END"
        )
    task_id = submit_and_wait(lane)
    assert_terminal(lane, task_id, "failed")
    assert len(lane.outcomes) == 1 and lane.outcomes[0].success is False
    assert lane.outcomes[0].error == "Task completion status could not be persisted."
