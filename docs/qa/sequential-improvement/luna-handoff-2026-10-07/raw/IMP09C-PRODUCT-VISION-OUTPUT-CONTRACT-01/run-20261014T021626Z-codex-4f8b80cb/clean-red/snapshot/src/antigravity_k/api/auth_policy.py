"""SEC-01 — 단일 AuthPolicy (fail-closed).

startup/HTTP/SSE/WS가 같은 정책 로직을 공유한다 (docs/11_COMMERCIAL_GA_100_PLAN.md §SEC-01).

계약:
  - 저장 PIN hash가 존재하면 loopback 개발 모드여도 **보호 상태**다.
    (구버전은 plaintext PIN 부재 시 hash 존재를 무시하고 익명을 허용했다 — SEC-01 결함)
  - 익명 허용(open-loopback)은 (1) 명시적 설정 ``AGK_SEC_DEV_NO_PIN_ALLOW``
    (2) loopback host (3) 저장 credential 전무 — 세 조건이 모두 충족될 때만.
  - 결정은 매 요청 시 credential 소스를 다시 읽어 재평가한다 (캐시 없음).
    PIN 변경/삭제 후 표시와 실제 인증이 즉시 일치한다.
  - 무자격 HTTP/SSE/WS 거부 코드는 401 / 401 / 4401 (plan 규정).

이 모듈은 FastAPI/Starlette에 의존하지 않는다 — 미들웨어와 WS 게이트 양쪽에서
안전하게 import할 수 있다 (engine/auth.py와 동일한 설계 원칙).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Literal

from antigravity_k.api.startup_security import is_loopback_host

AuthLevel = Literal["protected", "open_loopback", "deny"]

# 명시적 dev 허용 env (기본값 False — fail-closed).
DEV_NO_PIN_ALLOW_ENV = "AGK_SEC_DEV_NO_PIN_ALLOW"

# 저장 PIN hash가 유효한 credential로 인정되는 최소 조건.
# engine/auth.py hash_pin 형식: pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>
_MIN_HASH_MARKER = "pbkdf2_sha256$"


def _hash_file_has_valid_hash(path: Path) -> bool:
    """저장 hash 파일이 유효한 credential을 담고 있는지 (형식만 검사).

    NX-05: 저장 형식이 ``agk.auth.v1`` JSON(hash + epoch)으로 넓어졌으므로,
    구버전 한 줄 hash 와 새 형식을 같은 판정으로 처리한다.
    """
    from antigravity_k.security.auth_state import read_pin_hash

    stored = read_pin_hash(path)
    if stored is None:
        return False
    if stored.strip() and not stored.startswith(_MIN_HASH_MARKER):
        return False
    try:
        _algorithm, iterations_text, salt_text, digest_text = stored.split("$", 3)
        # verify_pin이 상세 검증을 수행하므로 여기선 구조 존재만 확인.
        return bool(iterations_text.isdigit() and salt_text and digest_text)
    except ValueError:
        return False


class AuthDecision:
    """정책 평가 결과 — level과 근거를 함께 담는다."""

    __slots__ = ("level", "reason")

    def __init__(self, level: AuthLevel, reason: str) -> None:
        self.level = level
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"AuthDecision(level={self.level!r}, reason={self.reason!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AuthDecision):
            return NotImplemented
        return self.level == other.level and self.reason == other.reason

    def __hash__(self) -> int:
        return hash((self.level, self.reason))


def resolve_auth_decision(
    *,
    stored_pin_hash: str | None,
    plaintext_pin_configured: str,
    host: str,
    dev_no_pin_allow: bool,
) -> AuthDecision:
    """순수 정책 함수 — 진리표의 단일 진실원.

    우선순위 (fail-closed):
      1. 저장 hash 또는 plaintext PIN 구성 → protected (host/dev 설정 무관)
      2. credential 전무 + dev 허용 env + loopback → open_loopback
      3. 그 외 → deny
    """
    if (stored_pin_hash is not None and stored_pin_hash.strip()) or plaintext_pin_configured.strip():
        return AuthDecision("protected", "credential-present")
    if dev_no_pin_allow and is_loopback_host(host):
        return AuthDecision("open_loopback", "explicit-dev-allow+loopback+no-credential")
    return AuthDecision("deny", "no-credential")


class AuthPolicy:
    """호출 가능한 credential 소스를 감싸는 정책 객체.

    소스는 콜백이므로 PIN 변경/삭제가 즉시 반영된다 (캐시 금지).
    """

    def __init__(
        self,
        *,
        stored_pin_hash: Callable[[], str | None],
        plaintext_pin: Callable[[], str],
        host: Callable[[], str] | None = None,
    ) -> None:
        self._stored_pin_hash = stored_pin_hash
        self._plaintext_pin = plaintext_pin
        self._host = host or (lambda: "")
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, *, pin_hash_file: str | Path, config_host: Callable[[], str] | None = None) -> AuthPolicy:
        """config.security 값에 바인딩되는 policy를 만든다 (매 평가 시 파일 재판독)."""

        def read_hash() -> str | None:
            # NX-05: 저장 형식이 agk.auth.v1 JSON(hash + epoch)으로 넓어졌다.
            # 파일 원문을 그대로 돌려주면 (a) JSON blob 이 hash 처럼 보이고
            # (b) pin_hash 가 null 인 상태(credential 제거)도 "protected" 로 오판된다.
            path = Path(pin_hash_file)
            if not _hash_file_has_valid_hash(path):
                return None
            from antigravity_k.security.auth_state import read_pin_hash

            try:
                return read_pin_hash(path)
            except OSError:
                return None

        def read_pin() -> str:
            from antigravity_k.config import config

            return config.security.access_pin

        def read_host() -> str:
            if config_host is not None:
                return config_host()
            from antigravity_k.config import config

            return config.server.host

        return cls(stored_pin_hash=read_hash, plaintext_pin=read_pin, host=read_host)

    @staticmethod
    def dev_no_pin_allow_enabled() -> bool:
        """명시적 dev 익명 허용 여부 — env가 설정된 값만 존중한다."""
        return os.environ.get(DEV_NO_PIN_ALLOW_ENV, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def is_production() -> bool:
        return os.environ.get("AGK_ENV", "development").strip().lower() == "production"

    @property
    def dev_no_pin_allow(self) -> bool:
        """현재 dev 익명 허용 env 상태 (테스트/표시용)."""
        return self.dev_no_pin_allow_enabled()

    def resolve(self, host: str | None = None) -> AuthDecision:
        """현재 credential 상태로 정책을 재평가한다.

        production에서는 익명 허용이 절대 없다 — dev 허용 env가 설정되어도
        무시한다 (fail-closed 이중 안전장치).
        """
        with self._lock:
            decision = resolve_auth_decision(
                stored_pin_hash=self._stored_pin_hash(),
                plaintext_pin_configured=self._plaintext_pin(),
                host=host if host is not None else self._host(),
                dev_no_pin_allow=self.dev_no_pin_allow_enabled(),
            )
        if decision.level == "open_loopback" and self.is_production():
            return AuthDecision("deny", "production-forbids-anonymous")
        return decision

    def evaluate_credential(self, *, token_verified: bool, host: str | None = None) -> AuthDecision:
        """제시된 credential 평가 — open_loopback 결정 시에만 무자격 허용.

        token_verified: JWT 검증 성공 여부 (호출자가 미리 수행).
        SEC-02: PIN credential 파라미터는 제거되었다 — PBKDF2 검증은
        rate-limited login/token route에서만 실행되며, 정책 객체는 임의 요청에서
        실행 가능한 PBKDF2 표면을 갖지 않는다 (credential 표면 축소).
        """
        decision = self.resolve(host)
        if decision.level == "open_loopback":
            return decision
        if token_verified:
            return AuthDecision("protected", "valid-token")
        return AuthDecision("deny", "invalid-or-missing-credential")

    def status(self) -> dict[str, object]:
        """UI/상태 endpoint용 표시 payload — 실제 인증과 같은 소스에서 산출."""
        decision = self.resolve()
        return {
            "protected": decision.level == "protected",
            "level": decision.level,
            "reason": decision.reason,
            "dev_no_pin_allow": self.dev_no_pin_allow,
        }


# ── 공유 싱글톤 ──────────────────────────────────────────────────────
# HTTP 미들웨어, WS 게이트, 상태 endpoint가 모두 이 객체를 사용한다.
# startup 시 init_shared_auth_policy()로 초기화한다.

_shared_auth_policy: AuthPolicy | None = None
_policy_lock = threading.Lock()


def get_shared_auth_policy() -> AuthPolicy:
    """공유 AuthPolicy를 반환한다 (미초기화 시 config 기반으로 lazy 생성)."""
    global _shared_auth_policy
    if _shared_auth_policy is None:
        with _policy_lock:
            if _shared_auth_policy is None:
                from antigravity_k.config import config

                _shared_auth_policy = AuthPolicy.from_config(pin_hash_file=config.security.pin_hash_file)
    return _shared_auth_policy


def init_shared_auth_policy(pin_hash_file: str | Path | None = None) -> AuthPolicy:
    """공유 policy를 (재)초기화한다 — server lifespan/auth bootstrap에서 호출."""
    global _shared_auth_policy
    path = pin_hash_file
    if path is None:
        from antigravity_k.config import config

        path = config.security.pin_hash_file
    with _policy_lock:
        _shared_auth_policy = AuthPolicy.from_config(pin_hash_file=path)
    return _shared_auth_policy


def reset_shared_auth_policy() -> None:
    """테스트 헬퍼 — 공유 policy를 해제한다."""
    global _shared_auth_policy
    with _policy_lock:
        _shared_auth_policy = None
