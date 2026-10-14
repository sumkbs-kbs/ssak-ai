"""Request-scoped project binding and session active-project revisions (WS-01).

Chat/task execution resolves ``project_id`` → canonical root via ARC-01
``RequestExecutionContext``. Session bindings provide an explicit active
project revision when the client omits ``project_id``. The module-global
``WORKSPACE_ROOT`` / config mutation path is not execution authority.
"""

from __future__ import annotations

import threading
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from antigravity_k.api.contracts.errors import MissingExecutionContextError
from antigravity_k.api.contracts.execution_context import (
    RequestExecutionContext,
    RequestExecutionContextWire,
)
from antigravity_k.engine.conversation_store import get_conversation_store
from antigravity_k.engine.project_registry import ProjectRegistry, get_project_registry
from antigravity_k.engine.request_execution_context import resolve_request_execution_context

DEFAULT_SESSION_ID = "default"
SESSION_ID_HEADER = "X-AGK-Session-Id"

_request_execution_context: ContextVar[RequestExecutionContext | None] = ContextVar(
    "request_execution_context",
    default=None,
)

_runtime_capture_enabled: bool = False
_runtime_captures: list[RequestExecutionContext] = []
_runtime_captures_lock = threading.Lock()


@dataclass(frozen=True)
class SessionActiveProject:
    """Explicit session → project binding with monotonic revision."""

    session_id: str
    project_id: str
    revision: int
    bound_at: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "bound_at": self.bound_at,
        }


class SessionProjectBindingStore:
    """Thread-safe store of explicit per-session active project revisions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bindings: dict[str, SessionActiveProject] = {}

    def get(self, session_id: str) -> SessionActiveProject | None:
        key = (session_id or "").strip() or DEFAULT_SESSION_ID
        with self._lock:
            return self._bindings.get(key)

    def bind(self, session_id: str, project_id: str) -> SessionActiveProject:
        key = (session_id or "").strip() or DEFAULT_SESSION_ID
        pid = (project_id or "").strip()
        if not pid:
            raise MissingExecutionContextError(
                detail="project_id is required to bind a session active project",
                context={"field": "project_id", "session_id": key},
            )
        with self._lock:
            previous = self._bindings.get(key)
            next_revision = 1 if previous is None else previous.revision + 1
            binding = SessionActiveProject(
                session_id=key,
                project_id=pid,
                revision=next_revision,
                bound_at=datetime.now(timezone.utc).isoformat(),
            )
            self._bindings[key] = binding
            return binding

    def clear(self, session_id: str) -> None:
        key = (session_id or "").strip() or DEFAULT_SESSION_ID
        with self._lock:
            _ = self._bindings.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._bindings.clear()


_session_bindings = SessionProjectBindingStore()


def get_session_project_bindings() -> SessionProjectBindingStore:
    return _session_bindings


def bind_session_active_project(session_id: str, project_id: str) -> SessionActiveProject:
    return _session_bindings.bind(session_id, project_id)


def get_session_active_project(session_id: str | None) -> SessionActiveProject | None:
    return _session_bindings.get(session_id or DEFAULT_SESSION_ID)


def get_bound_request_execution_context() -> RequestExecutionContext | None:
    return _request_execution_context.get()


def set_bound_request_execution_context(
    context: RequestExecutionContext,
) -> Token[RequestExecutionContext | None]:
    token = _request_execution_context.set(context)
    if _runtime_capture_enabled:
        with _runtime_captures_lock:
            _runtime_captures.append(context)
    return token


def reset_bound_request_execution_context(
    token: Token[RequestExecutionContext | None] | None = None,
) -> None:
    if token is not None:
        _request_execution_context.reset(token)
    else:
        _request_execution_context.set(None)


def get_request_project_root() -> str | None:
    """Return the request-scoped canonical root, if a context is bound."""
    ctx = _request_execution_context.get()
    return None if ctx is None else ctx.canonical_project_root


def get_request_project_id() -> str | None:
    ctx = _request_execution_context.get()
    return None if ctx is None else ctx.project_id


def enable_runtime_capture() -> list[RequestExecutionContext]:
    """Enable capture of resolved contexts (tests). Clears prior captures."""
    global _runtime_capture_enabled
    with _runtime_captures_lock:
        _runtime_captures.clear()
    _runtime_capture_enabled = True
    return _runtime_captures


def disable_runtime_capture() -> None:
    global _runtime_capture_enabled
    _runtime_capture_enabled = False


def get_runtime_captures() -> list[RequestExecutionContext]:
    with _runtime_captures_lock:
        return list(_runtime_captures)


def clear_runtime_captures() -> None:
    with _runtime_captures_lock:
        _runtime_captures.clear()


def _as_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    return default


def extract_project_id_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    """Pull project_id from top-level body or nested execution_context wire."""
    if not payload:
        return None
    direct = _as_text(payload.get("project_id"))
    if direct:
        return direct
    nested = payload.get("execution_context")
    if isinstance(nested, Mapping):
        nested_id = _as_text(nested.get("project_id"))
        if nested_id:
            return nested_id
    context_blob = payload.get("context")
    if isinstance(context_blob, Mapping):
        ctx_id = _as_text(context_blob.get("project_id"))
        if ctx_id:
            return ctx_id
        nested_ctx = context_blob.get("execution_context")
        if isinstance(nested_ctx, Mapping):
            nested_id = _as_text(nested_ctx.get("project_id"))
            if nested_id:
                return nested_id
    return None


def extract_session_id_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    header_session_id: str | None = None,
) -> str:
    if header_session_id and header_session_id.strip():
        return header_session_id.strip()
    if payload:
        for key in ("session_id", "agk_session_id"):
            value = _as_text(payload.get(key))
            if value:
                return value
        nested = payload.get("execution_context")
        if isinstance(nested, Mapping):
            value = _as_text(nested.get("session_id"))
            if value:
                return value
    return DEFAULT_SESSION_ID


def _wire_from_parts(
    *,
    project_id: str,
    payload: Mapping[str, Any] | None,
    session_id: str,
    actor_subject: str,
    model_id: str,
    request_id: str | None,
    conversation_id: str | None,
    conversation_revision: int | None,
    task_id: str | None,
    correlation_id: str,
) -> RequestExecutionContextWire:
    nested = payload.get("execution_context") if payload else None
    nested_map = nested if isinstance(nested, Mapping) else {}

    def pick(*keys: str, default: str = "") -> str:
        for key in keys:
            if payload:
                value = _as_text(payload.get(key))
                if value:
                    return value
            value = _as_text(nested_map.get(key))
            if value:
                return value
        return default

    rev = conversation_revision
    if rev is None:
        raw_rev = payload.get("conversation_revision") if payload else None
        if raw_rev is None:
            raw_rev = nested_map.get("conversation_revision")
        try:
            rev = int(raw_rev) if isinstance(raw_rev, (str, int, float)) else 0
        except ValueError:
            rev = 0

    return RequestExecutionContextWire(
        request_id=pick("request_id", default=request_id or f"req_{uuid.uuid4().hex[:12]}"),
        task_id=task_id or (_as_text(payload.get("task_id")) if payload else None) or None,
        project_id=project_id,
        conversation_id=pick("conversation_id", default=conversation_id or "conv_unspecified"),
        conversation_revision=max(0, rev),
        actor_subject=pick("actor_subject", default=actor_subject or "anonymous"),
        session_id=session_id,
        model_id=pick("model_id", "model", default=model_id or "default"),
        correlation_id=pick("correlation_id", default=correlation_id),
        client_hint_path=_as_text(nested_map.get("client_hint_path")) or None,
    )


def resolve_project_execution_context(
    *,
    payload: Mapping[str, Any] | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    header_session_id: str | None = None,
    actor_subject: str = "anonymous",
    model_id: str = "default",
    request_id: str | None = None,
    conversation_id: str | None = None,
    conversation_revision: int | None = None,
    task_id: str | None = None,
    correlation_id: str = "",
    registry: ProjectRegistry | None = None,
    require_existing_conversation: bool = False,
    bind: bool = True,
) -> RequestExecutionContext:
    """Resolve and optionally bind an immutable RequestExecutionContext.

    Resolution order:
    1. Explicit ``project_id`` (argument, body, or nested execution_context)
    2. Explicit session active-project binding (revisioned)
    3. Otherwise ``MissingExecutionContextError`` — never raw path / WORKSPACE_ROOT
    """
    resolved_session = extract_session_id_from_payload(
        payload,
        header_session_id=header_session_id or session_id,
    )
    explicit_project = (project_id or "").strip() or extract_project_id_from_payload(payload)

    session_binding: SessionActiveProject | None = None
    if not explicit_project:
        session_binding = get_session_active_project(resolved_session)
        if session_binding is None:
            raise MissingExecutionContextError(
                detail=("Chat/task requests require project_id or an explicit session active project binding"),
                context={
                    "field": "project_id",
                    "session_id": resolved_session,
                },
            )
        explicit_project = session_binding.project_id

    nested = payload.get("execution_context") if payload else None
    if isinstance(nested, Mapping) and _as_text(nested.get("project_id")):
        # Ensure session/actor defaults when nested wire is partial — re-build.
        try:
            wire_model = (
                nested
                if isinstance(nested, RequestExecutionContextWire)
                else RequestExecutionContextWire.model_validate(
                    {
                        **dict(nested),
                        "project_id": explicit_project,
                        "session_id": _as_text(nested.get("session_id")) or resolved_session,
                        "actor_subject": _as_text(nested.get("actor_subject")) or actor_subject,
                        "model_id": _as_text(nested.get("model_id")) or model_id or "default",
                        "request_id": _as_text(nested.get("request_id"))
                        or request_id
                        or f"req_{uuid.uuid4().hex[:12]}",
                        "conversation_id": _as_text(nested.get("conversation_id"))
                        or conversation_id
                        or "conv_unspecified",
                        "conversation_revision": nested.get("conversation_revision", 0),
                    }
                )
            )
        except Exception:
            wire_model = _wire_from_parts(
                project_id=explicit_project,
                payload=payload,
                session_id=resolved_session,
                actor_subject=actor_subject,
                model_id=model_id,
                request_id=request_id,
                conversation_id=conversation_id,
                conversation_revision=conversation_revision,
                task_id=task_id,
                correlation_id=correlation_id,
            )
    else:
        wire_model = _wire_from_parts(
            project_id=explicit_project,
            payload=payload,
            session_id=resolved_session,
            actor_subject=actor_subject,
            model_id=model_id,
            request_id=request_id,
            conversation_id=conversation_id,
            conversation_revision=conversation_revision,
            task_id=task_id,
            correlation_id=correlation_id,
        )

    # CTX-01: assert revision against authoritative store for real conversations.
    # Legacy "conv_unspecified" traffic skips store assert to avoid false 409s.
    conv_id = wire_model.conversation_id
    use_store = require_existing_conversation or (bool(conv_id) and conv_id != "conv_unspecified")
    context = resolve_request_execution_context(
        wire_model,
        registry=registry or get_project_registry(),
        conversation_store=get_conversation_store() if use_store else None,
        require_existing_conversation=require_existing_conversation,
    )
    if bind:
        set_bound_request_execution_context(context)
    return context


def execution_context_to_task_context(context: RequestExecutionContext) -> dict[str, object]:
    """Immutable project binding fields stored on task creation."""
    return {
        "project_id": context.project_id,
        "canonical_project_root": context.canonical_project_root,
        "conversation_id": context.conversation_id,
        "conversation_revision": context.conversation_revision,
        "request_id": context.request_id,
        "session_id": context.session_id,
        "actor_subject": context.actor_subject,
        "model_id": context.model_id,
        "project_name": context.project_name,
        "schema_version": context.schema_version,
        "execution_context": context.model_dump(mode="json"),
    }


__all__ = [
    "DEFAULT_SESSION_ID",
    "SESSION_ID_HEADER",
    "SessionActiveProject",
    "SessionProjectBindingStore",
    "bind_session_active_project",
    "clear_runtime_captures",
    "disable_runtime_capture",
    "enable_runtime_capture",
    "execution_context_to_task_context",
    "extract_project_id_from_payload",
    "extract_session_id_from_payload",
    "get_bound_request_execution_context",
    "get_request_project_id",
    "get_request_project_root",
    "get_runtime_captures",
    "get_session_active_project",
    "get_session_project_bindings",
    "reset_bound_request_execution_context",
    "resolve_project_execution_context",
    "set_bound_request_execution_context",
]
