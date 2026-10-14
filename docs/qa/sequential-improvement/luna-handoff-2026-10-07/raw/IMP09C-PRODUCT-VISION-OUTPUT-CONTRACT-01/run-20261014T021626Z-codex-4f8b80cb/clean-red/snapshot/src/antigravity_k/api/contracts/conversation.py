"""Conversation identity and revision CAS protocol (ARC-01 / CTX-01).

Authoritative store behavior is implemented by CTX-01. This module freezes the
wire types WS/CTX lanes share: expected revision on write, conflict payload on
409, and snapshot shape after append/compact.
"""

from __future__ import annotations

from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONVERSATION_REVISION_MIN: Final[int] = 0


class ConversationRef(BaseModel):
    """Immutable conversation pointer carried on every mutating request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=128)
    conversation_revision: int = Field(ge=CONVERSATION_REVISION_MIN)


class ConversationAppendRequest(BaseModel):
    """Client write: new turn content plus the revision the client last observed."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=CONVERSATION_REVISION_MIN)
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str = Field(min_length=1, max_length=512_000)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("content must not be blank")
        return text


class ConversationCompactRequest(BaseModel):
    """Client compact: expected revision + optional retain-tail size."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=CONVERSATION_REVISION_MIN)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    retain_tail: int = Field(default=6, ge=0, le=10_000)


class ConversationForkRequest(BaseModel):
    """Fork an existing conversation into a new authoritative id at revision 0."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=128)
    expected_revision: int | None = Field(default=None, ge=CONVERSATION_REVISION_MIN)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    new_conversation_id: str | None = Field(default=None, min_length=1, max_length=128)


class ConversationNewTurn(BaseModel):
    """Single new turn sent by the client (not a full history array)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str = Field(min_length=1, max_length=512_000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("content must not be blank")
        return text


class ConversationSnapshot(BaseModel):
    """Authoritative conversation head returned after a successful CAS write."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=CONVERSATION_REVISION_MIN)
    message_count: int = Field(ge=0)
    summary: str | None = None
    retained_message_ids: tuple[str, ...] = ()


class ConversationHistoryMessage(BaseModel):
    """Wire message returned on GET / refresh."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: float
    provenance: str = "append"


class ConversationHistoryResponse(BaseModel):
    """Full authoritative projection for refresh/reconnect."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    snapshot: ConversationSnapshot
    messages: tuple[ConversationHistoryMessage, ...] = ()
    token_estimate: int = Field(ge=0, default=0)


class ConversationOriginalHistoryResponse(BaseModel):
    """NX-02: original (pre-compaction) history read surface.

    Deliberately separate from :class:`ConversationHistoryResponse`: the view is
    what the model gets on the next prompt, the originals are what the user
    actually typed (recovery / audit / export).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    project_id: str
    offset: int = Field(ge=0, default=0)
    limit: int | None = Field(default=None, ge=0)
    total: int = Field(ge=0, default=0)
    revision: int = Field(ge=CONVERSATION_REVISION_MIN, default=0)
    journal_seq: int = Field(ge=0, default=0)
    history_incomplete: bool = False
    truncated_tail: bool = False
    messages: tuple[ConversationHistoryMessage, ...] = ()


class ConversationHistoryExportResponse(BaseModel):
    """NX-02: support/backup export of originals plus journal fingerprint."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    schema_id: str = "agk.conv-export.v1"
    project_id: str
    conversation_id: str
    exported_at: float
    revision: int = Field(ge=CONVERSATION_REVISION_MIN, default=0)
    journal_seq: int = Field(ge=0, default=0)
    journal_sha256: str = ""
    journal_schema: str = ""
    history_incomplete: bool = False
    deleted: bool = False
    message_count: int = Field(ge=0, default=0)
    messages: tuple[ConversationHistoryMessage, ...] = ()


class ConversationDeleteResponse(BaseModel):
    """NX-02: explicit deletion receipt (never a silent no-op)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    project_id: str
    deleted: bool
    erased_scope: Literal["journal_and_view", "nothing"]
    revision: int = Field(ge=CONVERSATION_REVISION_MIN, default=0)
    note: str = (
        "Deleted from the local conversation store. Copies outside this store "
        "(backups, forks, exported files) are not claimed to be erased."
    )


class ConversationConflictPayload(BaseModel):
    """409 body when expected_revision does not match the store."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[False] = False
    error: Literal["stale_conversation_revision"] = "stale_conversation_revision"
    detail: str = "Conversation revision does not match the authoritative store"
    conversation_id: str
    expected_revision: int = Field(ge=CONVERSATION_REVISION_MIN)
    current_revision: int = Field(ge=CONVERSATION_REVISION_MIN)
    correlation_id: str = ""


__all__ = [
    "CONVERSATION_REVISION_MIN",
    "ConversationAppendRequest",
    "ConversationCompactRequest",
    "ConversationConflictPayload",
    "ConversationDeleteResponse",
    "ConversationForkRequest",
    "ConversationHistoryExportResponse",
    "ConversationOriginalHistoryResponse",
    "ConversationHistoryMessage",
    "ConversationHistoryResponse",
    "ConversationNewTurn",
    "ConversationRef",
    "ConversationSnapshot",
]
