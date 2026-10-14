from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)


class KanbanBoard:
    """
    작업(Task)의 상태를 관리하는 Kanban 보드입니다.
    SQLite를 영구 저장소로 사용하여 시스템 재시작 시에도 복구되도록 합니다.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            configured_path = os.environ.get("AGK_KANBAN_DB_PATH", "").strip()
            if configured_path:
                db_path = configured_path
            else:
                try:
                    from antigravity_k.config import config

                    base_dir = config.paths.data_dir
                    base_dir.mkdir(parents=True, exist_ok=True)
                    test_file = base_dir / f".agk_write_test_{os.getpid()}"
                    test_file.touch()
                    test_file.unlink()
                except OSError:
                    base_dir = Path.home() / ".antigravity-k" / "data"
                    base_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(base_dir / "kanban.db")

        self.db_path: str = db_path
        self._lock: threading.Lock = threading.Lock()
        self._init_db()
        self._next_id: int = self._get_next_id()

    def _get_connection(self) -> sqlite3.Connection:
        # 멀티스레드 접근을 위해 check_same_thread=False
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL 모드로 동시성 성능 향상
        _ = conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """테이블을 생성합니다."""
        with self._lock:
            with self._get_connection() as conn:
                _ = conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        description TEXT,
                        status TEXT,
                        assignee TEXT,
                        tokens_used INTEGER DEFAULT 0,
                        worktree_branch TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                """
                )
                table_info_rows = cast(
                    list[sqlite3.Row],
                    conn.execute("PRAGMA table_info(tasks)").fetchall(),
                )
                columns = {str(cast(object, row[1])) for row in table_info_rows}
                if "worktree_branch" not in columns:
                    try:
                        _ = conn.execute("ALTER TABLE tasks ADD COLUMN worktree_branch TEXT")
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
                _ = conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        old_status TEXT,
                        new_status TEXT,
                        changed_at TEXT,
                        FOREIGN KEY(task_id) REFERENCES tasks(id)
                    )
                """
                )
                conn.commit()

    def _get_next_id(self) -> int:
        """가장 마지막 Task ID를 기반으로 다음 ID를 가져옵니다."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT id FROM tasks ORDER BY created_at DESC LIMIT 1")
                row = cast(sqlite3.Row | None, cur.fetchone())
                if row:
                    # 'TASK-X' 형식에서 숫자 추출
                    try:
                        return int(str(cast(object, row["id"])).split("-")[1]) + 1
                    except (IndexError, TypeError, ValueError):
                        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
                return 1

    def create_task(self, description: str, assignee: str | None = None) -> str:
        """새로운 태스크를 생성하고 DB에 저장합니다."""
        with self._lock:
            task_id = f"TASK-{self._next_id}"
            self._next_id += 1
            now = datetime.now().isoformat()

            with self._get_connection() as conn:
                _ = conn.execute(
                    "INSERT INTO tasks (id, description, status, assignee, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",  # noqa: E501
                    (task_id, description, "TODO", assignee, now, now),
                )
                conn.commit()

            logger.info("Task created: %s", task_id)
            return task_id

    def update_task_worktree(self, task_id: str, branch_name: str) -> None:
        """태스크에 할당된 워크트리 브랜치를 업데이트합니다."""
        with self._lock:
            with self._get_connection() as conn:
                _ = conn.execute(
                    "UPDATE tasks SET worktree_branch = ?, updated_at = ? WHERE id = ?",
                    (branch_name, datetime.now().isoformat(), task_id),
                )
                conn.commit()
            logger.info("Task %s worktree updated to %s", task_id, branch_name)

    def move_task(self, task_id: str, new_status: str, verification_note: str | None = None) -> None:
        """태스크 상태를 업데이트하고 히스토리를 남깁니다."""
        valid_statuses = {"TODO", "IN_PROGRESS", "REVIEW", "DONE", "BACKLOG"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status: {new_status}")

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
                row = cast(sqlite3.Row | None, cur.fetchone())
                if not row:
                    raise KeyError(f"Task not found: {task_id}")

                old_status = str(cast(object, row["status"]))

                # Verification Gate (REVIEW -> DONE)
                if old_status == "REVIEW" and new_status == "DONE":
                    if not verification_note or not verification_note.strip():
                        raise ValueError(
                            "Transition from REVIEW to DONE requires a verification_note (e.g., test logs, QA approval)."  # noqa: E501
                        )

                if old_status != new_status:
                    now = datetime.now().isoformat()
                    _ = conn.execute(
                        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                        (new_status, now, task_id),
                    )

                    # Store verification_note in changed_at or another column if we needed, but for now we append it to history's new_status or just enforce the gate.  # noqa: E501
                    history_status = new_status
                    if verification_note:
                        history_status = f"{new_status} (Note: {verification_note})"

                    _ = conn.execute(
                        "INSERT INTO task_history (task_id, old_status, new_status, changed_at) VALUES (?, ?, ?, ?)",
                        (task_id, old_status, history_status, now),
                    )
                    conn.commit()
                    logger.info("Task %s moved from %s to %s", task_id, old_status, new_status)

    def assign_task(self, task_id: str, assignee: str) -> None:
        """태스크를 에이전트에게 할당합니다. TODO 상태면 IN_PROGRESS로 이동합니다."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
                row = cast(sqlite3.Row | None, cur.fetchone())
                if not row:
                    logger.warning("Task %s not found for assignment.", task_id)
                    return

                now = datetime.now().isoformat()
                _ = conn.execute(
                    "UPDATE tasks SET assignee = ?, updated_at = ? WHERE id = ?",
                    (assignee, now, task_id),
                )
                conn.commit()
                logger.info("Task %s assigned to %s", task_id, assignee)

        # 락 밖에서 move_task 호출 (데드락 방지)
        with self._get_connection() as conn:
            cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            row = cast(sqlite3.Row | None, cur.fetchone())
            if row and str(cast(object, row["status"])) in ["TODO", "BACKLOG"]:
                self.move_task(task_id, "IN_PROGRESS")

    def add_tokens(self, task_id: str, tokens: int) -> None:
        """태스크 수행 중 발생한 토큰 사용량을 추가합니다."""
        with self._lock:
            with self._get_connection() as conn:
                _ = conn.execute(
                    "UPDATE tasks SET tokens_used = tokens_used + ?, updated_at = ? WHERE id = ?",
                    (tokens, datetime.now().isoformat(), task_id),
                )
                conn.commit()

    def pull_task(self, assignee: str) -> str | None:
        """
        에이전트가 처리할 수 있는 할당되지 않은 TODO 태스크를 자율적으로 가져옵니다 (Pull 방식).
        """
        with self._lock:
            with self._get_connection() as conn:
                # 할당되지 않은 TODO 작업을 오래된 순으로 하나 가져옴
                cur = conn.execute(
                    "SELECT id FROM tasks WHERE status = 'TODO' AND (assignee IS NULL OR assignee = '') ORDER BY created_at ASC LIMIT 1"  # noqa: E501
                )
                row = cast(sqlite3.Row | None, cur.fetchone())
                if row:
                    task_id = str(cast(object, row["id"]))
                    now = datetime.now().isoformat()
                    # 태스크를 가져오면서 바로 IN_PROGRESS로 상태 변경
                    _ = conn.execute(
                        "UPDATE tasks SET assignee = ?, status = 'IN_PROGRESS', updated_at = ? WHERE id = ?",
                        (assignee, now, task_id),
                    )
                    _ = conn.execute(
                        "INSERT INTO task_history (task_id, old_status, new_status, changed_at) VALUES (?, 'TODO', 'IN_PROGRESS', ?)",  # noqa: E501
                        (task_id, now),
                    )
                    conn.commit()
                    logger.info("Agent %s pulled task %s", assignee, task_id)
                    return task_id
        return None

    def get_board_state(self) -> dict[str, list[dict[str, object]]]:
        """전체 칸반 보드 상태를 UI 렌더링에 적합한 형태로 반환합니다."""
        columns: dict[str, list[dict[str, object]]] = {
            "BACKLOG": [],
            "TODO": [],
            "IN_PROGRESS": [],
            "REVIEW": [],
            "DONE": [],
        }

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC")
                rows = cast(list[sqlite3.Row], cur.fetchall())
                for row in rows:
                    task_dict: dict[str, object] = {key: cast(object, row[key]) for key in row.keys()}
                    status = str(task_dict["status"])
                    if status not in columns:
                        columns[status] = []
                    columns[status].append(task_dict)

        return columns
