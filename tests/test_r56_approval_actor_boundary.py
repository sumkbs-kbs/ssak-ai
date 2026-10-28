"""Authenticated approval ownership with the real executor and a synthetic file.

Only a test trigger replaces model generation. Real PIN login, signed tokens,
authentication middleware, approval HTTP routes, approval scope/binding,
permission layers and WriteArtifactTool remain installed. No model or transport
is called and all files belong to the inherited temporary ownership fixture.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from httpx import Response

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import (
    reset_bound_request_execution_context,
    set_bound_request_execution_context,
)
from antigravity_k.engine import access_mode, approval_manager
from antigravity_k.engine.approval_manager import ApprovalManager, ApprovalStatus
from antigravity_k.engine.project_registry import ProjectRegistry
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.engine.tool_policy import reset_tool_policy, set_tool_policy
from tests.test_r45_authenticated_task_ownership import OwnerCase
from tests.test_r45_authenticated_task_ownership import owner_case as owner_case

ARTIFACT = "r56-owned-approval.md"
FOREIGN_ARTIFACT = "r56-foreign-approval.md"
CONTENT = "합성 사용자가 직접 승인한 자료입니다."
TAG = "[APPROVAL REQUIRED]"
TRIGGER = "/api/r56/synthetic-approved-write"


@dataclass(frozen=True, slots=True)
class ApprovalCase:
    client: TestClient
    manager: ApprovalManager
    executor: ToolExecutor
    root: Path
    ownership: OwnerCase

    @property
    def target(self) -> Path:
        return self.root / "artifacts" / ARTIFACT

    def trigger(self, subject: str = "user") -> Response:
        return self.client.post(TRIGGER, headers=self.ownership.headers[subject])

    def create_pending(self) -> str:
        response = self.trigger()
        assert response.status_code == 200 and TAG in response.json()["result"]
        assert not self.target.exists()
        pending = self.manager.get_pending()
        assert len(pending) == 1 and pending[0].scope["actor"] == "user"
        return pending[0].request_id


@pytest.fixture
def approval_case(owner_case: OwnerCase, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApprovalCase]:
    from antigravity_k.api.routes import approval_api
    from antigravity_k.tools.artifact_tools import WriteArtifactTool
    from antigravity_k.tools.tool_registry import ToolRegistry
    from tests.test_r39_contracts import _executor

    registry = cast(ProjectRegistry, owner_case.state["registry"])
    project = registry.get_project(owner_case.project_ids["alpha"])
    assert project is not None
    project_id = project.id
    root = Path(project.path)
    manager = ApprovalManager()  # default pure policy review, no configured model
    monkeypatch.setattr(approval_manager, "_approval_manager", manager)
    monkeypatch.delenv(access_mode.EXECUTION_POLICY_ENV, raising=False)
    previous_mode = access_mode.get_access_mode()
    previous_policy = access_mode.get_execution_policy()
    access_mode.set_access_mode(access_mode.AccessMode.FULL_ACCESS)
    access_mode.set_execution_policy(access_mode.ExecutionPolicy.BALANCED)
    policy_token = set_tool_policy(None)
    tools = ToolRegistry(project_root=str(root))
    tools.install(WriteArtifactTool(project_root=str(root)))
    executor, _ = _executor(root, tools)
    owner_case.app.include_router(approval_api.router)

    @owner_case.app.post(TRIGGER)
    def trigger_approved_write(request: Request) -> dict[str, str]:
        # This is a synthetic trigger for the real tool boundary, not a model or
        # permission mock. Actor authority comes solely from verified middleware.
        actor = request.state.auth_subject
        assert actor in ("user", "foreign")
        context = RequestExecutionContext(
            request_id="r56-synthetic-request",
            task_id="r56-synthetic-task-" + actor,
            project_id=project_id,
            canonical_project_root=str(root),
            conversation_id="r56-synthetic-conversation-" + actor,
            conversation_revision=0,
            actor_subject=actor,
            session_id="r56-synthetic-session-" + actor,
            model_id="r56-no-model-used",
        )
        token = set_bound_request_execution_context(context)
        try:
            result = executor.execute(
                "write_artifact",
                {"artifact_name": ARTIFACT if actor == "user" or request.query_params.get("shared") else FOREIGN_ARTIFACT,
                 "content": CONTENT, "artifact_type": "other"},
            )
            return {"result": result}
        finally:
            reset_bound_request_execution_context(token)

    try:
        yield ApprovalCase(owner_case.client, manager, executor, root, owner_case)
    finally:
        reset_tool_policy(policy_token)
        access_mode.set_access_mode(previous_mode)
        access_mode.set_execution_policy(previous_policy)


@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_owner_sees_and_resolves_own_request_with_real_file_control(approval_case: ApprovalCase, decision: str) -> None:
    case = approval_case
    request_id = case.create_pending()
    own_headers = case.ownership.headers["user"]
    listed = case.client.get("/api/approval/pending", headers=own_headers)
    assert listed.status_code == 200
    assert [row["request_id"] for row in listed.json()["pending"]] == [request_id]
    detail = case.client.get(f"/api/approval/{request_id}", headers=own_headers)
    assert detail.status_code == 200 and detail.json()["request_id"] == request_id
    resolved = case.client.post(f"/api/approval/{request_id}/resolve", headers=own_headers, json={"decision": decision})
    assert resolved.status_code == 200 and resolved.json()["status"] == ("approved" if decision == "approve" else "denied")
    dispatched = case.trigger()
    assert dispatched.status_code == 200
    if decision == "approve":
        assert TAG not in dispatched.json()["result"]
        assert case.target.read_text(encoding="utf-8") == CONTENT
    else:
        assert TAG in dispatched.json()["result"] and not case.target.exists()


def test_foreign_pending_list_does_not_expose_other_users_request(approval_case: ApprovalCase) -> None:
    case = approval_case
    request_id = case.create_pending()
    response = case.client.get("/api/approval/pending", headers=case.ownership.headers["foreign"])
    assert response.status_code == 200
    assert response.json()["pending"] == [] and response.json()["count"] == 0
    assert request_id not in response.text and ARTIFACT not in response.text
    assert case.manager.get_request(request_id).status is ApprovalStatus.PENDING


def test_foreign_request_id_does_not_expose_approval_detail(approval_case: ApprovalCase) -> None:
    case = approval_case
    request_id = case.create_pending()
    response = case.client.get(f"/api/approval/{request_id}", headers=case.ownership.headers["foreign"])
    assert response.status_code == 404
    assert ARTIFACT not in response.text and CONTENT not in response.text
    assert case.manager.get_request(request_id).status is ApprovalStatus.PENDING


@pytest.mark.parametrize("decision", ["approve", "deny", "always_allow"])
def test_foreign_decision_cannot_change_owner_request_even_with_actor_spoof(
    approval_case: ApprovalCase, decision: str,
) -> None:
    case = approval_case
    request_id = case.create_pending()
    response = case.client.post(
        f"/api/approval/{request_id}/resolve",
        headers=case.ownership.headers["foreign"],
        json={"decision": decision, "actor_subject": "user"},
    )
    assert response.status_code == 404
    assert case.manager.get_request(request_id).status is ApprovalStatus.PENDING
    assert not case.manager.is_always_allowed("write_artifact") and not case.target.exists()
    # Denying foreign decisions must preserve the owner's positive path.
    owner = case.client.post(
        f"/api/approval/{request_id}/resolve",
        headers=case.ownership.headers["user"], json={"decision": "approve"},
    )
    assert owner.status_code == 200
    actual = case.trigger()
    assert actual.status_code == 200 and TAG not in actual.json()["result"]
    assert case.target.read_text(encoding="utf-8") == CONTENT


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer r56-invalid-synthetic-token"}])
def test_unauthenticated_approval_requests_never_reach_or_change_pending_state(
    approval_case: ApprovalCase, headers: dict[str, str],
) -> None:
    case = approval_case
    request_id = case.create_pending()
    for path in ("/api/approval/pending", f"/api/approval/{request_id}"):
        assert case.client.get(path, headers=headers).status_code == 401
    denied = case.client.post(f"/api/approval/{request_id}/resolve", headers=headers, json={"decision": "approve"})
    assert denied.status_code == 401
    assert case.manager.get_request(request_id).status is ApprovalStatus.PENDING and not case.target.exists()


def _owner_always_allow(case: ApprovalCase) -> str:
    request_id = case.create_pending()
    granted = case.client.post(
        f"/api/approval/{request_id}/resolve",
        headers=case.ownership.headers["user"], json={"decision": "always_allow"},
    )
    assert granted.status_code == 200 and granted.json()["status"] == "always_allow"
    return request_id


def test_owner_always_allow_does_not_authorize_foreign_executor(approval_case: ApprovalCase) -> None:
    case = approval_case
    _owner_always_allow(case)
    owner_dispatch = case.trigger()
    assert owner_dispatch.status_code == 200 and TAG not in owner_dispatch.json()["result"]
    assert case.target.read_text(encoding="utf-8") == CONTENT
    grants = case.client.get("/api/approval/always-allowed", headers=case.ownership.headers["user"]).json()["grants"]
    assert grants[0]["auto_approved_count"] == 1
    foreign = case.trigger("foreign")
    assert foreign.status_code == 200 and TAG in foreign.json()["result"]
    assert not (case.root / "artifacts" / FOREIGN_ARTIFACT).exists()
    foreign_pending = case.client.get("/api/approval/pending", headers=case.ownership.headers["foreign"])
    assert foreign_pending.status_code == 200 and foreign_pending.json()["count"] == 1
    assert foreign_pending.json()["pending"][0]["tool_name"] == "write_artifact"


def test_always_allow_list_only_shows_the_authenticated_actors_grants(approval_case: ApprovalCase) -> None:
    case = approval_case
    _owner_always_allow(case)
    own = case.client.get("/api/approval/always-allowed", headers=case.ownership.headers["user"])
    assert own.status_code == 200
    assert [grant["tool_name"] for grant in own.json()["grants"]] == ["write_artifact"]
    foreign = case.client.get("/api/approval/always-allowed", headers=case.ownership.headers["foreign"])
    assert foreign.status_code == 200
    assert foreign.json()["grants"] == [] and foreign.json()["count"] == 0


def test_foreign_reset_cannot_revoke_owner_always_allow(approval_case: ApprovalCase) -> None:
    case = approval_case
    _owner_always_allow(case)
    foreign = case.client.post("/api/approval/reset-always-allowed", headers=case.ownership.headers["foreign"])
    assert foreign.status_code == 200 and foreign.json()["revoked"] == []
    actual = case.trigger()
    assert actual.status_code == 200 and TAG not in actual.json()["result"]
    assert case.target.read_text(encoding="utf-8") == CONTENT


def test_owner_can_revoke_own_always_allow_and_require_approval_again(approval_case: ApprovalCase) -> None:
    case = approval_case
    _owner_always_allow(case)
    revoked = case.client.post("/api/approval/reset-always-allowed", headers=case.ownership.headers["user"])
    assert revoked.status_code == 200 and revoked.json()["revoked"] == ["write_artifact"]
    retried = case.trigger()
    assert retried.status_code == 200 and TAG in retried.json()["result"]
    assert not case.target.exists()


def test_same_arguments_keep_each_actors_pending_request_separate(approval_case: ApprovalCase) -> None:
    case = approval_case
    owner_id = case.create_pending()
    other = case.client.post(TRIGGER + "?shared=1", headers=case.ownership.headers["foreign"])
    assert other.status_code == 200 and TAG in other.json()["result"]
    listed = case.client.get("/api/approval/pending", headers=case.ownership.headers["foreign"]).json()["pending"]
    assert len(listed) == 1 and listed[0]["request_id"] != owner_id
    assert len(case.manager.get_pending()) == 2 and not case.target.exists()


def test_foreign_denial_of_its_own_identical_request_does_not_cancel_owner_approval(
    approval_case: ApprovalCase,
) -> None:
    case = approval_case
    owner_id = case.create_pending()
    response = case.client.post(TRIGGER + "?shared=1", headers=case.ownership.headers["foreign"])
    assert response.status_code == 200 and TAG in response.json()["result"]
    pending = case.client.get("/api/approval/pending", headers=case.ownership.headers["foreign"]).json()["pending"]
    assert len(pending) == 1 and pending[0]["request_id"] != owner_id
    own = case.client.post(f"/api/approval/{owner_id}/resolve", headers=case.ownership.headers["user"], json={"decision": "approve"})
    foreign = case.client.post(f"/api/approval/{pending[0]['request_id']}/resolve", headers=case.ownership.headers["foreign"], json={"decision": "deny"})
    assert own.status_code == foreign.status_code == 200
    actual = case.trigger()
    assert actual.status_code == 200 and TAG not in actual.json()["result"]
    assert case.target.read_text(encoding="utf-8") == CONTENT


@pytest.mark.parametrize("change", ["revoke", "switch"])
@pytest.mark.parametrize("legacy", [False, True], ids=["real-registry", "alternate-registry"])
def test_always_allow_is_rechecked_at_the_real_execution_boundary(
    approval_case: ApprovalCase, monkeypatch: pytest.MonkeyPatch, change: str, legacy: bool,
) -> None:
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    case = approval_case
    _owner_always_allow(case)
    dispatch = case.executor._execute_registry
    legacy_calls = []

    class AlternateRegistry:
        def execute_with_permission(self, name, args, objective):
            from antigravity_k.tools.tool_contracts import Permission
            legacy_calls.append(name)
            return Permission.ALLOW, "unexpected alternate dispatch"

    def changed_boundary(name, args, objective, approval_use):
        assert approval_use is not None
        if legacy:
            monkeypatch.setattr(case.executor, "tool_registry", AlternateRegistry())
        if change == "revoke":
            case.manager.reset_always_allowed(actor_subject="user")
            return dispatch(name, args, objective, approval_use)
        context = get_bound_request_execution_context()
        assert context is not None
        token = set_bound_request_execution_context(context.model_copy(update={"actor_subject": "foreign"}))
        try:
            return dispatch(name, args, objective, approval_use)
        finally:
            reset_bound_request_execution_context(token)

    monkeypatch.setattr(case.executor, "_execute_registry", changed_boundary)
    response = case.trigger()
    assert response.status_code == 200 and TAG in response.json()["result"]
    assert not case.target.exists() and legacy_calls == []


def test_revocation_between_verification_and_consumption_prevents_file_execution(
    approval_case: ApprovalCase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = approval_case
    _owner_always_allow(case)
    original = case.manager.consume_always_allowed
    calls = []

    def revoke_before_consume(name, *, actor_subject=None):
        case.manager.reset_always_allowed(actor_subject="user")
        consumed = original(name, actor_subject=actor_subject)
        calls.append((name, consumed))
        return consumed

    monkeypatch.setattr(case.manager, "consume_always_allowed", revoke_before_consume)
    result = case.trigger()
    assert result.status_code == 200 and TAG in result.json()["result"]
    assert calls == [("write_artifact", False), ("write_artifact", False)]
    pending = case.manager.get_pending()
    assert len(pending) == 1 and pending[0].scope["actor"] == "user"
    assert not case.target.exists()
