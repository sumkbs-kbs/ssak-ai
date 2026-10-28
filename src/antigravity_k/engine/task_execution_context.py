from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

from antigravity_k.engine.task_events import ExecutionEventRecord, RunEventMetadata
from antigravity_k.engine.task_process_supervisor import task_process_supervisor
from antigravity_k.engine.task_state_types import CheckpointRecord, TaskRecord, TaskStatusName


class TaskStateStoreProtocol(Protocol):
    def create_task(
        self,
        task_id: str,
        prompt: str,
        status: TaskStatusName,
        created_at: str,
        idempotency_key: str | None = None,
        owner_subject: str = "loopback",
    ) -> str: ...

    def transition(
        self,
        task_id: str,
        status: TaskStatusName,
        output: str | None = None,
        error: str | None = None,
        *,
        expected_status: TaskStatusName | str | None = None,
        expected_version: int | None = None,
        record_event: bool = False,
    ) -> bool: ...

    def get_task(self, task_id: str, owner_subject: str | None = None) -> TaskRecord | None: ...

    def save_checkpoint(self, task_id: str, step: int, context_json: str, output: str) -> None: ...

    def get_last_checkpoint(self, task_id: str, owner_subject: str | None = None) -> CheckpointRecord | None: ...

    def append_execution_event(
        self,
        task_id: str,
        event_type: str,
        payload_json: str,
        metadata: RunEventMetadata | None = None,
    ) -> int: ...

    def list_execution_events(
        self,
        task_id: str,
        after_sequence: int = 0,
        limit: int = 1_000,
        owner_subject: str | None = None,
    ) -> list[ExecutionEventRecord]: ...


@dataclass(frozen=True, slots=True)
class TaskExecutionContext:
    task_id: str
    state_store: TaskStateStoreProtocol


_task_execution_context: ContextVar[TaskExecutionContext | None] = ContextVar(
    "task_execution_context",
    default=None,
)


# r36: output already delivered before a pause/restart. The runner sets it while streaming a resumed
# task so a terminal write from inside the loop (tool_loop "done"/"paused") keeps the prior output
# instead of replacing it with only the resumed segment (intA8: 648 chars -> 35 chars).
resume_output_prefix: ContextVar[tuple[str, str]] = ContextVar("resume_output_prefix", default=("", ""))


def with_resume_prefix(task_id: str, output: str) -> str:
    owner, prefix = resume_output_prefix.get()
    if owner != task_id or not prefix or output.startswith(prefix):
        return output
    return prefix + output


def runner_owns_terminal(task_id: str) -> bool:
    """r36: True while BackgroundTaskRunner streams this task. The runner then owns the DONE write,
    which must come after the graph's cov_verify/code_review/quality_check stages (a loop-back may
    re-execute) and must carry the full streamed output, not only the tool-loop segment."""
    owner, _prefix = resume_output_prefix.get()
    return bool(task_id) and owner == task_id


def current_task_execution_context() -> TaskExecutionContext | None:
    return _task_execution_context.get()


@contextmanager
def bind_task_execution_context(execution_context: TaskExecutionContext) -> Generator[None, None, None]:
    task_process_supervisor.enter_task_scope(execution_context.task_id)
    token = _task_execution_context.set(execution_context)
    try:
        yield
    finally:
        _task_execution_context.reset(token)
        task_process_supervisor.exit_task_scope(execution_context.task_id)


__all__ = [
    "TaskExecutionContext",
    "TaskStateStoreProtocol",
    "bind_task_execution_context",
    "resume_output_prefix",
    "runner_owns_terminal",
    "with_resume_prefix",
    "current_task_execution_context",
]
