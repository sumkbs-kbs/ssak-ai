"""Project embedding routing with real owned Chroma and deterministic model doubles."""

from __future__ import annotations

import hashlib
import json
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import cast, override

import chromadb
import pytest
import yaml
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from antigravity_k.engine.embeddings import EmbeddingEngine, EmbeddingModelUnavailableError
from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.project_embedding_binding import (
    DIMENSIONS_METADATA_KEY,
    ProjectEmbeddingBinding,
    ProjectEmbeddingBindingError,
)
from antigravity_k.engine.rag_indexer import RAGIndexer
from antigravity_k.engine.vector_store import MetadataValue, VectorStore

MODEL = "configured-embedding"


class FakeEngine(EmbeddingEngine):
    def __init__(self, registry: ModelRegistry):
        super().__init__(registry=registry)
        self.calls: list[dict[str, object]] = []
        self.result: object = None
        self.failure: Exception | None = None

    @override
    def embed(self, text: str | list[str], model_name: str, *, allow_fallback: bool = True) -> list[list[float]]:
        self.calls.append({"text": text, "model_name": model_name, "allow_fallback": allow_fallback})
        if self.failure is not None:
            raise self.failure
        if self.result is not None:
            return cast(list[list[float]], self.result)
        texts = [text] if isinstance(text, str) else text
        return [[1.0, float(len(item) % 13 + 1), 0.5] for item in texts]


@dataclass
class Case:
    root: Path
    engine: FakeEngine
    forbidden: list[str]
    native: list[dict[str, object]]
    stores: list[VectorStore] = field(default_factory=list)
    observations: dict[str, object] = field(default_factory=dict)

    def binding(self, **kwargs: str) -> ProjectEmbeddingBinding:
        return ProjectEmbeddingBinding(self.engine, MODEL, **kwargs)

    def store(self, path: Path | None = None, binding: ProjectEmbeddingBinding | None = None) -> VectorStore:
        store = VectorStore(str(path or self.root / "vectors"), embedding_binding=binding or self.binding())
        self.stores.append(store)
        return store


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    forbidden: list[str] = []
    native: list[dict[str, object]] = []

    def deny(*args: object, **kwargs: object):
        forbidden.append("network/model-loader/fallback/default-embedding/download")
        raise AssertionError("Unexpected physical network, model loader, fallback or default Chroma embedding")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(EmbeddingEngine, "load_model", deny)
    monkeypatch.setattr(EmbeddingEngine, "_fallback_embedding", deny)
    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", deny)
    monkeypatch.setattr(ONNXMiniLM_L6_V2, "_download_model_if_not_exists", deny)
    original_upsert = Collection.upsert
    original_query = Collection.query
    original_delete = Collection.delete

    def upsert(self, *args, **kwargs):
        native.append(
            {
                "operation": "upsert",
                "ids": kwargs.get("ids"),
                "documents": kwargs.get("documents"),
                "embeddings": kwargs.get("embeddings"),
            }
        )
        return original_upsert(self, *args, **kwargs)

    def query(self, *args, **kwargs):
        native.append(
            {
                "operation": "query",
                "query_texts": kwargs.get("query_texts"),
                "query_embeddings": kwargs.get("query_embeddings"),
            }
        )
        return original_query(self, *args, **kwargs)

    def delete(self, *args, **kwargs):
        native.append({"operation": "delete", "ids": kwargs.get("ids"), "where": kwargs.get("where")})
        return original_delete(self, *args, **kwargs)

    monkeypatch.setattr(Collection, "delete", delete)
    monkeypatch.setattr(Collection, "upsert", upsert)
    monkeypatch.setattr(Collection, "query", query)
    config = tmp_path / "models.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "models": {
                    "embedding": [
                        {"name": MODEL, "repo": "nomic-embed-text:latest", "provider": "ollama", "dimensions": 0}
                    ]
                },
                "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
            }
        )
    )
    engine = FakeEngine(ModelRegistry(config_path=str(config)))
    result = Case(tmp_path, engine, forbidden, native)
    yield result
    for store in result.stores:
        store.close()
    capture = os.environ.get("RAG_BINDING_CAPTURE_ROOT")
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        (target / (hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16] + ".json")).write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "engine_calls": engine.calls,
                    "forbidden": forbidden,
                    "native": native,
                    "observations": result.observations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    assert forbidden == []


def chunk(identifier: str = "one", text: str = "stored document", source: str = "note.md") -> dict[str, object]:
    return {"id": identifier, "text": text, "metadata": {"source": source}}


def profile(case: Case):
    assert case.engine.registry is not None
    value = case.engine.registry.get_model(MODEL)
    assert value is not None
    return value


def test_constructor_no_inference_and_document_query_redaction_use_strict_binding(case: Case):
    binding = case.binding(document_prefix="search_document: ", query_prefix="search_query: ")
    store = case.store(binding=binding)
    assert case.engine.calls == []
    identity = binding.identity
    assert identity.configured_dimensions == 0 and identity.weight_revision is None
    assert identity.weight_revision_status == "UNVERIFIED"
    assert identity.endpoint == "http://localhost:11434"
    secret = "api_key=sk-" + "a" * 40
    store.upsert_chunks([chunk(text=secret)])
    original = store.export_all()[0]["document"]
    assert original == secret
    assert store.search("find secret", 1)
    assert store.redact_all() == 1
    redacted = store.export_all()[0]["document"]
    assert redacted != secret
    assert case.engine.calls == [
        {"text": ["search_document: " + secret], "model_name": MODEL, "allow_fallback": False},
        {"text": ["search_query: find secret"], "model_name": MODEL, "allow_fallback": False},
        {"text": ["search_document: " + str(redacted)], "model_name": MODEL, "allow_fallback": False},
    ]
    assert all(call.get("embeddings") is not None for call in case.native if call["operation"] == "upsert")
    assert all(
        call.get("query_embeddings") is not None and call.get("query_texts") is None
        for call in case.native
        if call["operation"] == "query"
    )
    case.observations.update(identity=identity.serialized(), stored_before=original, stored_after=redacted)


def test_unknown_dimensions_persist_reopen_and_peer_close(case: Case):
    store = case.store()
    assert store.collection is not None
    assert store.collection.metadata is not None
    assert store.collection.metadata[DIMENSIONS_METADATA_KEY] == 0
    assert store.search("empty") == [] and case.engine.calls == []
    store.upsert_chunks([chunk()])
    assert store.collection.metadata is not None
    assert store.collection.metadata[DIMENSIONS_METADATA_KEY] == 3
    peer = case.store()
    store.close()
    calls = len(case.engine.calls)
    with pytest.raises(RuntimeError, match="closed"):
        store.get_stats()
    with pytest.raises(RuntimeError, match="closed"):
        store.upsert_chunks([chunk()])
    with pytest.raises(RuntimeError, match="closed"):
        store.search("no native count")
    assert len(case.engine.calls) == calls
    peer.upsert_chunks([chunk("two")])
    assert peer.get_stats()["count"] == 2
    peer.close()
    reopened = case.store()
    assert reopened.get_stats()["count"] == 2
    case.engine.result = [[1.0, 2.0]]
    before = reopened.export_all()
    with pytest.raises(ProjectEmbeddingBindingError, match="dimensions"):
        reopened.upsert_chunks([chunk("three")])
    assert reopened.export_all() == before
    case.observations["reopened_records"] = before


@pytest.mark.parametrize("change", ["name", "repo", "endpoint", "document_prefix", "query_prefix", "dimensions"])
def test_same_dimension_identity_mismatch_rejected_without_mutation(case: Case, change: str):
    store = case.store()
    store.upsert_chunks([chunk()])
    before = store.export_all()
    old = profile(case)
    kwargs = {}
    if change == "name":
        old.name = "renamed-profile"
    elif change == "repo":
        old.repo = "other-model:latest"
    elif change == "endpoint":
        old.api_base = "http://127.0.0.1:11434"
    elif change == "dimensions":
        old.dimensions = 3
    else:
        kwargs[change] = "new-prefix: "
    with pytest.raises(ProjectEmbeddingBindingError, match="identity"):
        case.store(binding=case.binding(**kwargs))
    if change in {"name", "repo", "endpoint", "dimensions"}:
        with pytest.raises(ProjectEmbeddingBindingError, match="identity"):
            store.search("drift")
    assert store.collection is not None
    assert store.collection.count() == 1
    case.observations["records_before"] = before
    assert len(case.engine.calls) == 1


@pytest.mark.parametrize("populated", [False, True])
def test_explicit_open_rejects_legacy_without_metadata_even_when_empty(case: Case, populated: bool):
    client = chromadb.PersistentClient(path=str(case.root / "vectors"))
    legacy = client.create_collection("vault_notes", embedding_function=None)
    if populated:
        legacy.upsert(ids=["old"], documents=["legacy"], embeddings=[[1.0, 2.0, 3.0]])
    before = legacy.get(include=["documents"])
    with pytest.raises(ProjectEmbeddingBindingError, match="identity"):
        case.store()
    assert legacy.metadata is None and legacy.get(include=["documents"]) == before
    assert case.engine.calls == []
    cast(Callable[[], None], getattr(client, "close"))()


def test_implicit_refusal_and_other_identity_refusal_do_not_harm_bound_peer(case: Case):
    peer = case.store()
    peer.upsert_chunks([chunk()])
    with pytest.raises(ProjectEmbeddingBindingError, match="explicit"):
        VectorStore(str(case.root / "vectors"))
    with pytest.raises(ProjectEmbeddingBindingError, match="identity"):
        case.store(binding=case.binding(query_prefix="different"))
    peer.upsert_chunks([chunk("after")])
    assert len(peer.search("peer", 2)) == 2


@pytest.mark.parametrize(
    "bad",
    [
        [],
        [[1.0]],
        [[1.0, 2.0], [1.0]],
        [[True, 1.0, 2.0]],
        [[float("nan"), 1.0, 2.0]],
        [[float("inf"), 1.0, 2.0]],
        [[0.0, 0.0, 0.0]],
        [[1e100, 1.0, 2.0]],
        [["1", 2, 3]],
    ],
)
def test_invalid_vectors_fail_before_upsert_or_dimension_metadata(case: Case, bad: object):
    profile(case).dimensions = 3
    store = case.store()
    assert store.collection is not None
    before = dict(store.collection.metadata or {})
    case.engine.result = bad
    with pytest.raises(ProjectEmbeddingBindingError):
        store.upsert_chunks([chunk()])
    assert case.native == [] and store.get_stats()["count"] == 0
    assert store.collection.metadata == before


@pytest.mark.parametrize("failure", [EmbeddingModelUnavailableError(MODEL), RuntimeError("provider failure")])
def test_provider_failure_has_no_upsert_no_fallback(case: Case, failure: Exception):
    store = case.store()
    case.engine.failure = failure
    with pytest.raises(type(failure)):
        store.upsert_chunks([chunk()])
    assert store.get_stats()["count"] == 0 and case.native == []
    assert case.engine.calls[0]["allow_fallback"] is False


@pytest.mark.parametrize("change", ["provider", "role", "missing", "credentials", "query", "fragment"])
def test_unsupported_binding_rejected_before_loader_or_network(case: Case, change: str):
    value = profile(case)
    if change == "provider":
        value.provider = "mlx"
    elif change == "role":
        value.roles = ("coding",)
        value.role = "coding"
    elif change == "missing":
        assert case.engine.registry is not None
        case.engine.registry._models.clear()
    else:
        value.api_base = {
            "credentials": "http://user:secret@localhost:11434",
            "query": "http://localhost:11434?token=secret",
            "fragment": "http://localhost:11434#secret",
        }[change]
    with pytest.raises((ProjectEmbeddingBindingError, RuntimeError)):
        case.binding()
    assert not (case.root / "vectors").exists() and case.engine.calls == []


def test_mutable_registry_provider_endpoint_revalidated_before_every_model_call(case: Case):
    store = case.store()
    store.upsert_chunks([chunk()])
    assert case.engine.registry is not None
    case.engine.registry.providers["ollama"]["base_url"] = "http://other-host:11434"
    for action in (lambda: store.upsert_chunks([chunk("new")]), lambda: store.search("query"), store.redact_all):
        with pytest.raises(ProjectEmbeddingBindingError, match="identity"):
            action()
    assert len(case.engine.calls) == 1


def test_delete_and_purge_never_embed(case: Case):
    store = case.store()
    store.upsert_chunks([chunk(), chunk("two", source="second.md")])
    calls = len(case.engine.calls)
    store.delete_file_chunks_strict("note.md")
    assert store.clear() == 1
    assert len(case.engine.calls) == calls and store.get_stats()["count"] == 0


def test_native_upsert_failure_keeps_unknown_metadata_and_metadata_failure_is_uncertain(
    case: Case, monkeypatch: pytest.MonkeyPatch
):
    store = case.store()
    assert store.collection is not None
    before = dict(store.collection.metadata or {})
    original = Collection.upsert

    def fail(*args: object, **kwargs: object):
        raise RuntimeError("native write failed")

    monkeypatch.setattr(Collection, "upsert", fail)
    with pytest.raises(RuntimeError, match="native write"):
        store.upsert_chunks([chunk()])
    assert store.collection.metadata == before and store.collection.count() == 0
    monkeypatch.setattr(Collection, "upsert", original)
    monkeypatch.setattr(Collection, "modify", fail)
    with pytest.raises(RuntimeError, match="native write"):
        store.upsert_chunks([chunk()])
    assert store.collection.count() == 1 and store.collection.metadata == before
    with pytest.raises(ProjectEmbeddingBindingError, match="uncertain"):
        store.search("blocked")
    with pytest.raises(ProjectEmbeddingBindingError, match="uncertain"):
        case.store()


def test_persistent_failure_never_falls_back(case: Case, monkeypatch: pytest.MonkeyPatch):
    def fail(*args: object, **kwargs: object):
        raise KeyError("owned persistent failure")

    def forbidden(*args: object, **kwargs: object):
        pytest.fail("in-memory fallback called")

    monkeypatch.setattr(chromadb, "PersistentClient", fail)
    monkeypatch.setattr(chromadb, "Client", forbidden)
    with pytest.raises(KeyError):
        case.store()
    assert case.engine.calls == []


@pytest.mark.parametrize("method", ["index_file", "index_project", "sync"])
def test_rag_failed_embedding_preserves_rows_manifest_and_retryability(case: Case, method: str):
    project = case.root / "project"
    project.mkdir()
    source = project / "notes.md"
    source.write_text("# Old section\nold content\n\n# Another section\nold trailing content\n")
    store = case.store()
    indexer = RAGIndexer(str(project), vector_store=store)
    assert indexer.index_project() > 0
    before = store.export_all()
    manifest = Path(store.persist_directory) / "rag-manifest.json"
    saved_manifest = manifest.read_bytes()
    source.write_text("# New section\nnew replacement content\n")
    canonical = source.read_bytes()
    action = (lambda: indexer.index_file("notes.md")) if method == "index_file" else getattr(indexer, method)
    case.engine.failure = EmbeddingModelUnavailableError(MODEL)
    with pytest.raises(EmbeddingModelUnavailableError):
        action()
    failed_rows = store.export_all()
    case.observations.update(
        records_before=before,
        records_after_failure=failed_rows,
        manifest_before_sha256=hashlib.sha256(saved_manifest).hexdigest(),
        manifest_after_failure_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    assert failed_rows == before and manifest.read_bytes() == saved_manifest
    assert source.read_bytes() == canonical
    case.engine.failure = None
    assert action() > 0
    after = store.export_all()
    assert after and all("old " not in str(row["document"]) for row in after)
    assert source.read_bytes() == canonical
    calls = len(case.engine.calls)
    assert indexer.index_project() == 0 and len(case.engine.calls) == calls
    case.observations.update(
        records_before=before, records_after=after, canonical_sha256=hashlib.sha256(canonical).hexdigest()
    )


def test_real_rag_index_search_change_delete_preserves_other_project(case: Case):
    project = case.root / "project"
    project.mkdir()
    source = project / "notes.md"
    source.write_text("# Alpha\noriginal owned content\n")
    other = case.store(case.root / "other-vectors")
    other.upsert_chunks([chunk("other", "untouched other project")])
    other_before = other.export_all()
    store = case.store()
    indexer = RAGIndexer(str(project), vector_store=store)
    assert indexer.index_project() > 0
    canonical = source.read_bytes()
    assert indexer.search("content", n_results=1, mode="semantic")
    assert source.read_bytes() == canonical
    source.write_text("# Beta\nchanged owned content\n")
    changed = source.read_bytes()
    assert indexer.sync() > 0
    assert source.read_bytes() == changed and other.export_all() == other_before
    source.unlink()
    calls = len(case.engine.calls)
    assert indexer.sync() == 0 and store.get_stats()["count"] == 0
    assert len(case.engine.calls) == calls and other.export_all() == other_before


@pytest.mark.parametrize("operation", ["file", "parent-subdir", "symlink-index", "symlink-sync"])
def test_outside_sources_never_read_embed_or_store(case: Case, monkeypatch: pytest.MonkeyPatch, operation: str):
    project = case.root / "project"
    project.mkdir()
    sentinel = case.root / "outside.md"
    sentinel.write_text("outside private sentinel")
    digest = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    store = case.store()
    indexer = RAGIndexer(str(project), vector_store=store)
    if operation.startswith("symlink"):
        (project / "link.md").symlink_to(sentinel)
    original_open = __import__("builtins").open

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).resolve() == sentinel:
            pytest.fail("outside sentinel read")
        return original_open(file, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr("builtins.open", guarded_open)
        with pytest.raises(ValueError, match="outside"):
            if operation == "file":
                indexer.index_file(str(sentinel))
            elif operation == "parent-subdir":
                indexer.index_project([".."])
            elif operation == "symlink-index":
                indexer.index_project()
            else:
                indexer.sync()
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == digest
    assert case.engine.calls == [] and store.get_stats()["count"] == 0


def test_explicit_factory_failure_surfaces_but_legacy_fallback_remains(case: Case, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.dependencies import _attach_project_rag_indexer
    from antigravity_k.engine import vector_store as module
    from antigravity_k.engine.orchestrator import OrchestratorAgent

    def fail(*args: object, **kwargs: object):
        raise RuntimeError("owned vector constructor failure")

    monkeypatch.setattr(module, "VectorStore", fail)
    project = case.root / "allowed-project"
    project.mkdir()
    monkeypatch.setenv("AGK_RAG_ALLOWED_ROOT", str(case.root))
    orchestrator = cast(OrchestratorAgent, cast(object, SimpleNamespace()))
    with pytest.raises(RuntimeError, match="constructor failure"):
        _attach_project_rag_indexer(orchestrator, str(project), embedding_binding=case.binding())
    assert not hasattr(orchestrator, "_rag_indexer")
    _attach_project_rag_indexer(orchestrator, str(case.root))
    assert getattr(orchestrator, "_rag_indexer").vector_store is None


def test_bound_sync_validates_edits_before_deleting_removed_sources(case: Case):
    project = case.root / "project"
    project.mkdir()
    first = project / "first.md"
    removed = project / "removed.md"
    first.write_text("# First\nold first\n")
    removed.write_text("# Removed\nold removed\n")
    store = case.store()
    indexer = RAGIndexer(str(project), store)
    assert indexer.index_project() == 2
    before = store.export_all()
    manifest = Path(store.persist_directory) / "rag-manifest.json"
    old_manifest = manifest.read_bytes()
    first.write_text("# First\nnew first\n")
    removed.unlink()
    case.engine.failure = EmbeddingModelUnavailableError(MODEL)
    with pytest.raises(EmbeddingModelUnavailableError):
        indexer.sync()
    assert store.export_all() == before and manifest.read_bytes() == old_manifest
    case.engine.failure = None
    assert indexer.sync() == 1
    rows = store.export_all()
    assert len(rows) == 1 and "new first" in str(rows[0]["document"])


def test_unknown_dimension_stays_bound_after_purge_and_query_validation(case: Case):
    store = case.store()
    store.upsert_chunks([chunk()])
    case.engine.result = [[1.0, 2.0]]
    queries = len([row for row in case.native if row["operation"] == "query"])
    with pytest.raises(ProjectEmbeddingBindingError, match="dimensions"):
        store.search("invalid query dimensions")
    assert len([row for row in case.native if row["operation"] == "query"]) == queries
    assert store.clear() == 1
    store.close()
    reopened = case.store()
    with pytest.raises(ProjectEmbeddingBindingError, match="dimensions"):
        reopened.upsert_chunks([chunk()])
    assert reopened.get_stats()["count"] == 0


def test_unknown_first_batch_dimension_consistency_and_float32_norm(case: Case):
    store = case.store()
    for rows in ([[1.0, 2.0], [1.0, 2.0, 3.0]], [[1e-100, 0.0, 0.0], [1e-100, 0.0, 0.0]]):
        case.engine.result = rows
        with pytest.raises(ProjectEmbeddingBindingError):
            store.upsert_chunks([chunk(), chunk("two")])
    assert case.native == [] and store.get_stats()["count"] == 0


def test_persisted_vector_dimension_disagreement_rejects_reopen(case: Case):
    store = case.store()
    store.upsert_chunks([chunk()])
    assert store.collection is not None
    metadata = dict(store.collection.metadata or {})
    metadata[DIMENSIONS_METADATA_KEY] = 2
    store.collection.modify(metadata=cast(dict[str, MetadataValue], metadata))
    with pytest.raises(ProjectEmbeddingBindingError, match="Persisted"):
        case.store()
    assert len(case.engine.calls) == 1


def test_delete_native_failure_does_not_advance_bound_manifest(case: Case, monkeypatch: pytest.MonkeyPatch):
    project = case.root / "project"
    project.mkdir()
    source = project / "notes.md"
    source.write_text("# Delete\nthis record\n")
    store = case.store()
    indexer = RAGIndexer(str(project), store)
    assert indexer.index_project() == 1
    manifest = Path(store.persist_directory) / "rag-manifest.json"
    before = manifest.read_bytes()
    source.unlink()
    original = Collection.delete

    def fail(*args: object, **kwargs: object):
        raise RuntimeError("native delete failed")

    monkeypatch.setattr(Collection, "delete", fail)
    with pytest.raises(RuntimeError, match="native delete"):
        indexer.sync()
    assert manifest.read_bytes() == before and store.get_stats()["count"] == 1
    monkeypatch.setattr(Collection, "delete", original)
    assert indexer.sync() == 0 and store.get_stats()["count"] == 0


def test_legacy_unbound_constructor_never_uses_default_embedding(case: Case, monkeypatch: pytest.MonkeyPatch):
    """r29: the unbound constructor no longer falls back to Chroma's default (ONNX) embedding."""
    from antigravity_k.engine.embedding_guard import EmbeddingNotReadyError

    used: list[str] = []
    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", lambda self, input: used.append("default") or [])
    with VectorStore(str(case.root / "legacy-default")) as legacy:
        with pytest.raises(EmbeddingNotReadyError):
            legacy.upsert_chunks([chunk()])
        with pytest.raises(EmbeddingNotReadyError):
            legacy.search("legacy", 1)
    assert used == [] and case.engine.calls == []
