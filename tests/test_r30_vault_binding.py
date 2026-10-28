"""r30 P1: vault past_memory store uses the approved binding; empty legacy unbound collections adopt it (fake transport)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("chromadb")

from typing_extensions import override

from antigravity_k.engine import project_embedding_binding as peb
from antigravity_k.engine.embeddings import EmbeddingEngine
from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.project_embedding_binding import (
    ProjectEmbeddingBindingError,
)
from antigravity_k.engine.vector_store import VectorStore


class FakeEngine(EmbeddingEngine):
    def __init__(self) -> None:
        super().__init__(registry=ModelRegistry())
        self.calls = 0

    @override
    def embed(self, text: str | list[str], model_name: str, *, allow_fallback: bool = True) -> list[list[float]]:
        self.calls += 1
        texts = [text] if isinstance(text, str) else text
        return [[1.0, float(len(t) % 7 + 1), 0.5] for t in texts]


def _binding() -> object:
    from tests.test_r30_gbrain_binding import FakeBinding

    class _B(FakeBinding):
        def revalidate(self) -> None:
            return None

    return _B()


def test_legacy_empty_unbound_collection_stays_rejected(tmp_path: Path) -> None:
    """Contract (identity tests): no silent adoption; VaultEngine callers then fall back to sync_rag=False."""
    VectorStore(str(tmp_path), collection_name="vault_notes").close()
    with pytest.raises(ProjectEmbeddingBindingError):
        VectorStore(str(tmp_path), collection_name="vault_notes", embedding_binding=_binding())  # type: ignore[arg-type]


def test_helper_returns_none_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGK_RAG_EMBEDDING", raising=False)
    assert peb.configured_embedding_binding_or_none() is None


def test_helper_returns_none_on_misconfig(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise ProjectEmbeddingBindingError("synthetic misconfig")

    monkeypatch.setattr(peb, "configured_embedding_binding", boom)
    assert peb.configured_embedding_binding_or_none() is None


def test_vault_engine_passes_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.engine import vault as vault_mod

    b = _binding()
    monkeypatch.setattr(peb, "configured_embedding_binding_or_none", lambda: b)
    engine = vault_mod.VaultEngine(vault_path=str(tmp_path / "vault"), sync_rag=True)
    assert engine.vector_store.embedding_binding is b
