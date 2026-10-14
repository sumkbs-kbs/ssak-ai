from __future__ import annotations

import hashlib
import hmac
import json
import os
import shlex
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from croniter import croniter

from antigravity_k.engine.sandbox import SandboxRunner
from antigravity_k.engine.scheduled_job_models import (
    JobCreate,
    JobRun,
    JobSchedule,
    JobUpdate,
    ScheduledJob,
    utc_now,
)
from antigravity_k.engine.scheduled_job_store import ScheduledJobStore


class AgentSubmitter(Protocol):
    def __call__(
        self,
        *,
        prompt: str,
        context: dict[str, object],
        target_model: str,
        use_worktree: bool,
        idempotency_key: str,
    ) -> str: ...


class TaskStatusReader(Protocol):
    def __call__(self, task_id: str) -> dict[str, object] | None: ...


CommandRunner = Callable[[list[str]], tuple[int, str, str]]
DeliverySender = Callable[[str, dict[str, object], str], None]


class ScheduledJobService:
    def __init__(
        self,
        store: ScheduledJobStore,
        submit_agent: AgentSubmitter,
        read_task_status: TaskStatusReader,
        command_runner: CommandRunner | None = None,
        delivery_sender: DeliverySender | None = None,
    ):
        self.store: ScheduledJobStore = store
        self.submit_agent: AgentSubmitter = submit_agent
        self.read_task_status: TaskStatusReader = read_task_status
        self.command_runner: CommandRunner = command_runner or _run_command
        self.delivery_sender: DeliverySender = delivery_sender or _send_webhook

    def create_job(self, request: JobCreate, now: datetime | None = None) -> ScheduledJob:
        current = _aware_utc(now or utc_now())
        next_run_at = _next_run(request.schedule, current)
        job = ScheduledJob(
            name=request.name,
            prompt=request.prompt,
            model=request.model,
            context=request.context,
            context_mode=request.context_mode,
            use_worktree=request.use_worktree,
            execution=request.execution,
            delivery=request.delivery,
            schedule=request.schedule,
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            created_at=current,
            updated_at=current,
            next_run_at=next_run_at,
        )
        return self.store.create(job)

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self.store.get(job_id)

    def list_jobs(self, limit: int = 200) -> list[ScheduledJob]:
        return self.store.list_jobs(limit)

    def update_job(self, job_id: str, request: JobUpdate, now: datetime | None = None) -> ScheduledJob:
        existing = self._require_job(job_id)
        current = _aware_utc(now or utc_now())
        changes = request.model_dump(exclude_unset=True, exclude_none=True)
        existing_spec = JobCreate.model_validate(existing.model_dump(include=set(JobCreate.model_fields)))
        merged_spec = JobCreate.model_validate({**existing_spec.model_dump(), **changes})
        next_run_at = existing.next_run_at
        if "schedule" in changes:
            next_run_at = _next_run(merged_spec.schedule, current)
        updated = ScheduledJob(
            name=merged_spec.name,
            prompt=merged_spec.prompt,
            model=merged_spec.model,
            context=merged_spec.context,
            context_mode=merged_spec.context_mode,
            use_worktree=merged_spec.use_worktree,
            execution=merged_spec.execution,
            delivery=merged_spec.delivery,
            schedule=merged_spec.schedule,
            job_id=existing.job_id,
            status=existing.status,
            created_at=existing.created_at,
            updated_at=current,
            next_run_at=next_run_at,
            last_run_at=existing.last_run_at,
        )
        return self.store.replace(updated)

    def pause_job(self, job_id: str, now: datetime | None = None) -> ScheduledJob:
        return self._set_status(job_id, "paused", now)

    def resume_job(self, job_id: str, now: datetime | None = None) -> ScheduledJob:
        existing = self._require_job(job_id)
        current = _aware_utc(now or utc_now())
        resumed = existing.model_copy(
            update={
                "status": "active",
                "updated_at": current,
                "next_run_at": _next_run(existing.schedule, current),
            }
        )
        return self.store.replace(resumed)

    def delete_job(self, job_id: str) -> bool:
        return self.store.delete(job_id)

    def trigger_job(
        self,
        job_id: str,
        now: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> JobRun:
        job = self._require_job(job_id)
        if idempotency_key:
            existing = self.store.get_run_by_idempotency(idempotency_key)
            if existing is not None:
                if existing.job_id != job_id:
                    raise ValueError("idempotency key is already associated with another job")
                return existing
        current = _aware_utc(now or utc_now())
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        if job.execution.kind == "command":
            run = self._execute_command(job, run_id, current)
        else:
            run = self._submit_agent(job, run_id, current, idempotency_key or run_id)
        if run.status in {"succeeded", "failed"}:
            run = self._deliver(job, run)
        _ = self.store.save_run(run, idempotency_key=idempotency_key)
        _ = self.store.replace(job.model_copy(update={"last_run_at": current, "updated_at": current}))
        return run

    def get_run_by_idempotency(self, idempotency_key: str) -> JobRun | None:
        return self.store.get_run_by_idempotency(idempotency_key)

    def tick(self, now: datetime | None = None) -> list[JobRun]:
        current = _aware_utc(now or utc_now())
        _ = self.reconcile_runs(now=current)
        runs: list[JobRun] = []
        for job in self.store.list_due(current):
            next_run_at = _next_after_execution(job.schedule, current)
            if not self.store.claim_due(job.job_id, current, next_run_at):
                continue
            runs.append(self.trigger_job(job.job_id, now=current))
        return runs

    def reconcile_runs(self, now: datetime | None = None) -> list[JobRun]:
        current = _aware_utc(now or utc_now())
        reconciled: list[JobRun] = []
        for run in self.store.list_open_runs():
            if run.task_id is None:
                continue
            task = self.read_task_status(run.task_id)
            if task is None:
                continue
            status = str(task.get("status", ""))
            if status == "done":
                updated = run.model_copy(
                    update={
                        "status": "succeeded",
                        "output": str(task.get("output", "")),
                        "completed_at": current,
                    }
                )
            elif status in {"failed", "cancelled"}:
                updated = run.model_copy(
                    update={
                        "status": "failed",
                        "error": str(task.get("error", status)),
                        "completed_at": current,
                    }
                )
            else:
                updated = run.model_copy(update={"status": "running"})
            if updated.status in {"succeeded", "failed"}:
                job = self.store.get(updated.job_id)
                if job is not None:
                    updated = self._deliver(job, updated)
            _ = self.store.save_run(updated)
            reconciled.append(updated)
        return reconciled

    def list_runs(self, job_id: str, limit: int = 100) -> list[JobRun]:
        _ = self._require_job(job_id)
        _ = self.reconcile_runs()
        return self.store.list_runs(job_id, limit)

    def _submit_agent(
        self,
        job: ScheduledJob,
        run_id: str,
        now: datetime,
        idempotency_key: str,
    ) -> JobRun:
        context: dict[str, object] = dict(job.context)
        context["scheduled_job_id"] = job.job_id
        if job.context_mode == "continue":
            previous_output = self.store.last_successful_output(job.job_id)
            if previous_output:
                context["previous_output"] = previous_output[-12_000:]
        try:
            task_id = self.submit_agent(
                prompt=job.prompt,
                context=context,
                target_model=job.model,
                use_worktree=job.use_worktree,
                idempotency_key=idempotency_key,
            )
        except (OSError, RuntimeError, ValueError) as error:
            return JobRun(
                run_id=run_id,
                job_id=job.job_id,
                status="failed",
                error=str(error),
                started_at=now,
                completed_at=now,
            )
        return JobRun(
            run_id=run_id,
            job_id=job.job_id,
            status="submitted",
            task_id=task_id,
            started_at=now,
        )

    def _execute_command(self, job: ScheduledJob, run_id: str, now: datetime) -> JobRun:
        try:
            return_code, output, error = self.command_runner(list(job.execution.command))
        except (OSError, ValueError) as exc:
            return_code, output, error = 1, "", str(exc)
        succeeded = return_code == 0
        return JobRun(
            run_id=run_id,
            job_id=job.job_id,
            status="succeeded" if succeeded else "failed",
            output=output,
            error=error,
            started_at=now,
            completed_at=now,
        )

    def _set_status(self, job_id: str, status: str, now: datetime | None) -> ScheduledJob:
        existing = self._require_job(job_id)
        current = _aware_utc(now or utc_now())
        updated = existing.model_copy(update={"status": status, "updated_at": current})
        return self.store.replace(updated)

    def _deliver(self, job: ScheduledJob, run: JobRun) -> JobRun:
        if job.delivery.kind == "none":
            return run.model_copy(update={"delivery_status": "not_configured"})
        secret = os.environ.get(job.delivery.secret_env, "") if job.delivery.secret_env else ""
        payload: dict[str, object] = {
            "run_id": run.run_id,
            "job_id": run.job_id,
            "status": run.status,
            "task_id": run.task_id,
            "output": run.output,
            "error": run.error,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        try:
            self.delivery_sender(job.delivery.target, payload, secret)
        except (OSError, RuntimeError, ValueError, httpx.HTTPError) as error:
            return run.model_copy(update={"delivery_status": "failed", "delivery_error": str(error)})
        return run.model_copy(update={"delivery_status": "sent", "delivery_error": ""})

    def _require_job(self, job_id: str) -> ScheduledJob:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


def _next_run(schedule: JobSchedule, base: datetime) -> datetime:
    if schedule.kind == "once":
        if schedule.run_at is None:
            raise ValueError("once schedules require run_at")
        return max(_aware_utc(schedule.run_at), base)
    if schedule.kind == "interval":
        if schedule.interval_seconds is None:
            raise ValueError("interval schedules require interval_seconds")
        return base + timedelta(seconds=schedule.interval_seconds)
    if schedule.cron is None:
        raise ValueError("cron schedules require cron")
    expression = schedule.cron
    if not croniter.is_valid(expression):
        raise ValueError(f"invalid cron expression: {expression}")
    return _aware_utc(croniter(expression, base).get_next(datetime))


def _next_after_execution(schedule: JobSchedule, base: datetime) -> datetime | None:
    if schedule.kind == "once":
        return None
    return _next_run(schedule, base)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


def _run_command(command: list[str]) -> tuple[int, str, str]:
    result = SandboxRunner(
        project_root=os.getcwd(),
        enabled=True,
        network="none",
        timeout=3_600,
        max_output_bytes=100_000,
    ).execute(shlex.join(command))
    error = result.stderr or result.error
    return result.return_code, result.stdout, error


def _send_webhook(target: str, payload: dict[str, object], secret: str) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-AGK-Signature"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    from antigravity_k.tools.egress_policy import validate_public_httpx_request

    with httpx.Client(
        event_hooks={"request": [validate_public_httpx_request]},
        follow_redirects=True,
        timeout=15,
    ) as client:
        response = client.post(target, content=body, headers=headers)
        _ = response.raise_for_status()


__all__ = ["ScheduledJobService"]
