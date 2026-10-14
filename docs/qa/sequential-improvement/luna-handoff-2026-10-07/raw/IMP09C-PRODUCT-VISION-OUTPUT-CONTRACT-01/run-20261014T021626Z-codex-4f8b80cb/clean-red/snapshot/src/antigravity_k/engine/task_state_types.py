from __future__ import annotations

from typing import Final, Literal, TypedDict

TaskStatusName = Literal["pending", "running", "resuming", "done", "failed", "paused", "cancelled"]

TASK_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "running", "resuming", "done", "failed", "paused", "cancelled"},
)
# 취소의 결과 — `cancel` 이 **왜** 거부됐는지까지 구분한다. F-35: 살아 있는 다른 프로세스의 실행을
# `cancelled` 로 적으면 이력이 거짓이 된다(그 행은 끝났다고 말하고 실행은 계속된다). 그래서
# "소유자가 살아 있다"는 거부는 "활성 아님"과 **다른 결과**이고, API 도 다르게 낸다(409 대 404).
CancellationVerdict = Literal["cancelled", "not_active", "owned_elsewhere"]

TERMINAL_TASK_STATUSES: Final[frozenset[str]] = frozenset({"done", "failed", "cancelled"})
ALLOWED_TASK_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"done", "failed", "paused", "cancelled"}),
    "paused": frozenset({"running", "resuming", "cancelled"}),
    "resuming": frozenset({"running", "failed", "cancelled"}),
    "done": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

# Terminal race policy (DAT-01): first successful CAS to any terminal wins.
# cancel / completion / timeout(failed) / crash-recovery do not outrank each other once racing
# from the same expected status+version; prepare_resume remains the only path out of failed/paused.
TERMINAL_TRANSITION_PRIORITY: Final[tuple[str, ...]] = (
    "first_cas_wins",
    "terminal_fields_immutable",
    "events_follow_state",
)


class TaskRecord(TypedDict):
    task_id: str
    prompt: str
    status: str
    output: str
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None
    version: int
    # F-36: 보고 표면이 "누가 이 행을 실행 중인가"를 말할 수 있도록 조회 결과에 싣는다.
    owner_pid: int | None


class CheckpointRecord(TypedDict):
    task_id: str
    step: int
    context_json: str
    output_so_far: str
    created_at: str


class InvalidTaskTransitionError(RuntimeError):
    def __init__(self, task_id: str, current: str, requested: str) -> None:
        self.task_id: str = task_id
        self.current: str = current
        self.requested: str = requested
        super().__init__(f"Task {task_id} cannot transition from {current} to {requested}")


class TaskTransitionConflictError(RuntimeError):
    """Raised when a CAS transition matches 0 rows (lost race / stale expected)."""

    def __init__(
        self,
        task_id: str,
        *,
        requested: str,
        expected_status: str | None,
        expected_version: int | None,
        current_status: str | None = None,
        current_version: int | None = None,
    ) -> None:
        self.task_id: str = task_id
        self.requested: str = requested
        self.expected_status: str | None = expected_status
        self.expected_version: int | None = expected_version
        self.current_status: str | None = current_status
        self.current_version: int | None = current_version
        super().__init__(
            f"Task {task_id} transition conflict: requested={requested} "
            f"expected_status={expected_status!r} expected_version={expected_version!r} "
            f"current_status={current_status!r} current_version={current_version!r}"
        )


class InvalidTaskStatusError(ValueError):
    def __init__(self, status: str) -> None:
        self.status: str = status
        super().__init__(f"Unknown task status: {status}")


def parse_task_status(value: str) -> TaskStatusName:
    if value == "pending":
        return "pending"
    if value == "running":
        return "running"
    if value == "resuming":
        return "resuming"
    if value == "done":
        return "done"
    if value == "failed":
        return "failed"
    if value == "paused":
        return "paused"
    if value == "cancelled":
        return "cancelled"
    raise InvalidTaskStatusError(value)


def is_terminal_task_status(status: str) -> bool:
    return status in TERMINAL_TASK_STATUSES


__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "CheckpointRecord",
    "InvalidTaskStatusError",
    "InvalidTaskTransitionError",
    "TaskTransitionConflictError",
    "TERMINAL_TRANSITION_PRIORITY",
    "is_terminal_task_status",
    "parse_task_status",
    "TASK_STATUSES",
    "TERMINAL_TASK_STATUSES",
    "TaskRecord",
    "TaskStatusName",
]
