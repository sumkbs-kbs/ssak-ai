"""Authenticated execution of server-prepared cognitive actions.

Application composition must install CognitiveActiveService explicitly. The API
never accepts client authority, readiness, tool arguments or an approver identity.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from antigravity_k.api.auth_routes import extract_bearer_token, get_token_service
from antigravity_k.engine.cognitive_surface import CognitiveSurfaceAdapter, SurfaceEpisodeRequest, SurfaceNotReadyError

ActivationAuthorizer = Callable[[str, str, datetime], bool]


@dataclass(frozen=True)
class PreparedCognitiveAction:
    owner_subject: str
    project_id: str
    request: SurfaceEpisodeRequest


@dataclass(frozen=True)
class CognitiveActiveService:
    """Trusted server composition; factory creates a request-local adapter.

    All adapters must share the same durable journal and canonical store. Authority
    resolution belongs to that composition, never to the request JSON.
    """

    prepared: Mapping[str, PreparedCognitiveAction]
    build_adapter: Callable[[ActivationAuthorizer], CognitiveSurfaceAdapter]
    load_record: Callable[[str], object] | None = None


class ExecutePreparedAction(BaseModel):
    request_id: Annotated[str, Field(min_length=1, max_length=200)]
    action_digest: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]

    model_config = {"extra": "forbid"}


class PreparedActionView(BaseModel):
    request_id: str
    project_id: str
    tool: str
    scope: str
    action_digest: str
    arguments_json: str


class ActiveExecutionView(BaseModel):
    episode_id: str
    action_status: str | None
    refusal: str | None
    dispatched_actions: int
    refused_actions: int
    records: tuple[str, ...]
    note: str


class ObservePendingAction(BaseModel):
    action_key: Annotated[str, Field(min_length=1, max_length=200)]
    expected_receipt_id: Annotated[str, Field(min_length=1, max_length=200)]
    observed: bool
    succeeded: bool | None = None
    detail: Annotated[str, Field(default="", max_length=4000)]
    external_ref: Annotated[str, Field(default="", max_length=400)]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]

    model_config = {"extra": "forbid"}


class PendingClaimView(BaseModel):
    project_id: str
    action_key: str
    action_record_id: str
    receipt_id: str | None
    status: str
    pending_reason: str
    projection_revision: int


class ObservationResultView(BaseModel):
    accepted: bool
    refusal: str | None
    reason: str
    receipt_id: str | None
    observation_record_id: str | None
    projection_revision: int
    redispatched: bool


router = APIRouter(prefix="/active", tags=["cognitive"])


def _identity(request: Request) -> tuple[str, str]:
    token = extract_bearer_token(request)
    claims = get_token_service().verify_token(token) if token else None
    subject = claims.get("sub") if claims is not None else None
    if token is None or not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=401, detail="A verified bearer identity is required")
    return token, subject


def _service(request: Request) -> CognitiveActiveService:
    service = getattr(request.app.state, "cognitive_active_service", None)
    if not isinstance(service, CognitiveActiveService):
        raise HTTPException(status_code=503, detail="Cognitive ACTIVE service is not configured")
    return service


def _prepared(service: CognitiveActiveService, request_id: str, subject: str) -> PreparedCognitiveAction:
    prepared = service.prepared.get(request_id)
    if prepared is None or prepared.owner_subject != subject:
        raise HTTPException(status_code=404, detail="Prepared action not found")
    if prepared.request.intent is None:
        raise HTTPException(status_code=409, detail="Prepared request has no action")
    return prepared


@router.get("/requests/{request_id}")
def prepared_action_view(request_id: str, request: Request) -> PreparedActionView:
    _, subject = _identity(request)
    prepared = _prepared(_service(request), request_id, subject)
    intent = prepared.request.intent
    if intent is None:
        raise HTTPException(status_code=409, detail="Prepared request has no action")
    return PreparedActionView(
        request_id=request_id,
        project_id=prepared.project_id,
        tool=intent.tool,
        scope=intent.scope,
        action_digest=intent.to_intent().args_digest(),
        arguments_json=json.dumps(dict(intent.arguments), sort_keys=True, ensure_ascii=False, allow_nan=False),
    )


@router.post("/execute")
def execute_prepared_action(body: ExecutePreparedAction, request: Request) -> ActiveExecutionView:
    token, subject = _identity(request)
    service = _service(request)
    prepared = _prepared(service, body.request_id, subject)
    intent = prepared.request.intent
    if intent is None or intent.to_intent().args_digest() != body.action_digest:
        raise HTTPException(status_code=409, detail="Prepared action changed; review its current digest")

    def authorize(project_id: str, approver: str, now: datetime) -> bool:
        claims = get_token_service().verify_token(token)
        return (
            claims is not None
            and claims.get("sub") == subject
            and project_id == prepared.project_id
            and approver == f"human:{subject}"
        )

    adapter = service.build_adapter(authorize)
    if adapter.settings.project_id != prepared.project_id:
        raise HTTPException(status_code=409, detail="Prepared project does not match the execution context")
    try:
        adapter.activate(approver=f"human:{subject}", reason=body.reason)
        run = adapter.run_active(prepared.request)
    except SurfaceNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ActiveExecutionView(
        episode_id=run.episode_id,
        action_status=run.action_status,
        refusal=run.refusal,
        dispatched_actions=run.dispatched_actions,
        refused_actions=run.refused_actions,
        records=run.planned_records,
        note=run.note,
    )


@router.get("/pending")
def list_pending_claims(request: Request) -> list[PendingClaimView]:
    """Operator view of durable pending claims. Timeout never releases them."""
    token, subject = _identity(request)
    service = _service(request)
    # Any prepared action owned by subject defines the project scope we expose.
    projects = {item.project_id for item in service.prepared.values() if item.owner_subject == subject}
    if not projects:
        raise HTTPException(status_code=404, detail="No owned projects for pending lookup")

    def authorize(project_id: str, approver: str, now: datetime) -> bool:
        claims = get_token_service().verify_token(token)
        return (
            claims is not None
            and claims.get("sub") == subject
            and project_id in projects
            and approver == f"human:{subject}"
        )

    adapter = service.build_adapter(authorize)
    if adapter.settings.project_id not in projects:
        raise HTTPException(status_code=409, detail="Execution context project is not owned")
    pending = adapter.list_pending_actions()
    return [
        PendingClaimView(
            project_id=row.project_id,
            action_key=row.action_key,
            action_record_id=row.action_record_id,
            receipt_id=row.receipt_id,
            status=row.status,
            pending_reason=row.pending_reason,
            projection_revision=row.projection_revision,
        )
        for row in pending
    ]


@router.post("/observe")
def observe_pending_action(body: ObservePendingAction, request: Request) -> ObservationResultView:
    """Attach observation to a durable pending receipt. Never redispatches."""
    token, subject = _identity(request)
    service = _service(request)
    owned = [item for item in service.prepared.values() if item.owner_subject == subject]
    if not owned:
        raise HTTPException(status_code=404, detail="No owned project for observation")
    project_ids = {item.project_id for item in owned}

    def authorize(project_id: str, approver: str, now: datetime) -> bool:
        claims = get_token_service().verify_token(token)
        return (
            claims is not None
            and claims.get("sub") == subject
            and project_id in project_ids
            and approver == f"human:{subject}"
        )

    adapter = service.build_adapter(authorize)
    if adapter.settings.project_id not in project_ids:
        raise HTTPException(status_code=409, detail="Execution context project is not owned")
    if service.load_record is None:
        raise HTTPException(status_code=503, detail="Canonical record loader is not configured")
    try:
        adapter.activate(approver=f"human:{subject}", reason=body.reason)
        result = adapter.submit_observation(
            action_key=body.action_key,
            expected_receipt_id=body.expected_receipt_id,
            observed=body.observed,
            succeeded=body.succeeded,
            detail=body.detail,
            external_ref=body.external_ref,
            load_record=service.load_record,
        )
    except SurfaceNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.accepted:
        code = 409
        if result.refusal and result.refusal.value == "UNKNOWN_ACTION":
            code = 404
        elif result.refusal and result.refusal.value == "PROJECT_MISMATCH":
            code = 403
        raise HTTPException(
            status_code=code,
            detail={
                "refusal": None if result.refusal is None else result.refusal.value,
                "reason": result.reason,
            },
        )
    return ObservationResultView(
        accepted=True,
        refusal=None,
        reason=result.reason,
        receipt_id=result.receipt_id,
        observation_record_id=result.observation_record_id,
        projection_revision=result.projection_revision,
        redispatched=result.redispatched,
    )
