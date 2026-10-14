"""Durable action claim projection across dispatcher and process lifetimes.

Claims are operational admission state, not a replacement for the canonical sink.
A claim is never automatically released: a crash cannot prove that no effect ran.
The journal is a rebuildable index: pending lookup and receipt links are projections
over durable claim rows; canonical action/receipt bytes live in the record sink.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from antigravity_k.engine.cognitive.models import Record

CLAIMED = "claimed"
PENDING = "pending"
SETTLED = "settled"


@dataclass(frozen=True, slots=True)
class ActionClaimView:
    """Readable projection of one durable claim row."""

    project_id: str
    action_key: str
    intent_json: str
    action_record_id: str
    status: str
    receipt_id: str | None
    updated_at: str
    observation_digest: str | None = None
    observation_record_id: str | None = None
    projection_revision: int = 0
    pending_reason: str = ""


@dataclass(frozen=True, slots=True)
class ObservationPublication:
    """Canonical identities to publish after the append succeeds."""

    digest: str
    observation_record_id: str
    receipt_id: str
    status: str


class ActionJournal(Protocol):
    """Atomically persist intent and expose pending/receipt recovery projections."""

    def claim(self, project_id: str, action_key: str, intent: Record) -> bool: ...

    def attach_receipt(
        self,
        project_id: str,
        action_key: str,
        receipt_id: str,
        *,
        status: str = PENDING,
    ) -> None: ...

    def attach_observation(
        self,
        expected: ActionClaimView,
        publication: ObservationPublication,
        append_records: Callable[[], None],
    ) -> bool: ...

    def get(self, project_id: str, action_key: str) -> ActionClaimView | None: ...

    def list_pending(self, project_id: str) -> tuple[ActionClaimView, ...]: ...


@dataclass(frozen=True, slots=True)
class SqliteActionJournal:
    """SQLite unique claims are serialized and committed before the effect boundary."""

    path: Path

    def claim(self, project_id: str, action_key: str, intent: Record) -> bool:
        """Return False for an existing claim; database errors propagate before dispatch."""
        now = datetime.now(UTC).isoformat()
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                self._ensure_schema(connection)
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO action_claims "
                    "(project_id, action_key, intent, action_record_id, status, receipt_id, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                    (project_id, action_key, intent.model_dump_json(), intent.id, CLAIMED, now),
                )
                return inserted.rowcount == 1

    def attach_receipt(
        self,
        project_id: str,
        action_key: str,
        receipt_id: str,
        *,
        status: str = PENDING,
    ) -> None:
        """Link the durable receipt ID onto an existing claim (fail closed if missing)."""
        now = datetime.now(UTC).isoformat()
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                self._ensure_schema(connection)
                updated = connection.execute(
                    "UPDATE action_claims SET receipt_id = ?, status = ?, updated_at = ? "
                    "WHERE project_id = ? AND action_key = ? AND projection_revision = 0",
                    (receipt_id, status, now, project_id, action_key),
                )
                if updated.rowcount != 1:
                    raise LookupError(
                        f"action claim missing or observation already published: {project_id}/{action_key}"
                    )

    def attach_observation(
        self,
        expected: ActionClaimView,
        publication: ObservationPublication,
        append_records: Callable[[], None],
    ) -> bool:
        """Serialize publication; canonical append precedes authoritative projection.

        A failed append or process exit rolls back this transaction. Canonical rows
        may already exist; the caller reuses their stable IDs on the next attempt.
        """
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                self._ensure_schema(connection)
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT receipt_id, projection_revision, status FROM action_claims "
                    "WHERE project_id = ? AND action_key = ?",
                    (expected.project_id, expected.action_key),
                ).fetchone()
                if row != (expected.receipt_id, expected.projection_revision, expected.status):
                    return False
                if expected.status == SETTLED:
                    return False
                append_records()
                connection.execute(
                    "UPDATE action_claims SET receipt_id = ?, status = ?, updated_at = ?, "
                    "observation_digest = ?, observation_record_id = ?, projection_revision = ? "
                    "WHERE project_id = ? AND action_key = ?",
                    (
                        publication.receipt_id,
                        publication.status,
                        datetime.now(UTC).isoformat(),
                        publication.digest,
                        publication.observation_record_id,
                        expected.projection_revision + 1,
                        expected.project_id,
                        expected.action_key,
                    ),
                )
                return True

    def get(self, project_id: str, action_key: str) -> ActionClaimView | None:
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT project_id, action_key, intent, action_record_id, status, receipt_id, updated_at, observation_digest, observation_record_id, projection_revision "
                "FROM action_claims WHERE project_id = ? AND action_key = ?",
                (project_id, action_key),
            ).fetchone()
        return None if row is None else self._row_to_view(row)

    def list_pending(self, project_id: str) -> tuple[ActionClaimView, ...]:
        """Claims that still need observation/reconcile after restart."""
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                "SELECT project_id, action_key, intent, action_record_id, status, receipt_id, updated_at, observation_digest, observation_record_id, projection_revision "
                "FROM action_claims WHERE project_id = ? AND status IN (?, ?) "
                "ORDER BY updated_at ASC, action_key ASC",
                (project_id, CLAIMED, PENDING),
            ).fetchall()
        return tuple(self._row_to_view(row) for row in rows)

    @staticmethod
    def _row_to_view(row: tuple[object, ...]) -> ActionClaimView:
        status = str(row[4] or CLAIMED)
        receipt_id = None if row[5] is None else str(row[5])
        reason = "awaiting_observation"
        if status == SETTLED:
            reason = "settled"
        elif status == CLAIMED and receipt_id is None:
            reason = "claimed_awaiting_receipt"
        elif status == PENDING:
            reason = "pending_observation_after_effect"
        return ActionClaimView(
            project_id=str(row[0]),
            action_key=str(row[1]),
            intent_json=str(row[2]),
            action_record_id=str(row[3] or ""),
            status=status,
            receipt_id=receipt_id,
            updated_at=str(row[6] or ""),
            observation_digest=None if len(row) < 8 or row[7] is None else str(row[7]),
            observation_record_id=None if len(row) < 9 or row[8] is None else str(row[8]),
            projection_revision=int(str(row[9] or 0)) if len(row) > 9 else 0,
            pending_reason=reason,
        )

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        # DDL does not implicitly start a sqlite3 transaction. Serialize schema
        # inspection and migration so competing processes never act on stale columns.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS action_claims ("
                "project_id TEXT NOT NULL, "
                "action_key TEXT NOT NULL, "
                "intent TEXT NOT NULL, "
                "action_record_id TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL DEFAULT 'claimed', "
                "receipt_id TEXT, "
                "updated_at TEXT NOT NULL DEFAULT '', "
                "PRIMARY KEY(project_id, action_key))"
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(action_claims)")}
            migrations = (
                ("action_record_id", "TEXT NOT NULL DEFAULT ''"),
                ("status", "TEXT NOT NULL DEFAULT 'claimed'"),
                ("receipt_id", "TEXT"),
                ("updated_at", "TEXT NOT NULL DEFAULT ''"),
                ("observation_digest", "TEXT"),
                ("observation_record_id", "TEXT"),
                ("projection_revision", "INTEGER NOT NULL DEFAULT 0"),
            )
            for name, decl in migrations:
                if name not in columns:
                    connection.execute(f"ALTER TABLE action_claims ADD COLUMN {name} {decl}")


__all__ = [
    "CLAIMED",
    "PENDING",
    "SETTLED",
    "ActionClaimView",
    "ActionJournal",
    "SqliteActionJournal",
]
