"""Fail-closed startup checks for remotely reachable API binds."""

from __future__ import annotations

import base64
import binascii
import ipaddress
from pathlib import Path
from typing import Final

_HASH_ALGORITHM: Final = "pbkdf2_sha256"
_MIN_HASH_ITERATIONS: Final = 100_000
_MIN_PIN_LENGTH: Final = 8


class StartupSecurityError(RuntimeError):
    """Raised when a reachable server would start without a usable credential."""

    def __init__(self, *, host: str, environment: str) -> None:
        self.host: str = host
        self.environment: str = environment
        super().__init__(
            " ".join(
                (
                    "Refusing to start a production or non-loopback server without a strong access PIN",
                    "(at least 8 characters) or an existing valid PIN hash. Set AGK_SEC_ACCESS_PIN.",
                ),
            ),
        )


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _has_valid_pin_hash(path: Path) -> bool:
    # NX-05: 저장 형식이 agk.auth.v1 JSON(hash + epoch)으로 넓어졌다. hash 추출은
    # security.auth_state 가 담당하고(구버전 한 줄도 읽는다), 여기서는 강도만 본다.
    from antigravity_k.security.auth_state import read_pin_hash

    stored = read_pin_hash(path) or ""
    try:
        algorithm, iterations_text, salt_text, digest_text = stored.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        digest = base64.b64decode(digest_text, validate=True)
    except (OSError, ValueError, binascii.Error):
        return False
    return algorithm == _HASH_ALGORITHM and iterations >= _MIN_HASH_ITERATIONS and len(salt) >= 16 and len(digest) >= 32


def validate_startup_security(
    *,
    host: str,
    environment: str,
    access_pin: str,
    pin_hash_file: Path,
) -> None:
    """Reject remotely reachable or production startup without strong authentication."""
    requires_strong_auth = environment.strip().lower() == "production" or not is_loopback_host(host)
    if not requires_strong_auth:
        return
    if len(access_pin.strip()) >= _MIN_PIN_LENGTH or _has_valid_pin_hash(pin_hash_file):
        return
    raise StartupSecurityError(host=host, environment=environment)
