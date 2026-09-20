"""Memory Service module."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, TypedDict, cast, final


class _RowLike(Protocol):
    def keys(self) -> list[str]: ...

    def __getitem__(self, key: str | int) -> object: ...


class _CursorLike(Protocol):
    lastrowid: int | None

    def fetchone(self) -> _RowLike | None: ...

    def fetchall(self) -> list[_RowLike]: ...


def _cursor(value: object) -> _CursorLike:
    return cast(_CursorLike, value)


def _row(value: object) -> _RowLike:
    return cast(_RowLike, value)


def _row_dict(value: object) -> dict[str, object]:
    row = _row(value)
    return {key: row[key] for key in row.keys()}


def _row_value(value: object, key: str | int) -> object:
    return _row(value)[key]


def _fetchall(value: object) -> list[_RowLike]:
    return _cursor(value).fetchall()


def _fetchone(value: object) -> _RowLike | None:
    return _cursor(value).fetchone()


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _number(value: object, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


class _VectorStoreLike(Protocol):
    def store_embedding(self, source_table: str, source_id: int, text: str) -> bool: ...

    def search_similar(self, query: str, source_table: str, top_k: int = 10) -> list[dict[str, object]]: ...

    def fit_tfidf(self, documents: list[str]) -> None: ...

    def get_stats(self) -> dict[str, object]: ...

    def clear(self) -> int: ...


class StatsPayload(TypedDict):
    knowledge_items: int
    context_snapshots: int
    db_path: str
    vector_store: dict[str, object]


logger = logging.getLogger(__name__)


def _browser_memory_purge(
    service: MemoryService,
    *,
    mode: str,
    max_age_days: int | None = None,
) -> int:
    """브라우저 작업 기억(task 21)도 같은 운영 경로로 지운다.

    지연 임포트다: 이 서비스를 쓰는 `browser_task_memory` 와 이 서비스가 지우는 관계는 잎 모듈
    (`browser_task_memory_store`)을 통해서만 만나야 순환 import 가 생기지 않는다(basedpyright 가
    순환을 오류로 잡는다). 모듈이 없으면(구버전 트리) 조용히 0 이다.
    """
    try:
        from antigravity_k.tools.browser_task_memory_store import integration_purge
    except Exception:
        logger.debug("browser task memory module unavailable for purge", exc_info=True)
        return 0
    try:
        if mode == "expired":
            return integration_purge(service, mode="expired", max_age_days=max_age_days)
        if mode == "redact":
            return integration_purge(service, mode="redact")
        return integration_purge(service, mode="all")
    except Exception:
        logger.exception("browser task memory purge failed")
        return 0


@final
class MemoryService:
    """에이전트 팀의 지속적 메모리(GBrain 모델)를 담당합니다.

    작업 이력, 학습된 지식, 컨텍스트 스냅샷을 영구적으로 저장하고 조회할 수 있습니다.

    Phase 3 업그레이드:
    - VectorStore 통합으로 시맨틱 검색 지원
    - 하이브리드 검색: 벡터 유사도 + 키워드 LIKE 결합
    - 자동 임베딩 갱신
    """

    def __init__(self, db_path: str | None = None):
        """Initialize the MemoryService.

        Args:
            db_path (str | None): str | None db path.

        """
        if db_path is None:
            configured_path = os.environ.get("AGK_MEMORY_DB_PATH", "").strip()
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
                db_path = str(base_dir / "memory.db")

        self.db_path = db_path
        self._vector_store: _VectorStoreLike | None = None
        self._init_db()

    @property
    def vector_store(self) -> _VectorStoreLike | None:
        """VectorStore를 지연 로드합니다."""
        if self._vector_store is None:
            try:
                from antigravity_k.engine.vector_store import VectorStore

                vector_path = f"{self.db_path}.vectors"
                self._vector_store = VectorStore(persist_directory=vector_path)
                logger.info("VectorStore initialized for hybrid search")
            except Exception:
                logger.exception("VectorStore init failed, keyword-only mode")
        return self._vector_store

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _ = conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            _ = conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_items (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            _ = conn.execute("""
                CREATE TABLE IF NOT EXISTS context_snapshots (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    snapshot_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def add_knowledge(self, topic: str, content: str, tags: list[str] | None = None) -> int:
        """새로운 지식 항목을 저장하고 벡터 임베딩을 자동 생성합니다."""
        now = datetime.now().astimezone().replace(tzinfo=None).isoformat()
        tags_str = json.dumps(tags) if tags else "[]"
        with self._get_connection() as conn:
            cursor = _cursor(
                cast(
                    object,
                    conn.execute(
                        "INSERT INTO knowledge_items (topic, content, tags, created_at) VALUES (?, ?, ?, ?)",
                        (topic, content, tags_str, now),
                    ),
                )
            )
            item_id = cursor.lastrowid
            if item_id is None:
                raise sqlite3.DatabaseError("SQLite did not return an inserted knowledge item id")
            conn.commit()

        # 벡터 임베딩 자동 생성
        if self.vector_store is not None:
            embed_text = f"{topic} {content}"
            _ = self.vector_store.store_embedding("knowledge_items", item_id, embed_text)

        logger.info("Knowledge added on topic: %s (id=%s)", topic, item_id)
        return item_id

    def search_knowledge(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
    ) -> list[dict[str, object]]:
        """지식을 검색합니다.

        Args:
            query: 검색 쿼리
            mode: 검색 모드
                - "keyword": 기존 LIKE 검색
                - "vector": 벡터 유사도 검색
                - "hybrid": 벡터 + 키워드 결합 (기본값)
            top_k: 반환할 최대 결과 수

        Returns:
            검색 결과 리스트 (유사도/관련성 내림차순)

        """
        if mode == "keyword" or self.vector_store is None:
            return self._keyword_search(query, top_k)
        elif mode == "vector":
            return self._vector_search(query, top_k)
        else:  # hybrid
            return self._hybrid_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int) -> list[dict[str, object]]:
        """기존 LIKE 기반 키워드 검색."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM knowledge_items WHERE topic LIKE ? OR content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", top_k),
            )
            rows = _fetchall(cur)
            results = [_row_dict(row) for row in rows]
            for r in results:
                r["_search_mode"] = "keyword"
                r["_score"] = 1.0  # 키워드 매칭은 바이너리
            return results

    def _vector_search(self, query: str, top_k: int) -> list[dict[str, object]]:
        """벡터 유사도 검색."""
        if self.vector_store is None:
            return self._keyword_search(query, top_k)

        similar = self.vector_store.search_similar(
            query,
            source_table="knowledge_items",
            top_k=top_k,
        )

        if not similar:
            return []

        # source_id로 원본 데이터 조회
        ids = [_integer(s.get("source_id")) for s in similar]
        sim_map = {_integer(s.get("source_id")): _number(s.get("similarity")) for s in similar}

        placeholders = ",".join("?" * len(ids))
        with self._get_connection() as conn:
            cur = _cursor(
                cast(
                    object,
                    conn.execute(
                        # `placeholders` contains one `?` per separately bound value.
                        f"SELECT * FROM knowledge_items WHERE id IN ({placeholders})",  # nosec B608
                        ids,
                    ),
                )
            )
            rows = [_row_dict(row) for row in cur.fetchall()]

        # 유사도 순 정렬
        for row in rows:
            row["_search_mode"] = "vector"
            row["_score"] = sim_map.get(_integer(row.get("id")), 0.0)
        rows.sort(key=lambda x: _number(x.get("_score")), reverse=True)

        return rows

    def _hybrid_search(self, query: str, top_k: int) -> list[dict[str, object]]:
        """하이브리드 검색: 벡터 + 키워드 결과를 결합합니다.

        Reciprocal Rank Fusion (RRF) 알고리즘 사용.
        """
        k_results = self._keyword_search(query, top_k * 2)
        v_results = self._vector_search(query, top_k * 2)

        # RRF 스코어 계산
        rrf_scores: dict[int, float] = {}
        rrf_k = 60  # RRF 상수

        for rank, item in enumerate(k_results):
            item_id = _integer(item.get("id"))
            rrf_scores[item_id] = rrf_scores.get(item_id, 0) + 1.0 / (rrf_k + rank + 1)

        for rank, item in enumerate(v_results):
            item_id = _integer(item.get("id"))
            rrf_scores[item_id] = rrf_scores.get(item_id, 0) + 1.0 / (rrf_k + rank + 1)

        # 모든 결과를 id 기준으로 병합
        all_items: dict[int, dict[str, object]] = {}
        for item in k_results + v_results:
            item_id = _integer(item.get("id"))
            if item_id not in all_items:
                all_items[item_id] = item

        # RRF 점수 부여 및 정렬
        results: list[dict[str, object]] = []
        for item_id, item in all_items.items():
            item["_search_mode"] = "hybrid"
            item["_score"] = round(rrf_scores.get(item_id, 0), 6)
            results.append(item)

        results.sort(key=lambda x: _number(x.get("_score")), reverse=True)
        return results[:top_k]

    def rebuild_embeddings(self) -> int:
        """기존 지식 항목의 벡터 임베딩을 재생성합니다."""
        if self.vector_store is None:
            logger.warning("VectorStore not available — cannot rebuild embeddings")
            return 0

        with self._get_connection() as conn:
            rows = _fetchall(conn.execute("SELECT id, topic, content FROM knowledge_items"))

        # TF-IDF 학습 (전체 문서로)
        documents = [f"{_text(_row_value(r, 'topic'))} {_text(_row_value(r, 'content'))}" for r in rows]
        if documents:
            self.vector_store.fit_tfidf(documents)

        count = 0
        for row in rows:
            text = f"{_text(_row_value(row, 'topic'))} {_text(_row_value(row, 'content'))}"
            if self.vector_store.store_embedding("knowledge_items", _integer(_row_value(row, "id")), text):
                count += 1

        logger.info("Rebuilt %s/%s embeddings", count, len(rows))
        return count

    def save_snapshot(self, agent_name: str, snapshot_data: dict[str, object]) -> None:
        """에이전트의 현재 상태(컨텍스트) 스냅샷을 저장합니다."""
        now = datetime.now().astimezone().replace(tzinfo=None).isoformat()
        data_str = json.dumps(snapshot_data, ensure_ascii=False)
        with self._get_connection() as conn:
            _ = conn.execute(
                "INSERT INTO context_snapshots (agent_name, snapshot_data, created_at) VALUES (?, ?, ?)",
                (agent_name, data_str, now),
            )
            conn.commit()
        logger.info("Context snapshot saved for agent %s", agent_name)

    def load_latest_snapshot(self, agent_name: str) -> dict[str, object] | None:
        """에이전트의 가장 최근 상태 스냅샷을 불러옵니다."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT snapshot_data FROM context_snapshots WHERE agent_name = ? ORDER BY created_at DESC LIMIT 1",
                (agent_name,),
            )
            row = _fetchone(cur)
            if row:
                payload = cast(object, json.loads(_text(_row_value(row, "snapshot_data"))))
                return cast(dict[str, object], payload) if isinstance(payload, dict) else None
        return None

    def clear_all(self) -> int:
        with self._get_connection() as conn:
            knowledge_count = _integer(_row_value(_fetchone(conn.execute("SELECT COUNT(*) FROM knowledge_items")), 0))
            snapshot_count = _integer(_row_value(_fetchone(conn.execute("SELECT COUNT(*) FROM context_snapshots")), 0))
            _ = conn.execute("DELETE FROM knowledge_items")
            _ = conn.execute("DELETE FROM context_snapshots")
            conn.commit()

        if self._vector_store is not None:
            _ = self._vector_store.clear()
        # 브라우저 작업 기억(task 21)도 같은 DB 를 쓴다 — 전체 삭제가 그것만 남기면 거짓말이 된다.
        browser_count = _browser_memory_purge(self, mode="all")
        return knowledge_count + snapshot_count + browser_count

    def export_all(self) -> list[dict[str, object]]:
        with self._get_connection() as conn:
            knowledge = [
                _row_dict(row) for row in _fetchall(conn.execute("SELECT * FROM knowledge_items ORDER BY created_at"))
            ]
            snapshots = [
                _row_dict(row) for row in _fetchall(conn.execute("SELECT * FROM context_snapshots ORDER BY created_at"))
            ]
        result: list[dict[str, object]] = [{"kind": "knowledge", "data": row} for row in knowledge]
        return result + [{"kind": "snapshot", "data": row} for row in snapshots]

    def redact_all(self) -> int:
        from antigravity_k.engine.secret_scanner import redact_full

        changed = 0
        with self._get_connection() as conn:
            for row in _fetchall(conn.execute("SELECT id, topic, content, tags FROM knowledge_items")):
                topic = _text(_row_value(row, "topic"))
                content = _text(_row_value(row, "content"))
                tags = _text(_row_value(row, "tags"))
                values = [redact_full(topic), redact_full(content), redact_full(tags)]
                if values != [topic, content, tags]:
                    _ = conn.execute(
                        "UPDATE knowledge_items SET topic = ?, content = ?, tags = ? WHERE id = ?",
                        (*values, _row_value(row, "id")),
                    )
                    changed += 1
            for row in _fetchall(conn.execute("SELECT id, snapshot_data FROM context_snapshots")):
                snapshot_data = _text(_row_value(row, "snapshot_data"))
                redacted = redact_full(snapshot_data)
                if redacted != snapshot_data:
                    _ = conn.execute(
                        "UPDATE context_snapshots SET snapshot_data = ? WHERE id = ?",
                        (redacted, _row_value(row, "id")),
                    )
                    changed += 1
            conn.commit()
        # 브라우저 기억은 항목 단위로 색인을 지운다(전체 clear 는 vault 청크까지 지운다).
        changed += _browser_memory_purge(self, mode="redact")
        if changed and self._vector_store is not None:
            _ = self._vector_store.clear()
            _ = self.rebuild_embeddings()
        return changed

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        cutoff = (datetime.now().astimezone().replace(tzinfo=None) - timedelta(days=max_age_days)).isoformat()
        with self._get_connection() as conn:
            knowledge_cursor = conn.execute("DELETE FROM knowledge_items WHERE created_at < ?", (cutoff,))
            snapshots_cursor = conn.execute("DELETE FROM context_snapshots WHERE created_at < ?", (cutoff,))
            knowledge = knowledge_cursor.rowcount
            snapshots = snapshots_cursor.rowcount
            conn.commit()
        if knowledge and self._vector_store is not None:
            _ = self._vector_store.clear()
            _ = self.rebuild_embeddings()
        return knowledge + snapshots + _browser_memory_purge(self, mode="expired", max_age_days=max_age_days)

    def get_stats(self) -> StatsPayload:
        """메모리 서비스 통계."""
        with self._get_connection() as conn:
            ki_count = _integer(_row_value(_fetchone(conn.execute("SELECT COUNT(*) FROM knowledge_items")), 0))
            snap_count = _integer(_row_value(_fetchone(conn.execute("SELECT COUNT(*) FROM context_snapshots")), 0))

        stats = cast(
            StatsPayload,
            cast(
                object,
                {
                    "knowledge_items": ki_count,
                    "context_snapshots": snap_count,
                    "db_path": self.db_path,
                },
            ),
        )

        if self.vector_store is not None:
            stats["vector_store"] = self.vector_store.get_stats()

        return stats
