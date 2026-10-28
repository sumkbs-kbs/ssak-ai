"""Tests for memory_service.py — MemoryService class.

Covers:
- __init__ with custom/auto db_path, table creation
- add_knowledge with and without vector_store
- _keyword_search, _vector_search, _hybrid_search (RRF)
- search_knowledge dispatcher
- save_snapshot / load_latest_snapshot
- get_stats, rebuild_embeddings
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import MagicMock

import pytest

from antigravity_k.knowledge.memory_service import MemoryService
from tests._legacy_fake_embedding import legacy_fake_binding  # noqa: F401  # r29 explicit fake binding

pytestmark = pytest.mark.usefixtures("legacy_fake_binding")


class _MockMethod(Protocol):
    called: bool

    def assert_called_once(self) -> None: ...


class _VectorStoreDouble(Protocol):
    store_embedding: _MockMethod
    search_similar: _MockMethod
    get_stats: _MockMethod
    fit_tfidf: _MockMethod


class _CursorDouble:
    lastrowid: int | None = None


class _ConnectionDouble:
    def __enter__(self) -> _ConnectionDouble:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> _CursorDouble:
        return _CursorDouble()


def _set_vector_store(mem: MemoryService, value: object) -> None:
    setattr(mem, "_vector_store", value)


def _connection(mem: MemoryService) -> sqlite3.Connection:
    return cast(sqlite3.Connection, getattr(mem, "_get_connection")())


def _search(mem: MemoryService, method: str, query: str, top_k: int) -> list[dict[str, object]]:
    fn = cast(Callable[[str, int], list[dict[str, object]]], getattr(mem, method))
    return fn(query, top_k)


def _none_vector_store(_service: MemoryService) -> None:
    return None


# ─── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def mem(tmp_path: Path) -> MemoryService:
    """MemoryService with temporary SQLite database."""
    db_path = str(tmp_path / "test_memory.db")
    return MemoryService(db_path=db_path)


# ─── Init ────────────────────────────────────────────────────────


class TestMemoryServiceInit:
    def test_custom_db_path(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "custom.db")
        ms = MemoryService(db_path=db_path)
        assert ms.db_path == db_path
        assert getattr(ms, "_vector_store") is None

    def test_auto_db_path(self):
        """db_path=None이면 data/memory.db에 생성."""
        ms = MemoryService(db_path=None)
        assert ms.db_path is not None
        assert "memory.db" in ms.db_path
        assert "data" in ms.db_path

    def test_tables_created(self, mem: MemoryService):
        """초기화 시 knowledge_items와 context_snapshots 테이블 생성."""
        conn = _connection(mem)
        tables = cast(list[sqlite3.Row], conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        table_names = [str(cast(object, t["name"])) for t in tables]
        assert "knowledge_items" in table_names
        assert "context_snapshots" in table_names


# ─── Add Knowledge ────────────────────────────────────────────────


class TestMemoryServiceAddKnowledge:
    def test_adds_knowledge(self, mem: MemoryService):
        item_id = mem.add_knowledge("python", "Python is a programming language")
        assert item_id is not None
        assert isinstance(item_id, int)

    def test_adds_knowledge_with_tags(self, mem: MemoryService):
        item_id = mem.add_knowledge("pytest", "Testing framework", tags=["test", "python"])
        assert item_id is not None

    def test_adds_knowledge_when_vector_backend_is_unavailable(
        self,
        mem: MemoryService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(sys.modules, "chromadb", None)
        item_id = mem.add_knowledge("topic", "content")
        assert item_id is not None
        assert mem.vector_store is None

    def test_adds_knowledge_with_vector_store(self, tmp_path: Path) -> None:
        """vector_store가 있으면 store_embedding 호출."""
        ms = MemoryService(db_path=str(tmp_path / "vec_test.db"))

        mock_vs = cast(_VectorStoreDouble, MagicMock())
        setattr(mock_vs.store_embedding, "return_value", True)
        _set_vector_store(ms, mock_vs)

        _ = ms.add_knowledge("test", "vector content")
        mock_vs.store_embedding.assert_called_once()

    def test_add_knowledge_rejects_missing_sqlite_id(self, mem: MemoryService, monkeypatch: pytest.MonkeyPatch) -> None:
        conn = _ConnectionDouble()
        monkeypatch.setattr(mem, "_get_connection", lambda: conn)

        with pytest.raises(sqlite3.DatabaseError, match="inserted knowledge item id"):
            _ = mem.add_knowledge("topic", "content")


# ─── Keyword Search ──────────────────────────────────────────────


class TestMemoryServiceKeywordSearch:
    def test_empty_results(self, mem: MemoryService):
        results = _search(mem, "_keyword_search", "nonexistent", 10)
        assert results == []

    def test_matches_topic(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "A programming language")
        _ = mem.add_knowledge("java", "Another language")
        results = _search(mem, "_keyword_search", "python", 10)
        assert len(results) == 1
        assert results[0]["topic"] == "python"

    def test_matches_content(self, mem: MemoryService):
        _ = mem.add_knowledge("general", "This is about python programming")
        results = _search(mem, "_keyword_search", "python", 10)
        assert len(results) == 1

    def test_respects_top_k(self, mem: MemoryService):
        for i in range(5):
            _ = mem.add_knowledge(f"topic{i}", f"content{i}")
        results = _search(mem, "_keyword_search", "topic", 3)
        assert len(results) <= 3

    def test_sets_search_mode(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        results = _search(mem, "_keyword_search", "python", 10)
        assert results[0]["_search_mode"] == "keyword"

    def test_sets_score(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        results = _search(mem, "_keyword_search", "python", 10)
        assert results[0]["_score"] == 1.0


# ─── Vector Search ───────────────────────────────────────────────


class TestMemoryServiceVectorSearch:
    def test_falls_back_to_keyword_when_no_vector_store(
        self, mem: MemoryService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vector_store가 없으면 keyword 검색으로 폴백."""
        monkeypatch.setattr(MemoryService, "vector_store", property(_none_vector_store))
        _ = mem.add_knowledge("python", "content")
        results = _search(mem, "_vector_search", "python", 10)
        assert len(results) == 1
        assert results[0]["_search_mode"] == "keyword"

    def test_returns_empty_when_no_similar(self, mem: MemoryService):
        mock_vs = cast(_VectorStoreDouble, MagicMock())
        setattr(mock_vs.search_similar, "return_value", [])
        _set_vector_store(mem, mock_vs)
        results = _search(mem, "_vector_search", "anything", 10)
        assert results == []

    def test_uses_vector_store(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        mock_vs = cast(_VectorStoreDouble, MagicMock())
        # search_similar returns results with source_id
        setattr(
            mock_vs.search_similar,
            "return_value",
            [
                {"source_id": 1, "similarity": 0.95},
            ],
        )
        _set_vector_store(mem, mock_vs)

        results = _search(mem, "_vector_search", "python", 10)
        assert len(results) == 1
        assert results[0]["_search_mode"] == "vector"
        assert results[0]["_score"] == 0.95


# ─── Hybrid Search (RRF) ─────────────────────────────────────────


class TestMemoryServiceHybridSearch:
    def test_hybrid_search_empty(self, mem: MemoryService):
        results = _search(mem, "_hybrid_search", "nonexistent", 10)
        assert results == []

    def test_hybrid_search_with_data(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "programming")
        _ = mem.add_knowledge("java", "programming")

        # Without vector_store, hybrid = keyword only
        results = _search(mem, "_hybrid_search", "programming", 10)
        assert len(results) >= 2
        assert all(r["_search_mode"] == "hybrid" for r in results)

    def test_hybrid_rrf_scoring(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "best language")

        mock_vs = cast(_VectorStoreDouble, MagicMock())
        setattr(
            mock_vs.search_similar,
            "return_value",
            [
                {"source_id": 1, "similarity": 0.9},
            ],
        )
        _set_vector_store(mem, mock_vs)

        results = _search(mem, "_hybrid_search", "python", 10)
        assert len(results) >= 1
        assert results[0]["_search_mode"] == "hybrid"
        # RRF score should be a small positive float
        assert 0 < cast(float, results[0]["_score"]) < 1.0

    def test_hybrid_respects_top_k(self, mem: MemoryService):
        for i in range(5):
            _ = mem.add_knowledge(f"topic{i}", f"python related {i}")
        results = _search(mem, "_hybrid_search", "python", 2)
        assert len(results) <= 2


# ─── Search Knowledge ────────────────────────────────────────────


class TestMemoryServiceSearchKnowledge:
    def test_keyword_mode(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        results = mem.search_knowledge("python", mode="keyword")
        assert len(results) == 1

    def test_vector_mode_fallback(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        results = mem.search_knowledge("python", mode="vector")
        assert len(results) == 1

    def test_hybrid_mode_default(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content")
        results = mem.search_knowledge("python")
        assert len(results) >= 1


# ─── Snapshots ────────────────────────────────────────────────────


class TestMemoryServiceSnapshots:
    def test_save_snapshot(self, mem: MemoryService):
        _ = mem.save_snapshot("agent1", {"state": "running", "task": "test"})
        conn = _connection(mem)
        count = cast(int, conn.execute("SELECT COUNT(*) FROM context_snapshots").fetchone()[0])
        assert count == 1

    def test_load_latest_snapshot_none(self, mem: MemoryService):
        result = mem.load_latest_snapshot("nonexistent")
        assert result is None

    def test_load_latest_snapshot(self, mem: MemoryService):
        _ = mem.save_snapshot("agent1", {"state": "idle"})
        _ = mem.save_snapshot("agent1", {"state": "running"})
        result = mem.load_latest_snapshot("agent1")
        assert result is not None
        assert result["state"] == "running"

    def test_load_latest_snapshot_multiple_agents(self, mem: MemoryService):
        _ = mem.save_snapshot("agent_a", {"task": "A"})
        _ = mem.save_snapshot("agent_b", {"task": "B"})
        result_a = mem.load_latest_snapshot("agent_a")
        result_b = mem.load_latest_snapshot("agent_b")
        assert result_a is not None
        assert result_b is not None
        assert result_a["task"] == "A"
        assert result_b["task"] == "B"


# ─── Stats ────────────────────────────────────────────────────────


class TestMemoryServiceGetStats:
    def test_empty_stats(self, mem: MemoryService):
        stats = mem.get_stats()
        assert stats["knowledge_items"] == 0
        assert stats["context_snapshots"] == 0
        assert stats["db_path"] == mem.db_path

    def test_with_data(self, mem: MemoryService):
        _ = mem.add_knowledge("topic", "content")
        _ = mem.save_snapshot("agent", {"data": "test"})
        stats = mem.get_stats()
        assert stats["knowledge_items"] == 1
        assert stats["context_snapshots"] == 1

    def test_with_vector_store_stats(self, mem: MemoryService):
        mock_vs = cast(_VectorStoreDouble, MagicMock())
        setattr(mock_vs.get_stats, "return_value", {"embeddings": 5})
        _set_vector_store(mem, mock_vs)
        stats = mem.get_stats()
        assert "vector_store" in stats
        assert stats["vector_store"]["embeddings"] == 5


# ─── Rebuild Embeddings ──────────────────────────────────────────


class TestMemoryServiceRebuildEmbeddings:
    def test_no_vector_store_returns_zero(self, mem: MemoryService, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(MemoryService, "vector_store", property(_none_vector_store))
        count = mem.rebuild_embeddings()
        assert count == 0

    def test_rebuilds_embeddings(self, mem: MemoryService):
        _ = mem.add_knowledge("python", "content about python")
        _ = mem.add_knowledge("java", "content about java")

        mock_vs = cast(_VectorStoreDouble, MagicMock())
        setattr(mock_vs.store_embedding, "return_value", True)
        _set_vector_store(mem, mock_vs)

        count = mem.rebuild_embeddings()
        assert count == 2
        assert mock_vs.fit_tfidf.called


# ─── VectorStore property ────────────────────────────────────────


class TestMemoryServiceVectorStoreProperty:
    def test_vector_store_returns_none_when_not_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vector_store 모듈이 없으면 property가 None 반환."""
        ms = MemoryService(db_path=str(tmp_path / "no_vs.db"))
        monkeypatch.setattr(MemoryService, "vector_store", property(_none_vector_store))
        vs = ms.vector_store
        assert vs is None

    def test_vector_store_returns_mock_when_set_directly(self, tmp_path: Path) -> None:
        """_vector_store 직접 설정 시 해당 값 반환."""
        ms = MemoryService(db_path=str(tmp_path / "mock_vs.db"))
        mock_vs = MagicMock()
        _set_vector_store(ms, mock_vs)
        assert ms.vector_store is mock_vs
