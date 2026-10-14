"""SQLite persistence primitives for the persistent agency layer."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeAlias, cast, final

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class _RowLike(Protocol):
    def __getitem__(self, key: str) -> object: ...


class _CursorLike(Protocol):
    lastrowid: int | None
    rowcount: int

    def fetchone(self) -> _RowLike | None: ...

    def fetchall(self) -> list[_RowLike]: ...


class EventType(StrEnum):
    """Stable event types stored in the append-only trajectory."""

    OBSERVATION = "observation"
    THOUGHT = "thought"
    DECISION = "decision"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    SUMMARY = "summary"
    FAILURE = "failure"


class ObjectiveStatus(StrEnum):
    """Lifecycle states for a durable objective."""

    PENDING = "pending"
    CLAIMED = "claimed"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TrajectoryEvent:
    """One immutable event in a project-scoped trajectory."""

    event_id: int
    project_id: str
    trajectory_id: str
    branch_id: str
    parent_event_id: int | None
    event_type: EventType
    payload: Mapping[str, JsonValue]
    sensitivity: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Objective:
    """A durable objective that can be claimed exactly once per state."""

    objective_id: str
    project_id: str
    title: str
    description: str
    priority: int
    status: ObjectiveStatus
    trajectory_id: str
    created_at: str
    updated_at: str


@final
class PersistentAgencyStore:
    """SQLite-backed append-only trajectory and objective store."""

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
        self._initialize()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS agency_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, trajectory_id TEXT NOT NULL, branch_id TEXT NOT NULL, parent_event_id INTEGER, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, sensitivity TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            _ = connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agency_events_scope ON agency_events (project_id, trajectory_id, event_id)"
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS agency_objectives (objective_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, priority INTEGER NOT NULL, status TEXT NOT NULL, trajectory_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            _ = connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agency_objectives_queue ON agency_objectives (project_id, status, priority DESC, created_at)"
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS agency_controls (project_id TEXT PRIMARY KEY, paused INTEGER NOT NULL DEFAULT 0)"
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS agency_objective_tasks (task_id TEXT PRIMARY KEY, objective_id TEXT NOT NULL, project_id TEXT NOT NULL, trajectory_id TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            _ = connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agency_objective_tasks_objective ON agency_objective_tasks (objective_id)"
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS agency_task_results (task_id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def append_event(
        self,
        project_id: str,
        trajectory_id: str,
        branch_id: str,
        parent_event_id: int | None,
        event_type: EventType,
        payload: Mapping[str, JsonValue],
        sensitivity: str,
    ) -> TrajectoryEvent:
        created_at = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO agency_events (project_id, trajectory_id, branch_id, parent_event_id, event_type, payload_json, sensitivity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    trajectory_id,
                    branch_id,
                    parent_event_id,
                    event_type.value,
                    json.dumps(payload, ensure_ascii=False),
                    sensitivity,
                    created_at,
                ),
            )
            event_id = cursor.lastrowid
        if event_id is None:
            raise sqlite3.DatabaseError("agency event insert did not return an id")
        return TrajectoryEvent(
            event_id,
            project_id,
            trajectory_id,
            branch_id,
            parent_event_id,
            event_type,
            dict(payload),
            sensitivity,
            created_at,
        )

    def list_events(self, project_id: str, trajectory_id: str, limit: int = 1_000) -> list[TrajectoryEvent]:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT event_id, project_id, trajectory_id, branch_id, parent_event_id, event_type, payload_json, sensitivity, created_at FROM agency_events WHERE project_id = ? AND trajectory_id = ? ORDER BY event_id ASC LIMIT ?",
                        (project_id, trajectory_id, limit),
                    ),
                ),
            )
            rows = cursor.fetchall()
        return [self._event_from_row(row) for row in rows]

    def create_objective(self, objective: Objective) -> Objective:
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT INTO agency_objectives VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    objective.objective_id,
                    objective.project_id,
                    objective.title,
                    objective.description,
                    objective.priority,
                    objective.status.value,
                    objective.trajectory_id,
                    objective.created_at,
                    objective.updated_at,
                ),
            )
        return objective

    def get_objective(self, objective_id: str) -> Objective | None:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute("SELECT * FROM agency_objectives WHERE objective_id = ?", (objective_id,)),
                ),
            )
            row = cursor.fetchone()
        return self._objective_from_row(row) if row else None

    def list_objectives(self, project_id: str, limit: int = 100) -> list[Objective]:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT * FROM agency_objectives WHERE project_id = ? ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                        (project_id, max(1, limit)),
                    ),
                ),
            )
            rows = cursor.fetchall()
        return [self._objective_from_row(row) for row in rows]

    def claim_next_objective(self, project_id: str) -> Objective | None:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT * FROM agency_objectives WHERE project_id = ? AND status = ? ORDER BY priority DESC, created_at ASC LIMIT 1",
                        (project_id, ObjectiveStatus.PENDING.value),
                    ),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            updated_at = datetime.now(UTC).isoformat()
            _ = connection.execute(
                "UPDATE agency_objectives SET status = ?, updated_at = ? WHERE objective_id = ? AND status = ?",
                (ObjectiveStatus.CLAIMED.value, updated_at, row["objective_id"], ObjectiveStatus.PENDING.value),
            )
            return Objective(
                str(row["objective_id"]),
                str(row["project_id"]),
                str(row["title"]),
                str(row["description"]),
                int(cast(int | str, row["priority"])),
                ObjectiveStatus.CLAIMED,
                str(row["trajectory_id"]),
                str(row["created_at"]),
                updated_at,
            )

    def reclaim_stale_objectives(self, lease_seconds: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(seconds=max(0, lease_seconds))).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE agency_objectives SET status = ?, updated_at = ? WHERE status = ? AND updated_at < ?",
                (ObjectiveStatus.PENDING.value, datetime.now(UTC).isoformat(), ObjectiveStatus.CLAIMED.value, cutoff),
            )
        return cursor.rowcount

    def complete_objective(self, objective_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE agency_objectives SET status = ?, updated_at = ? WHERE objective_id = ? AND status = ?",
                (
                    ObjectiveStatus.DONE.value,
                    datetime.now(UTC).isoformat(),
                    objective_id,
                    ObjectiveStatus.CLAIMED.value,
                ),
            )
        return cursor.rowcount == 1

    def requeue_objective(self, objective_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE agency_objectives SET status = ?, updated_at = ? WHERE objective_id = ? AND status = ?",
                (
                    ObjectiveStatus.PENDING.value,
                    datetime.now(UTC).isoformat(),
                    objective_id,
                    ObjectiveStatus.CLAIMED.value,
                ),
            )
        return cursor.rowcount == 1

    def bind_objective_task(self, task_id: str, objective_id: str, project_id: str, trajectory_id: str) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT OR REPLACE INTO agency_objective_tasks (task_id, objective_id, project_id, trajectory_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, objective_id, project_id, trajectory_id, datetime.now(UTC).isoformat()),
            )

    def objective_task(self, task_id: str) -> tuple[str, str, str] | None:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT objective_id, project_id, trajectory_id FROM agency_objective_tasks WHERE task_id = ?",
                        (task_id,),
                    ),
                ),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return str(row["objective_id"]), str(row["project_id"]), str(row["trajectory_id"])

    def mark_task_result(self, task_id: str, status: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO agency_task_results (task_id, status, created_at) VALUES (?, ?, ?)",
                (task_id, status, datetime.now(UTC).isoformat()),
            )
        return cursor.rowcount == 1

    def list_objective_tasks(self, project_id: str) -> list[str]:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT t.task_id FROM agency_objective_tasks AS t JOIN agency_objectives AS o ON o.objective_id = t.objective_id WHERE t.project_id = ? AND o.status = ? ORDER BY t.created_at ASC",
                        (project_id, ObjectiveStatus.CLAIMED.value),
                    ),
                ),
            )
            rows = cursor.fetchall()
        return [str(row["task_id"]) for row in rows]

    def has_pending_objective(self, project_id: str) -> bool:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object,
                    connection.execute(
                        "SELECT 1 FROM agency_objectives WHERE project_id = ? AND status IN (?, ?) LIMIT 1",
                        (project_id, ObjectiveStatus.PENDING.value, ObjectiveStatus.CLAIMED.value),
                    ),
                ),
            )
            row = cursor.fetchone()
        return row is not None

    def set_paused(self, project_id: str, paused: bool) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT INTO agency_controls (project_id, paused) VALUES (?, ?) ON CONFLICT(project_id) DO UPDATE SET paused = excluded.paused",
                (project_id, int(paused)),
            )

    def is_paused(self, project_id: str) -> bool:
        with self._connection() as connection:
            cursor = cast(
                _CursorLike,
                cast(
                    object, connection.execute("SELECT paused FROM agency_controls WHERE project_id = ?", (project_id,))
                ),
            )
            row = cursor.fetchone()
        return bool(row and row["paused"])

    @staticmethod
    def _event_from_row(row: _RowLike) -> TrajectoryEvent:
        return TrajectoryEvent(
            int(cast(int | str, row["event_id"])),
            str(row["project_id"]),
            str(row["trajectory_id"]),
            str(row["branch_id"]),
            cast(int | None, row["parent_event_id"]),
            EventType(str(row["event_type"])),
            cast(
                Mapping[str, JsonValue],
                cast(object, json.loads(str(row["payload_json"]))),
            ),
            str(row["sensitivity"]),
            str(row["created_at"]),
        )

    @staticmethod
    def _objective_from_row(row: _RowLike) -> Objective:
        return Objective(
            str(row["objective_id"]),
            str(row["project_id"]),
            str(row["title"]),
            str(row["description"]),
            int(cast(int | str, row["priority"])),
            ObjectiveStatus(str(row["status"])),
            str(row["trajectory_id"]),
            str(row["created_at"]),
            str(row["updated_at"]),
        )


__all__ = ["EventType", "JsonValue", "Objective", "ObjectiveStatus", "PersistentAgencyStore", "TrajectoryEvent"]
