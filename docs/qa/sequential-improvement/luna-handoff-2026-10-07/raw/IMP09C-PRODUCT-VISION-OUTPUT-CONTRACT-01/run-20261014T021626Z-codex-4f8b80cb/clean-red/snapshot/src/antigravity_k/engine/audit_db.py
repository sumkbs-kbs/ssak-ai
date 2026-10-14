"""AuditDb — SQLite 기반 감사 이벤트 영구 적재.

=============================================
Sidabari의 audit_log.rs 패턴을 Python SQLite로 이식.

기존 OCSF JSONL 감사 로그(audit_logger.py)와 듀얼 싱크하여
데이터 손실을 방지하면서 쿼리 가능한 영구 저장소를 제공합니다.

위치: vault_data/audit.sqlite3

보안 (Sidabari CLAUDE.md §1.2.7):
  - DB 파일 권한 0600 (Unix)
  - tool_input/tool_result에 사용자 명령·로그 본문이 포함될 수 있어 외부 노출 금지
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import platform
import sqlite3
import stat
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TypeAlias, cast

logger = logging.getLogger("antigravity_k.engine.audit_db")

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hook_events (

    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms           INTEGER NOT NULL,
    panel_id        TEXT,
    kind            TEXT NOT NULL,
    hook_event_name TEXT,
    tool_name       TEXT,
    payload_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hook_events_ts ON hook_events(ts_ms);
CREATE INDEX IF NOT EXISTS idx_hook_events_panel ON hook_events(panel_id);
CREATE INDEX IF NOT EXISTS idx_hook_events_kind ON hook_events(kind);
CREATE INDEX IF NOT EXISTS idx_hook_events_tool ON hook_events(tool_name);
"""


class AuditDb:
    """SQLite 기반 감사 이벤트 영구 적재.

    Sidabari audit_log.rs의 Python 이식.
    """

    def __init__(self, db_path: str | None = None):
        """Initialize the AuditDb.

        Args:
            db_path (str | None): str | None db path.

        """
        self._db_path: Path | None = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None
        self._lock: threading.Lock = threading.Lock()
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def init(self, vault_data_dir: str | None = None) -> "AuditDb":
        """DB를 초기화합니다."""
        if self._initialized:
            return self

        if vault_data_dir:
            db_dir = Path(vault_data_dir)
        elif self._db_path:
            db_dir = self._db_path.parent
        else:
            try:
                from antigravity_k.config import config

                db_dir = config.paths.data_dir / "vault_data"
            except Exception:
                project_root = Path(__file__).resolve().parent.parent.parent.parent
                db_dir = project_root / "vault_data"

        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            test_file = db_dir / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
        except OSError:
            db_dir = Path.home() / ".antigravity-k" / "vault_data"
            db_dir.mkdir(parents=True, exist_ok=True)

        self._db_path = db_dir / "audit.sqlite3"

        try:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            _ = self._conn.executescript(SCHEMA_SQL)
            _ = self._conn.execute("PRAGMA journal_mode=WAL")
            _ = self._conn.execute("PRAGMA synchronous=NORMAL")
        except Exception as e:
            logger.error("[AuditDb] DB 초기화 실패: %s", e)
            raise

        # Unix 파일 권한 0600
        if platform.system() != "Windows":
            try:
                os.chmod(self._db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError as e:
                logger.warning("[AuditDb] 파일 권한 설정 실패: %s", e)

        self._initialized = True
        logger.info("[AuditDb] Initialized at %s", self._db_path)
        return self

    def close(self):
        """DB 연결을 닫습니다."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                logger.exception("Unhandled exception")
            self._conn = None
        self._initialized = False

    def __del__(self):
        self.close()

    def insert(
        self,
        panel_id: str | None,
        kind: str,
        hook_event_name: str | None,
        tool_name: str | None,
        payload_json: str,
    ) -> None:
        """이벤트를 DB에 삽입합니다.

        실패해도 흐름 차단 X — stderr 로그만 남깁니다.
        (Sidabari audit_log.rs insert 패턴)
        """
        if not self._conn:
            return

        ts_ms = int(time.time() * 1000)

        try:
            with self._lock:
                _ = self._conn.execute(
                    "INSERT INTO hook_events (ts_ms, panel_id, kind, hook_event_name, tool_name, payload_json) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts_ms, panel_id, kind, hook_event_name, tool_name, payload_json),
                )
                self._conn.commit()
        except Exception:
            logger.exception("[AuditDb] insert 실패")

    def insert_from_dict(self, event_dict: dict[str, object]) -> None:
        """딕셔너리 형태의 이벤트를 삽입합니다."""
        meta_raw = event_dict.get("_antigravity")
        meta = cast(Mapping[str, object], meta_raw) if isinstance(meta_raw, Mapping) else cast(dict[str, object], {})
        panel_id = _optional_string(meta.get("panel_id"))
        kind = str(event_dict.get("event") or event_dict.get("hook_event_name") or "unknown")
        hook_event_name = _optional_string(event_dict.get("hook_event_name"))
        tool_name = _optional_string(event_dict.get("tool_name"))

        payload_json = json.dumps(event_dict, ensure_ascii=False, default=str)
        self.insert(panel_id, kind, hook_event_name, tool_name, payload_json)

    # ── 조회 API ──

    def query_recent(
        self,
        limit: int = 100,
        kind: str | None = None,
        panel_id: str | None = None,
        since_ms: int | None = None,
    ) -> list[dict[str, object]]:
        """최근 이벤트를 조회합니다."""
        if not self._conn:
            return []

        conditions: list[str] = []
        params: list[object] = []

        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if panel_id:
            conditions.append("panel_id = ?")
            params.append(panel_id)
        if since_ms:
            conditions.append("ts_ms >= ?")
            params.append(since_ms)

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        query = (
            f"SELECT id, ts_ms, panel_id, kind, hook_event_name, tool_name, payload_json "  # nosec B608
            f"FROM hook_events{where} ORDER BY ts_ms DESC LIMIT ?"
        )
        params.append(limit)

        try:
            with self._lock:
                cursor = self._conn.execute(query, params)
                rows = cast(list[tuple[object, ...]], cursor.fetchall())
        except Exception:
            logger.exception("[AuditDb] query 실패")
            return []

        return [
            {
                "id": row[0],
                "ts_ms": row[1],
                "panel_id": row[2],
                "kind": row[3],
                "hook_event_name": row[4],
                "tool_name": row[5],
                "payload": _loads_payload(row[6]),
            }
            for row in rows
        ]

    def query_tool_stats(self, since_ms: int | None = None) -> list[dict[str, object]]:
        """도구별 호출 통계를 조회합니다."""
        if not self._conn:
            return []

        where = ""
        params: list[object] = []
        if since_ms:
            where = " WHERE ts_ms >= ? AND tool_name IS NOT NULL"
            params.append(since_ms)
        else:
            where = " WHERE tool_name IS NOT NULL"

        query = (
            f"SELECT tool_name, COUNT(*) as cnt, MIN(ts_ms) as first_ts, MAX(ts_ms) as last_ts "  # nosec B608
            f"FROM hook_events{where} "
            f"GROUP BY tool_name ORDER BY cnt DESC"
        )

        try:
            with self._lock:
                cursor = self._conn.execute(query, params)
                rows = cast(list[tuple[object, ...]], cursor.fetchall())
        except Exception:
            logger.exception("[AuditDb] tool_stats query 실패")
            return []

        return [
            {
                "tool_name": row[0],
                "count": row[1],
                "first_ts": row[2],
                "last_ts": row[3],
            }
            for row in rows
        ]

    def count_events(self, since_ms: int | None = None) -> int:
        """총 이벤트 수를 반환합니다."""
        if not self._conn:
            return 0

        try:
            with self._lock:
                if since_ms:
                    cursor = self._conn.execute(
                        "SELECT COUNT(*) FROM hook_events WHERE ts_ms >= ?",
                        (since_ms,),
                    )
                else:
                    cursor = self._conn.execute("SELECT COUNT(*) FROM hook_events")
                row = cast(tuple[object, ...] | None, cursor.fetchone())
                if not row:
                    return 0
                value = row[0]
                return int(value) if isinstance(value, (int, float, str)) else 0
        except Exception:
            logger.exception("[AuditDb] count 실패")
            return 0


# ── 글로벌 싱글톤 ──

_global_audit_db: AuditDb | None = None
_global_lock = threading.Lock()


def get_audit_db() -> AuditDb:
    """글로벌 AuditDb 인스턴스를 반환합니다."""
    global _global_audit_db
    if _global_audit_db is None:
        with _global_lock:
            if _global_audit_db is None:
                _global_audit_db = AuditDb()
    return _global_audit_db


def init_audit_db(vault_data_dir: str | None = None) -> AuditDb:
    """글로벌 AuditDb를 초기화합니다."""
    db = get_audit_db()
    _ = db.init(vault_data_dir)
    return db


def _close_global_audit_db():
    """프로세스 종료 시 전역 AuditDb의 DB 연결을 정리합니다."""
    global _global_audit_db
    if _global_audit_db is not None:
        try:
            _global_audit_db.close()
        except Exception:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        _global_audit_db = None


_ = atexit.register(_close_global_audit_db)


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _loads_payload(value: object) -> object:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return cast(JsonValue, json.loads(value))
    except (TypeError, ValueError):
        return {}
