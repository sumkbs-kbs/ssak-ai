from __future__ import annotations

from typing import Annotated, ClassVar

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from antigravity_k.api.dependencies import get_agent_runtime
from antigravity_k.engine.persistent_agency import (
    Objective,
    PersistentAgencyController,
    ProjectedContext,
    SchedulerDecision,
)

router = APIRouter(prefix="/api/agency")


class ObjectiveCreateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=8_000)
    priority: int = Field(default=0, ge=-1_000, le=1_000)
    trajectory_id: str = Field(default="main", min_length=1, max_length=128)

    @field_validator("title", "trajectory_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AgencyScopeRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=512)


class ObjectiveResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    objective_id: str
    project_id: str
    title: str
    description: str
    priority: int
    status: str
    trajectory_id: str
    created_at: str
    updated_at: str

    @classmethod
    def from_objective(cls, objective: Objective) -> ObjectiveResponse:
        return cls(
            objective_id=objective.objective_id,
            project_id=objective.project_id,
            title=objective.title,
            description=objective.description,
            priority=objective.priority,
            status=objective.status.value,
            trajectory_id=objective.trajectory_id,
            created_at=objective.created_at,
            updated_at=objective.updated_at,
        )


class SchedulerResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    should_wake: bool
    reason: str
    delay_seconds: int
    objective_id: str | None

    @classmethod
    def from_decision(cls, decision: SchedulerDecision) -> SchedulerResponse:
        return cls(
            should_wake=decision.should_wake,
            reason=decision.reason,
            delay_seconds=decision.delay_seconds,
            objective_id=decision.objective_id,
        )


class AgencyStatusResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    project_id: str
    enabled: bool
    paused: bool
    scheduler: SchedulerResponse
    context_text: str
    context_event_ids: tuple[int, ...]
    objective_task_ids: tuple[str, ...]


class AgencyPauseResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    project_id: str
    paused: bool


def _agency() -> PersistentAgencyController:
    runtime = get_agent_runtime()
    controller = getattr(getattr(runtime, "orchestrator", None), "persistent_agency", None)
    if not isinstance(controller, PersistentAgencyController):
        raise HTTPException(status_code=503, detail="Persistent agency is unavailable")
    return controller


def _project_id(controller: PersistentAgencyController, requested: str | None) -> str:
    project_id = requested or controller.project_id
    if project_id != controller.project_id:
        raise HTTPException(status_code=403, detail="Project scope mismatch")
    return project_id


def _context_payload(context: ProjectedContext) -> tuple[str, tuple[int, ...]]:
    return context.text, context.event_ids


@router.post(
    "/objectives",
    response_model=ObjectiveResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_objective(request: ObjectiveCreateRequest) -> ObjectiveResponse:
    controller = _agency()
    project_id = _project_id(controller, request.project_id)
    objective = controller.enqueue_objective(
        project_id=project_id,
        title=request.title,
        description=request.description.strip(),
        priority=request.priority,
        trajectory_id=request.trajectory_id,
    )
    return ObjectiveResponse.from_objective(objective)


@router.get("/objectives", response_model=list[ObjectiveResponse])
def list_objectives(
    project_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ObjectiveResponse]:
    controller = _agency()
    scope = _project_id(controller, project_id)
    return [ObjectiveResponse.from_objective(item) for item in controller.list_objectives(scope, limit=limit)]


@router.get("/objectives/{objective_id}", response_model=ObjectiveResponse)
def get_objective(objective_id: str) -> ObjectiveResponse:
    controller = _agency()
    objective = controller.get_objective(objective_id)
    if objective is None or objective.project_id != controller.project_id:
        raise HTTPException(status_code=404, detail="Objective not found")
    return ObjectiveResponse.from_objective(objective)


@router.get("/status", response_model=AgencyStatusResponse)
def agency_status(
    project_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    trajectory_id: Annotated[str, Query(min_length=1, max_length=128)] = "main",
    query: Annotated[str, Query(max_length=2_000)] = "",
    idle_cycles: Annotated[int, Query(ge=0, le=100)] = 0,
) -> AgencyStatusResponse:
    controller = _agency()
    scope = _project_id(controller, project_id)
    context = controller.project_context(scope, trajectory_id.strip(), query)
    scheduler = controller.scheduler_decision(scope, idle_cycles=idle_cycles)
    text, event_ids = _context_payload(context)
    return AgencyStatusResponse(
        project_id=scope,
        enabled=controller.config.enabled,
        paused=controller.store.is_paused(scope),
        scheduler=SchedulerResponse.from_decision(scheduler),
        context_text=text,
        context_event_ids=event_ids,
        objective_task_ids=tuple(controller.list_objective_tasks(scope)),
    )


@router.post("/pause", response_model=AgencyPauseResponse)
def pause_agency(request: AgencyScopeRequest) -> AgencyPauseResponse:
    controller = _agency()
    project_id = _project_id(controller, request.project_id)
    controller.pause(project_id)
    return AgencyPauseResponse(project_id=project_id, paused=True)


@router.post("/resume", response_model=AgencyPauseResponse)
def resume_agency(request: AgencyScopeRequest) -> AgencyPauseResponse:
    controller = _agency()
    project_id = _project_id(controller, request.project_id)
    controller.resume(project_id)
    return AgencyPauseResponse(project_id=project_id, paused=False)


__all__ = ["router"]
