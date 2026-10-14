"""브라우저 세션 소유권 단일 지점 (task 16).

왜 하나여야 하는가: 브라우저 진입점이 넷(`api/routes/agent_tools.py`, `tools/browser_tools.py`,
`tools/browser_tool.py`, `agents/browser_surfing_agent.py`)인데 각자 브라우저를 직접 띄우고 있었다.
그래서 **누가 열었는지·몇 개가 떠 있는지·언제 닫히는지**를 아무도 몰랐고, 전역 `_page` 하나는
태스크가 끝나도 살아 있었으며, `headless=False` 로 사용자 화면에 창을 띄우는 경로도 있었다.

이 모듈이 지키는 문장은 넷이다.

1. **누가 여는지 모르면 열지 않는다.** 모든 세션은 `BrowserOwner`(subject · scope · task)에 묶이고,
   `begin()` 이 그 owner 의 세션인지 확인한다. 같은 owner 는 같은 세션을 **재사용**한다.
2. **호스트는 기본 2개만 연다.** 상한을 넘는 요청은 `BrowserSessionLimitError`(HTTP 429)로 끝나고,
   놀고 있는 세션(기본 15분)과 작업 시간을 넘긴 세션(기본 10분)은 **회수**된다 — 전에는 상한만 있고
   시간 축이 없어서, 죽은 태스크의 브라우저가 무한히 남았다. 이 상한은 **프로세스 경계를 넘는다**:
   자리 수는 프로세스 메모리가 아니라 공유 원장(`browser_session_ledger.py`)에서 세므로, 앱이 2개를
   열어 두면 CLI 의 세 번째 시도가 거절된다(반대도 같다). 죽은 프로세스의 자리는 **다른 프로세스가**
   즉시 걷어낸다.
3. **기본은 격리된 일회용 컨텍스트다.** persistent profile 은 **명시 연결 + 명시 owner scope** 일 때만
   허용한다(`begin(..., persistent_profile=...)`). 익명/기본 scope 로 개인 프로필을 열 수 없다.
4. **남의 페이지를 채택하지 않는다.** 개인 Chrome 이나 Node CDP 가 열어 둔 페이지는 **관찰만** 하고
   항상 새 페이지를 연다(`remember_foreign_pages`). 남의 탭을 조종하기 시작하면 그건 사용자의
   브라우저를 우리 세션으로 삼키는 일이다.

이 모듈은 **정책·소유권**만 갖고 브라우저를 직접 띄우지 않는다. 띄우는 일은 각 진입점의 런타임
(sync `playwright.sync_api` / async `playwright.async_api`)이 하되, 그 사이에 `begin()` → `commit()`
두 단계를 반드시 지나간다. 두 단계로 나눈 이유는 **예약이 상한을 미리 차지**해야 하기 때문이다 —
launch 는 await/IO 라서, 예약 없이 세면 동시 첫 호출 10개가 전부 통과해 10개의 브라우저가 뜬다
(task 12 의 검색 런타임에서 같은 함정을 겪었다).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar, cast, final

from antigravity_k.tools.browser_session_ledger import STATE_ENV, HostSessionLedger, LedgerDecision

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: 호스트가 동시에 열어 두는 기본 세션 수. "2개면 충분하다"가 아니라, 넘으면 **줄 세우지 않고 거절**한다.
DEFAULT_MAX_ACTIVE_SESSIONS = 2

#: 놀고 있는 세션을 회수하는 시간(초). 기본 15분.
DEFAULT_IDLE_TTL_SECONDS = 15 * 60

#: 한 작업이 브라우저를 붙잡을 수 있는 시간(초). 기본 10분.
DEFAULT_TASK_DEADLINE_SECONDS = 10 * 60

MAX_SESSIONS_ENV = "AGK_BROWSER_MAX_SESSIONS"
IDLE_TTL_ENV = "AGK_BROWSER_IDLE_TTL_SECONDS"
TASK_DEADLINE_ENV = "AGK_BROWSER_TASK_DEADLINE_SECONDS"

#: 인증 정보가 없는 요청/도구 호출의 주체. 이 주체는 persistent profile 을 **열 수 없다**.
ANONYMOUS_SUBJECT = "anonymous"

#: 명시 scope 가 없는 경우(구형 클라이언트 호환). 이 scope 는 persistent profile 을 **열 수 없다**.
DEFAULT_SCOPE = "default"

#: 개인 프로필(사용자 Chrome 쿠키·프로필)을 실제로 쓰겠다는 명시적 동의. 없으면 개인 프로필을 읽지 않는다.
PERSONAL_PROFILE_ENV = "AGK_BROWSER_ALLOW_PERSONAL_PROFILE"

#: `status()` 에 실을 페이지 주소. URL 전체를 그대로 돌려주면 쿼리에 토큰이 섞여 나갈 수 있다.
_MAX_URL_CHARS = 120


class BrowserSessionLimitError(RuntimeError):
    """상한을 넘었다 — 기다리게 하지 않고 거절한다(줄 세우면 결국 같은 수의 브라우저가 뜬다)."""


class BrowserSessionRefusedError(RuntimeError):
    """정책상 열 수 없다(persistent profile 을 익명/기본 scope 로 요청하는 등)."""


@final
@dataclass(frozen=True)
class BrowserOwner:
    """세션 하나를 소유하는 주체. `key` 가 세션 동일성의 기준이다."""

    subject: str = ANONYMOUS_SUBJECT
    scope: str = DEFAULT_SCOPE
    task_id: str = ""

    def __post_init__(self) -> None:
        for name in ("subject", "scope", "task_id"):
            value = getattr(self, name)
            if not isinstance(value, str):  # pragma: no cover - 타입으로 막히지만 런타임 방어
                object.__setattr__(self, name, "")
        object.__setattr__(self, "subject", self.subject.strip() or ANONYMOUS_SUBJECT)
        object.__setattr__(self, "scope", self.scope.strip() or DEFAULT_SCOPE)
        object.__setattr__(self, "task_id", self.task_id.strip())

    @classmethod
    def anonymous(cls) -> "BrowserOwner":
        return cls()

    @property
    def is_explicit(self) -> bool:
        """인증 주체와 명시 scope 를 **둘 다** 가진 owner 인가(persistent profile 의 전제)."""
        return self.subject != ANONYMOUS_SUBJECT and self.scope != DEFAULT_SCOPE

    @property
    def key(self) -> str:
        material = f"{self.subject}|{self.scope}|{self.task_id}".encode()
        return hashlib.sha256(material).hexdigest()

    def describe(self) -> dict[str, str]:
        """로그·status 용. `key` 는 앞 12자만 노출한다(전체 해시는 동일성 판정에만 쓴다)."""
        return {"subject": self.subject, "scope": self.scope, "task_id": self.task_id, "key": self.key[:12]}


def _describe_page(page: object) -> str:
    url = getattr(page, "url", "")
    text = url if isinstance(url, str) else ""
    if len(text) > _MAX_URL_CHARS:
        text = text[:_MAX_URL_CHARS] + "…"
    return text or "(unknown)"


@dataclass
class BrowserLease:
    """살아 있는 세션 하나. 진입점은 `page` 만 쓰고, 닫는 일은 `close` 에 맡긴다."""

    owner: BrowserOwner
    page: object
    close: Callable[[], object] | None = None
    persistent_profile: str | None = None
    purpose: str = ""
    opened_at: float = 0.0
    last_used_at: float = 0.0
    foreign_pages: tuple[str, ...] = ()
    #: 공유 원장의 자리 표식 — 호스트 전역 상한의 근거. 퇴화 모드에서는 빈 문자열이다.
    slot: str = ""

    def touch(self, now: float) -> None:
        self.last_used_at = now

    def age(self, now: float) -> float:
        return max(0.0, now - self.opened_at)

    def idle(self, now: float) -> float:
        return max(0.0, now - self.last_used_at)

    def to_dict(self, now: float) -> dict[str, object]:
        return {
            "slot": self.slot,
            "owner": self.owner.describe(),
            "purpose": self.purpose,
            "persistent": bool(self.persistent_profile),
            "profile": Path(self.persistent_profile).name if self.persistent_profile else None,
            "url": _describe_page(self.page),
            "age_seconds": round(self.age(now), 1),
            "idle_seconds": round(self.idle(now), 1),
            "foreign_pages": list(self.foreign_pages),
        }


@final
@dataclass(frozen=True)
class SessionReservation:
    """`begin()` 이 차지한 자리. `commit()` 하거나 `abort()` 해야 한다."""

    token: str
    owner: BrowserOwner
    persistent_profile: str | None
    purpose: str
    reuse: BrowserLease | None = None
    reserved_at: float = 0.0
    #: 공유 원장의 자리 표식(호스트 전역 상한의 근거). 퇴화 모드에서는 빈 문자열이다.
    slot: str = ""

    @property
    def is_reuse(self) -> bool:
        return self.reuse is not None


class _Closable(Protocol):
    def close(self) -> object: ...


@final
class BrowserSessionOwner:
    """호스트 단위 단일 브라우저 세션 소유자(정책 + 원장)."""

    def __init__(
        self,
        *,
        max_active_sessions: int = DEFAULT_MAX_ACTIVE_SESSIONS,
        idle_ttl_seconds: float = DEFAULT_IDLE_TTL_SECONDS,
        task_deadline_seconds: float = DEFAULT_TASK_DEADLINE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        ledger: HostSessionLedger | None = None,
    ) -> None:
        if max_active_sessions < 1:
            raise ValueError("max_active_sessions must be positive")
        if idle_ttl_seconds <= 0 or task_deadline_seconds <= 0:
            raise ValueError("ttl/deadline must be positive")
        self.max_active_sessions: int = max_active_sessions
        self.idle_ttl_seconds: float = float(idle_ttl_seconds)
        self.task_deadline_seconds: float = float(task_deadline_seconds)
        self._clock = clock
        # 자리 수는 **공유 원장**에서 센다 — 앱과 CLI 가 같은 호스트에서 서로를 세지 못하던 결함의
        # 수리 지점이다(task 16 후속). 벽시계는 원장에 실리는 시각용이고, 프로세스 안 TTL 판정은
        # 단조 시계(`clock`)를 그대로 쓴다(두 시계를 섞으면 한쪽이 다른 쪽의 기준을 오해한다).
        self._ledger = ledger if ledger is not None else HostSessionLedger(wall_clock=wall_clock)
        self._leases: dict[str, BrowserLease] = {}
        self._reservations: dict[str, SessionReservation] = {}
        self._reaped: list[dict[str, object]] = []
        self._host_reclaimed: list[dict[str, object]] = []

    # ── 정책 읽기 ────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "BrowserSessionOwner":
        """환경변수로 정책을 바꾼다(잘못된 값은 **기본값으로 되돌리고 경고**한다 — 기동을 막지 않는다)."""
        source = os.environ if env is None else env

        def _int(name: str, default: int, *, minimum: int = 1) -> int:
            raw = str(source.get(name, "") or "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                logger.warning("%s=%r is not an integer; using %s", name, raw, default)
                return default
            if value < minimum:
                logger.warning("%s=%r is below %s; using %s", name, raw, minimum, default)
                return default
            return value

        return cls(
            max_active_sessions=_int(MAX_SESSIONS_ENV, DEFAULT_MAX_ACTIVE_SESSIONS),
            idle_ttl_seconds=_int(IDLE_TTL_ENV, DEFAULT_IDLE_TTL_SECONDS),
            task_deadline_seconds=_int(TASK_DEADLINE_ENV, DEFAULT_TASK_DEADLINE_SECONDS),
        )

    @property
    def active_count(self) -> int:
        """**이 프로세스**가 붙잡은 세션 + 예약.

        상한 판정은 이 값이 아니라 공유 원장(`host_active_count`)을 기준으로 한다 — 프로세스 안
        수만 세면 앱과 CLI 가 서로를 세지 못한다. 이 값은 진단·호환용으로 남긴다.
        """
        return len(self._leases) + len(self._reservations)

    @property
    def host_active_count(self) -> int:
        """호스트 전체가 점유한 자리 수(다른 프로세스·다른 호스트까지 포함)."""
        return self._ledger.host_active()

    @property
    def ledger(self) -> HostSessionLedger:
        """공유 원장(진단·시험용)."""
        return self._ledger

    def lease_for(self, owner: BrowserOwner) -> BrowserLease | None:
        return self._leases.get(owner.key)

    def status(self) -> dict[str, object]:
        now = self._clock()
        return {
            "max_active_sessions": self.max_active_sessions,
            "idle_ttl_seconds": self.idle_ttl_seconds,
            "task_deadline_seconds": self.task_deadline_seconds,
            "active": self.active_count,
            "reservations": len(self._reservations),
            "sessions": [lease.to_dict(now) for lease in self._leases.values()],
            "reaped": list(self._reaped[-20:]),
            "host": {
                # 호스트 전역 상한의 실제 판정 근거. 원장을 못 쓰면 `degraded` 가 그 사실을 말한다.
                "max_active_sessions": self.max_active_sessions,
                "active": self._ledger.host_active(),
                "ledger": self._ledger.status(),
                "reclaimed": list(self._host_reclaimed[-20:]),
            },
        }

    # ── 회수 ────────────────────────────────────────────────────────────────

    def reap(self) -> list[dict[str, object]]:
        """놀고 있거나(유휴 TTL) 작업 시간을 넘긴(deadline) 세션을 닫고, 무엇을 닫았는지 돌려준다.

        `begin()` 이 항상 먼저 부르므로 별도 타이머 스레드가 필요 없다 — 회수는 세션을 열려는 순간에
        일어난다. 시간이 지났다고 브라우저를 닫으려면 어차피 다른 일이 그 사실을 알아야 한다.
        """
        now = self._clock()
        reaped: list[dict[str, object]] = []
        for key, lease in list(self._leases.items()):
            idle, age = lease.idle(now), lease.age(now)
            if idle < self.idle_ttl_seconds and age < self.task_deadline_seconds:
                continue
            reason = "idle_ttl" if idle >= self.idle_ttl_seconds else "task_deadline"
            descriptor = lease.to_dict(now)
            descriptor["reason"] = reason
            self._leases.pop(key, None)
            # 자리도 함께 반납한다 — 원장의 TTL 판정은 **벽시계**라, 프로세스 안에서 회수한
            # 세션의 자리를 남겨 두면 만료된 세션이 호스트 상한을 계속 차지한다(그러면 살아 있는
            # 사용자가 영원히 429 를 받는다).
            if lease.slot:
                _ = self._ledger.release(slot=lease.slot)
            _close_quietly(lease)
            reaped.append(descriptor)
            logger.info("[Browser] reaped session (%s): %s", reason, lease.owner.describe())
        for token, reservation in list(self._reservations.items()):
            # 예약은 페이지가 아직 없으므로 TTL 로만 정리한다(launch 가 매달린 채 죽은 경우).
            if now - reservation.reserved_at >= self.task_deadline_seconds:
                self._reservations.pop(token, None)
                if reservation.slot:
                    _ = self._ledger.release(slot=reservation.slot)
                reaped.append({"owner": reservation.owner.describe(), "reason": "abandoned_reservation"})
        if reaped:
            self._reaped.extend(reaped)
            del self._reaped[:-40]
        return reaped

    # ── 공유 원장과의 정합(프로세스 경계 너머) ───────────────────────────────

    def _drop_reclaimed_lease(self, key: str, lease: BrowserLease) -> dict[str, object]:
        """다른 프로세스가 걷어간 자리의 세션을 닫는다(협조적 회수 — 닫는 일은 소유자가 한다)."""
        self._leases.pop(key, None)
        descriptor = lease.to_dict(self._clock())
        descriptor["reason"] = "host_reclaimed"
        _close_quietly(lease)
        self._reaped.append(descriptor)
        del self._reaped[:-40]
        logger.info(
            "[Browser] closed a session that another process reclaimed: %s (slot=%s)",
            lease.owner.describe(),
            lease.slot,
        )
        return descriptor

    # ── 열기 ────────────────────────────────────────────────────────────────

    def _authorize_persistent(self, owner: BrowserOwner, persistent_profile: str) -> str:
        raw = persistent_profile.strip()
        if not raw:
            raise BrowserSessionRefusedError("persistent profile path is empty")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise BrowserSessionRefusedError("persistent profile must be an absolute path")
        if not owner.is_explicit:
            raise BrowserSessionRefusedError(
                "persistent browser profile requires an authenticated subject and an explicit session scope",
            )
        resolved = str(path.resolve())
        if not path.is_dir():
            raise BrowserSessionRefusedError(f"persistent profile directory does not exist: {path.name}")
        return resolved

    def begin(
        self,
        owner: BrowserOwner | None = None,
        *,
        persistent_profile: str | None = None,
        purpose: str = "",
    ) -> SessionReservation:
        """자리를 확인하고 예약한다(브라우저를 띄우지 않는다 — 그건 진입점의 런타임 몫).

        같은 owner 는 **재사용**한다: `reservation.is_reuse` 면 `reservation.reuse.page` 를 그대로 쓰고
        이미 있는 세션을 두 번 세지 않는다.
        """
        self.reap()
        resolved_owner = owner or BrowserOwner.anonymous()
        # 다른 프로세스가 우리 자리를 걷어갔는지는 **원장의 판정**이 알려 준다(재사용 대신 새 자리를
        # 내준다). 여기서 따로 판단하지 않는다 — 두 곳이 판단하면 둘이 어긋나는 순간이 생긴다.
        existing = self._leases.get(resolved_owner.key)
        in_flight = next(
            (item for item in self._reservations.values() if item.owner.key == resolved_owner.key),
            None,
        )
        if in_flight is not None:
            # 같은 owner 의 동시 첫 호출: 두 번째 launch 를 만들지 않는다(single-flight).
            return in_flight

        authorized = None
        if persistent_profile is not None:
            authorized = self._authorize_persistent(resolved_owner, persistent_profile)

        # 자리 판정은 **공유 원장**이 한다: 이 프로세스의 수가 아니라 호스트 전체의 수를 세고,
        # 죽은 프로세스·유지 TTL·작업 deadline 을 지난 자리를 그 자리에서 걷어낸다. **재사용
        # 여부도 이 판정 하나에서 나온다** — 두 곳(프로세스 안·원장)이 따로 판단하면 "원장에는
        # 없는 자리를 재사용하는" 구간이 생긴다.
        decision = self._admit(resolved_owner, purpose=purpose, persistent=authorized is not None)
        if decision.kind == "degraded":
            # 원장을 못 쓴다(상태 디렉터리 불가·잠금 실패) — 기동을 막지 않고 프로세스 안
            # 규칙으로 퇴화한다. 그 사실은 `status()["host"]["ledger"]["degraded"]` 로 드러난다.
            if existing is not None:
                existing.touch(self._clock())
                return self._reuse(resolved_owner, existing, purpose)
            if self.active_count >= self.max_active_sessions:
                raise BrowserSessionLimitError(
                    f"Too many active browser sessions ({self.active_count}/{self.max_active_sessions})",
                )
        elif decision.kind == "reuse" and existing is not None:
            existing.touch(self._clock())
            return self._reuse(resolved_owner, existing, purpose)
        elif decision.kind == "reuse":
            # 원장에는 우리 자리가 살아 있는데 이 프로세스에 임대가 없다(원장만 살아남은 경우).
            # 그 자리를 반납하고 다시 요청한다 — 안 그러면 같은 자리를 두 번 세게 된다.
            _ = self._ledger.release(slot=decision.slot or "")
            decision = self._admit(resolved_owner, purpose=purpose, persistent=authorized is not None)

        if decision.kind != "degraded" and not decision.granted:
            raise BrowserSessionLimitError(
                f"Too many active browser sessions on this host ({decision.host_active}/{decision.max_active})",
            )
        if decision.reclaimed:
            self._host_reclaimed.extend(decision.reclaimed)
            del self._host_reclaimed[:-40]
        if existing is not None:
            # 남아 있던 임대가 있는데 원장이 새 자리를 내줬다면, 그 자리는 다른 프로세스가
            # 걷어간 것이다 — 그 세션을 그대로 쓰면 상한이 세지 않는 브라우저가 생긴다.
            _ = self._drop_reclaimed_lease(resolved_owner.key, existing)

        reservation = SessionReservation(
            token=uuid.uuid4().hex[:12],
            owner=resolved_owner,
            persistent_profile=authorized,
            purpose=purpose,
            reserved_at=self._clock(),
            slot=decision.slot or "",
        )
        self._reservations[reservation.token] = reservation
        return reservation

    def _admit(self, owner: BrowserOwner, *, purpose: str, persistent: bool) -> LedgerDecision:
        """원장에 자리를 요청한다(정책 값은 이 소유자 것을 그대로 넘긴다)."""
        return self._ledger.admit(
            owner_key=owner.key,
            max_active=self.max_active_sessions,
            idle_ttl=self.idle_ttl_seconds,
            task_deadline=self.task_deadline_seconds,
            purpose=purpose,
            persistent=persistent,
        )

    def _reuse(self, owner: BrowserOwner, lease: BrowserLease, purpose: str) -> SessionReservation:
        """이미 있는 세션을 그대로 쓰는 예약(자리를 새로 세지 않는다)."""
        return SessionReservation(
            token="",
            owner=owner,
            persistent_profile=lease.persistent_profile,
            purpose=purpose or lease.purpose,
            reuse=lease,
            reserved_at=self._clock(),
            slot=lease.slot,
        )

    def commit(
        self,
        reservation: SessionReservation,
        *,
        page: object,
        close: Callable[[], object] | None = None,
        foreign_pages: Sequence[object] = (),
    ) -> BrowserLease:
        """예약을 실제 세션으로 바꾼다. 재사용 예약이면 페이지를 새로 등록하지 않는다."""
        now = self._clock()
        foreign = self.remember_foreign_pages(foreign_pages)
        if reservation.is_reuse:
            lease = reservation.reuse
            assert lease is not None
            lease.touch(now)
            if foreign:
                lease.foreign_pages = tuple(dict.fromkeys((*lease.foreign_pages, *foreign)))
            return lease
        # 원장에서 예약을 **세션으로 확정**한다. 그 사이 다른 프로세스가 걷어갔다면 원장이 다시
        # 자리를 요청하고, 그마저 안 되면(다른 프로세스가 먼저 가져감) 확정하지 않는다 —
        # 브라우저는 이미 떠 있으므로 호출자의 실패 경로(`abort()`)가 정리한다.
        decision = self._ledger.commit(
            reservation.slot,
            owner_key=reservation.owner.key,
            max_active=self.max_active_sessions,
            idle_ttl=self.idle_ttl_seconds,
            task_deadline=self.task_deadline_seconds,
            purpose=reservation.purpose,
            persistent=reservation.persistent_profile is not None,
        )
        if not decision.granted:
            raise BrowserSessionLimitError(
                f"Too many active browser sessions on this host ({decision.host_active}/{decision.max_active})",
            )
        if decision.reclaimed:
            self._host_reclaimed.extend(decision.reclaimed)
            del self._host_reclaimed[:-40]
        self._reservations.pop(reservation.token, None)
        lease = BrowserLease(
            owner=reservation.owner,
            page=page,
            close=close,
            persistent_profile=reservation.persistent_profile,
            purpose=reservation.purpose,
            opened_at=now,
            last_used_at=now,
            foreign_pages=foreign,
            slot=decision.slot or reservation.slot,
        )
        self._leases[reservation.owner.key] = lease
        logger.info(
            "[Browser] session opened: owner=%s persistent=%s foreign_pages=%d",
            reservation.owner.describe(),
            bool(reservation.persistent_profile),
            len(foreign),
        )
        return lease

    def abort(self, reservation: SessionReservation) -> None:
        """launch 가 실패했을 때 예약을 돌려준다(자리를 붙잡은 채 남기지 않는다)."""
        if reservation.token:
            self._reservations.pop(reservation.token, None)
        if reservation.slot:
            _ = self._ledger.release(slot=reservation.slot)

    def release(self, owner: BrowserOwner) -> bool:
        """owner 의 세션을 닫고 원장에서 지운다. 닫을 것이 없으면 False."""
        lease = self._leases.pop(owner.key, None)
        if lease is None:
            return False
        if lease.slot:
            _ = self._ledger.release(slot=lease.slot)
        else:
            # 퇴화 모드에서 열린 세션 — 원장이 나중에 살아났다면 owner 기준으로 남은 자리를 치운다.
            _ = self._ledger.release(owner_key=owner.key)
        _close_quietly(lease)
        return True

    def remember_foreign_pages(self, pages: Sequence[object]) -> tuple[str, ...]:
        """**채택하지 않고** 관찰만 한 페이지들(개인 Chrome·CDP 가 열어 둔 탭).

        호출자는 이 페이지들을 조종하지 않고 항상 새 페이지를 연다. 여기 남는 이유는, 나중에
        "왜 사용자 탭이 안 움직이냐"는 질문에 '우리가 그걸 채택하지 않기로 했다'고 답하기 위해서다.
        """
        if not pages:
            return ()
        described = tuple(_describe_page(page) for page in pages)
        logger.info("[Browser] ignoring %d pre-existing page(s): %s", len(described), list(described))
        return described

    def close_all(self) -> int:
        """호스트 종료 경로. 열려 있던 세션을 전부 닫고 개수를 돌려준다."""
        count = 0
        for lease in list(self._leases.values()):
            count += 1
            if lease.slot:
                _ = self._ledger.release(slot=lease.slot)
            else:
                _ = self._ledger.release(owner_key=lease.owner.key)
            _close_quietly(lease)
        self._leases.clear()
        # launch 중 죽은 채 남긴 자리도 반납한다(원장에 실려 있다).
        for reservation in list(self._reservations.values()):
            if reservation.slot:
                _ = self._ledger.release(slot=reservation.slot)
        self._reservations.clear()
        if count:
            logger.info("[Browser] closed %d session(s) on shutdown", count)
        return count

    # ── 접근(egress) ────────────────────────────────────────────────────────

    def validate_navigation(self, url: str, *, allow_local: bool = False) -> str:
        """모든 진입점이 **같은** egress 규칙을 쓴다. 통과하면 정규화된 URL, 아니면 예외.

        `allow_local=True` 는 **운영자가 지정한 대상**(하네스·QA 가 두드릴 앱의 주소, 보통 루프백)에만
        쓴다 — 에이전트가 스스로 고른 주소를 로컬로 허용하는 일이 없도록 기본값은 False 이고, 쓰려면
        호출부에 그 사실이 드러나게 적어야 한다.
        """
        from antigravity_k.tools.egress_policy import validate_egress_url

        return validate_egress_url(url, allow_local=allow_local)


def _close_quietly(lease: BrowserLease) -> None:
    """닫기는 실패해도 흐름을 멈추지 않는다 — 회수 경로에서 예외가 나면 나머지 세션이 안 닫힌다."""
    closer: Callable[[], object] | None = lease.close
    if closer is None:
        candidate = cast("Callable[[], object] | None", getattr(lease.page, "close", None))
        closer = candidate if callable(candidate) else None
        if closer is None:
            return
    try:
        result = closer()
        # async close 는 여기서 기다릴 수 없다(동기 회수 경로). 코루틴이면 **닫아** 준다 —
        # 안 닫으면 "coroutine was never awaited" 경고가 남고, 그 경고가 진짜 누수를 가린다.
        if hasattr(result, "__await__"):
            discard = cast("Callable[[], object] | None", getattr(result, "close", None))
            if callable(discard):
                _ = discard()
    except Exception:
        logger.exception("[Browser] failed to close session for %s", lease.owner.describe())


# ── 전역 소유자 ─────────────────────────────────────────────────────────────

# 소문자 이름: 정책이 바뀔 때 재할당되는 모듈 전역이라 대문자 상수로 두면 정적 분석이 재정의를 막는다.
_owner: BrowserSessionOwner | None = None


def get_browser_session_owner() -> BrowserSessionOwner:
    """호스트 단일 소유자. 처음 부를 때 환경 정책으로 만든다."""
    global _owner
    if _owner is None:
        _owner = BrowserSessionOwner.from_env()
    return _owner


def configure_browser_session_owner(
    *,
    max_active_sessions: int | None = None,
    idle_ttl_seconds: float | None = None,
    task_deadline_seconds: float | None = None,
    clock: Callable[[], float] | None = None,
    wall_clock: Callable[[], float] | None = None,
    ledger: HostSessionLedger | None = None,
) -> BrowserSessionOwner:
    """정책을 명시적으로 세운다(호스트 기동·시험). 인자를 주지 않은 축은 환경/기본값을 따른다."""
    global _owner
    if _owner is not None:
        _ = _owner.close_all()
    base = BrowserSessionOwner.from_env()
    _owner = BrowserSessionOwner(
        max_active_sessions=base.max_active_sessions if max_active_sessions is None else max_active_sessions,
        idle_ttl_seconds=base.idle_ttl_seconds if idle_ttl_seconds is None else idle_ttl_seconds,
        task_deadline_seconds=(base.task_deadline_seconds if task_deadline_seconds is None else task_deadline_seconds),
        clock=clock if clock is not None else time.monotonic,
        wall_clock=wall_clock if wall_clock is not None else time.time,
        ledger=ledger,
    )
    return _owner


def reset_browser_session_owner() -> None:
    """시험용: 소유자와 세션을 함께 버린다."""
    global _owner
    if _owner is not None:
        _ = _owner.close_all()
    _owner = None


def shutdown_browser_sessions() -> dict[str, object] | None:
    """lifespan 종료 훅. 만든 적이 없으면 `None`(종료 경로에서 새로 만들지 않는다)."""
    if _owner is None:
        return None
    closed = _owner.close_all()
    return {"closed": closed, "max_active_sessions": _owner.max_active_sessions}


# ── 진입점이 쓰는 컨텍스트 ──────────────────────────────────────────────────

_OWNER_CONTEXT: ContextVar[BrowserOwner | None] = ContextVar("agk_browser_owner", default=None)


@contextmanager
def bound_browser_owner(owner: BrowserOwner) -> Iterator[BrowserOwner]:
    """도구 호출 하나의 owner 를 묶는다(HTTP 요청이 아닌 경로도 주체를 갖게 한다)."""
    token = _OWNER_CONTEXT.set(owner)
    try:
        yield owner
    finally:
        _OWNER_CONTEXT.reset(token)


def current_browser_owner() -> BrowserOwner:
    """지금 실행 중인 owner. 없으면 **기본 scope 의 로컬 도구 소유자**다.

    기본 scope(`default`)라는 것은 "명시적으로 연결한 세션이 아니다"라는 뜻이고, 그래서 이 주체는
    persistent profile 을 열 수 없다. 도구 호출에 주체를 주려면 `AGK_BROWSER_SUBJECT` 와
    `AGK_BROWSER_SCOPE` 를 **둘 다** 세운다(호출자가 명시적으로 소유권을 주장하는 경우).
    """
    bound = _OWNER_CONTEXT.get()
    if bound is not None:
        return bound
    return BrowserOwner(
        subject=os.environ.get("AGK_BROWSER_SUBJECT", "") or "local-tool",
        scope=os.environ.get("AGK_BROWSER_SCOPE", ""),
    )


def personal_profile_allowed(env: Mapping[str, str] | None = None) -> bool:
    """사용자 Chrome 프로필(쿠키 포함)을 읽어도 되는가. 기본은 **아니오**(명시 동의 필요)."""
    source = os.environ if env is None else env
    raw = str(source.get(PERSONAL_PROFILE_ENV, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def describe_policy(owner: BrowserSessionOwner | None = None) -> dict[str, object]:
    """진단용 정책 요약(비밀 없음)."""
    target = owner or get_browser_session_owner()
    ledger = target.ledger
    return {
        "max_active_sessions": target.max_active_sessions,
        "idle_ttl_seconds": target.idle_ttl_seconds,
        "task_deadline_seconds": target.task_deadline_seconds,
        "personal_profile_allowed": personal_profile_allowed(),
        # 상한이 **프로세스 경계 너머**에서도 같은지: 자리 수를 세는 공유 원장의 상태.
        # 파일 경로는 이름만 노출한다(사용자 이름이 상태 응답으로 새어 나가면 안 된다).
        "host_sessions": {
            "cap_is_host_wide": True,
            "shared_ledger_file": ledger.path().name,
            "shared_ledger_degraded": ledger.degraded,
            "shared_ledger_degrade_reason": ledger.degrade_reason,
        },
        "env": {
            "max_sessions": MAX_SESSIONS_ENV,
            "idle_ttl": IDLE_TTL_ENV,
            "task_deadline": TASK_DEADLINE_ENV,
            "personal_profile": PERSONAL_PROFILE_ENV,
            "session_state": STATE_ENV,
        },
    }


__all__ = [
    "ANONYMOUS_SUBJECT",
    "DEFAULT_IDLE_TTL_SECONDS",
    "DEFAULT_MAX_ACTIVE_SESSIONS",
    "DEFAULT_SCOPE",
    "DEFAULT_TASK_DEADLINE_SECONDS",
    "IDLE_TTL_ENV",
    "MAX_SESSIONS_ENV",
    "PERSONAL_PROFILE_ENV",
    "STATE_ENV",
    "TASK_DEADLINE_ENV",
    "BrowserLease",
    "BrowserOwner",
    "BrowserSessionLimitError",
    "BrowserSessionOwner",
    "BrowserSessionRefusedError",
    "HostSessionLedger",
    "SessionReservation",
    "bound_browser_owner",
    "configure_browser_session_owner",
    "current_browser_owner",
    "describe_policy",
    "get_browser_session_owner",
    "personal_profile_allowed",
    "reset_browser_session_owner",
    "shutdown_browser_sessions",
]
