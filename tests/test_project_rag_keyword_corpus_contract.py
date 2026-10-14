"""Actual Chroma lexical corpus contracts; deterministic vectors prove routing only."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from chromadb.api.models.Collection import Collection

from antigravity_k.engine.rag_indexer import RAGIndexer
from tests.test_project_rag_embedding_identity_contract import Case, chunk
from tests.test_project_rag_embedding_identity_contract import case as case


@pytest.fixture
def native_exports(case: Case, monkeypatch: pytest.MonkeyPatch):
    original = Collection.get

    def get(self, *args, **kwargs):
        case.native.append({"operation": "get", "include": kwargs.get("include")})
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Collection, "get", get)


def corpus(case: Case) -> RAGIndexer:
    project = case.root / "project"
    project.mkdir()
    store = case.store()
    rows = [
        {
            "id": "identifier",
            "text": "def reconcile_ledger(): pass",
            "metadata": {"source": "worker.py", "node_name": "reconcile_ledger"},
        },
        {
            "id": "text",
            "text": "reconcile ledger happens here",
            "metadata": {"source": "notes.md", "node_name": "notes"},
        },
        {
            "id": "filename",
            "text": "unrelated content",
            "metadata": {"source": "invoice_archive.py", "node_name": "archive"},
        },
    ]
    for row in rows:
        meta = cast(dict[str, str], row["metadata"])
        (project / meta["source"]).write_text(str(row["text"]))
    store.upsert_chunks(rows)
    case.engine.calls.clear()
    case.native.clear()
    return RAGIndexer(str(project), store)


@pytest.mark.usefixtures("native_exports")
@pytest.mark.parametrize(("query", "expected"), [("reconcile ledger", "identifier"), ("invoice archive", "filename")])
def test_real_keyword_export_rank_without_embedding(case: Case, query: str, expected: str):
    indexer = corpus(case)
    result = indexer.search(query, mode="keyword")
    assert case.engine.calls == []
    assert result[0]["id"] == expected
    assert "text" in result[0] and "document" not in result[0]
    assert not any(op["operation"] == "query" for op in case.native)
    assert any(op["operation"] == "get" and op["include"] == ["documents", "metadatas"] for op in case.native)
    case.observations["results"] = result


@pytest.mark.parametrize("query", ["", "unmatchedword", "!!!"])
@pytest.mark.parametrize("populated", [False, True])
def test_empty_or_no_match_keyword_never_embeds(case: Case, query: str, populated: bool):
    indexer = corpus(case) if populated else RAGIndexer(str(case.root), case.store())
    assert indexer.search(query, mode="keyword") == []
    assert case.engine.calls == []


@pytest.mark.parametrize(("query", "expected"), [("ledger", 1), ("context", 2)])
def test_hybrid_only_existing_semantic_channels_embed(case: Case, query: str, expected: int):
    indexer = corpus(case)
    assert indexer.search(query)
    assert len(case.engine.calls) == expected
    assert sum(op["operation"] == "query" for op in case.native) == expected
    assert all(call["allow_fallback"] is False for call in case.engine.calls)
    case.observations["results"] = indexer.search(query, mode="keyword")
    assert len(case.engine.calls) == expected


def test_keyword_corpus_change_delete_reopen_and_other_project(case: Case):
    project = case.root / "project"
    project.mkdir()
    source = project / "ledger.py"
    source.write_text("def old_identifier():\n    return 1\n")
    store = case.store()
    indexer = RAGIndexer(str(project), store)
    assert indexer.index_file("ledger.py") == 1
    other = case.store(case.root / "other-vectors")
    other.upsert_chunks([chunk("other", "other_sentinel", "elsewhere.py")])
    other_before = other.export_all()
    case.engine.calls.clear()
    assert indexer.search("old identifier", mode="keyword")
    assert indexer.search("other sentinel", mode="keyword") == []
    assert case.engine.calls == []
    source.write_text("def new_identifier():\n    return 2\n")
    assert indexer.index_file("ledger.py") == 1
    case.engine.calls.clear()
    assert indexer.search("old", mode="keyword") == []
    result = indexer.search("new identifier", mode="keyword")
    assert len(result) == 1 and cast(dict[str, object], result[0]["provenance"])["freshness"] == "fresh"
    assert case.engine.calls == []
    store.close()
    reopened = case.store()
    indexer = RAGIndexer(str(project), reopened)
    assert indexer.search("new identifier", mode="keyword")[0]["id"] == result[0]["id"]
    source.unlink()
    assert indexer.sync() == 0
    assert indexer.search("new identifier", mode="keyword") == []
    assert case.engine.calls == []
    assert other.export_all() == other_before
    case.observations["fresh_result"] = result


def test_existing_stale_filters_and_provenance_unchanged(case: Case):
    project = case.root / "project"
    project.mkdir()
    source = project / "ledger.py"
    source.write_text("def ledger():\n    return 1\n")
    store = case.store()
    indexer = RAGIndexer(str(project), store)
    indexer.index_file("ledger.py")
    source.write_text("def ledger():\n    return 2\n")
    case.engine.calls.clear()
    lexical = indexer.search("ledger", mode="keyword")
    assert cast(dict[str, object], lexical[0]["provenance"])["freshness"] == "stale"
    assert case.engine.calls == []
    assert indexer.search("ledger", mode="hybrid") == []
    assert indexer.search("ledger", mode="long_context") == []
    assert len(case.engine.calls) == 2


def test_closed_and_export_failure_surface_without_model(case: Case, monkeypatch: pytest.MonkeyPatch):
    indexer = corpus(case)
    store = case.stores[0]

    def fail():
        raise RuntimeError("export failed")

    with monkeypatch.context() as patch:
        patch.setattr(store, "export_all", fail)
        with pytest.raises(RuntimeError, match="export failed"):
            indexer.search("ledger", mode="keyword")
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        indexer.search("ledger", mode="keyword")
    assert case.engine.calls == []


class LegacyStore:
    def __init__(self):
        self.calls = 0

    def search(self, query: str, n_results: int = 5):
        self.calls += 1
        return [{"id": "legacy", "text": query, "metadata": {}}][:n_results]


def test_private_chunks_compatibility_and_genuine_absence_fallback(tmp_path: Path):
    store = LegacyStore()
    indexer = RAGIndexer(str(tmp_path), store)
    assert indexer.search("ledger", mode="keyword")[0]["id"] == "legacy"
    assert store.calls == 1
    setattr(store, "_chunks", [{"id": "private", "text": "ledger", "metadata": {}}])
    assert indexer.search("ledger", mode="keyword")[0]["id"] == "private"
    assert store.calls == 1


@pytest.mark.parametrize(
    "value",
    [
        None,
        "bad",
        [None],
        [{"id": 1, "document": "ledger", "metadata": {}}],
        [{"id": "one", "document": 1, "metadata": {}}],
        [{"id": "one", "document": "ledger", "metadata": None}],
    ],
)
def test_invalid_export_is_not_semantic_fallback(tmp_path: Path, value: object):
    store = LegacyStore()
    setattr(store, "export_all", cast(Callable[[], object], lambda: value))
    with pytest.raises(ValueError, match="corpus"):
        RAGIndexer(str(tmp_path), store).search("ledger", mode="keyword")
    assert store.calls == 0


@pytest.mark.parametrize("exporter", [None, 7, "not callable"])
def test_present_but_invalid_export_capability_is_not_fallback(tmp_path: Path, exporter: object):
    store = LegacyStore()
    setattr(store, "export_all", exporter)
    with pytest.raises(ValueError, match="corpus"):
        RAGIndexer(str(tmp_path), store).search("ledger", mode="keyword")
    assert store.calls == 0


@pytest.mark.parametrize("query", ["reconcile ledger", "invoice archive"])
def test_native_export_preserves_existing_lexical_ranking(case: Case, query: str):
    indexer = corpus(case)
    legacy = LegacyStore()
    setattr(
        legacy,
        "_chunks",
        [
            {"id": row["id"], "text": row["document"], "metadata": row["metadata"]}
            for row in case.stores[0].export_all()
        ],
    )
    previous = RAGIndexer(indexer.project_root, legacy)
    assert indexer._keyword_search(query) == previous._keyword_search(query)
    assert case.engine.calls == [] and legacy.calls == 0
