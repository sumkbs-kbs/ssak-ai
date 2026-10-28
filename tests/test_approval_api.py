from __future__ import annotations

from typing import cast

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from antigravity_k.api.routes import approval_api
from antigravity_k.api.routes.approval_api import router
from antigravity_k.engine.approval_manager import (
    AlwaysAllowGrant,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)

JsonObject = dict[str, object]
TEST_ACTOR = "approval-unit-user"


class _FakeManager:
    def __init__(self) -> None:
        self.pending: list[ApprovalRequest] = []
        self.request: ApprovalRequest | None = None
        self.resolve_result: bool = False
        self.resolve_calls: list[tuple[str, ApprovalDecision]] = []
        self.reset_calls: int = 0
        self.grants: list[AlwaysAllowGrant] = []
        self.always_allowed_keys: set[str] = set()

    def get_pending(self) -> list[ApprovalRequest]:
        return self.pending

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        _ = request_id
        return self.request

    def resolve(
        self, request_id: str, decision: ApprovalDecision, *, actor_subject: str | None = None
    ) -> bool:
        assert actor_subject == TEST_ACTOR
        self.resolve_calls.append((request_id, decision))
        return self.resolve_result

    def reset_always_allowed(self, *, actor_subject: str | None = None) -> list[str]:
        assert actor_subject == TEST_ACTOR
        self.reset_calls += 1
        return sorted(self.always_allowed_keys)

    def always_allowed_grants(self, *, actor_subject: str | None = None) -> list[AlwaysAllowGrant]:
        assert actor_subject == TEST_ACTOR
        return list(self.grants)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def install_test_actor(request: Request, call_next: RequestResponseEndpoint) -> StarletteResponse:
        request.state.auth_subject = TEST_ACTOR
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _install_manager(monkeypatch: MonkeyPatch, manager: _FakeManager) -> None:
    monkeypatch.setattr(approval_api, "get_approval_manager", lambda: manager)


def _json(response: Response) -> JsonObject:
    return cast(JsonObject, response.json())


class TestListPending:
    def test_empty(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/pending")
        assert response.status_code == 200
        data = _json(response)
        assert data["count"] == 0
        assert data["pending"] == []

    def test_with_items(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        manager.pending = [ApprovalRequest("req-1", "write_file", {}, scope={"actor": TEST_ACTOR})]
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/pending")
        assert response.status_code == 200
        data = _json(response)
        assert data["count"] == 1
        pending = cast(list[JsonObject], data["pending"])
        assert pending[0]["request_id"] == "req-1"


class TestGetRequest:
    def test_found(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        manager.request = ApprovalRequest("req-1", "write_file", {}, scope={"actor": TEST_ACTOR})
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/req-1")
        assert response.status_code == 200
        data = _json(response)
        assert data["request_id"] == "req-1"

    def test_not_found(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/nonexistent")
        assert response.status_code == 404
        data = _json(response)
        assert "찾을 수 없습니다" in cast(str, data["detail"])


class TestResolveApproval:
    def test_approve(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        manager.resolve_result = True
        manager.request = ApprovalRequest(
            "req-1", "write_file", {}, status=ApprovalStatus.APPROVED, scope={"actor": TEST_ACTOR}
        )
        _install_manager(monkeypatch, manager)

        response = client.post("/api/approval/req-1/resolve", json={"decision": "approve"})
        assert response.status_code == 200
        data = _json(response)
        assert data["ok"] is True
        assert data["request_id"] == "req-1"
        assert manager.resolve_calls == [("req-1", ApprovalDecision.APPROVE)]

    def test_invalid_decision(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.post("/api/approval/req-1/resolve", json={"decision": "invalid"})
        assert response.status_code == 400
        data = _json(response)
        assert "잘못된 결정" in cast(str, data["detail"])

    def test_resolve_fail_not_found(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.post("/api/approval/req-1/resolve", json={"decision": "deny"})
        assert response.status_code == 404
        data = _json(response)
        assert "찾을 수 없거나" in cast(str, data["detail"])


class TestAlwaysAllowedGrants:
    def test_empty(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/always-allowed")
        assert response.status_code == 200
        data = _json(response)
        assert data["count"] == 0
        assert data["grants"] == []

    def test_lists_grants_with_reason_and_count(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        """부여 목록은 도구·시각·근거·동의 없이 실행된 횟수를 낸다(F-33)."""
        manager = _FakeManager()
        manager.grants = [
            AlwaysAllowGrant(
                tool_name="run_bash_command",
                granted_at=1_700_000_000.0,
                granted_for="run_bash_command 실행",
                auto_approved_count=3,
                last_auto_approved_at=1_700_000_500.0,
            )
        ]
        _install_manager(monkeypatch, manager)

        response = client.get("/api/approval/always-allowed")
        assert response.status_code == 200
        data = _json(response)
        assert data["count"] == 1
        grants = cast(list[JsonObject], data["grants"])
        assert grants[0]["tool_name"] == "run_bash_command"
        assert grants[0]["granted_for"] == "run_bash_command 실행"
        assert grants[0]["auto_approved_count"] == 3


class TestResetAlwaysAllowed:
    def test_reset_ok(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        manager.always_allowed_keys = {"write_file", "run_bash_command"}
        _install_manager(monkeypatch, manager)

        response = client.post("/api/approval/reset-always-allowed")
        assert response.status_code == 200
        assert manager.reset_calls == 1
        data = _json(response)
        assert data["ok"] is True
        # 해제가 **무엇을** 되돌렸는지 응답이 말한다 — 조용한 해제는 검증할 수 없다(F-33).
        assert data["revoked"] == ["run_bash_command", "write_file"]
        assert "2건" in cast(str, data["message"])

    def test_reset_without_grants_says_zero(self, client: TestClient, monkeypatch: MonkeyPatch) -> None:
        manager = _FakeManager()
        _install_manager(monkeypatch, manager)

        response = client.post("/api/approval/reset-always-allowed")
        assert response.status_code == 200
        data = _json(response)
        assert data["revoked"] == []
        assert "0건" in cast(str, data["message"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/approval/pending"),
        ("GET", "/api/approval/always-allowed"),
        ("GET", "/api/approval/req-1"),
        ("POST", "/api/approval/req-1/resolve"),
        ("POST", "/api/approval/reset-always-allowed"),
    ],
)
def test_routes_require_verified_actor_without_auth_middleware(
    method: str, path: str, monkeypatch: MonkeyPatch
) -> None:
    manager = _FakeManager()
    _install_manager(monkeypatch, manager)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as unauthenticated:
        response = unauthenticated.request(method, path, json={"decision": "approve", "actor_subject": TEST_ACTOR})
    assert response.status_code == 401
    assert manager.resolve_calls == []
    assert manager.reset_calls == 0


def test_ownerless_request_is_hidden_and_cannot_be_claimed(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    manager = _FakeManager()
    ownerless = ApprovalRequest("req-1", "write_file", {})
    manager.pending = [ownerless]
    manager.request = ownerless
    manager.resolve_result = True
    _install_manager(monkeypatch, manager)

    assert _json(client.get("/api/approval/pending"))["pending"] == []
    assert client.get("/api/approval/req-1").status_code == 404
    response = client.post(
        "/api/approval/req-1/resolve", json={"decision": "approve", "actor_subject": TEST_ACTOR}
    )
    assert response.status_code == 404
    assert manager.resolve_calls == []
