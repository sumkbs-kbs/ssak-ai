import json
from collections.abc import Iterator
from typing import Protocol, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from antigravity_k.api.server import app
from antigravity_k.config import config
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.protocol_translator import ProtocolTranslator
from antigravity_k.tools.tool_contracts import Permission

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class _MockCall(Protocol):
    kwargs: dict[str, object]


class _MockMethod(Protocol):
    call_count: int
    call_args: _MockCall
    call_args_list: list[_MockCall]

    def assert_not_called(self) -> None: ...

    def assert_called_once_with(self, *args: object, **kwargs: object) -> None: ...


class _ManagerDouble(Protocol):
    generate: _MockMethod
    status: _MockMethod
    router: MagicMock

    def reset_mock(self) -> None: ...


class _RuntimeDouble(Protocol):
    submit_task: _MockMethod
    cancel_task: _MockMethod
    get_task_status: _MockMethod
    list_tasks: _MockMethod
    get_task_output: _MockMethod
    resume_task: _MockMethod
    steer_task: _MockMethod


class _GateDouble(Protocol):
    check: _MockMethod


def _response_json(response: Response) -> JsonObject:
    return cast(JsonObject, response.json())


def _as_object(value: object) -> JsonObject:
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return list(cast(list[object], value)) if isinstance(value, list) else []


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _response_content(response: Response) -> str:
    payload = _response_json(response)
    choices = _as_list(payload.get("choices"))
    first = _as_object(choices[0]) if choices else {}
    message = _as_object(first.get("message"))
    return _as_text(message.get("content"))


@pytest.fixture
def mock_manager() -> _ManagerDouble:
    manager = cast(_ManagerDouble, MagicMock(spec=ModelManager))
    # generate 메서드가 성공적으로 문자열을 반환하도록 설정
    setattr(manager.generate, "return_value", "This is a mock response from the LLM.")
    # status()가 딕셔너리를 반환하도록 설정 (health check 등에서 사용)
    setattr(manager.status, "return_value", {"loaded_models": []})
    # SlashCommandRegistry가 model_manager.router를 참조한다
    manager.router = MagicMock()
    return manager


@pytest.fixture
def mock_translator() -> ProtocolTranslator:
    # 실제 ProtocolTranslator를 사용하거나 Mocking
    return ProtocolTranslator()


@pytest.fixture
def client(mock_manager: _ManagerDouble, mock_translator: ProtocolTranslator) -> Iterator[TestClient]:
    """FastAPI DI + legacy module의 get_model_manager를 함께 오버라이드.

    _get_slash_registry()가 get_model_manager()를 직접 호출할 때도
    mock_manager가 반환되도록 legacy 모듈에도 패치를 적용합니다.
    """
    from antigravity_k.api import dependencies

    app.dependency_overrides[dependencies.get_model_manager] = lambda: mock_manager
    app.dependency_overrides[dependencies.get_translator] = lambda: mock_translator

    # legacy._get_slash_registry()가 직접 호출하는 get_model_manager도 오버라이드
    with patch("antigravity_k.api.dependencies.get_model_manager", return_value=mock_manager):
        with TestClient(app) as c:
            if config.security.access_pin:
                c.headers.update({"X-Access-Pin": config.security.access_pin})
            # Fixture 멤버 초기화 중 발생한 호출 기록 제거
            mock_manager.reset_mock()
            yield c

    app.dependency_overrides.clear()


def test_health_check(client: TestClient):
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = _response_json(response)
    assert data["status"] == "ok"
    assert data["backends"] == []
    assert "rag_index_files" in data
    assert "cov_active" in data


def test_health_check_root_alias(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = _response_json(response)
    assert data["status"] == "ok"
    assert data["backends"] == []
    assert "rag_index_files" in data
    assert "cov_active" in data


def test_dashboard_spa_deep_link_serves_index(client: TestClient):
    response = client.get("/agent")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_api_routes_require_access_pin_without_auth_header():
    if not config.security.access_pin:
        pytest.skip("Access PIN is disabled for this environment")

    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.post("/api/slash", json={"input": "/goal test"})

    assert response.status_code == 401
    assert _response_json(response)["ok"] is False


def test_memory_purge_requires_access_pin_without_auth_header():
    if not config.security.access_pin:
        pytest.skip("Access PIN is disabled for this environment")

    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.request("DELETE", "/api/memory", json={"scope": "all"})

    assert response.status_code == 401


def test_skill_publish_github_honors_permission_denial_before_publisher_start(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from antigravity_k.api.routes import system_api

    gate = cast(_GateDouble, MagicMock())
    setattr(gate.check, "return_value", Permission.DENY)
    monkeypatch.setattr(system_api, "_permission_gate", lambda: gate, raising=False)

    response = client.post(
        "/api/system/skills/publish-github",
        json={"skill_name": "demo", "repo": "org/repo"},
    )

    assert response.status_code == 403


def test_skill_publish_npm_honors_permission_denial_before_publisher_start(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from antigravity_k.api.routes import system_api

    gate = cast(_GateDouble, MagicMock())
    setattr(gate.check, "return_value", Permission.DENY)
    monkeypatch.setattr(system_api, "_permission_gate", lambda: gate)

    response = client.post(
        "/api/system/skills/publish-npm",
        json={"skill_name": "demo"},
    )

    assert response.status_code == 403


def test_env_settings_honors_permission_denial_before_file_write(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import system_api as legacy

    gate = cast(_GateDouble, MagicMock())
    setattr(gate.check, "return_value", Permission.DENY)
    monkeypatch.setattr(legacy, "_permission_gate", lambda: gate, raising=False)
    monkeypatch.setattr("builtins.open", MagicMock())

    response = client.post(
        "/api/settings/env",
        json={"OPENAI_API_KEY": "redacted"},
    )

    assert response.status_code == 403


def test_env_settings_rejects_non_object_payload(client: TestClient):
    response = client.post("/api/settings/env", json=[])

    assert response.status_code == 400


def test_env_settings_rejects_non_string_value(client: TestClient):
    response = client.post("/api/settings/env", json={"OPENAI_API_KEY": 123})

    assert response.status_code == 400


def test_kanban_tasks_are_project_scoped_cancelled_and_removable(client: TestClient):
    from antigravity_k.api.routes import kanban_api as legacy

    original_tasks = list(legacy.kanban_tasks)
    original_counter = cast(int, legacy.task_counter)
    legacy.kanban_tasks.clear()
    legacy.task_counter = 9100

    try:
        alpha = client.post(
            "/api/kanban/tasks",
            json={
                "description": "Alpha project task",
                "assignee": "QA",
                "workspace": "/tmp/antigravity-alpha",
            },
        )
        beta = client.post(
            "/api/kanban/tasks",
            json={
                "description": "Beta project task",
                "assignee": "WORKER",
                "workspace": "/tmp/antigravity-beta",
            },
        )

        assert alpha.status_code == 200
        assert beta.status_code == 200
        assert _response_json(alpha)["project_name"] == "antigravity-alpha"
        assert _response_json(beta)["project_name"] == "antigravity-beta"

        scoped = client.get("/api/kanban/tasks", params={"workspace": "/tmp/antigravity-alpha"})
        assert scoped.status_code == 200
        scoped_tasks = _as_list(_response_json(scoped)["data"])
        assert [_as_object(task)["title"] for task in scoped_tasks] == ["Alpha project task"]

        cancel = client.post(f"/api/kanban/tasks/{_response_json(alpha)['id']}/cancel")
        assert cancel.status_code == 200
        assert _as_object(_response_json(cancel)["task"])["status"] == "cancelled"

        remove = client.delete(f"/api/kanban/tasks/{_response_json(alpha)['id']}")
        assert remove.status_code == 200
        assert _response_json(remove)["ok"] is True

        scoped_after_remove = client.get("/api/kanban/tasks", params={"workspace": "/tmp/antigravity-alpha"})
        assert scoped_after_remove.status_code == 200
        assert _response_json(scoped_after_remove)["data"] == []
    finally:
        legacy.kanban_tasks.clear()
        legacy.kanban_tasks.extend(original_tasks)
        legacy.task_counter = original_counter


def test_kanban_websocket_sends_flat_tasks_payload(client: TestClient):
    from antigravity_k.api.routes import kanban_api as legacy

    original_tasks = list(legacy.kanban_tasks)
    legacy.kanban_tasks.clear()
    legacy.kanban_tasks.append(
        {
            "id": "T-WS",
            "title": "WebSocket payload task",
            "description": "WebSocket payload task",
            "role": "QA",
            "status": "todo",
            "project_path": "/tmp/antigravity-ws",
            "project_name": "antigravity-ws",
        },
    )

    try:
        # SEC-03: WS auth uses a short-lived single-use ticket (?ticket=).
        # The old ?pin= channel was removed in SEC-02; long-lived bearer
        # tokens in query strings were removed in SEC-03.
        ws_url = "/ws/kanban"
        if config.security.access_pin:
            from antigravity_k.engine.auth import TokenService
            from antigravity_k.security.ws_ticket import get_ws_ticket_service

            ticket = get_ws_ticket_service(TokenService()).issue("test")
            ws_url += f"?ticket={ticket}"
        with client.websocket_connect(ws_url) as websocket:
            payload = cast(JsonObject, json.loads(websocket.receive_text()))

        assert "tasks" in payload
        assert _as_object(_as_list(payload["tasks"])[0])["id"] == "T-WS"
        assert _as_object(_as_list(payload["todo"])[0])["id"] == "T-WS"
        assert _as_object(_as_list(payload["BACKLOG"])[0])["id"] == "T-WS"
    finally:
        legacy.kanban_tasks.clear()
        legacy.kanban_tasks.extend(original_tasks)


def test_chat_completions_openai_format(client: TestClient, mock_manager: _ManagerDouble):
    payload = {
        "model": "test-combo",
        "messages": [{"role": "user", "content": "Hello, Antigravity!"}],
        "temperature": 0.8,
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    data = _response_json(response)

    # OpenAI 응답 구조 확인
    assert "id" in data
    assert data["object"] == "chat.completion"
    choices = _as_list(data["choices"])
    assert len(choices) > 0
    message = _as_object(_as_object(choices[0])["message"])
    assert message["role"] == "assistant"
    assert message["content"] == "This is a mock response from the LLM."
    assert "usage" in data

    # ModelManager.generate 호출 확인 (intent classifier 1회 + 실제 생성 1회)
    assert mock_manager.generate.call_count == 2
    # 실제 생성 호출(두 번째 호출)의 kwargs 검증
    kwargs = mock_manager.generate.call_args_list[1].kwargs
    assert kwargs["target"] == "test-combo"
    assert kwargs["temperature"] == 0.8
    # Prompt string 확인 (간단하게 포함 여부만)
    assert "Hello, Antigravity!" in _as_text(kwargs["prompt"])


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"model": 123, "messages": []},
        {"model": "test-combo", "messages": "not-an-array"},
        {"model": "test-combo", "messages": [None]},
        {"model": "test-combo", "messages": [{"role": 1, "content": "hello"}]},
        {"model": "test-combo", "messages": [{"role": "user", "content": ["hello"]}]},
        {"model": "test-combo", "messages": [], "stream": "false"},
    ],
)
def test_chat_completions_rejects_malformed_payload(client: TestClient, payload: JsonValue):
    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 400


def test_chat_completions_rejects_malformed_json(client: TestClient):
    response = client.post("/v1/chat/completions", content="{")

    assert response.status_code == 400


@pytest.mark.parametrize("payload", [[], {"name": 123}, {"name": "test-combo", "role": 123}])
def test_set_default_model_rejects_malformed_payload(client: TestClient, payload: JsonValue):
    response = client.post("/api/models/default", json=payload)

    assert response.status_code == 400


def test_set_default_model_rejects_malformed_json(client: TestClient):
    response = client.post("/api/models/default", content="{")

    assert response.status_code == 400


def test_chat_reconnect_endpoint_uses_shared_session_state(client: TestClient):
    from antigravity_k.api.routes.session_state import reset_active_session

    _ = reset_active_session()

    response = client.get("/v1/chat/completions/reconnect")

    assert response.status_code == 200
    assert "data: [DONE]" in response.text


def test_chat_completions_routes_slash_goal(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)
    payload = {
        "model": "test-combo",
        "messages": [{"role": "user", "content": "/goal DOM 기능을 테스트하고 리포트를 작성해줘"}],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = _response_content(response)
    assert "/goal Autonomous Goal Contract" in content
    assert "Autonomous Judgment Policy" in content
    assert "Autonomous Loop" in content
    mock_manager.generate.assert_not_called()


def test_chat_completions_capabilities_uses_connected_policy(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)
    payload = {
        "model": "test-combo",
        "messages": [{"role": "user", "content": "/capabilities DOM browser testing"}],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = _response_content(response)
    assert "Autonomous Capability Manifest" in content
    assert "Autonomous Capability Policy" in content
    assert content.count("Autonomous Capability Policy") == 1
    assert "**Tools/MCP:** allow=" in content
    assert "Tool registry not connected" not in content
    assert "Skill loader not connected" not in content
    mock_manager.generate.assert_not_called()


def test_chat_completions_routes_slash_codex(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)
    payload = {
        "model": "test-combo",
        "messages": [
            {
                "role": "user",
                "content": "/codex DOM 테스트와 제로 오류 정책을 업그레이드해줘",
            },
        ],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = _response_content(response)
    assert "Codex Capability Transfer Manifest" in content
    assert "Zero-Error Completion Gates" in content
    assert "Autonomous Tool Judgment" in content
    assert "Private model weights" in content
    mock_manager.generate.assert_not_called()


def test_chat_completions_self_capability_bypasses_llm(client: TestClient, mock_manager: _ManagerDouble):
    payload = {
        "model": "test-combo",
        "messages": [
            {
                "role": "user",
                "content": "너를 소개하고 니가 할 수 있는 일과 할 수 없는 일을 알려줘",
            },
        ],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = _response_content(response)
    assert "Ssak-Ai Self Capability Report" in content
    assert "현재 런타임에 등록되지 않은 도구" in content
    assert "등록 도구" in content
    mock_manager.generate.assert_not_called()


def test_slash_api_accepts_input_alias(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)

    response = client.post(
        "/api/slash",
        json={"input": "/goal 출력 품질을 Codex 수준으로 개선해줘"},
    )

    assert response.status_code == 200
    data = _response_json(response)
    assert data["ok"] is True
    result = _as_text(data["result"])
    assert "/goal Autonomous Goal Contract" in result
    assert "Response quality gates" in result
    mock_manager.generate.assert_not_called()


def test_slash_api_empty_command_returns_structured_error(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)

    response = client.post("/api/slash", json={})

    assert response.status_code == 200
    data = _response_json(response)
    assert data == {"ok": True, "result": "Error: Empty command."}
    mock_manager.generate.assert_not_called()


def test_slash_api_benchmark_help_returns_plain_text(client: TestClient, mock_manager: _ManagerDouble):
    import antigravity_k.api.dependencies as deps

    setattr(deps, "_slash_registry", None)

    response = client.post("/api/slash", json={"input": "/benchmark"})

    assert response.status_code == 200
    data = _response_json(response)
    assert data["ok"] is True
    assert isinstance(data["result"], str)
    assert "Benchmark 명령어" in data["result"]
    mock_manager.generate.assert_not_called()


def test_task_benchmark_api_submits_a_canonical_scenario(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(runtime.submit_task, "return_value", "task_benchmark_001")
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    response = client.post(
        "/api/tasks/benchmark/srch-002",
        json={"model": "qwen3.6:latest", "idempotency_key": "benchmark-srch-002"},
    )

    assert response.status_code == 200
    assert _as_object(_response_json(response)["benchmark_case"])["id"] == "srch-002"
    submitted = runtime.submit_task.call_args.kwargs
    assert submitted["target_model"] == "qwen3.6:latest"
    assert submitted["idempotency_key"] == "benchmark-srch-002"
    context = _as_object(submitted["context"])
    assert context["benchmark_case_id"] == "srch-002"
    assert context["expected_tools"] == ["web_search"]
    assert context["expected_keywords"]
    assert context["benchmark_read_only"] is True


def test_task_cancel_api_cancels_background_task(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(runtime.cancel_verdict, "return_value", "cancelled")
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    response = client.post("/api/tasks/task_123/cancel")

    assert response.status_code == 200
    assert _response_json(response) == {"status": "cancelled", "task_id": "task_123"}
    runtime.cancel_verdict.assert_called_once_with("task_123", owner_subject="loopback")


def test_task_cancel_api_rejects_unknown_or_terminal_task(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(runtime.cancel_verdict, "return_value", "not_active")
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    response = client.post("/api/tasks/task_missing/cancel")

    assert response.status_code == 404
    assert _response_json(response)["detail"] == "Task is not active"


def test_task_cancel_api_reports_owned_elsewhere_as_conflict(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """F-35: 살아 있는 다른 프로세스의 실행은 404 가 아니라 **409** 다 — 조용한 실패가 아니다."""
    from antigravity_k.api.routes import task_api

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(runtime.cancel_verdict, "return_value", "owned_elsewhere")
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    response = client.post("/api/tasks/task_123/cancel")

    assert response.status_code == 409
    assert "another live process" in str(_response_json(response)["detail"]).lower()


def test_task_steering_api_records_accepted_queued_replay(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import task_api
    from antigravity_k.engine.task_steering import TaskSteeringResult

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(
        runtime.steer_task,
        "return_value",
        TaskSteeringResult(status="accepted", task_id="task_123", steering_id="steer_1"),
    )
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    response = client.post("/api/tasks/task_123/steer", json={"instruction": "focus on security"})

    assert response.status_code == 202
    assert _response_json(response) == {
        "status": "accepted",
        "task_id": "task_123",
        "steering_id": "steer_1",
        "mode": "queued_replay",
    }
    runtime.steer_task.assert_called_once_with("task_123", "focus on security", owner_subject="loopback")


def test_task_api_reads_and_resumes_direct_task_through_canonical_runtime(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from antigravity_k.api.routes import task_api

    runtime = cast(_RuntimeDouble, MagicMock())
    setattr(runtime.get_task_status, "return_value", {"task_id": "direct_001", "status": "failed"})
    setattr(runtime.list_tasks, "return_value", [{"task_id": "direct_001", "status": "failed"}])
    setattr(runtime.get_task_output, "return_value", "partial-output")
    setattr(runtime.resume_task, "return_value", True)
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)

    status = client.get("/api/tasks/direct_001/status")
    tasks = client.get("/api/tasks?limit=1")
    output = client.get("/api/tasks/direct_001/output")
    resumed = client.post("/api/tasks/direct_001/resume")

    assert _response_json(status)["data"] == {"task_id": "direct_001", "status": "failed"}
    assert _response_json(tasks)["data"] == [{"task_id": "direct_001", "status": "failed"}]
    assert _response_json(output) == {"status": "ok", "task_id": "direct_001", "output": "partial-output"}
    assert _response_json(resumed) == {"status": "resumed", "task_id": "direct_001"}
    runtime.get_task_status.assert_called_once_with("direct_001", owner_subject="loopback")
    runtime.list_tasks.assert_called_once_with(limit=1, owner_subject="loopback")
    runtime.get_task_output.assert_called_once_with("direct_001", owner_subject="loopback")


def test_embeddings_endpoint_uses_local_fallback(client: TestClient):
    payload = {"model": "test-embed-model", "input": "Hello, embeddings!"}

    response = client.post("/v1/embeddings", json=payload)

    assert response.status_code == 200
    data = _response_json(response)
    assert data["object"] == "list"
    assert data["model"] == "test-embed-model"
    embeddings = _as_list(data["data"])
    assert len(embeddings) == 1
    assert len(_as_list(_as_object(embeddings[0])["embedding"])) == 1536
    assert cast(int, _as_object(data["usage"])["total_tokens"]) > 0
