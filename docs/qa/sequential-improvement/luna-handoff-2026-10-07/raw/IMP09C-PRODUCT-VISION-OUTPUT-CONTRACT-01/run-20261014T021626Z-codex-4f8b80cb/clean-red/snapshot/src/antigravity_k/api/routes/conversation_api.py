"""Conversation revision CAS API (CTX-01) + original-history surface (NX-02).

Authoritative server store endpoints:
- GET  /v1/conversations/{id}              — snapshot + messages (prompt view)
- POST /v1/conversations/append            — CAS append new turn
- POST /v1/conversations/compact           — CAS compact; summary + retained IDs + revision
- POST /v1/conversations/fork              — fork at consistent revision
- GET  /v1/conversations/{id}/history      — original (pre-compaction) history, paged
- GET  /v1/conversations/{id}/export       — originals + journal fingerprint (support/backup)
- DELETE /v1/conversations/{id}            — delete originals and view together
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Request

from antigravity_k.api.contracts.conversation import (
    ConversationAppendRequest,
    ConversationCompactRequest,
    ConversationDeleteResponse,
    ConversationForkRequest,
    ConversationHistoryExportResponse,
    ConversationHistoryMessage,
    ConversationHistoryResponse,
    ConversationOriginalHistoryResponse,
)
from antigravity_k.api.contracts.errors import ConversationNotFoundError
from antigravity_k.api.error_handler import ValidationError, correlation_id_var
from antigravity_k.api.project_binding import (
    SESSION_ID_HEADER,
    extract_project_id_from_payload,
    resolve_project_execution_context,
)
from antigravity_k.engine.conversation_store import MessageRole, get_conversation_store

logger = logging.getLogger("antigravity_k.api.conversation")

router = APIRouter()


def _resolve_project_id(request: Request, body: dict[str, Any] | None, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    from_body = extract_project_id_from_payload(body)
    if from_body:
        return from_body
    # Fall through to session binding via resolve_project_execution_context.
    ctx = resolve_project_execution_context(
        payload=body,
        header_session_id=request.headers.get(SESSION_ID_HEADER),
        actor_subject=str(getattr(request.state, "auth_subject", None) or "anonymous"),
        model_id="default",
        correlation_id=correlation_id_var.get(""),
        require_existing_conversation=False,
        bind=False,
    )
    return ctx.project_id


def _non_negative_int(raw: str | None, *, default: int, field: str) -> int:
    """Query param parse that fails loudly instead of silently defaulting."""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(detail=f"{field} must be a non-negative integer", context={"field": field}) from exc
    if value < 0:
        raise ValidationError(detail=f"{field} must be a non-negative integer", context={"field": field})
    return value


def _require_live_conversation(state: dict[str, Any], *, project_id: str, conversation_id: str) -> None:
    """NX-02: deleted conversations expose no originals (and no export)."""
    if state.get("exists") and not state.get("deleted"):
        return
    raise ConversationNotFoundError(
        detail=f"Conversation not found: {conversation_id}",
        context={
            "project_id": project_id,
            "conversation_id": conversation_id,
            "reason": "deleted" if state.get("deleted") else "missing",
        },
    )


def _original_message(payload: dict[str, Any]) -> ConversationHistoryMessage:
    """Originals come from the journal (role/provenance are free-form there)."""
    role = str(payload.get("role") or "user")
    if role not in ("user", "assistant", "system", "tool"):
        role = "user"
    return ConversationHistoryMessage(
        id=str(payload.get("id") or ""),
        role=cast(MessageRole, role),
        content=str(payload.get("content") or ""),
        created_at=float(payload.get("created_at") or 0.0),
        provenance=str(payload.get("provenance") or "append"),
    )


def _history_response(project_id: str, conversation_id: str) -> ConversationHistoryResponse:
    store = get_conversation_store()
    record = store.get(project_id=project_id, conversation_id=conversation_id)
    if record is None:
        raise ConversationNotFoundError(
            detail=f"Conversation not found: {conversation_id}",
            context={"project_id": project_id, "conversation_id": conversation_id},
        )
    messages = tuple(
        ConversationHistoryMessage(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            provenance=m.provenance,
        )
        for m in record.messages
    )
    return ConversationHistoryResponse(
        snapshot=record.snapshot(),
        messages=messages,
        token_estimate=record.estimate_tokens(),
    )


@router.get("/v1/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    project_id = request.query_params.get("project_id")
    if not project_id:
        project_id = _resolve_project_id(request, None, None)
    return _history_response(project_id, conversation_id).model_dump(mode="json")


@router.post("/v1/conversations/append")
async def append_conversation(request: Request, req: ConversationAppendRequest) -> dict[str, Any]:
    body = req.model_dump(mode="json", exclude_none=True)
    project_id = _resolve_project_id(request, body, req.project_id)
    # Validate project exists via execution context (no conversation require).
    _ = resolve_project_execution_context(
        payload={
            **body,
            "project_id": project_id,
            "conversation_id": req.conversation_id,
            "conversation_revision": req.expected_revision,
        },
        header_session_id=request.headers.get(SESSION_ID_HEADER),
        actor_subject=str(getattr(request.state, "auth_subject", None) or "anonymous"),
        model_id="default",
        correlation_id=correlation_id_var.get(""),
        require_existing_conversation=False,
        bind=False,
    )
    store = get_conversation_store()
    snap = store.append(
        project_id=project_id,
        conversation_id=req.conversation_id,
        expected_revision=req.expected_revision,
        role=req.role,
        content=req.content,
    )
    return snap.model_dump(mode="json")


@router.post("/v1/conversations/compact")
@router.post("/compact")
async def compact_conversation(request: Request, req: ConversationCompactRequest) -> dict[str, Any]:
    """CAS compact. Returns summary, retained_message_ids, and new revision."""
    body = req.model_dump(mode="json", exclude_none=True)
    project_id = _resolve_project_id(request, body, req.project_id)
    _ = resolve_project_execution_context(
        payload={
            **body,
            "project_id": project_id,
            "conversation_id": req.conversation_id,
            "conversation_revision": req.expected_revision,
        },
        header_session_id=request.headers.get(SESSION_ID_HEADER),
        actor_subject=str(getattr(request.state, "auth_subject", None) or "anonymous"),
        model_id="default",
        correlation_id=correlation_id_var.get(""),
        require_existing_conversation=False,
        bind=False,
    )
    store = get_conversation_store()
    before = store.get(project_id=project_id, conversation_id=req.conversation_id)
    tokens_before = before.estimate_tokens() if before else 0
    snap = store.compact(
        project_id=project_id,
        conversation_id=req.conversation_id,
        expected_revision=req.expected_revision,
        retain_tail=req.retain_tail,
    )
    after = store.get(project_id=project_id, conversation_id=req.conversation_id)
    tokens_after = after.estimate_tokens() if after else 0
    payload = snap.model_dump(mode="json")
    payload["tokens_before"] = tokens_before
    payload["tokens_after"] = tokens_after
    payload["tokens_reduced"] = max(0, tokens_before - tokens_after)
    return payload


@router.post("/v1/conversations/fork")
async def fork_conversation(request: Request, req: ConversationForkRequest) -> dict[str, Any]:
    body = req.model_dump(mode="json", exclude_none=True)
    project_id = _resolve_project_id(request, body, req.project_id)
    _ = resolve_project_execution_context(
        payload={
            **body,
            "project_id": project_id,
            "conversation_id": req.conversation_id,
            "conversation_revision": req.expected_revision or 0,
        },
        header_session_id=request.headers.get(SESSION_ID_HEADER),
        actor_subject=str(getattr(request.state, "auth_subject", None) or "anonymous"),
        model_id="default",
        correlation_id=correlation_id_var.get(""),
        require_existing_conversation=False,
        bind=False,
    )
    store = get_conversation_store()
    snap = store.fork(
        project_id=project_id,
        source_conversation_id=req.conversation_id,
        expected_revision=req.expected_revision,
        new_conversation_id=req.new_conversation_id,
    )
    return snap.model_dump(mode="json")


@router.get("/v1/conversations/{conversation_id}/history")
async def get_original_history(conversation_id: str, request: Request) -> dict[str, Any]:
    """NX-02: original (pre-compaction) history, paged, separate from the view."""
    project_id = request.query_params.get("project_id") or _resolve_project_id(request, None, None)
    offset = _non_negative_int(request.query_params.get("offset"), default=0, field="offset")
    raw_limit = request.query_params.get("limit")
    limit = None if raw_limit in (None, "") else _non_negative_int(raw_limit, default=0, field="limit")

    store = get_conversation_store()
    state = store.history_state(project_id=project_id, conversation_id=conversation_id)
    _require_live_conversation(state, project_id=project_id, conversation_id=conversation_id)
    originals = store.original_history(
        project_id=project_id, conversation_id=conversation_id, offset=offset, limit=limit
    )
    return ConversationOriginalHistoryResponse(
        conversation_id=conversation_id,
        project_id=project_id,
        offset=offset,
        limit=limit,
        total=int(state["original_message_count"]),
        revision=int(state["revision"]),
        journal_seq=int(state["journal_seq"]),
        history_incomplete=bool(state["history_incomplete"]),
        truncated_tail=bool(state["truncated_tail"]),
        messages=tuple(_original_message(m) for m in originals),
    ).model_dump(mode="json")


@router.get("/v1/conversations/{conversation_id}/export")
async def export_original_history(conversation_id: str, request: Request) -> dict[str, Any]:
    """NX-02: export originals with the journal fingerprint (support/backup)."""
    project_id = request.query_params.get("project_id") or _resolve_project_id(request, None, None)
    store = get_conversation_store()
    state = store.history_state(project_id=project_id, conversation_id=conversation_id)
    _require_live_conversation(state, project_id=project_id, conversation_id=conversation_id)
    payload = store.export_original_history(project_id=project_id, conversation_id=conversation_id)
    return ConversationHistoryExportResponse(
        schema_id=str(payload["schema"]),
        project_id=project_id,
        conversation_id=conversation_id,
        exported_at=float(payload["exported_at"]),
        revision=int(payload["revision"] or 0),
        journal_seq=int(payload["journal_seq"] or 0),
        journal_sha256=str(payload["journal_sha256"]),
        journal_schema=str(payload["journal_schema"]),
        history_incomplete=bool(payload["history_incomplete"]),
        deleted=bool(payload["deleted"]),
        message_count=int(payload["message_count"]),
        messages=tuple(_original_message(m) for m in payload["messages"]),
    ).model_dump(mode="json")


@router.delete("/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    """NX-02: delete originals and the view together (explicit receipt).

    Deleted ids are not reused, so a client that deleted a conversation cannot
    silently resurrect it with a later append.
    """
    project_id = request.query_params.get("project_id") or _resolve_project_id(request, None, None)
    raw_expected = request.query_params.get("expected_revision")
    expected_revision = (
        None if raw_expected in (None, "") else _non_negative_int(raw_expected, default=0, field="expected_revision")
    )
    store = get_conversation_store()
    deleted = store.delete_conversation(
        project_id=project_id, conversation_id=conversation_id, expected_revision=expected_revision
    )
    return ConversationDeleteResponse(
        conversation_id=conversation_id,
        project_id=project_id,
        deleted=deleted,
        erased_scope="journal_and_view" if deleted else "nothing",
    ).model_dump(mode="json")


__all__ = ["router"]
