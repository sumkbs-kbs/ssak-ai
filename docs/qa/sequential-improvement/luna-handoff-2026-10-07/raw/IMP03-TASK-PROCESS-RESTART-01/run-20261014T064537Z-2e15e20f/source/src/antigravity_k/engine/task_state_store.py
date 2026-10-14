from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast, final

from antigravity_k.engine.task_events import (
    ExecutionEventRecord,
    RunEventMetadata,
    append_execution_event,
    initialize_execution_event_schema,
    list_execution_events,
)
from antigravity_k.engine.task_execution_context import (
    TaskExecutionContext as TaskExecutionContext,
)
from antigravity_k.engine.task_execution_context import (
    bind_task_execution_context as bind_task_execution_context,
)
from antigravity_k.engine.task_execution_context import (
    current_task_execution_context as current_task_execution_context,
)
from antigravity_k.engine.task_process_ownership import can_cancel, can_prepare_resume, owner_pid_for_status
from antigravity_k.engine.task_state_types import (
    ALLOWED_TASK_TRANSITIONS,
    TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    CancellationVerdict,
    CheckpointRecord,
    InvalidTaskStatusError,
    InvalidTaskTransitionError,
    TaskRecord,
    TaskStatusName,
    TaskTransitionConflictError,
    is_terminal_task_status,
)

# 사용자(또는 다른 프로세스)가 취소를 요청해 끝난 태스크의 오류 문구. 이전 문구("… or it was lost in
# memory")는 **살아 있는 소유자를 가리키지 않는다**는 것을 말하지 못했고, F-35 의 거짓 이력은 바로
# 그 자리에서 생겼다 — 문구가 "무슨 일이 일어났는가"를 말하도록 바꾼다.
_CANCELLED_BY_REQUEST_MESSAGE: Final[str] = "Task was cancelled by an explicit cancel request."


def _fetchone(cursor: sqlite3.Cursor) -> sqlite3.Row | None:
    return cast(sqlite3.Row | None, cursor.fetchone())


def _fetchall(cursor: sqlite3.Cursor) -> list[sqlite3.Row]:
    return cast(list[sqlite3.Row], cursor.fetchall())


def _row_value(row: sqlite3.Row, key: str) -> object:
    return cast(object, row[key])


@final
class TaskStateStore:
    """Persisted task state with status/version CAS transitions (DAT-01).

    Observation order (UI must not show contradictory terminals):
    1. ``task_history.status`` / ``version`` is authoritative for terminal outcome.
    2. A successful CAS may append ``task.status`` in the same write transaction;
       event ``sequence`` therefore never claims a terminal that lost the CAS.
    3. Projectors prefer store status over event-derived status when they differ.
    """

    def __init__(self, db_path: str) -> None:
        p = Path(db_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            test_file = p.parent / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            self.db_path = str(p)
        except OSError:
            fallback_dir = Path.home() / ".antigravity-k" / "data"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(fallback_dir / p.name)
        self.initialize()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        connection.row_factory = sqlite3.Row
        _ = cast(sqlite3.Row | None, connection.execute("PRAGMA journal_mode=WAL").fetchone())
        _ = connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS task_history ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE, "
                + "prompt TEXT NOT NULL, status TEXT NOT NULL, output TEXT, error TEXT, "
                + "created_at TEXT NOT NULL, completed_at TEXT, updated_at TEXT, owner_pid INTEGER, "
                + "owner_subject TEXT NOT NULL DEFAULT 'loopback', "
                + "version INTEGER NOT NULL DEFAULT 0)",
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS task_checkpoints ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, step INTEGER NOT NULL, "
                + "context_json TEXT NOT NULL, output_so_far TEXT NOT NULL, created_at TEXT NOT NULL)",
            )
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS task_idempotency ("
                + "idempotency_key TEXT NOT NULL, owner_subject TEXT NOT NULL DEFAULT 'loopback', "
                + "task_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, "
                + "PRIMARY KEY (idempotency_key, owner_subject))",
            )
            initialize_execution_event_schema(connection)
            columns = {
                _row_value(row, "name") for row in _fetchall(connection.execute("PRAGMA table_info(task_history)"))
            }
            if "updated_at" not in columns:
                _ = connection.execute("ALTER TABLE task_history ADD COLUMN updated_at TEXT")
                _ = connection.execute("UPDATE task_history SET updated_at = created_at WHERE updated_at IS NULL")
            if "owner_pid" not in columns:
                _ = connection.execute("ALTER TABLE task_history ADD COLUMN owner_pid INTEGER")
            if "owner_subject" not in columns:
                _ = connection.execute(
                    "ALTER TABLE task_history ADD COLUMN owner_subject TEXT NOT NULL DEFAULT 'loopback'"
                )
            if "version" not in columns:
                _ = connection.execute("ALTER TABLE task_history ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
            idempotency_info = _fetchall(connection.execute("PRAGMA table_info(task_idempotency)"))
            idempotency_columns = {_row_value(row, "name") for row in idempotency_info}
            if "owner_subject" not in idempotency_columns:
                _ = connection.execute(
                    "ALTER TABLE task_idempotency ADD COLUMN owner_subject TEXT NOT NULL DEFAULT 'loopback'",
                )
                idempotency_info = _fetchall(connection.execute("PRAGMA table_info(task_idempotency)"))
            if any(
                _row_value(row, "name") == "idempotency_key" and _row_value(row, "pk") == 1 for row in idempotency_info
            ) and not any(
                _row_value(row, "name") == "owner_subject" and _row_value(row, "pk") == 2 for row in idempotency_info
            ):
                _ = connection.execute("ALTER TABLE task_idempotency RENAME TO task_idempotency_legacy")
                _ = connection.execute(
                    "CREATE TABLE task_idempotency ("
                    "idempotency_key TEXT NOT NULL, owner_subject TEXT NOT NULL DEFAULT 'loopback', "
                    "task_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, "
                    "PRIMARY KEY (idempotency_key, owner_subject))",
                )
                _ = connection.execute(
                    "INSERT INTO task_idempotency (idempotency_key, owner_subject, task_id, created_at) "
                    "SELECT idempotency_key, owner_subject, task_id, created_at FROM task_idempotency_legacy",
                )
                _ = connection.execute("DROP TABLE task_idempotency_legacy")

    def create_task(
        self,
        task_id: str,
        prompt: str,
        status: TaskStatusName,
        created_at: str,
        idempotency_key: str | None = None,
        owner_subject: str = "loopback",
    ) -> str:
        if status not in TASK_STATUSES:
            raise InvalidTaskStatusError(status)

        normalized_owner = owner_subject.strip() or "loopback"
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                row = _fetchone(
                    connection.execute(
                        "SELECT task_id FROM task_idempotency WHERE idempotency_key = ? AND owner_subject = ?",
                        (idempotency_key, normalized_owner),
                    )
                )
                if row:
                    return str(_row_value(row, "task_id"))

            _ = connection.execute(
                "INSERT INTO task_history (task_id, prompt, status, created_at, updated_at, owner_subject, version) "
                + "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (task_id, prompt, status, created_at, created_at, normalized_owner),
            )
            if idempotency_key:
                _ = connection.execute(
                    "INSERT INTO task_idempotency (idempotency_key, owner_subject, task_id, created_at) "
                    + "VALUES (?, ?, ?, ?)",
                    (idempotency_key, normalized_owner, task_id, created_at),
                )
        return task_id

    def get_task(self, task_id: str, owner_subject: str | None = None) -> TaskRecord | None:
        # F-36: `owner_pid` 도 읽는다 — 보고 표면이 "이 행을 누가 실행 중인가"를 말하려면
        # 그 값이 조회 결과에 있어야 한다(저장 구조에는 처음부터 있었다).
        with self._connection() as connection:
            if owner_subject is None:
                row = _fetchone(
                    connection.execute(
                        "SELECT task_id, prompt, status, output, error, created_at, updated_at, completed_at, version, "
                        + "owner_pid FROM task_history WHERE task_id = ?",
                        (task_id,),
                    )
                )
            else:
                row = _fetchone(
                    connection.execute(
                        "SELECT task_id, prompt, status, output, error, created_at, updated_at, completed_at, version, "
                        + "owner_pid FROM task_history WHERE task_id = ? AND owner_subject = ?",
                        (task_id, owner_subject),
                    )
                )
        if not row:
            return None
        return self._row_to_task(row)

    def transition(
        self,
        task_id: str,
        status: TaskStatusName,
        output: str | None = None,
        error: str | None = None,
        *,
        expected_status: TaskStatusName | str | None = None,
        expected_version: int | None = None,
        record_event: bool = False,
    ) -> bool:
        """CAS transition on expected status+version.

        When ``expected_status`` / ``expected_version`` are omitted, the current
        row values are used as the CAS predicate (still conditional — not last-write-wins).
        Affected row 0 raises ``TaskTransitionConflictError``.

        Pass ``record_event=True`` to append ``task.status`` in the same write
        transaction as the CAS winner (recommended for terminal handoff paths that
        do not already emit a domain-specific completion event).
        """
        if status not in TASK_STATUSES:
            # OBS-01: 허용 전이 밖 상태 거절도 운영 metric에 기록
            from antigravity_k.engine.operational_metrics import record_task_transition_conflict

            record_task_transition_conflict("rejected")
            raise InvalidTaskStatusError(status)

        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = _fetchone(
                connection.execute(
                    "SELECT status, output, error, version FROM task_history WHERE task_id = ?",
                    (task_id,),
                )
            )
            if not row:
                return False

            current = str(_row_value(row, "status"))
            current_version = int(cast(int, _row_value(row, "version") or 0))
            current_output = cast(str | None, _row_value(row, "output"))
            current_error = cast(str | None, _row_value(row, "error"))

            cas_status = current if expected_status is None else str(expected_status)
            cas_version = current_version if expected_version is None else int(expected_version)

            if expected_status is not None and str(expected_status) != current:
                # OBS-01: stale expected CAS 충돌을 운영 metric에 기록
                from antigravity_k.engine.operational_metrics import record_task_transition_conflict

                record_task_transition_conflict("conflict")
                raise TaskTransitionConflictError(
                    task_id,
                    requested=status,
                    expected_status=str(expected_status),
                    expected_version=expected_version,
                    current_status=current,
                    current_version=current_version,
                )
            if expected_version is not None and int(expected_version) != current_version:
                from antigravity_k.engine.operational_metrics import record_task_transition_conflict as _rtc

                _rtc("conflict")
                raise TaskTransitionConflictError(
                    task_id,
                    requested=status,
                    expected_status=expected_status if expected_status is None else str(expected_status),
                    expected_version=expected_version,
                    current_status=current,
                    current_version=current_version,
                )

            # Terminal freeze: winner's reason/output cannot be overwritten.
            if is_terminal_task_status(current):
                if status == current and output is None and error is None:
                    return True
                raise InvalidTaskTransitionError(task_id, current, status)

            if current != status and status not in ALLOWED_TASK_TRANSITIONS.get(current, frozenset()):
                raise InvalidTaskTransitionError(task_id, current, status)

            next_output = output if output is not None else current_output
            next_error = error if error is not None else current_error
            updated_at = datetime.now(UTC).isoformat()
            completed_at = updated_at if status in TERMINAL_TASK_STATUSES else None
            next_version = current_version + 1

            cursor = connection.execute(
                "UPDATE task_history SET status = ?, output = ?, error = ?, updated_at = ?, completed_at = ?, "
                "owner_pid = ?, version = ? "
                "WHERE task_id = ? AND status = ? AND version = ?",
                (
                    status,
                    next_output,
                    next_error,
                    updated_at,
                    completed_at,
                    owner_pid_for_status(status),
                    next_version,
                    task_id,
                    cas_status,
                    cas_version,
                ),
            )
            if cursor.rowcount != 1:
                fresh = _fetchone(
                    connection.execute(
                        "SELECT status, version FROM task_history WHERE task_id = ?",
                        (task_id,),
                    )
                )
                # OBS-01: CAS 충돌(lost race / stale expected)을 운영 metric에 기록
                from antigravity_k.engine.operational_metrics import record_task_transition_conflict

                record_task_transition_conflict("conflict")
                raise TaskTransitionConflictError(
                    task_id,
                    requested=status,
                    expected_status=cas_status,
                    expected_version=cas_version,
                    current_status=None if fresh is None else str(_row_value(fresh, "status")),
                    current_version=None if fresh is None else int(cast(int, _row_value(fresh, "version") or 0)),
                )

            if record_event:
                payload = json.dumps(
                    {
                        "from_status": current,
                        "to_status": status,
                        "from_version": current_version,
                        "to_version": next_version,
                        "terminal": status in TERMINAL_TASK_STATUSES,
                    },
                    sort_keys=True,
                )
                _ = append_execution_event(connection, task_id, "task.status", payload)

        return True

    def prepare_resume(self, task_id: str, owner_subject: str | None = None) -> bool:
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            if owner_subject is None:
                row = _fetchone(
                    connection.execute(
                        "SELECT status, owner_pid, version FROM task_history WHERE task_id = ?",
                        (task_id,),
                    )
                )
            else:
                row = _fetchone(
                    connection.execute(
                        "SELECT status, owner_pid, version FROM task_history WHERE task_id = ? AND owner_subject = ?",
                        (task_id, owner_subject),
                    )
                )
            owner_pid_value = _row_value(row, "owner_pid") if row else None
            owner_pid = None if owner_pid_value is None else int(cast(int, owner_pid_value))
            raw_status = "" if not row else str(_row_value(row, "status"))
            current_version = 0 if not row else int(cast(int, _row_value(row, "version") or 0))
            if not row or not can_prepare_resume(raw_status, owner_pid):
                return False

            cursor = connection.execute(
                "UPDATE task_history SET status = ?, error = NULL, updated_at = ?, completed_at = NULL, "  # nosec B608
                + "owner_pid = ?, version = ? "
                + "WHERE task_id = ? AND status = ? AND owner_pid IS ? AND version = ?"
                + (" AND owner_subject = ?" if owner_subject is not None else ""),
                (
                    "resuming",
                    datetime.now(UTC).isoformat(),
                    owner_pid_for_status("resuming"),
                    current_version + 1,
                    task_id,
                    raw_status,
                    owner_pid,
                    current_version,
                )
                + ((owner_subject,) if owner_subject is not None else ()),
            )
        return cursor.rowcount == 1

    def cancel_if_permitted(
        self,
        task_id: str,
        owner_subject: str | None = None,
    ) -> CancellationVerdict:
        """**소유 규칙을 지키며** 취소한다 — 다른 살아 있는 프로세스의 실행은 건드리지 않는다.

        F-35: 이 메서드가 없던 동안 `cancel` 은 메모리에 태스크가 없으면 DB 의
        `status ∈ {pending, running}` 만 보고 `cancelled` 로 적었다. 그 결과 **다른 프로세스가
        실제로 실행 중인** 태스크의 이력이 "취소됨"이 되는데 실행은 계속됐다(취소 신호는 프로세스
        안의 event 라 닿지 않는다). `resume` 이 이미 갖고 있던 소유 규칙을 취소에도 **같은 함수로**
        적용하고, 거부를 `owned_elsewhere` 로 **이름 붙여** 돌려준다(조용한 404 가 아니다).

        `prepare_resume` 과 같은 형태의 CAS 다: 읽은 `status`·`owner_pid`·`version` 을 조건에
        넣으므로 그 사이 소유자가 상태를 바꿨다면 0행이 되어 실패한다(last-write-wins 가 아니다).
        """
        with self._connection() as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            query = "SELECT status, owner_pid, version FROM task_history WHERE task_id = ?"
            parameters: tuple[object, ...] = (task_id,)
            if owner_subject is not None:
                query += " AND owner_subject = ?"
                parameters += (owner_subject,)
            row = _fetchone(connection.execute(query, parameters))
            if not row:
                return "not_active"
            owner_pid_value = _row_value(row, "owner_pid")
            owner_pid = None if owner_pid_value is None else int(cast(int, owner_pid_value))
            raw_status = str(_row_value(row, "status"))
            current_version = int(cast(int, _row_value(row, "version") or 0))
            if raw_status not in {"pending", "running", "paused"}:
                return "not_active"
            if not can_cancel(raw_status, owner_pid):
                return "owned_elsewhere"

            # B608: 문자열 결합은 **고정 조각**뿐이고(아래 `AND owner_subject = ?`), 값은 전부
            # 바인딩 파라미터다. `prepare_resume` 이 같은 형태에 같은 표기를 쓰는 것과 맞춘다.
            cursor = connection.execute(
                "UPDATE task_history SET status = ?, error = ?, completed_at = ?, updated_at = ?, "  # nosec B608
                + "owner_pid = NULL, version = ? "
                + "WHERE task_id = ? AND status = ? AND owner_pid IS ? AND version = ?"
                + (" AND owner_subject = ?" if owner_subject is not None else ""),
                (
                    "cancelled",
                    _CANCELLED_BY_REQUEST_MESSAGE,
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                    current_version + 1,
                    task_id,
                    raw_status,
                    owner_pid,
                    current_version,
                )
                + ((owner_subject,) if owner_subject is not None else ()),
            )
        return "cancelled" if cursor.rowcount == 1 else "not_active"

    def list_tasks(self, limit: int, owner_subject: str | None = None) -> list[TaskRecord]:
        # F-36: 목록도 `owner_pid` 를 읽는다 — 화면의 복구 제안(재개 버튼)은 **목록**의 행을 보고
        # 그려지므로, 목록이 소유 사실을 말하지 않으면 그 자리가 조용해진다.
        with self._connection() as connection:
            if owner_subject is None:
                rows = _fetchall(
                    connection.execute(
                        "SELECT task_id, prompt, status, output, error, created_at, updated_at, completed_at, version, "
                        + "owner_pid FROM task_history ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    )
                )
            else:
                rows = _fetchall(
                    connection.execute(
                        "SELECT task_id, prompt, status, output, error, created_at, updated_at, completed_at, version, "
                        + "owner_pid FROM task_history WHERE owner_subject = ? ORDER BY created_at DESC LIMIT ?",
                        (owner_subject, limit),
                    )
                )
        return [self._row_to_task(row) for row in rows]

    def last_checkpoint_steps(self, task_ids: Sequence[str]) -> dict[str, int]:
        """여러 태스크의 **마지막 체크포인트 단계**를 한 번에 읽는다 — 복구 가능성의 재료다.

        F-36: 표면이 "재개할 수 있는가"를 말하려면 체크포인트 유무가 필요한데, 행마다
        `get_last_checkpoint` 를 부르면 목록 하나에 N번 질의한다. 한 문장으로 묶는다.
        없는 태스크는 결과에 **없다**(0 단계 체크포인트와 "체크포인트 없음"은 다른 사실이다).
        """
        ordered = [task_id for task_id in dict.fromkeys(task_ids) if task_id]
        if not ordered:
            return {}
        placeholders = ", ".join("?" for _ in ordered)
        with self._connection() as connection:
            rows = _fetchall(
                connection.execute(
                    "SELECT task_id, MAX(step) AS last_step FROM task_checkpoints "  # nosec B608
                    + f"WHERE task_id IN ({placeholders}) GROUP BY task_id",
                    tuple(ordered),
                )
            )
        return {str(_row_value(row, "task_id")): int(cast(int, _row_value(row, "last_step"))) for row in rows}

    def save_checkpoint(self, task_id: str, step: int, context_json: str, output: str) -> None:
        with self._connection() as connection:
            _ = connection.execute(
                "INSERT INTO task_checkpoints "
                + "(task_id, step, context_json, output_so_far, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, step, context_json, output, datetime.now(UTC).isoformat()),
            )

    def get_last_checkpoint(self, task_id: str, owner_subject: str | None = None) -> CheckpointRecord | None:
        with self._connection() as connection:
            query = (
                "SELECT c.task_id, c.step, c.context_json, c.output_so_far, c.created_at "
                + "FROM task_checkpoints c JOIN task_history t ON t.task_id = c.task_id "
                + "WHERE c.task_id = ?"
            )
            params: tuple[str, ...] = (task_id,)
            if owner_subject is not None:
                query += " AND t.owner_subject = ?"
                params += (owner_subject,)
            query += " ORDER BY c.step DESC LIMIT 1"
            row = _fetchone(connection.execute(query, params))
        if not row:
            return None
        return {
            "task_id": str(_row_value(row, "task_id")),
            "step": int(cast(int, _row_value(row, "step"))),
            "context_json": str(_row_value(row, "context_json")),
            "output_so_far": str(_row_value(row, "output_so_far")),
            "created_at": str(_row_value(row, "created_at")),
        }

    def append_execution_event(
        self,
        task_id: str,
        event_type: str,
        payload_json: str,
        metadata: RunEventMetadata | None = None,
    ) -> int:
        with self._connection() as connection:
            return append_execution_event(
                connection,
                task_id,
                event_type,
                payload_json,
                metadata,
            )

    def list_execution_events(
        self,
        task_id: str,
        after_sequence: int = 0,
        limit: int = 1_000,
        owner_subject: str | None = None,
    ) -> list[ExecutionEventRecord]:
        if owner_subject is not None and self.get_task(task_id, owner_subject) is None:
            return []
        with self._connection() as connection:
            return list_execution_events(connection, task_id, after_sequence, limit)

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        version_raw = _row_value(row, "version") if "version" in row.keys() else 0
        owner_pid_raw = _row_value(row, "owner_pid") if "owner_pid" in row.keys() else None
        return {
            "task_id": str(_row_value(row, "task_id")),
            "prompt": str(_row_value(row, "prompt")),
            "status": str(_row_value(row, "status")),
            "output": str(_row_value(row, "output") or ""),
            "error": cast(str | None, _row_value(row, "error")),
            "created_at": str(_row_value(row, "created_at")),
            "updated_at": str(_row_value(row, "updated_at") or _row_value(row, "created_at")),
            "completed_at": cast(str | None, _row_value(row, "completed_at")),
            "version": int(cast(int, version_raw or 0)),
            "owner_pid": None if owner_pid_raw is None else int(cast(int, owner_pid_raw)),
        }
