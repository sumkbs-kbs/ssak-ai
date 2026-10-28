"""Shared agent-session primitives for streaming routes.

스트림 라우트 전반에서 공유하는 활성 에이전트 세션 상태와
WebSocket 인증 헬퍼를 담는 중립 모듈이다. 라우트 모듈 간에는
이 모듈을 향한 의존만 허용하고, 모듈 간 직접 임포트(역류)는 하지 않는다.
"""

import logging
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, WebSocket

from antigravity_k.api.contracts.execution_context import RequestExecutionContext

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
    "ActiveResponseBody",
    "active_response_snapshot",
    "aclose_authorized_ws",
    "authorized_ws_count",
    "close_authorized_ws_blocking",
    "close_unauthorized_ws",
    "begin_active_response",
    "ensure_active_response_available",
    "finish_active_response",
    "get_active_session",
    "register_authorized_ws",
    "reset_active_session",
    "reset_authorized_ws_registry",
]


@dataclass(frozen=True)
class ActiveResponseOwner:
    actor_subject: str
    project_id: str
    canonical_project_root: str
    session_id: str

    @classmethod
    def from_context(cls, context: RequestExecutionContext) -> "ActiveResponseOwner":
        return cls(context.actor_subject, context.project_id, context.canonical_project_root, context.session_id)


@dataclass(frozen=True)
class ActiveResponseSnapshot:
    generation: int
    q: str
    is_active: bool
    history: tuple[str, ...]
    done: bool
    error: str | None


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
        self.owner: ActiveResponseOwner | None = None
        self.generation: int = 0


_active_session = ActiveAgentSession()
_active_session_lock = threading.RLock()


def get_active_session() -> ActiveAgentSession:
    """활성 세션 싱글톤을 반환합니다.

    세션 교체는 바인딩 재할당이 아니라 reset_active_session()으로 수행한다.
    값 복사 임포트를 하는 소비자 모듈이 있어도 바인딩이 흐트러지지 않는다.
    """
    return _active_session


def reset_active_session() -> ActiveAgentSession:
    """세션 필드를 초기화하되 싱글톤 객체 정체는 유지합니다."""
    with _active_session_lock:
        _active_session.q = ""
        _active_session.is_active = False
        _active_session.history.clear()
        _active_session.done = False
        _active_session.error = None
        _active_session.orchestrator = None
        _active_session.owner = None
        _active_session.generation += 1
        return _active_session


def ensure_active_response_available(context: RequestExecutionContext | None) -> None:
    """Reject replacement of a running response before route side effects."""
    with _active_session_lock:
        if not _active_session.is_active:
            return
        owner = ActiveResponseOwner.from_context(context) if context is not None else None
        if _active_session.owner != owner:
            raise HTTPException(status_code=404, detail="Active response not found")
        raise HTTPException(status_code=409, detail="An agent response is already active")


def begin_active_response(context: RequestExecutionContext | None, q: str = "") -> ActiveAgentSession:
    """Atomically claim the singleton; None is reserved for internal legacy callers."""
    with _active_session_lock:
        ensure_active_response_available(context)
        session = reset_active_session()
        session.owner = ActiveResponseOwner.from_context(context) if context is not None else None
        session.q = q
        session.is_active = True
        return session


def finish_active_response(generation: int) -> None:
    """Only the response that acquired this generation may release it."""
    with _active_session_lock:
        if _active_session.generation == generation:
            _active_session.is_active = False


class ActiveResponseBody(AsyncGenerator[str, None]):
    """Release a claimed response even when headers fail before iteration starts."""

    def __init__(self, body: AsyncGenerator[str, None], generation: int) -> None:
        self._body = body
        self._generation = generation

    def __aiter__(self) -> AsyncGenerator[str, None]:
        return self

    async def __anext__(self) -> str:
        return await self.asend(None)

    async def asend(self, value: None) -> str:
        try:
            return await self._body.asend(value)
        except StopAsyncIteration:
            finish_active_response(self._generation)
            raise

    async def athrow(
        self,
        typ: type[BaseException] | BaseException,
        val: BaseException | None = None,
        tb: TracebackType | None = None,
    ) -> str:
        try:
            if val is None and tb is None:
                return await self._body.athrow(typ)
            return await self._body.athrow(typ, val, tb)
        except StopAsyncIteration:
            finish_active_response(self._generation)
            raise

    async def aclose(self) -> None:
        await self._body.aclose()
        finish_active_response(self._generation)


def _authorize_active_response(request: Request) -> None:
    session = _active_session
    if session.owner is None:
        if session.is_active or session.q or session.history or session.error:
            raise HTTPException(status_code=404, detail="Active response not found")
        return
    from antigravity_k.api import project_binding

    owner = session.owner
    actor = getattr(request.state, "auth_subject", None)
    actor = actor.strip() if isinstance(actor, str) and actor.strip() else "anonymous"
    session_id = project_binding.extract_session_id_from_payload(
        {"session_id": request.query_params.get("session_id")},
        header_session_id=request.headers.get(project_binding.SESSION_ID_HEADER),
    )
    project_id = (request.query_params.get("project_id") or "").strip()
    binding = project_binding.get_session_active_project(session_id)
    if not project_id and binding is not None:
        project_id = binding.project_id
    # Existing reconnect clients omit project_id; the stored server-resolved root
    # remains authority only after the actor and session match exactly.
    project_id = project_id or owner.project_id
    if (
        actor != owner.actor_subject
        or session_id != owner.session_id
        or project_id != owner.project_id
        or project_binding.get_project_registry().resolve_canonical_root(project_id) != owner.canonical_project_root
    ):
        raise HTTPException(status_code=404, detail="Active response not found")


def active_response_snapshot(
    request: Request | None = None,
    *,
    generation: int | None = None,
) -> ActiveResponseSnapshot | None:
    """Copy only the authorized response generation; never follow a reused singleton.

    HTTP routes always pass Request. A missing request supports existing trusted
    internal callers and fixtures, which are not an authentication entry point.
    """
    with _active_session_lock:
        if generation is not None and _active_session.generation != generation:
            return None
        if request is not None:
            _authorize_active_response(request)
        session = _active_session
        return ActiveResponseSnapshot(
            session.generation, session.q, session.is_active, tuple(session.history), session.done, session.error
        )


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
