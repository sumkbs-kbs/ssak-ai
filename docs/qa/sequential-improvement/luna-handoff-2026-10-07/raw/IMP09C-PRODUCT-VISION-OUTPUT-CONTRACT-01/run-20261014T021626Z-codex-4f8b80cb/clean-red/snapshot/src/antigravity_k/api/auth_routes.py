"""Authentication API routes: login, token verify, logout.

Provides a token-exchange login flow on top of :mod:`antigravity_k.engine.auth`.
On first boot, the configured plaintext PIN is hashed and persisted so that
subsequent logins are verified against the hash (constant-time) rather than the
plaintext.

Routes
------
- ``POST /api/auth/login``  — exchange a PIN for a signed bearer token.
- ``POST /api/auth/change-pin`` — authenticated PIN change (``current_pin`` + ``new_pin``).
- ``POST /api/auth/verify`` — confirm a token is still valid.
- ``POST /api/auth/logout`` — informational; stateless tokens are client-revoked.

PIN length notes
----------------
- Non-loopback / production *bootstrap* of an initial plaintext PIN still requires
  at least 8 characters (see ``startup_security._MIN_PIN_LENGTH``).
- The authenticated change-pin endpoint accepts ``new_pin`` lengths of 4–128 so
  short local PINs (e.g. ``0000``) can be set after login.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, ParamSpec, Protocol, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from antigravity_k.config import config
from antigravity_k.engine.auth import TokenService, hash_pin, verify_pin
from antigravity_k.security.auth_state import (
    bump_epoch_atomic,
    current_epoch,
    read_auth_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Local limiter reference for the login route. The app-level limiter
# (registered in server.py via app.state.limiter) handles the SlowAPIMiddleware
# integration; per-route decorators reference a Limiter instance directly.
_P = ParamSpec("_P")
_R = TypeVar("_R")


class _RateLimitDecorator(Protocol):
    def __call__(self, function: Callable[_P, _R]) -> Callable[_P, _R]: ...


class _Limiter(Protocol):
    def limit(
        self,
        limit_value: str,
        key_func: Callable[..., str] | None = None,
        per_method: bool = False,
        methods: list[str] | None = None,
        error_message: str | None = None,
        exempt_when: Callable[..., bool] | None = None,
        cost: int | Callable[..., int] = 1,
        override_defaults: bool = True,
    ) -> _RateLimitDecorator: ...


_limiter: _Limiter = Limiter(key_func=get_remote_address, config_filename=os.environ.get("AGK_ENV_FILE"))


def _rate_limit(limit_value: str) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    return _limiter.limit(limit_value)


# ---------------------------------------------------------------------------
# Shared state — initialized once at import time via :func:`init_auth_state`.
# ---------------------------------------------------------------------------

_token_service: TokenService | None = None
_pin_hash: str | None = None


def init_auth_state() -> None:
    """Initialize the token service and bootstrap the PIN hash.

    Idempotent: safe to call multiple times. On first call it:
      1. Creates the :class:`TokenService` using the configured secret path.
      2. Loads an existing auth state (PIN hash + NX-05 epoch) from
         ``pin_hash_file`` if present — 구버전 한 줄 hash 파일도 읽는다.
      3. Otherwise hashes the configured plaintext ``access_pin`` and persists
         it (epoch 1) so future logins verify against the hash.

    NX-05: epoch 공급자는 파일을 **매 검증 때** 다시 읽는다(프로세스별 캐시 금지).
    """
    global _token_service, _pin_hash

    if _token_service is not None:
        return

    _token_service = TokenService(
        secret_path=config.security.token_secret_file,
        token_ttl_hours=config.security.token_ttl_hours,
        epoch_provider=get_current_auth_epoch,
    )

    # SEC-01: 공유 AuthPolicy를 현재 config 바인딩으로 (재)초기화 —
    # HTTP/WS/상태 endpoint가 이 policy 객체 하나를 공유한다.
    from antigravity_k.api.auth_policy import init_shared_auth_policy

    _ = init_shared_auth_policy(config.security.pin_hash_file)

    hash_path = Path(config.security.pin_hash_file)
    state = read_auth_state(hash_path)
    if state is None and hash_path.exists():
        logger.warning("Could not read auth state from %s", hash_path)
    if state is not None:
        _pin_hash = state.pin_hash
        try:
            hash_path.chmod(0o600)
        except OSError:
            logger.warning("Could not restrict PIN hash permissions on %s", hash_path)

    if _pin_hash is None and config.security.access_pin:
        # Bootstrap: hash the plaintext PIN and persist hash + epoch together.
        _pin_hash = hash_pin(config.security.access_pin)
        try:
            written = bump_epoch_atomic(hash_path, pin_hash=_pin_hash)
            logger.info("Bootstrapped PIN hash at %s (epoch=%s)", hash_path, written.epoch)
        except OSError:
            logger.warning("Could not persist PIN hash to %s", hash_path)


def get_current_auth_epoch() -> int:
    """현재 auth epoch — 매 호출 파일에서 다시 읽는다(캐시 금지).

    이 함수가 :class:`TokenService` 의 세대 공급자다. 다른 프로세스가 PIN 을
    바꾸면 이 프로세스의 다음 토큰 검증이 즉시 이전 세대를 거부한다.
    """
    return current_epoch(config.security.pin_hash_file)


def get_token_service() -> TokenService:
    """Return the singleton :class:`TokenService`, initializing if needed."""
    if _token_service is None:
        init_auth_state()
    assert _token_service is not None  # noqa: S101 — initialized above
    return _token_service


def get_current_pin_hash() -> str | None:
    """Return the active PIN hash (or None if auth is disabled).

    NX-05: 파일이 진실의 원본이다 — 매 호출 다시 읽는다(캐시 금지). 프로세스에
    hash 를 캐시하면 다른 프로세스가 PIN 을 바꾼 뒤에도 이 프로세스가 **구 PIN
    로그인을 계속 받아준다**(새 세대 토큰을 발급해 주므로 폐기가 무력해진다).
    저장 파일이 아예 없는 경우에만 시작 시 bootstrap 한 메모리 값을 쓴다.
    """
    if _token_service is None:
        init_auth_state()
    state = read_auth_state(config.security.pin_hash_file)
    if state is not None:
        # 파일이 있으면 그 값이 정답이다(pin_hash=null 이면 인증 비활성).
        return state.pin_hash
    return _pin_hash


def set_current_pin_hash(new_hash: str) -> None:
    """Update the in-memory PIN hash used when no state file exists.

    Callers that persist a new hash must also write ``pin_hash_file``; this
    setter only refreshes the fallback value used when the file is absent.
    """
    global _pin_hash
    _pin_hash = new_hash


def _persist_pin_hash_atomic(new_hash: str) -> Path:
    """Write PIN hash + next epoch as one atomic document (0600).

    NX-05: hash 와 세대는 같은 파일에 함께 교체된다 — 어느 쪽만 먼저 바뀌는 중간
    상태를 남기지 않는다(읽는 쪽은 항상 (이전 hash, 이전 epoch) 또는 (새 hash,
    새 epoch) 중 하나만 본다). 세대 계산과 교체는 파일 잠금으로 직렬화되므로
    동시 변경에서도 **성공 1건 = 새 세대 1개**다.
    """
    hash_path = Path(config.security.pin_hash_file)
    state = bump_epoch_atomic(hash_path, pin_hash=new_hash)
    logger.info("Persisted PIN hash at %s (epoch=%s)", hash_path, state.epoch)
    return hash_path


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Login request body."""

    pin: str = Field(..., description="The access PIN.")


class TokenResponse(BaseModel):
    """Successful login response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class VerifyResponse(BaseModel):
    """Token verification response."""

    valid: bool
    subject: str | None = None


class ChangePinRequest(BaseModel):
    """Authenticated PIN change request.

    ``new_pin`` allows 4–128 characters. Non-loopback bootstrap of an *initial*
    plaintext PIN still requires ≥8 characters (``startup_security``); this
    endpoint is intentionally more permissive for post-login changes.
    """

    current_pin: str = Field(..., min_length=1, max_length=128, description="Current access PIN.")
    new_pin: str = Field(
        ...,
        min_length=4,
        max_length=128,
        description="New access PIN (4–128 chars; bootstrap of initial plaintext still requires ≥8 off-loopback).",
    )


class ChangePinResponse(BaseModel):
    """Successful PIN change response.

    NX-05: PIN 변경은 이 버전부터 **세션을 모두 폐기**한다. 응답은 클라이언트가
    재로그인해야 함을 명시적으로 알린다(`reauth_required`). 새 세대(epoch)는
    관측용으로 함께 반환하며, 클라이언트는 이를 저장하지 않아도 된다.
    """

    ok: bool = True
    detail: str = "PIN updated. All sessions were revoked; sign in again."
    reauth_required: bool = True
    epoch: int = 0
    sessions_revoked: int = 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
@_rate_limit("5/minute")
def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Exchange a PIN for a signed bearer token.

    SEC-02: PIN은 이 route(rate-limited)에서만 수용한다. 두 겹의 방어:
      1. slowapi — IP당 요청 레이트 제한 (429)
      2. credential_gate — 실패 burst/sustained 임계 초과 시 lockout (403).
         lockout 중에는 PBKDF2 검증을 실행하지 않아 공격이 CPU를 소진하지 못한다.
    모든 성공/실패/lockout은 credential 없이 audit에 기록된다.
    """
    from antigravity_k.engine.operational_metrics import record_auth_event as record_auth_metric
    from antigravity_k.security.auth_audit import record_auth_event
    from antigravity_k.security.credential_gate import get_credential_gate

    remote = request.client.host if request.client else "unknown"
    gate = get_credential_gate()
    gate_key = f"ip:{remote}"

    # 1단계: credential gate — lockout이면 PBKDF2로 진입하지 않는다.
    gate_decision = gate.register(gate_key)
    if not gate_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Too many failed attempts. Retry after {max(1, int(gate_decision.retry_after_sec))}s.",
            headers={"Retry-After": str(max(1, int(gate_decision.retry_after_sec)))},
        )

    stored = get_current_pin_hash()

    if stored is None:
        # No PIN configured — auth is effectively disabled.
        logger.warning("Login attempted with no PIN hash configured.")
        record_auth_metric("failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )

    if not verify_pin(body.pin, stored):
        decision = gate.record_failure(gate_key)
        logger.info("Failed login attempt from %s", remote)
        record_auth_event("login_failed", remote)
        record_auth_metric("failed")
        if not decision.allowed:
            record_auth_event("lockout", remote, "failure threshold reached")
            record_auth_metric("lockout")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Too many failed attempts. Retry after {max(1, int(decision.retry_after_sec))}s.",
                headers={"Retry-After": str(max(1, int(decision.retry_after_sec)))},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN.",
        )

    gate.record_success(gate_key)
    record_auth_event("login_success", remote)
    record_auth_metric("success")
    token = get_token_service().issue_token(subject="user")
    return TokenResponse(access_token=token, expires_in=get_token_service().ttl_seconds)


@router.post("/change-pin", response_model=ChangePinResponse)
@_rate_limit("5/minute")
def change_pin(request: Request, body: ChangePinRequest) -> ChangePinResponse:
    """Change the access PIN (requires a valid bearer token).

    Verifies ``current_pin`` against the stored hash, then re-hashes ``new_pin``
    and persists it atomically (0600). Updates in-memory ``_pin_hash`` so login
    uses the new value immediately.

    Length policy: ``new_pin`` may be 4–128 characters. Non-loopback / production
    bootstrap of an *initial* plaintext PIN still requires ≥8 characters
    (``startup_security._MIN_PIN_LENGTH``); this authenticated change path is
    intentionally more permissive for local short PINs.

    Audit events never include PIN plaintext.
    """
    from antigravity_k.security.auth_audit import record_auth_event

    remote = request.client.host if request.client else "unknown"
    subject = getattr(request.state, "auth_subject", None)
    if not isinstance(subject, str) or not subject:
        # Middleware should already reject unauthenticated callers; fail closed.
        record_auth_event("pin_change_failed", remote, "unauthenticated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    stored = get_current_pin_hash()
    if stored is None:
        record_auth_event("pin_change_failed", remote, "auth not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )

    if not verify_pin(body.current_pin, stored):
        logger.info("Failed PIN change attempt from %s", remote)
        record_auth_event("pin_change_failed", remote, "wrong current pin")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current PIN.",
        )

    new_hash = hash_pin(body.new_pin)
    # NX-05: 저장 실패에서는 기존 상태(이전 hash + 이전 epoch)가 그대로 유지된다.
    try:
        persisted = bump_epoch_atomic(config.security.pin_hash_file, pin_hash=new_hash)
    except OSError as exc:
        logger.warning("Could not persist new PIN hash: %s", exc)
        record_auth_event("pin_change_failed", remote, "persist failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not persist new PIN.",
        ) from exc

    set_current_pin_hash(new_hash)

    # NX-05: 이전 세대 토큰·ticket 은 위 저장 지점에서 이미 무효가 됐다. 이미 열려
    # 있는 인증 WS 연결은 다음 요청을 기다리지 않고 즉시 닫는다(카드: ≤5초).
    revoked_ws = _revoke_authorized_ws_connections()

    record_auth_event("pin_change_success", remote, "pin updated; sessions revoked")
    logger.info(
        "Access PIN changed by subject=%s from %s (epoch=%s, ws_closed=%s)",
        subject,
        remote,
        persisted.epoch,
        revoked_ws,
    )
    return ChangePinResponse(epoch=persisted.epoch, sessions_revoked=revoked_ws)


def _revoke_authorized_ws_connections() -> int:
    """인증된 WS 연결을 같은 세대 기준으로 즉시 닫는다(실패해도 응답은 유지)."""
    try:
        # NX-10: 폐기 헬퍼는 leaf 모듈이 소유한다. `session_state` 는 이 모듈(`auth_routes`)을
        # 임포트하므로 여기서 session_state 를 임포트하면 순환한다(게이트: reportImportCycles).
        from antigravity_k.security.ws_registry import close_authorized_ws_blocking

        return close_authorized_ws_blocking(code=4401, reason="Session revoked: PIN changed")
    except Exception as exc:  # noqa: BLE001 — 폐기 실패가 PIN 변경 성공을 가리면 안 된다
        logger.warning("Could not close authorized WS connections: %s", exc)
        return 0


@router.post("/token", response_model=TokenResponse)
@_rate_limit("5/minute")
def token_login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """OAuth2-compatible token endpoint (password grant type).

    Swagger UI의 Authorize 버튼에서 사용됩니다.
    `username` 필드에 액세스 PIN을 입력하면 JWT 토큰을 반환합니다.
    `password` 필드는 무시됩니다 (자리 채움용).

    Returns:
        표준 OAuth2 token response: ``{"access_token": "...", "token_type": "bearer", "expires_in": ...}``
    """
    _ = request
    from antigravity_k.engine.operational_metrics import record_auth_event as record_auth_metric
    from antigravity_k.security.auth_audit import record_auth_event
    from antigravity_k.security.credential_gate import get_credential_gate

    remote = request.client.host if request.client else "unknown"
    gate = get_credential_gate()
    gate_key = f"ip:{remote}"
    gate_decision = gate.register(gate_key)
    if not gate_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Too many failed attempts. Retry after {max(1, int(gate_decision.retry_after_sec))}s.",
            headers={"Retry-After": str(max(1, int(gate_decision.retry_after_sec)))},
        )

    stored = get_current_pin_hash()
    if stored is None:
        record_auth_metric("failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )

    if not verify_pin(form_data.username, stored):
        decision = gate.record_failure(gate_key)
        record_auth_event("login_failed", remote)
        record_auth_metric("failed")
        if not decision.allowed:
            record_auth_event("lockout", remote, "failure threshold reached")
            record_auth_metric("lockout")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Too many failed attempts. Retry after {max(1, int(decision.retry_after_sec))}s.",
                headers={"Retry-After": str(max(1, int(decision.retry_after_sec)))},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN.",
        )

    gate.record_success(gate_key)
    record_auth_event("login_success", remote)
    record_auth_metric("success")
    token = get_token_service().issue_token(subject="user")
    return TokenResponse(
        access_token=token,
        expires_in=get_token_service().ttl_seconds,
    )


@router.post("/verify", response_model=VerifyResponse)
def verify_token(request: Request) -> VerifyResponse:
    """Verify a bearer token is still valid.

    Extracts the token from the Authorization header and checks its signature
    and expiration. Returns the validation result and the token subject.
    """
    token = _extract_bearer(request)
    if token is None:
        return VerifyResponse(valid=False, subject=None)

    claims = get_token_service().verify_token(token)
    if claims is None:
        return VerifyResponse(valid=False, subject=None)

    subject = claims.get("sub")
    return VerifyResponse(valid=True, subject=subject if isinstance(subject, str) else None)


@router.post("/logout")
def logout() -> dict[str, str]:
    """Logout endpoint.

    Tokens are stateless (signed JWTs), so the server cannot revoke them
    directly. The client must discard its token. This endpoint exists for API
    symmetry and future blocklist support.
    """
    return {"detail": "Token is stateless; discard it client-side to complete logout."}


class WSTicketResponse(BaseModel):
    """SEC-03 — 단기 1회성 WS ticket 발급 응답."""

    ticket: str
    expires_in: int


@router.post("/ws-ticket", response_model=WSTicketResponse)
def issue_ws_ticket(request: Request) -> WSTicketResponse:
    """인증된 세션에 단기(30초) 1회성 WebSocket ticket을 발급한다.

    SEC-03: browser WS 클라이언트는 장기 bearer를 URL에 실을 수 없다(로그/
    history 노출). 대신 이 endpoint(Bearer 인증 필요)에서 ticket을 받아
    ``?ticket=``로 단 한 번 사용한다. ticket은 재사용 불가이므로 유출되어도
    노출 창이 수 초다. 인증되지 않은 호출은 middleware가 차단한다(401).
    """
    from antigravity_k.security.ws_ticket import get_ws_ticket_service

    subject = getattr(request.state, "auth_subject", None)
    if not isinstance(subject, str) or not subject:
        subject = "bearer"
    service = get_ws_ticket_service(get_token_service())
    return WSTicketResponse(ticket=service.issue(subject), expires_in=int(service.ttl_sec))


@router.get("/status")
def auth_status() -> dict[str, object]:
    """SEC-01 상태 endpoint — UI 표시와 실제 인증이 같은 policy 소스를 쓴다.

    응답은 공유 AuthPolicy의 ``status()`` 그대로다:
      ``{protected, level, reason, dev_no_pin_allow}``
    PIN 변경/삭제/재시작 후 이 endpoint가 즉시 새 상태를 반영한다 (캐시 없음).
    """
    from antigravity_k.api.auth_policy import get_shared_auth_policy

    return get_shared_auth_policy().status()


# ---------------------------------------------------------------------------
# Helpers used by the middleware and the verify route
# ---------------------------------------------------------------------------


def extract_bearer_token(request: Request) -> str | None:
    """Pull the bearer token from the Authorization header.

    공개 이름(NX-05 잔여): 열린 SSE 스트림을 폐기하려면 `api/sse_revocation.py` 가 같은
    추출 규칙을 써야 한다. 규칙을 복제하면 한쪽만 바뀌어 판정이 갈라진다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


# 구 이름 별칭 — 기존 호출자/시험이 그대로 동작한다.
_extract_bearer = extract_bearer_token


def _mark_authenticated(request: Request, subject: str) -> None:
    request.state.auth_subject = subject


def authenticate_request(request: Request) -> bool:
    """Return True if the request carries valid credentials.

    SEC-01 단일 정책: 판정은 공유 :class:`~antigravity_k.api.auth_policy.AuthPolicy`
    의 단일 진리표를 따른다 (HTTP/WS/상태 endpoint가 같은 객체를 사용). 구버전의
    "plaintext PIN 부재 시 loopback 익명 허용" 분기는 저장 hash를 무시하는
    결함이므로 제거되었다.

    SEC-02: **bearer 토큰만 수용한다** — raw PIN(X-Access-Pin 헤더/ag_access_pin
    쿠키)은 이 경로에서 PBKDF2 검증하지 않는다. PIN은 rate-limited
    ``/api/auth/login`` (또는 ``/api/auth/token``)에서만 토큰으로 교환된다.
    임의 보호 URL로 PIN 후보를 보내도 PBKDF2 비용이 발생하지 않는다.

    Checks, in order:
      1. A valid bearer token in the ``Authorization`` header.
      2. Anonymous access only when the shared policy resolves
         ``open_loopback`` (explicit dev allow + loopback + no credential).
      3. Everything else fails closed. Raw PIN headers/cookies are ignored
         here by design (SEC-02 credential surface reduction).
    """
    from antigravity_k.api.auth_policy import get_shared_auth_policy

    policy = get_shared_auth_policy()
    token = _extract_bearer(request)
    if token is not None:
        claims = get_token_service().verify_token(token)
        if claims is not None:
            subject = claims.get("sub")
            _mark_authenticated(request, subject if isinstance(subject, str) and subject else "bearer")
            return True

    # SEC-02: raw PIN 헤더/쿠키는 credential 표면에서 제거됐다 — verify_pin
    # (PBKDF2)은 rate-limited login/token route에서만 실행된다. 익명 허용은
    # 정책이 open_loopback으로 판정할 때만 가능하다 (SEC-01 fail-closed).
    decision = policy.resolve(host=config.server.host)
    if decision.level == "open_loopback":
        _mark_authenticated(request, "loopback")
        return True
    return False
    return False
