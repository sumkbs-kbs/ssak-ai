"""NX-02: append-only conversation journal (originals) for ConversationStore.

ADR: ``docs/adr/ADR-DAT-02-conversation-history-journal.md``.

The journal is the source of truth for the *original* conversation history; the
``<sha>.json`` record written by :class:`~antigravity_k.engine.conversation_store.ConversationStore`
is a **materialized, bounded view** (prompt view + summary + NX-01 memory) that
can be rebuilt by replaying the journal.

Contracts implemented here:

* one event per line (JSON Lines), schema ``agk.conv-journal.v1``; an unknown
  schema is refused instead of guessed at,
* ``seq`` is assigned by the journal (1-based, monotonic) and ``revision`` is the
  published conversation revision carried by the event, so "one logical append =
  one revision" stays observable from the journal alone,
* a commit is "line appended + fsync"; the directory is fsynced when the file is
  created,
* a **truncated final line** (no trailing newline) is an uncommitted tail: it is
  reported and moved aside for recovery, never silently treated as committed,
* a **corrupt middle line** is a hard error carrying the line number and byte
  offset; it is never skipped,
* replay is deterministic and only uses committed events.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping

logger = logging.getLogger("antigravity_k.engine.conversation_journal")

JOURNAL_SCHEMA_VERSION: Final[str] = "agk.conv-journal.v1"
JOURNAL_SUFFIX: Final[str] = ".jsonl"
DELETION_MARKER_SUFFIX: Final[str] = ".deleted.json"
DELETION_MARKER_SCHEMA: Final[str] = "agk.conv-deleted.v1"

EVENT_TYPES: Final[tuple[str, ...]] = ("base", "append", "compact", "fork", "delete")

# 꼬리 창 크기. 마지막 커밋 줄 하나를 담기에 충분한 크기로 시작해
# 줄이 그보다 길면 창을 키우다가, 상한을 넘으면 종전과 동일한 전체 스캔으로
# 되돌아간다(정확성 우선). 8시간 soak 에서 append 1회가 journal 전체(24 MB)를
# 3회 파싱해 SC-6 이 RSS 로 실패했다 — nx10/SOAK_8H_FINDINGS.md §3.
TAIL_WINDOW_BYTES: Final[int] = 64 * 1024
TAIL_WINDOW_MAX_BYTES: Final[int] = 8 * 1024 * 1024


class ConversationJournalError(RuntimeError):
    """Journal could not be read or written (never a silent degradation)."""


class ConversationJournalSchemaMismatchError(ConversationJournalError):
    """A stored event declares a schema this build does not understand."""


class ConversationJournalCorruptError(ConversationJournalError):
    """A committed region of the journal is not parseable (never skipped)."""

    def __init__(self, *, path: Path, line_no: int, offset: int, reason: str) -> None:
        super().__init__(f"Conversation journal is corrupt at line {line_no} (offset {offset}): {reason}")
        self.path = path
        self.line_no = line_no
        self.offset = offset
        self.reason = reason


def _fsync_fd(fd: int) -> None:
    """fsync (테스트에서 실패 주입 지점)."""
    os.fsync(fd)


def _append_bytes(path: Path, payload: bytes) -> None:
    """O_APPEND 쓰기 + fsync (테스트에서 실패/중단 주입 지점)."""
    if not path.parent.is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        _fsync_fd(fd)
    finally:
        os.close(fd)
    if created and os.name == "posix":
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            _fsync_fd(dir_fd)
        except OSError:  # pragma: no cover - 디렉터리 fsync 미지원 파일시스템
            pass
        finally:
            os.close(dir_fd)


def _truncate_file(path: Path, size: int) -> None:
    """명시적 tail 정리를 위한 truncate (테스트에서 실패 주입 지점)."""
    with path.open("r+b") as handle:
        handle.truncate(size)
        handle.flush()
        _fsync_fd(handle.fileno())


def _write_bytes_atomically(path: Path, payload: bytes) -> None:
    """원자 교체 쓰기(디렉터리 fsync 포함)."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            _fsync_fd(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


@dataclass(frozen=True)
class JournalEvent:
    """One committed history event."""

    seq: int
    revision: int
    event_type: str
    project_id: str
    conversation_id: str
    message_id: str = ""
    role: str = ""
    content: str = ""
    created_at: float = 0.0
    provenance: str = ""
    summary: str = ""
    retained_message_ids: tuple[str, ...] = ()
    # ``base``/``fork`` events carry the full copied view (list form); ``append``
    # and ``compact`` carry one message via the scalar fields above.
    messages: list[dict[str, Any]] | None = None
    memory: dict[str, Any] | None = None
    history_incomplete: bool = False
    schema: str = JOURNAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "seq": self.seq,
            "revision": self.revision,
            "event_type": self.event_type,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
        }
        if self.message_id:
            payload["message_id"] = self.message_id
        if self.role:
            payload["role"] = self.role
        if self.content:
            payload["content"] = self.content
        if self.provenance:
            payload["provenance"] = self.provenance
        if self.summary:
            payload["summary"] = self.summary
        if self.retained_message_ids:
            payload["retained_message_ids"] = list(self.retained_message_ids)
        if self.messages:
            payload["messages"] = [dict(m) for m in self.messages]
        if self.memory is not None:
            payload["memory"] = self.memory
        if self.history_incomplete:
            payload["history_incomplete"] = True
        return payload

    def to_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JournalEvent:
        schema = str(data.get("schema") or "")
        if schema != JOURNAL_SCHEMA_VERSION:
            raise ConversationJournalSchemaMismatchError(
                f"Unsupported conversation journal schema: {schema!r} (expected {JOURNAL_SCHEMA_VERSION!r})"
            )
        event_type = str(data.get("event_type") or "")
        if event_type not in EVENT_TYPES:
            raise ConversationJournalCorruptError(
                path=Path("<journal>"),
                line_no=0,
                offset=0,
                reason=f"unknown event_type {event_type!r}",
            )
        retained = data.get("retained_message_ids") or []
        raw_messages = data.get("messages")
        messages = (
            [dict(item) for item in raw_messages if isinstance(item, Mapping)]
            if isinstance(raw_messages, list)
            else None
        )
        memory = data.get("memory")
        return cls(
            seq=int(data.get("seq") or 0),
            revision=int(data.get("revision") or 0),
            event_type=event_type,
            project_id=str(data.get("project_id") or ""),
            conversation_id=str(data.get("conversation_id") or ""),
            message_id=str(data.get("message_id") or ""),
            role=str(data.get("role") or ""),
            content=str(data.get("content") or ""),
            created_at=float(data.get("created_at") or 0.0),
            provenance=str(data.get("provenance") or ""),
            summary=str(data.get("summary") or ""),
            retained_message_ids=tuple(str(x) for x in retained) if isinstance(retained, list) else (),
            messages=messages,
            memory=dict(memory) if isinstance(memory, Mapping) else None,
            history_incomplete=bool(data.get("history_incomplete")),
        )


@dataclass(frozen=True)
class JournalTail:
    """Cheap state read from the journal (last committed event + tail health)."""

    exists: bool
    seq: int
    revision: int
    truncated_tail: bool
    deleted: bool
    history_incomplete: bool


@dataclass
class ReplayState:
    """Deterministic replay result (originals + view)."""

    seq: int = 0
    revision: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    memory: dict[str, Any] | None = None
    history_incomplete: bool = False
    deleted: bool = False
    originals: list[dict[str, Any]] = field(default_factory=list)


class ConversationJournal:
    """Append-only JSON Lines journal for one conversation."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # ── state ───────────────────────────────────────────────────────────
    def exists(self) -> bool:
        return self.path.is_file()

    def fingerprint(self) -> str:
        try:
            payload = self.path.read_bytes()
        except OSError:
            return ""
        return hashlib.sha256(payload).hexdigest()

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    # ── write ───────────────────────────────────────────────────────────
    def append(self, event: Mapping[str, Any], *, tail: JournalTail | None = None) -> JournalEvent:
        """Commit one event (line + fsync) and return it with its assigned seq.

        ``tail`` 는 호출자가 **같은 flock 임계 구역 안에서** 읽은 꼬리다(flush 배치 F1).
        직전 판정에 쓴 그 값을 다시 읽지 않는다 — 종전에는 append 1회가 같은 꼬리를 3번
        읽어 약 113 KiB 를 다시 읽었다(nx10/fsync/probe-flush-output.json). 미결 꼬리
        (truncated)를 들고 오면 신뢰하지 않고 다시 읽는다 — seq 오부여를 막는다.
        """
        current = tail if tail is not None and not tail.truncated_tail else self.tail()
        seq = current.seq + 1
        payload = dict(event)
        payload.setdefault("schema", JOURNAL_SCHEMA_VERSION)
        payload["schema"] = JOURNAL_SCHEMA_VERSION
        payload["seq"] = seq
        payload.setdefault("created_at", time.time())
        candidate = JournalEvent.from_dict(payload)
        line = candidate.to_line() + "\n"
        try:
            _append_bytes(self.path, line.encode("utf-8"))
        except OSError as exc:
            raise ConversationJournalError(
                f"Conversation journal append failed: {self.path} ({type(exc).__name__}: {exc})"
            ) from exc
        return candidate

    def rewrite_without_truncated_tail(self) -> Path | None:
        """Move an uncommitted torn tail aside before further appends.

        Returns the recovery path (or ``None`` when the tail is clean). The torn
        bytes are preserved in a sibling file — they are reported, not deleted —
        and the journal keeps only committed events.
        """
        raw = self._read_bytes()
        if raw is None:
            return None
        good_bytes, remainder, truncated = self._split_truncated_tail(raw)
        if not truncated:
            return None
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        recovery = self.path.with_name(f"{self.path.name}.tail-recovery-{stamp}.bin")
        _write_bytes_atomically(recovery, remainder)
        _truncate_file(self.path, len(good_bytes))
        logger.warning(
            "Conversation journal had an uncommitted torn tail; moved %d bytes to %s",
            len(remainder),
            recovery,
        )
        return recovery

    # ── read ────────────────────────────────────────────────────────────
    def _read_bytes(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ConversationJournalError(f"Conversation journal could not be read: {self.path}") from exc

    @staticmethod
    def _split_truncated_tail(raw: bytes) -> tuple[bytes, bytes, bool]:
        """Split committed bytes from a torn (no trailing newline) tail."""
        if not raw or raw.endswith(b"\n"):
            return raw, b"", False
        last_newline = raw.rfind(b"\n")
        return raw[: last_newline + 1], raw[last_newline + 1 :], True

    def read(self) -> tuple[list[JournalEvent], bool]:
        """Return ``(committed events, truncated_tail)``.

        A corrupt committed line raises :class:`ConversationJournalCorruptError`
        with its line number and byte offset.
        """
        raw = self._read_bytes()
        if raw is None:
            return [], False
        good_bytes, _remainder, truncated = self._split_truncated_tail(raw)
        events: list[JournalEvent] = []
        offset = 0
        for line_no, line in enumerate(good_bytes.split(b"\n"), start=1):
            if line == b"":
                offset += 1
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ConversationJournalCorruptError(
                    path=self.path, line_no=line_no, offset=offset, reason=type(exc).__name__
                ) from exc
            if not isinstance(data, dict):
                raise ConversationJournalCorruptError(
                    path=self.path, line_no=line_no, offset=offset, reason="not_an_object"
                )
            try:
                events.append(JournalEvent.from_dict(data))
            except ConversationJournalSchemaMismatchError:
                raise
            except ConversationJournalError as exc:
                raise ConversationJournalCorruptError(
                    path=self.path, line_no=line_no, offset=offset, reason=str(exc)
                ) from exc
            offset += len(line) + 1
        return events, truncated

    def tail(self) -> JournalTail:
        """Last committed event state without replaying the whole file.

        마지막 커밋 줄은 파일 끝에 있으므로 앞부분을 다시 파싱할 이유가 없다 —
        꼬리 창(window)만 읽는다. 창 안에서 읽히는 줄을 못 찾으면(줄이 창보다 긴
        비정상 파일) 창을 키우고, 상한을 넘으면 종전과 **동일한 전체 스캔**으로
        되돌아간다(정확성 우선).
        """
        # 읽는 동안 파일이 줄어들면(다른 프로세스의 truncate) 줄 경계 판단이 틀릴 수 있다
        # — 짧게 읽힌 경우는 다시 시도하고, 그래도 안 되면 전체 스캔으로 되돌아간다.
        for _ in range(3):
            tail, retry = self._tail_from_window()
            if not retry:
                return tail if tail is not None else self._tail_by_full_scan()
        return self._tail_by_full_scan()

    def _tail_from_window(self) -> tuple[JournalTail | None, bool]:
        """꼬리 창으로 판정한다. ``(결과 또는 None, 다시 시도할까)``."""
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except FileNotFoundError:
            return JournalTail(False, 0, 0, False, False, False), False
        except OSError as exc:
            raise ConversationJournalError(f"Conversation journal could not be read: {self.path}") from exc
        try:
            size = os.fstat(fd).st_size
            if size == 0:
                return JournalTail(True, 0, 0, False, False, False), False
            window = min(TAIL_WINDOW_BYTES, size)
            while True:
                offset = size - window
                chunk = os.pread(fd, window, offset)
                if offset > 0 and len(chunk) < window:
                    return None, True  # 파일이 줄어들었다 — 크기를 다시 읽는다
                event, truncated = self._last_event_in_window(chunk, partial_head=offset > 0)
                if event is not None:
                    return (
                        JournalTail(
                            True,
                            event.seq,
                            event.revision,
                            truncated,
                            event.event_type == "delete",
                            event.history_incomplete,
                        ),
                        False,
                    )
                if window >= size or window >= TAIL_WINDOW_MAX_BYTES:
                    return None, False  # 창으로 결정할 수 없다 → 전체 스캔 폴백
                window = min(window * 2, size, TAIL_WINDOW_MAX_BYTES)
        except OSError as exc:
            raise ConversationJournalError(f"Conversation journal could not be read: {self.path}") from exc
        finally:
            os.close(fd)

    def _last_event_in_window(self, chunk: bytes, *, partial_head: bool) -> tuple[JournalEvent | None, bool]:
        """``(마지막으로 읽히는 이벤트, torn tail 여부)`` — 이벤트가 None 이면 창을 키운다.

        ``partial_head`` 는 창이 줄 중간에서 시작함을 뜻한다 — 그 첫 조각은 마지막
        줄이 아니므로 버린다. 읽히는 줄이 하나도 없는 창은 결정적이지 않으므로
        호출자가 창을 키우게 한다(끝까지 키워도 안 되면 전체 스캔 폴백).
        """
        truncated = bool(chunk) and not chunk.endswith(b"\n")
        body = chunk[: chunk.rfind(b"\n") + 1] if truncated else chunk
        segments = body.split(b"\n")
        if partial_head:
            segments = segments[1:]
        for line in reversed(segments):
            if not line.strip():
                continue
            event = _parse_lenient_line(line)
            if event is not None:
                return event, truncated
        return None, truncated

    def _tail_by_full_scan(self) -> JournalTail:
        """종전 전체 스캔 — 창 경로가 판정하지 못한 파일의 폴백(의미 동일)."""
        raw = self._read_bytes()
        if raw is None:
            return JournalTail(False, 0, 0, False, False, False)
        good_bytes, _remainder, truncated = self._split_truncated_tail(raw)
        last: JournalEvent | None = None
        for line in good_bytes.split(b"\n"):
            if not line.strip():
                continue
            event = _parse_lenient_line(line)
            if event is not None:
                last = event
        if last is None:
            return JournalTail(True, 0, 0, truncated, False, False)
        return JournalTail(
            True,
            last.seq,
            last.revision,
            truncated,
            last.event_type == "delete",
            last.history_incomplete,
        )

    def events_after(self, seq: int) -> list[JournalEvent]:
        events, _truncated = self.read()
        return [event for event in events if event.seq > seq]


def _parse_lenient_line(line: bytes) -> JournalEvent | None:
    """``tail()`` 전용 관대한 줄 파서 — 못 읽는 줄은 건너뛴다(오류는 ``read()`` 가 낸다)."""
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return JournalEvent.from_dict(data)
    except ConversationJournalError:
        return None


def is_original(message: Mapping[str, Any]) -> bool:
    """Originals are turns that were actually recorded, never synthesized ones.

    Store-generated summary messages belong to the bounded view (``summary`` /
    ``memory``), so they are excluded from the originals read surface. Presenting a
    summary as an original turn would be the mirror image of inventing originals
    from a summary, which ADR-DAT-02 forbids.
    """
    return str(message.get("provenance") or "") != "summary"


def replay(events: list[JournalEvent]) -> ReplayState:
    """Rebuild originals + bounded view from committed events (deterministic)."""
    state = ReplayState()
    for event in events:
        state.seq = event.seq
        state.revision = event.revision
        state.history_incomplete = state.history_incomplete or event.history_incomplete
        if event.event_type == "delete":
            state.deleted = True
            state.messages = []
            state.summary = None
            state.memory = None
            state.originals = []
            continue
        if event.event_type in ("base", "fork"):
            if event.messages:
                state.messages = [dict(m) for m in event.messages]
            elif event.message_id or event.content:
                state.messages = [
                    {
                        "id": event.message_id or "msg_base",
                        "role": event.role,
                        "content": event.content,
                        "created_at": event.created_at,
                        "provenance": event.provenance or event.event_type,
                    }
                ]
            else:
                state.messages = []
            if event.memory is not None:
                state.memory = dict(event.memory)
            if event.summary:
                state.summary = event.summary
            state.originals = [dict(m) for m in state.messages if is_original(m)]
            continue
        if event.event_type == "compact":
            state.summary = event.summary or state.summary
            if event.message_id:
                # The turn that triggered the compaction is an original too.
                state.originals.append(
                    {
                        "id": event.message_id,
                        "role": event.role,
                        "content": event.content,
                        "created_at": event.created_at,
                        "provenance": event.provenance or "append",
                    }
                )
            retained_ids = set(event.retained_message_ids)
            retained = [dict(m) for m in state.messages if m.get("id") in retained_ids]
            summary_id = event.message_id or "msg_summary"
            summary_message = {
                "id": "msg_summary" if event.message_id else summary_id,
                "role": "system",
                "content": event.summary,
                "created_at": event.created_at,
                "provenance": "summary",
            }
            state.messages = [summary_message, *retained]
            if event.memory is not None:
                state.memory = dict(event.memory)
            # The synthesized summary stays in the view/summary, not in originals.
            continue
        # append
        message = {
            "id": event.message_id,
            "role": event.role,
            "content": event.content,
            "created_at": event.created_at,
            "provenance": event.provenance or "append",
        }
        state.messages.append(dict(message))
        state.originals.append(dict(message))
    return state


def base_event_from_view(view: Mapping[str, Any]) -> dict[str, Any]:
    """Build a ``base`` journal event from a materialized view record (NX-02).

    Used both by the lazy first-touch migration and by
    ``scripts/migrate_conversation_storage.py`` so the two agree on one rule: a
    view that already carries a summary cannot yield originals, so the journal is
    marked ``history_incomplete`` instead of pretending the turns were recorded.
    """
    raw_messages = view.get("messages")
    messages = [dict(m) for m in raw_messages] if isinstance(raw_messages, list) else []
    summary = str(view.get("summary") or "")
    memory = view.get("memory")
    incomplete = bool(summary) or any(str(m.get("provenance") or "") == "summary" for m in messages)
    return {
        "event_type": "base",
        "project_id": str(view.get("project_id") or ""),
        "conversation_id": str(view.get("conversation_id") or ""),
        "revision": int(view.get("revision") or 0),
        "messages": messages,
        "summary": summary,
        "memory": dict(memory) if isinstance(memory, Mapping) else {},
        "history_incomplete": incomplete,
    }


def deletion_marker_path(view_path: Path) -> Path:
    """Deletion marker path derived from the materialized view path."""
    return view_path.with_suffix(DELETION_MARKER_SUFFIX)


def write_deletion_marker(view_path: Path, *, project_id: str, conversation_id: str, seq: int, revision: int) -> None:
    """Record a durable deletion marker (no message content, no secrets)."""
    payload = {
        "schema": DELETION_MARKER_SCHEMA,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "seq": seq,
        "revision": revision,
        "deleted_at": time.time(),
    }
    _write_bytes_atomically(
        deletion_marker_path(view_path), (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def read_deletion_marker(view_path: Path) -> dict[str, Any] | None:
    """Read a deletion marker (``None`` when absent/corrupt)."""
    path = deletion_marker_path(view_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != DELETION_MARKER_SCHEMA:
        return None
    return data


__all__ = [
    "ConversationJournal",
    "ConversationJournalCorruptError",
    "ConversationJournalError",
    "ConversationJournalSchemaMismatchError",
    "DELETION_MARKER_SCHEMA",
    "DELETION_MARKER_SUFFIX",
    "EVENT_TYPES",
    "JOURNAL_SCHEMA_VERSION",
    "JOURNAL_SUFFIX",
    "JournalEvent",
    "JournalTail",
    "ReplayState",
    "base_event_from_view",
    "deletion_marker_path",
    "is_original",
    "read_deletion_marker",
    "replay",
    "write_deletion_marker",
]
