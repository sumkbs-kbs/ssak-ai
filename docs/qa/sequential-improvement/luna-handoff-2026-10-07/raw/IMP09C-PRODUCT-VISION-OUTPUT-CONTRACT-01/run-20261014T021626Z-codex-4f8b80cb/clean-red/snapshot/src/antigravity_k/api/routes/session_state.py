"""Shared agent-session primitives for streaming routes.

스트림 라우트 전반에서 공유하는 활성 에이전트 세션 상태와
WebSocket 인증 헬퍼를 담는 중립 모듈이다. 라우트 모듈 간에는
이 모듈을 향한 의존만 허용하고, 모듈 간 직접 임포트(역류)는 하지 않는다.
"""

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

# ── NX-05: 인증된 WebSocket 연결 레지스트리 ────────────────────────────────
# NX-10: 구현은 leaf 모듈 `antigravity_k.security.ws_registry` 로 내렸다. 이 모듈은
# `auth_routes`(토큰 검증)를 임포트하므로, 레지스트리가 여기 있으면 PIN 변경 라우트가
# 폐기 함수를 부르기 위한 `auth_routes → session_state` 임포트가 **순환**이 된다.
# 기존 호출자/테스트를 깨지 않기 위해 이름은 여기서 다시 내보낸다(재바인딩).
from antigravity_k.security.ws_registry import (
    aclose_authorized_ws,
    authorized_ws_count,
    close_authorized_ws_blocking,
    register_authorized_ws,
    reset_authorized_ws_registry,
)

if TYPE_CHECKING:
    from antigravity_k.engine.agent_runtime import OrchestratorPort

logger = logging.getLogger("antigravity_k.api.session_state")

__all__ = [
    "ActiveAgentSession",
    "aclose_authorized_ws",
    "authorized_ws_count",
    "close_authorized_ws_blocking",
    "close_unauthorized_ws",
    "get_active_session",
    "register_authorized_ws",
    "reset_active_session",
    "reset_authorized_ws_registry",
]


class ActiveAgentSession:
    """Holds the currently active agent session state for streaming."""

    def __init__(self) -> None:
        """Initialize the ActiveAgentSession."""
        self.q: str = ""
        self.is_active: bool = False
        self.history: list[str] = []
        self.done: bool = False
        self.error: str | None = None
        self.orchestrator: OrchestratorPort | None = None


_active_session = ActiveAgentSession()


def get_active_session() -> ActiveAgentSession:
    """활성 세션 싱글톤을 반환합니다.

    세션 교체는 바인딩 재할당이 아니라 reset_active_session()으로 수행한다.
    값 복사 임포트를 하는 소비자 모듈이 있어도 바인딩이 흐트러지지 않는다.
    """
    return _active_session


def reset_active_session() -> ActiveAgentSession:
    """세션 필드를 초기화하되 싱글톤 객체 정체는 유지합니다."""
    _active_session.q = ""
    _active_session.is_active = False
    _active_session.history.clear()
    _active_session.done = False
    _active_session.error = None
    _active_session.orchestrator = None
    return _active_session


async def close_unauthorized_ws(websocket: WebSocket) -> bool:
    """Close WebSocket if not authorized. Returns True if closed.

    SEC-01 단일 정책: 판정은 HTTP 미들웨어와 같은 공유 AuthPolicy로 수행한다.
    저장 PIN hash가 있으면 loopback 개발 모드도 보호 상태이며, 익명 허용은
    명시적 dev 설정 + loopback + credential 전무 조건에서만 가능하다.

    SEC-03 보호 순서:
      1. **Origin allowlist** — browser 클라이언트(Origin 헤더 존재)는
         allowlist 정확 일치만 허용. 불일치는 4403 거절 (cross-site 차단).
         Origin이 없으면 browser가 아닌 클라이언트(curl/CLI)로 보고 통과.
      2. **credential** — bearer token(``Sec-WebSocket-Protocol`` subprotocol
         채널) 또는 단기 1회성 ticket(``?ticket=``). PIN query는 SEC-02에서
         이미 제거되었고, 장기 bearer의 **query 전달도 제거**되었다 — URL은
         로그/browser history에 남으므로 credential이 노출된다 (plan §SEC-03).
      3. 판정은 공유 AuthPolicy(ticket/bearer 검증 결과를 token_verified로
         반영) — 실패는 4401 거절.
    """
    from antigravity_k.api.auth_policy import get_shared_auth_policy
    from antigravity_k.api.auth_routes import get_token_service
    from antigravity_k.config import config
    from antigravity_k.engine.auth import extract_token_from_ws
    from antigravity_k.security.ws_origin import ws_origin_allowed

    # Accept first so we can send a close code; Starlette requires accept before close.
    await websocket.accept()
    websocket.state.agk_accepted = True

    # ── SEC-03 1단계: Origin allowlist (cross-site browser 차단) ──
    origin: str | None = None
    try:
        origin = websocket.headers.get("origin") or None
    except AttributeError:
        origin = None  # 테스트 더블 등 headers가 없는 클라이언트
    if not ws_origin_allowed(origin):
        await websocket.close(code=4403, reason="Origin not allowed")
        return True

    # ── SEC-03 2단계: credential — subprotocol bearer 또는 단기 ticket ──
    credential = extract_token_from_ws(websocket)
    ticket: str | None = None
    try:
        ticket = websocket.query_params.get("ticket") or None
    except AttributeError:
        ticket = None

    token_verified = False
    token_subject: str | None = None
    if credential and "." in credential:
        claims = get_token_service().verify_token(credential)
        if claims is not None:
            token_verified = True
            subject = claims.get("sub")
            token_subject = subject if isinstance(subject, str) and subject else "bearer"
    elif ticket:
        from antigravity_k.security.ws_ticket import get_ws_ticket_service

        ticket_subject = get_ws_ticket_service().consume(ticket)
        if ticket_subject is not None:
            token_verified = True
            token_subject = ticket_subject

    # SEC-02: evaluate_credential은 PIN credential을 받지 않는다.
    decision = get_shared_auth_policy().evaluate_credential(
        token_verified=token_verified,
        host=config.server.host,
    )
    if decision.level == "open_loopback":
        websocket.state.auth_subject = "loopback"
        return False
    if token_verified and token_subject is not None:
        websocket.state.auth_subject = token_subject
        # NX-05: 인증된 연결을 등록 — PIN 변경 시 이 연결을 즉시 닫는다.
        # (익명 open_loopback 연결은 폐기할 credential 이 없어 등록하지 않는다.)
        register_authorized_ws(websocket)
        return False

    # SEC-02/SEC-03: WS는 subprotocol bearer 또는 단기 ticket만 수용한다 —
    # query ?pin= (SEC-02 제거)와 query ?token= (SEC-03 제거, URL credential
    # 노출) 모두 더 이상 인증 수단이 아니다.
    # No valid credential — deny (4401, plan 규정 equivalent).
    await websocket.close(code=4401, reason="Unauthorized")
    return True
