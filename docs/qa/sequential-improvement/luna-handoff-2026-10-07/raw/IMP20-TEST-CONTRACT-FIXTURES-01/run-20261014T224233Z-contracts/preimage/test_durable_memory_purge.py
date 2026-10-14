from pathlib import Path
from typing import Protocol, cast
from unittest.mock import MagicMock

import networkx as nx
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


def test_vector_store_clear_deletes_all_collection_ids():
    class Collection:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def get(self) -> dict[str, list[str]]:
            return {"ids": ["one", "two"]}

        def delete(self, ids: list[str]) -> None:
            self.deleted = ids

    store = object.__new__(VectorStore)
    setattr(store, "collection", Collection())
    setattr(store, "_closed", True)

    assert store.clear() == 2
    collection = cast(Collection, getattr(store, "collection"))
    assert collection.deleted == ["one", "two"]


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


def test_gbrain_clear_all_removes_graph_and_vectors():
    class Collection:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def get(self) -> dict[str, list[str]]:
            return {"ids": ["one", "two"]}

        def delete(self, ids: list[str]) -> None:
            self.deleted = ids

    brain = object.__new__(GBrain)
    brain.graph = nx.DiGraph()
    brain.graph.add_nodes_from(["one", "two"])
    brain.collection = Collection()
    setattr(brain, "_closed", True)
    setattr(brain, "_save_graph", MagicMock())

    assert brain.clear_all() == 2
    assert brain.graph.number_of_nodes() == 0
    assert brain.collection.deleted == ["one", "two"]
    cast(_CallMock, getattr(brain, "_save_graph")).assert_called_once_with()


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
