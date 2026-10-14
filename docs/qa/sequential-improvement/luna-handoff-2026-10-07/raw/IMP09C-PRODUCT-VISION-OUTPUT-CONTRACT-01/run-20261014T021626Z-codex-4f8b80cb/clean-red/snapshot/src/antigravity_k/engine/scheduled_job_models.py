from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Literal, Self

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class JobSchedule(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["once", "interval", "cron"]
    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    cron: str | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        cron_expression = (self.cron or "").strip()
        if self.kind == "once" and self.run_at is None:
            raise ValueError("once schedules require run_at")
        if self.kind == "interval" and self.interval_seconds is None:
            raise ValueError("interval schedules require interval_seconds")
        if self.kind == "cron" and not cron_expression:
            raise ValueError("cron schedules require cron")
        if self.kind == "cron" and not croniter.is_valid(cron_expression):
            raise ValueError("invalid cron expression")
        if self.run_at is not None and self.run_at.tzinfo is None:
            raise ValueError("run_at must include a timezone")
        return self


class JobExecution(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["agent", "command"] = "agent"
    command: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_execution(self) -> Self:
        if self.kind == "command" and not self.command:
            raise ValueError("command execution requires command arguments")
        if self.kind == "agent" and self.command:
            raise ValueError("agent execution does not accept command arguments")
        if any(not value.strip() for value in self.command):
            raise ValueError("command arguments must not be blank")
        return self


class JobDelivery(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["none", "webhook"] = "none"
    target: str = ""
    secret_env: str = ""

    @model_validator(mode="after")
    def validate_delivery(self) -> Self:
        if self.kind == "webhook" and not self.target.strip():
            raise ValueError("webhook delivery requires target")
        if self.kind == "none" and (self.target or self.secret_env):
            raise ValueError("disabled delivery does not accept webhook settings")
        return self


class JobCreate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1)
    model: str = ""
    context: dict[str, JsonValue] = Field(default_factory=dict)
    context_mode: Literal["fresh", "continue"] = "fresh"
    use_worktree: bool = False
    execution: JobExecution = Field(default_factory=JobExecution)
    delivery: JobDelivery = Field(default_factory=JobDelivery)
    schedule: JobSchedule

    @field_validator("name", "prompt")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class JobUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    prompt: str | None = Field(default=None, min_length=1)
    model: str | None = None
    context: dict[str, JsonValue] | None = None
    context_mode: Literal["fresh", "continue"] | None = None
    use_worktree: bool | None = None
    execution: JobExecution | None = None
    delivery: JobDelivery | None = None
    schedule: JobSchedule | None = None

    @field_validator("name", "prompt")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class ScheduledJob(JobCreate):
    job_id: str
    status: Literal["active", "paused"] = "active"
    created_at: datetime
    updated_at: datetime
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class JobRun(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    job_id: str
    status: Literal["submitted", "running", "succeeded", "failed"]
    task_id: str | None = None
    output: str = ""
    error: str = ""
    delivery_status: Literal["not_configured", "pending", "sent", "failed"] = "not_configured"
    delivery_error: str = ""
    started_at: datetime
    completed_at: datetime | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "JobCreate",
    "JobDelivery",
    "JobExecution",
    "JobRun",
    "JobSchedule",
    "JobUpdate",
    "ScheduledJob",
    "utc_now",
]
