"""Authentication primitives: PIN hashing, JWT token issuance/verification.

This module provides the crypto layer for the API auth system. It is
deliberately self-contained (no FastAPI/Starlette imports) so it can be unit
tested in isolation and reused by both HTTP middleware and WebSocket handlers.

Design notes
------------
- PIN hashing uses PBKDF2-HMAC-SHA256 with a per-hash random salt and 600,000
  iterations (OWASP 2023 guidance). The format is compatible with common
  ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`` strings.
- All comparisons are constant-time via :func:`hmac.compare_digest`.
- Tokens are HS256-signed JWTs. The signing secret is generated once and
  persisted to a file so tokens survive a server restart; if the file cannot
  be written an ephemeral in-memory secret is used (tokens then do not survive
  restart, which is the safe default).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import secrets
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jwt

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)

# PBKDF2 parameters (OWASP 2023 recommendation for SHA-256).
_PBKDF2_ITERATIONS = 600_000
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_HASH_DIGEST_SIZE = 32  # SHA-256 output length in bytes

# Default token lifetime, overridable by the caller.
DEFAULT_TOKEN_TTL_HOURS = 12

# JWT configuration.
_JWT_ALGORITHM = "HS256"
_JWT_ISSUER = "antigravity-k"

# NX-05: PIN 변경 시 폐기되는 세션 세대 claim 이름.
EPOCH_CLAIM = "epoch"

# File permissions for the persisted signing secret (owner read/write only).
_SECRET_FILE_MODE = 0o600


class AuthError(Exception):
    """Base class for authentication errors."""


def hash_pin(pin: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Hash a PIN using PBKDF2-HMAC-SHA256 with a random salt.

    Args:
        pin: The plaintext PIN to hash.
        iterations: PBKDF2 iteration count (default 600,000).

    Returns:
        A string of the form ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``.

    """
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, _HASH_DIGEST_SIZE)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"{_PBKDF2_ALGORITHM}${iterations}${salt_b64}${hash_b64}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a plaintext PIN against a stored hash.

    Uses constant-time comparison to mitigate timing attacks. Returns ``False``
    for any malformed stored value rather than raising, so callers can treat
    "no valid hash" and "wrong PIN" identically.

    Args:
        pin: The plaintext PIN to check.
        stored: The stored hash string (as produced by :func:`hash_pin`).

    Returns:
        True if the PIN matches, False otherwise (including malformed stored).

    """
    try:
        algorithm, iters_str, salt_b64, hash_b64 = stored.split("$", 3)
    except ValueError:
        logger.warning("Malformed stored PIN hash; rejecting login.")
        return False

    if algorithm != _PBKDF2_ALGORITHM:
        logger.warning("Unknown PIN hash algorithm '%s'; rejecting login.", algorithm)
        return False

    try:
        iterations = int(iters_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, binascii.Error):
        logger.warning("Corrupt PIN hash components; rejecting login.")
        return False

    derived = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, dklen=len(expected))
    # Constant-time comparison of the raw bytes.
    return hmac.compare_digest(derived, expected)


def generate_token_secret() -> str:
    """Generate a cryptographically random signing secret for JWTs.

    Returns:
        A URL-safe base64 string with ~512 bits of entropy.

    """
    return secrets.token_urlsafe(64)


class TokenService:
    """Issue and verify HS256 JWT access tokens.

    The signing secret is loaded from (or written to) ``secret_path`` so that
    tokens remain valid across server restarts. The class is thread-safe.
    """

    def __init__(
        self,
        secret_path: str | Path | None = None,
        *,
        token_ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS,
        epoch_provider: Callable[[], int] | None = None,
    ):
        """Initialize the token service, loading or creating the signing secret.

        Args:
            secret_path: Optional path to persist the signing secret. If the
                file exists its content is loaded; otherwise a new secret is
                generated and (best-effort) written there.
            token_ttl_hours: Token lifetime in hours.
            epoch_provider: NX-05 세션 세대 공급자. 주어지면 발급 시 ``epoch``
                claim 을 넣고 검증 시 현재 값과 비교한다. **캐시하지 않는다** —
                다른 프로세스가 PIN 을 바꾸면 이 프로세스도 즉시 이전 토큰을
                거부해야 한다. 이 인자가 없으면 암호 계층 단위 시험용으로
                세대 검사 없이 동작한다(제품 배선은 항상 공급자를 넘긴다).

        """
        self._ttl: timedelta = timedelta(hours=token_ttl_hours)
        self._lock: threading.Lock = threading.Lock()
        self._secret: str = self._load_or_create_secret(secret_path)
        self._epoch_provider = epoch_provider

    @staticmethod
    def _load_or_create_secret(secret_path: str | Path | None) -> str:
        """Return a signing secret, persisting a new one if none exists."""
        if secret_path is None:
            return generate_token_secret()

        path = Path(secret_path)
        try:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    try:
                        path.chmod(_SECRET_FILE_MODE)
                    except OSError:
                        logger.warning("Could not restrict token secret permissions on %s", path)
                    return content
        except OSError:
            logger.warning("Could not read token secret from %s; generating new one.", path)

        # Generate a fresh secret and persist it.
        new_secret = generate_token_secret()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write with restricted permissions.
            fd = path.open("w", encoding="utf-8")
            with fd:
                _ = fd.write(new_secret)
            try:
                path.chmod(_SECRET_FILE_MODE)
            except OSError:
                pass  # chmod may fail on some platforms/setups; non-fatal.
            logger.info("Generated and persisted new JWT signing secret at %s", path)
        except OSError:
            logger.warning("Could not persist token secret to %s; using ephemeral secret.", path)
        return new_secret

    @property
    def secret(self) -> str:
        """The signing secret (exposed for testing)."""
        return self._secret

    @property
    def ttl_seconds(self) -> int:
        """Token lifetime in seconds."""
        return int(self._ttl.total_seconds())

    @property
    def epoch_provider(self) -> Callable[[], int] | None:
        """세션 세대 공급자(WS ticket 등 같은 세대를 공유하는 표면이 사용)."""
        return self._epoch_provider

    def current_epoch(self) -> int | None:
        """현재 세대(공급자가 없으면 ``None``). 매 호출 재평가한다."""
        if self._epoch_provider is None:
            return None
        return int(self._epoch_provider())

    def issue_token(self, subject: str, *, extra_claims: dict[str, object] | None = None) -> str:
        """Issue a signed JWT for ``subject``.

        Args:
            subject: The subject claim (e.g. ``"user"`` or a client id).
            extra_claims: Optional additional claims to include.

        Returns:
            The encoded JWT string.

        """
        now = datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "sub": subject,
            "iat": now,
            "exp": now + self._ttl,
            "iss": _JWT_ISSUER,
        }
        epoch = self.current_epoch()
        if epoch is not None:
            payload[EPOCH_CLAIM] = epoch
        if extra_claims:
            payload.update(extra_claims)
        with self._lock:
            return jwt.encode(payload, self._secret, algorithm=_JWT_ALGORITHM)

    def verify_token(self, token: str) -> dict[str, object] | None:
        """Verify a JWT's signature and expiry.

        Args:
            token: The encoded JWT string.

        Returns:
            The decoded claims dict on success, or ``None`` if the token is
            invalid, expired, or tampered with.

        """
        try:
            with self._lock:
                claims = jwt.decode(
                    token,
                    self._secret,
                    algorithms=[_JWT_ALGORITHM],
                    issuer=_JWT_ISSUER,
                    options={"require": ["exp", "iat", "sub"]},
                )
        except jwt.PyJWTError as e:
            logger.debug("Token verification failed: %s", e)
            return None

        # NX-05: 세션 세대 검사. 서명/만료가 유효해도 이전 세대 토큰은 거부한다.
        expected = self.current_epoch()
        if expected is None:
            return claims  # 암호 계층 단위 시험용(세대 미배선)
        token_epoch = claims.get(EPOCH_CLAIM)
        if not isinstance(token_epoch, int) or isinstance(token_epoch, bool):
            # 구버전 토큰(epoch claim 없음) — 재로그인 필요.
            logger.info("Rejected legacy token without %s claim", EPOCH_CLAIM)
            return None
        if token_epoch != expected:
            logger.info("Rejected token from revoked session epoch %s (current %s)", token_epoch, expected)
            return None
        return claims


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract a bearer token from an ``Authorization`` header value.

    Args:
        authorization_header: The raw header value (may be None).

    Returns:
        The token string, or None if the header is absent or malformed.

    """
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def extract_token_from_ws(websocket: "WebSocket") -> str | None:
    """Extract an auth token from a WebSocket connection.

    Browsers cannot set custom headers on WebSocket handshakes, so we accept
    the token from either a ``token`` query parameter or (preferably) the
    ``Sec-WebSocket-Protocol`` subprotocol.

    SEC-01/SEC-02: ``pin`` query parameter 인증은 제거되었다 — PIN은
    rate-limited login route로만 제출한다. WS에서 PIN credential을 수집하지
    않는다 (credential 표면 축소 + 로그/audit 누출 방지).

    SEC-03: 장기 bearer의 ``token`` query parameter도 제거되었다 — URL(로그,
    browser history, proxy 로그)에 credential이 남는 채널이므로, browser
    클라이언트는 단기 1회성 ticket(``?ticket=``)을, 비-browser 클라이언트는
    subprotocol bearer 채널을 쓴다.

    Args:
        websocket: The inbound WebSocket connection.

    Returns:
        The token string, or None if none was provided.

    """
    # Subprotocol header (set by non-browser clients).
    protocols = websocket.headers.get("sec-websocket-protocol")
    if protocols:
        for proto in protocols.split(","):
            candidate = proto.strip()
            if candidate.startswith("bearer."):
                return candidate[len("bearer.") :]
    return None
