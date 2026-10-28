from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api.routes import task_api
from antigravity_k.api.task_models import TaskEvent, TaskEventsResponse, TaskStatusResponse
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.direct_task_execution import MaxEnginePort
from antigravity_k.engine.task_events import ExecutionEventRecord
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskStateStore


class BoundOrchestrator:
    @property
    def max_engine(self) -> MaxEnginePort | None:
        return None

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        prompt = str(messages[-1]["content"])
        context = (target_model, max_steps, ephemeral_message)
        yield f"{prompt.upper()}:{context[0]}"

    def get_model_for_role(self, role: str) -> str:
        assert role == "default"
        return "qwen3.6:latest"


@contextmanager
def _runtime(db_path: str, monkeypatch: pytest.MonkeyPatch) -> Generator[AgentRuntime, None, None]:
    runner = BackgroundTaskRunner(db_path=db_path)
    runtime = AgentRuntime(BoundOrchestrator(), task_runner=runner)
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)
    yield runtime


@pytest.fixture
def client() -> TestClient:
    application = FastAPI()

    @application.middleware("http")
    async def set_loopback_subject(request, call_next):
        request.state.auth_subject = "loopback"
        return await call_next(request)

    application.include_router(task_api.router)
    return TestClient(application)


def test_two_concurrent_ledger_tasks_have_zero_cross_talk(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "tasks.db")
    with _runtime(db_path, monkeypatch) as runtime:
        first = runtime.submit_task("first task", target_model="qwen3.6:latest")
        second = runtime.submit_task("second task", target_model="qwen3.6:latest")
        _wait_for_terminal(client, first)
        _wait_for_terminal(client, second)
        store = TaskStateStore(db_path)
        _ = store.append_execution_event(first, "task.marker", json.dumps({"marker": "first"}))
        _ = store.append_execution_event(second, "task.marker", json.dumps({"marker": "second"}))

        first_events = _events(client, first)
        second_events = _events(client, second)

    assert {event.task_id for event in first_events.events} == {first}
    assert {event.task_id for event in second_events.events} == {second}
    assert first_events.events[-1].payload == {"marker": "first"}
    assert second_events.events[-1].payload == {"marker": "second"}


def test_reconnect_after_sequence_has_no_loss_or_duplicate(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "tasks.db")
    with _runtime(db_path, monkeypatch) as runtime:
        task_id = runtime.submit_task("reconnect task", target_model="qwen3.6:latest")
        _wait_for_terminal(client, task_id)
        store = TaskStateStore(db_path)
        for marker in ("one", "two", "three"):
            _ = store.append_execution_event(task_id, "task.marker", json.dumps({"marker": marker}))
        full = _events(client, task_id).events
        split = len(full) // 2
        before = full[:split]
        after = _events(client, task_id, after_sequence=before[-1].sequence).events
        replayed = before + after

    assert [event.sequence for event in replayed] == [event.sequence for event in full]
    assert replayed == full


def test_store_reopen_preserves_task_and_event_resume_state(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "tasks.db")
    with _runtime(db_path, monkeypatch) as runtime:
        task_id = runtime.submit_task("restart task", target_model="qwen3.6:latest")
        _wait_for_terminal(client, task_id)
        before = _events(client, task_id)
        before_status = _status(client, task_id).data

    reopened_store = TaskStateStore(db_path)
    reopened_record = reopened_store.get_task(task_id)
    assert reopened_record is not None
    assert reopened_record["status"] == "done"
    assert reopened_record["prompt"] == before_status["prompt"]
    assert len(reopened_record["output"]) == before_status["output_length"]
    # 저장소는 생산자가 쓴 payload_json 문자열을 그대로 보존하고 API 는 파싱한 payload 를 준다.
    # 문자열 직렬화 형식(공백)이 아니라 같은 이벤트·같은 의미인지 비교한다 — task.status 도 포함.
    reopened_events = reopened_store.list_execution_events(task_id)
    assert [_semantic(record) for record in reopened_events] == [_semantic(_record(event)) for event in before.events]
    status_events = [json.loads(r["payload_json"]) for r in reopened_events if r["event_type"] == "task.status"]
    assert status_events, "상태 전이 이벤트가 재개방 후에도 보존돼야 한다"
    assert status_events[-1]["to_status"] == "done"
    assert status_events[-1]["terminal"] is True
    assert [e["to_version"] for e in status_events] == list(range(1, len(status_events) + 1))
    assert TaskStateStore(db_path).list_execution_events(task_id) == reopened_events  # 읽기는 이벤트를 만들지 않는다


def test_legacy_and_v2_events_have_replay_parity(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        table = (
            "CREATE TABLE task_execution_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "task_id TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        _ = connection.execute(table)
        insert = "INSERT INTO task_execution_events (task_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)"
        _ = connection.execute(
            insert,
            ("task-legacy", "legacy_event", json.dumps({"legacy": True}), "2026-01-01T00:00:00Z"),
        )

    store = TaskStateStore(str(db_path))
    _ = store.append_execution_event("task-legacy", "v2_event", json.dumps({"v2": True}))
    records = store.list_execution_events("task-legacy")
    projected = [
        {
            "sequence": record["sequence"],
            "schema_version": record["schema_version"],
            "event_type": record["event_type"],
            "payload": json.loads(record["payload_json"]),
            "task_id": record["task_id"],
        }
        for record in records
    ]

    assert projected == [
        {
            "sequence": 1,
            "schema_version": 1,
            "event_type": "legacy_event",
            "payload": {"legacy": True},
            "task_id": "task-legacy",
        },
        {
            "sequence": 2,
            "schema_version": 2,
            "event_type": "v2_event",
            "payload": {"v2": True},
            "task_id": "task-legacy",
        },
    ]


def _events(client: TestClient, task_id: str, after_sequence: int = 0) -> TaskEventsResponse:
    response = client.get(
        f"/api/tasks/{task_id}/events",
        params={"after_sequence": after_sequence, "limit": 500},
    )
    assert response.status_code == 200
    return TaskEventsResponse.model_validate(response.json())


def _status(client: TestClient, task_id: str) -> TaskStatusResponse:
    response = client.get(f"/api/tasks/{task_id}/status")
    assert response.status_code == 200
    return TaskStatusResponse.model_validate(response.json())


def _semantic(record: ExecutionEventRecord) -> tuple[object, ...]:
    data: dict[str, object] = dict(record)
    payload = json.loads(str(data.pop("payload_json")))
    return (tuple(sorted(data.items())), json.dumps(payload, sort_keys=True))


def _record(event: TaskEvent) -> ExecutionEventRecord:
    return ExecutionEventRecord(
        sequence=event.sequence,
        schema_version=event.schema_version,
        task_id=event.task_id,
        step_id=event.step_id,
        agent_id=event.agent_id,
        parent_id=event.parent_id,
        tool_call_id=event.tool_call_id,
        approval_id=event.approval_id,
        resource_job_id=event.resource_job_id,
        correlation_id=event.correlation_id,
        event_type=event.event_type,
        payload_json=json.dumps(event.payload, separators=(",", ":")),
        created_at=event.created_at,
    )


def _wait_for_terminal(client: TestClient, task_id: str) -> None:
    for _ in range(100):
        if _status(client, task_id).data["status"] in {"done", "failed", "cancelled"}:
            return
    raise AssertionError(f"task did not reach terminal state: {task_id}")
