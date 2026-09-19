"""호스트 전역 브라우저 세션 원장 — 상한·회수를 프로세스 경계 너머로 (task 16 후속).

왜 필요한가: task 16 의 소유자(`browser_session_owner.py`)는 정책과 원장을 한 곳에 모았지만
그 원장은 **프로세스 안**에 있었다. 앱(server)과 CLI(도구)가 같은 호스트에서 각자
`AGK_BROWSER_MAX_SESSIONS=2` 를 지키면 호스트에는 최대 4개의 브라우저가 뜬다 — 서로를 세지
않기 때문이다. task 15 의 `_child_running()` 이 프로세스 경계를 넘지 못해 겪은 것과 같은 계열이다.

이 모듈이 지키는 문장은 다섯이다.

1. **호스트 전체가 하나의 상한을 센다.** 세션 수는 프로세스 메모리가 아니라 **공유 원장**에서
   센다. 앱이 2개를 열어 두면 CLI 의 세 번째 시도는 거절된다(반대도 같다).
2. **원장은 임계구역 안에서만 바뀐다.** 파일 잠금(advisory lock)을 잡고 읽고-고치고-쓰며,
   쓰기는 임시 파일 + `os.replace` 로 원자적이다(부분 기록된 JSON 이 남지 않는다).
3. **죽은 프로세스의 자리는 즉시 회수된다.** 상한을 붙잡은 채 죽은 앱이 호스트를 영구히 막지
   않는다. 유휴 TTL·작업 deadline 도 **다른 프로세스가 판정**한다.
4. **원장을 못 쓰면 기동을 막지 않는다.** 상태 디렉터리를 못 만들거나 잠금을 못 잡으면 경고하고
   **프로세스 안 규칙으로 퇴화**한다(degraded). 그 사실은 `status()` 에 드러난다.
5. **손상된 원장은 버릴 수 있다.** JSON 이 깨져 있으면 옆으로 치우고 새로 시작한다(손상이 영구
   거절이 되지 않는다).

시간 축은 **벽시계**(`time.time`, epoch 초)를 쓴다. 소유자의 원장은 `time.monotonic` 을 쓰지만
그 값은 프로세스마다 다른 기준점을 가져 **다른 프로세스와 비교할 수 없다**. 그래서 파일에 실리는
시각만 벽시계이고, `idle`/`age` 는 음수가 되지 않게 자른다(시계가 뒤로 가도 회수가 앞당겨지지
않는다). 회수의 한계는 **협조적**이라는 점이다 — 다른 프로세스의 브라우저를 우리가 닫을 수는
없으므로 그 자리를 원장에서 회수하고, 소유 프로세스는 **다음 호출에서** 그 사실을 알고 닫는다.
따라서 원장이 세는 것은 "점유된 자리(claim)"이고, 그 순간 OS 에 살아 있는 브라우저 수가 더 클 수 있다.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import socket
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, final

logger = logging.getLogger(__name__)


def _import_optional(name: str) -> Any:
    """플랫폼 모듈을 선택적으로 가져온다(없으면 None).

    `Any` 로 두는 이유: 한 플랫폼에만 있는 속성(`msvcrt.locking`, `msvcrt.LK_NBLCK`)을 다른
    플랫폼에서 정적으로 검사하면 오탐이 난다(실측: basedpyright 가 `None` 의 속성으로 읽는다).
    잠금 호출은 두 함수(`_lock_fd`/`_unlock_fd`)에만 있고, 그 둘이 시험으로 덮인다.
    """
    try:
        return importlib.import_module(name)
    except ImportError:  # pragma: no cover - 플랫폼에 따라 한쪽만 없다
        return None


_FCNTL: Any = _import_optional("fcntl")  # POSIX
_MSVCRT: Any = _import_optional("msvcrt")  # Windows


def _lock_fd(handle: int) -> None:
    """배타 잠금을 **비차단**으로 시도한다. 이미 잡혀 있으면 `OSError`."""
    if _FCNTL is not None:
        _FCNTL.flock(handle, _FCNTL.LOCK_EX | _FCNTL.LOCK_NB)
        return
    if _MSVCRT is None:  # pragma: no cover - 정상 CPython 에는 둘 중 하나가 있다
        raise OSError("no file locking module on this platform")
    os.lseek(handle, 0, os.SEEK_SET)
    _MSVCRT.locking(handle, _MSVCRT.LK_NBLCK, 1)


def _unlock_fd(handle: int) -> None:
    """잠금을 푼다. 닫히면 어차피 풀리므로 실패는 삼킨다."""
    try:
        if _FCNTL is not None:
            _FCNTL.flock(handle, _FCNTL.LOCK_UN)
            return
        if _MSVCRT is None:  # pragma: no cover
            return
        os.lseek(handle, 0, os.SEEK_SET)
        _MSVCRT.locking(handle, _MSVCRT.LK_UNLCK, 1)
    except OSError:  # pragma: no cover - 닫히면 잠금도 풀린다
        pass


#: 원장 파일의 스키마 표식. 다른 스키마가 보이면 손상 취급하지 않고 **경고 후 무시**한다.
SCHEMA = "ssak.browser.sessions/1.0"

#: 원장 파일(또는 그 디렉터리)을 지정하는 환경변수. 비어 있으면 사용자 상태 디렉터리를 쓴다.
STATE_ENV = "AGK_BROWSER_SESSION_STATE"

#: 잠금을 기다리는 시간(초). 넘으면 퇴화 모드로 내려간다(기동을 막지 않는다).
LOCK_TIMEOUT_ENV = "AGK_BROWSER_SESSION_LOCK_TIMEOUT_SECONDS"
DEFAULT_LOCK_TIMEOUT_SECONDS = 2.0

#: 사용자 상태 디렉터리 기본값 — `~/.antigravity-k` 는 이미 신뢰 루트다(task 13/15).
STATE_RELATIVE = Path("browser_sessions.json")

KIND_SESSION = "session"
KIND_RESERVATION = "reservation"

#: 회수 이유(문자열은 로그·증거에 그대로 실린다).
REASON_DEAD_PROCESS = "dead_process"
REASON_IDLE_TTL = "idle_ttl"
REASON_TASK_DEADLINE = "task_deadline"
REASON_ABANDONED_RESERVATION = "abandoned_reservation"

_SLOT_CHARS = 12
_MAX_PURPOSE_CHARS = 80


def state_path(env: Mapping[str, str] | None = None) -> Path:
    """원장 파일 경로. `AGK_BROWSER_SESSION_STATE` 가 디렉터리면 그 안의 기본 파일명을 쓴다."""
    source = os.environ if env is None else env
    raw = str(source.get(STATE_ENV, "") or "").strip()
    if not raw:
        return Path.home() / ".antigravity-k" / STATE_RELATIVE
    candidate = Path(raw).expanduser()
    if candidate.is_dir() or raw.endswith(os.sep):
        return candidate / STATE_RELATIVE.name
    return candidate


def lock_timeout_seconds(env: Mapping[str, str] | None = None) -> float:
    """잠금 대기 시간. 잘못된 값은 기본값으로 되돌린다(기동을 막지 않는다)."""
    source = os.environ if env is None else env
    raw = str(source.get(LOCK_TIMEOUT_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_LOCK_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using %s", LOCK_TIMEOUT_ENV, raw, DEFAULT_LOCK_TIMEOUT_SECONDS)
        return DEFAULT_LOCK_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning("%s=%r must be positive; using %s", LOCK_TIMEOUT_ENV, raw, DEFAULT_LOCK_TIMEOUT_SECONDS)
        return DEFAULT_LOCK_TIMEOUT_SECONDS
    return value


def _process_alive(pid: int) -> bool:
    """그 pid 가 아직 살아 있는가. 확실하지 않으면 **살아 있다고 본다**(자리를 함부로 지우지 않는다).

    Windows 에서 `os.kill(pid, 0)` 은 위험하다 — 지원하지 않는 신호는 `TerminateProcess` 로
    흘러가 프로세스를 실제로 죽인다. 그래서 플랫폼마다 다른 방법을 쓴다.
    """
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":  # pragma: no cover - 이 저장소의 판정 환경은 macOS/Linux
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 살아 있지만 우리 것이 아니다
    except OSError:
        return True
    return True


def _windows_process_alive(pid: int) -> bool:  # pragma: no cover - Windows 전용
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


@dataclass
class LedgerEntry:
    """원장에 실린 자리 하나. `kind` 가 아직 launch 중인지(예약) 확정됐는지(세션)를 가른다."""

    slot: str
    owner_key: str
    pid: int
    opened_at: float
    last_used_at: float
    kind: str = KIND_RESERVATION
    host: str = ""
    persistent: bool = False
    purpose: str = ""

    def age(self, now: float) -> float:
        return max(0.0, now - self.opened_at)

    def idle(self, now: float) -> float:
        return max(0.0, now - self.last_used_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "owner_key": self.owner_key,
            "pid": self.pid,
            "host": self.host,
            "kind": self.kind,
            "opened_at": self.opened_at,
            "last_used_at": self.last_used_at,
            "persistent": self.persistent,
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LedgerEntry | None":
        try:
            slot = str(raw["slot"])
            owner_key = str(raw["owner_key"])
            pid = int(raw["pid"])
            opened_at = float(raw["opened_at"])
            last_used_at = float(raw["last_used_at"])
        except (KeyError, TypeError, ValueError):
            return None
        kind = str(raw.get("kind", KIND_RESERVATION))
        return cls(
            slot=slot,
            owner_key=owner_key,
            pid=pid,
            opened_at=opened_at,
            last_used_at=last_used_at,
            kind=kind if kind in {KIND_SESSION, KIND_RESERVATION} else KIND_RESERVATION,
            host=str(raw.get("host", "")),
            persistent=bool(raw.get("persistent", False)),
            purpose=str(raw.get("purpose", ""))[:_MAX_PURPOSE_CHARS],
        )

    def describe(self, now: float) -> dict[str, Any]:
        """로그·status 용. owner_key 는 앞 12자만(전체 해시는 동일성 판정에만 쓴다)."""
        return {
            "slot": self.slot,
            "owner": self.owner_key[:12],
            "pid": self.pid,
            "kind": self.kind,
            "age_seconds": round(self.age(now), 1),
            "idle_seconds": round(self.idle(now), 1),
            "persistent": self.persistent,
            "purpose": self.purpose,
        }


@final
@dataclass(frozen=True)
class LedgerDecision:
    """`admit()`/`commit()` 의 판정. `granted=False` 면 호출자는 상한 초과로 거절해야 한다."""

    granted: bool
    kind: str  # "new" | "reuse" | "reservation" | "refused" | "degraded"
    slot: str | None = None
    host_active: int = 0
    max_active: int = 0
    reclaimed: tuple[dict[str, Any], ...] = ()
    reason: str = ""


@final
class HostSessionLedger:
    """호스트 전역 세션 원장. 상한 판정과 회수를 프로세스 경계 너머로 옮긴다."""

    def __init__(
        self,
        *,
        path: Path | None = None,
        lock_timeout: float | None = None,
        wall_clock: Any = time.time,
        hostname: str | None = None,
        pid: int | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._explicit_path = Path(path).expanduser() if path is not None else None
        self._env = dict(env) if env is not None else None
        self._lock_timeout = lock_timeout
        self._wall_clock = wall_clock
        self._hostname = hostname or socket.gethostname()
        self._pid = os.getpid() if pid is None else pid
        self._degraded: str = ""

    # ── 경로·상태 ────────────────────────────────────────────────────────────

    @property
    def pid(self) -> int:
        return self._pid

    def path(self) -> Path:
        """원장 파일 경로(첫 사용 시 결정 — 시험이 env 를 먼저 세울 수 있게 지연 해석한다)."""
        if self._explicit_path is not None:
            return self._explicit_path
        return state_path(self._env)

    @property
    def degraded(self) -> bool:
        return bool(self._degraded)

    @property
    def degrade_reason(self) -> str:
        return self._degraded

    def _degrade(self, reason: str) -> None:
        if not self._degraded:
            self._degraded = reason
            logger.warning("[Browser] host session ledger unavailable (%s); falling back to per-process rules", reason)

    # ── 파일 읽기/쓰기 ──────────────────────────────────────────────────────

    def _read(self) -> list[LedgerEntry]:
        target = self.path()
        try:
            raw = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as error:
            self._degrade(f"read:{error.__class__.__name__}")
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._quarantine(target)
            return []
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            logger.warning("[Browser] ignoring host session ledger with unexpected schema at %s", target.name)
            return []
        entries = payload.get("entries")
        if not isinstance(entries, list):
            self._quarantine(target)
            return []
        restored: list[LedgerEntry] = []
        for item in entries:
            if isinstance(item, dict):
                entry = LedgerEntry.from_dict(item)
                if entry is not None:
                    restored.append(entry)
        return restored

    def _write(self, entries: list[LedgerEntry]) -> None:
        target = self.path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": SCHEMA, "entries": [entry.to_dict() for entry in entries]}
            temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex[:8]}.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except OSError as error:
            self._degrade(f"write:{error.__class__.__name__}")

    def _quarantine(self, target: Path) -> None:
        """손상된 원장을 옆으로 치운다 — 손상이 영구 거절이 되지 않게 한다."""
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        try:
            os.replace(target, target.with_name(f"{target.name}.corrupt-{stamp}"))
            logger.warning("[Browser] quarantined a corrupt host session ledger: %s", target.name)
        except OSError:  # pragma: no cover - 치우지 못하면 그냥 새로 시작한다
            logger.warning("[Browser] could not quarantine the corrupt host session ledger: %s", target.name)

    # ── 잠금 ────────────────────────────────────────────────────────────────

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """파일 잠금 안에서만 원장을 읽고 쓴다. 잠금을 못 잡으면 **경고하고 임계구역 없이** 진행한다.

        잠금은 advisory 이므로 같은 규칙을 쓰는 프로세스끼리만 유효하다. 그 사실이 곧 이 원장의
        신뢰 가정이다(다른 도구가 같은 파일을 직접 쓰면 우리는 그것을 보호할 수 없다).
        """
        if _FCNTL is None and _MSVCRT is None:  # pragma: no cover - 정상 CPython 에는 둘 중 하나가 있다
            self._degrade("no_file_lock")
            yield
            return
        target = self.path()
        lock_path = target.with_name(f"{target.name}.lock")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as error:
            self._degrade(f"lock:{error.__class__.__name__}")
            yield
            return
        acquired = False
        try:
            acquired = self._acquire_lock(handle)
            if not acquired:
                # 잠금 대기 초과 — 다른 프로세스가 임계구역에 오래 있다. 닫는 것과 여는 것을
                # 모두 막으면 호스트가 그 프로세스에 인질이 되므로, 퇴화 모드로 내려간다.
                self._degrade("lock_timeout")
            yield
        finally:
            if acquired:
                _unlock_fd(handle)
            os.close(handle)

    def _acquire_lock(self, handle: int) -> bool:
        """잠금을 잡을 때까지 짧게 기다린다. 시간을 넘기면 False(퇴화 모드로 내려간다)."""
        timeout = self._lock_timeout if self._lock_timeout is not None else lock_timeout_seconds(self._env)
        deadline = time.monotonic() + timeout
        while True:
            try:
                _lock_fd(handle)
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)

    # ── 회수 판정 ───────────────────────────────────────────────────────────

    @staticmethod
    def _reclaim(entries: list[LedgerEntry], now: float, idle_ttl: float, task_deadline: float) -> list[dict[str, Any]]:
        """죽은 프로세스·유휴 TTL·작업 deadline 을 지나 점유된 자리를 **걷어낸다**(in place).

        걷어낸 자리는 원장에서 사라지고, 소유 프로세스는 다음 호출에서 그 사실을 알고 닫는다.
        """
        reclaimed: list[dict[str, Any]] = []
        kept: list[LedgerEntry] = []
        for entry in entries:
            reason = ""
            if not _process_alive(entry.pid):
                reason = REASON_DEAD_PROCESS
            elif entry.kind == KIND_RESERVATION:
                if entry.age(now) >= task_deadline:
                    reason = REASON_ABANDONED_RESERVATION
            elif entry.idle(now) >= idle_ttl:
                reason = REASON_IDLE_TTL
            elif entry.age(now) >= task_deadline:
                reason = REASON_TASK_DEADLINE
            if reason:
                descriptor = entry.describe(now)
                descriptor["reason"] = reason
                reclaimed.append(descriptor)
                logger.info(
                    "[Browser] reclaimed a host session slot (%s): slot=%s pid=%s",
                    reason,
                    entry.slot,
                    entry.pid,
                )
                continue
            kept.append(entry)
        entries[:] = kept
        return reclaimed

    # ── 공개 API ────────────────────────────────────────────────────────────

    def entries(self) -> tuple[LedgerEntry, ...]:
        """원장에 지금 실려 있는 자리들(회수 판정 없이 읽기만)."""
        with self._locked():
            return tuple(self._read())

    def host_active(self) -> int:
        """호스트 전체가 점유한 자리 수(죽은 프로세스의 자리는 세지 않는다)."""
        return len(self.entries())

    def admit(
        self,
        *,
        owner_key: str,
        max_active: int,
        idle_ttl: float,
        task_deadline: float,
        purpose: str = "",
        persistent: bool = False,
    ) -> LedgerDecision:
        """자리를 하나 요청한다(원장 기준). 상한을 넘으면 `granted=False`.

        같은 (owner_key, pid) 의 세션이 이미 있으면 **재사용**이고 새 자리를 쓰지 않는다. 자리
        요청은 **예약**으로 실린다 — launch 전에 자리를 차지해야 동시 첫 호출이 브라우저를 여러
        개 띄우지 않는다(task 12/16 과 같은 이유).
        """
        now = self._wall_clock()
        with self._locked():
            if self._degraded:
                return LedgerDecision(granted=True, kind="degraded", host_active=0, max_active=max_active)
            entries = self._read()
            reclaimed = self._reclaim(entries, now, idle_ttl, task_deadline)
            mine = [entry for entry in entries if entry.owner_key == owner_key and entry.pid == self._pid]
            live = [entry for entry in mine if entry.kind == KIND_SESSION]
            pending = [entry for entry in mine if entry.kind == KIND_RESERVATION]
            if live:
                live[0].last_used_at = now
                self._write(entries)
                logger.info("[Browser] host ledger reuse: slot=%s host_active=%d", live[0].slot, len(entries))
                return LedgerDecision(
                    granted=True,
                    kind="reuse",
                    slot=live[0].slot,
                    host_active=len(entries),
                    max_active=max_active,
                    reclaimed=tuple(reclaimed),
                )
            if pending:
                pending[0].last_used_at = now
                self._write(entries)
                return LedgerDecision(
                    granted=True,
                    kind="reservation",
                    slot=pending[0].slot,
                    host_active=len(entries),
                    max_active=max_active,
                    reclaimed=tuple(reclaimed),
                )
            if len(entries) >= max_active:
                logger.info(
                    "[Browser] host session limit reached: %d/%d (this process holds %d)",
                    len(entries),
                    max_active,
                    len(mine),
                )
                return LedgerDecision(
                    granted=False,
                    kind="refused",
                    host_active=len(entries),
                    max_active=max_active,
                    reclaimed=tuple(reclaimed),
                    reason="host_limit",
                )
            entry = LedgerEntry(
                slot=uuid.uuid4().hex[:_SLOT_CHARS],
                owner_key=owner_key,
                pid=self._pid,
                opened_at=now,
                last_used_at=now,
                kind=KIND_RESERVATION,
                host=self._hostname,
                persistent=persistent,
                purpose=purpose[:_MAX_PURPOSE_CHARS],
            )
            entries.append(entry)
            self._write(entries)
            logger.info(
                "[Browser] host ledger reserved: slot=%s host_active=%d/%d", entry.slot, len(entries), max_active
            )
            return LedgerDecision(
                granted=True,
                kind="new",
                slot=entry.slot,
                host_active=len(entries),
                max_active=max_active,
                reclaimed=tuple(reclaimed),
            )

    def commit(
        self,
        slot: str,
        *,
        owner_key: str,
        max_active: int,
        idle_ttl: float,
        task_deadline: float,
        purpose: str = "",
        persistent: bool = False,
    ) -> LedgerDecision:
        """예약을 확정한다. 그 사이 다른 프로세스가 자리를 회수했다면 **다시 자리를 요청**한다.

        회수는 보통 deadline 을 지난 예약에만 일어나므로 그 시점에는 자리가 비어 있다. 그래도
        비어 있지 않다면(다른 프로세스가 먼저 가져갔다면) 상한을 넘기지 않고 거절한다 —
        확정 실패는 호출자의 실패 경로(`abort()`)가 처리한다.
        """
        now = self._wall_clock()
        with self._locked():
            if self._degraded:
                return LedgerDecision(granted=True, kind="degraded", slot=None, max_active=max_active)
            entries = self._read()
            reclaimed = self._reclaim(entries, now, idle_ttl, task_deadline)
            for entry in entries:
                if entry.slot == slot and entry.owner_key == owner_key and entry.pid == self._pid:
                    entry.kind = KIND_SESSION
                    entry.last_used_at = now
                    entry.persistent = entry.persistent or persistent
                    entry.purpose = entry.purpose or purpose[:_MAX_PURPOSE_CHARS]
                    self._write(entries)
                    return LedgerDecision(
                        granted=True,
                        kind="session",
                        slot=slot,
                        host_active=len(entries),
                        max_active=max_active,
                        reclaimed=tuple(reclaimed),
                    )
        # 자리가 사라졌다(다른 프로세스가 회수했거나 우리 원장이 손상됐다) — 새로 요청한다.
        decision = self.admit(
            owner_key=owner_key,
            max_active=max_active,
            idle_ttl=idle_ttl,
            task_deadline=task_deadline,
            purpose=purpose,
            persistent=persistent,
        )
        return replace(decision, reclaimed=(*reclaimed, *decision.reclaimed), reason="slot_reclaimed")

    def heartbeat(self, slot: str) -> bool:
        """내 자리를 살아 있다고 표시한다. 다른 프로세스가 이미 회수했으면 False."""
        if not slot:
            return False
        now = self._wall_clock()
        with self._locked():
            if self._degraded:
                return True
            entries = self._read()
            for entry in entries:
                if entry.slot == slot and entry.pid == self._pid:
                    entry.last_used_at = now
                    self._write(entries)
                    return True
        return False

    def release(self, *, slot: str = "", owner_key: str = "") -> bool:
        """자리를 반납한다(닫을 때). slot 을 주면 그 자리만, 아니면 이 프로세스의 그 owner 자리 전부."""
        with self._locked():
            if self._degraded:
                return False
            entries = self._read()
            kept: list[LedgerEntry] = []
            removed = False
            for entry in entries:
                mine = entry.pid == self._pid and (not owner_key or entry.owner_key == owner_key)
                if slot and entry.slot == slot and entry.pid == self._pid:
                    removed = True
                    continue
                if not slot and mine:
                    removed = True
                    continue
                kept.append(entry)
            if removed:
                entries[:] = kept
                self._write(entries)
            return removed

    def reclaim(self, *, idle_ttl: float, task_deadline: float) -> tuple[dict[str, Any], ...]:
        """회수만 한 번 돌린다(판정 근거를 돌려준다). `begin()` 이 아닌 경로에서도 쓸 수 있다."""
        now = self._wall_clock()
        with self._locked():
            if self._degraded:
                return ()
            entries = self._read()
            reclaimed = self._reclaim(entries, now, idle_ttl, task_deadline)
            if reclaimed:
                self._write(entries)
            return tuple(reclaimed)

    def status(self) -> dict[str, Any]:
        """진단용 스냅숏. **경로 전체를 노출하지 않는다**(사용자 이름이 새어 나갈 수 있다)."""
        now = self._wall_clock()
        entries = self.entries()
        return {
            "file": self.path().name,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "host_active": len(entries),
            "hosts": sorted({entry.host for entry in entries if entry.host}),
            "entries": [entry.describe(now) for entry in entries],
        }


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "KIND_RESERVATION",
    "KIND_SESSION",
    "LOCK_TIMEOUT_ENV",
    "REASON_ABANDONED_RESERVATION",
    "REASON_DEAD_PROCESS",
    "REASON_IDLE_TTL",
    "REASON_TASK_DEADLINE",
    "SCHEMA",
    "STATE_ENV",
    "HostSessionLedger",
    "LedgerDecision",
    "LedgerEntry",
    "lock_timeout_seconds",
    "state_path",
]
