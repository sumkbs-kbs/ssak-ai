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
from contextlib import AbstractContextManager, nullcontext
from contextvars import Token
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypedDict, cast, final, runtime_checkable

from pydantic import JsonValue, TypeAdapter

from antigravity_k.engine.benchmark_harness import TaskOutcome
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

TaskContext: TypeAlias = dict[str, object]
TaskInfo: TypeAlias = dict[str, object]


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
        self.checkpoints: list[TaskCheckpoint] = []
        self._thread: threading.Thread | None = None
        self.worktree_path: str | None = None
        self.vault_writes: set[str] = set()

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
        try:
            if orchestrator is None:
                raise ValueError("Orchestrator is required for task execution")

            # ─── Snapshot (Filesystem Checkpoint) 생성 ───
            # W-6: 순환참조 제거 — api.server 역방향 import 대신 DI된 vault_engine 사용
            vault_engine = vault_engine or getattr(orchestrator, "vault_engine", None)

            is_read_only_benchmark = task.context.get("benchmark_read_only") is True
            if vault_engine and not is_read_only_benchmark:
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
            restored_snapshot = load_task_context_snapshot(self.state_store, task.task_id)
            if restored_snapshot is not None:
                messages = [*restored_task_context_messages(restored_snapshot), *messages]
            if task.context:
                context_str = json.dumps(task.context, ensure_ascii=False)
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

            output_parts = [initial_output] if initial_output else []
            step = initial_step
            for chunk in self._stream_task(task, orchestrator, target_model, messages):
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

                output_parts.append(chunk)
                step += 1

                # 매 10스텝마다 자동 체크포인트
                if step % 10 == 0:
                    task.output = "".join(output_parts)
                    task.progress = min(0.95, step / 100)  # 추정 진행률
                    task.updated_at = datetime.now(UTC).isoformat()
                    self._save_checkpoint(task.task_id, step, task.context, task.output)

            task.output = "".join(output_parts)
            state_record = self.state_store.get_task(task.task_id)
            if state_record is not None and state_record["status"] == TaskStatus.PAUSED:
                task.status = TaskStatus.PAUSED
                task.updated_at = datetime.now(UTC).isoformat()
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

            if not self._update_db_status(task.task_id, TaskStatus.DONE, output=task.output):
                record = self.state_store.get_task(task.task_id)
                if record is not None:
                    task.status = parse_task_status(record["status"])
                    task.error = record["error"]
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
                self._rollback_snapshot(task, cast(VaultEnginePort | None, vault_engine))
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.updated_at = datetime.now(UTC).isoformat()
            if not self._update_db_status(task.task_id, TaskStatus.FAILED, error=str(e)):
                record = self.state_store.get_task(task.task_id)
                if record is not None:
                    task.status = parse_task_status(record["status"])
                    task.error = record["error"]
            self._record_task_outcome(task, target_model, started_at, "failed")
            logger.exception("Background task failed: %s, error", task.task_id)

        finally:
            _reset_worktree_context(worktree_binding_token)
            if task.worktree_path and task.status != TaskStatus.PAUSED:
                self.worktree_manager.remove_worktree(task.task_id)

    def _bind_worktree_context(self, task: BackgroundTask) -> Token[RequestExecutionContext | None] | None:
        """Bind RequestExecutionContext to the task's worktree (DAT-02).

        Worktree tasks must execute tools against the worktree root regardless
        of the ambient request/session binding (server cwd=A, project=B rule).
        Returns a reset token for :func:`_reset_worktree_context`.
        """
        if not task.worktree_path:
            return None
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
        with binding:
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
            return task.to_dict()

        record = self.state_store.get_task(task_id, owner_subject=owner_subject)
        if record:
            return self._record_info(record, has_checkpoint=self.get_last_checkpoint(task_id) is not None)
        return None

    @staticmethod
    def _record_info(record: TaskRecord, *, has_checkpoint: bool) -> TaskInfo:
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
        with_checkpoints = self.state_store.last_checkpoint_steps([str(record["task_id"]) for record in records])
        for record in records:
            info = self._record_info(record, has_checkpoint=str(record["task_id"]) in with_checkpoints)
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

    def _save_checkpoint(self, task_id: str, step: int, context: TaskContext, output: str) -> None:
        """체크포인트를 DB에 저장합니다."""
        try:
            checkpoint_context = dict(context)
            checkpoint = self.state_store.get_last_checkpoint(task_id)
            if checkpoint is not None:
                try:
                    previous_context = cast(object, json.loads(checkpoint["context_json"]))
                except (json.JSONDecodeError, TypeError):
                    previous_context = None
                if isinstance(previous_context, dict) and "tool_loop" not in checkpoint_context:
                    previous_context_map = cast(dict[str, object], previous_context)
                    tool_loop = previous_context_map.get("tool_loop")
                    if isinstance(tool_loop, dict):
                        checkpoint_context["tool_loop"] = tool_loop
            self.state_store.save_checkpoint(
                task_id,
                step,
                json.dumps(checkpoint_context, ensure_ascii=False),
                output,
            )
            logger.debug("Checkpoint saved: %s at step %s", task_id, step)
        except Exception:
            logger.exception("Checkpoint save failed")

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
            raw_context = cast(object, json.loads(checkpoint["context_json"]))
            context = cast(TaskContext, raw_context) if isinstance(raw_context, dict) else {}
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
        if not self.state_store.prepare_resume(task_id, owner_subject=owner_subject):
            return False

        # 체크포인트 컨텍스트로 새 태스크 생성
        checkpoint_context = checkpoint["context"]
        checkpoint_step = checkpoint["step"]
        checkpoint_output = checkpoint["output_so_far"]
        working_memory = checkpoint_context.get("working_memory", "")
        working_memory_block = (
            f"Working memory state:\n{working_memory}\n"
            if isinstance(working_memory, str) and working_memory.strip()
            else ""
        )
        resume_prompt = (
            f"{record['prompt']}\n\n"
            f"[RESUMING FROM CHECKPOINT at step {checkpoint_step}]\n"
            f"{working_memory_block}"
            f"Previous output:\n{checkpoint_output[-2000:]}\n"
            f"Continue from where you left off."
        )

        task = BackgroundTask(
            task_id,
            resume_prompt,
            checkpoint_context,
            owner_subject=owner_subject or "loopback",
        )
        task.output = checkpoint_output

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
            return self.state_store.transition(task_id, status, output=output, error=error)
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
