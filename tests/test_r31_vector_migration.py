"""r31: explicit legacy-collection migration, startup setup-pending, raw-text memory.

Synthetic directories only (tmp_path). Embeddings use the production binding over a mocked
Ollama transport (tests/_legacy_fake_embedding.build_fake_binding) — no model is contacted.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.engine import vector_migration as vm
from antigravity_k.engine.project_embedding_binding import (
    IDENTITY_METADATA_KEY,
    RAG_ALLOWED_ROOT_ENV,
    ProjectEmbeddingBindingError,
)
from tests._legacy_fake_embedding import DIM, build_fake_binding

COLLECTION = "vault_notes"


def _plant_legacy(persist: Path, n: int) -> list[str]:
    """A pre-binding collection: no identity metadata, 384-dim vectors (old implicit default)."""
    import chromadb

    client = chromadb.PersistentClient(path=str(persist))
    try:
        col = client.get_or_create_collection(name=COLLECTION, embedding_function=None)
        ids = [f"note-{i}.md::0" for i in range(n)]
        if n:
            col.upsert(
                ids=ids,
                documents=[f"synthetic legacy note number {i} topic{i} alpha{i}" for i in range(n)],
                metadatas=[{"file_path": f"note-{i}.md", "chunk": 0, "title": f"t{i}"} for i in range(n)],
                embeddings=[[float((i + j) % 7) / 7.0 + 0.01 for j in range(384)] for i in range(n)],
            )
        return ids
    finally:
        client.close()


@pytest.fixture
def binding(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    return build_fake_binding(monkeypatch)


def test_inspect_distinguishes_empty_and_populated_legacy_and_keeps_original(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    full, empty = tmp_path / "full", tmp_path / "empty"
    _ = _plant_legacy(full, 3)
    _ = _plant_legacy(empty, 0)
    before = vm.tree_sha256(full)
    assert vm.inspect_collection(full, COLLECTION, binding) == "legacy_with_data"
    assert vm.inspect_collection(empty, COLLECTION, binding) == "legacy_empty"
    assert vm.inspect_collection(tmp_path / "none", COLLECTION, binding) == "absent"
    assert vm.tree_sha256(full) == before


def test_bound_store_still_refuses_legacy_collection(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.engine.vector_store import VectorStore

    persist = tmp_path / "chroma"
    _ = _plant_legacy(persist, 2)
    before = vm.tree_sha256(persist)
    with pytest.raises(ProjectEmbeddingBindingError, match="no automatic migration"):
        _ = VectorStore(str(persist), collection_name=COLLECTION, embedding_binding=binding)
    assert vm.inspect_collection(persist, COLLECTION, binding) == "legacy_with_data"
    _ = before


def test_migration_preserves_original_reembeds_and_works_after_restart(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.engine.vector_store import VectorStore

    persist = tmp_path / "chroma"
    ids = _plant_legacy(persist, 5)
    original_hash = vm.tree_sha256(persist)

    report = vm.migrate_legacy_collection(persist, COLLECTION, binding)

    assert report.outcome == "migrated", report
    assert report.state_before == "legacy_with_data"
    assert report.legacy_count == report.migrated_count == len(ids)
    assert report.dimensions == DIM
    assert report.model == "nomic-embed-text:latest"
    assert report.checks and all(report.checks.values()), report.checks
    preserved = Path(report.preserved_as)
    assert preserved.is_dir() and vm.tree_sha256(preserved) == original_hash  # original kept byte-for-byte
    assert vm.inspect_collection(persist, COLLECTION, binding) == "bound_current"

    # "Restart": a fresh bound store opens the switched directory, searches and records new experience.
    store = VectorStore(str(persist), collection_name=COLLECTION, embedding_binding=binding)
    try:
        hits = store.search("topic3 alpha3", n_results=1)
        assert hits and "topic3" in str(hits[0])
        store.upsert_chunks([{"id": "exp-1::0", "text": "new experience gamma", "metadata": {"file_path": "exp-1"}}])
    finally:
        store.close()
    again = VectorStore(str(persist), collection_name=COLLECTION, embedding_binding=binding)
    try:
        assert "gamma" in str(again.search("new experience gamma", n_results=1))
    finally:
        again.close()


def test_empty_legacy_collection_migrates_without_reembedding(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    persist = tmp_path / "chroma"
    _ = _plant_legacy(persist, 0)
    report = vm.migrate_legacy_collection(persist, COLLECTION, binding)
    assert report.outcome == "migrated", report
    assert report.state_before == "legacy_empty"
    assert report.legacy_count == report.migrated_count == 0
    assert report.dimensions == 0
    assert vm.inspect_collection(persist, COLLECTION, binding) == "bound_current"


def test_abort_keeps_original_and_retry_succeeds_then_idempotent(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    persist = tmp_path / "chroma"
    _ = _plant_legacy(persist, 4)
    original_hash = vm.tree_sha256(persist)

    aborted = vm.migrate_legacy_collection(persist, COLLECTION, binding, abort_after_staging=lambda: True)
    assert aborted.outcome == "failed" and "aborted" in aborted.detail
    assert vm.tree_sha256(persist) == original_hash  # original still in place, unchanged
    assert Path(aborted.failed_staging).is_dir()  # incomplete staging set aside, not deleted

    retried = vm.migrate_legacy_collection(persist, COLLECTION, binding)
    assert retried.outcome == "migrated", retried
    assert vm.tree_sha256(Path(retried.preserved_as)) == original_hash

    siblings = sorted(p.name for p in tmp_path.iterdir())
    third = vm.migrate_legacy_collection(persist, COLLECTION, binding)
    assert third.outcome == "already_migrated"
    assert sorted(p.name for p in tmp_path.iterdir()) == siblings


def test_unapproved_model_is_refused_before_any_write(tmp_path: Path) -> None:
    persist = tmp_path / "chroma"
    _ = _plant_legacy(persist, 1)
    before = sorted(p.name for p in tmp_path.iterdir())
    other = SimpleNamespace(identity=SimpleNamespace(wire_model="other-embed:latest"))
    with pytest.raises(vm.VectorMigrationError, match="not approved"):
        _ = vm.migrate_legacy_collection(persist, COLLECTION, other)  # type: ignore[arg-type]
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_other_identity_is_refused_not_restamped(tmp_path: Path, binding) -> None:  # type: ignore[no-untyped-def]
    import chromadb

    persist = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(persist))
    try:
        _ = client.create_collection(
            name=COLLECTION, embedding_function=None, metadata={IDENTITY_METADATA_KEY: '{"other":1}', "dims": 0}
        )
    finally:
        client.close()
    before = vm.tree_sha256(persist)
    report = vm.migrate_legacy_collection(persist, COLLECTION, binding)
    assert report.outcome == "refused" and report.state_before == "bound_other_identity"
    assert vm.tree_sha256(persist) == before


def test_vector_not_ready_does_not_block_raw_text_vault(
    tmp_path: Path, binding, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.api import dependencies
    from antigravity_k.engine import project_embedding_binding as peb
    from antigravity_k.engine.project_memory_paths import project_vault_dir

    project = tmp_path / "proj"
    project.mkdir()
    _ = _plant_legacy(project_vault_dir(project) / ".chroma", 2)
    monkeypatch.setattr(peb, "configured_embedding_binding_or_none", lambda: binding)
    vault = dependencies._build_project_vault(str(project))
    assert vault is not None
    assert vault.sync_rag is False  # legacy vectors refused -> explicit not-ready, no implicit embedding
    vault.write_note("raw.md", {"title": "raw"}, "raw text memory survives")
    _meta, body = vault.read_note("raw.md")
    assert "raw text memory survives" in body
    assert vault.search_notes("survives")


class _Orch:
    pass


def test_implicit_default_project_is_setup_pending_not_ready(
    tmp_path: Path, binding, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.api import dependencies
    from antigravity_k.engine import project_embedding_binding as peb

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    cwd_project = tmp_path / "cwd"
    cwd_project.mkdir()
    monkeypatch.setenv(RAG_ALLOWED_ROOT_ENV, str(allowed))
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "1")
    monkeypatch.setattr(peb, "configured_embedding_binding", lambda *a, **k: binding)
    orch = _Orch()
    dependencies._attach_rag_or_mark_setup_pending(orch, "default", str(cwd_project))  # type: ignore[arg-type]
    assert getattr(orch, "_rag_indexer") is None
    assert getattr(orch, "_project_rag_unavailable_reason") == "initial_setup_pending"
    assert dependencies.project_rag_state("default") == "initial_setup_pending"


def test_explicit_project_outside_allowed_root_is_still_rejected(
    tmp_path: Path, binding, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.api import dependencies
    from antigravity_k.engine import project_embedding_binding as peb

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv(RAG_ALLOWED_ROOT_ENV, str(allowed))
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "1")
    monkeypatch.setattr(peb, "configured_embedding_binding", lambda *a, **k: binding)
    with pytest.raises(ProjectEmbeddingBindingError, match="outside the allowed root"):
        dependencies._attach_rag_or_mark_setup_pending(_Orch(), "proj_chosen", str(outside))  # type: ignore[arg-type]
    assert dependencies.project_rag_state("proj_chosen") != "attached"


def test_explicit_project_inside_allowed_root_attaches(
    tmp_path: Path, binding, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from antigravity_k.api import dependencies
    from antigravity_k.engine import project_embedding_binding as peb

    allowed = tmp_path / "allowed"
    inside = allowed / "p"
    inside.mkdir(parents=True)
    monkeypatch.setenv(RAG_ALLOWED_ROOT_ENV, str(allowed))
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "1")
    monkeypatch.setattr(peb, "configured_embedding_binding", lambda *a, **k: binding)
    orch = _Orch()
    dependencies._attach_rag_or_mark_setup_pending(orch, "proj_in", str(inside))  # type: ignore[arg-type]
    assert getattr(orch, "_rag_indexer") is not None
    assert dependencies.project_rag_state("proj_in") == "attached"


def test_embedding_status_never_reports_ready_while_setup_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.api import dependencies
    from antigravity_k.api.routes import vault_api
    from antigravity_k.engine import embedding_readiness

    monkeypatch.setenv("AGK_RAG_EMBEDDING", "ollama")
    from antigravity_k.engine import model_registry

    class _Reg:
        def get_default(self, role: str) -> object:
            return SimpleNamespace(name="nomic-embed-text:latest")

    monkeypatch.setattr(model_registry, "ModelRegistry", _Reg)
    monkeypatch.setattr(embedding_readiness, "check_embedding_readiness", lambda *a, **k: {"state": "ready"})
    monkeypatch.setattr(dependencies, "project_rag_state", lambda project_id=None: "initial_setup_pending")
    pending = vault_api.vault_embedding_status()
    assert pending["embedding_verified"] is True
    assert pending["app_rag_ready"] is False
    assert pending["project_rag_state"] == "initial_setup_pending"
    monkeypatch.setattr(dependencies, "project_rag_state", lambda project_id=None: "attached")
    assert vault_api.vault_embedding_status()["app_rag_ready"] is True
