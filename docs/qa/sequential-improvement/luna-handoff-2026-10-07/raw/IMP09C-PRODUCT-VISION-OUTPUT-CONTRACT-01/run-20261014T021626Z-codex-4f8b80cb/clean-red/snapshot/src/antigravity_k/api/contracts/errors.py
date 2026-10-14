"""Typed boundary errors for RequestExecutionContext resolution (ARC-01).

HTTP mapping is part of the frozen contract so WS/CTX lanes and the dashboard
share one status/code vocabulary.
"""

from __future__ import annotations

from typing import Final, Mapping

from antigravity_k.api.error_handler import APIError, JsonValue

CONTEXT_ERROR_HTTP_STATUS: Final[dict[str, int]] = {
    "missing_execution_context": 400,
    "invalid_execution_context": 400,
    "invalid_conversation_revision": 400,
    "project_not_found": 404,
    "conversation_not_found": 404,
    "project_root_invalid": 403,
    "stale_conversation_revision": 409,
    "conversation_integrity_error": 409,
    "conversation_storage_migration_required": 503,
    # NX-02: journal(원본 이력) 손상/미가용은 view 와 분리해 보고한다.
    "conversation_history_corrupt": 409,
    "conversation_history_unavailable": 503,
    # NX-02 후속(ADR-DAT-02 Context 8): journal 이 정한 byte 한계를 넘어 **쓰기를 거절**한다.
    # 507 은 "데이터가 틀렸다"가 아니라 "저장 공간 한계"라 409/503 과 구분한다. 기존 데이터는
    # 지우지 않는다(운영자가 관측·회수하는 문제) — 조용한 prune 금지.
    "conversation_history_quota_exceeded": 507,
}


class ExecutionContextError(APIError):
    """Base class for ARC-01 execution-context boundary failures."""

    status_code: int = 400
    error_code: str = "invalid_execution_context"
    detail: str = "Request execution context is invalid"


class MissingExecutionContextError(ExecutionContextError):
    status_code: int = 400
    error_code: str = "missing_execution_context"
    detail: str = "Required execution context fields are missing"


class InvalidExecutionContextError(ExecutionContextError):
    status_code: int = 400
    error_code: str = "invalid_execution_context"
    detail: str = "Request execution context failed validation"


class ProjectNotFoundError(ExecutionContextError):
    status_code: int = 404
    error_code: str = "project_not_found"
    detail: str = "Project is not registered"


class ProjectRootInvalidError(ExecutionContextError):
    status_code: int = 403
    error_code: str = "project_root_invalid"
    detail: str = "Project canonical root is missing, escaped, or not a directory"


class ConversationNotFoundError(ExecutionContextError):
    status_code: int = 404
    error_code: str = "conversation_not_found"
    detail: str = "Conversation is not found for this project"


class InvalidConversationRevisionError(ExecutionContextError):
    status_code: int = 400
    error_code: str = "invalid_conversation_revision"
    detail: str = "Conversation revision must be a non-negative integer"


class StaleConversationRevisionError(ExecutionContextError):
    status_code: int = 409
    error_code: str = "stale_conversation_revision"
    detail: str = "Conversation revision does not match the authoritative store"


class ConversationIntegrityError(ExecutionContextError):
    """CR-01: stored bytes do not belong to the requested conversation identity.

    Raised instead of returning an empty/other conversation when a storage
    record is corrupt or its embedded ids do not exactly match the request.
    """

    status_code: int = 409
    error_code: str = "conversation_integrity_error"
    detail: str = "Stored conversation data does not match the requested identity"


class ConversationHistoryCorruptError(ExecutionContextError):
    """NX-02: committed journal region is unreadable (never silently skipped).

    Reported with the line number and byte offset instead of falling back to a
    "no original history" answer, so operators can quarantine and repair.
    """

    status_code: int = 409
    error_code: str = "conversation_history_corrupt"
    detail: str = "Stored conversation history (journal) is corrupt"


class ConversationHistoryUnavailableError(ExecutionContextError):
    """NX-02: journal cannot be used by this build (IO failure / newer schema)."""

    status_code: int = 503
    error_code: str = "conversation_history_unavailable"
    detail: str = "Conversation history (journal) is not readable by this build"


class ConversationHistoryQuotaExceededError(ExecutionContextError):
    """NX-02 후속(ADR-DAT-02 Context 8): 정한 byte 한계를 넘어 append 를 거절했다.

    이 오류는 **데이터 손실이 없다**는 뜻이다 — 기존 journal/view 는 그대로 남고 새 쓰기만
    거절된다. 한계를 늘리거나(환경변수) 운영자가 저장소 사용량을 회수하면 다시 쓸 수 있다.
    """

    status_code: int = 507
    error_code: str = "conversation_history_quota_exceeded"
    detail: str = "Conversation history (journal) has reached its configured byte cap"


class ConversationStorageMigrationRequiredError(ExecutionContextError):
    """CR-01: legacy (pre-v2) conversation files must be migrated first.

    The store refuses reads/writes until the one-time, verified migration has
    produced its completion marker, so new writes cannot fork the data set.
    """

    status_code: int = 503
    error_code: str = "conversation_storage_migration_required"
    detail: str = "Conversation storage migration to the v2 layout has not completed"


_ERROR_BY_CODE: Final[dict[str, type[ExecutionContextError]]] = {
    "missing_execution_context": MissingExecutionContextError,
    "invalid_execution_context": InvalidExecutionContextError,
    "project_not_found": ProjectNotFoundError,
    "project_root_invalid": ProjectRootInvalidError,
    "conversation_not_found": ConversationNotFoundError,
    "invalid_conversation_revision": InvalidConversationRevisionError,
    "stale_conversation_revision": StaleConversationRevisionError,
    "conversation_integrity_error": ConversationIntegrityError,
    "conversation_storage_migration_required": ConversationStorageMigrationRequiredError,
    "conversation_history_corrupt": ConversationHistoryCorruptError,
    "conversation_history_unavailable": ConversationHistoryUnavailableError,
    "conversation_history_quota_exceeded": ConversationHistoryQuotaExceededError,
}


def execution_context_error_from_code(
    error_code: str,
    *,
    detail: str | None = None,
    context: Mapping[str, JsonValue] | None = None,
) -> ExecutionContextError:
    """Build a typed error from a frozen wire code (dashboard/fixtures)."""
    cls = _ERROR_BY_CODE.get(error_code, InvalidExecutionContextError)
    return cls(detail=detail, context=context)


__all__ = [
    "CONTEXT_ERROR_HTTP_STATUS",
    "ConversationHistoryCorruptError",
    "ConversationHistoryUnavailableError",
    "ConversationIntegrityError",
    "ConversationNotFoundError",
    "ConversationStorageMigrationRequiredError",
    "ExecutionContextError",
    "InvalidConversationRevisionError",
    "InvalidExecutionContextError",
    "MissingExecutionContextError",
    "ProjectNotFoundError",
    "ProjectRootInvalidError",
    "StaleConversationRevisionError",
    "execution_context_error_from_code",
]
