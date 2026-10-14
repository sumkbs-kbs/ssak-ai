from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import ClassVar, cast, final

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.engine.scheduled_job_models import JobRun, utc_now
from antigravity_k.engine.scheduled_job_service import ScheduledJobService


def _row_value(row: sqlite3.Row, key: str) -> object:
    return cast(object, row[key])


@final
class JobRunNotFoundError(LookupError):
    run_id: str

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(run_id)


@final
class JobRunStateError(RuntimeError):
    run_id: str
    status: str

    def __init__(self, run_id: str, status: str):
        self.run_id = run_id
        self.status = status
        super().__init__(f"run {run_id} is {status}")


@final
class JobRetryInProgressError(RuntimeError):
    run_id: str

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(run_id)


class JobHealthPolicy(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    run_window: int = Field(default=500, ge=1, le=10_000)
    stale_after_seconds: int = Field(default=900, ge=1, le=604_800)
    maximum_failure_rate: float = Field(default=0.05, ge=0.0, le=1.0)


class JobHealthSummary(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    run_window: int
    active_jobs: int = Field(ge=0)
    paused_jobs: int = Field(ge=0)
    open_runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    succeeded_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    delivery_failed_runs: int = Field(ge=0)
    stale_runs: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    healthy: bool
    reasons: tuple[str, ...] = ()


class JobRetryResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    source_run_id: str
    run: JobRun


@dataclass(frozen=True, slots=True)
class _RunState:
    job_id: str
    status: str


@dataclass(frozen=True, slots=True)
class _RetryClaim:
    created: bool
    retry_run_id: str | None


class ScheduledJobOperations:
    _service: ScheduledJobService
    _db_path: str

    def __init__(self, service: ScheduledJobService):
        self._service = service
        self._db_path = service.store.db_path
        self._initialize()

    def health(
        self,
        policy: JobHealthPolicy | None = None,
        now: datetime | None = None,
    ) -> JobHealthSummary:
        active_policy = policy or JobHealthPolicy()
        current = (now or utc_now()).astimezone(UTC)
        _ = self._service.reconcile_runs(now=current)
        with self._connection() as connection:
            job_rows = cast(
                list[sqlite3.Row],
                connection.execute("SELECT status, COUNT(*) AS count FROM scheduled_jobs GROUP BY status").fetchall(),
            )
            run_rows = cast(
                list[sqlite3.Row],
                connection.execute(
                    "SELECT status, delivery_status, started_at FROM scheduled_job_runs ORDER BY started_at DESC LIMIT ?",
                    (active_policy.run_window,),
                ).fetchall(),
            )
        jobs = {str(_row_value(row, "status")): int(str(_row_value(row, "count"))) for row in job_rows}
        succeeded = sum(str(_row_value(row, "status")) == "succeeded" for row in run_rows)
        failed = sum(str(_row_value(row, "status")) == "failed" for row in run_rows)
        open_runs = sum(str(_row_value(row, "status")) in {"submitted", "running"} for row in run_rows)
        delivery_failed = sum(str(_row_value(row, "delivery_status")) == "failed" for row in run_rows)
        stale_cutoff = current - timedelta(seconds=active_policy.stale_after_seconds)
        stale = sum(
            str(_row_value(row, "status")) in {"submitted", "running"}
            and datetime.fromisoformat(str(_row_value(row, "started_at"))).astimezone(UTC) < stale_cutoff
            for row in run_rows
        )
        completed = succeeded + failed
        success_rate = 1.0 if completed == 0 else succeeded / completed
        failure_rate = 1.0 - success_rate
        reasons: list[str] = []
        if failure_rate > active_policy.maximum_failure_rate:
            reasons.append("failure rate exceeds policy")
        if delivery_failed:
            reasons.append("webhook delivery failures detected")
        if stale:
            reasons.append("stale runs detected")
        return JobHealthSummary(
            generated_at=current,
            run_window=active_policy.run_window,
            active_jobs=jobs.get("active", 0),
            paused_jobs=jobs.get("paused", 0),
            open_runs=open_runs,
            completed_runs=completed,
            succeeded_runs=succeeded,
            failed_runs=failed,
            delivery_failed_runs=delivery_failed,
            stale_runs=stale,
            success_rate=round(success_rate, 6),
            healthy=not reasons,
            reasons=tuple(reasons),
        )

    def retry_failed_run(
        self,
        job_id: str,
        source_run_id: str,
        now: datetime | None = None,
    ) -> JobRetryResult:
        current = (now or utc_now()).astimezone(UTC)
        _ = self._service.reconcile_runs(now=current)
        source = self._run_state(source_run_id)
        if source is None or source.job_id != job_id:
            raise JobRunNotFoundError(source_run_id)
        if source.status != "failed":
            raise JobRunStateError(source_run_id, source.status)
        claim = self._claim_retry(source_run_id, job_id, current)
        if not claim.created:
            if claim.retry_run_id is None:
                raise JobRetryInProgressError(source_run_id)
            existing = next(
                (run for run in self._service.store.list_runs(job_id, 500) if run.run_id == claim.retry_run_id),
                None,
            )
            if existing is None:
                raise JobRetryInProgressError(source_run_id)
            return JobRetryResult(source_run_id=source_run_id, run=existing)
        run = self._service.trigger_job(
            job_id,
            now=current,
            idempotency_key=f"scheduled-job-retry:{source_run_id}",
        )
        self._bind_retry(source_run_id, run.run_id)
        return JobRetryResult(source_run_id=source_run_id, run=run)

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        _ = cast(object, connection.execute("PRAGMA journal_mode=WAL").fetchone())
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS scheduled_job_retries ("
                + "source_run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, retry_run_id TEXT, created_at TEXT NOT NULL)"
            )

    def _run_state(self, run_id: str) -> _RunState | None:
        with self._connection() as connection:
            row = cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT job_id, status FROM scheduled_job_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone(),
            )
        if row is None:
            return None
        return _RunState(job_id=str(_row_value(row, "job_id")), status=str(_row_value(row, "status")))

    def _claim_retry(self, source_run_id: str, job_id: str, now: datetime) -> _RetryClaim:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO scheduled_job_retries "
                + "(source_run_id, job_id, retry_run_id, created_at) VALUES (?, ?, NULL, ?)",
                (source_run_id, job_id, now.isoformat()),
            )
            row = cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT retry_run_id FROM scheduled_job_retries WHERE source_run_id = ?",
                    (source_run_id,),
                ).fetchone(),
            )
        retry_run_id = (
            None if row is None or _row_value(row, "retry_run_id") is None else str(_row_value(row, "retry_run_id"))
        )
        return _RetryClaim(created=cursor.rowcount == 1, retry_run_id=retry_run_id)

    def _bind_retry(self, source_run_id: str, retry_run_id: str) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "UPDATE scheduled_job_retries SET retry_run_id = ? WHERE source_run_id = ?",
                (retry_run_id, source_run_id),
            )


__all__ = [
    "JobHealthPolicy",
    "JobHealthSummary",
    "JobRetryInProgressError",
    "JobRetryResult",
    "JobRunNotFoundError",
    "JobRunStateError",
    "ScheduledJobOperations",
]
