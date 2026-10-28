"""
BackgroundTaskRunner — 장기 실행 태스크 비동기 처리 엔진
=======================================================
Codex 스타일의 long-horizon task 실행 및 Checkpoint/Resume 지원.

핵심 기능:
  1) submit_task() — 태스크를 백그라운드 스레드로 실행
  2) get_status()  — 진행 상태 조회 (running/done/failed)
  3) checkpoint()  — 현재 상태 스냅샷 저장 (SQLite)
  4) resume()      — 마지막 체크포인트에서 재개
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import Token
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, TypeAlias, TypedDict, assert_never, cast, final, runtime_checkable

from pydantic import JsonValue, TypeAdapter, ValidationError

from antigravity_k.engine.access_mode import AccessMode, get_access_mode
from antigravity_k.engine.benchmark_harness import TaskOutcome
from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.secret_scanner import redact, redact_full, redact_url, strip_credentials
from antigravity_k.engine.task_context_snapshot import (
    ContextSnapshotStoreError,
    load_task_context_snapshot,
    restored_task_context_messages,
    save_task_context_snapshot,
)
from antigravity_k.engine.task_process_ownership import (
    execution_owner_of,
    owner_pid_for_raw_status,
    resumable_task,
)
from antigravity_k.engine.task_process_supervisor import task_process_supervisor
from antigravity_k.engine.task_state_store import (
    TaskStateStore,
)
from antigravity_k.engine.task_state_types import (
    CancellationVerdict,
    InvalidTaskStatusError,
    InvalidTaskTransitionError,
    TaskRecord,
    TaskStatusName,
    TaskTransitionConflictError,
    parse_task_status,
)
from antigravity_k.engine.task_steering import TaskSteeringQueue, TaskSteeringResult
from antigravity_k.engine.tool_policy import (
    REQUEST_TOOL_POLICY_KEY,
    InvalidToolPolicySnapshotError,
    bind_tool_policy,
    get_tool_policy,
    narrow_tool_policy,
    parse_tool_policy_snapshot,
    request_allows_side_effects,
    serialize_tool_policy,
    snapshot_tool_policy,
)
from antigravity_k.engine.worktree_manager import WorktreeManager

if TYPE_CHECKING:
    from antigravity_k.api.contracts.execution_context import RequestExecutionContext


def _stderr_text(error: subprocess.CalledProcessError) -> str:
    raw_stderr: object = error.__dict__.get("stderr")
    if isinstance(raw_stderr, str):
        return raw_stderr
    if isinstance(raw_stderr, bytes):
        return raw_stderr.decode(errors="replace")
    return str(error)


def _reset_worktree_context(token: Token[RequestExecutionContext | None] | None) -> None:
    """Restore the ambient request execution context after a task finishes."""
    if token is None:
        return
    try:
        from antigravity_k.api.project_binding import reset_bound_request_execution_context

        reset_bound_request_execution_context(token)
    except Exception:
        logger.debug("worktree context reset failed", exc_info=True)


logger = logging.getLogger(__name__)

_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_BOOKKEEPING_READ_ONLY: Final = "_bookkeeping_read_only"

TaskContext: TypeAlias = dict[str, object]
TaskInfo: TypeAlias = dict[str, object]


class _TaskCheckpointPersistenceError(RuntimeError):
    def __init__(self, task_id: str) -> None:
        self.task_id: str = task_id
        super().__init__(f"Pause checkpoint could not be persisted for task {task_id}.")


def _request_restricts_bookkeeping() -> bool:
    """Read both authoritative restrictions before a request leaves its thread."""
    return get_access_mode() is AccessMode.READ_ONLY or not request_allows_side_effects()


def _task_allows_bookkeeping(task: BackgroundTask) -> bool:
    """Keep automatic vault effects within the task's captured and current authority."""
    restricted = task.context.get(_BOOKKEEPING_READ_ONLY) is True or _request_restricts_bookkeeping()
    if restricted:
        task.context[_BOOKKEEPING_READ_ONLY] = True
    return not restricted


class CheckpointInfo(TypedDict):
    task_id: str
    step: int
    context: TaskContext
    output_so_far: str
    created_at: str


class ModelManagerPort(Protocol):
    def stream_generate(
        self,
        *,
        prompt: str,
        target: str,
        raw_messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]: ...


class VaultEnginePort(Protocol):
    def create_snapshot(self, description: str) -> str | None: ...

    def restore_snapshot(self, snapshot_hash: str, scope: Sequence[str] | None = None) -> bool: ...

    def write_note(
        self,
        *,
        relative_path: str,
        metadata: Mapping[str, object],
        content: str,
        commit_message: str,
    ) -> object: ...


class OrchestratorPort(Protocol):
    def get_model_for_role(self, role: str) -> str: ...

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]: ...


_DIRECT_RESPONSE_MARKERS = (
    "파일을 수정하지",
    "도구를 사용하지",
    "코드만",
    "answer only",
    "code only",
    "do not modify files",
    "do not use tools",
)

_VAULT_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")

# Directories whose vault writes are legitimate side-effects of task
# bookkeeping rather than the task's intended work product. Scoped rollback
# never discards changes under these prefixes (BR-01: only task-owned work
# files are reverted; housekeeping artifacts of the runner itself survive).
_TASK_VAULT_KEEP_PREFIXES: tuple[str, ...] = (".agent/", ".agk/", ".chroma/", ".git/")


def _record_vault_mutation(task: "BackgroundTask", relative_path: str) -> None:
    """Track a vault path a task mutated so rollback can scope to it (DAT-02).

    ``task.vault_writes`` may be pre-seeded by the caller with paths the task is
    expected to own (e.g. its worktree-scoped scratchpad). Recording here is
    best-effort bookkeeping: failures never affect task execution.
    """
    try:
        normalized = str(relative_path).replace("\\", "/").lstrip("/")
        if not normalized:
            return
        owned = task.vault_writes
        if isinstance(owned, set):
            owned.add(normalized)
    except Exception:
        logger.debug("vault mutation tracking failed", exc_info=True)


def _task_rollback_scope(task: "BackgroundTask") -> tuple[str, ...]:
    """Paths this task owns in the shared vault, for a scoped restore (DAT-02).

    Always returns at least one entry so the runner can never fall back into a
    full ``reset --hard`` restore (which would destroy concurrent tasks'
    committed/uncommitted/untracked changes — audit finding BR-01).
    """
    owned = task.vault_writes if isinstance(task.vault_writes, set) else set()
    return tuple(
        sorted(p for p in owned if isinstance(p, str) and p and not p.startswith(_TASK_VAULT_KEEP_PREFIXES)),
    ) or ("__no_task_owned_paths__",)


def _redact_vault_text(text: str) -> str:
    redacted = redact_full(redact(text))

    def replace_url(match: re.Match[str]) -> str:
        return redact_url(match.group(0)) or "<REDACTED_URL>"

    return _VAULT_URL_PATTERN.sub(replace_url, redacted)


@runtime_checkable
class TaskExecutionBindingPort(Protocol):
    def bind_task_execution(
        self,
        task_id: str,
        state_store: TaskStateStore,
    ) -> AbstractContextManager[None]: ...

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]: ...


class TaskStatus:
    PENDING: TaskStatusName = "pending"
    RUNNING: TaskStatusName = "running"
    RESUMING: TaskStatusName = "resuming"
    DONE: TaskStatusName = "done"
    FAILED: TaskStatusName = "failed"
    PAUSED: TaskStatusName = "paused"
    CANCELLED: TaskStatusName = "cancelled"


@final
class TaskCheckpoint:
    """태스크 실행 중간 상태 스냅샷"""

    def __init__(self, task_id: str, step: int, context: TaskContext, output_so_far: str):
        self.task_id = task_id
        self.step = step
        self.context = context
        self.output_so_far = output_so_far
        self.timestamp = datetime.now(UTC).isoformat()


@final
class BackgroundTask:
    """백그라운드 태스크 상태 객체.

    ``vault_writes`` accumulates the vault-relative paths this task mutated
    (best-effort tracking via :func:`_record_vault_mutation`). It seeds the
    task-scoped rollback scope so a failed task never triggers a shared-vault
    full restore (BR-01 / DAT-02).
    """

    def __init__(
        self,
        task_id: str,
        prompt: str,
        context: TaskContext | None = None,
        owner_subject: str = "loopback",
    ):
        self.task_id = task_id
        self.prompt = prompt
        self.context = context or {}
        self.owner_subject = owner_subject or "loopback"
        self.status = TaskStatus.PENDING
        self.progress = 0.0
        self.output = ""
        self.error: str | None = None
        self.created_at = datetime.now(UTC).isoformat()
        self.updated_at = self.created_at
        self.cancel_event = threading.Event()
        # r32: user pause is NOT cancel — it checkpoints and keeps the worktree/snapshot.
        self.pause_event = threading.Event()
        self.checkpoints: list[TaskCheckpoint] = []
        self._thread: threading.Thread | None = None
        self.worktree_path: str | None = None
        self.vault_writes: set[str] = set()
        # r33: output already delivered before a pause/restart; set only by resume_task.
        self.resume_prior_output: str = ""

    def to_dict(self) -> TaskInfo:
        # F-36: 이 태스크는 **이 프로세스가** 실행 중이다 — 소유 사실을 말한다. `resumable` 은
        # 행동(`resume_task`)이 이 행에 대해 성공할 것인가이며, 여기서는 **아니다**: 실행 중인
        # 태스크를 재개할 수는 없다(`can_prepare_resume` 이 이 프로세스의 pid 를 거부한다).
        return {
            "task_id": self.task_id,
            "prompt": (self.prompt[:100] + "..." if len(self.prompt) > 100 else self.prompt),
            "status": self.status,
            "progress": self.progress,
            "output_length": len(self.output),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "checkpoint_count": len(self.checkpoints),
            "execution_owner": execution_owner_of(self.status, owner_pid_for_raw_status(self.status)),
            "resumable": resumable_task(self.status, owner_pid_for_raw_status(self.status), bool(self.checkpoints)),
        }

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def attach_thread(self, thread: threading.Thread) -> None:
        self._thread = thread


RESUME_CONTINUE_INSTRUCTION = (
    "The assistant message above is output already delivered to the user before a pause. "
    "Continue immediately after its last line. Do not repeat or renumber anything already written, "
    "do not restart the answer, and do not re-run tool actions that already completed."
)
RESUME_PRIOR_OUTPUT_CHARS = 6000
_BANNER_RE = re.compile(
    r"^\s*(?:🛡️ \*\*\[정밀 엔지니어링 모드\]\*\*|🚀 \*\*\[빠른 프로토타이핑 모드\]\*\*|🏢|"
    r"\*\*\[CEO\]\*\* .{0,40}\*\*[A-Z_]+\*\* 위임 [^\n]*)\s*$"
)


def is_orchestrator_banner_chunk(chunk: str) -> bool:
    """True only for the orchestrator's mode/CEO-delegation banner display events.

    This legacy text classifier is narrower than a stream channel: tool details
    are not banners. Typed progress is retained separately as execution events.
    """
    return bool(_BANNER_RE.match(chunk)) or not chunk.strip()


@contextmanager
def _resume_prefix_scope(task_id: str, prior_output: str) -> Iterator[None]:
    """r36: runner owns this task's DONE write; prior output is kept on loop terminal writes.
    Always restored (normal end, exception, early return, generator close)."""
    from antigravity_k.engine.task_execution_context import resume_output_prefix

    token = resume_output_prefix.set((task_id, prior_output or ""))
    try:
        yield
    finally:
        resume_output_prefix.reset(token)


_CONTROL_NOTICE_RE = re.compile(r"^\s*🧭 [^\n]*\s*$")


def resume_control_kind(chunk: str) -> str | None:
    """r37: classify a resume-prelude chunk as a control/display event (never body text).

    Banners (mode/CEO marker) and the trajectory-compaction notice are display events emitted by
    the orchestrator as ProgressChunk; they are not part of the answer body, so at the resume
    cursor they must not be spliced into it. Returns the kind, or None for body text."""
    if not chunk.strip():
        return "blank"
    if _BANNER_RE.match(chunk):
        return "banner"
    if _CONTROL_NOTICE_RE.match(chunk):
        return "compaction_notice"
    return None


_RESUME_REPEAT_RUN = 3


def resume_join_issue(prior: str, final: str) -> str | None:
    """r42: exact-only check that the resumed segment did not restart already-delivered text.

    Flags (a) the new segment's first non-blank line equals the first non-blank line of the prior
    answer (answer restarted from the top) when that line is not trivially short, or (b) the first
    ``_RESUME_REPEAT_RUN`` non-blank new lines equal a consecutive run of prior lines. A single
    repeated sentence (normal repetition) is never flagged. Paraphrased regeneration is NOT
    detectable by this check (documented limit)."""
    if not prior or not final.startswith(prior):
        return "final output does not extend the delivered prefix" if prior and final else None
    new_lines = [line.strip() for line in final[len(prior) :].splitlines() if line.strip()]
    prior_lines = [line.strip() for line in prior.splitlines() if line.strip()]
    if not new_lines or not prior_lines:
        return None
    if new_lines[0] == prior_lines[0] and len(prior_lines) > 1 and len(new_lines[0]) >= 12:
        return "resumed segment restarts the answer from its first line"
    run = new_lines[:_RESUME_REPEAT_RUN]
    if len(run) == _RESUME_REPEAT_RUN:
        for i in range(len(prior_lines) - _RESUME_REPEAT_RUN + 1):
            if prior_lines[i : i + _RESUME_REPEAT_RUN] == run:
                return f"resumed segment repeats {_RESUME_REPEAT_RUN} consecutive delivered lines"
    return None


_SAVED_PATH_RE = re.compile(r"Successfully saved to (\S+?)\.?\s")
_HASH_CLAIM_RE = re.compile(
    r"(?i)(?:sha[-_ ]?256[^\n`0-9a-f]{0,24}|해시[^\n`0-9a-f]{0,24}|hash[^\n`0-9a-f]{0,24})`?([0-9a-f]{8,64})"
)


def _verified_artifact_block(state_store: object, task_id: str, output: str) -> str:
    """r42: hash/size of artifacts this task wrote, computed now from the real file."""
    import hashlib

    from antigravity_k.engine import task_tool_contract as ttc

    if not callable(getattr(state_store, "list_execution_events", None)):
        return ""
    paths: list[str] = []
    try:
        for record in ttc.completed_records(cast("ttc._Store", state_store), task_id):
            match = _SAVED_PATH_RE.search(str(record.get("result") or "") + " ")
            if match and match.group(1) not in paths:
                paths.append(match.group(1))
    except Exception:
        logger.warning("verified artifact scan failed for %s", task_id, exc_info=True)
        return ""
    if not paths:
        return ""
    lines = ["", "", "---", "**검증된 산출물 정보 (실제 파일에서 계산)**"]
    verified: list[str] = []
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            lines.append(f"- `{os.path.basename(path)}`: 확인 불가 ({type(exc).__name__}) — 값을 확정하지 않음")
            continue
        digest = hashlib.sha256(data).hexdigest()
        verified.append(digest)
        lines.append(
            f"- `{os.path.basename(path)}`: sha256 `{digest}`, {len(data)} bytes, {len(data.decode('utf-8', 'replace'))} chars"
        )
    for claim in sorted({m.group(1).lower() for m in _HASH_CLAIM_RE.finditer(output)}):
        if not any(d.startswith(claim) for d in verified):
            lines.append(f"- ⚠ 불일치: 응답 본문의 해시 `{claim}`는 검증값과 다릅니다 (검증값 기준으로 정정).")
    lines.append("- 응답 본문의 크기·길이 서술은 검증값이 아니며, 위 값이 기준입니다.")
    return "\n".join(lines) + "\n"


@final
class ResumeJoiner:
    """r37: stitches the first resumed body text onto the paused output at the streaming cursor.

    All lengths are Python ``str`` character counts (never UTF-8 bytes). The pause cursor may sit
    mid-line; the resumed model then typically restarts that line. Body chunks are buffered only
    until the restart can be decided (buffer >= the open partial line, or a newline arrived, or the
    stream ended); then an *exact* restart of the open partial line (or of the last complete line)
    is dropped once, and everything else is appended verbatim. Nothing already in ``prior`` is
    ever deleted, and no text other than an exact boundary restart is removed."""

    def __init__(self, prior: str) -> None:
        self._prior = prior
        if prior and not prior.endswith("\n"):
            self._partial = prior.rsplit("\n", 1)[-1]
            self._last_full = ""
        else:
            self._partial = ""
            stripped = prior.rstrip("\n")
            self._last_full = stripped.rsplit("\n", 1)[-1] if stripped else ""
        self._buffer = ""
        self._decided = not prior
        self.dropped_chars = 0

    @property
    def decided(self) -> bool:
        return self._decided

    def feed(self, chunk: str) -> str:
        if self._decided:
            return chunk
        self._buffer += chunk
        need = len(self._partial or self._last_full)
        if len(self._buffer) < need and "\n" not in self._buffer:
            return ""
        return self._decide()

    def flush(self) -> str:
        if self._decided:
            return ""
        return self._decide()

    def _decide(self) -> str:
        self._decided = True
        text, self._buffer = self._buffer, ""
        if self._partial and text.startswith(self._partial):
            self.dropped_chars = len(self._partial)
            return text[len(self._partial) :]
        if self._last_full:
            first, sep, rest = text.partition("\n")
            if first.strip() == self._last_full.strip() and (sep or len(first) >= len(self._last_full)):
                self.dropped_chars = len(first) + len(sep)
                return rest
        return text


def join_resume_chunk(prior: str, chunk: str) -> str:
    """r34: first body chunk after resume.

    The pause cursor may sit mid-line (token streaming), so the chunk is appended verbatim —
    no separator is invented. Only when the prior output ended on a complete line and the
    model re-emits that exact line first is the repeat dropped (duplicate guard). Banner
    display events never reach here (filtered by is_orchestrator_banner_chunk), which is what
    removes the r32 "🏢 1. 🛡️ ..." splice.
    """
    if not prior or not prior.endswith("\n"):
        return chunk
    last_line = prior.rstrip("\n").rsplit("\n", 1)[-1].strip()
    first, sep, rest = chunk.partition("\n")
    if last_line and first.strip() == last_line:
        return rest if sep else ""
    return chunk


@final
class BackgroundTaskRunner:
    """
    장기 실행 태스크의 비동기 실행 및 Checkpoint 관리.

    Codex의 durable execution 패턴을 로컬 환경에 이식:
    - 태스크를 백그라운드 스레드에서 실행
    - 중간 체크포인트를 SQLite에 저장
    - 중단 시 마지막 체크포인트에서 재개 가능
    """

    def __init__(
        self,
        db_path: str | None = None,
        vault_engine: object | None = None,
        state_store: TaskStateStore | None = None,
        outcome_recorder: Callable[[TaskOutcome], object] | None = None,
    ):
        if db_path is None:
            configured_path = os.environ.get("AGK_TASK_DB_PATH", "").strip()
            if configured_path:
                db_path = configured_path
            else:
                try:
                    from antigravity_k.config import config

                    base_dir = config.paths.data_dir
                    base_dir.mkdir(parents=True, exist_ok=True)
                    test_file = base_dir / f".agk_write_test_{os.getpid()}"
                    test_file.touch()
                    test_file.unlink()
                except OSError:
                    base_dir = Path.home() / ".antigravity-k" / "data"
                    base_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(base_dir / "tasks.db")

        self.db_path = db_path
        self.vault_engine = vault_engine  # W-6: DI 패턴으로 순환참조 제거
        self.state_store = state_store or TaskStateStore(db_path)
        self.outcome_recorder = outcome_recorder
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._steering = TaskSteeringQueue()
        self.worktree_manager = WorktreeManager()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:  # pyright: ignore[reportUnusedFunction]
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _ = conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        self.state_store.initialize()

    def submit_task(
        self,
        prompt: str,
        context: Mapping[str, object] | None = None,
        orchestrator: object | None = None,
        target_model: str = "",
        use_worktree: bool = False,
        idempotency_key: str | None = None,
        owner_subject: str = "loopback",
    ) -> str:
        """
        태스크를 백그라운드 스레드에 제출합니다.

        Returns:
            task_id: 고유 태스크 ID
        """
        task_context = dict(context or {})
        task_context[REQUEST_TOOL_POLICY_KEY] = snapshot_tool_policy()
        # ContextVars are not inherited by the worker thread. Replace any client
        # value with the server's decision and persist the restriction for resume.
        task_context[_BOOKKEEPING_READ_ONLY] = _request_restricts_bookkeeping()
        if "allowed_tools" in task_context:
            # r41: server-side per-task tool allowlist, enforced by ToolExecutor.
            from antigravity_k.engine.task_tool_contract import normalize_allowed_tools

            allowed = normalize_allowed_tools(task_context["allowed_tools"])
            task_context["allowed_tools"] = allowed
            usable = [tool for tool, quota in (allowed or {}).items() if quota > 0]
            if allowed is not None and not usable:
                task_context["direct_response"] = True
            elif usable and not task_context.get("expected_tools"):
                task_context["expected_tools"] = usable
        if use_worktree:
            task_context["use_worktree"] = True
            _ = task_context.setdefault("persist_context_snapshot", True)
        if self._should_use_direct_response(prompt, task_context, use_worktree):
            task_context["direct_response"] = True
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(UTC).isoformat()
        stored_task_id = self.state_store.create_task(
            task_id,
            prompt,
            TaskStatus.PENDING,
            created_at,
            idempotency_key=idempotency_key,
            owner_subject=owner_subject,
        )
        if stored_task_id != task_id:
            return stored_task_id

        task = BackgroundTask(task_id, prompt, task_context, owner_subject=owner_subject)
        self._save_checkpoint(task_id, 0, task.context, "")

        if use_worktree:
            try:
                task.worktree_path = self.worktree_manager.create_worktree(task_id)
            except Exception:
                logger.exception("Failed to create worktree")

        with self._lock:
            self._tasks[task_id] = task

        # 백그라운드 스레드 시작
        thread = threading.Thread(
            target=self._run_task,
            args=(task, orchestrator, target_model),
            name=f"bg-{task_id}",
            daemon=True,
        )
        task.attach_thread(thread)
        thread.start()

        logger.info("Background task submitted: %s", task_id)
        return task_id

    @staticmethod
    def _should_use_direct_response(prompt: str, context: TaskContext, use_worktree: bool) -> bool:
        configured_mode = context.get("direct_response")
        if isinstance(configured_mode, bool):
            return configured_mode
        if use_worktree or context.get("use_worktree") is True:
            return False
        expected_tools = context.get("expected_tools", ())
        if isinstance(expected_tools, str) and expected_tools.strip():
            return False
        if isinstance(expected_tools, (list, tuple, set, frozenset)) and any(
            str(tool).strip() for tool in cast(Iterable[object], expected_tools)
        ):
            return False
        prompt_lower = prompt.casefold()
        return any(marker in prompt_lower for marker in _DIRECT_RESPONSE_MARKERS)

    def cancel_task(self, task_id: str, owner_subject: str | None = None) -> bool:
        """현재 실행 중인 태스크에 중단 시그널을 보냅니다.

        bool 로 좁힌 형태다 — 거부 사유가 필요한 호출자(API)는 `cancel_verdict` 를 쓴다.
        """
        return self.cancel_verdict(task_id, owner_subject=owner_subject) == "cancelled"

    def cancel_verdict(
        self,
        task_id: str,
        owner_subject: str | None = None,
    ) -> CancellationVerdict:
        """취소의 **상세 결과** — 왜 거부됐는지까지 구분한다(F-35).

        `cancel_task` 는 이 함수를 bool 로 좁힌 것이고(기존 호출자 보존), API 는 거부 사유를
        구분해야 한다: "활성 아님"(404)과 "다른 살아 있는 프로세스가 실행 중"(409)은 다른 사건이다.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and owner_subject is not None and task.owner_subject != owner_subject:
                task = None
            if task is not None:
                if task.status in [TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    return "not_active"
                # 이 프로세스가 소유한 태스크다 — event 로 직접 멈춘다(기존 경로 그대로).
                logger.info("Sending cancel signal to task %s", task_id)
                task.cancel_event.set()
                task.status = TaskStatus.CANCELLED
                task.error = "Task was manually cancelled by the user."
                task.updated_at = datetime.now(UTC).isoformat()
                updated = self._update_db_status(task_id, TaskStatus.CANCELLED, error=task.error)
                if not updated:
                    record = self.state_store.get_task(task_id)
                    if record is not None:
                        task.status = parse_task_status(record["status"])
                        task.error = record["error"]
                _ = task_process_supervisor.cancel_task(task_id)
                return "cancelled" if updated else "not_active"
        return self.state_store.cancel_if_permitted(task_id, owner_subject=owner_subject)

    def pause_task(self, task_id: str, owner_subject: str | None = None) -> str:
        """r32: request a user pause of a task running in THIS process.

        Returns "pausing" (signal set; the runner checkpoints and CASes running->paused at the next
        chunk boundary), "not_active" (unknown/terminal/not running), or "owned_elsewhere".
        Distinct from cancel: no rollback, no worktree removal, resumable via resume_task.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and owner_subject is not None and task.owner_subject != owner_subject:
                task = None
            if task is not None:
                if task.status != TaskStatus.RUNNING:
                    return "not_active"
                task.pause_event.set()
                return "pausing"
        record = self.state_store.get_task(task_id, owner_subject=owner_subject)
        if record is None:
            return "not_active"
        return "owned_elsewhere" if record["status"] == TaskStatus.RUNNING else "not_active"

    def steer_task(self, task_id: str, instruction: str, owner_subject: str | None = None) -> TaskSteeringResult | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and owner_subject is not None and task.owner_subject != owner_subject:
                task = None
        if task is None:
            status = self.get_status(task_id, owner_subject=owner_subject)
            if status is None or status["status"] not in {TaskStatus.PENDING, TaskStatus.RUNNING}:
                return None
            return None
        if task.status not in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            return None
        request = self._steering.request(task_id, instruction)
        _ = self.state_store.append_execution_event(
            task_id,
            "task.steering.requested",
            json.dumps(
                {"steering_id": request.steering_id, "instruction": request.instruction, "mode": "queued_replay"},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        return TaskSteeringResult(status="accepted", task_id=task_id, steering_id=request.steering_id)

    @staticmethod
    def _benchmark_validation_error(task: BackgroundTask) -> str | None:
        if not isinstance(task.context.get("benchmark_case_id"), str):
            return None
        raw_keywords = task.context.get("expected_keywords", ())
        expected_keywords: tuple[str, ...]
        if isinstance(raw_keywords, str):
            expected_keywords = (raw_keywords,)
        elif isinstance(raw_keywords, (list, tuple, set, frozenset)):
            expected_keywords = tuple(str(keyword) for keyword in cast(Iterable[object], raw_keywords) if str(keyword))
        else:
            return None
        missing = [keyword for keyword in expected_keywords if keyword.lower() not in task.output.lower()]
        if not missing:
            return None
        return f"Benchmark output missing required content: {', '.join(missing)}"

    def _run_task(
        self,
        task: BackgroundTask,
        orchestrator: object | None,
        target_model: str,
        initial_step: int = 0,
        initial_output: str = "",
        claim_status: TaskStatusName = TaskStatus.PENDING,
    ):
        """백그라운드 스레드에서 실제 태스크 실행."""
        started_at = time.monotonic()
        if task.cancel_event.is_set():
            try:
                cancelled = self.state_store.transition(
                    task.task_id,
                    TaskStatus.CANCELLED,
                    error="Task was cancelled before execution started.",
                    expected_status=claim_status,
                    record_event=True,
                )
            except TaskTransitionConflictError:
                cancelled = False
            except (sqlite3.Error, InvalidTaskStatusError, InvalidTaskTransitionError):
                logger.exception("Task pre-start cancellation failed: %s", task.task_id)
                cancelled = False
            if not cancelled:
                record = self.state_store.get_task(task.task_id)
                if record is not None:
                    task.status = parse_task_status(record["status"])
                    task.error = record["error"]
                return
            task.status = TaskStatus.CANCELLED
            self._record_task_outcome(task, target_model, started_at, "cancelled")
            return

        task.output = initial_output
        task.progress = min(0.95, initial_step / 100)
        task.updated_at = datetime.now(UTC).isoformat()
        if not self._claim_task_execution(task.task_id, claim_status):
            record = self.state_store.get_task(task.task_id)
            if record is not None:
                task.status = parse_task_status(record["status"])
                task.error = record["error"]
            return
        task.status = TaskStatus.RUNNING

        # DAT-02: a worktree task executes against its own worktree, never the
        # server process cwd. Bind the execution context to the worktree root so
        # PermissionGate/tool path resolution use it as the canonical root.
        worktree_binding_token = self._bind_worktree_context(task)
        vault_engine = self.vault_engine
        output_parts = [initial_output] if initial_output else []
        step = initial_step
        joiner = ResumeJoiner(initial_output)
        try:
            if orchestrator is None:
                raise ValueError("Orchestrator is required for task execution")

            # ─── Snapshot (Filesystem Checkpoint) 생성 ───
            # W-6: 순환참조 제거 — api.server 역방향 import 대신 DI된 vault_engine 사용
            vault_engine = vault_engine or getattr(orchestrator, "vault_engine", None)

            is_read_only_benchmark = task.context.get("benchmark_read_only") is True
            if vault_engine and not is_read_only_benchmark and _task_allows_bookkeeping(task):
                try:
                    snapshot_hash = cast(VaultEnginePort, vault_engine).create_snapshot(
                        f"Pre-task checkpoint for {task.task_id}"
                    )
                    if snapshot_hash:
                        task.context["snapshot_hash"] = snapshot_hash
                        logger.info("Created pre-task snapshot: %s", snapshot_hash)
                except Exception:
                    logger.exception("Failed to create pre-task snapshot")

            messages = [{"role": "user", "content": task.prompt}]
            if task.resume_prior_output:
                messages = [
                    {"role": "assistant", "content": task.resume_prior_output[-RESUME_PRIOR_OUTPUT_CHARS:]},
                    *messages,
                ]
            restored_snapshot = load_task_context_snapshot(self.state_store, task.task_id)
            if restored_snapshot is not None:
                messages = [*restored_task_context_messages(restored_snapshot), *messages]
            from antigravity_k.engine import task_plan_state as tps

            model_context = tps.context_without_plan_state(task.context) if task.context else {}
            model_context.pop(REQUEST_TOOL_POLICY_KEY, None)
            if model_context:
                context_str = json.dumps(model_context, ensure_ascii=False)
                messages.append(
                    {"role": "system", "content": f"Task execution context: {context_str}"},
                )

            # target_model이 빈 문자열이면 오케스트레이터 기본 모델로 폴백
            if not target_model:
                get_model_for_role = getattr(orchestrator, "get_model_for_role", None)
                if not callable(get_model_for_role):
                    get_model_for_role = getattr(orchestrator, "_get_model_for_role", None)
                if not callable(get_model_for_role):
                    raise TypeError("Orchestrator does not provide a model resolver")
                target_model = cast(Callable[[str], str], get_model_for_role)("default")

            if task.context.get("persist_context_snapshot") is True:
                snapshot_messages = messages
                if len(snapshot_messages) > 256:
                    snapshot_messages = [*snapshot_messages[:16], *snapshot_messages[-240:]]
                try:
                    _ = save_task_context_snapshot(
                        self.state_store,
                        task.task_id,
                        snapshot_messages,
                        target_model,
                    )
                except ContextSnapshotStoreError as error:
                    logger.warning("Initial task context snapshot failed: %s", error, exc_info=True)

            # r33/r37: on resume the orchestrator re-emits display events (mode/CEO banners, the 🧭
            # compaction notice). In the resume prelude they are control events, not body: they are
            # recorded as execution events and never spliced into the body at the pause cursor. The
            # first body text is stitched by ResumeJoiner (cursor-aware, char counts, exact restart only).
            resume_prelude = bool(initial_output)
            from antigravity_k.engine import tool_execution_journal as tej

            # r35: restore contract — previous context restored on every exit path (incl. early returns).
            # r38: plan/step state persisted inside task.context (saved by every checkpoint) so a resume
            # continues from the first incomplete pipeline step instead of re-planning.
            raw_plan_state = task.context.setdefault(tps.PLAN_STATE_KEY, {})
            plan_state = raw_plan_state if isinstance(raw_plan_state, dict) else None
            with (
                tej.task_scope(task.task_id, claim_status == TaskStatus.RESUMING),
                _resume_prefix_scope(task.task_id, initial_output),
                tps.bind_plan_state(plan_state),
            ):
                for chunk in self._stream_task(task, orchestrator, target_model, messages):
                    match chunk:
                        case ProgressChunk():
                            is_progress = True
                            _ = self.state_store.append_execution_event(
                                task.task_id,
                                "task.stream.progress",
                                json.dumps(
                                    {
                                        "kind": "progress",
                                        "text": _redact_vault_text(str(chunk)),
                                        "source": "ProgressChunk",
                                        "step": step,
                                        "resumed": claim_status == TaskStatus.RESUMING,
                                    },
                                    ensure_ascii=False,
                                    sort_keys=True,
                                ),
                            )
                        case str():
                            is_progress = False
                        case unreachable:
                            assert_never(unreachable)
                    if resume_prelude:
                        kind = resume_control_kind(chunk)
                        if kind is not None:
                            if kind != "blank":
                                _ = self.state_store.append_execution_event(
                                    task.task_id,
                                    "task.resume.control_event",
                                    json.dumps({"kind": kind}, sort_keys=True),
                                )
                            if not is_progress:
                                continue
                        elif not is_progress:
                            resume_prelude = False
                    if not is_progress:
                        if not joiner.decided:
                            # Buffered content counts as a body step and is flushed before pause.
                            chunk = joiner.feed(chunk)
                            if joiner.decided and joiner.dropped_chars:
                                _ = self.state_store.append_execution_event(
                                    task.task_id,
                                    "task.resume.joined",
                                    json.dumps({"dropped_restart_chars": joiner.dropped_chars}, sort_keys=True),
                                )
                    if task.cancel_event.is_set():
                        logger.info("Task %s interrupted by cancel event.", task.task_id)
                        task.status = TaskStatus.CANCELLED
                        _ = self._update_db_status(
                            task.task_id,
                            TaskStatus.CANCELLED,
                            error="Task was manually cancelled.",
                        )

                        # Worktree 정리
                        if task.context.get("use_worktree", False):
                            try:
                                self.worktree_manager.remove_worktree(task.task_id)
                            except Exception:
                                logger.exception("Failed to cleanup worktree on cancellation")
                        self._rollback_snapshot(task, cast(VaultEnginePort | None, vault_engine))
                        self._record_task_outcome(task, target_model, started_at, "cancelled")
                        return

                    if not is_progress:
                        output_parts.append(chunk)
                        step += 1

                    if task.pause_event.is_set():
                        tail = joiner.flush()
                        if tail:
                            output_parts.append(tail)
                        # r32: user pause — checkpoint at the exact pause point (no rollback, no cleanup),
                        # then CAS running->paused. resume_task continues from this checkpoint.
                        task.output = "".join(output_parts)
                        task.updated_at = datetime.now(UTC).isoformat()
                        if not self._save_checkpoint(task.task_id, step, task.context, task.output):
                            raise _TaskCheckpointPersistenceError(task.task_id)
                        if self._update_db_status(task.task_id, TaskStatus.PAUSED, output=task.output):
                            task.status = TaskStatus.PAUSED
                            paused_checkpoint = self.state_store.get_last_checkpoint(task.task_id)
                            paused_step = paused_checkpoint["step"] if paused_checkpoint is not None else step
                            _ = self.state_store.append_execution_event(
                                task.task_id,
                                "task.paused",
                                json.dumps({"reason": "user_pause", "step": paused_step}, sort_keys=True),
                            )
                            self._record_task_outcome(task, target_model, started_at, "paused")
                            logger.info("Background task paused by user at step %s: %s", step, task.task_id)
                            return
                        task.pause_event.clear()

                    # 매 10스텝마다 자동 체크포인트
                    if not is_progress and step % 10 == 0:
                        tail = joiner.flush()
                        if tail:
                            output_parts.append(tail)
                        task.output = "".join(output_parts)
                        task.progress = min(0.95, step / 100)  # 추정 진행률
                        task.updated_at = datetime.now(UTC).isoformat()
                        self._save_checkpoint(task.task_id, step, task.context, task.output)

            tail = joiner.flush()
            if tail:
                output_parts.append(tail)
            task.output = "".join(output_parts)
            state_record = self.state_store.get_task(task.task_id)
            if state_record is not None and state_record["status"] == TaskStatus.PAUSED:
                task.status = TaskStatus.PAUSED
                task.updated_at = datetime.now(UTC).isoformat()
                # r32: approval pause must also leave a checkpoint, otherwise resume_task finds none
                # when fewer than 10 chunks were streamed (root cause of checkpoint_count=0).
                self._save_checkpoint(task.task_id, step, task.context, task.output)
                _ = self._update_db_status(task.task_id, TaskStatus.PAUSED, output=task.output)
                self._record_task_outcome(task, target_model, started_at, "approval_required")
                logger.info("Background task paused for approval: %s", task.task_id)
                return
            if state_record is not None and state_record["status"] == TaskStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error = str(state_record["error"] or "Task execution failed.")
                task.updated_at = datetime.now(UTC).isoformat()
                self._rollback_snapshot(task, cast(VaultEnginePort | None, vault_engine))
                completion_reason = "quality_gate_failed" if task.error.startswith("quality_gate_failed:") else "failed"
                self._record_task_outcome(task, target_model, started_at, completion_reason)
                logger.warning("Background task completed with a failed terminal state: %s", task.task_id)
                return
            # r42: a resumed segment that re-emits already-delivered lines verbatim cannot be joined
            # safely; it is neither trimmed nor reported as success.
            join_issue = resume_join_issue(initial_output, task.output) if initial_output else None
            if join_issue:
                task.status = TaskStatus.FAILED
                task.error = f"resume_join_unverified: {join_issue}"
                task.updated_at = datetime.now(UTC).isoformat()
                _ = self.state_store.append_execution_event(
                    task.task_id,
                    "task.resume.join_unverified",
                    json.dumps({"reason": join_issue, "prior_chars": len(initial_output)}, sort_keys=True),
                )
                _ = self._update_db_status(task.task_id, TaskStatus.FAILED, output=task.output, error=task.error)
                self._record_task_outcome(task, target_model, started_at, "failed")
                return
            # r42: file facts shown to the user come from the real file, never from model text.
            verified_block = _verified_artifact_block(self.state_store, task.task_id, task.output)
            if verified_block:
                task.output = task.output + verified_block
                _ = self.state_store.append_execution_event(
                    task.task_id, "task.verified_artifacts", json.dumps({"chars": len(verified_block)}, sort_keys=True)
                )
            validation_error = self._benchmark_validation_error(task)
            if validation_error:
                task.status = TaskStatus.FAILED
                task.error = validation_error
                task.updated_at = datetime.now(UTC).isoformat()
                _ = self._update_db_status(
                    task.task_id,
                    TaskStatus.FAILED,
                    output=task.output,
                    error=validation_error,
                )
                self._record_task_outcome(task, target_model, started_at, "benchmark_validation_failed")
                logger.warning("Benchmark task failed output validation: %s", task.task_id)
                return
            task.progress = 1.0
            task.status = TaskStatus.DONE
            task.updated_at = datetime.now(UTC).isoformat()

            if not self._persist_task_completion(task):
                self._record_task_outcome(
                    task,
                    target_model,
                    started_at,
                    "cancelled" if task.status == TaskStatus.CANCELLED else "failed",
                )
                return
            self._record_task_outcome(task, target_model, started_at, "done")
            logger.info("Background task completed: %s, output length: %s", task.task_id, len(task.output))

            # ─── LLM Wiki (Vault) 자동 기록: 세컨드 브레인 축적 ───
            if not is_read_only_benchmark:
                self._save_to_vault(task, orchestrator, target_model)

        except Exception as e:
            if task.status != TaskStatus.DONE:
                tail = joiner.flush()
                if tail:
                    output_parts.append(tail)
                task.output = "".join(output_parts)
                try:
                    state_record = self.state_store.get_task(task.task_id)
                except sqlite3.Error:
                    # A recovery read must not replace the original stream failure.
                    state_record = None
                    logger.warning("Task state lookup failed during failure recovery: %s", task.task_id, exc_info=True)
                if state_record is not None and state_record["status"] not in {
                    TaskStatus.DONE,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                }:
                    self._save_checkpoint(task.task_id, step, task.context, task.output)
                self._rollback_snapshot(task, cast(VaultEnginePort | None, vault_engine))
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.updated_at = datetime.now(UTC).isoformat()
            if not self._update_db_status(task.task_id, TaskStatus.FAILED, output=task.output, error=str(e)):
                record = self.state_store.get_task(task.task_id)
                if record is not None:
                    task.status = parse_task_status(record["status"])
                    task.output = record["output"] or ""
                    task.error = record["error"]
            self._record_task_outcome(task, target_model, started_at, "failed")
            logger.exception("Background task failed: %s, error", task.task_id)

        finally:
            _reset_worktree_context(worktree_binding_token)
            if task.worktree_path and task.status != TaskStatus.PAUSED:
                self.worktree_manager.remove_worktree(task.task_id)

    def _persist_task_completion(self, task: BackgroundTask) -> bool:
        """Accept the atomic terminal winner; fail a completion write that did not commit."""
        record = self.state_store.get_task(task.task_id)
        if record is not None and record["status"] == TaskStatus.DONE:
            task.output = record["output"] or ""
            task.error = record["error"]
            return True
        if self._update_db_status(task.task_id, TaskStatus.DONE, output=task.output):
            return True

        record = self.state_store.get_task(task.task_id)
        if record is not None and record["status"] in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            task.status = parse_task_status(record["status"])
            task.output = record["output"] or ""
            task.error = record["error"]
            return task.status == TaskStatus.DONE

        task.status = TaskStatus.FAILED
        task.error = "Task completion status could not be persisted."
        if not self._update_db_status(task.task_id, TaskStatus.FAILED, output=task.output, error=task.error):
            record = self.state_store.get_task(task.task_id)
            if record is not None:
                task.status = parse_task_status(record["status"])
                task.output = record["output"] or ""
                task.error = record["error"]
        return task.status == TaskStatus.DONE

    def _bind_worktree_context(self, task: BackgroundTask) -> Token[RequestExecutionContext | None] | None:
        """Bind RequestExecutionContext to the task's worktree (DAT-02).

        Worktree tasks must execute tools against the worktree root regardless
        of the ambient request/session binding (server cwd=A, project=B rule).
        Returns a reset token for :func:`_reset_worktree_context`.
        """
        if not task.worktree_path:
            return self._bind_task_project_context(task)
        try:
            from antigravity_k.api.contracts.execution_context import RequestExecutionContext
            from antigravity_k.api.project_binding import (
                get_bound_request_execution_context,
                set_bound_request_execution_context,
            )

            ambient = get_bound_request_execution_context()
            worktree_root = os.path.realpath(task.worktree_path)
            if ambient is not None:
                context = ambient.model_copy(
                    update={
                        "canonical_project_root": worktree_root,
                        "request_id": f"{ambient.request_id}#wt-{task.task_id}",
                        "task_id": task.task_id,
                    },
                )
            else:
                context = RequestExecutionContext(
                    request_id=f"task-{task.task_id}",
                    task_id=task.task_id,
                    project_id=f"worktree:{task.task_id}",
                    canonical_project_root=worktree_root,
                    conversation_id="conv_task_worktree",
                    conversation_revision=0,
                    actor_subject=task.owner_subject or "task-runner",
                    session_id=f"task-{task.task_id}",
                    model_id="task-worktree",
                )
            return set_bound_request_execution_context(context)
        except Exception:
            logger.exception("Worktree context binding failed for task %s", task.task_id)
            return None

    def merge_worktree_changes(
        self,
        task_id: str,
        worktree_path: str,
        *,
        merge_on_failure: bool = False,
    ) -> bool:
        """Merge a successful task's worktree commit into the base branch.

        DAT-02 contract: merge-back runs only for terminal-success tasks (or
        when ``merge_on_failure`` is explicitly True). Conflicts leave the base
        branch untouched (original preserved) and return False — never an
        automatic overwrite.

        Requires the worktree to be on a task branch with a committed state;
        uncommitted work in the worktree is committed first with a task marker.
        """
        del task_id  # reserved for audit/event correlation in a later phase
        repo = self.worktree_manager.base_repo_path
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            if status.stdout.strip():
                _ = subprocess.run(
                    ["git", "add", "-A"],
                    cwd=worktree_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                _ = subprocess.run(
                    ["git", "commit", "-m", "[Task] Worktree merge-back checkpoint"],
                    cwd=worktree_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            branch_res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            task_branch = branch_res.stdout.strip()
            if not task_branch or task_branch == "HEAD":
                logger.error("Worktree %s is not on a branch; refusing merge-back", worktree_path)
                return False

            # Fail-fast conflict probe (git ≥2.38 merge-tree --write-tree):
            # detect a conflicting merge before touching the base branch so the
            # original state is always preserved on conflict.
            base_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            task_head = subprocess.run(
                ["git", "rev-parse", task_branch],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            probe = subprocess.run(
                ["git", "merge-tree", "--write-tree", base_head, task_head],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if probe.returncode != 0:
                logger.error(
                    "Merge-back conflict detected for branch %s; base branch preserved",
                    task_branch,
                )
                return False

            merge = subprocess.run(
                ["git", "merge", "--no-ff", "-m", f"Merge task worktree: {task_branch}", task_branch],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if merge.returncode != 0:
                # Never leave the shared repo mid-merge; keep the original state.
                _ = subprocess.run(
                    ["git", "merge", "--abort"],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                )
                logger.error("Merge-back failed for %s; base branch preserved: %s", task_branch, merge.stderr)
                return False
            logger.info("Merged task worktree branch %s into base", task_branch)
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Merge-back process failed: %s", _stderr_text(e))
            return False
        except Exception:
            logger.exception("Unexpected merge-back failure")
            return False

    def _rollback_snapshot(self, task: BackgroundTask, vault_engine: VaultEnginePort | None) -> None:
        """Roll back only the paths this task owns (DAT-02 / BR-01).

        The scope is always non-empty so the restore call can never degrade
        into a full-tree ``git reset --hard`` that would destroy concurrent
        tasks' committed, uncommitted, and untracked changes.
        """
        if not _task_allows_bookkeeping(task):
            return
        snapshot_hash = task.context.get("snapshot_hash")
        if not isinstance(snapshot_hash, str) or vault_engine is None:
            return
        scope = _task_rollback_scope(task)
        try:
            if vault_engine.restore_snapshot(snapshot_hash, scope=scope):
                logger.info(
                    "Rolled back task %s to snapshot %s (scoped: %d paths)",
                    task.task_id,
                    snapshot_hash,
                    len(scope),
                )
            else:
                logger.error("Snapshot rollback was rejected for task %s", task.task_id)
        except Exception:
            logger.exception("Snapshot rollback failed for task %s", task.task_id)

    @staticmethod
    def _bind_task_project_context(task: "BackgroundTask") -> "Token[RequestExecutionContext | None] | None":
        """r36: a non-worktree task runs in a fresh thread with no request context, so tools fell
        back to the process cwd (r35 A2 wrote into the app data dir). Re-bind the immutable
        execution context stored on the task at submit time (WS-01)."""
        raw = task.context.get("execution_context")
        if not isinstance(raw, dict):
            return None
        try:
            from antigravity_k.api.contracts.execution_context import RequestExecutionContext
            from antigravity_k.api.project_binding import set_bound_request_execution_context

            context = RequestExecutionContext.model_validate(raw)
            if not context.canonical_project_root:
                return None
            return set_bound_request_execution_context(context)
        except Exception:
            logger.exception("Task project context binding failed for task %s", task.task_id)
            return None

    def _stream_task(
        self,
        task: BackgroundTask,
        orchestrator: object,
        target_model: str,
        messages: list[dict[str, str]],
    ) -> Iterator[str]:
        binding: AbstractContextManager[None] = nullcontext()
        if isinstance(orchestrator, TaskExecutionBindingPort):
            binding = orchestrator.bind_task_execution(task.task_id, self.state_store)
        policy_binding: AbstractContextManager[None] = nullcontext()
        if REQUEST_TOOL_POLICY_KEY in task.context:
            policy_binding = bind_tool_policy(
                parse_tool_policy_snapshot(_JSON_VALUE_ADAPTER.validate_python(task.context[REQUEST_TOOL_POLICY_KEY]))
            )
        with policy_binding, binding:
            port = cast(OrchestratorPort, orchestrator)
            while True:
                if self._apply_pending_steering(task, messages):
                    continue
                restarted = False
                for chunk in port.run_stream(messages=messages, target_model=target_model):
                    yield chunk
                    restarted = self._apply_pending_steering(task, messages)
                    if restarted:
                        break
                if not restarted:
                    return

    def _apply_pending_steering(self, task: BackgroundTask, messages: list[dict[str, str]]) -> bool:
        pending = self._steering.drain(task.task_id)
        if pending:
            # r38: steering changes the request, so a stored plan no longer applies (re-plan as before).
            from antigravity_k.engine import task_plan_state as tps

            raw_state = task.context.get(tps.PLAN_STATE_KEY)
            tps.reset_plan_state(raw_state if isinstance(raw_state, dict) else None)
        for request in pending:
            messages.append({"role": "user", "content": f"[Active-turn steering]\n{request.instruction}"})
            _ = self.state_store.append_execution_event(
                task.task_id,
                "task.steering.applied",
                json.dumps({"steering_id": request.steering_id, "mode": "queued_replay"}, sort_keys=True),
            )
        return bool(pending)

    def _record_task_outcome(
        self,
        task: BackgroundTask,
        target_model: str,
        started_at: float,
        completion_reason: str,
    ) -> None:
        if self.outcome_recorder is None:
            return

        try:
            from antigravity_k.engine.tool_call_parser import EventType, ToolCallParser

            parser = ToolCallParser()
            events = parser.feed(task.output) + parser.flush()
            used_tools = tuple(
                dict.fromkeys(
                    event.tool_call.name
                    for event in events
                    if event.type == EventType.TOOL_CALL_COMPLETE and event.tool_call is not None
                ),
            )
            expected_tools_raw = task.context.get("expected_tools", ())
            expected_tools: tuple[str, ...]
            if isinstance(expected_tools_raw, str):
                expected_tools = (expected_tools_raw,)
            elif isinstance(expected_tools_raw, (list, tuple, set, frozenset)):
                expected_tools = tuple(str(tool) for tool in cast(Iterable[object], expected_tools_raw))
            else:
                expected_tools = ()
            benchmark_case_id = task.context.get("benchmark_case_id")
            case_id = benchmark_case_id if isinstance(benchmark_case_id, str) and benchmark_case_id else task.task_id
            retry_count = task.context.get("retry_count", 0)
            cost_usd = task.context.get("cost_usd", 0.0)
            outcome = TaskOutcome(
                case_id=case_id,
                target=target_model,
                success=task.status == TaskStatus.DONE,
                completion_reason=completion_reason,
                expected_tools=expected_tools,
                used_tools=used_tools,
                retry_count=int(retry_count) if isinstance(retry_count, (int, float, str)) else 0,
                latency_ms=(time.monotonic() - started_at) * 1000,
                tokens_in=len(task.prompt) // 4,
                tokens_out=len(task.output) // 4,
                cost_usd=float(cost_usd) if isinstance(cost_usd, (int, float, str)) else 0.0,
                error=task.error or "",
                calibration_eligible=isinstance(benchmark_case_id, str) and bool(benchmark_case_id),
            )
            _ = self.outcome_recorder(outcome)
        except Exception:
            logger.exception("Task outcome recording failed: %s", task.task_id)

    def get_status(self, task_id: str, owner_subject: str | None = None) -> TaskInfo | None:
        """태스크 진행 상태를 조회합니다."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and owner_subject is not None and task.owner_subject != owner_subject:
                task = None

        if task:
            info = task.to_dict()
            # r33: report the stored count (a resumed task's in-memory list starts from one seed).
            info["checkpoint_count"] = self.state_store.checkpoint_counts([task_id]).get(task_id, 0)
            return info

        record = self.state_store.get_task(task_id, owner_subject=owner_subject)
        if record:
            count = self.state_store.checkpoint_counts([task_id]).get(task_id, 0)
            return self._record_info(record, has_checkpoint=count > 0, checkpoint_count=count)
        return None

    @staticmethod
    def _record_info(record: TaskRecord, *, has_checkpoint: bool, checkpoint_count: int) -> TaskInfo:
        """DB 행 → 보고용 정보. **파생 필드가 생기는 자리**(F-36).

        `status` 는 저장된 값을 **그대로** 말한다(정책을 바꾸지 않는다 — 재시작이 고아 행을
        자동으로 끝내면 재개 가능성이 사라진다). 대신 `execution_owner` 와 `resumable` 이
        "그 상태가 지금 사실인가, 복구할 수 있는가"를 말한다. 둘 다 **저장하지 않는다**.
        """
        raw_status = str(record["status"])
        owner_pid_value = record.get("owner_pid")
        return {
            "task_id": record["task_id"],
            "prompt": record["prompt"][:100],
            "status": record["status"],
            "output_length": len(record["output"]),
            "error": record["error"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "completed_at": record["completed_at"],
            "version": record["version"],
            "checkpoint_count": checkpoint_count,
            "execution_owner": execution_owner_of(raw_status, owner_pid_value),
            "resumable": resumable_task(raw_status, owner_pid_value, has_checkpoint),
        }

    def list_tasks(self, limit: int = 20, owner_subject: str | None = None) -> list[TaskInfo]:
        """최근 태스크 목록을 반환합니다."""
        results: list[TaskInfo] = []

        # 메모리의 활성 태스크
        with self._lock:
            for task in self._tasks.values():
                if owner_subject is not None and task.owner_subject != owner_subject:
                    continue
                results.append(task.to_dict())

        # DB의 히스토리 (활성 태스크와 중복 제거)
        active_ids = {str(r["task_id"]) for r in results}
        records = [
            record
            for record in self.state_store.list_tasks(limit, owner_subject=owner_subject)
            if record["task_id"] not in active_ids
        ]
        # 체크포인트 유무는 **한 번의 질의**로 모은다(행마다 질의하면 목록 하나가 N번 질의한다).
        counts = self.state_store.checkpoint_counts([str(record["task_id"]) for record in records])
        for record in records:
            count = counts.get(str(record["task_id"]), 0)
            info = self._record_info(record, has_checkpoint=count > 0, checkpoint_count=count)
            info.pop("output_length", None)
            info.pop("completed_at", None)
            results.append(info)

        return sorted(results, key=lambda x: str(x.get("created_at", "")), reverse=True)[:limit]

    def get_output(self, task_id: str, owner_subject: str | None = None) -> str | None:
        """완료된 태스크의 전체 출력을 반환합니다."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and owner_subject is not None and task.owner_subject != owner_subject:
                task = None
            if task:
                return task.output

        record = self.state_store.get_task(task_id, owner_subject=owner_subject)
        if record:
            return record["output"]
        return None

    def wait_task(self, task_id: str, timeout: float | None = None) -> TaskInfo | None:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is not None:
            task.join(timeout)
        return self.get_status(task_id)

    def _save_checkpoint(self, task_id: str, step: int, context: TaskContext, output: str) -> bool:
        """체크포인트를 DB에 저장합니다."""
        try:
            checkpoint_context = dict(context)
            checkpoint_step = step
            checkpoint = self.state_store.get_last_checkpoint(task_id)
            if checkpoint is not None:
                # Completed tool rounds may be ahead of streamed body chunks.
                # Reuse known progress so this later output wins at the same step.
                checkpoint_step = max(step, checkpoint["step"])
                try:
                    previous_context = cast(object, json.loads(checkpoint["context_json"]))
                except (json.JSONDecodeError, TypeError) as error:
                    raise InvalidToolPolicySnapshotError from error
                if isinstance(previous_context, dict):
                    previous_context_map = cast(dict[str, object], previous_context)
                    if REQUEST_TOOL_POLICY_KEY in previous_context_map:
                        saved_policy = parse_tool_policy_snapshot(
                            _JSON_VALUE_ADAPTER.validate_python(previous_context_map[REQUEST_TOOL_POLICY_KEY])
                        )
                        checkpoint_context[REQUEST_TOOL_POLICY_KEY] = serialize_tool_policy(
                            narrow_tool_policy(saved_policy, get_tool_policy())
                        )
                    elif get_tool_policy() is not None:
                        checkpoint_context[REQUEST_TOOL_POLICY_KEY] = snapshot_tool_policy()
                    else:
                        checkpoint_context.pop(REQUEST_TOOL_POLICY_KEY, None)
                    tool_loop = previous_context_map.get("tool_loop")
                    if isinstance(tool_loop, dict):
                        # ToolLoop persists producer state directly. A resumed
                        # task's in-memory copy must not overwrite its newer evidence.
                        checkpoint_context["tool_loop"] = tool_loop
                else:
                    raise InvalidToolPolicySnapshotError
            self.state_store.save_checkpoint(
                task_id,
                checkpoint_step,
                json.dumps(checkpoint_context, ensure_ascii=False),
                output,
            )
            logger.debug("Checkpoint saved: %s at step %s", task_id, checkpoint_step)
            with self._lock:
                live = self._tasks.get(task_id)
            if live is not None:
                live.checkpoints.append(TaskCheckpoint(task_id, checkpoint_step, dict(context), output))
            return True
        except Exception:
            logger.exception("Checkpoint save failed")
            return False

    def _save_to_vault(
        self,
        task: BackgroundTask,
        orchestrator: object | None = None,
        target_model: str = "",
    ) -> None:
        """태스크 완료 결과를 Vault에 기록하여 세컨드 브레인 메모리로 축적.
        Orchestrator가 주어지면 LLM을 통해 기억을 정제(Consolidation)합니다.
        target_model이 주어지면 정제에 그 모델을 사용합니다.
        """
        if not _task_allows_bookkeeping(task):
            return
        try:
            # W-6: 순환참조 제거 — DI된 vault_engine 또는 orchestrator에서 추출
            orchestrator_vault = (
                cast(VaultEnginePort | None, getattr(orchestrator, "vault_engine", None))
                if orchestrator is not None
                else None
            )
            vault_engine = self.vault_engine or orchestrator_vault

            if not vault_engine:
                logger.warning("VaultEngine is not available. Skipping vault record.")
                return

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f".agent/tasks/task_{task.task_id[:8]}_{timestamp}.md"
            safe_prompt = _redact_vault_text(task.prompt)
            safe_output = _redact_vault_text(task.output)
            safe_context = strip_credentials(_JSON_VALUE_ADAPTER.validate_python(task.context))

            # 컨텍스트와 결과를 마크다운으로 포맷팅
            context_md = ""
            if task.context:
                context_md = (
                    "## Context\n```json\n" + json.dumps(safe_context, ensure_ascii=False, indent=2) + "\n```\n\n"
                )

            # --- 1. Memory Consolidation (기억 정제 및 도구 이력 추출) ---
            summary_content = ""
            if orchestrator is not None and task.output:
                try:
                    import re

                    summary_prompt = (
                        "당신은 에이전트의 작업 로그를 분석하여 세컨드 브레인(Wiki)에 저장할 핵심 기억(Memory)을 추출하는 전문가입니다.\n"  # noqa: E501
                        f"아래는 에이전트가 수행한 작업의 로그입니다.\n\n"
                        f"<task_prompt>\n{safe_prompt}\n</task_prompt>\n\n"
                        f"<task_output>\n{safe_output[-6000:]}\n</task_output>\n\n"
                        "다음 항목을 마크다운 포맷으로 작성해주세요:\n"
                        "1. **핵심 요약 (Lessons Learned)**: 이 작업에서 성공적으로 해결한 문제와 배운 점을 3~4줄로 요약.\n"  # noqa: E501
                        "2. **도구 및 에러 이력 (Tool Trajectory)**: 사용한 주요 도구들과 직면했던 에러, 그리고 어떻게 극복했는지 간략히 기록."  # noqa: E501
                    )

                    get_model_for_role = getattr(orchestrator, "get_model_for_role", None)
                    if not callable(get_model_for_role):
                        get_model_for_role = getattr(orchestrator, "_get_model_for_role", None)
                    if not callable(get_model_for_role):
                        raise TypeError("Orchestrator does not provide a model resolver")
                    summarizer_model = target_model or cast(Callable[[str], str], get_model_for_role)("default")

                    manager = cast(ModelManagerPort | None, getattr(orchestrator, "manager", None))
                    if manager is None:
                        raise TypeError("Orchestrator does not provide a model manager")
                    if not _task_allows_bookkeeping(task):
                        return
                    response_gen = manager.stream_generate(
                        prompt=summary_prompt,
                        target=summarizer_model,
                        raw_messages=[{"role": "user", "content": summary_prompt}],
                        system_prompt="출력은 오직 마크다운으로 작성된 분석 결과여야 합니다. 불필요한 서론/결론은 생략하세요. /no_think",  # noqa: E501
                    )

                    extracted_text = ""
                    for chunk in response_gen:
                        extracted_text += chunk

                    extracted_text = re.sub(r"<think>.*?</think>", "", extracted_text, flags=re.DOTALL).strip()

                    if extracted_text:
                        summary_content = (
                            f"## 🧠 Memory Consolidation (자가 학습)\n\n{_redact_vault_text(extracted_text)}\n\n"
                        )
                except Exception:
                    logger.exception("Memory consolidation failed")
                    summary_content = "## 🧠 Memory Consolidation\n\n*(요약 생성에 실패했습니다)*\n\n"

            # --- 2. 최종 마크다운 조합 ---
            content = f"# Task: {safe_prompt[:50]}...\n\n"
            content += f"**Task ID**: {task.task_id}\n"
            content += f"**Status**: {task.status}\n"
            content += f"**Date**: {task.updated_at}\n\n"
            content += f"## Prompt\n{safe_prompt}\n\n"
            content += context_md
            content += summary_content
            content += f"## Raw Result\n\n<details>\n<summary>전체 로그 보기</summary>\n\n{safe_output}\n\n</details>\n"

            metadata = {
                "type": "background_task",
                "task_id": task.task_id,
                "date": task.updated_at,
                "tags": ["task", "history", "memory"],
            }

            if not _task_allows_bookkeeping(task):
                return
            _ = cast(VaultEnginePort, vault_engine).write_note(
                relative_path=filename,
                metadata=metadata,
                content=content,
                commit_message=f"Agent memory recorded with consolidation for task {task.task_id}",
            )
            logger.info("Task memory saved to vault: %s", filename)
        except Exception:
            logger.exception("Failed to save task result to vault")

    def get_last_checkpoint(self, task_id: str, owner_subject: str | None = None) -> CheckpointInfo | None:
        """마지막 체크포인트를 조회합니다."""
        checkpoint = self.state_store.get_last_checkpoint(task_id, owner_subject=owner_subject)
        if checkpoint:
            try:
                raw_context = cast(object, json.loads(checkpoint["context_json"]))
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(raw_context, dict):
                return None
            context = cast(TaskContext, raw_context)
            return {
                "task_id": checkpoint["task_id"],
                "step": checkpoint["step"],
                "context": context,
                "output_so_far": checkpoint["output_so_far"],
                "created_at": checkpoint["created_at"],
            }
        return None

    def resume_task(
        self,
        task_id: str,
        orchestrator: object | None = None,
        target_model: str = "",
        owner_subject: str | None = None,
    ) -> bool:
        """마지막 체크포인트에서 태스크를 재개합니다."""
        checkpoint = self.get_last_checkpoint(task_id, owner_subject=owner_subject)
        if not checkpoint:
            logger.warning("No checkpoint found for task %s", task_id)
            return False

        # 원래 프롬프트 조회
        record = self.state_store.get_task(task_id, owner_subject=owner_subject)
        if not record:
            return False
        checkpoint_context = checkpoint["context"]
        if REQUEST_TOOL_POLICY_KEY in checkpoint_context:
            try:
                saved_policy = parse_tool_policy_snapshot(
                    _JSON_VALUE_ADAPTER.validate_python(checkpoint_context[REQUEST_TOOL_POLICY_KEY])
                )
            except (InvalidToolPolicySnapshotError, ValidationError):
                logger.warning("Invalid saved request tool policy for task %s", task_id)
                return False
            checkpoint_context[REQUEST_TOOL_POLICY_KEY] = serialize_tool_policy(
                narrow_tool_policy(saved_policy, get_tool_policy())
            )
        elif get_tool_policy() is not None:
            checkpoint_context[REQUEST_TOOL_POLICY_KEY] = snapshot_tool_policy()
        if not self.state_store.prepare_resume(task_id, owner_subject=owner_subject):
            return False

        # 체크포인트 컨텍스트로 새 태스크 생성
        # A missing/invalid legacy decision cannot prove permission. A new
        # restriction can narrow a resume; current full access cannot lift one.
        checkpoint_context[_BOOKKEEPING_READ_ONLY] = (
            checkpoint_context.get(_BOOKKEEPING_READ_ONLY) is not False or _request_restricts_bookkeeping()
        )
        checkpoint_step = checkpoint["step"]
        checkpoint_output = checkpoint["output_so_far"]
        if not self._save_checkpoint(task_id, checkpoint_step, checkpoint_context, checkpoint_output):
            _ = self._update_db_status(
                task_id, TaskStatus.FAILED, error="Resume policy checkpoint could not be persisted."
            )
            return False
        working_memory = checkpoint_context.get("working_memory", "")
        working_memory_block = (
            f"Working memory state:\n{working_memory}\n"
            if isinstance(working_memory, str) and working_memory.strip()
            else ""
        )
        # r33: the previous output is model text, not a user request. It goes in as an assistant
        # turn (see _run_task) so preflight/quality checks evaluate only the user's own request.
        resume_prompt = (
            f"{record['prompt']}\n\n"
            f"[RESUMING FROM CHECKPOINT at step {checkpoint_step}]\n"
            f"{working_memory_block}"
            f"{RESUME_CONTINUE_INSTRUCTION}"
        )

        task = BackgroundTask(
            task_id,
            resume_prompt,
            checkpoint_context,
            owner_subject=owner_subject or "loopback",
        )
        task.output = checkpoint_output
        task.resume_prior_output = checkpoint_output
        task.checkpoints.append(TaskCheckpoint(task_id, checkpoint_step, checkpoint_context, checkpoint_output))

        with self._lock:
            self._tasks[task_id] = task

        thread = threading.Thread(
            target=self._run_task,
            args=(task, orchestrator, target_model, checkpoint_step, checkpoint_output, TaskStatus.RESUMING),
            name=f"bg-resume-{task_id}",
            daemon=True,
        )
        task.attach_thread(thread)
        thread.start()

        logger.info("Task resumed from checkpoint: %s at step %s", task_id, checkpoint_step)
        return True

    def _claim_task_execution(self, task_id: str, expected_status: TaskStatusName) -> bool:
        try:
            return self.state_store.transition(
                task_id,
                TaskStatus.RUNNING,
                expected_status=expected_status,
                record_event=True,
            )
        except TaskTransitionConflictError:
            logger.info("Task execution claim lost: %s", task_id)
            return False
        except (sqlite3.Error, InvalidTaskStatusError, InvalidTaskTransitionError):
            logger.exception("Task execution claim failed: %s", task_id)
            return False

    def _update_db_status(
        self,
        task_id: str,
        status: TaskStatusName,
        output: str | None = None,
        error: str | None = None,
    ) -> bool:
        """DB에 태스크 상태를 업데이트합니다."""
        try:
            return self.state_store.transition(task_id, status, output=output, error=error, record_event=True)
        except (sqlite3.Error, InvalidTaskStatusError, InvalidTaskTransitionError, TaskTransitionConflictError):
            logger.exception("DB status update failed")
            return False


# ── 싱글톤 인스턴스 ──
_task_runner: BackgroundTaskRunner | None = None


def get_task_runner() -> BackgroundTaskRunner:
    global _task_runner
    if _task_runner is None:
        _task_runner = BackgroundTaskRunner()
    return _task_runner
