from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, override

from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    ReservationId,
    UnslothReservation,
    UnslothReservationState,
    UnslothResourceOperation,
)

_CREATE_TABLE_SQL: Final = (
    "CREATE TABLE IF NOT EXISTS unsloth_resource_reservations ("
    "reservation_id TEXT PRIMARY KEY,"
    "idempotency_key TEXT NOT NULL UNIQUE,"
    "request_fingerprint TEXT NOT NULL,"
    "operation TEXT NOT NULL,"
    "device_id TEXT NOT NULL,"
    "estimated_peak_bytes INTEGER NOT NULL,"
    "provenance_fingerprint TEXT NOT NULL,"
    "resource_job_id TEXT,"
    "state TEXT NOT NULL,"
    "created_at TEXT NOT NULL,"
    "released_at TEXT)"
)
_INSERT_SQL: Final = (
    "INSERT INTO unsloth_resource_reservations ("
    "reservation_id,idempotency_key,request_fingerprint,operation,device_id,"
    "estimated_peak_bytes,provenance_fingerprint,resource_job_id,state,created_at,released_at"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)"
)
_RELEASE_SQL: Final = (
    "UPDATE unsloth_resource_reservations SET state = ?, "
    "released_at = COALESCE(released_at, ?) WHERE reservation_id = ? RETURNING *"
)
_BIND_JOB_SQL: Final = (
    "UPDATE unsloth_resource_reservations SET resource_job_id = COALESCE(resource_job_id, ?) "
    "WHERE reservation_id = ? AND state = ? AND (resource_job_id IS NULL OR resource_job_id = ?) RETURNING *"
)


@dataclass(slots=True)
class RepositoryRowError(RuntimeError):
    column: str
    expected: str

    @override
    def __str__(self) -> str:
        return f"Expected {self.expected} in SQLite column {self.column}."


type SQLiteValue = str | int | float | bytes | None


class SQLiteValueRow(Protocol):
    def __getitem__(self, column: str | int, /) -> SQLiteValue: ...


class SQLiteCursor(Protocol):
    def fetchone(self) -> SQLiteValueRow | None: ...


def _text(row: SQLiteValueRow, column: str | int) -> str:
    match row[column]:
        case str() as value:
            return value
        case None | int() | float() | bytes():
            pass
    raise RepositoryRowError(str(column), "text")


def _integer(row: SQLiteValueRow, column: str | int) -> int:
    match row[column]:
        case int() as value:
            return value
        case None | str() | float() | bytes():
            pass
    raise RepositoryRowError(str(column), "integer")


def _optional_text(row: SQLiteValueRow, column: str) -> str | None:
    match row[column]:
        case str() as value:
            return value
        case None:
            return None
        case int() | float() | bytes():
            pass
    raise RepositoryRowError(column, "nullable text")


def _typed_fetchone(cursor: SQLiteCursor) -> SQLiteValueRow | None:
    return cursor.fetchone()


@dataclass(frozen=True, slots=True)
class StoredAdmission:
    reservation_id: ReservationId
    request_fingerprint: str
    provenance_fingerprint: str
    resource_job_id: str | None
    state: UnslothReservationState


@dataclass(frozen=True, slots=True)
class PendingReservation:
    reservation_id: ReservationId
    idempotency_key: str
    request_fingerprint: str
    operation: UnslothResourceOperation
    device_id: str
    estimated_peak_bytes: int
    provenance_fingerprint: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ExistingAdmission:
    stored: StoredAdmission


@dataclass(frozen=True, slots=True)
class DeviceOccupancy:
    active_count: int


AdmissionInspection = ExistingAdmission | DeviceOccupancy


@dataclass(frozen=True, slots=True)
class AdmissionTransaction:
    connection: sqlite3.Connection

    def inspect(self, idempotency_key: str, device_id: str) -> AdmissionInspection:
        idempotency_row = _typed_fetchone(
            self.connection.execute(
                "SELECT * FROM unsloth_resource_reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            ),
        )
        match idempotency_row:
            case None:
                pass
            case row:
                return ExistingAdmission(
                    stored=StoredAdmission(
                        reservation_id=ReservationId(_text(row, "reservation_id")),
                        request_fingerprint=_text(row, "request_fingerprint"),
                        provenance_fingerprint=_text(row, "provenance_fingerprint"),
                        resource_job_id=_optional_text(row, "resource_job_id"),
                        state=UnslothReservationState(_text(row, "state")),
                    ),
                )
        occupancy_row = _typed_fetchone(
            self.connection.execute(
                "SELECT COUNT(*) FROM unsloth_resource_reservations WHERE device_id = ? AND state = ?",
                (device_id, UnslothReservationState.ACTIVE.value),
            ),
        )
        match occupancy_row:
            case None:
                pass
            case row:
                return DeviceOccupancy(active_count=_integer(row, 0))
        raise RepositoryRowError("active count", "SQLite row")

    def insert(self, pending: PendingReservation) -> None:
        _ = self.connection.execute(
            _INSERT_SQL,
            (
                pending.reservation_id,
                pending.idempotency_key,
                pending.request_fingerprint,
                pending.operation.value,
                pending.device_id,
                pending.estimated_peak_bytes,
                pending.provenance_fingerprint,
                UnslothReservationState.ACTIVE.value,
                pending.created_at,
            ),
        )


class UnslothResourceRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path: Path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def admission(self) -> Generator[AdmissionTransaction, None, None]:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            yield AdmissionTransaction(connection)

    def list_active(self) -> tuple[UnslothReservation, ...]:
        with self._connection() as connection:
            cursor = connection.execute(
                "SELECT * FROM unsloth_resource_reservations WHERE state = ? ORDER BY created_at",
                (UnslothReservationState.ACTIVE.value,),
            )
            reservations: list[UnslothReservation] = []
            while True:
                match _typed_fetchone(cursor):
                    case None:
                        return tuple(reservations)
                    case row:
                        reservations.append(self._row_to_reservation(row))

    def release(self, reservation_id: ReservationId, released_at: str) -> UnslothReservation | None:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            released_row = _typed_fetchone(
                connection.execute(
                    _RELEASE_SQL,
                    (UnslothReservationState.RELEASED.value, released_at, reservation_id),
                ),
            )
            match released_row:
                case None:
                    return None
                case row:
                    return self._row_to_reservation(row)

    def bind_job(self, reservation_id: ReservationId, resource_job_id: str) -> UnslothReservation | None:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            bound_row = _typed_fetchone(
                connection.execute(
                    _BIND_JOB_SQL,
                    (
                        resource_job_id,
                        reservation_id,
                        UnslothReservationState.ACTIVE.value,
                        resource_job_id,
                    ),
                ),
            )
            match bound_row:
                case None:
                    return None
                case row:
                    return self._row_to_reservation(row)

    @staticmethod
    def _row_to_reservation(row: SQLiteValueRow) -> UnslothReservation:
        return UnslothReservation(
            reservation_id=_text(row, "reservation_id"),
            operation=UnslothResourceOperation(_text(row, "operation")),
            device_id=_text(row, "device_id"),
            estimated_peak_bytes=_integer(row, "estimated_peak_bytes"),
            provenance_fingerprint=_text(row, "provenance_fingerprint"),
            resource_job_id=_optional_text(row, "resource_job_id"),
            state=UnslothReservationState(_text(row, "state")),
            created_at=_text(row, "created_at"),
            released_at=_optional_text(row, "released_at"),
        )

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        _ = connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.execute("PRAGMA journal_mode = WAL")
            _ = connection.execute(_CREATE_TABLE_SQL)
            rows: list[SQLiteValueRow] = connection.execute(
                "PRAGMA table_info(unsloth_resource_reservations)"
            ).fetchall()
            columns = {_text(row, 1) for row in rows}
            if "resource_job_id" not in columns:
                _ = connection.execute("ALTER TABLE unsloth_resource_reservations ADD COLUMN resource_job_id TEXT")
