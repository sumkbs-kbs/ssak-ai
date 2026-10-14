import json
from pathlib import Path

from antigravity_k.api.task_models import TaskEvent, TaskEventsResponse, TaskStreamEnd
from antigravity_k.engine.task_state_store import TaskStateStore


def test_filtered_replay_declares_global_cursor_and_preserves_other_tasks(tmp_path: Path) -> None:
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    for task_id in ("selected", "other"):
        _ = store.create_task(task_id, task_id, "pending", "2026-10-14T00:00:00Z")
    first = store.append_execution_event("selected", "task.status", json.dumps({"status": "running"}))
    _ = store.append_execution_event("other", "task.progress", "{}")
    last = store.append_execution_event("selected", "task.status", json.dumps({"status": "failed"}))
    records = store.list_execution_events("selected")
    events = [TaskEvent.from_record(record) for record in records]
    response = TaskEventsResponse(task_id="selected", events=events, last_sequence=last, has_more=False)
    assert [event.sequence for event in response.events] == [first, last]
    assert last == first + 2
    assert response.sequence_scope == "global"
    assert all(event.sequence_scope == "global" for event in events)
    assert TaskStreamEnd(task_id="selected", last_sequence=last, status="failed").sequence_scope == "global"
    assert len(store.list_execution_events("other")) == 1
    assert [record["sequence"] for record in store.list_execution_events("selected", after_sequence=first)] == [last]
