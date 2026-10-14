from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from antigravity_k.api.dependencies import get_scheduled_job_service
from antigravity_k.engine.scheduled_job_models import JobCreate, JobRun, JobUpdate, ScheduledJob
from antigravity_k.engine.scheduled_job_operations import (
    JobHealthPolicy,
    JobHealthSummary,
    JobRetryInProgressError,
    JobRetryResult,
    JobRunNotFoundError,
    JobRunStateError,
    ScheduledJobOperations,
)

router = APIRouter(prefix="/api/jobs")
LimitParam = Annotated[int, Query(ge=1, le=500)]
RunWindowParam = Annotated[int, Query(ge=1, le=10_000)]
StaleAfterParam = Annotated[int, Query(ge=1, le=604_800)]
FailureRateParam = Annotated[float, Query(ge=0.0, le=1.0)]


def _require_job(job_id: str) -> ScheduledJob:
    job = get_scheduled_job_service().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return job


@router.post("", response_model=ScheduledJob, status_code=status.HTTP_201_CREATED)
def create_job(request: JobCreate) -> ScheduledJob:
    return get_scheduled_job_service().create_job(request)


@router.get("", response_model=list[ScheduledJob])
def list_jobs(limit: LimitParam = 100) -> list[ScheduledJob]:
    return get_scheduled_job_service().list_jobs(limit)


@router.get("/health", response_model=JobHealthSummary)
def get_job_health(
    run_window: RunWindowParam = 500,
    stale_after_seconds: StaleAfterParam = 900,
    maximum_failure_rate: FailureRateParam = 0.05,
) -> JobHealthSummary:
    service = get_scheduled_job_service()
    return ScheduledJobOperations(service).health(
        JobHealthPolicy(
            run_window=run_window,
            stale_after_seconds=stale_after_seconds,
            maximum_failure_rate=maximum_failure_rate,
        )
    )


@router.get("/{job_id}", response_model=ScheduledJob)
def get_job(job_id: str) -> ScheduledJob:
    return _require_job(job_id)


@router.patch("/{job_id}", response_model=ScheduledJob)
def update_job(job_id: str, request: JobUpdate) -> ScheduledJob:
    _ = _require_job(job_id)
    return get_scheduled_job_service().update_job(job_id, request)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str) -> Response:
    if not get_scheduled_job_service().delete_job(job_id):
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/pause", response_model=ScheduledJob)
def pause_job(job_id: str) -> ScheduledJob:
    _ = _require_job(job_id)
    return get_scheduled_job_service().pause_job(job_id)


@router.post("/{job_id}/resume", response_model=ScheduledJob)
def resume_job(job_id: str) -> ScheduledJob:
    _ = _require_job(job_id)
    return get_scheduled_job_service().resume_job(job_id)


@router.post("/{job_id}/trigger", response_model=JobRun, status_code=status.HTTP_202_ACCEPTED)
def trigger_job(job_id: str) -> JobRun:
    _ = _require_job(job_id)
    return get_scheduled_job_service().trigger_job(job_id)


@router.get("/{job_id}/runs", response_model=list[JobRun])
def list_job_runs(job_id: str, limit: LimitParam = 100) -> list[JobRun]:
    _ = _require_job(job_id)
    return get_scheduled_job_service().list_runs(job_id, limit)


@router.post(
    "/{job_id}/runs/{run_id}/retry",
    response_model=JobRetryResult,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job_run(job_id: str, run_id: str) -> JobRetryResult:
    service = get_scheduled_job_service()
    try:
        return ScheduledJobOperations(service).retry_failed_run(job_id, run_id)
    except JobRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Scheduled job run not found") from error
    except JobRunStateError as error:
        raise HTTPException(status_code=409, detail="Only failed job runs can be retried") from error
    except JobRetryInProgressError as error:
        raise HTTPException(status_code=409, detail="Job run retry is already in progress") from error


__all__ = ["router"]
