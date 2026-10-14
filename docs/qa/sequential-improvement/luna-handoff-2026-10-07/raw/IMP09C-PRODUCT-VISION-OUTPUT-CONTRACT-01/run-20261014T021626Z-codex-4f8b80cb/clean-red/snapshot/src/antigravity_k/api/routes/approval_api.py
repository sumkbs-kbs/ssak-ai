"""승인(Approval) API 라우트 (P1-3).

대시보드/클라이언트가 대기 중인 승인 요청을 조회하고 응답하는 엔드포인트.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from antigravity_k.engine.approval_manager import (
    NO_ALWAYS_ALLOW_TOOLS,
    ApprovalDecision,
    get_approval_manager,
)

logger = logging.getLogger("antigravity_k.api.approval")

router = APIRouter(prefix="/api/approval", tags=["approval"])


class ApprovalResponse(BaseModel):
    """승인 응답 요청 본문."""

    decision: str  # approve / deny / always_allow


class AlwaysAllowGrantPayload(BaseModel):
    """'항상 허용' 부여 한 건의 API 표현."""

    tool_name: str
    granted_at: float
    granted_for: str
    auto_approved_count: int
    last_auto_approved_at: float | None


class AlwaysAllowListPayload(BaseModel):
    """'항상 허용' 목록 응답."""

    grants: list[AlwaysAllowGrantPayload]
    count: int


class ResetAlwaysAllowedPayload(BaseModel):
    """'항상 허용' 해제 응답."""

    ok: bool
    revoked: list[str]
    message: str


@router.get("/pending")
async def list_pending_approvals():
    """대기 중인 승인 요청 목록을 반환합니다."""
    manager = get_approval_manager()
    pending = manager.get_pending()
    return {
        "pending": [req.to_dict() for req in pending],
        "count": len(pending),
    }


@router.get("/always-allowed", response_model=AlwaysAllowListPayload)
async def list_always_allowed():
    """'항상 허용' 부여 목록을 반환합니다.

    부여는 **도구 단위**이고 프로세스 수명 동안 유지되므로, 사용자가 그것을 **읽고 되돌릴 수**
    있어야 한다(F-33). 각 항목은 언제·무엇에 대해 주어졌는지와 **동의 없이 실행된 횟수**(#)를 낸다.

    경로가 `/{request_id}` 보다 **먼저** 선언되어야 한다 — 그렇지 않으면 `always-allowed` 가
    요청 ID 로 해석되어 404 가 된다(실측: attempt-025).
    """
    manager = get_approval_manager()
    grants = manager.always_allowed_grants()
    return {
        "grants": [grant.to_dict() for grant in grants],
        "count": len(grants),
    }


@router.get("/{request_id}")
async def get_approval_request(request_id: str):
    """특정 승인 요청의 상세 정보(diff 미리보기 포함)."""
    manager = get_approval_manager()
    request = manager.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")
    return request.to_dict()


@router.post("/{request_id}/resolve")
async def resolve_approval(request_id: str, response: ApprovalResponse):
    """승인 요청에 대한 사용자 결정을 처리합니다."""
    manager = get_approval_manager()

    try:
        decision = ApprovalDecision(response.decision)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"잘못된 결정 값: {response.decision}. approve/deny/always_allow 중 하나",
        )

    # '항상 허용' 이 성립하지 않는 도구는 **여기서** 막는다(승인 창이 그런 버튼을 보여 주면
    # 사용자는 눌렀는데 실행이 거절되는 것을 보게 된다). 정책은 엔진이 갖고 라우트는 묻기만 한다.
    if decision is ApprovalDecision.ALWAYS_ALLOW:
        existing = manager.get_request(request_id)
        if existing is not None and existing.tool_name in NO_ALWAYS_ALLOW_TOOLS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "always_allow_forbidden",
                    "detail": (
                        f"'{existing.tool_name}' 에는 '항상 허용' 을 줄 수 없습니다: 매 행동에 대해 "
                        "그 대상·내용·페이지 상태에 묶인 승인이 필요합니다"
                    ),
                },
            )

    success = manager.resolve(request_id, decision)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="승인 요청을 찾을 수 없거나 이미 해결되었습니다",
        )

    req = manager.get_request(request_id)
    return {
        "ok": True,
        "request_id": request_id,
        "status": req.status.value if req else "resolved",
    }


@router.post("/reset-always-allowed", response_model=ResetAlwaysAllowedPayload)
async def reset_always_allowed():
    """'항상 허용' 목록을 초기화합니다 (모든 도구를 다시 승인 필요로)."""
    manager = get_approval_manager()
    revoked = manager.reset_always_allowed()
    return {
        "ok": True,
        "revoked": revoked,
        "message": f"'항상 허용' 목록이 초기화되었습니다 ({len(revoked)}건)",
    }
