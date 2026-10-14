import json
import typing

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect

from antigravity_k.api.routes import task_api
from antigravity_k.api.task_models import TaskEventsResponse


class FakeTaskRuntime:
    def __init__(self) -> None:
        self.submit_calls: list[dict[str, object]] = []
        self.event_calls: list[tuple[str, int, int]] = []
        self.event_sequences: list[int] = [7]
        # F-35: 취소의 결과는 bool 이 아니라 **이유**다 — 이 시험대는 그 사실을 흔들어 확인한다.
        self.cancel_verdict_result: str = "cancelled"

    def submit_task(self, **kwargs: object) -> str:
        self.submit_calls.append(kwargs)
        return "task-123"

    def get_task_status(self, task_id: str, owner_subject: str | None = None) -> dict[str, object] | None:
        if task_id == "missing" or owner_subject == "foreign":
            return None
        return {
            "task_id": task_id,
            "prompt": "inspect the repository",
            "status": "done",
            "output": "source result",
        }

    def list_task_events(
        self,
        task_id: str,
        after_sequence: int,
        limit: int,
        owner_subject: str | None = None,
    ) -> list[dict[str, object]]:
        self.event_calls.append((task_id, after_sequence, limit))
        if owner_subject == "foreign":
            return []
        records: list[dict[str, object]] = []
        for sequence in self.event_sequences:
            if sequence <= after_sequence:
                continue
            records.append(
                {
                    "sequence": sequence,
                    "schema_version": 2,
                    "task_id": task_id,
                    "step_id": "step-1",
                    "agent_id": "agent-root",
                    "parent_id": None,
                    "tool_call_id": None,
                    "approval_id": None,
                    "resource_job_id": None,
                    "correlation_id": "request-1",
                    "event_type": "task.completed",
                    "payload_json": '{"result":"ok"}',
                    "created_at": "2026-08-20T00:00:00+00:00",
                },
            )
        return records[:limit]

    def list_tasks(self, limit: int, owner_subject: str | None = None) -> list[dict[str, object]]:
        if owner_subject == "foreign":
            return []
        tasks: list[dict[str, object]] = [{"task_id": "task-123", "status": "done"}]
        return tasks[:limit]

    def get_task_output(self, task_id: str, owner_subject: str | None = None) -> str | None:
        if owner_subject == "foreign":
            return None
        return "source result" if task_id == "task-123" else None

    def cancel_verdict(self, task_id: str, owner_subject: str | None = None) -> str:
        _ = task_id
        if owner_subject == "foreign":
            return "not_active"
        return self.cancel_verdict_result

    def cancel_task(self, task_id: str, owner_subject: str | None = None) -> bool:
        return self.cancel_verdict(task_id, owner_subject=owner_subject) == "cancelled"

    def resume_task(self, task_id: str, owner_subject: str | None = None) -> bool:
        _ = task_id
        return owner_subject != "foreign"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> FakeTaskRuntime:
    fake = FakeTaskRuntime()
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    async def _set_test_auth_subject(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request.state.auth_subject = request.headers.get("X-Test-Subject", "owner")
        return await call_next(request)

    _ = app.middleware("http")(_set_test_auth_subject)
    app.include_router(task_api.router)
    return TestClient(app)


def test_submit_task_uses_typed_canonical_runtime_contract(client: TestClient, runtime: FakeTaskRuntime) -> None:
    response = client.post(
        "/api/tasks/submit",
        json={
            "prompt": "  inspect the repository  ",
            "context": {"expected_tools": ["read_file"]},
            "model": "qwen-local",
            "use_worktree": True,
            "idempotency_key": "request-1",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "submitted", "task_id": "task-123"}
    # WS-01: submit context는 immutable project binding 필드가 merge된다.
    assert len(runtime.submit_calls) == 1
    call = runtime.submit_calls[0]
    assert call["prompt"] == "inspect the repository"
    assert call["target_model"] == "qwen-local"
    assert call["use_worktree"] is True
    assert call["idempotency_key"] == "request-1"
    assert call["owner_subject"] == "owner"
    binding_ctx = call["context"]
    assert binding_ctx["expected_tools"] == ["read_file"]
    assert binding_ctx["project_id"] == "default"
    assert binding_ctx["canonical_project_root"]
    assert binding_ctx["session_id"] == "default"
    assert binding_ctx["actor_subject"] == "owner"
    assert binding_ctx["schema_version"] == 1
    assert binding_ctx["execution_context"]["project_id"] == "default"


def test_submit_task_rejects_blank_prompt(client: TestClient, runtime: FakeTaskRuntime) -> None:
    response = client.post("/api/tasks/submit", json={"prompt": "   "})

    assert response.status_code == 422
    assert runtime.submit_calls == []


def test_submit_task_rejects_overlong_prompt_at_api_boundary(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.post("/api/tasks/submit", json={"prompt": "x" * 32_001})

    assert response.status_code == 422
    assert runtime.submit_calls == []


def test_submit_task_rejects_oversized_context_at_api_boundary(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.post(
        "/api/tasks/submit",
        json={"prompt": "inspect", "context": {"payload": "x" * 66_000}},
    )

    assert response.status_code == 422
    assert runtime.submit_calls == []


def test_fork_task_rejects_overlong_prompt_at_api_boundary(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.post(
        "/api/tasks/task-source/fork",
        json={"prompt": "x" * 32_001},
    )

    assert response.status_code == 422
    assert runtime.submit_calls == []


def test_fork_task_submits_source_snapshot_without_mutating_source(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.post("/api/tasks/task-source/fork", json={})

    assert response.status_code == 202
    assert response.json() == {
        "status": "forked",
        "task_id": "task-123",
        "source_task_id": "task-source",
    }
    assert runtime.submit_calls == [
        {
            "prompt": "inspect the repository",
            "context": {
                "fork": {
                    "source_task_id": "task-source",
                    "source_status": "done",
                    "source_output": "source result",
                    "source_last_sequence": 7,
                },
            },
            "target_model": "",
            "use_worktree": False,
            "idempotency_key": None,
            "owner_subject": "owner",
        },
    ]
    assert runtime.get_task_status("task-source") == {
        "task_id": "task-source",
        "prompt": "inspect the repository",
        "status": "done",
        "output": "source result",
    }


def test_task_event_replay_is_task_scoped_and_decodes_payload(client: TestClient, runtime: FakeTaskRuntime) -> None:
    response = client.get("/api/tasks/task-123/events?after_sequence=3&limit=25")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "events": [
            {
                "sequence": 7,
                "schema_version": 2,
                "task_id": "task-123",
                "step_id": "step-1",
                "agent_id": "agent-root",
                "parent_id": None,
                "tool_call_id": None,
                "approval_id": None,
                "resource_job_id": None,
                "correlation_id": "request-1",
                "event_type": "task.completed",
                "payload": {"result": "ok"},
                "created_at": "2026-08-20T00:00:00+00:00",
            },
        ],
        "last_sequence": 7,
        "has_more": False,
    }
    assert runtime.event_calls == [("task-123", 3, 26)]


def test_task_event_replay_reports_when_another_page_exists(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    runtime.event_sequences = [4, 5, 6]

    response = client.get("/api/tasks/task-123/events?after_sequence=3&limit=2")

    assert response.status_code == 200
    payload = TaskEventsResponse.model_validate(response.json())
    assert [event.sequence for event in payload.events] == [4, 5]
    assert payload.last_sequence == 5
    assert payload.has_more is True
    assert runtime.event_calls == [("task-123", 3, 3)]


def test_task_event_replay_rejects_unknown_task(client: TestClient, runtime: FakeTaskRuntime) -> None:
    response = client.get("/api/tasks/missing/events")

    assert response.status_code == 404
    assert runtime.event_calls == []


def test_task_status_rejects_foreign_authenticated_subject(client: TestClient, runtime: FakeTaskRuntime) -> None:
    _ = runtime
    response = client.get("/api/tasks/task-123/status", headers={"X-Test-Subject": "foreign"})

    assert response.status_code == 404


def test_cancel_of_task_owned_by_another_live_process_is_a_conflict(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    """F-35: 살아 있는 다른 프로세스의 실행은 404(활성 아님)가 아니라 **409** 다.

    예전에는 이 자리가 조용했다 — 소유 여부를 보지 않고 `cancelled` 로 적었기 때문이다.
    """
    runtime.cancel_verdict_result = "owned_elsewhere"
    response = client.post("/api/tasks/task-123/cancel")

    assert response.status_code == 409
    assert "another live process" in str(response.json()["detail"]).lower()


def test_cancel_of_inactive_task_is_not_found(client: TestClient, runtime: FakeTaskRuntime) -> None:
    runtime.cancel_verdict_result = "not_active"

    assert client.post("/api/tasks/task-123/cancel").status_code == 404


def test_cancel_of_owned_task_reports_cancelled(client: TestClient, runtime: FakeTaskRuntime) -> None:
    runtime.cancel_verdict_result = "cancelled"
    response = client.post("/api/tasks/task-123/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/tasks/task-123/output"),
        ("post", "/api/tasks/task-123/cancel"),
        ("post", "/api/tasks/task-123/resume"),
        ("get", "/api/tasks/task-123/events"),
        ("get", "/api/tasks/task-123/events/stream"),
    ],
)
def test_task_mutation_and_replay_reject_foreign_authenticated_subject(
    client: TestClient,
    runtime: FakeTaskRuntime,
    method: str,
    path: str,
) -> None:
    _ = runtime
    response = client.request(method.upper(), path, headers={"X-Test-Subject": "foreign"})

    assert response.status_code == 404


def test_task_listing_is_owner_scoped(client: TestClient, runtime: FakeTaskRuntime) -> None:
    _ = runtime
    response = client.get("/api/tasks", headers={"X-Test-Subject": "foreign"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "data": []}


def test_task_event_sse_replays_then_ends_for_terminal_task(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.get("/api/tasks/task-123/events/stream?after_sequence=0")

    assert response.status_code == 200
    frames = [frame for frame in response.text.strip().split("\n\n") if frame]
    assert frames[0].startswith("id: 7\nevent: task.completed\ndata: ")
    event = typing.cast(dict[str, object], json.loads(frames[0].split("data: ", 1)[1]))
    assert runtime.event_calls == [("task-123", 0, 200)]
    assert event["task_id"] == "task-123"
    assert event["payload"] == {"result": "ok"}
    assert frames[1].startswith("event: stream.end\ndata: ")
    end = typing.cast(dict[str, object], json.loads(frames[1].split("data: ", 1)[1]))
    assert end == {"task_id": "task-123", "last_sequence": 7, "status": "done"}


def test_task_event_sse_resumes_from_last_event_id_header(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    response = client.get(
        "/api/tasks/task-123/events/stream?after_sequence=3",
        headers={"Last-Event-ID": "7"},
    )

    assert response.status_code == 200
    assert response.text.startswith("event: stream.end\ndata: ")
    assert runtime.event_calls == [("task-123", 7, 200)]


def test_task_event_websocket_replays_task_scoped_events_and_ends(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    with client.websocket_connect("/api/tasks/task-123/events/ws?after_sequence=3") as websocket:
        replay = typing.cast(dict[str, object], websocket.receive_json())
        stream_end = typing.cast(dict[str, object], websocket.receive_json())

    assert replay == {
        "sequence": 7,
        "schema_version": 2,
        "task_id": "task-123",
        "step_id": "step-1",
        "agent_id": "agent-root",
        "parent_id": None,
        "tool_call_id": None,
        "approval_id": None,
        "resource_job_id": None,
        "correlation_id": "request-1",
        "event_type": "task.completed",
        "payload": {"result": "ok"},
        "created_at": "2026-08-20T00:00:00+00:00",
    }
    assert stream_end == {
        "type": "stream.end",
        "task_id": "task-123",
        "last_sequence": 7,
        "status": "done",
    }
    assert runtime.event_calls == [("task-123", 3, 200)]


def test_task_event_websocket_rejects_unknown_task_before_replay(
    client: TestClient,
    runtime: FakeTaskRuntime,
) -> None:
    with client.websocket_connect("/api/tasks/missing/events/ws") as websocket:
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    assert runtime.event_calls == []
