"""auth_audit — SEC-02 인증 이벤트 감사 로그 (secret-free).

성공/실패/lockout 이벤트를 메모리 링 버퍼에 기록한다. 절대 규칙:
**credential(pin/password/token)은 어떤 필드에도 남기지 않는다.**
이벤트 구조는 {event, remote, ts, detail?} — detail에도 credential 키를 금지한다.

보조 모듈이므로 stdlib만 사용한다 (fastapi/pydantic 없음).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Final, TypedDict

__all__ = [
    "AuthAuditEvent",
    "get_auth_audit_events",
    "record_auth_event",
    "reset_auth_audit",
]

_MAX_EVENTS: Final[int] = 500

_CREDENTIAL_KEYS: Final[frozenset[str]] = frozenset(
    {"pin", "password", "credential", "token", "secret", "attempt", "plaintext"}
)


class AuthAuditEvent(TypedDict):
    """감사 이벤트 1건 — credential 필드를 절대 포함하지 않는다."""

    event: str  # login_success | login_failed | lockout
    remote: str  # 클라이언트 식별 (IP 등) — secret 아님
    ts: float  # unix epoch seconds
    detail: str  # 사람용 설명 (secret 금지)


_events: deque[AuthAuditEvent] = deque(maxlen=_MAX_EVENTS)
_lock = threading.Lock()


def _scrub_detail(detail: str) -> str:
    """detail에서 credential 키=값 패턴을 제거한다 (방어적 스크럽)."""
    lowered = detail.lower()
    for key in _CREDENTIAL_KEYS:
        if f"{key}=" in lowered or f"{key}:" in lowered:
            lowered = lowered.split(f"{key}=")[0].split(f"{key}:")[0]
    return lowered.strip()


def record_auth_event(event: str, remote: str, detail: str = "") -> AuthAuditEvent:
    """인증 이벤트를 기록한다. credential 필드는 구조적으로 금지된다."""
    record = AuthAuditEvent(
        event=event,
        remote=remote or "unknown",
        ts=time.time(),
        detail=_scrub_detail(detail),
    )
    with _lock:
        _events.append(record)
    return record


def get_auth_audit_events() -> list[dict[str, object]]:
    """기록된 감사 이벤트 스냅샷 (오래된 것부터)."""
    with _lock:
        return [dict(e) for e in _events]


def reset_auth_audit() -> None:
    """테스트용 — 버퍼 비우기."""
    with _lock:
        _events.clear()
