"""브라우저 작업 기억의 **저장 스키마와 운영 삭제** — `memory_service` 와 `browser_task_memory` 가
함께 쓰는 규칙을 한 곳에 둔다.

순환 import 를 끊는 것이 이 모듈의 존재 이유다(task 15 의 `ssak_search_trust` 와 같은 구조):

- `knowledge/memory_service.py` 는 자기 운영 경로(전체 삭제·보관 기간·비밀 소거)가 브라우저
  기억까지 덮게 하려고 `integration_purge` 가 필요하다.
- `tools/browser_task_memory.py` 는 기본 서비스를 만들려고 `MemoryService` 가 필요하다.

양쪽이 서로를 import 하면 basedpyright 가 순환을 오류로 잡는다(실제로 잡았다). 그래서 스키마
상수와 삭제 경로를 이 **잎 모듈**에 두고 양쪽이 여기를 본다 — 어느 쪽도 다른 쪽을 정적으로
가리키지 않게 된다.

이 모듈은 정책을 모른다(켜짐·꺼짐·동의). 지우는 일이 설정에 막히면 그건 삭제가 아니므로
`integration_purge` 는 **정책과 무관하게** 동작한다.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Final, Literal

from antigravity_k.engine.secret_scanner import redact_full

logger = logging.getLogger(__name__)

#: SQLite 표 이름(메모리 서비스와 **같은 DB 파일**을 쓴다 — 별도 파일을 만들지 않는다).
TABLE: Final = "browser_task_memory"

#: 색인에서 이 표의 항목을 구분하는 표 이름(임베딩 id 는 `{VECTOR_TABLE}:{row_id}` 다).
VECTOR_TABLE: Final = "browser_task_memory"

#: 표 생성 SQL. 스키마를 아는 곳은 여기 한 곳이다(`browser_task_memory` 가 초기화에 쓴다).
CREATE_TABLE_SQL: Final = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL UNIQUE,
    dedupe_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    owner TEXT NOT NULL,
    origin TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    goal TEXT NOT NULL,
    body TEXT NOT NULL,
    steps TEXT NOT NULL,
    evidence TEXT NOT NULL,
    consent TEXT NOT NULL,
    minimized TEXT NOT NULL,
    source_task TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT NOT NULL DEFAULT '',
    revoke_reason TEXT NOT NULL DEFAULT ''
)
"""


def parse_epoch(stamp: str) -> float:
    """`YYYY-MM-DDTHH:MM:SSZ` 를 epoch 초로. 못 읽는 값은 0(과거 취급 — 회수가 불리한 쪽)."""
    from datetime import datetime, timezone

    text = str(stamp or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def integration_purge(
    service: object,
    *,
    mode: Literal["expired", "all", "redact"],
    max_age_days: int | None = None,
    now: float | None = None,
) -> int:
    """메모리 서비스의 기존 운영 경로(전체 삭제·보관 기간·비밀 소거)가 **브라우저 기억도 덮게** 한다.

    `MemoryService.redact_all`/`apply_retention`/`clear_all` 이 이 함수를 부른다. 설정이 꺼져 있어도
    동작한다 — 운영자의 삭제가 기능 플래그에 막히면 그건 삭제가 아니다.
    """
    db_path = str(getattr(service, "db_path", "") or "")
    if not db_path:
        return 0
    store = getattr(service, "vector_store", None)
    drop = getattr(store, "delete_embedding", None)
    moment = time.time() if now is None else now
    changed = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT id, entry_id, body, expires_at, updated_at, revoked_at FROM {TABLE}"
            ).fetchall()
        except sqlite3.OperationalError:
            return 0  # 아직 표가 없다 = 기억을 쓴 적이 없다
        for row in rows:
            row_id = int(row["id"])
            entry_id = str(row["entry_id"])
            if mode == "redact":
                body = str(row["body"])
                redacted = redact_full(body)
                if redacted != body:
                    _ = conn.execute(f"UPDATE {TABLE} SET body = ? WHERE entry_id = ?", (redacted, entry_id))
                    changed += 1
                continue
            # `all` = 설정과 무관한 전부 삭제, `expired` = 만료됐거나 마지막 확인이 보관 기간을 넘긴 항목.
            stale = mode == "all" or parse_epoch(str(row["expires_at"])) <= moment
            if mode == "expired" and max_age_days is not None:
                age_limit = moment - max_age_days * 86400
                stale = stale or parse_epoch(str(row["updated_at"])) <= age_limit
            if stale or str(row["revoked_at"] or ""):
                _ = conn.execute(f"DELETE FROM {TABLE} WHERE entry_id = ?", (entry_id,))
                if callable(drop):
                    try:
                        _ = drop(VECTOR_TABLE, row_id)
                    except Exception:
                        logger.exception("browser task memory embedding removal failed during purge")
                changed += 1
        conn.commit()
    return changed


__all__ = [
    "CREATE_TABLE_SQL",
    "TABLE",
    "VECTOR_TABLE",
    "integration_purge",
    "parse_epoch",
]
