"""Server-side resolution of RequestExecutionContext (ARC-01).

`project_id` is the source of truth. The project registry yields the canonical
root; client paths never authorize execution. Conversation revision is checked
against an authoritative store protocol (CTX-01 implements persistence).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from antigravity_k.api.contracts.errors import (
    ConversationNotFoundError,
    InvalidConversationRevisionError,
    InvalidExecutionContextError,
    MissingExecutionContextError,
    ProjectNotFoundError,
    ProjectRootInvalidError,
    StaleConversationRevisionError,
)
from antigravity_k.api.contracts.execution_context import (
    RequestExecutionContext,
    RequestExecutionContextWire,
)
from antigravity_k.api.path_security import configured_allowed_bases
from antigravity_k.engine.project_registry import ProjectRecord, ProjectRegistry, get_project_registry


class ConversationRevisionStore(Protocol):
    """Minimal CAS surface frozen for CTX-01 consumers."""

    def get_revision(self, *, project_id: str, conversation_id: str) -> int | None:
        """Return current revision, or None when the conversation is unknown."""
        ...

    def compare_and_set(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        next_revision: int,
    ) -> bool:
        """Return True when the store advanced from expected → next."""
        ...


class InMemoryConversationRevisionStore:
    """Test/fixture store. Not the production CTX-01 backend."""

    def __init__(self) -> None:
        self._revisions: dict[tuple[str, str], int] = {}

    def seed(self, *, project_id: str, conversation_id: str, revision: int) -> None:
        self._revisions[(project_id, conversation_id)] = revision

    def get_revision(self, *, project_id: str, conversation_id: str) -> int | None:
        return self._revisions.get((project_id, conversation_id))

    def compare_and_set(
        self,
        *,
        project_id: str,
        conversation_id: str,
        expected_revision: int,
        next_revision: int,
    ) -> bool:
        key = (project_id, conversation_id)
        current = self._revisions.get(key)
        if current is None:
            if expected_revision != 0:
                return False
            self._revisions[key] = next_revision
            return True
        if current != expected_revision:
            return False
        self._revisions[key] = next_revision
        return True


# Protected system prefixes must never become canonical execution roots
# (aligned with PermissionGate.PROTECTED_PATHS / sandbox denials).
_UNSAFE_PROJECT_ROOT_PREFIXES: tuple[str, ...] = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
    "/var/root",
    "/System",
    "/Library",
    "/private/etc",
    "/private/var/root",
)


def _is_unsafe_system_project_root(canonical: str) -> bool:
    """Return True when ``canonical`` is the filesystem root or a protected system path."""
    normalized = os.path.realpath(canonical)
    if normalized in {"/", os.path.sep}:
        return True
    for prefix in _UNSAFE_PROJECT_ROOT_PREFIXES:
        prefix_real = os.path.realpath(prefix) if os.path.lexists(prefix) else os.path.abspath(prefix)
        if normalized == prefix_real or normalized.startswith(prefix_real.rstrip(os.sep) + os.sep):
            return True
        if normalized == prefix or normalized.startswith(prefix.rstrip(os.sep) + os.sep):
            return True
    return False


def _path_within_bases(canonical: str, bases: tuple[Path, ...]) -> bool:
    candidate = Path(canonical)
    for base in bases:
        try:
            _ = candidate.relative_to(base)
        except ValueError:
            continue
        return True
    return False


def resolve_canonical_project_root(
    project_id: str,
    *,
    registry: ProjectRegistry | None = None,
) -> tuple[ProjectRecord, str]:
    """Map project_id → (record, absolute canonical root).

    Raises typed ARC-01 errors when the project is missing or the root is not a
    usable directory under the configured allowlist. Escape via ``..``,
    symlink-out, or unsafe system paths is rejected at this boundary.
    """
    if not project_id or not str(project_id).strip():
        raise MissingExecutionContextError(
            detail="project_id is required",
            context={"field": "project_id"},
        )

    reg = registry or get_project_registry()
    record = reg.get_project(project_id.strip())
    if record is None:
        raise ProjectNotFoundError(
            detail=f"Project not registered: {project_id}",
            context={"project_id": project_id},
        )

    # Registry record is authority for project_id → root identity, but the
    # resolved realpath must still remain under configured trusted bases and
    # must not be an unsafe system path. Registry paths are intentionally
    # excluded from the base set so a poisoned entry cannot self-allowlist.
    raw_path = record.path
    raw_expanded = Path(raw_path).expanduser()
    candidate = raw_expanded.resolve()
    if not candidate.is_dir():
        raise ProjectRootInvalidError(
            detail="Project canonical root is not an existing directory",
            context={"project_id": project_id, "canonical_project_root": str(candidate)},
        )

    canonical = os.path.realpath(candidate)
    if not os.path.isdir(canonical):
        raise ProjectRootInvalidError(
            detail="Project canonical root is not an existing directory after realpath",
            context={"project_id": project_id, "canonical_project_root": canonical},
        )

    if _is_unsafe_system_project_root(canonical):
        raise ProjectRootInvalidError(
            detail="Project root resolves to an unsafe system path",
            context={
                "project_id": project_id,
                "path": raw_path,
                "canonical_project_root": canonical,
            },
        )

    bases = configured_allowed_bases()
    if not _path_within_bases(canonical, bases):
        raise ProjectRootInvalidError(
            detail="Project root escapes configured workspace roots",
            context={
                "project_id": project_id,
                "path": raw_path,
                "canonical_project_root": canonical,
            },
        )

    # Symlink-out and ``..`` normalization are covered by realpath + bases check:
    # a registry path that lexically looks local but realpaths outside configured
    # bases (or onto an unsafe system path) is rejected above.
    return record, canonical


def assert_conversation_revision(
    *,
    project_id: str,
    conversation_id: str,
    expected_revision: int,
    store: ConversationRevisionStore,
    require_existing: bool = True,
) -> int:
    """Validate expected revision against the authoritative store.

    Returns the current revision when it matches. Creates are allowed when
    `require_existing` is False and expected_revision is 0 for a missing id.
    """
    if expected_revision < 0:
        raise InvalidConversationRevisionError(
            detail="conversation_revision must be >= 0",
            context={"conversation_revision": expected_revision},
        )

    current = store.get_revision(project_id=project_id, conversation_id=conversation_id)
    if current is None:
        if require_existing and expected_revision != 0:
            raise ConversationNotFoundError(
                detail=f"Conversation not found: {conversation_id}",
                context={
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                    "expected_revision": expected_revision,
                },
            )
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
        return 0

    if current != expected_revision:
        raise StaleConversationRevisionError(
            detail="Conversation revision does not match the authoritative store",
            context={
                "project_id": project_id,
                "conversation_id": conversation_id,
                "expected_revision": expected_revision,
                "current_revision": current,
            },
        )
    return current


def resolve_request_execution_context(
    wire: RequestExecutionContextWire | None,
    *,
    registry: ProjectRegistry | None = None,
    conversation_store: ConversationRevisionStore | None = None,
    require_existing_conversation: bool = True,
) -> RequestExecutionContext:
    """Build an immutable resolved context from the wire payload.

    `client_hint_path` is intentionally ignored for authority.
    """
    if wire is None:
        raise MissingExecutionContextError(detail="RequestExecutionContext payload is required")

    try:
        # Re-validate in case callers constructed via dict.
        payload = (
            wire if isinstance(wire, RequestExecutionContextWire) else RequestExecutionContextWire.model_validate(wire)
        )
    except Exception as exc:
        raise InvalidExecutionContextError(
            detail=f"RequestExecutionContext wire validation failed: {exc}",
        ) from exc

    # Explicitly refuse treating client path hints as authority (migration guard).
    _ = payload.client_hint_path

    record, canonical_root = resolve_canonical_project_root(payload.project_id, registry=registry)

    if conversation_store is not None:
        _ = assert_conversation_revision(
            project_id=payload.project_id,
            conversation_id=payload.conversation_id,
            expected_revision=payload.conversation_revision,
            store=conversation_store,
            require_existing=require_existing_conversation,
        )

    return RequestExecutionContext(
        schema_version=payload.schema_version,
        request_id=payload.request_id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        canonical_project_root=canonical_root,
        conversation_id=payload.conversation_id,
        conversation_revision=payload.conversation_revision,
        actor_subject=payload.actor_subject,
        session_id=payload.session_id,
        model_id=payload.model_id,
        correlation_id=payload.correlation_id,
        project_name=record.name,
    )


def reject_raw_path_authority(raw_path: str | Path | None) -> None:
    """Boundary helper: callers must not use a raw path as execution authority.

    WS-01 replaces WORKSPACE_ROOT mutation; until then this documents/enforces
    the ARC-01 rule at shared helpers.
    """
    if raw_path is None:
        return
    raise InvalidExecutionContextError(
        detail="Raw filesystem path is not execution authority; send project_id",
        context={"rejected_path": str(raw_path)},
    )


__all__ = [
    "ConversationRevisionStore",
    "InMemoryConversationRevisionStore",
    "assert_conversation_revision",
    "reject_raw_path_authority",
    "resolve_canonical_project_root",
    "resolve_request_execution_context",
]
