"""Frozen commercial GA API contracts (ARC-01 / CTX-01).

WS-01 / CTX-01 lanes consume these types; they must not redefine the
execution-context shape or error codes.
"""

from __future__ import annotations

from antigravity_k.api.contracts.conversation import (
    CONVERSATION_REVISION_MIN,
    ConversationAppendRequest,
    ConversationCompactRequest,
    ConversationConflictPayload,
    ConversationForkRequest,
    ConversationHistoryMessage,
    ConversationHistoryResponse,
    ConversationNewTurn,
    ConversationRef,
    ConversationSnapshot,
)
from antigravity_k.api.contracts.errors import (
    CONTEXT_ERROR_HTTP_STATUS,
    ConversationIntegrityError,
    ConversationNotFoundError,
    ConversationStorageMigrationRequiredError,
    ExecutionContextError,
    InvalidConversationRevisionError,
    InvalidExecutionContextError,
    MissingExecutionContextError,
    ProjectNotFoundError,
    ProjectRootInvalidError,
    StaleConversationRevisionError,
    execution_context_error_from_code,
)
from antigravity_k.api.contracts.execution_context import (
    REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION,
    ActorSessionRef,
    RequestExecutionContext,
    RequestExecutionContextWire,
)
from antigravity_k.api.contracts.shell import (
    SHELL_ERROR_HTTP_STATUS,
    ShellApprovalRequiredError,
    ShellBoundaryError,
    ShellPolicyDeniedError,
    ShellSandboxUnavailableError,
    ShellTimeoutError,
)

__all__ = [
    "CONVERSATION_REVISION_MIN",
    "CONTEXT_ERROR_HTTP_STATUS",
    "REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION",
    "SHELL_ERROR_HTTP_STATUS",
    "ActorSessionRef",
    "ConversationAppendRequest",
    "ConversationCompactRequest",
    "ConversationConflictPayload",
    "ConversationForkRequest",
    "ConversationHistoryMessage",
    "ConversationHistoryResponse",
    "ConversationIntegrityError",
    "ConversationNewTurn",
    "ConversationNotFoundError",
    "ConversationRef",
    "ConversationSnapshot",
    "ConversationStorageMigrationRequiredError",
    "ExecutionContextError",
    "InvalidConversationRevisionError",
    "InvalidExecutionContextError",
    "MissingExecutionContextError",
    "ProjectNotFoundError",
    "ProjectRootInvalidError",
    "RequestExecutionContext",
    "RequestExecutionContextWire",
    "ShellApprovalRequiredError",
    "ShellBoundaryError",
    "ShellPolicyDeniedError",
    "ShellSandboxUnavailableError",
    "ShellTimeoutError",
    "StaleConversationRevisionError",
    "execution_context_error_from_code",
]
