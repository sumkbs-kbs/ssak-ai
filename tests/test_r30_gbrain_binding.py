"""r30 P1: gbrain vector memory through an explicit embedding binding (fake transport, no model)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

pytest.importorskip("chromadb")

from antigravity_k.engine.embedding_guard import EmbeddingNotReadyError
from antigravity_k.engine.gbrain import GBrain


class _Identity:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def serialized(self) -> str:
        return f'{{"fake":"{self.tag}"}}'


class FakeBinding:
    """Deterministic bag-of-words embedding; counts calls (fake transport, not a real model call)."""

    DIM = 16

    def __init__(self, tag: str = "v1") -> None:
        self.identity = _Identity(tag)
        self.calls = 0
        self.fail = False

    def embed(self, texts: list[str], *, query: bool = False, observed_dimensions: int = 0) -> list[list[float]]:
        _ = (query, observed_dimensions)
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic embed failure")
        out = []
        for text in texts:
            vec = [0.0] * self.DIM
            for word in text.lower().split():
                vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
            vec[0] += 0.01
            norm = math.sqrt(sum(v * v for v in vec))
            out.append([v / norm for v in vec])
        return out


def _brain(tmp_path: Path, binding: FakeBinding) -> GBrain:
    return GBrain(storage_dir=str(tmp_path / "gb"), embedding_binding=binding)  # type: ignore[arg-type]


def test_semantic_search_returns_bound_results(tmp_path: Path) -> None:
    b = FakeBinding()
    g = _brain(tmp_path, b)
    g.add_node("n1", "concept", "apple banana fruit salad")
    g.add_node("n2", "concept", "kubernetes cluster deployment")
    hits = g.search_semantic("banana fruit", limit=1)
    assert [h["id"] for h in hits] == ["n1"]
    assert b.calls >= 3
    g.close()


def test_store_failure_is_atomic(tmp_path: Path) -> None:
    b = FakeBinding()
    g = _brain(tmp_path, b)
    g.add_node("n1", "concept", "alpha beta")
    b.fail = True
    with pytest.raises(RuntimeError):
        g.add_node("n2", "concept", "gamma delta")
    b.fail = False
    assert not g.graph.has_node("n2")
    assert g.collection.count() == 1
    g.close()


def test_metadata_sanitized_to_scalars(tmp_path: Path) -> None:
    g = _brain(tmp_path, FakeBinding())
    g.add_node("n1", "concept", "alpha", metadata={"ok": "x", "nested": {"a": 1}, "lst": [1]})
    rec = g.collection.get(ids=["n1"], include=["metadatas"])
    meta = rec["metadatas"][0]
    assert meta["ok"] == "x" and meta["label"] == "concept"
    assert "nested" not in meta and "lst" not in meta
    g.close()


def test_restart_persistence_and_identity_guard(tmp_path: Path) -> None:
    g = _brain(tmp_path, FakeBinding())
    g.add_node("n1", "concept", "persistent memory fact")
    g.close()
    g2 = _brain(tmp_path, FakeBinding())
    assert [h["id"] for h in g2.search_semantic("persistent memory", limit=1)] == ["n1"]
    g2.close()
    g3 = _brain(tmp_path, FakeBinding(tag="other"))
    assert g3.vector_not_ready_reason is not None
    with pytest.raises(EmbeddingNotReadyError):
        g3.search_semantic("persistent memory")
    g3.close()


def test_no_binding_stays_not_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGK_RAG_EMBEDDING", raising=False)
    g = GBrain(storage_dir=str(tmp_path / "gb"))
    assert g.vector_not_ready_reason is not None
    with pytest.raises(EmbeddingNotReadyError):
        g.search_semantic("anything")
    g.close()


def test_graphify_semantic_uses_binding_or_reports_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.engine.optimizers import graphify_builder as gb

    class _N:
        def __init__(self, name: str, file: str) -> None:
            self.kind, self.name, self.file = "function", name, file

    graph = type("G", (), {"nodes": [_N("parse_invoice totals", "billing.py"), _N("render chart", "ui.py")]})()
    monkeypatch.setattr(
        "antigravity_k.engine.project_embedding_binding.configured_embedding_binding", lambda *a, **k: None
    )
    assert gb.embedding_retrieve(graph, "invoice") == []  # type: ignore[arg-type]
    assert gb.last_retrieval_mode.startswith("keyword")
    fake = FakeBinding()
    monkeypatch.setattr(
        "antigravity_k.engine.project_embedding_binding.configured_embedding_binding", lambda *a, **k: fake
    )
    hits = gb.embedding_retrieve(graph, "parse_invoice totals", top_k=1)  # type: ignore[arg-type]
    assert hits and hits[0].file == "billing.py"
    assert gb.last_retrieval_mode.startswith("semantic")
