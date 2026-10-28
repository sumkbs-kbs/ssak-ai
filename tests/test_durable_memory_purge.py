from contextlib import closing
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import MagicMock

import pytest
from fastapi import Request as FastAPIRequest
from starlette.datastructures import State

from antigravity_k.engine.durable_memory import DurableMemoryProvider
from antigravity_k.engine.gbrain import GBrain
from antigravity_k.engine.memory_provider import MemoryManager
from antigravity_k.engine.vector_store import VectorStore
from antigravity_k.knowledge import wiki
from antigravity_k.knowledge.memory_service import MemoryService


class _CallMock(Protocol):
    def assert_called_once_with(self, *args: object, **kwargs: object) -> None: ...

    def assert_not_called(self) -> None: ...


def test_memory_service_clear_all_removes_rows_and_embeddings(tmp_path: Path):
    service = MemoryService(db_path=str(tmp_path / "memory.db"))
    _ = service.add_knowledge("topic", "private knowledge")
    _ = service.save_snapshot("agent", {"secret": "snapshot"})
    vector_store = MagicMock()
    setattr(service, "_vector_store", vector_store)

    deleted = service.clear_all()

    assert deleted == 2
    assert service.get_stats()["knowledge_items"] == 0
    assert service.get_stats()["context_snapshots"] == 0
    cast(_CallMock, vector_store.clear).assert_called_once_with()


@pytest.mark.parametrize("closed", [False, True], ids=["open", "closed"])
def test_vector_store_clear_deletes_all_collection_ids(tmp_path: Path, closed: bool) -> None:
    from chromadb import Collection

    storage = str(tmp_path / "vectors")
    with closing(VectorStore(storage)) as store:
        assert isinstance(store.collection, Collection)
        store.collection.upsert(ids=["one", "two"], embeddings=[[1.0, 0.0], [0.0, 1.0]])
        assert set(store.collection.get()["ids"]) == {"one", "two"}
        if closed:
            store.close()
            with pytest.raises(RuntimeError, match="VectorStore is closed"):
                store.clear()
        else:
            assert store.clear() == 2
            assert store.collection.get()["ids"] == []
            assert store.clear() == 0

    with closing(VectorStore(storage)) as reopened:
        assert isinstance(reopened.collection, Collection)
        assert set(reopened.collection.get()["ids"]) == ({"one", "two"} if closed else set())


def test_wiki_clear_all_removes_entries_and_generated_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wiki, "WIKI_DIR", tmp_path / "wiki")
    knowledge = wiki.LLMWiki(db_path=tmp_path / "wiki.db")
    _ = knowledge.add_entry("Private note", "secret content", category="note")

    deleted = knowledge.clear_all()

    assert deleted == 1
    assert knowledge.get_stats()["total_entries"] == 0
    assert list((tmp_path / "wiki").rglob("*.md")) == []


@pytest.mark.parametrize("closed", [False, True], ids=["open", "closed"])
def test_gbrain_clear_all_removes_graph_and_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, closed: bool
) -> None:
    import numpy as np
    from chromadb import Collection
    from chromadb.api.types import DefaultEmbeddingFunction, Documents, Embeddings

    def synthetic_embedding(self: DefaultEmbeddingFunction, input: Documents) -> Embeddings:
        return [np.array([1.0, 0.0], dtype=np.float32) for _ in input]

    # Exercise real locks, GraphML and Chroma persistence without model inference.
    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", synthetic_embedding)
    storage = str(tmp_path / "gbrain")
    with closing(GBrain(storage_dir=storage)) as brain:
        # r29: no default-embedding collection; vector side is explicit not-ready, graph purge still real.
        assert brain.collection is None and brain.vector_not_ready_reason
        assert not isinstance(brain.collection, Collection)
        brain.add_node("one", "note", "private knowledge one")
        brain.add_node("two", "note", "private knowledge two")
        brain.add_edge("one", "two", "related")
        assert brain.graph.number_of_nodes() == 2
        assert brain.graph.number_of_edges() == 1
        assert brain.reward_tick == 3
        if closed:
            brain.close()
            with pytest.raises(RuntimeError, match="Cannot clear a closed GBrain instance"):
                brain.clear_all()
        else:
            assert brain.clear_all() == 2
            assert brain.graph.number_of_nodes() == 0
            assert brain.graph.number_of_edges() == 0
            assert brain.reward_tick == 0
            assert brain.clear_all() == 0

    with closing(GBrain(storage_dir=storage)) as reopened:
        assert reopened.collection is None and reopened.vector_not_ready_reason  # r29
        expected_ids = {"one", "two"} if closed else set()
        assert {node["id"] for node in reopened.export_all()} == expected_ids
        assert reopened.graph.number_of_edges() == int(closed)
        assert reopened.reward_tick == (3 if closed else 0)


def test_durable_provider_runs_purge_only_for_all_scope() -> None:
    clear_all = MagicMock(return_value=3)
    manager = MemoryManager()
    manager.add_provider(DurableMemoryProvider("durable", clear_all))

    assert manager.clear("global") == {"durable": 0}
    clear_all.assert_not_called()
    assert manager.clear("all") == {"durable": 3}
    clear_all.assert_called_once_with()


def test_dependency_memory_manager_registers_durable_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from antigravity_k.api import dependencies
    from antigravity_k.engine.project_registry import ProjectRegistry

    storage = tmp_path / "projects.json"
    monkeypatch.setattr(
        "antigravity_k.engine.project_registry._DEFAULT_STORAGE_PATH",
        storage,
    )
    import antigravity_k.engine.project_registry as preg

    monkeypatch.setattr(preg, "_global_registry", None)
    from antigravity_k.config import config

    monkeypatch.setattr(config.paths, "project_root", tmp_path.resolve())
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)

    dependencies.reset_runtime_dependencies()
    project_root = tmp_path / "project"
    project_root.mkdir()
    registry = ProjectRegistry(storage_path=storage)
    monkeypatch.setattr(preg, "_global_registry", registry)
    rec = registry.add_project("proj", str(project_root))

    manager = dependencies.get_memory_manager(project_id=rec.id, project_root=str(project_root))

    assert [provider.name for provider in manager.providers] == [
        "builtin",
        "episodic",
        "working_memory",
        "global",
        "project",
        "memory_service",
        "wiki",
        "gbrain",
        "project_vector",
        "search_cache",
    ]
    dependencies.reset_runtime_dependencies()


@pytest.mark.asyncio
async def test_memory_purge_route_reports_durable_provider_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.api.routes import system_api

    manager = MemoryManager()
    manager.add_provider(DurableMemoryProvider("wiki", lambda: 4))
    audit_logger = MagicMock()
    monkeypatch.setattr(system_api, "_get_memory_manager", lambda: manager)
    monkeypatch.setattr(system_api, "get_audit_logger", lambda: audit_logger)

    class RequestStub:
        async def json(self) -> dict[str, str]:
            return {"scope": "all"}

    result = await system_api.purge_memory(cast(FastAPIRequest[State], cast(object, RequestStub())))

    assert result["deleted"] == {"wiki": 4}
    cast(_CallMock, audit_logger.log_event).assert_called_once_with(
        "memory_purge",
        {"scope": "all", "deleted": {"wiki": 4}},
    )
