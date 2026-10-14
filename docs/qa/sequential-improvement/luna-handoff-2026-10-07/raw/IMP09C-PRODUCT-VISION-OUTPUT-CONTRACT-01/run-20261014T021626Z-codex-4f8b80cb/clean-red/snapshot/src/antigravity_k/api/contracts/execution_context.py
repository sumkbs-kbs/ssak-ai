"""Immutable RequestExecutionContext wire + domain types (ARC-01).

`canonical_project_root` is always server-resolved from `project_id` via the
project registry. Client-supplied filesystem paths are never authority for
chat/tool/memory/RAG execution.
"""

from __future__ import annotations

from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION: Final[int] = 1


class ActorSessionRef(BaseModel):
    """Operator + browser/session identity bound to a request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    actor_subject: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)


class RequestExecutionContextWire(BaseModel):
    """Client/server shared wire shape before server resolves canonical root.

    Clients MUST send `project_id`. They MUST NOT send a raw path as the
    execution authority. Optional `client_hint_path` is ignored for authority
    and retained only for diagnostics / migration telemetry.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION, ge=1)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    conversation_revision: int = Field(ge=0)
    actor_subject: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(default="", max_length=128)
    client_hint_path: str | None = Field(default=None, max_length=4096)

    @field_validator("project_id", "conversation_id", "request_id", "actor_subject", "session_id", "model_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("field must not be blank")
        return text

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class RequestExecutionContext(BaseModel):
    """Immutable resolved execution context handed to task/tool/memory/RAG.

    Frozen after construction. `canonical_project_root` is an absolute real
    path resolved by the server from `project_id`; it is the sole filesystem
    authority for the request.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION, ge=1)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    canonical_project_root: str = Field(min_length=1, max_length=4096)
    conversation_id: str = Field(min_length=1, max_length=128)
    conversation_revision: int = Field(ge=0)
    actor_subject: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(default="", max_length=128)
    project_name: str = Field(default="", max_length=256)

    @field_validator("canonical_project_root")
    @classmethod
    def require_absolute_root(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("canonical_project_root must not be blank")
        # Absolute on POSIX or Windows drive path; reject relative authority.
        if not (text.startswith("/") or (len(text) >= 3 and text[1] == ":")):
            raise ValueError("canonical_project_root must be an absolute path")
        return text


__all__ = [
    "REQUEST_EXECUTION_CONTEXT_SCHEMA_VERSION",
    "ActorSessionRef",
    "RequestExecutionContext",
    "RequestExecutionContextWire",
]
