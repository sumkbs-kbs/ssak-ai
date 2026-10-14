"""credential_gate — SEC-02 로그인 실패 제한 (burst/sustained/lockout).

GA-100 plan §SEC-02: "IP와 계정/session 기준 burst 및 sustained limit이 적용된다"
"부하 시험에서 공격 요청이 정상 인증 latency와 CPU를 허용 threshold 이상 악화시키지
않는다".

설계:
- key 문자열 기준(예: ``ip:1.2.3.4``, ``user:<subject>``)으로 실패 횟수를 추적한다.
- burst limit: 짧은 창(burst_window_sec) 내 실패 임계 초과 → lockout.
- sustained limit: 긴 창(sustained_window_sec) 내 누적 실패 임계 초과 → lockout.
- lockout 중 ``check`` 는 False를 반환하고 **호출자는 PBKDF2를 실행하지 않는다** —
  무차별 대입이 CPU 비용(PBKDF2 반복)을 소진하지 못하게 하는 핵심.
- record_success가 해당 key의 실패 이력을 초기화한다.

stdlib 전용 — 어디서든 import 가능.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Final

__all__ = [
    "CredentialGate",
    "GateDecision",
    "get_credential_gate",
    "reset_credential_gate",
]


@dataclass(frozen=True, slots=True)
class GateDecision:
    """credential gate 판정 결과."""

    allowed: bool
    reason: str = ""  # "" | "lockout"
    retry_after_sec: float = 0.0  # lockout 남은 시간 (allowed=False일 때만 의미)


@dataclass(slots=True)
class _FailureRecord:
    timestamps: deque[float]
    locked_until: float = 0.0


class CredentialGate:
    """key별 로그인 실패 제한기.

    Args:
        burst_limit: burst_window_sec 동안 허용되는 최대 실패 수.
        burst_window_sec: burst 창 길이 (초).
        sustained_limit: sustained_window_sec 동안 허용되는 누적 실패 수.
            None이면 sustained 검사를 생략한다.
        sustained_window_sec: sustained 창 길이 (초).
        lockout_sec: 임계 초과 시 차단 지속 시간 (초).
        max_keys: 메모리 상한 — 이 개수를 넘는 서로 다른 key가 들어오면
            가장 오래된 key 기록을 버린다 (메모리 DoS 방지).
    """

    def __init__(
        self,
        *,
        burst_limit: int = 5,
        burst_window_sec: float = 60.0,
        sustained_limit: int | None = 20,
        sustained_window_sec: float = 600.0,
        lockout_sec: float = 300.0,
        max_keys: int = 10_000,
    ) -> None:
        self._burst_limit = burst_limit
        self._burst_window = burst_window_sec
        self._sustained_limit = sustained_limit
        self._sustained_window = sustained_window_sec
        self._lockout_sec = lockout_sec
        self._max_keys = max_keys
        self._records: dict[str, _FailureRecord] = {}
        self._lock = threading.Lock()

    # ─── 공개 API ────────────────────────────────────────────────

    def check(self, key: str) -> GateDecision:
        """요청 허용 여부 판정 (상태 변경 없음 — lockout 만료 정리는 제외)."""
        now = time.monotonic()
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return GateDecision(allowed=True)
            if record.locked_until > now:
                return GateDecision(
                    allowed=False,
                    reason="lockout",
                    retry_after_sec=round(record.locked_until - now, 3),
                )
            return GateDecision(allowed=True)

    def register(self, key: str) -> GateDecision:
        """요청 진입 시 게이트 판정 — lockout이면 즉시 거절 (PBKDF2 실행 전 호출)."""
        decision = self.check(key)
        if not decision.allowed:
            record_event = _audit_record
            record_event("lockout", key, f"blocked request during lockout ({decision.retry_after_sec}s left)")
        return decision

    def record_failure(self, key: str) -> GateDecision:
        """실패 기록 → 임계 초과 시 lockout 시작. 다음 판정 결과를 반환한다."""
        now = time.monotonic()
        with self._lock:
            record = self._records.get(key)
            if record is None:
                self._evict_if_needed(now)
                record = _FailureRecord(timestamps=deque())
                self._records[key] = record

            record.timestamps.append(now)
            self._trim(record, now)

            burst_failed = len(record.timestamps) >= self._burst_limit
            sustained_failed = (
                self._sustained_limit is not None
                and len([t for t in record.timestamps if t > now - self._sustained_window]) >= self._sustained_limit
            )
            if (burst_failed or sustained_failed) and record.locked_until <= now:
                record.locked_until = now + self._lockout_sec

            if record.locked_until > now:
                return GateDecision(
                    allowed=False,
                    reason="lockout",
                    retry_after_sec=round(record.locked_until - now, 3),
                )
            return GateDecision(allowed=True)

    def record_success(self, key: str) -> None:
        """성공 — 해당 key의 실패 이력/lockout을 초기화한다."""
        with self._lock:
            self._records.pop(key, None)

    # ─── 내부 ────────────────────────────────────────────────────

    def _trim(self, record: _FailureRecord, now: float) -> None:
        """창 밖의 오래된 타임스탬프 제거."""
        horizon = max(self._burst_window, self._sustained_window or 0.0)
        cutoff = now - horizon
        while record.timestamps and record.timestamps[0] < cutoff:
            _ = record.timestamps.popleft()

    def _evict_if_needed(self, now: float) -> None:
        """key 수 상한 관리 — 만료된/가장 오래된 기록부터 제거."""
        if len(self._records) < self._max_keys:
            return
        expired = [k for k, r in self._records.items() if r.locked_until <= now and not r.timestamps]
        for k in expired:
            del self._records[k]
        while len(self._records) >= self._max_keys:
            oldest = min(self._records, key=lambda k: min(self._records[k].timestamps, default=now))
            del self._records[oldest]


# ─── 프로세스 공유 싱글턴 ────────────────────────────────────────────

_gate: CredentialGate | None = None
_gate_lock = threading.Lock()

_DEFAULT_BURST: Final[int] = 5
_DEFAULT_LOCKOUT: Final[float] = 300.0


def get_credential_gate() -> CredentialGate:
    """앱 전역 credential gate (login route에서 사용)."""
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = CredentialGate(burst_limit=_DEFAULT_BURST, lockout_sec=_DEFAULT_LOCKOUT)
        return _gate


def reset_credential_gate() -> None:
    """테스트용 — 싱글턴 초기화."""
    global _gate
    with _gate_lock:
        _gate = None


def _audit_record(event: str, remote: str, detail: str) -> None:
    """지연 import로 순환 의존을 피한다."""
    from antigravity_k.security.auth_audit import record_auth_event

    record_auth_event(event, remote, detail)
