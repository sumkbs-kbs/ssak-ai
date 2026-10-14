from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, TypedDict, cast

RUN_EVENT_SCHEMA_VERSION: Final[int] = 2


@dataclass(frozen=True, slots=True)
class RunEventMetadata:
    step_id: str | None = None
    agent_id: str | None = None
    parent_id: str | None = None
    tool_call_id: str | None = None
    approval_id: str | None = None
    resource_job_id: str | None = None
    correlation_id: str | None = None


class ExecutionEventRecord(TypedDict):
    sequence: int
    schema_version: int
    task_id: str
    step_id: str | None
    agent_id: str | None
    parent_id: str | None
    tool_call_id: str | None
    approval_id: str | None
    resource_job_id: str | None
    correlation_id: str | None
    event_type: str
    payload_json: str
    created_at: str


_OPTIONAL_EVENT_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("step_id", "TEXT"),
    ("agent_id", "TEXT"),
    ("parent_id", "TEXT"),
    ("tool_call_id", "TEXT"),
    ("approval_id", "TEXT"),
    ("resource_job_id", "TEXT"),
    ("correlation_id", "TEXT"),
)


def initialize_execution_event_schema(connection: sqlite3.Connection) -> None:
    _ = connection.execute(
        "CREATE TABLE IF NOT EXISTS task_execution_events ("
        + "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
        + "schema_version INTEGER NOT NULL DEFAULT 2, "
        + "task_id TEXT NOT NULL, step_id TEXT, agent_id TEXT, parent_id TEXT, "
        + "tool_call_id TEXT, approval_id TEXT, resource_job_id TEXT, correlation_id TEXT, "
        + "event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
    )
    table_info_rows = cast(
        list[sqlite3.Row],
        connection.execute("PRAGMA table_info(task_execution_events)").fetchall(),
    )
    columns = {str(cast(object, row["name"])) for row in table_info_rows}
    if "schema_version" not in columns:
        _ = connection.execute("ALTER TABLE task_execution_events ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1")
    for column_name, column_type in _OPTIONAL_EVENT_COLUMNS:
        if column_name not in columns:
            _ = connection.execute(f"ALTER TABLE task_execution_events ADD COLUMN {column_name} {column_type}")
    _ = connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_execution_events_task_sequence ON task_execution_events (task_id, sequence)",
    )


def append_execution_event(
    connection: sqlite3.Connection,
    task_id: str,
    event_type: str,
    payload_json: str,
    metadata: RunEventMetadata | None = None,
) -> int:
    details = metadata or RunEventMetadata()
    cursor = connection.execute(
        "INSERT INTO task_execution_events ("
        "schema_version, task_id, step_id, agent_id, parent_id, tool_call_id, "
        "approval_id, resource_job_id, correlation_id, event_type, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            RUN_EVENT_SCHEMA_VERSION,
            task_id,
            details.step_id,
            details.agent_id,
            details.parent_id,
            details.tool_call_id,
            details.approval_id,
            details.resource_job_id,
            details.correlation_id,
            event_type,
            payload_json,
            datetime.now(UTC).isoformat(),
        ),
    )
    sequence = cursor.lastrowid
    if sequence is None:
        raise sqlite3.DatabaseError("execution event insert did not return a sequence")
    return sequence


def list_execution_events(
    connection: sqlite3.Connection,
    task_id: str,
    after_sequence: int = 0,
    limit: int = 1_000,
) -> list[ExecutionEventRecord]:
    if after_sequence < 0:
        raise ValueError("after_sequence must be non-negative")
    if limit < 1:
        raise ValueError("limit must be positive")
    rows = cast(
        list[sqlite3.Row],
        connection.execute(
            "SELECT sequence, schema_version, task_id, step_id, agent_id, parent_id, tool_call_id, approval_id, "
            + "resource_job_id, correlation_id, event_type, payload_json, created_at FROM task_execution_events "
            + "WHERE task_id = ? AND sequence > ? ORDER BY sequence ASC LIMIT ?",
            (task_id, after_sequence, limit),
        ).fetchall(),
    )
    return [_row_to_execution_event(row) for row in rows]


def _optional_text(row: sqlite3.Row, column: str) -> str | None:
    value = cast(object, row[column])
    return None if value is None else str(value)


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError("expected integer event field")


def _row_to_execution_event(row: sqlite3.Row) -> ExecutionEventRecord:
    return {
        "sequence": _as_int(cast(object, row["sequence"])),
        "schema_version": _as_int(cast(object, row["schema_version"])),
        "task_id": str(cast(object, row["task_id"])),
        "step_id": _optional_text(row, "step_id"),
        "agent_id": _optional_text(row, "agent_id"),
        "parent_id": _optional_text(row, "parent_id"),
        "tool_call_id": _optional_text(row, "tool_call_id"),
        "approval_id": _optional_text(row, "approval_id"),
        "resource_job_id": _optional_text(row, "resource_job_id"),
        "correlation_id": _optional_text(row, "correlation_id"),
        "event_type": str(cast(object, row["event_type"])),
        "payload_json": str(cast(object, row["payload_json"])),
        "created_at": str(cast(object, row["created_at"])),
    }


__all__ = [
    "ExecutionEventRecord",
    "RUN_EVENT_SCHEMA_VERSION",
    "RunEventMetadata",
    "append_execution_event",
    "initialize_execution_event_schema",
    "list_execution_events",
]
