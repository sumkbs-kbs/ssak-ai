"""CR-14 F-33 회귀 — '항상 허용'(always_allow) 부여의 **범위·수명·동의**.

발견(F-33, attempt-025)
=======================
attempt-023/024 는 `ApprovalManager` 의 '항상 허용' 상태를 제품의 승인 경로
(`ApprovalDecision.ALWAYS_ALLOW`)로 만들었다. 그 상태가 제품에서 **무엇을 덮고**, **언제까지
살아 있고**, **사용자가 무엇에 동의했는지**는 재지 않았다. 실물 코드를 재 보니:

- 부여는 `set[str]` 였다 — **도구 이름 하나**만 남아, 언제·무엇 때문에 주어졌는지가 사라졌다.
- 부여를 **읽을** 표면이 없었다(해제만 있었다) — 보이지 않는 영구 부여는 동의가 아니다.
- 부여된 도구가 **동의 없이** 실행된 횟수를 아무도 세지 않았다.
- 그리고 해제를 읽으려고 만든 `GET /api/approval/always-allowed` 는 `GET /{request_id}` **뒤에**
  선언되어 요청 ID 로 해석됐다(404) — 경로 순서가 조용한 결함을 만들었다.

이 파일은 그 다섯 요구를 제품 경로에서 고정한다:

  R1. 같은 사용자에게 부여 범위는 **도구 전체**이고(인자·경로·프로젝트 무관), UI가 그 범위를 말한다.
  R2. 부여는 **읽을 수 있다**(매니저 API + 라우트, `/{request_id}` 에 가려지지 않는다).
  R3. 부여는 **되돌릴 수 있고**, 해제가 무엇을 되돌렸는지 말한다.
  R4. 부여는 **언제·무엇에 대해** 주어졌는지 보존한다(만료는 프로세스 수명 — 세션 한정이 아니다).
  R5. 동의 없이 실행된 호출이 **부여 기록에서 관측**된다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import (
    reset_bound_request_execution_context,
    set_bound_request_execution_context,
)
from antigravity_k.api.routes import approval_api
from antigravity_k.api.routes.approval_api import router
from antigravity_k.engine.approval_manager import (
    AlwaysAllowGrant,
    ApprovalDecision,
    ApprovalManager,
    ApprovalStatus,
    get_approval_manager,
    reset_approval_manager,
)
from antigravity_k.engine.tool_executor import ToolExecutor, _BoundApprovalUse

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = "run_bash_command"
TEST_ACTOR = "always-allow-unit-user"


@pytest.fixture()
def manager() -> Iterator[ApprovalManager]:
    """각 테스트마다 깨끗한 매니저 — 싱글턴 오염을 남기지 않는다."""
    m = ApprovalManager(default_timeout_sec=10)
    yield m


@pytest.fixture()
def client(manager: ApprovalManager, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """합성 인증 사용자의 라우트와 실제 매니저를 연결한다."""
    monkeypatch.setattr(approval_api, "get_approval_manager", lambda: manager)
    context = RequestExecutionContext(
        request_id="always-allow-unit-request",
        project_id="always-allow-unit-project",
        canonical_project_root=str(tmp_path),
        conversation_id="always-allow-unit-conversation",
        conversation_revision=0,
        actor_subject=TEST_ACTOR,
        session_id="always-allow-unit-session",
        model_id="synthetic-unused-model",
    )
    token = set_bound_request_execution_context(context)
    app = FastAPI()

    @app.middleware("http")
    async def install_test_actor(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.auth_subject = TEST_ACTOR
        return await call_next(request)

    app.include_router(router)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        reset_bound_request_execution_context(token)


def _grant(manager: ApprovalManager, tool: str = TOOL, description: str = f"{TOOL} 실행") -> None:
    """제품 경로로 부여한다 — 해결(ALWAYS_ALLOW)이 유일한 부여 경로다."""
    request = manager.request_approval(tool, {"command": "echo hello"}, description=description)
    assert manager.resolve(request.request_id, ApprovalDecision.ALWAYS_ALLOW)


# ─── R1 · R4: 범위와 기록 ────────────────────────────────────────────────


class TestGrantScopeAndRecord:
    def test_explicit_server_actor_owns_grant_and_auto_approval(self, manager: ApprovalManager) -> None:
        request = manager.request_approval(TOOL, {"command": "echo synthetic"}, actor_subject="synthetic-owner")
        assert request.scope["actor"] == "synthetic-owner"
        assert not manager.resolve(request.request_id, ApprovalDecision.ALWAYS_ALLOW, actor_subject="synthetic-other")
        assert request.status == ApprovalStatus.PENDING
        assert manager.resolve(request.request_id, ApprovalDecision.ALWAYS_ALLOW, actor_subject="synthetic-owner")

        repeated = manager.request_approval(TOOL, {"command": "echo again"}, actor_subject="synthetic-owner")
        assert repeated.status == ApprovalStatus.ALWAYS_ALLOW
        assert repeated.scope["actor"] == "synthetic-owner"
        other = manager.request_approval(TOOL, {"command": "echo synthetic"}, actor_subject="synthetic-other")
        assert other.status == ApprovalStatus.PENDING
        assert manager.always_allowed_grants(actor_subject="synthetic-other") == []
        assert manager.reset_always_allowed(actor_subject="synthetic-other") == []
        own = manager.always_allowed_grants(actor_subject="synthetic-owner")
        assert len(own) == 1
        assert own[0].auto_approved_count == 1
        assert manager.reset_always_allowed(actor_subject="synthetic-owner") == [TOOL]
        assert manager.always_allowed_grants() == []

    def test_grant_covers_the_whole_tool_not_the_approved_call(self, manager: ApprovalManager) -> None:
        """동의한 것은 `echo hello` 한 번이지만 부여는 도구 전체를 덮는다 — UI 가 그렇게 말해야 한다."""
        _grant(manager)

        other_call = manager.request_approval(TOOL, {"command": "rm -rf /tmp/whatever"})
        assert other_call.status == ApprovalStatus.ALWAYS_ALLOW
        # 다른 도구는 덮지 않는다(범위가 도구 단위라는 진술의 반대편).
        assert manager.is_always_allowed("write_file") is False

    def test_grant_records_when_and_why(self, manager: ApprovalManager) -> None:
        """부여는 시각과 근거를 남긴다 — 근거 없는 영구 부여는 감사할 수 없다."""
        _grant(manager, description="run_bash_command 실행")

        grants = manager.always_allowed_grants()
        assert len(grants) == 1
        grant = grants[0]
        assert isinstance(grant, AlwaysAllowGrant)
        assert grant.tool_name == TOOL
        assert grant.granted_at > 0
        assert grant.granted_for == "run_bash_command 실행"
        assert grant.auto_approved_count == 0
        assert grant.last_auto_approved_at is None

    def test_grants_are_listed_in_grant_order(self, manager: ApprovalManager) -> None:
        _grant(manager, "edit_file")
        _grant(manager, "write_file")

        assert [grant.tool_name for grant in manager.always_allowed_grants()] == [
            "edit_file",
            "write_file",
        ]

    def test_grant_has_no_expiry_and_dies_with_the_process(
        self, manager: ApprovalManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """부여는 세션 한정이 아니라 **프로세스 수명**이다(만료 시각이 없다) — 그 사실을 고정한다."""
        _grant(manager)

        import antigravity_k.engine.approval_manager as am

        far_future = am.time.time() + 365 * 24 * 3600
        monkeypatch.setattr(am.time, "time", lambda: far_future)
        assert manager.is_always_allowed(TOOL) is True

        # 프로세스가 새로 뜨면 부여는 없다(영속화하지 않는다).
        assert ApprovalManager().is_always_allowed(TOOL) is False

    def test_grant_is_process_wide_not_session_scoped(self) -> None:
        """같은 사용자는 세션·프로젝트가 달라도 같은 프로세스의 부여를 본다."""
        reset_approval_manager()
        try:
            first = get_approval_manager()
            _grant(first)
            assert get_approval_manager().is_always_allowed(TOOL) is True
        finally:
            reset_approval_manager()


# ─── R2: 읽기 표면 ──────────────────────────────────────────────────────


class TestGrantIsReadable:
    def test_route_lists_grants_even_though_a_request_id_route_exists(
        self, client: TestClient, manager: ApprovalManager
    ) -> None:
        """`/always-allowed` 는 `/{request_id}` 에 **가려지지 않는다**.

        이 경로가 뒤에 선언되면 서버는 `always-allowed` 를 요청 ID 로 읽어 404 를 낸다 —
        attempt-025 에서 실제로 났던 결함이다.
        """
        _grant(manager)

        response = client.get("/api/approval/always-allowed")
        assert response.status_code == 200, response.text
        payload = cast(dict[str, object], response.json())
        assert payload["count"] == 1
        grants = cast(list[dict[str, object]], payload["grants"])
        assert grants[0]["tool_name"] == TOOL
        assert grants[0]["granted_for"] == f"{TOOL} 실행"

    def test_request_id_route_still_resolves_a_real_id(self, client: TestClient, manager: ApprovalManager) -> None:
        """반대편도 살아 있어야 한다 — 전용 경로를 앞으로 옮기면서 ID 조회를 깨면 안 된다."""
        request = manager.request_approval(TOOL, {"command": "echo hello"})

        response = client.get(f"/api/approval/{request.request_id}")
        assert response.status_code == 200
        assert cast(dict[str, object], response.json())["tool_name"] == TOOL

    def test_reading_grants_is_not_a_side_effect_free_alias_of_counting(self, manager: ApprovalManager) -> None:
        """읽기는 감사 기록을 바꾸지 않는다 — 조회가 세는 값이 되면 안 된다."""
        _grant(manager)

        for _ in range(3):
            assert manager.is_always_allowed(TOOL) is True
            _ = manager.always_allowed_grants()

        grant = manager.always_allowed_grants()[0]
        assert grant.auto_approved_count == 0
        assert grant.last_auto_approved_at is None


# ─── R3: 되돌리기 ───────────────────────────────────────────────────────


class TestGrantIsRevocable:
    def test_reset_names_what_it_revoked(self, manager: ApprovalManager) -> None:
        _grant(manager, "edit_file")
        _grant(manager, "write_file")

        revoked = manager.reset_always_allowed()

        assert revoked == ["edit_file", "write_file"]
        assert manager.always_allowed_grants() == []
        assert manager.is_always_allowed("edit_file") is False

    def test_reset_route_reports_the_revoked_tools(self, client: TestClient, manager: ApprovalManager) -> None:
        _grant(manager)

        response = client.post("/api/approval/reset-always-allowed")
        assert response.status_code == 200
        payload = cast(dict[str, object], response.json())
        assert payload["ok"] is True
        assert payload["revoked"] == [TOOL]
        assert "1건" in cast(str, payload["message"])


# ─── R5: 동의 없는 실행의 관측 ───────────────────────────────────────────


class TestUnconsentedRunsAreCounted:
    def test_auto_request_requires_successful_consumption_after_revocation(
        self, manager: ApprovalManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _grant(manager)
        grant = manager.always_allowed_grants()[0]
        consume = manager.consume_always_allowed

        def revoke_before_consume(tool_name: str, *, actor_subject: str | None = None) -> bool:
            assert manager.reset_always_allowed(actor_subject=actor_subject) == [TOOL]
            return consume(tool_name, actor_subject=actor_subject)

        monkeypatch.setattr(manager, "is_always_allowed", lambda tool_name, *, actor_subject=None: True)
        monkeypatch.setattr(manager, "consume_always_allowed", revoke_before_consume)
        request = manager.request_approval(TOOL, {"command": "echo synthetic"})

        assert request.status == ApprovalStatus.PENDING
        assert manager.get_pending() == [request]
        assert grant.auto_approved_count == 0
        assert manager.always_allowed_grants() == []

    def test_consumption_checks_owner_and_revocation(self, manager: ApprovalManager) -> None:
        request = manager.request_approval(TOOL, {"command": "echo synthetic"}, actor_subject="synthetic-owner")
        assert manager.resolve(request.request_id, ApprovalDecision.ALWAYS_ALLOW, actor_subject="synthetic-owner")
        grant = manager.always_allowed_grants(actor_subject="synthetic-owner")[0]

        assert not manager.consume_always_allowed(TOOL, actor_subject="synthetic-other")
        assert grant.auto_approved_count == 0
        assert manager.consume_always_allowed(TOOL, actor_subject="synthetic-owner")
        assert grant.auto_approved_count == 1
        assert manager.reset_always_allowed(actor_subject="synthetic-owner") == [TOOL]
        assert not manager.consume_always_allowed(TOOL, actor_subject="synthetic-owner")
        assert grant.auto_approved_count == 1

    def test_manager_counts_each_auto_approved_request(self, manager: ApprovalManager) -> None:
        _grant(manager)

        manager.request_approval(TOOL, {"command": "ls"})
        manager.request_approval(TOOL, {"command": "pwd"})

        grant = manager.always_allowed_grants()[0]
        assert grant.auto_approved_count == 2
        assert grant.last_auto_approved_at is not None

    def test_counting_without_a_grant_never_creates_one(self, manager: ApprovalManager) -> None:
        """순수 조회·기록 경로는 부여를 만들지 않는다 — 기록이 동의가 되면 안 된다."""
        manager.record_auto_approval("write_file")
        assert manager.always_allowed_grants() == []

    def test_executor_counts_when_bound_approval_is_consumed(
        self, manager: ApprovalManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """승인 등록·확인은 세지 않고, 실행 경계에서 승인을 소비할 때 센다."""
        _grant(manager)
        monkeypatch.setattr("antigravity_k.engine.approval_manager.get_approval_manager", lambda: manager)
        monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: manager)

        executor = ToolExecutor(
            tool_registry=cast(MagicMock, MagicMock()),
            permission_gate=cast(MagicMock, MagicMock()),
            project_root=".",
        )
        proceed, request_id = executor._register_approval_request(  # noqa: SLF001
            TOOL, {"command": "ls"}, "실행"
        )

        assert proceed is not None  # r40: always-allow sentinel evidence
        assert request_id == ""
        grant = manager.always_allowed_grants()[0]
        assert grant.auto_approved_count == 0
        approval_use = _BoundApprovalUse(executor, TOOL, {"command": "ls"}, proceed)
        assert approval_use.verify() == ""
        assert grant.auto_approved_count == 0
        assert approval_use.consume() == ""
        assert grant.auto_approved_count == 1
        # 자동 승인 경로는 새 요청을 만들지 않는다 — 남은 대기열이 비어 있어야 한다.
        assert manager.get_pending() == []


# ─── R1: 동의 문구가 범위를 말하는가 ─────────────────────────────────────


class TestAgreementTextStatesTheScope:
    """대시보드가 '도구 전체'를 말하는지 소스 계약으로 고정한다(CR-05 와 같은 방식)."""

    @staticmethod
    def _source(relative: str) -> str:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} 가 없다"
        return path.read_text(encoding="utf-8")

    def test_always_allow_control_states_tool_wide_scope(self) -> None:
        source = self._source("dashboard/src/features/task-execution/ApprovalQueue.tsx")

        assert "도구를 항상 허용 (이후 모든 호출을 승인 없이 실행)" in source
        assert "도구 전체" in source
        assert "인자·경로·프로젝트와 무관하게" in source

    def test_queue_reads_and_revokes_the_grants(self) -> None:
        queue = self._source("dashboard/src/features/task-execution/ApprovalQueue.tsx")
        api = self._source("dashboard/src/features/task-execution/approvalApi.ts")

        assert "/api/approval/always-allowed" in api
        assert "/api/approval/reset-always-allowed" in api
        # 부여 목록과 해제 컨트롤이 화면에 있다.
        assert "부여 모두 해제" in queue
        assert "동의 없이" in queue
        assert re.search(r"부여 근거", queue) is not None
