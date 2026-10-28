"""Browser approval ownership through authenticated HTTP, without a browser.

Page observations and actions are scripted in memory. Authentication, effect
classification, HTTP routes, the approval manager, live binding comparison and
single-use browser tickets are production code. No page is launched or fetched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from fastapi import Request
from httpx import Response

from antigravity_k.api.browser_session_state import BrowserSessionRegistry
from antigravity_k.api.routes import agent_tools, approval_api
from antigravity_k.engine import access_mode, approval_manager
from antigravity_k.engine.approval_manager import ApprovalManager, ApprovalStatus
from antigravity_k.tools import browser_approval, browser_session_owner
from antigravity_k.tools.browser_approval import BrowserApprovalGate, BrowserSecretVault
from antigravity_k.tools.browser_observation import ActionResult, ElementRef, Observation
from antigravity_k.tools.browser_session_ledger import HostSessionLedger
from antigravity_k.tools.browser_session_owner import BrowserOwner, BrowserSessionOwner
from tests.test_r45_authenticated_task_ownership import OwnerCase
from tests.test_r45_authenticated_task_ownership import owner_case as owner_case

ACTION = "/api/agent/tools/browser/action"
SESSION_HEADER = "X-AGK-Browser-Session"
SESSION = "r56-synthetic-browser"


@dataclass(slots=True)
class SyntheticPage:
    url: str = "https://browser-fixture.invalid/form"

    async def evaluate(self, expression: str) -> dict[str, object]:
        # The real handoff detector receives only these synthetic page facts.
        return {"mfa": [], "captcha": [], "mfa_text": False, "captcha_text": False}


@dataclass(slots=True)
class SyntheticObserver:
    owner: BrowserOwner
    page: SyntheticPage
    generation: int = 1
    actions: list[str] = field(default_factory=list)

    @property
    def session_tag(self) -> str:
        return self.owner.key[:6]

    @property
    def ref(self) -> str:
        return f"{self.session_tag}-snap-main-e1"

    def element_fact(self, ref: str | None, page_key: str | None = None) -> dict[str, object] | None:
        if ref != self.ref:
            return None
        return {"role": "button", "name": "Send message", "tag": "button", "url": self.page.url,
                "generation": self.generation, "secret": False, "disabled": False}

    def page_fact(self) -> dict[str, object]:
        return {"url": self.page.url, "generation": self.generation}

    async def observe(self, *, screenshot: bool = False) -> Observation:
        assert screenshot is False
        return Observation(
            session_tag=self.session_tag, snapshot_id="r56-synthetic-snapshot", generation=self.generation,
            page_key="main", url=self.page.url, title="합성 승인 화면", captured_at="2026-10-28T00:00:00Z",
            refs=(ElementRef(ref=self.ref, role="button", name="Send message", tag="button", frame="main"),),
        )

    async def act(self, action: str, **kwargs: object) -> ActionResult:
        assert action == "click" and kwargs["ref"] == self.ref
        self.actions.append(action)
        return ActionResult(action=action, performed=True, goal_verified=True, detail="합성 클릭 관측",
                            ref=self.ref, snapshot_id="r56-synthetic-snapshot", generation=self.generation,
                            url_before=self.page.url, url_after=self.page.url)


@dataclass(frozen=True, slots=True)
class BrowserCase:
    ownership: OwnerCase
    manager: ApprovalManager
    gate: BrowserApprovalGate
    observers: dict[str, SyntheticObserver]

    def headers(self, subject: str = "user", session: str = SESSION) -> dict[str, str]:
        return {**self.ownership.headers[subject], SESSION_HEADER: session}

    def observer(self, subject: str = "user", session: str = SESSION) -> SyntheticObserver:
        return self.observers[BrowserOwner(subject=subject, scope=session).key]

    def request_approval(self) -> str:
        client = self.ownership.client
        observed = client.post(ACTION, headers=self.headers(), json={"action": "observe"})
        assert observed.status_code == 200
        ref = observed.json()["observation"]["refs"][0]["ref"]
        asked = client.post(ACTION, headers=self.headers(), json={"action": "click", "ref": ref})
        assert asked.status_code == 428 and asked.json()["detail"]["requirement"]["effect"] == "transmit"
        request_id = asked.json()["detail"]["requirement"]["request_id"]
        request = self.manager.get_request(request_id)
        assert request is not None and request.scope["actor"] == "user"
        assert self.observer().actions == []
        return cast(str, request_id)


@pytest.fixture
def browser_case(owner_case: OwnerCase, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[BrowserCase]:
    manager = ApprovalManager()
    gate = BrowserApprovalGate()
    monkeypatch.setattr(approval_manager, "_approval_manager", manager)
    monkeypatch.setattr(browser_approval, "_gate", gate)
    monkeypatch.setattr(browser_approval, "_vault", BrowserSecretVault())
    sessions = BrowserSessionRegistry(max_sessions=8)
    monkeypatch.setattr(agent_tools, "browser_sessions", sessions)
    ledger = HostSessionLedger(path=tmp_path / "r56-browser-ledger.json", hostname="r56-synthetic-host")
    monkeypatch.setattr(browser_session_owner, "_owner", BrowserSessionOwner(max_active_sessions=8, ledger=ledger))
    observers: dict[str, SyntheticObserver] = {}

    def observer_for_request(request: Request, state: object, *, with_sandbox: bool) -> SyntheticObserver:
        owner = agent_tools._browser_owner(request)
        return observers[owner.key]

    monkeypatch.setattr(agent_tools, "_browser_observer", observer_for_request)
    for subject, session in (("user", SESSION), ("foreign", SESSION), ("user", "r56-other-browser")):
        owner = BrowserOwner(subject=subject, scope=session)
        page = SyntheticPage()
        observers[owner.key] = SyntheticObserver(owner, page)
        request = Request({"type": "http", "headers": [(SESSION_HEADER.lower().encode(), session.encode())]})
        request.state.auth_subject = subject
        state = sessions.get(agent_tools._browser_session_id(request))
        state.page = cast(object, page)
    owner_case.app.include_router(approval_api.router)
    owner_case.app.include_router(agent_tools.router)
    previous_mode = access_mode.get_access_mode()
    previous_policy = access_mode.get_execution_policy()
    monkeypatch.delenv(access_mode.EXECUTION_POLICY_ENV, raising=False)
    access_mode.set_access_mode(access_mode.AccessMode.FULL_ACCESS)
    # Even an explicitly autonomous request still needs the inner browser-effect
    # approval. The real outer PermissionGate is installed, not monkeypatched.
    access_mode.set_execution_policy(access_mode.ExecutionPolicy.AUTO_PILOT)
    try:
        yield BrowserCase(owner_case, manager, gate, observers)
    finally:
        access_mode.set_access_mode(previous_mode)
        access_mode.set_execution_policy(previous_policy)


def _resolve(case: BrowserCase, request_id: str) -> Response:
    return case.ownership.client.post(f"/api/approval/{request_id}/resolve", headers=case.headers(),
                                      json={"decision": "approve"})


def test_browser_owner_observes_approves_and_consumes_real_ticket_once(browser_case: BrowserCase) -> None:
    case, client = browser_case, browser_case.ownership.client
    request_id = case.request_approval()
    pending = client.get("/api/approval/pending", headers=case.headers())
    assert pending.status_code == 200 and [row["request_id"] for row in pending.json()["pending"]] == [request_id]
    detail = client.get(f"/api/approval/{request_id}", headers=case.headers())
    assert detail.status_code == 200 and detail.json()["always_allow_allowed"] is False
    assert _resolve(case, request_id).status_code == 200
    granted = client.post(f"/api/agent/tools/browser/approval/{request_id}/grant", headers=case.headers())
    assert granted.status_code == 200
    token = granted.json()["ticket"]["approval_token"]
    body = {"action": "click", "ref": case.observer().ref, "approval_token": token}
    clicked = client.post(ACTION, headers=case.headers(), json=body)
    assert clicked.status_code == 200 and clicked.json()["approval"]["consumed"] is True
    assert case.observer().actions == ["click"]
    replayed = client.post(ACTION, headers=case.headers(), json=body)
    assert replayed.status_code == 409 and case.observer().actions == ["click"]


@pytest.mark.parametrize("subject,session", [("foreign", SESSION), ("user", "r56-other-browser")])
def test_browser_pending_filters_actor_and_browser_session(browser_case: BrowserCase, subject: str, session: str) -> None:
    case, client = browser_case, browser_case.ownership.client
    request_id = case.request_approval()
    hidden = client.get("/api/agent/tools/browser/approval/pending", headers=case.headers(subject, session))
    assert hidden.status_code == 200 and hidden.json()["pending"] == [] and hidden.json()["count"] == 0
    assert hidden.json()["gate"]["pending"] == 0
    assert set(hidden.json()["gate"]) == {"ttl_seconds", "pending"}
    assert request_id not in hidden.text
    if subject == "foreign":
        general = client.get("/api/approval/pending", headers=case.headers(subject, session))
        assert general.status_code == 200 and general.json()["pending"] == []
    own = client.get("/api/agent/tools/browser/approval/pending", headers=case.headers())
    assert own.status_code == 200 and [row["request_id"] for row in own.json()["pending"]] == [request_id]


@pytest.mark.parametrize("subject,session", [("foreign", SESSION), ("user", "r56-other-browser")])
def test_foreign_browser_cannot_withdraw_an_owner_request(browser_case: BrowserCase, subject: str, session: str) -> None:
    case, client = browser_case, browser_case.ownership.client
    request_id = case.request_approval()
    rejected = client.post(f"/api/agent/tools/browser/approval/{request_id}/withdraw", headers=case.headers(subject, session))
    assert rejected.status_code == 403 and case.gate.pending(request_id) is not None
    own = client.post(f"/api/agent/tools/browser/approval/{request_id}/withdraw", headers=case.headers())
    assert own.status_code == 200 and own.json()["withdrawn"] is True and case.gate.pending(request_id) is None


def test_foreign_grant_is_rejected_before_pending_status_is_exposed(browser_case: BrowserCase) -> None:
    case = browser_case
    request_id = case.request_approval()
    rejected = case.ownership.client.post(f"/api/agent/tools/browser/approval/{request_id}/grant", headers=case.headers("foreign"))
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["error_code"] == browser_approval.APPROVAL_BINDING_CHANGED
    assert "status" not in rejected.json()["detail"]
    assert case.manager.get_request(request_id).status is ApprovalStatus.PENDING


@pytest.mark.parametrize("change", ["generation", "origin"])
def test_owner_still_needs_reapproval_when_live_page_binding_changes(browser_case: BrowserCase, change: str) -> None:
    case = browser_case
    request_id = case.request_approval()
    assert _resolve(case, request_id).status_code == 200
    if change == "generation":
        case.observer().generation += 1
    else:
        case.observer().page.url = "https://other-browser-fixture.invalid/form"
    changed = case.ownership.client.post(f"/api/agent/tools/browser/approval/{request_id}/grant", headers=case.headers())
    assert changed.status_code == 409
    assert changed.json()["detail"]["error_code"] == browser_approval.APPROVAL_BINDING_CHANGED
    assert case.observer().actions == []


def test_browser_approval_endpoints_require_actual_authentication(browser_case: BrowserCase) -> None:
    case, client = browser_case, browser_case.ownership.client
    request_id = case.request_approval()
    assert client.get("/api/agent/tools/browser/approval/pending").status_code == 401
    for suffix in ("grant", "withdraw"):
        assert client.post(f"/api/agent/tools/browser/approval/{request_id}/{suffix}").status_code == 401
    assert case.gate.pending(request_id) is not None and case.observer().actions == []


def test_autonomous_browser_producer_records_the_verified_owner_for_general_api(browser_case: BrowserCase) -> None:
    from antigravity_k.agents.browser_surfing_agent import BrowserSurfingAgent
    from antigravity_k.agents.browser_task_loop import PlannedAction

    case = browser_case
    observer = case.observer()
    portal = case.ownership.client.portal
    assert portal is not None
    agent = BrowserSurfingAgent()
    message = portal.call(agent._approval_block, observer, observer.owner, observer.ref,
                          PlannedAction(action="click", ref=observer.ref))
    assert message is not None and message.startswith("approval_required(request=")
    request_id = message.split("request=", 1)[1].split(",", 1)[0]
    request = case.manager.get_request(request_id)
    assert request is not None and request.scope["actor"] == "user"
    listed = case.ownership.client.get("/api/approval/pending", headers=case.headers())
    assert listed.status_code == 200 and [row["request_id"] for row in listed.json()["pending"]] == [request_id]
    foreign = case.ownership.client.get("/api/approval/pending", headers=case.headers("foreign"))
    assert foreign.status_code == 200 and foreign.json()["pending"] == []
    assert _resolve(case, request_id).status_code == 200 and observer.actions == []
