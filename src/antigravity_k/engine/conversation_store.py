"""Authoritative conversation history store with revision CAS (CTX-01).

Server-owned message history. Clients send new turns + expected revision only;
append/compact advance revision via compare-and-set. Two concurrent writers
never silently overwrite — losers get stale_conversation_revision (HTTP 409).

CR-01 identity contract:
- The storage key of a conversation is the full SHA-256 hex digest of the raw
  UTF-8 ``project_id`` / ``conversation_id`` strings (``v2/<sha(project)>/
  <sha(conversation)>.json``). Raw ids are never normalised, substituted, or
  truncated, so ``a.b`` and ``a_b`` — or ``Conv`` and ``conv`` on a
  case-insensitive filesystem — stay distinct conversations.
- Every read verifies that the embedded ids of the stored record exactly match
  the requested ids. Corrupt or mismatched bytes raise
  ``ConversationIntegrityError`` instead of degrading to an empty conversation.
- Until the one-time legacy migration has produced its completion marker
  (``migration_v2.json``), reads and writes fail with
  ``ConversationStorageMigrationRequiredError`` so new writes cannot fork the
  data set before it is verified.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, Mapping, cast

from antigravity_k.api.contracts.conversation import ConversationSnapshot
from antigravity_k.api.contracts.errors import (
    ConversationHistoryCorruptError,
    ConversationHistoryQuotaExceededError,
    ConversationHistoryUnavailableError,
    ConversationIntegrityError,
    ConversationNotFoundError,
    ConversationStorageMigrationRequiredError,
    InvalidConversationRevisionError,
    StaleConversationRevisionError,
)
from antigravity_k.engine.context_summary import summarize_messages
from antigravity_k.engine.conversation_journal import (
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_SUFFIX,
    ConversationJournal,
    ConversationJournalCorruptError,
    ConversationJournalError,
    ConversationJournalSchemaMismatchError,
    JournalEvent,
    base_event_from_view,
    read_deletion_marker,
    replay,
    write_deletion_marker,
)
from antigravity_k.engine.conversation_retention import (
    JournalRetentionPolicy,
    format_mb,
    resolve_policy,
)
from antigravity_k.engine.summary_memory import (
    CARRIED_SUMMARY_MAX_CHARS,
    SummaryMemory,
    carryover_prose,
    record_generation,
    update_from_messages,
)
from antigravity_k.engine.tokenizer import TokenEstimator

logger = logging.getLogger("antigravity_k.engine.conversation_store")

MessageRole = Literal["user", "assistant", "system", "tool"]

_DEFAULT_RETAIN_TAIL: Final[int] = 6
# EX-05 / Decision A: bound in-memory (and on-disk rewritten) history so long
# chats cannot grow RSS without bound. 0 disables auto-compact.
_DEFAULT_SOFT_MAX_MESSAGES: Final[int] = 64
# NX-02 retention: `store_usage()` 가 돌려주는 "가장 큰 journal" 목록 크기(관측/회수 단서).
_USAGE_TOP_N: Final[int] = 10
_SUMMARY_MESSAGE_ID: Final[str] = "msg_summary"
# NX-02: materialized-view export schema (original history export contract).
HISTORY_EXPORT_SCHEMA: Final[str] = "agk.conv-export.v1"
VIEW_SCHEMA_VERSION: Final[str] = "agk.conv-view.v1"


def _soft_max_messages() -> int:
    """Return soft max message count (0 = disable auto-compact on append)."""
    raw = os.environ.get("AGK_CONVERSATION_SOFT_MAX_MESSAGES")
    if raw is None or raw.strip() == "":
        return _DEFAULT_SOFT_MAX_MESSAGES
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_SOFT_MAX_MESSAGES


# CR-01: versioned identity layout + one-time migration marker.
_IDENTITY_SCHEMA_VERSION: Final[str] = "v2"
MIGRATION_MARKER_NAME: Final[str] = "migration_v2.json"
_IGNORED_STORAGE_ENTRIES: Final[frozenset[str]] = frozenset({MIGRATION_MARKER_NAME, ".cas.lock", ".DS_Store"})


def conversation_identity_digest(value: str) -> str:
    """Return the full SHA-256 hex digest of a raw UTF-8 identifier."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def conversation_storage_relative_path(project_id: str, conversation_id: str) -> Path:
    """Return the storage-relative CR-01 v2 path for raw ids.

    ``v2/<sha256(project_id)>/<sha256(conversation_id)>.json``. The digest is
    the key; the raw ids are re-verified from the record body on every read.
    """
    return (
        Path(_IDENTITY_SCHEMA_VERSION)
        / conversation_identity_digest(project_id)
        / f"{conversation_identity_digest(conversation_id)}.json"
    )


@dataclass(frozen=True)
class ConversationMessage:
    """Single stored message with stable id for retained-range tracking."""

    id: str
    role: MessageRole
    content: str
    created_at: float
    provenance: str = "append"  # append | summary | fork | system

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConversationMessage:
        role = str(data.get("role") or "user")
        if role not in ("user", "assistant", "system", "tool"):
            role = "user"
        return cls(
            id=str(data.get("id") or _new_message_id()),
            role=role,  # type: ignore[arg-type]
            content=str(data.get("content") or ""),
            created_at=float(data.get("created_at") or time.time()),
            provenance=str(data.get("provenance") or "append"),
        )

    def as_chat_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content, "id": self.id}


@dataclass
class ConversationRecord:
    conversation_id: str
    project_id: str
    revision: int = 0
    messages: list[ConversationMessage] = field(default_factory=list)
    summary: str | None = None
    retained_message_ids: tuple[str, ...] = ()
    forked_from: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # NX-01: structured constraints carried across compaction generations.
    # Records written before NX-01 simply have no ``memory`` key.
    memory: SummaryMemory = field(default_factory=SummaryMemory)
    # NX-02: journal sequence this view was materialized from, and whether the
    # originals for this conversation are known to be incomplete.
    journal_seq: int = 0
    history_incomplete: bool = False

    def snapshot(self) -> ConversationSnapshot:
        retained = self.retained_message_ids or tuple(m.id for m in self.messages)
        return ConversationSnapshot(
            conversation_id=self.conversation_id,
            project_id=self.project_id,
            revision=self.revision,
            message_count=len(self.messages),
            summary=self.summary,
            retained_message_ids=retained,
        )

    def prompt_messages(self) -> list[dict[str, str]]:
        """History assembled for the next model call (authoritative)."""
        out: list[dict[str, str]] = []
        for msg in self.messages:
            out.append({"role": msg.role, "content": msg.content})
        return out

    def estimate_tokens(self) -> int:
        return TokenEstimator.estimate_messages(self.prompt_messages())

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "messages": [m.to_dict() for m in self.messages],
            "summary": self.summary,
            "retained_message_ids": list(self.retained_message_ids),
            "forked_from": self.forked_from,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "memory": self.memory.to_dict(),
            "journal_seq": self.journal_seq,
            "history_incomplete": self.history_incomplete,
            "view_schema": VIEW_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConversationRecord:
        msgs = [ConversationMessage.from_dict(m) for m in (data.get("messages") or []) if isinstance(m, Mapping)]
        retained_raw = data.get("retained_message_ids") or []
        retained = tuple(str(x) for x in retained_raw) if isinstance(retained_raw, list) else ()
        return cls(
            conversation_id=str(data.get("conversation_id") or ""),
            project_id=str(data.get("project_id") or ""),
            revision=int(data.get("revision") or 0),
            messages=msgs,
            summary=data.get("summary") if isinstance(data.get("summary"), str) else None,
            retained_message_ids=retained,
            forked_from=data.get("forked_from") if isinstance(data.get("forked_from"), str) else None,
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            memory=SummaryMemory.from_dict(data.get("memory") if isinstance(data.get("memory"), Mapping) else None),
            journal_seq=int(data.get("journal_seq") or 0),
            history_incomplete=bool(data.get("history_incomplete")),
        )


def _coerce_role(value: Any) -> MessageRole:
    role = str(value or "user")
    if role not in ("user", "assistant", "system", "tool"):
        return "user"
    return cast(MessageRole, role)


def _new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


def _new_conversation_id() -> str:
    return f"conv_{uuid.uuid4().hex[:12]}"


class ConversationStore:
    """Thread-safe authoritative conversation store (revision CAS).

    Implements ``ConversationRevisionStore`` protocol used by ARC-01 resolvers.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._records: dict[tuple[str, str], ConversationRecord] = {}
        if storage_dir is None:
            storage_dir = os.environ.get("AGK_CONVERSATION_STORE_DIR") or os.path.join(
                os.path.expanduser("~"), ".antigravity", "conversations"
            )
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # VAL-02: 다중 프로세스 writer 간 원자성 — 프로세스 공유 flock(CTX-01 계약
        # "두 동시 writer는 침묵 중 덮어쓰지 않는다"를 프로세스 경계에서도 유지).
        # 단일 프로세스 스레드 경쟁은 기존 threading.RLock으로 충분하다.
        self._flock_path = self._storage_dir / ".cas.lock"
        self._flock_fd: int | None = None
        # NX-02: 같은 스레드가 중첩 호출(예: export → history_state)을 하면
        # 별도 fd 로 flock 을 다시 잡을 때 자기 자신과 교착한다. 보유 스레드를
        # 기억해 재진입은 그대로 통과시키고, 해제는 최외곽에서만 한다.
        self._flock_owner: int | None = None
        self._flock_depth = 0
        # CR-01: legacy layout detection is memoised per process; the operator
        # runs the migration with the service stopped.
        self._layout_checked = False
        self._legacy_paths: tuple[Path, ...] = ()
        # NX-02 retention: soft cap 경고를 대화당 한 번만 남기기 위한 기억.
        self._soft_cap_warned: set[tuple[str, str]] = set()
        # F1(flush 배치): flock 임계 구역 안에서 읽은 저널 꼬리의 한 칸짜리 기억.
        # 구역 **밖으로 새지 않는다** — 구역에 들어갈 때마다 비운다(`_cross_process_lock`).
        self._tail_memo: tuple[str, Any] | None = None
        # F2(view 신선도): 밀린 view 재작성의 장부 — 값은 “아직 쓰지 않은 커밋 수”다.
        # 판정은 시퀀스로 하고(계약 C-2), 따라잡기는 메모리 레코드로 한다(C-4).
        self._view_lag: dict[tuple[str, str], int] = {}

    # ── CR-01 identity / migration state ────────────────────────────────

    def migration_marker_path(self) -> Path:
        """Path of the one-time migration completion marker."""
        return self._storage_dir / MIGRATION_MARKER_NAME

    def migration_completed(self) -> bool:
        """True when a valid completion marker exists for the v2 layout."""
        marker = self.migration_marker_path()
        if not marker.is_file():
            return False
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            isinstance(data, dict) and data.get("layout") == _IDENTITY_SCHEMA_VERSION and data.get("completed") is True
        )

    def legacy_storage_paths(self) -> tuple[Path, ...]:
        """Return pre-v2 record files still present under the storage root.

        Path names are never used to reconstruct ids; callers must read the
        record body for the authoritative ids. Migration tooling consumes this.
        """
        if not self._storage_dir.is_dir():
            return ()
        found: list[Path] = []
        for entry in sorted(self._storage_dir.iterdir()):
            name = entry.name
            if name in _IGNORED_STORAGE_ENTRIES or name.startswith("."):
                continue
            if entry.is_dir():
                if name == _IDENTITY_SCHEMA_VERSION:
                    continue
                found.extend(sorted(p for p in entry.rglob("*.json") if p.is_file()))
            elif entry.is_file() and entry.suffix == ".json":
                found.append(entry)
        return tuple(found)

    def storage_layout_state(self) -> str:
        """Return ``v2`` or ``legacy_requires_migration`` for this storage root."""
        if not self._layout_checked:
            self._legacy_paths = self.legacy_storage_paths()
            self._layout_checked = True
        if not self._legacy_paths:
            return _IDENTITY_SCHEMA_VERSION
        return _IDENTITY_SCHEMA_VERSION if self.migration_completed() else "legacy_requires_migration"

    def refresh_storage_layout(self) -> str:
        """Drop the memoised layout scan (tests / post-migration reload)."""
        self._layout_checked = False
        self._legacy_paths = ()
        return self.storage_layout_state()

    def _assert_storage_ready(self) -> None:
        """Fail closed while unmigrated legacy records exist."""
        if self.storage_layout_state() == "legacy_requires_migration":
            raise ConversationStorageMigrationRequiredError(
                detail=(
                    "Legacy conversation files require the one-time v2 migration before reads or writes are served"
                ),
                context={
                    "storage_dir": str(self._storage_dir),
                    "legacy_record_count": len(self._legacy_paths),
                    "marker_path": str(self.migration_marker_path()),
                    "migration_script": "scripts/migrate_conversation_storage.py",
                },
            )

    # ── ConversationRevisionStore protocol ──────────────────────────────

    @contextmanager
    def _cross_process_lock(self) -> Generator[None, None, None]:
        """프로세스 간 CAS 원자성을 위한 flock (스레드 락은 self._lock이 담당).

        NX-02: 같은 스레드의 재진입은 이미 보유한 flock 을 그대로 사용한다
        (flock 은 open-file-description 단위라 같은 프로세스에서 다시 잡으면
        자기 자신과 교착한다).
        """
        import fcntl

        thread_id = threading.get_ident()
        if self._flock_depth > 0 and self._flock_owner == thread_id:
            self._flock_depth += 1
            try:
                yield
            finally:
                self._flock_depth -= 1
            return
        self._flock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._flock_path), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self._flock_owner = thread_id
        self._flock_depth = 1
        self._flock_fd = fd
        # F1: 새 임계 구역이다 — 이전 구역의 꼬리 기억은 다른 프로세스의 쓰기 때문에 낡았을 수 있다.
        self._tail_memo = None
        try:
            yield
        finally:
            self._flock_depth = 0
            self._flock_owner = None
            self._flock_fd = None
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextmanager
    def _journal_errors(self) -> Generator[None, None, None]:
        """NX-02: journal 실패를 타입이 지정된 API 오류로 변환한다.

        원본 이력 손상을 \"원문 없음\"으로 낮추지 않는다(ADR-DAT-02). 손상은
        줄 번호/오프셋과 함께 409, IO 실패·상위 schema 는 503으로 보고한다.
        """
        try:
            yield
        except ConversationJournalSchemaMismatchError as exc:
            raise ConversationHistoryUnavailableError(
                detail="Conversation journal was written by a newer schema this build cannot read",
                context={"reason": "schema_mismatch", "journal_schema": JOURNAL_SCHEMA_VERSION},
            ) from exc
        except ConversationJournalCorruptError as exc:
            raise ConversationHistoryCorruptError(
                detail="Committed conversation history is corrupt (line/offset reported)",
                context={
                    "reason": exc.reason,
                    "journal_line": exc.line_no,
                    "journal_offset": exc.offset,
                },
            ) from exc
        except ConversationJournalError as exc:
            raise ConversationHistoryUnavailableError(
                detail="Conversation journal could not be read or written",
                context={"reason": type(exc).__name__},
            ) from exc

    def _refresh_latest(
        self, project_id: str, conversation_id: str, *, flush_deferred: bool = False
    ) -> ConversationRecord | None:
        """FR-05/RP-05: 캐시를 디스크 진실 원천과 동기화한 뒤 반환한다.

        ``self._lock``과 ``_cross_process_lock``을 이미 보유한 상태에서만
        호출한다. 파일이 삭제됐으면 캐시도 무효화한다(삭제된 대화를 되살리지
        않는다).

        CR-01: 손상된 JSON이나 다른 식별자의 레코드는 조용히 None/빈 대화로
        낮추지 않고 ``ConversationIntegrityError``로 전파한다.

        NX-02: view 는 journal 의 파생물이다. view 가 없으면 journal 로 재생성하고,
        journal 이 view 보다 나중에 쓰였으면(view 지연/미커밋 tail) 재생성한다.
        """
        key = (project_id, conversation_id)
        journal = self._journal(project_id, conversation_id)
        if self.deletion_marker(project_id=project_id, conversation_id=conversation_id) is not None or (
            journal.exists() and self._journal_tail(journal).deleted
        ):
            self._records.pop(key, None)
            self._view_lag.pop(key, None)
            return None
        disk_record = self._read_record(project_id, conversation_id)
        if disk_record is None:
            cached = self._records.get(key)
            if journal.exists() and cached is not None and cached.journal_seq == self._journal_tail(journal).seq:
                if flush_deferred:
                    self._persist(cached)
                    self._view_lag.pop(key, None)
                return cached
            rebuilt = self._materialize_from_journal(project_id, conversation_id)
            if rebuilt is not None:
                self._records[key] = rebuilt
                self._persist(rebuilt)
                self._view_lag.pop(key, None)
                logger.warning(
                    "Conversation view was missing and rebuilt from the journal (%s/%s, seq=%s)",
                    project_id,
                    conversation_id,
                    rebuilt.journal_seq,
                )
                return rebuilt
            self._records.pop(key, None)
            self._view_lag.pop(key, None)
            return None
        if journal.exists():
            self._ensure_journal_base(disk_record)
            journal = self._journal(project_id, conversation_id)
            if self._view_is_behind(journal, disk_record):
                cached = self._records.get(key)
                if cached is not None and cached.journal_seq == self._journal_tail(journal).seq:
                    # 계약 F2-C4: 밀린 것은 **view 파일**이지 기록이 아니다.
                    # 여기서 `_reconcile_view_with_journal`(저널 전체 재생)로 가면 view 스로틸이
                    # 이득이 아니라 회귀가 된다 — 실측: 3회에 1회로 미루면 재생이 1.17회/미룸 붙었다.
                    disk_record = cached
                else:
                    disk_record = self._reconcile_view_with_journal(project_id, conversation_id, disk_record)
        self._records[key] = disk_record
        if flush_deferred:
            # 계약 F2-C7: 읽기는 밀린 view 를 수렴시킨다(지연 창은 읽기를 넘지 않는다).
            self._flush_view(disk_record)
        return disk_record

    # ── NX-02: journal (originals) ──────────────────────────────────────

    def journal_path(self, *, project_id: str, conversation_id: str) -> Path:
        """Append-only original-history journal path for one conversation."""
        return self._path_for(project_id, conversation_id).with_suffix(JOURNAL_SUFFIX)

    def _journal_tail(self, journal: ConversationJournal, *, fresh: bool = False) -> Any:
        """커밋 임계 구역 안에서 저널 꼬리는 **한 번만** 읽는다(flush 배치 F1).

        이 프로세스가 그 구역 안에서 저널에 쓰지 않았다면 꼬리는 변하지 않는다 — 그래서
        같은 구역의 읽기 지점들(`_authoritative_record` · `_reconcile_view_with_journal` ·
        `_commit_event` · `ConversationJournal.append`)이 같은 값을 나눠 쓴다. 우리가 방금
        썼거나(`fresh=True`) 구역이 바뀌었으면(진입 시 초기화) 기억을 버린다.
        """
        if not fresh and self._tail_memo is not None and self._tail_memo[0] == str(journal.path):
            return self._tail_memo[1]
        tail = journal.tail()
        self._tail_memo = (str(journal.path), tail)
        return tail

    def _view_refresh_policy(self) -> tuple[str, int]:
        """계약 F2-C6: 기본은 `immediate` — 노브를 켠 실행만 view 재작성을 지연한다."""
        raw = (os.environ.get("AGK_CONVERSATION_VIEW_REFRESH") or "immediate").strip().lower()
        if raw != "coalesced":
            return "immediate", 0
        try:
            max_lag = int((os.environ.get("AGK_CONVERSATION_VIEW_REFRESH_MAX_LAG") or "8").strip())
        except ValueError:
            max_lag = 8
        return "coalesced", max(1, max_lag)

    def _persist_view_or_defer(self, record: ConversationRecord) -> None:
        """계약 F2-C3: view 는 캐시다 — 지연 창은 **유한**하고 기본은 지연 없음."""
        key = (record.project_id, record.conversation_id)
        mode, max_lag = self._view_refresh_policy()
        lag = self._view_lag.get(key, 0) + 1
        self._view_lag[key] = lag
        if mode == "immediate" or lag >= max_lag:
            self._persist(record)
            self._view_lag.pop(key, None)

    def _flush_view(self, record: ConversationRecord) -> None:
        """계약 F2-C4/C7: 밀린 view 를 **저널 재생 없이** 메모리 레코드로 따라잡는다."""
        key = (record.project_id, record.conversation_id)
        if key in self._view_lag:
            self._persist(record)
            self._view_lag.pop(key, None)

    def flush_views(self) -> None:
        """계약 F2-C5: 밀린 view 는 프로세스 수명을 넘지 않는다(writer-only 프로세스의 수렴점)."""
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            pending = sorted(self._view_lag)
            for project_id, conversation_id in pending:
                self._refresh_latest(project_id, conversation_id, flush_deferred=True)

    def _journal(self, project_id: str, conversation_id: str) -> ConversationJournal:
        return ConversationJournal(self.journal_path(project_id=project_id, conversation_id=conversation_id))

    def deletion_marker(self, *, project_id: str, conversation_id: str) -> dict[str, Any] | None:
        """Deletion marker for this id (``None`` when the id was never deleted)."""
        return read_deletion_marker(self._path_for(project_id, conversation_id))

    def _view_is_behind(self, journal: ConversationJournal, record: ConversationRecord) -> bool:
        """계약 F2-C2: view 가 뒤처졌는지는 **시퀀스로** 판정한다(mtime 이 아니다).

        종전 판정은 `journal mtime > view mtime` 이었다. 그 판정은 복원·동기화 도구가 옛 view 를
        **새 mtime 으로** 놓는 순간 거짓이 된다 — 실측: 저널 tail seq 3 인데 view 를 seq 1 내용 +
        새 mtime 으로 놓으면 읽기가 revision 1 을 돌려줬다(커밋된 턴 2개를 놓쳤다).
        nx10/fsync2/probe-view-staleness-output.json.
        """
        try:
            tail = self._journal_tail(journal)
        except OSError:
            return True
        return record.journal_seq != tail.seq

    def _materialize_from_journal(self, project_id: str, conversation_id: str) -> ConversationRecord | None:
        """Rebuild the bounded view from committed journal events (deterministic)."""
        journal = self._journal(project_id, conversation_id)
        if not journal.exists():
            return None
        with self._journal_errors():
            if journal.tail().truncated_tail:
                journal.rewrite_without_truncated_tail()
            events, _truncated = journal.read()
        if not events:
            return None
        state = replay(events)
        if state.deleted:
            return None
        messages = [
            ConversationMessage(
                id=str(message.get("id") or _new_message_id()),
                role=_coerce_role(message.get("role")),
                content=str(message.get("content") or ""),
                created_at=float(message.get("created_at") or time.time()),
                provenance=str(message.get("provenance") or "append"),
            )
            for message in state.messages
        ]
        return ConversationRecord(
            conversation_id=conversation_id,
            project_id=project_id,
            revision=state.revision,
            messages=messages,
            summary=state.summary,
            retained_message_ids=tuple(message.id for message in messages),
            memory=SummaryMemory.from_dict(state.memory),
            journal_seq=state.seq,
            history_incomplete=state.history_incomplete,
        )

    def _reconcile_view_with_journal(
        self, project_id: str, conversation_id: str, record: ConversationRecord
    ) -> ConversationRecord:
        """Journal 이 앞서면(또는 view 가 미커밋 tail 을 포함하면) 재생성한다."""
        journal = self._journal(project_id, conversation_id)
        if self._journal_tail(journal).truncated_tail:
            journal.rewrite_without_truncated_tail()
        rebuilt = self._materialize_from_journal(project_id, conversation_id)
        if rebuilt is None or rebuilt.journal_seq == record.journal_seq:
            return record
        logger.warning(
            "Conversation view rebuilt from journal (%s/%s): view_seq=%s journal_seq=%s",
            project_id,
            conversation_id,
            record.journal_seq,
            rebuilt.journal_seq,
        )
        self._persist(rebuilt)
        return rebuilt

    def _ensure_journal_base(self, record: ConversationRecord) -> None:
        """NX-02 migration: snapshot an existing view into a fresh journal (once).

        Idempotent: the journal is only created when it does not exist yet. The
        base event carries the current view, so replay reproduces it exactly;
        originals are marked incomplete when the view already carries a summary.
        """
        journal = self._journal(record.project_id, record.conversation_id)
        if journal.exists():
            return
        event = base_event_from_view(record.to_dict())
        with self._journal_errors():
            committed = journal.append(event)
        record.journal_seq = committed.seq
        record.history_incomplete = record.history_incomplete or bool(event["history_incomplete"])
        self._persist(record)

    def backfill_journal(
        self,
        *,
        project_id: str,
        conversation_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """NX-02 migration: create a journal base event from an existing view once.

        Idempotent (a journal that already exists is left untouched) and it never
        invents originals: a view that already carries a summary is recorded as
        ``history_incomplete`` so the missing originals stay visible.
        """
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            journal = self._journal(project_id, conversation_id)
            journal_path = self.journal_path(project_id=project_id, conversation_id=conversation_id)
            if journal.exists():
                return {
                    "action": "already_present",
                    "journal_path": str(journal_path),
                    "journal_seq": journal.tail().seq,
                    "history_incomplete": journal.tail().history_incomplete,
                }
            record = self._read_record(project_id, conversation_id)
            if record is None:
                return {
                    "action": "no_record",
                    "journal_path": str(journal_path),
                    "journal_seq": 0,
                    "history_incomplete": False,
                }
            incomplete = bool(record.summary) or any(message.provenance == "summary" for message in record.messages)
            planned = {
                "action": "would_create" if dry_run else "created",
                "journal_path": str(journal_path),
                "message_count": len(record.messages),
                "history_incomplete": incomplete,
            }
            if dry_run:
                return planned
            self._ensure_journal_base(record)
            return {**planned, "journal_path": str(journal_path), "journal_seq": record.journal_seq}

    def _authoritative_record(self, project_id: str, conversation_id: str) -> ConversationRecord | None:
        """Record for a mutation: revision/seq follow the committed journal."""
        record = self._refresh_latest(project_id, conversation_id)
        journal = self._journal(project_id, conversation_id)
        if not journal.exists():
            return record
        tail = self._journal_tail(journal)
        if tail.truncated_tail:
            journal.rewrite_without_truncated_tail()
            tail = self._journal_tail(journal, fresh=True)
        if tail.deleted:
            return None
        if record is None or record.journal_seq != tail.seq:
            rebuilt = self._materialize_from_journal(project_id, conversation_id)
            if rebuilt is not None:
                return rebuilt
        return record

    def _assert_journal_capacity(self, record: ConversationRecord, journal: ConversationJournal) -> None:
        """ADR-DAT-02 Context 8: 정한 byte 한계를 넘으면 **쓰기를 거절**한다(지우지 않는다).

        조용한 prune 은 ADR 이 금지한다 — 자동 삭제를 넣으면 "원본을 보존한다"는 NX-02 계약
        자체가 깨진다. 대신 한계에 닫으면 507 로 알리고 기존 데이터는 그대로 둔다.
        """
        policy = resolve_policy()
        if policy.soft_cap_bytes <= 0 and not policy.enforced:
            return
        size = journal.size_bytes()
        if size <= 0:
            return
        verdict = policy.verdict(size)
        if verdict == "ok":
            return
        if verdict == "soft_exceeded":
            self._warn_soft_cap(record, size, policy)
            return
        raise ConversationHistoryQuotaExceededError(
            detail=(
                "Conversation history (journal) reached its hard cap — append refused; existing history is preserved"
            ),
            context={
                "project_id": record.project_id,
                "conversation_id": record.conversation_id,
                "journal_bytes": size,
                "soft_cap_bytes": policy.soft_cap_bytes,
                "hard_cap_bytes": policy.hard_cap_bytes,
                "remedy": (
                    "raise AGK_CONVERSATION_JOURNAL_HARD_CAP_MB, or reclaim storage "
                    "(store_usage() reports the largest journals); nothing was deleted"
                ),
            },
        )

    def _warn_soft_cap(self, record: ConversationRecord, size: int, policy: JournalRetentionPolicy) -> None:
        """soft cap 경고 — 대화당 한 번만 남긴다(턴마다 같은 줄을 쓰면 로그가 쓸모없어진다)."""
        key = (record.project_id, record.conversation_id)
        with self._lock:
            if key in self._soft_cap_warned:
                return
            self._soft_cap_warned.add(key)
        logger.warning(
            "Conversation journal above soft cap: project=%s conversation=%s size=%s soft_cap=%s "
            "hard_cap=%s (writes continue; no automatic pruning — see ADR-DAT-02 Context 8)",
            record.project_id,
            record.conversation_id,
            format_mb(size),
            format_mb(policy.soft_cap_bytes),
            format_mb(policy.hard_cap_bytes),
        )

    def store_usage(self) -> dict[str, Any]:
        """저장소 전체 사용량 관측(NX-02 retention) — 요청 시에만 실행한다.

        매 append 마다 전체를 스캔하면 O(대화 수) 가 쓰기 경로에 붙는다. 한계 집행은 대화
        하나당 journal 크기로 하고(쓰기 경로), 저장소 전체 사용량은 운영자가 이 메서드로 본다
        (한계 초과 대화를 찾아 회수하는 것이 목적).
        """
        policy = resolve_policy()
        total_bytes = 0
        journals: list[tuple[int, str]] = []
        for path in sorted(self._storage_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:  # pragma: no cover - 스캔 중 사라진 파일은 사용량에서 빠진다
                continue
            total_bytes += size
            if path.name.endswith(JOURNAL_SUFFIX):
                journals.append((size, path.relative_to(self._storage_dir).as_posix()))
        journals.sort(key=lambda entry: (-entry[0], entry[1]))
        over_hard = [entry for entry in journals if policy.verdict(entry[0]) == "hard_exceeded"]
        over_soft = [entry for entry in journals if policy.verdict(entry[0]) in {"soft_exceeded", "hard_exceeded"}]
        return {
            "storage_dir": str(self._storage_dir),
            "total_bytes": total_bytes,
            "journal_count": len(journals),
            "largest_journals": [{"path": relative, "bytes": size} for size, relative in journals[:_USAGE_TOP_N]],
            "journals_over_soft_cap": len(over_soft),
            "journals_over_hard_cap": len(over_hard),
            "policy": policy.to_dict(),
        }

    def _commit_event(self, record: ConversationRecord, payload: dict[str, Any]) -> JournalEvent:
        """Commit one logical mutation to the journal, then refresh the view.

        The journal line + fsync is the commit point. If the view write fails the
        event stays committed (the view is rebuilt from the journal later), and
        the failure is propagated to the caller.
        """
        journal = self._journal(record.project_id, record.conversation_id)
        self._assert_journal_capacity(record, journal)
        with self._journal_errors():
            tail = self._journal_tail(journal)
            if tail.truncated_tail:
                journal.rewrite_without_truncated_tail()
                tail = self._journal_tail(journal, fresh=True)
            event = journal.append(
                {**payload, "project_id": record.project_id, "conversation_id": record.conversation_id},
                tail=tail,
            )
        # F1: 방금 우리가 저널에 썼다 — 이 구역의 꼬리 기억은 낡았다.
        self._tail_memo = None
        record.journal_seq = event.seq
        record.history_incomplete = record.history_incomplete or event.history_incomplete
        # 계약 F2-C3: 기본(immediate)에서는 종전과 똑같이 즉시 쓴다.
        self._persist_view_or_defer(record)
        return event

    def _assert_id_reusable(self, project_id: str, conversation_id: str) -> None:
        """NX-02: a deleted id is never recreated implicitly."""
        if self.deletion_marker(project_id=project_id, conversation_id=conversation_id) is not None:
            raise ConversationNotFoundError(
                detail="Conversation was deleted and its id is not reused",
                context={"project_id": project_id, "conversation_id": conversation_id, "reason": "deleted"},
            )

    def original_history(
        self,
        *,
        project_id: str,
        conversation_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Original (pre-compaction) history from the journal.

        This is the recovery/export read surface; the prompt view lives in
        ``get()``/``snapshot()``. Deleted conversations return an empty list.
        """
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            journal = self._journal(project_id, conversation_id)
            if not journal.exists():
                return []
            with self._journal_errors():
                if journal.tail().truncated_tail:
                    journal.rewrite_without_truncated_tail()
                events, _truncated = journal.read()
            state = replay(events)
            if state.deleted:
                return []
            originals = [dict(message) for message in state.originals]
            start = max(0, int(offset))
            sliced = originals[start:] if limit is None else originals[start : start + max(0, int(limit))]
            return sliced

    def history_state(self, *, project_id: str, conversation_id: str) -> dict[str, Any]:
        """Observable state of originals vs view (diagnostics/UX, no mutation)."""
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            view_path = self._path_for(project_id, conversation_id)
            journal = self._journal(project_id, conversation_id)
            marker = read_deletion_marker(view_path)
            view_exists = view_path.is_file()
            if not journal.exists() and not view_exists:
                return {
                    "exists": False,
                    "deleted": marker is not None,
                    "content_erased": bool(marker is not None) and not view_exists and not journal.exists(),
                    "journal_seq": 0,
                    "revision": 0,
                    "original_message_count": 0,
                    "view_message_count": 0,
                    "history_incomplete": False,
                    "truncated_tail": False,
                }
            with self._journal_errors():
                events, truncated = journal.read() if journal.exists() else ([], False)
            state = replay(events)
            record = self._read_record(project_id, conversation_id)
            return {
                "exists": True,
                "deleted": state.deleted or marker is not None,
                "content_erased": state.deleted or (marker is not None and not journal.exists() and not view_exists),
                "journal_seq": state.seq,
                "revision": state.revision if events else (record.revision if record else 0),
                "original_message_count": len(state.originals),
                "view_message_count": len(record.messages) if record else len(state.messages),
                "history_incomplete": state.history_incomplete,
                "truncated_tail": truncated,
            }

    def export_original_history(self, *, project_id: str, conversation_id: str) -> dict[str, Any]:
        """Export payload for support/backup tooling (originals + provenance)."""
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            self._refresh_latest(project_id, conversation_id, flush_deferred=True)
            journal = self._journal(project_id, conversation_id)
            state = self.history_state(project_id=project_id, conversation_id=conversation_id)
            messages = self.original_history(project_id=project_id, conversation_id=conversation_id)
            return {
                "schema": HISTORY_EXPORT_SCHEMA,
                "project_id": project_id,
                "conversation_id": conversation_id,
                "exported_at": time.time(),
                "revision": state["revision"],
                "journal_seq": state["journal_seq"],
                "journal_sha256": journal.fingerprint(),
                "journal_schema": JOURNAL_SCHEMA_VERSION,
                "history_incomplete": state["history_incomplete"],
                "deleted": state["deleted"],
                "message_count": len(messages),
                "messages": messages,
            }

    def delete_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int | None = None,
    ) -> bool:
        """NX-02: delete originals and the view together.

        Order (all under the store locks): commit a ``delete`` event, write a
        durable deletion marker, then remove the journal and the view bytes.
        A crash before the removal leaves the deletion visible to readers.
        """
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            view_path = self._path_for(project_id, conversation_id)
            journal = self._journal(project_id, conversation_id)
            record = self._authoritative_record(project_id, conversation_id)
            if record is None and not journal.exists() and not view_path.is_file():
                return False
            if record is not None and expected_revision is not None and record.revision != expected_revision:
                raise StaleConversationRevisionError(
                    detail="Conversation revision does not match the authoritative store",
                    context={
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "expected_revision": expected_revision,
                        "current_revision": record.revision,
                    },
                )
            revision = (record.revision if record is not None else 0) + 1
            with self._journal_errors():
                event = journal.append(
                    {
                        "event_type": "delete",
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "revision": revision,
                    }
                )
            write_deletion_marker(
                view_path,
                project_id=project_id,
                conversation_id=conversation_id,
                seq=event.seq,
                revision=revision,
            )
            for stale_path in (journal.path, view_path):
                try:
                    stale_path.unlink()
                except FileNotFoundError:
                    pass
            self._records.pop((project_id, conversation_id), None)
            # F2 계약 C-8: 삭제는 밀린 view 쓰기를 취소한다.
            self._view_lag.pop((project_id, conversation_id), None)
            return True

    def _read_record(self, project_id: str, conversation_id: str) -> ConversationRecord | None:
        """Read one record and verify its embedded identity against the request.

        Returns None only when no file exists for this identity. Any other
        failure (unreadable bytes, invalid JSON, id mismatch) raises
        ``ConversationIntegrityError``.
        """
        path = self._path_for(project_id, conversation_id)
        if not path.is_file():
            return None
        context: dict[str, Any] = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "storage_path": str(path),
        }
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConversationIntegrityError(
                detail="Conversation record could not be read from storage",
                context={**context, "reason": type(exc).__name__},
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConversationIntegrityError(
                detail="Conversation record is not valid JSON",
                context={**context, "reason": "json_decode"},
            ) from exc
        if not isinstance(data, dict):
            raise ConversationIntegrityError(
                detail="Conversation record must contain a JSON object",
                context={**context, "reason": "not_an_object"},
            )
        record = ConversationRecord.from_dict(data)
        if record.project_id != project_id or record.conversation_id != conversation_id:
            raise ConversationIntegrityError(
                detail="Conversation record ids do not match the requested identity",
                context={
                    **context,
                    "reason": "identity_mismatch",
                    "record_project_id": record.project_id,
                    "record_conversation_id": record.conversation_id,
                },
            )
        return record

    def get_revision(self, *, project_id: str, conversation_id: str) -> int | None:
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._refresh_latest(project_id, conversation_id, flush_deferred=True)
            return None if record is None else record.revision

    def compare_and_set(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        next_revision: int,
    ) -> bool:
        """Bare revision CAS (no message mutation). Prefer append/compact.

        FR-05/RP-05: CAS 평가와 persist가 프로세스 간 critical section
        안에서 디스크 최신 상태를 대상으로 이뤄진다.
        """
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._refresh_latest(project_id, conversation_id)
            if record is None:
                if expected_revision != 0:
                    return False
                record = ConversationRecord(
                    conversation_id=conversation_id,
                    project_id=project_id,
                    revision=next_revision,
                )
                self._records[(project_id, conversation_id)] = record
                self._persist(record)
                return True
            if record.revision != expected_revision:
                return False
            record.revision = next_revision
            record.updated_at = time.time()
            self._persist(record)
            return True

    # ── Reads ───────────────────────────────────────────────────────────

    def get(self, *, project_id: str, conversation_id: str) -> ConversationRecord | None:
        # FR-05/RP-05: 모든 공개 읽기는 프로세스 간 lock 아래 디스크 최신
        # 상태로 갱신한다(다른 worker의 append/compact을 즉시 관찰).
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._refresh_latest(project_id, conversation_id, flush_deferred=True)
            return None if record is None else deepcopy(record)

    def get_or_create(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int = 0,
    ) -> ConversationRecord:
        """Return existing record or create at revision 0 when expected is 0.

        FR-05/RP-05: 최신 revision 비교와 신규 persist가 같은 프로세스 간
        critical section 안에서 이뤄진다.
        """
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._refresh_latest(project_id, conversation_id, flush_deferred=True)
            if record is not None:
                if record.revision != expected_revision:
                    raise StaleConversationRevisionError(
                        detail="Conversation revision does not match the authoritative store",
                        context={
                            "project_id": project_id,
                            "conversation_id": conversation_id,
                            "expected_revision": expected_revision,
                            "current_revision": record.revision,
                        },
                    )
                return deepcopy(record)
            if expected_revision != 0:
                raise ConversationNotFoundError(
                    detail=f"Conversation not found: {conversation_id}",
                    context={
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "expected_revision": expected_revision,
                    },
                )
            record = ConversationRecord(
                conversation_id=conversation_id,
                project_id=project_id,
                revision=0,
            )
            self._records[(project_id, conversation_id)] = record
            self._persist(record)
            return deepcopy(record)

    def snapshot(self, *, project_id: str, conversation_id: str) -> ConversationSnapshot:
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._refresh_latest(project_id, conversation_id, flush_deferred=True)
            if record is None:
                raise ConversationNotFoundError(
                    detail=f"Conversation not found: {conversation_id}",
                    context={"project_id": project_id, "conversation_id": conversation_id},
                )
            return record.snapshot()

    def _build_compaction_summary(
        self,
        record: ConversationRecord,
        old: list[ConversationMessage],
        summarize_fn=None,
    ) -> str:
        """Fold ``old`` into the structured memory and render the new summary.

        NX-01: the previous store summary is carried forward explicitly (its
        prose), and the constraints it introduced are preserved as structured
        items with stable ids, status and source message id. Caller must hold
        the locks; revision is already advanced for the triggering mutation.
        """
        update_from_messages(
            record.memory,
            [{"id": m.id, "role": m.role, "content": m.content} for m in old],
            revision=record.revision,
        )
        previous = carryover_prose("\n".join(m.content for m in old if m.provenance == "summary"))
        if previous:
            record.memory.carried_summary = previous[:CARRIED_SUMMARY_MAX_CHARS]
        record_generation(
            record.memory,
            revision=record.revision,
            message_count=len(old),
            source_ids=[m.id for m in old],
        )
        return summarize_messages(
            [{"id": m.id, "role": m.role, "content": m.content} for m in old],
            summarize_fn,
            memory=record.memory,
            carryover=record.memory.carried_summary,
        )

    def _inline_compact_messages(
        self,
        record: ConversationRecord,
        *,
        retain_tail: int = _DEFAULT_RETAIN_TAIL,
        summarize_fn=None,
    ) -> None:
        """Replace older messages with a summary in-place (no revision bump).

        Caller must already hold locks and have advanced revision for the
        triggering mutation. Used by append soft-max bounding (Decision A).
        """
        retain_tail = max(0, int(retain_tail))
        messages = list(record.messages)
        if len(messages) <= retain_tail:
            record.retained_message_ids = tuple(m.id for m in record.messages)
            return
        old = messages[:-retain_tail] if retain_tail else messages
        retained = messages[-retain_tail:] if retain_tail else []
        summary_text = self._build_compaction_summary(record, old, summarize_fn)
        if not summary_text:
            summary_text = f"[대화 요약 — {len(old)}개 메시지 압축]"
        summary_msg = ConversationMessage(
            id=_SUMMARY_MESSAGE_ID if not any(m.id == _SUMMARY_MESSAGE_ID for m in retained) else _new_message_id(),
            role="system",
            content=summary_text,
            created_at=time.time(),
            provenance="summary",
        )
        new_messages = [summary_msg, *retained]
        record.messages = new_messages
        record.summary = summary_text
        record.retained_message_ids = tuple(m.id for m in new_messages)

    # ── Mutations (CAS) ─────────────────────────────────────────────────

    def append(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        role: MessageRole,
        content: str,
        message_id: str | None = None,
        provenance: str = "append",
        create_if_missing: bool = True,
    ) -> ConversationSnapshot:
        """Append one turn under revision CAS. Returns new snapshot."""
        text = (content or "").strip()
        if not text:
            raise InvalidConversationRevisionError(
                detail="append content must not be blank",
                context={"conversation_id": conversation_id},
            )
        if expected_revision < 0:
            raise InvalidConversationRevisionError(
                detail="conversation_revision must be >= 0",
                context={"conversation_revision": expected_revision},
            )

        # VAL-02: 다른 프로세스의 append와 경쟁할 수 있으므로 flock 안에서
        # 디스크 최신 상태를 재적재한 뒤 CAS를 평가한다 (stale 메모리 캐시로
        # 인한 침묵 덮어쓰기 방지).
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._authoritative_record(project_id, conversation_id)
            if record is None:
                self._assert_id_reusable(project_id, conversation_id)
                if not create_if_missing or expected_revision != 0:
                    if expected_revision != 0:
                        raise StaleConversationRevisionError(
                            detail="Conversation does not exist at the expected revision",
                            context={
                                "project_id": project_id,
                                "conversation_id": conversation_id,
                                "expected_revision": expected_revision,
                                "current_revision": 0,
                            },
                        )
                    raise ConversationNotFoundError(
                        detail=f"Conversation not found: {conversation_id}",
                        context={
                            "project_id": project_id,
                            "conversation_id": conversation_id,
                            "expected_revision": expected_revision,
                        },
                    )
                record = ConversationRecord(
                    conversation_id=conversation_id,
                    project_id=project_id,
                    revision=0,
                )
                self._records[(project_id, conversation_id)] = record

            if record.revision != expected_revision:
                raise StaleConversationRevisionError(
                    detail="Conversation revision does not match the authoritative store",
                    context={
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "expected_revision": expected_revision,
                        "current_revision": record.revision,
                    },
                )

            msg = ConversationMessage(
                id=message_id or _new_message_id(),
                role=role,
                content=text,
                created_at=time.time(),
                provenance=provenance,
            )
            record.messages.append(msg)
            record.revision = expected_revision + 1
            compacted = False
            soft_max = _soft_max_messages()
            if soft_max > 0 and len(record.messages) > soft_max:
                # Decision A (EX-05): bound RSS for long conversations without an
                # extra client-visible revision bump beyond this append.
                self._inline_compact_messages(record, retain_tail=_DEFAULT_RETAIN_TAIL)
                compacted = True
                try:
                    from antigravity_k.engine.operational_metrics import record_compaction

                    record_compaction("success")
                except Exception:  # noqa: BLE001 — metrics must not fail append
                    pass
            else:
                record.retained_message_ids = tuple(m.id for m in record.messages)
            record.updated_at = time.time()
            if compacted:
                # NX-02: one logical append = one journal event = one revision.
                # The compact event carries both the new turn (originals) and the
                # bounded view state, so replay stays lossless and deterministic.
                self._commit_event(
                    record,
                    {
                        "event_type": "compact",
                        "revision": record.revision,
                        "message_id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at,
                        "provenance": msg.provenance,
                        "summary": record.summary or "",
                        "retained_message_ids": list(record.retained_message_ids),
                        "memory": record.memory.to_dict(),
                    },
                )
            else:
                self._commit_event(
                    record,
                    {
                        "event_type": "append",
                        "revision": record.revision,
                        "message_id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at,
                        "provenance": msg.provenance,
                    },
                )
            return record.snapshot()

    def compact(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        retain_tail: int = _DEFAULT_RETAIN_TAIL,
        summarize_fn=None,
    ) -> ConversationSnapshot:
        """Compact older messages into a summary under revision CAS.

        Returns snapshot with summary, retained_message_ids, and new revision.
        """
        # OBS-01: 압축 시도 결과를 운영 metric에 기록 (record/persist 실패 제외).
        from antigravity_k.engine.operational_metrics import record_compaction

        if expected_revision < 0:
            raise InvalidConversationRevisionError(
                detail="conversation_revision must be >= 0",
                context={"conversation_revision": expected_revision},
            )
        retain_tail = max(0, int(retain_tail))

        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            record = self._authoritative_record(project_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(
                    detail=f"Conversation not found: {conversation_id}",
                    context={
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "expected_revision": expected_revision,
                    },
                )
            if record.revision != expected_revision:
                raise StaleConversationRevisionError(
                    detail="Conversation revision does not match the authoritative store",
                    context={
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "expected_revision": expected_revision,
                        "current_revision": record.revision,
                    },
                )

            messages = list(record.messages)
            if len(messages) <= retain_tail:
                # Still bump revision so clients observe a CAS success and
                # receive an explicit snapshot (summary may stay None).
                record.revision = expected_revision + 1
                record.retained_message_ids = tuple(m.id for m in record.messages)
                record.updated_at = time.time()
                self._commit_event(
                    record,
                    {
                        "event_type": "compact",
                        "revision": record.revision,
                        "message_id": "",
                        "summary": record.summary or "",
                        "retained_message_ids": list(record.retained_message_ids),
                        "memory": record.memory.to_dict(),
                    },
                )
                record_compaction("success")
                return record.snapshot()

            old = messages[:-retain_tail] if retain_tail else messages
            retained = messages[-retain_tail:] if retain_tail else []
            summary_text = self._build_compaction_summary(record, old, summarize_fn)
            if not summary_text:
                summary_text = f"[대화 요약 — {len(old)}개 메시지 압축]"

            summary_msg = ConversationMessage(
                id=_SUMMARY_MESSAGE_ID if not any(m.id == _SUMMARY_MESSAGE_ID for m in retained) else _new_message_id(),
                role="system",
                content=summary_text,
                created_at=time.time(),
                provenance="summary",
            )
            new_messages = [summary_msg, *retained]
            record.messages = new_messages
            record.summary = summary_text
            record.retained_message_ids = tuple(m.id for m in new_messages)
            record.revision = expected_revision + 1
            record.updated_at = time.time()
            self._commit_event(
                record,
                {
                    "event_type": "compact",
                    "revision": record.revision,
                    "message_id": "",
                    "summary": record.summary or "",
                    "retained_message_ids": list(record.retained_message_ids),
                    "memory": record.memory.to_dict(),
                },
            )
            record_compaction("success")
            return record.snapshot()

    def fork(
        self,
        *,
        project_id: str,
        source_conversation_id: str,
        expected_revision: int | None = None,
        new_conversation_id: str | None = None,
    ) -> ConversationSnapshot:
        """Fork conversation at current (or expected) revision into a new id at revision 0."""
        with self._lock, self._cross_process_lock():
            self._assert_storage_ready()
            source = self._refresh_latest(project_id, source_conversation_id)
            if source is None:
                raise ConversationNotFoundError(
                    detail=f"Conversation not found: {source_conversation_id}",
                    context={
                        "project_id": project_id,
                        "conversation_id": source_conversation_id,
                    },
                )
            if expected_revision is not None and source.revision != expected_revision:
                raise StaleConversationRevisionError(
                    detail="Conversation revision does not match the authoritative store",
                    context={
                        "project_id": project_id,
                        "conversation_id": source_conversation_id,
                        "expected_revision": expected_revision,
                        "current_revision": source.revision,
                    },
                )
            new_id = new_conversation_id or _new_conversation_id()
            forked = ConversationRecord(
                conversation_id=new_id,
                project_id=project_id,
                revision=0,
                messages=[
                    ConversationMessage(
                        id=_new_message_id(),
                        role=m.role,
                        content=m.content,
                        created_at=time.time(),
                        # NX-01: keep store-summary provenance so a compacted
                        # fork still carries its previous summary forward.
                        provenance="summary" if m.provenance == "summary" else "fork",
                    )
                    for m in source.messages
                ],
                summary=source.summary,
                retained_message_ids=(),
                forked_from=source_conversation_id,
                memory=deepcopy(source.memory),
            )
            forked.retained_message_ids = tuple(m.id for m in forked.messages)
            # NX-02: a fork starts a new id; its originals begin at the fork point.
            # Originals of the *source* stay in the source journal.
            source_bounded = bool(source.summary) or source.history_incomplete
            forked.history_incomplete = bool(source_bounded)
            self._records[(project_id, new_id)] = forked
            self._commit_event(
                forked,
                {
                    "event_type": "fork",
                    "revision": 0,
                    "messages": [m.to_dict() for m in forked.messages],
                    "summary": forked.summary or "",
                    "memory": forked.memory.to_dict(),
                    "history_incomplete": bool(source_bounded),
                },
            )
            return forked.snapshot()

    def assemble_history_for_request(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        new_turn: Mapping[str, Any] | None = None,
        create_if_missing: bool = True,
    ) -> tuple[list[dict[str, str]], ConversationSnapshot]:
        """Authoritative history for a chat request.

        Optionally CAS-appends ``new_turn`` first, then returns prompt messages
        + snapshot. Clients must not treat a client-side full array as SoT.
        """
        if new_turn is not None:
            role = str(new_turn.get("role") or "user")
            if role not in ("user", "assistant", "system", "tool"):
                role = "user"
            snap = self.append(
                project_id=project_id,
                conversation_id=conversation_id,
                expected_revision=expected_revision,
                role=role,  # type: ignore[arg-type]
                content=str(new_turn.get("content") or ""),
                create_if_missing=create_if_missing,
            )
        else:
            record = self.get_or_create(
                project_id=project_id,
                conversation_id=conversation_id,
                expected_revision=expected_revision,
            )
            snap = record.snapshot()

        current = self.get(project_id=project_id, conversation_id=conversation_id)
        assert current is not None
        return current.prompt_messages(), snap

    # ── Persistence ─────────────────────────────────────────────────────

    def _path_for(self, project_id: str, conversation_id: str) -> Path:
        """CR-01 v2 identity path (full SHA-256 of the raw UTF-8 ids).

        Character substitution / truncation is gone: distinct raw ids always
        produce distinct paths, including on case-insensitive filesystems.
        """
        return self._storage_dir / conversation_storage_relative_path(project_id, conversation_id)

    def _persist(self, record: ConversationRecord) -> None:
        path = self._path_for(record.project_id, record.conversation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # VAL-02 수정: 결정론적 tmp 파일명(<conv>.tmp)은 동시 writer가 서로의 tmp를
        # 삭제/치환해 FileNotFoundError로 유실을 만든다. 프로세스 고유 tmp + os.replace
        # 로 원자성과 임시파일 격리를 동시에 보장한다.
        tmp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def _load(self, project_id: str, conversation_id: str) -> ConversationRecord | None:
        record = self._read_record(project_id, conversation_id)
        if record is None:
            return None
        self._records[(project_id, conversation_id)] = record
        return record

    def _ensure_loaded(self, project_id: str, conversation_id: str) -> ConversationRecord | None:
        key = (project_id, conversation_id)
        record = self._records.get(key)
        if record is not None:
            return record
        return self._load(project_id, conversation_id)

    def clear_memory(self) -> None:
        """Test helper: drop in-memory cache (disk files remain).

        F2 계약 C-5: 밀린 view 를 먼저 수렴시킨다 — write-behind 는 프로세스 수명을 넘지 않는다.
        """
        self.flush_views()
        with self._lock:
            self._records.clear()


_store_singleton: ConversationStore | None = None
_store_lock = threading.Lock()


def get_conversation_store() -> ConversationStore:
    """Process-wide authoritative conversation store singleton."""
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            _store_singleton = ConversationStore()
        return _store_singleton


def reset_conversation_store_for_tests(store: ConversationStore | None = None) -> ConversationStore:
    """Replace the singleton (tests only)."""
    global _store_singleton
    import tempfile

    with _store_lock:
        if store is not None:
            _store_singleton = store
        elif os.environ.get("AGK_CONVERSATION_STORE_DIR"):
            _store_singleton = ConversationStore(storage_dir=Path(os.environ["AGK_CONVERSATION_STORE_DIR"]))
        else:
            _store_singleton = ConversationStore(storage_dir=tempfile.mkdtemp(prefix="agk-conv-"))
        return _store_singleton


__all__ = [
    "ConversationJournalCorruptError",
    "ConversationJournalError",
    "ConversationMessage",
    "ConversationRecord",
    "ConversationStore",
    "HISTORY_EXPORT_SCHEMA",
    "JOURNAL_SCHEMA_VERSION",
    "JOURNAL_SUFFIX",
    "MIGRATION_MARKER_NAME",
    "VIEW_SCHEMA_VERSION",
    "conversation_identity_digest",
    "conversation_storage_relative_path",
    "get_conversation_store",
    "reset_conversation_store_for_tests",
]
