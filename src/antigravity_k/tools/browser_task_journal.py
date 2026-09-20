"""작업 저널 — 브라우저 작업의 의도·발송·관측 결과를 **디스크에 남긴다**(task 20).

이 파일이 재는 것
----------------
**"무슨 일이 일어났는지" 를 프로세스가 죽어도 알 수 있게 한다.** task 19 의 루프는 결말을 코드로
말하지만 그 코드는 **메모리**에 살았다. 앱이 재시작하거나 CLI 가 SIGKILL 을 맞으면, 이미 사이트에
도달했을 수도 있는 행동(송금·제출·삭제)의 운명은 아무 데도 남지 않는다 — 그러면 재개는 **같은
행동을 다시 누르는 것**이고, 그것이 이 파일이 막으려는 유일한 사고다.

기록 순서는 계약이다: `intent`(누르려 한다) → `dispatched`(보냈다) → `observed_outcome`(결과를 봤다).
**발송 기록이 있고 결과 기록이 없으면 그 행동의 운명은 모른다.** 되돌릴 수 없는 효과라면 그
상태를 `UNKNOWN_OUTCOME` 이라 부르고 **자동 재실행을 금지**한다(`ResumePlan.replay_allowed`).

무엇을 남기지 않는가
------------------
**비밀은 남기지 않는다.** 비밀번호·토큰·쿠키·인증 헤더·입력값은 기록될 수 없고, 값 대신
handle(`secret_ref`)만 남는다. 이 규칙은 호출자의 절제가 아니라 **쓰기 경로의 검사**다
(`_reject_secrets`) — 사람이 실수로 넘겨도 파일에 들어가지 않는다.

idempotency 의 범위
------------------
같은 `idempotency_key` 의 두 번째 요청은 **실행되지 않고** 기록된 결말을 돌려준다(중복 방지).
이것은 **이 서비스 내부의 중복 방지**이지 외부 사이트의 exactly-once 보장이 아니다 — 저널은 우리가
보낸 것을 아는 만큼만 안다. 그 한계가 `ResumePlan.idempotency_scope` 에 문장으로 남는다.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast, final

logger = logging.getLogger(__name__)

#: 저널 파일의 스키마 표식. 다른 스키마 줄은 손상으로 취급하지 않고 **건너뛴다**.
SCHEMA: Final = "ssak.browser.tasks/1.0"

#: 저널 파일(또는 디렉터리)을 지정하는 환경변수. 비어 있으면 사용자 상태 디렉터리.
JOURNAL_ENV: Final = "AGK_BROWSER_TASK_JOURNAL"

#: 잠금 대기 시간(초). 넘으면 기록을 **거절**한다(중복 방지는 거짓말하면 안 되는 판정이다).
LOCK_TIMEOUT_ENV: Final = "AGK_BROWSER_TASK_JOURNAL_LOCK_TIMEOUT_SECONDS"
DEFAULT_LOCK_TIMEOUT_SECONDS: Final = 2.0

#: 사용자 상태 디렉터리 기본값 — `~/.antigravity-k` 는 이미 신뢰 루트다(task 13/15/16).
JOURNAL_RELATIVE: Final = Path("browser_tasks.jsonl")

# ── 기록 종류 ───────────────────────────────────────────────────────────────
KIND_OPENED: Final = "task_opened"
KIND_INTENT: Final = "intent"
KIND_DISPATCH: Final = "dispatched"
KIND_OUTCOME: Final = "observed_outcome"
KIND_FINISHED: Final = "task_finished"
KIND_CANCEL_REQUESTED: Final = "cancel_requested"
KIND_CANCEL_OBSERVED: Final = "cancel_observed"
KIND_RESUMED: Final = "resumed"
KINDS: Final[frozenset[str]] = frozenset(
    {
        KIND_OPENED,
        KIND_INTENT,
        KIND_DISPATCH,
        KIND_OUTCOME,
        KIND_FINISHED,
        KIND_CANCEL_REQUESTED,
        KIND_CANCEL_OBSERVED,
        KIND_RESUMED,
    }
)

# ── 결말 코드 ───────────────────────────────────────────────────────────────
UNKNOWN_OUTCOME: Final = "UNKNOWN_OUTCOME"
REPLAY_REFUSED: Final = "REPLAY_REFUSED"
SAFE_RETRY: Final = "SAFE_RETRY"
DUPLICATE_REQUEST: Final = "DUPLICATE_REQUEST"
STALE_SESSION: Final = "STALE_SESSION"
STALE_APPROVAL: Final = "STALE_APPROVAL"
ALREADY_FINISHED: Final = "ALREADY_FINISHED"
CANCEL_REQUESTED: Final = "CANCEL_REQUESTED"
CANCELLED_BEFORE_START: Final = "CANCELLED_BEFORE_START"

# ── 오류 코드 ───────────────────────────────────────────────────────────────
SECRET_IN_RECORD: Final = "SECRET_IN_RECORD"
ORDER_VIOLATION: Final = "ORDER_VIOLATION"
UNKNOWN_TASK: Final = "UNKNOWN_TASK"
JOURNAL_UNAVAILABLE: Final = "JOURNAL_UNAVAILABLE"

#: 되돌릴 수 없는 효과(task 18 의 `REQUIRES_APPROVAL` 과 **같은 집합**을 이름으로 갖는다).
#: 효과 이름을 문자열로 두는 이유: 저널은 승인 모듈을 import 하지 않는다(파일 형식이 코드에 묶이지
#: 않게). 값은 `browser_approval.Effect` 의 값과 같고, 시험이 그 일치를 확인한다.
CONSEQUENTIAL_EFFECTS: Final[frozenset[str]] = frozenset(
    {
        "transmit",
        "upload",
        "auth",
        "permission",
        "delete",
        "settings",
        "financial",
        "unknown",
    }
)

#: 절대 기록되지 않는 키. 값이 아니라 **키 이름**으로 막는다(비밀은 어디서든 같은 이름을 쓴다).
FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "secrets",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "auth_header",
        "cookie",
        "cookies",
        "set_cookie",
        "credential",
        "credentials",
        "otp",
        "mfa_code",
        "value",  # 입력값(비밀일 수 있다) — 값은 `secret_ref` handle 로만 다룬다
        "form_value",
        "fill_value",
        "card_number",
        "cvv",
        "ssn",
    }
)

#: 사람이 취소를 눌렀을 때 그 요청이 **관측되기까지** 기다리는 시간(초). 계획의 "2초 내 협력 취소".
DEFAULT_CANCEL_GRACE_SECONDS: Final = 2.0


class JournalError(RuntimeError):
    """저널이 계약을 거절했다. `code` 가 상위 계층의 다음 행동을 정한다."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.details: dict[str, Any] = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


# ── 플랫폼 잠금 (browser_session_ledger 와 같은 모양) ────────────────────────
def _import_optional(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError:  # pragma: no cover - 플랫폼에 따라 한쪽만 없다
        return None


_FCNTL: Any = _import_optional("fcntl")
_MSVCRT: Any = _import_optional("msvcrt")


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


def journal_path(env: Mapping[str, str] | None = None) -> Path:
    """저널 파일 경로. `AGK_BROWSER_TASK_JOURNAL` 이 디렉터리면 그 안의 기본 파일명을 쓴다."""
    source = os.environ if env is None else env
    raw = str(source.get(JOURNAL_ENV, "") or "").strip()
    if not raw:
        return Path.home() / ".antigravity-k" / JOURNAL_RELATIVE
    candidate = Path(raw).expanduser()
    if candidate.is_dir() or raw.endswith(os.sep):
        return candidate / JOURNAL_RELATIVE.name
    return candidate


# ── 값 검사 ─────────────────────────────────────────────────────────────────
def _reject_secrets(payload: Mapping[str, Any], *, where: str) -> None:
    """비밀 모양의 키가 있으면 **쓰기를 거절**한다(경고가 아니라 거절이다).

    경고로 두면 그 줄은 이미 파일에 있다. 이 저널은 재시작 뒤에도 읽히므로, 한 번 들어간 비밀은
    지우기 전까지 남는다 — 그래서 판정을 쓰기 **앞**에 둔다. 호출자가 넘긴 `metadata` 도 같은
    검사를 지나므로, 깊이를 숨겨도(중첩 mapping) 빠져나가지 못하다.
    """
    for key, value in payload.items():
        if str(key).strip().lower() in FORBIDDEN_KEYS:
            raise JournalError(
                SECRET_IN_RECORD,
                f"{where}: 비밀로 취급되는 키는 저널에 기록할 수 없다: {key!r} (값 대신 handle 만 남긴다)",
                details={"field": str(key)},
            )
        if isinstance(value, Mapping):
            _reject_secrets(cast("Mapping[str, Any]", value), where=where)


def _is_consequential(effect: str) -> bool:
    return str(effect).strip().lower() in CONSEQUENTIAL_EFFECTS


# ── 레코드 ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class JournalRecord:
    """저널 한 줄. 모르는 키는 버리고 아는 키만 남긴다(전방 호환)."""

    seq: int
    at: float
    kind: str
    task_id: str
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def intent_seq(self) -> int | None:
        raw = self.data.get("intent_seq")
        return int(raw) if isinstance(raw, (int, float)) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "seq": self.seq,
            "at": self.at,
            "kind": self.kind,
            "task_id": self.task_id,
            **self.data,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "JournalRecord | None":
        try:
            seq = int(raw["seq"])
            at = float(raw["at"])
            kind = str(raw["kind"])
            task_id = str(raw["task_id"])
        except (KeyError, TypeError, ValueError):
            return None
        if kind not in KINDS:
            return None
        data = {k: v for k, v in raw.items() if k not in {"schema", "seq", "at", "kind", "task_id"}}
        return cls(seq=seq, at=at, kind=kind, task_id=task_id, data=data)


@dataclass(frozen=True)
class TaskIntent:
    """발송 **전** 의도. `seq` 가 이 의도의 신원이고, 발송·결과 기록이 이 번호를 가리킨다."""

    seq: int
    action: str
    target: str
    effect: str
    consequential: bool
    ref: str
    generation: int
    approval: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "action": self.action,
            "target": self.target,
            "effect": self.effect,
            "consequential": self.consequential,
            "ref": self.ref,
            "generation": self.generation,
            "approval": self.approval,
        }


@dataclass(frozen=True)
class CancelRequest:
    """취소 요청. `requested_at` 이 사람이 누른 시각이고, 관측 시각과의 차이가 협력 지연이다."""

    task_id: str
    requested_at: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "requested_at": self.requested_at, "reason": self.reason}


@dataclass(frozen=True)
class OpenResult:
    """`open_task` 의 결과. `duplicate=True` 면 **이미 본 요청**이라 실행하지 않는다."""

    task_id: str
    duplicate: bool
    opened_at: float
    finished: Mapping[str, Any] | None = None
    phase: str = "new"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "duplicate": self.duplicate,
            "opened_at": self.opened_at,
            "finished": dict(self.finished) if self.finished else None,
            "phase": self.phase,
        }


@dataclass(frozen=True)
class ResumePlan:
    """재시작 뒤 이 작업을 어떻게 이어받을 것인가 — **판정 하나**로 모은다.

    `replay_allowed=False` 는 "다시 눌러도 되는지 모른다" 가 아니라 "다시 누르면 안 된다" 다.
    `unknown_outcomes` 가 비어 있지 않으면 되돌릴 수 없는 행동의 운명이 미확정이므로, 사람이
    사이트에서 확인하기 전까지 이 작업은 자동으로 진행되지 않는다.
    """

    task_id: str
    phase: str
    code: str
    reason: str
    replay_allowed: bool
    must_reobserve: bool
    open_intents: tuple[TaskIntent, ...]
    unknown_outcomes: tuple[TaskIntent, ...]
    stale_approvals: tuple[str, ...]
    cancel: CancelRequest | None
    finished: Mapping[str, Any] | None
    idempotency_scope: str

    @property
    def resumable(self) -> bool:
        """이어받아 **계속 돌려도 되는가**. 취소·미확정·종료된 작업은 여기 없다.

        취소된 작업은 이어받는 것이 아니라 **새 작업**으로 시작해야 하고, 미확정 작업은 사람이
        확인해야 하며, 끝난 작업은 다시 돌릴 이유가 없다. 이 셋을 '재개 가능' 으로 묶으면 화면이
        누를 수 없는 버튼을 그린다.
        """
        return self.phase in {"read_only_open", "idle"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "code": self.code,
            "reason": self.reason,
            "replay_allowed": self.replay_allowed,
            "must_reobserve": self.must_reobserve,
            "open_intents": [item.to_dict() for item in self.open_intents],
            "unknown_outcomes": [item.to_dict() for item in self.unknown_outcomes],
            "stale_approvals": list(self.stale_approvals),
            "cancel": self.cancel.to_dict() if self.cancel else None,
            "finished": dict(self.finished) if self.finished else None,
            "idempotency_scope": self.idempotency_scope,
        }


_IDEMPOTENCY_SCOPE: Final = (
    "중복 방지는 이 서비스 안에서만 유효하다 — 같은 idempotency_key 의 두 번째 요청은 실행되지 않고 "
    "기록된 결말을 돌려준다. 외부 사이트의 exactly-once 는 보장하지 않는다(저널은 우리가 보낸 것만 안다)."
)


# ── 저널 ────────────────────────────────────────────────────────────────────
@final
class BrowserTaskJournal:
    """append-only JSONL. 읽기는 전방 호환(모르는 줄은 건너뛴다), 쓰기는 계약을 지킨다."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        clock: Callable[[], float] = time.time,
        lock_timeout: float | None = None,
    ) -> None:
        self.path: Path = Path(path) if path is not None else journal_path()
        self._clock = clock
        self._lock_timeout = DEFAULT_LOCK_TIMEOUT_SECONDS if lock_timeout is None else lock_timeout
        self._seq = 0  # 마지막으로 읽거나 쓴 seq — 읽을 때마다 파일에서 다시 맞춘다

    # ── 경로/기본 ──
    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def exists(self) -> bool:
        return self.path.exists()

    def now(self) -> float:
        """이 저널이 **기록에 쓰는 시계**의 현재 값.

        취소 지연을 재는 쪽이 다른 시계(단조 시계 등)를 쓰면 두 값이 다른 원점을 갖는다 — 그러면
        "제때 멈췄다" 가 항상 참이 되어 시간초과 판정이 조용히 사라진다(실제로 그렇게 잘못 재었다).
        """
        return self._clock()

    # ── 읽기 ──
    def records(self, *, task_id: str | None = None) -> tuple[JournalRecord, ...]:
        """파일을 처음부터 읽는다. 손상된 줄·부분 줄(크래시 중 기록)은 **건너뛴다**."""
        if not self.path.exists():
            return ()
        out: list[JournalRecord] = []
        try:
            with self.path.open("rb") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.warning("browser task journal: skipping an unreadable line in %s", self.path)
                        continue
                    if not isinstance(parsed, Mapping) or parsed.get("schema") != SCHEMA:
                        continue
                    record = JournalRecord.from_dict(parsed)
                    if record is None:
                        continue
                    if task_id is not None and record.task_id != task_id:
                        continue
                    out.append(record)
        except OSError as exc:  # pragma: no cover - 읽을 수 없으면 아는 것이 없다(거짓말하지 않는다)
            logger.warning("browser task journal: cannot read %s (%s)", self.path, exc)
            return ()
        if out:
            self._seq = max(self._seq, out[-1].seq)
        return tuple(out)

    def task_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for record in self.records():
            if record.task_id not in seen:
                seen.append(record.task_id)
        return tuple(seen)

    # ── 쓰기 ──
    def _append(self, task_id: str, kind: str, data: Mapping[str, Any]) -> JournalRecord:
        _reject_secrets(data, where=kind)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise JournalError(JOURNAL_UNAVAILABLE, f"저널 디렉터리를 만들 수 없다: {exc}") from exc
        with self._locked():
            seq = self._next_seq()
            record = JournalRecord(seq=seq, at=self._clock(), kind=kind, task_id=task_id, data=dict(data))
            payload = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            except OSError as exc:
                raise JournalError(JOURNAL_UNAVAILABLE, f"저널을 열 수 없다: {exc}") from exc
            try:
                os.write(fd, payload + b"\n")
                os.fsync(fd)
            finally:
                os.close(fd)
        return record

    def _next_seq(self) -> int:
        """seq 는 파일에서 이어받는다 — 프로세스가 여러 개여도 한 줄씩 증가한다."""
        existing = self.records()
        return (existing[-1].seq if existing else 0) + 1

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """판정(읽고-쓰기) 구간을 파일 잠금으로 감싼다. 잡지 못하면 **거절**한다.

        자리를 세는 원장(task 16 후속)은 잠금 실패 시 퇴화해도 되지만, 중복 방지는 퇴화하면
        거짓말이 된다("처음 보는 요청" 이라며 같은 일을 두 번 시킨다). 그래서 여기서는 멈춘다.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise JournalError(JOURNAL_UNAVAILABLE, f"저널 잠금 파일을 열 수 없다: {exc}") from exc
        deadline = time.monotonic() + max(0.0, self._lock_timeout)
        try:
            while True:
                try:
                    _lock_fd(handle)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise JournalError(
                            JOURNAL_UNAVAILABLE,
                            "저널 잠금을 잡지 못했다 — 중복 방지 판정을 거짓으로 말하지 않으려고 기록을 거절한다",
                            details={"lock": str(self.lock_path)},
                        ) from None
                    time.sleep(0.02)
            yield
        finally:
            _unlock_fd(handle)
            os.close(handle)

    # ── 작업 수명 ──
    def open_task(
        self,
        task_id: str,
        *,
        goal: str,
        postconditions: Any = (),
        session: str = "",
        idempotency_key: str | None = None,
        owner_pid: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OpenResult:
        """작업을 연다. 같은 idempotency_key 를 이미 봤다면 **실행하지 않고** 그 결말을 알린다."""
        key = str(idempotency_key or task_id)
        with self._locked():
            records = list(self.records())
            prior = self._find_by_key(records, key)
            if prior is not None:
                finished = self._finished(records, prior)
                return OpenResult(
                    task_id=prior,
                    duplicate=True,
                    opened_at=self._opened_at(records, prior),
                    finished=finished,
                    phase="finished" if finished is not None else "open",
                )
            seq = self._next_seq()
            record = JournalRecord(
                seq=seq,
                at=self._clock(),
                kind=KIND_OPENED,
                task_id=task_id,
                data={
                    "goal": goal,
                    "postconditions": json.dumps(postconditions, ensure_ascii=False),
                    "session": session,
                    "idempotency_key": key,
                    "owner_pid": owner_pid if owner_pid is not None else os.getpid(),
                    "metadata": dict(metadata or {}),
                },
            )
            self._write_locked(record)
        return OpenResult(task_id=task_id, duplicate=False, opened_at=record.at, phase="new")

    def record_intent(
        self,
        task_id: str,
        *,
        action: str,
        target: str = "",
        effect: str = "",
        ref: str = "",
        generation: int = 0,
        approval: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskIntent:
        """발송 **전** 의도. 여기서부터 이 행동의 운명이 추적된다."""
        record = self._append(
            task_id,
            KIND_INTENT,
            {
                "action": action,
                "target": target,
                "effect": effect,
                "ref": ref,
                "generation": generation,
                "approval": approval,
                "metadata": dict(metadata or {}),
            },
        )
        return TaskIntent(
            seq=record.seq,
            action=action,
            target=target,
            effect=effect,
            consequential=_is_consequential(effect),
            ref=ref,
            generation=generation,
            approval=approval,
        )

    def record_dispatch(self, task_id: str, intent_seq: int, *, via: str = "browser") -> None:
        """보냈다. **의도 없이 발송은 없다**(순서 계약)."""
        with self._locked():
            records = list(self.records())
            intent = self._intent(records, task_id, intent_seq)
            if intent is None:
                raise JournalError(
                    ORDER_VIOLATION,
                    f"발송에 앞서 의도({intent_seq})가 기록돼야 한다",
                    details={"task_id": task_id, "intent_seq": intent_seq},
                )
            if self._dispatch_of(records, task_id, intent_seq) is not None:
                return
            self._write_locked(
                JournalRecord(
                    seq=self._next_seq(),
                    at=self._clock(),
                    kind=KIND_DISPATCH,
                    task_id=task_id,
                    data={"intent_seq": intent_seq, "effect": intent.effect, "via": via},
                )
            )

    def record_outcome(
        self,
        task_id: str,
        intent_seq: int,
        *,
        performed: bool,
        goal_verified: bool = False,
        detail: str = "",
        url_after: str = "",
        generation: int = 0,
    ) -> None:
        """결과를 봤다. **발송 없이 결과는 없다**(순서 계약)."""
        with self._locked():
            records = list(self.records())
            if self._dispatch_of(records, task_id, intent_seq) is None:
                raise JournalError(
                    ORDER_VIOLATION,
                    f"결과에 앞서 발송({intent_seq})이 기록돼야 한다 — 보내지 않은 행동의 결과는 알 수 없다",
                    details={"task_id": task_id, "intent_seq": intent_seq},
                )
            if self._outcome_of(records, task_id, intent_seq) is not None:
                return
            self._write_locked(
                JournalRecord(
                    seq=self._next_seq(),
                    at=self._clock(),
                    kind=KIND_OUTCOME,
                    task_id=task_id,
                    data={
                        "intent_seq": intent_seq,
                        "performed": bool(performed),
                        "goal_verified": bool(goal_verified),
                        "detail": detail,
                        "url_after": url_after,
                        "generation": generation,
                    },
                )
            )

    def finish_task(self, task_id: str, *, status: str, code: str, reason: str = "", actions: int = 0) -> None:
        """작업의 결말. 결말은 한 번만 기록된다(두 번째 호출은 무시한다)."""
        with self._locked():
            records = list(self.records())
            if self._finished(records, task_id) is not None:
                return
            self._write_locked(
                JournalRecord(
                    seq=self._next_seq(),
                    at=self._clock(),
                    kind=KIND_FINISHED,
                    task_id=task_id,
                    data={"status": status, "code": code, "reason": reason, "actions": actions},
                )
            )

    def record_cancel_observed(self, task_id: str, *, mode: str, forced: bool = False) -> None:
        """취소를 **관측**했다 — 협력이었는지(제때 멈췄는지) 시간초과였는지 남긴다."""
        self._append(
            task_id,
            KIND_CANCEL_OBSERVED,
            {"mode": mode, "forced_shutdown": bool(forced), "observed_by_pid": os.getpid()},
        )

    def record_resumed(self, task_id: str, *, must_reobserve: bool, session: str = "", generation: int = 0) -> None:
        self._append(
            task_id,
            KIND_RESUMED,
            {"must_reobserve": bool(must_reobserve), "session": session, "generation": generation, "pid": os.getpid()},
        )

    # ── 취소 ──
    def request_cancel(self, task_id: str, *, reason: str = "user cancelled") -> CancelRequest:
        """취소를 **요청**한다. 첫 요청이 이긴다(두 번째 호출은 그 시각을 그대로 돌려준다).

        이 기록은 곧바로 파일에 있다 — 화면은 같은 파일을 읽으므로 "요청 즉시 표시" 는 별도 통로가
        아니라 이 한 줄이다.
        """
        with self._locked():
            records = list(self.records())
            existing = self._cancel(records, task_id)
            if existing is not None:
                return existing
            record = JournalRecord(
                seq=self._next_seq(),
                at=self._clock(),
                kind=KIND_CANCEL_REQUESTED,
                task_id=task_id,
                data={"reason": reason, "requested_by_pid": os.getpid()},
            )
            self._write_locked(record)
        return CancelRequest(task_id=task_id, requested_at=record.at, reason=reason)

    def cancel_request(self, task_id: str) -> CancelRequest | None:
        return self._cancel(self.records(), task_id)

    # ── 재개 판정 ──
    def resume_plan(
        self,
        task_id: str,
        *,
        approval_is_live: Callable[[str], bool] | None = None,
    ) -> ResumePlan:
        """재시작 뒤 이 작업을 이어받을 수 있는가 — 그리고 **다시 눌러도 되는가**.

        `approval_is_live` 는 승인이 아직 살아 있는지 묻는 콜백이다(task 18 의 승인은 프로세스
        안에 있으므로 재시작을 넘기지 못한다). 콜백이 없으면 **살아 있는 승인은 없다**고 본다 —
        재개가 승인을 다시 요구하는 쪽이 안전 측 기본값이다.
        """
        records = list(self.records(task_id=task_id))
        if not records:
            raise JournalError(UNKNOWN_TASK, f"저널에 없는 작업이다: {task_id}", details={"task_id": task_id})
        cancel = self._cancel(records, task_id)
        finished = self._finished(records, task_id)
        open_intents = self._open_intents(records, task_id)
        # 승인은 **발송 여부와 무관하게** 재시작을 넘기지 못한다(task 18 의 승인은 프로세스 안에 있다).
        # 의도만 적힌 승인도 다시 물어야 한다 — 그 티켓을 든 프로세스는 이미 죽었다.
        stale = tuple(
            intent.approval
            for intent in self._all_intents(records, task_id)
            if intent.approval and not (approval_is_live is not None and approval_is_live(intent.approval))
        )
        unknown = tuple(intent for intent in open_intents if intent.consequential)

        if finished is not None:
            return ResumePlan(
                task_id=task_id,
                phase="finished",
                code=ALREADY_FINISHED,
                reason=f"이미 끝난 작업이다(status={finished.get('status')})",
                replay_allowed=False,
                must_reobserve=False,
                open_intents=open_intents,
                unknown_outcomes=(),
                stale_approvals=(),
                cancel=cancel,
                finished=finished,
                idempotency_scope=_IDEMPOTENCY_SCOPE,
            )
        if cancel is not None:
            return ResumePlan(
                task_id=task_id,
                phase="cancelled",
                code=CANCEL_REQUESTED,
                reason="사용자가 취소를 요청했다 — 재개는 **새 작업**으로만 시작한다",
                replay_allowed=False,
                must_reobserve=True,
                open_intents=open_intents,
                unknown_outcomes=unknown,
                stale_approvals=stale,
                cancel=cancel,
                finished=None,
                idempotency_scope=_IDEMPOTENCY_SCOPE,
            )
        if unknown:
            first = unknown[0]
            return ResumePlan(
                task_id=task_id,
                phase="unknown_outcome",
                code=UNKNOWN_OUTCOME,
                reason=(
                    f"되돌릴 수 없는 행동({first.action} → {first.target or first.ref}, 효과 {first.effect})이 "
                    "발송됐지만 결과가 기록되지 않았다 — 사이트에서 실제로 일어났는지 사람이 확인해야 한다"
                ),
                replay_allowed=False,
                must_reobserve=True,
                open_intents=open_intents,
                unknown_outcomes=unknown,
                stale_approvals=stale,
                cancel=None,
                finished=None,
                idempotency_scope=_IDEMPOTENCY_SCOPE,
            )
        if open_intents:
            first = open_intents[0]
            return ResumePlan(
                task_id=task_id,
                phase="read_only_open",
                code=SAFE_RETRY,
                reason=(
                    f"읽기 행동({first.action} → {first.target or first.ref})이 발송됐지만 결과가 없다 — "
                    "새 관찰 뒤 다시 계획해도 안전하다(사이트 상태를 바꾸지 않는 행동이다)"
                ),
                replay_allowed=True,
                must_reobserve=True,
                open_intents=open_intents,
                unknown_outcomes=(),
                stale_approvals=stale,
                cancel=None,
                finished=None,
                idempotency_scope=_IDEMPOTENCY_SCOPE,
            )
        if stale:
            return ResumePlan(
                task_id=task_id,
                phase="stale_approval",
                code=STALE_APPROVAL,
                reason="이전 프로세스가 받은 승인은 살아 있지 않다 — 사람에게 다시 물어야 한다",
                replay_allowed=False,
                must_reobserve=True,
                open_intents=(),
                unknown_outcomes=(),
                stale_approvals=stale,
                cancel=None,
                finished=None,
                idempotency_scope=_IDEMPOTENCY_SCOPE,
            )
        return ResumePlan(
            task_id=task_id,
            phase="idle",
            code=SAFE_RETRY,
            reason="미결 행동이 없다 — 새 관찰로 이어받아도 안전하다",
            replay_allowed=True,
            must_reobserve=True,
            open_intents=(),
            unknown_outcomes=(),
            stale_approvals=(),
            cancel=None,
            finished=None,
            idempotency_scope=_IDEMPOTENCY_SCOPE,
        )

    # ── 내부 판정 ──
    def _write_locked(self, record: JournalRecord) -> None:
        """`_locked()` 를 **이미 잡은** 상태에서 한 줄 쓴다(판정과 쓰기를 한 임계구역에 묶는다)."""
        _reject_secrets(record.data, where=record.kind)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _find_by_key(records: Sequence[JournalRecord], key: str) -> str | None:
        for record in records:
            if record.kind == KIND_OPENED and str(record.data.get("idempotency_key", "")) == key:
                return record.task_id
        return None

    @staticmethod
    def _opened_at(records: Sequence[JournalRecord], task_id: str) -> float:
        for record in records:
            if record.kind == KIND_OPENED and record.task_id == task_id:
                return record.at
        return 0.0

    @staticmethod
    def _finished(records: Sequence[JournalRecord], task_id: str) -> Mapping[str, Any] | None:
        for record in reversed(records):
            if record.kind == KIND_FINISHED and record.task_id == task_id:
                return dict(record.data)
        return None

    @staticmethod
    def _cancel(records: Sequence[JournalRecord], task_id: str) -> CancelRequest | None:
        for record in records:
            if record.kind == KIND_CANCEL_REQUESTED and record.task_id == task_id:
                return CancelRequest(
                    task_id=task_id,
                    requested_at=record.at,
                    reason=str(record.data.get("reason", "")),
                )
        return None

    @staticmethod
    def _intent(records: Sequence[JournalRecord], task_id: str, intent_seq: int) -> TaskIntent | None:
        for record in records:
            if record.kind == KIND_INTENT and record.task_id == task_id and record.seq == intent_seq:
                return BrowserTaskJournal._intent_of(record)
        return None

    @staticmethod
    def _intent_of(record: JournalRecord) -> TaskIntent:
        effect = str(record.data.get("effect", ""))
        return TaskIntent(
            seq=record.seq,
            action=str(record.data.get("action", "")),
            target=str(record.data.get("target", "")),
            effect=effect,
            consequential=_is_consequential(effect),
            ref=str(record.data.get("ref", "")),
            generation=int(cast("int", record.data.get("generation") or 0)),
            approval=str(record.data.get("approval", "")),
        )

    @staticmethod
    def _dispatch_of(records: Sequence[JournalRecord], task_id: str, intent_seq: int) -> JournalRecord | None:
        for record in records:
            if record.kind == KIND_DISPATCH and record.task_id == task_id and record.intent_seq == intent_seq:
                return record
        return None

    @staticmethod
    def _outcome_of(records: Sequence[JournalRecord], task_id: str, intent_seq: int) -> JournalRecord | None:
        for record in records:
            if record.kind == KIND_OUTCOME and record.task_id == task_id and record.intent_seq == intent_seq:
                return record
        return None

    def _all_intents(self, records: Sequence[JournalRecord], task_id: str) -> tuple[TaskIntent, ...]:
        return tuple(
            self._intent_of(record) for record in records if record.kind == KIND_INTENT and record.task_id == task_id
        )

    def _open_intents(self, records: Sequence[JournalRecord], task_id: str) -> tuple[TaskIntent, ...]:
        """발송됐지만 결과가 기록되지 않은 의도 — 재개 판정의 유일한 입력이다."""
        open_items: list[TaskIntent] = []
        for record in records:
            if record.kind != KIND_INTENT or record.task_id != task_id:
                continue
            dispatch = self._dispatch_of(records, task_id, record.seq)
            if dispatch is None or self._outcome_of(records, task_id, record.seq) is not None:
                continue
            open_items.append(self._intent_of(record))
        return tuple(open_items)


__all__ = [
    "ALREADY_FINISHED",
    "BrowserTaskJournal",
    "CONSEQUENTIAL_EFFECTS",
    "CANCEL_REQUESTED",
    "CANCELLED_BEFORE_START",
    "CancelRequest",
    "DUPLICATE_REQUEST",
    "DEFAULT_CANCEL_GRACE_SECONDS",
    "FORBIDDEN_KEYS",
    "JOURNAL_ENV",
    "JOURNAL_UNAVAILABLE",
    "JournalError",
    "JournalRecord",
    "KIND_CANCEL_OBSERVED",
    "KIND_CANCEL_REQUESTED",
    "KIND_DISPATCH",
    "KIND_FINISHED",
    "KIND_INTENT",
    "KIND_OPENED",
    "KIND_OUTCOME",
    "KIND_RESUMED",
    "OpenResult",
    "ORDER_VIOLATION",
    "REPLAY_REFUSED",
    "ResumePlan",
    "SAFE_RETRY",
    "SCHEMA",
    "SECRET_IN_RECORD",
    "STALE_APPROVAL",
    "STALE_SESSION",
    "TaskIntent",
    "UNKNOWN_OUTCOME",
    "UNKNOWN_TASK",
    "journal_path",
]
