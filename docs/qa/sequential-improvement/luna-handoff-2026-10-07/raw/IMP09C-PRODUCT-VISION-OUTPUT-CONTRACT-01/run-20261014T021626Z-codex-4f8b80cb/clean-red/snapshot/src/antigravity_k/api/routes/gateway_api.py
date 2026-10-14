from __future__ import annotations

from typing import ClassVar, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from antigravity_k.api.dependencies import get_scheduled_job_service
from antigravity_k.engine.scheduled_job_models import (
    JobCreate,
    JobDelivery,
    JobSchedule,
    utc_now,
)

router = APIRouter(prefix="/api/gateway")


class GatewayMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    channel: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    sender_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    model: str = ""
    context_mode: Literal["fresh", "continue"] = "fresh"
    reply_webhook: str = ""
    idempotency_key: str | None = Field(default=None, max_length=200)

    @field_validator("sender_id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class GatewayAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    job_id: str
    run_id: str
    task_id: str | None


@router.post("/messages", response_model=GatewayAccepted, status_code=status.HTTP_202_ACCEPTED)
def accept_gateway_message(request: GatewayMessage) -> GatewayAccepted:
    service = get_scheduled_job_service()
    now = utc_now()
    delivery = (
        JobDelivery(
            kind="webhook",
            target=request.reply_webhook,
            secret_env="AGK_GATEWAY_WEBHOOK_SECRET",
        )
        if request.reply_webhook
        else JobDelivery()
    )
    submission_key = f"gateway:{request.channel}:{request.idempotency_key}" if request.idempotency_key else None
    if submission_key:
        existing = service.get_run_by_idempotency(submission_key)
        if existing is not None:
            return GatewayAccepted(job_id=existing.job_id, run_id=existing.run_id, task_id=existing.task_id)
    job = service.create_job(
        JobCreate(
            name=f"{request.channel}:{request.sender_id}",
            prompt=request.text,
            model=request.model,
            context={
                "gateway": {
                    "channel": request.channel,
                    "sender_id": request.sender_id,
                    "idempotency_key": request.idempotency_key,
                }
            },
            context_mode=request.context_mode,
            delivery=delivery,
            schedule=JobSchedule(kind="once", run_at=now),
        ),
        now=now,
    )
    run = service.trigger_job(job.job_id, now=now, idempotency_key=submission_key)
    return GatewayAccepted(job_id=job.job_id, run_id=run.run_id, task_id=run.task_id)


__all__ = ["router"]
