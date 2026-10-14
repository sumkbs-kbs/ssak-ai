from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast, final

from antigravity_k.engine.scheduled_job_models import JobCreate, JobRun, ScheduledJob


class _RowLike(Protocol):
    def __getitem__(self, key: str) -> object: ...


class _CursorLike(Protocol):
    def fetchone(self) -> object: ...

    def fetchall(self) -> list[object]: ...


def _as_row(value: object) -> _RowLike:
    if not isinstance(value, sqlite3.Row):
        raise TypeError("expected sqlite row")
    return cast(_RowLike, cast(object, value))


def _fetchone(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> _RowLike | None:
    cursor = cast(_CursorLike, connection.execute(query, parameters))
    value = cursor.fetchone()
    return None if value is None else _as_row(value)


def _fetchall(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> list[_RowLike]:
    cursor = cast(_CursorLike, connection.execute(query, parameters))
    return [_as_row(value) for value in cursor.fetchall()]


@final
class ScheduledJobStore:
    def __init__(self, db_path: str) -> None:
        p = Path(db_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            test_file = p.parent / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            self.db_path = str(p)
        except OSError:
            fallback_dir = Path.home() / ".antigravity-k"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(fallback_dir / p.name)
        self.initialize()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        pragma_cursor = cast(_CursorLike, connection.execute("PRAGMA journal_mode=WAL"))
        _ = pragma_cursor.fetchone()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS scheduled_jobs ("
                + "job_id TEXT PRIMARY KEY, spec_json TEXT NOT NULL, status TEXT NOT NULL, "
                + "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, next_run_at TEXT, last_run_at TEXT)"
            )
            _ = connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due ON scheduled_jobs(status, next_run_at)"
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS scheduled_job_runs ("
                + "run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL, "
                + "task_id TEXT, output TEXT NOT NULL, error TEXT NOT NULL, "
                + "delivery_status TEXT NOT NULL DEFAULT 'not_configured', delivery_error TEXT NOT NULL DEFAULT '', "
                + "started_at TEXT NOT NULL, completed_at TEXT, idempotency_key TEXT, "
                + "FOREIGN KEY(job_id) REFERENCES scheduled_jobs(job_id) ON DELETE CASCADE)"
            )
            pragma_rows = _fetchall(connection, "PRAGMA table_info(scheduled_job_runs)")
            run_columns = {str(row["name"]) for row in pragma_rows}
            if "delivery_status" not in run_columns:
                _ = connection.execute(
                    "ALTER TABLE scheduled_job_runs ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'not_configured'"
                )
            if "delivery_error" not in run_columns:
                _ = connection.execute(
                    "ALTER TABLE scheduled_job_runs ADD COLUMN delivery_error TEXT NOT NULL DEFAULT ''"
                )
            if "idempotency_key" not in run_columns:
                _ = connection.execute("ALTER TABLE scheduled_job_runs ADD COLUMN idempotency_key TEXT")
            _ = connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduled_job_runs_job ON scheduled_job_runs(job_id, started_at DESC)"
            )
            _ = connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_job_runs_idempotency "
                "ON scheduled_job_runs(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )

    def create(self, job: ScheduledJob) -> ScheduledJob:
        spec = _job_spec(job).model_dump_json()
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT INTO scheduled_jobs "
                "(job_id, spec_json, status, created_at, updated_at, next_run_at, last_run_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    job.job_id,
                    spec,
                    job.status,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    _iso(job.next_run_at),
                    _iso(job.last_run_at),
                ),
            )
        return job

    def get(self, job_id: str) -> ScheduledJob | None:
        with self._connection() as connection:
            row = _fetchone(connection, "SELECT * FROM scheduled_jobs WHERE job_id = ?", (job_id,))
        return None if row is None else _job_from_row(row)

    def list_jobs(self, limit: int = 200) -> list[ScheduledJob]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT * FROM scheduled_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [_job_from_row(row) for row in rows]

    def list_due(self, now: datetime, limit: int = 100) -> list[ScheduledJob]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT * FROM scheduled_jobs WHERE status = 'active' "
                "AND next_run_at IS NOT NULL AND next_run_at <= ? "
                "ORDER BY next_run_at ASC LIMIT ?",
                (now.isoformat(), limit),
            )
        return [_job_from_row(row) for row in rows]

    def replace(self, job: ScheduledJob) -> ScheduledJob:
        spec = _job_spec(job).model_dump_json()
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE scheduled_jobs SET spec_json = ?, status = ?, updated_at = ?, "
                "next_run_at = ?, last_run_at = ? WHERE job_id = ?",
                (
                    spec,
                    job.status,
                    job.updated_at.isoformat(),
                    _iso(job.next_run_at),
                    _iso(job.last_run_at),
                    job.job_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(job.job_id)
        return job

    def claim_due(self, job_id: str, now: datetime, next_run_at: datetime | None) -> bool:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = _fetchone(
                connection,
                "SELECT next_run_at, status FROM scheduled_jobs WHERE job_id = ?",
                (job_id,),
            )
            if row is None or row["status"] != "active" or row["next_run_at"] is None:
                return False
            if datetime.fromisoformat(str(row["next_run_at"])) > now:
                return False
            status = "paused" if next_run_at is None else "active"
            cursor = connection.execute(
                "UPDATE scheduled_jobs SET status = ?, next_run_at = ?, last_run_at = ?, updated_at = ? "
                "WHERE job_id = ? AND status = 'active' AND next_run_at = ?",
                (
                    status,
                    _iso(next_run_at),
                    now.isoformat(),
                    now.isoformat(),
                    job_id,
                    row["next_run_at"],
                ),
            )
        return cursor.rowcount == 1

    def delete(self, job_id: str) -> bool:
        with self._connection() as connection:
            _ = connection.execute("DELETE FROM scheduled_job_runs WHERE job_id = ?", (job_id,))
            cursor = connection.execute("DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,))
        return cursor.rowcount == 1

    def save_run(self, run: JobRun, idempotency_key: str | None = None) -> JobRun:
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT INTO scheduled_job_runs "
                "(run_id, job_id, status, task_id, output, error, delivery_status, delivery_error, "
                "started_at, completed_at, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET job_id = excluded.job_id, status = excluded.status, "
                "task_id = excluded.task_id, output = excluded.output, error = excluded.error, "
                "delivery_status = excluded.delivery_status, delivery_error = excluded.delivery_error, "
                "started_at = excluded.started_at, completed_at = excluded.completed_at, "
                "idempotency_key = COALESCE(excluded.idempotency_key, scheduled_job_runs.idempotency_key)",
                (
                    run.run_id,
                    run.job_id,
                    run.status,
                    run.task_id,
                    run.output,
                    run.error,
                    run.delivery_status,
                    run.delivery_error,
                    run.started_at.isoformat(),
                    _iso(run.completed_at),
                    idempotency_key,
                ),
            )
        return run

    def get_run_by_idempotency(self, idempotency_key: str) -> JobRun | None:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                "SELECT * FROM scheduled_job_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            )
        return None if row is None else _run_from_row(row)

    def list_runs(self, job_id: str, limit: int = 100) -> list[JobRun]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT * FROM scheduled_job_runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            )
        return [_run_from_row(row) for row in rows]

    def list_open_runs(self, limit: int = 200) -> list[JobRun]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT * FROM scheduled_job_runs WHERE status IN ('submitted', 'running') "
                "ORDER BY started_at ASC LIMIT ?",
                (limit,),
            )
        return [_run_from_row(row) for row in rows]

    def last_successful_output(self, job_id: str) -> str:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                "SELECT output FROM scheduled_job_runs WHERE job_id = ? AND status = 'succeeded' "
                "ORDER BY started_at DESC LIMIT 1",
                (job_id,),
            )
        return "" if row is None else str(row["output"])


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _job_spec(job: ScheduledJob) -> JobCreate:
    return JobCreate.model_validate(job.model_dump(include=set(JobCreate.model_fields)))


def _job_from_row(row: _RowLike) -> ScheduledJob:
    spec = JobCreate.model_validate_json(str(row["spec_json"]))
    return ScheduledJob.model_validate(
        {
            **spec.model_dump(),
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "created_at": datetime.fromisoformat(str(row["created_at"])),
            "updated_at": datetime.fromisoformat(str(row["updated_at"])),
            "next_run_at": (None if row["next_run_at"] is None else datetime.fromisoformat(str(row["next_run_at"]))),
            "last_run_at": (None if row["last_run_at"] is None else datetime.fromisoformat(str(row["last_run_at"]))),
        }
    )


def _run_from_row(row: _RowLike) -> JobRun:
    return JobRun.model_validate(
        {
            "run_id": str(row["run_id"]),
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "task_id": None if row["task_id"] is None else str(row["task_id"]),
            "output": str(row["output"]),
            "error": str(row["error"]),
            "delivery_status": str(row["delivery_status"]),
            "delivery_error": str(row["delivery_error"]),
            "started_at": datetime.fromisoformat(str(row["started_at"])),
            "completed_at": (None if row["completed_at"] is None else datetime.fromisoformat(str(row["completed_at"]))),
        }
    )


__all__ = ["ScheduledJobStore"]
