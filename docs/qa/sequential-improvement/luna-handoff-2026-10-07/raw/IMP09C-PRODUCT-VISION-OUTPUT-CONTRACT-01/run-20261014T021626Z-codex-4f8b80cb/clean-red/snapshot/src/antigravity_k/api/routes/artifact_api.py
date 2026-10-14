from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from antigravity_k.api.dependencies import get_agent_runtime
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.artifact_provenance import (
    ArtifactManifest,
    ArtifactProvenanceError,
    ArtifactSource,
    create_manifest,
    record_manifest_event,
)
from antigravity_k.engine.direct_task_execution import TaskStoreRunnerPort
from antigravity_k.engine.task_runner import TaskStatus

router = APIRouter()


class InvalidArtifactPathError(ValueError):
    pass


class ArtifactProvenanceRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    paths: tuple[str, ...] = Field(min_length=1, max_length=128)
    source: ArtifactSource = "workspace"

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(path.strip() for path in value)
        if any(not path or Path(path).is_absolute() or ".." in Path(path).parts for path in normalized):
            raise InvalidArtifactPathError("artifact paths must be non-empty relative paths")
        return normalized


class ArtifactProvenanceResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: Literal["recorded"] = "recorded"
    task_id: str
    source: ArtifactSource
    digest: str
    sequence: int
    artifact_count: int = Field(ge=1)


class ArtifactManifestProvenanceRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    manifest: ArtifactManifest
    source: ArtifactSource = "workspace"


class ProvenanceTaskRegistrationRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    source: ArtifactSource
    idempotency_key: str = Field(min_length=1, max_length=256)


class ProvenanceTaskRegistrationResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: Literal["registered"] = "registered"
    task_id: str
    source: ArtifactSource


def _auth_subject(request: Request) -> str:
    subject = getattr(request.state, "auth_subject", "anonymous")
    return subject.strip() if isinstance(subject, str) and subject.strip() else "anonymous"


@router.post(
    "/api/tasks/provenance/register",
    response_model=ProvenanceTaskRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_provenance_task(
    payload: ProvenanceTaskRegistrationRequest,
    request: Request,
) -> ProvenanceTaskRegistrationResponse:
    runtime: AgentRuntime = get_agent_runtime()
    task_runner = runtime.task_runner
    if not isinstance(task_runner, TaskStoreRunnerPort):
        raise HTTPException(status_code=503, detail="Task event store is unavailable")
    owner_subject = _auth_subject(request)
    task_id = f"provenance_{uuid.uuid4().hex[:16]}"
    created_at = datetime.now(UTC).isoformat()
    stored_task_id = task_runner.state_store.create_task(
        task_id,
        f"Artifact provenance: {payload.source}",
        TaskStatus.PENDING,
        created_at,
        idempotency_key=payload.idempotency_key,
        owner_subject=owner_subject,
    )
    if stored_task_id == task_id:
        _ = task_runner.state_store.append_execution_event(
            stored_task_id,
            "artifact.provenance.task_registered",
            json.dumps({"source": payload.source}, sort_keys=True),
        )
    return ProvenanceTaskRegistrationResponse(task_id=stored_task_id, source=payload.source)


@router.post(
    "/api/tasks/{task_id}/provenance",
    response_model=ArtifactProvenanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_task_provenance(
    task_id: str,
    payload: ArtifactProvenanceRequest,
    request: Request,
) -> ArtifactProvenanceResponse:
    runtime: AgentRuntime = get_agent_runtime()
    owner_subject = _auth_subject(request)
    if runtime.get_task_status(task_id, owner_subject=owner_subject) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_runner = runtime.task_runner
    if not isinstance(task_runner, TaskStoreRunnerPort):
        raise HTTPException(status_code=503, detail="Task event store is unavailable")
    try:
        manifest = create_manifest(Path.cwd(), tuple(Path(path) for path in payload.paths))
        event = record_manifest_event(task_runner.state_store, task_id, manifest, source=payload.source)
    except ArtifactProvenanceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ArtifactProvenanceResponse(
        task_id=event.task_id,
        source=event.source,
        digest=event.digest,
        sequence=event.sequence,
        artifact_count=len(manifest.artifacts),
    )


@router.post(
    "/api/tasks/{task_id}/provenance/manifest",
    response_model=ArtifactProvenanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_task_manifest_provenance(
    task_id: str,
    payload: ArtifactManifestProvenanceRequest,
    request: Request,
) -> ArtifactProvenanceResponse:
    runtime: AgentRuntime = get_agent_runtime()
    owner_subject = _auth_subject(request)
    if runtime.get_task_status(task_id, owner_subject=owner_subject) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_runner = runtime.task_runner
    if not isinstance(task_runner, TaskStoreRunnerPort):
        raise HTTPException(status_code=503, detail="Task event store is unavailable")
    try:
        event = record_manifest_event(
            task_runner.state_store,
            task_id,
            payload.manifest,
            source=payload.source,
        )
    except ArtifactProvenanceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ArtifactProvenanceResponse(
        task_id=event.task_id,
        source=event.source,
        digest=event.digest,
        sequence=event.sequence,
        artifact_count=len(payload.manifest.artifacts),
    )


__all__ = ["router"]
