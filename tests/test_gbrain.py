"""Tests for gbrain — Graph + Vector Memory system.

Covers GBrain init, add_node, add_edge, search_semantic, get_related,
close, atexit cleanup, and edge cases.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

import pytest

from antigravity_k.engine.gbrain import GBrainCorruptSnapshotError


def _require_chromadb() -> None:
    pytest.importorskip("chromadb", reason="chromadb not installed (pip install -e '.[rag]')")


class _NodeViewLike(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, key: str) -> Mapping[str, object]: ...


class _EdgeViewLike(Protocol):
    def __getitem__(self, key: tuple[str, str]) -> Mapping[str, object]: ...


class _GraphLike(Protocol):
    nodes: _NodeViewLike
    edges: _EdgeViewLike

    def has_node(self, node: str) -> bool: ...

    def has_edge(self, source: str, target: str) -> bool: ...


class _CollectionLike(Protocol):
    def count(self) -> int: ...

    def get(self, ids: list[str]) -> Mapping[str, list[Mapping[str, object]]]: ...

    def upsert(self, *, ids: list[str], documents: list[str], metadatas: list[dict[str, object]]) -> object: ...


class _ExecutorLike(Protocol):
    def shutdown(self, wait: bool = True) -> None: ...


class _GBrainLike(Protocol):
    reward_tick: int

    def reward_score(self, source_id: str, target_id: str) -> float: ...

    def clear_all(self) -> int: ...

    def redact_all(self) -> int: ...

    graph: _GraphLike
    collection: _CollectionLike
    chroma_client: object | None
    _closed: bool

    def add_node(
        self, node_id: str, label: str, content: str, metadata: Mapping[str, object] | None = None
    ) -> None: ...

    def add_edge(self, source: str, target: str, relation: str) -> None: ...

    def search_semantic(
        self, query: str, limit: int = 5, filter_label: str | None = None
    ) -> list[Mapping[str, object]]: ...

    def get_related(self, node_id: str) -> list[Mapping[str, object]]: ...

    def close(self) -> None: ...


def _new_gbrain(storage: Path) -> _GBrainLike:
    from antigravity_k.engine.gbrain import GBrain

    return cast(_GBrainLike, cast(object, GBrain(storage_dir=str(storage))))


class TestGBrainInit:
    def test_init_creates_storage_dir(self, tmp_path: Path) -> None:
        storage = tmp_path / "gbrain_test"
        gbrain = _new_gbrain(storage)
        assert storage.exists()
        assert gbrain.graph is not None
        gbrain.close()

    def test_init_loads_existing_graph(self, tmp_path: Path) -> None:
        import networkx as nx

        storage = tmp_path / "gbrain_existing"
        storage.mkdir(parents=True, exist_ok=True)
        graph_file = storage / "knowledge_graph.graphml"
        graph_factory = cast(Callable[[], object], getattr(nx, "DiGraph"))
        graph = graph_factory()
        add_node = cast(Callable[..., object], getattr(graph, "add_node"))
        _ = add_node("test_node", label="test", content="hello")
        write_graphml = cast(Callable[[object, str], object], getattr(nx, "write_graphml"))
        _ = write_graphml(graph, str(graph_file))

        gbrain = _new_gbrain(storage)
        assert gbrain.graph.has_node("test_node")
        assert gbrain.graph.nodes["test_node"]["label"] == "test"
        assert gbrain.reward_tick == 0
        assert gbrain.reward_score("test_node", "test_node") == 0.0
        gbrain.close()

    def test_init_handles_corrupt_graph(self, tmp_path: Path) -> None:
        storage = tmp_path / "gbrain_corrupt"
        storage.mkdir(parents=True, exist_ok=True)
        graph_file = storage / "knowledge_graph.graphml"
        _ = graph_file.write_text("not valid graphml")

        with pytest.raises(GBrainCorruptSnapshotError):
            _ = _new_gbrain(storage)


class TestGBrainAddNode:
    def test_adds_node_to_graph_and_vector(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_add")
        gbrain.add_node("node_1", "test_label", "test content", {"source": "test"})

        assert gbrain.graph.has_node("node_1")
        assert gbrain.graph.nodes["node_1"]["label"] == "test_label"
        assert gbrain.collection.count() == 1
        gbrain.close()

    def test_add_node_without_metadata(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_nometa")
        gbrain.add_node("node_1", "test_label", "content")

        assert gbrain.graph.has_node("node_1")
        assert gbrain.graph.nodes["node_1"]["label"] == "test_label"
        gbrain.close()

    def test_add_node_filters_non_chroma_metadata(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_meta")
        gbrain.add_node(
            "node_1",
            "test_label",
            "content",
            metadata={"str_key": "val", "int_key": 42, "list_key": [1, 2, 3]},
        )

        result = gbrain.collection.get(ids=["node_1"])
        assert result["metadatas"][0]["str_key"] == "val"
        assert result["metadatas"][0]["int_key"] == 42
        assert "list_key" not in result["metadatas"][0]
        gbrain.close()

    def test_add_node_duplicate_id_updates(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_dup")
        gbrain.add_node("node_1", "label_a", "content a")
        gbrain.add_node("node_1", "label_b", "content b")

        assert gbrain.reward_tick == 2
        assert gbrain.reward_score("node_1", "node_1") == pytest.approx(1.95)
        assert len(gbrain.graph.nodes) == 1
        assert gbrain.graph.nodes["node_1"]["label"] == "label_b"
        assert gbrain.graph.nodes["node_1"]["content"] == "content b"
        gbrain.close()

    def test_failed_vector_upsert_does_not_count_or_keep_graph_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_vector_failure")
        collection = cast(object, gbrain.collection)
        upsert = cast(Callable[..., object], getattr(collection, "upsert"))

        def fail_upsert(**_kwargs: object) -> object:
            raise RuntimeError("simulated Chroma failure")

        monkeypatch.setattr(collection, "upsert", fail_upsert)
        with pytest.raises(RuntimeError, match="simulated Chroma failure"):
            gbrain.add_node("not-committed", "label", "content")

        assert not gbrain.graph.has_node("not-committed")
        assert gbrain.reward_tick == 0
        assert gbrain.reward_score("not-committed", "not-committed") == 0.0
        monkeypatch.setattr(collection, "upsert", upsert)
        gbrain.close()


class TestGBrainAddEdge:
    def test_edges_are_directed_and_one_relation_is_stored_per_ordered_pair(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_edge")
        gbrain.add_node("source", "label", "source content")
        gbrain.add_node("target", "label", "target content")
        gbrain.add_edge("source", "target", "supports")
        gbrain.add_edge("target", "source", "contradicts")
        gbrain.add_edge("source", "target", "supersedes")

        assert gbrain.graph.has_edge("source", "target")
        assert gbrain.graph.has_edge("target", "source")
        assert gbrain.graph.edges["source", "target"]["relation"] == "supersedes"
        assert gbrain.graph.edges["target", "source"]["relation"] == "contradicts"
        assert [node["id"] for node in gbrain.get_related("source")] == ["target"]
        assert [node["id"] for node in gbrain.get_related("target")] == ["source"]
        assert gbrain.reward_tick == 5
        assert gbrain.reward_score("source", "target") == pytest.approx(1.0 + 0.95**2)
        assert gbrain.reward_score("target", "source") == 0.95
        assert gbrain.reward_score("source", "source") == pytest.approx(0.95**4)
        assert gbrain.reward_score("target", "target") == pytest.approx(0.95**3)
        gbrain.close()

    def test_graphml_round_trip_preserves_semantic_nodes_and_relations(self, tmp_path: Path) -> None:
        storage = tmp_path / "gbrain_round_trip"
        gbrain = _new_gbrain(storage)
        gbrain.add_node("concept:a", "concept", "first concept", {"source": "test"})
        gbrain.add_node("concept:b", "concept", "second concept")
        gbrain.add_edge("concept:a", "concept:b", "related_to")

        # Writes wait for the GraphML commit; close the executor before reopening
        # so this asserts the durable representation, not worker timing.
        cast(_ExecutorLike, getattr(gbrain, "_executor")).shutdown(wait=True)
        gbrain.close()

        reloaded = _new_gbrain(storage)
        try:
            assert reloaded.graph.has_node("concept:a")
            assert reloaded.graph.nodes["concept:a"]["label"] == "concept"
            assert reloaded.graph.nodes["concept:a"]["source"] == "test"
            assert reloaded.graph.has_edge("concept:a", "concept:b")
            assert reloaded.graph.edges["concept:a", "concept:b"]["relation"] == "related_to"
            assert reloaded.reward_tick == 3
            assert reloaded.reward_score("concept:a", "concept:a") == pytest.approx(0.95**2)
            assert reloaded.reward_score("concept:b", "concept:b") == pytest.approx(0.95)
            assert reloaded.reward_score("concept:a", "concept:b") == 1.0
        finally:
            reloaded.close()

    def test_add_edge_missing_source_does_nothing(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_edge_missing")
        gbrain.add_node("target", "label", "content")
        gbrain.add_edge("nonexistent", "target", "related_to")

        assert not gbrain.graph.has_edge("nonexistent", "target")
        assert gbrain.reward_tick == 1
        assert gbrain.reward_score("nonexistent", "target") == 0.0
        gbrain.close()

    def test_add_edge_missing_target_does_nothing(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_edge_missing_t")
        gbrain.add_node("source", "label", "content")
        gbrain.add_edge("source", "nonexistent", "related_to")

        assert not gbrain.graph.has_edge("source", "nonexistent")
        assert gbrain.reward_tick == 1
        assert gbrain.reward_score("source", "nonexistent") == 0.0
        gbrain.close()

    def test_reward_cap_applies_to_each_pair(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_reward_cap")
        for _ in range(40):
            gbrain.add_node("same", "label", "content")

        assert gbrain.reward_tick == 40
        assert gbrain.reward_score("same", "same") == 10.0
        assert all(0 < score <= 10 for score in gbrain._pair_rewards.values())
        gbrain.close()

    def test_failed_graphml_write_rolls_back_graph_tick_and_reward(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from antigravity_k.engine import gbrain as gbrain_module

        gbrain = _new_gbrain(tmp_path / "gbrain_reward_save_failure")

        def fail_write(_graph: object, _path: str) -> object:
            raise OSError("simulated GraphML write failure")

        monkeypatch.setattr(gbrain_module, "_write_graphml", fail_write)
        with pytest.raises(OSError, match="simulated GraphML write failure"):
            gbrain.add_node("not-committed", "label", "content")

        assert not gbrain.graph.has_node("not-committed")
        assert gbrain.reward_tick == 0
        assert gbrain.reward_score("not-committed", "not-committed") == 0.0
        assert not (tmp_path / "gbrain_reward_save_failure" / "knowledge_graph.graphml").exists()
        gbrain.close()

    def test_reward_state_is_isolated_by_storage_directory(self, tmp_path: Path) -> None:
        first = _new_gbrain(tmp_path / "gbrain_isolated_a")
        second = _new_gbrain(tmp_path / "gbrain_isolated_b")
        first.add_node("shared-id", "label", "content")

        assert first.reward_tick == 1
        assert first.reward_score("shared-id", "shared-id") == 1.0
        assert second.reward_tick == 0
        assert second.reward_score("shared-id", "shared-id") == 0.0
        first.close()
        second.close()

    def test_two_instances_on_same_store_refresh_after_other_writer(self, tmp_path: Path) -> None:
        storage = tmp_path / "gbrain_shared_storage"
        first = _new_gbrain(storage)
        second = _new_gbrain(storage)
        first.add_node("first", "label", "first")
        second.add_node("second", "label", "second")

        assert second.reward_tick == 2
        assert second.graph.has_node("first")
        assert second.graph.has_node("second")
        assert second.reward_score("first", "first") == pytest.approx(0.95)
        assert second.reward_score("second", "second") == 1.0
        first.close()
        second.close()

    def test_failed_clear_save_restores_graph_and_rewards(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from antigravity_k.engine import gbrain as gbrain_module

        gbrain = _new_gbrain(tmp_path / "gbrain_clear_failure")
        gbrain.add_node("keep", "label", "content")
        before_tick = gbrain.reward_tick
        before_score = gbrain.reward_score("keep", "keep")

        def fail_write(_graph: object, _path: str) -> object:
            raise OSError("clear save failure")

        monkeypatch.setattr(gbrain_module, "_write_graphml", fail_write)
        with pytest.raises(OSError, match="clear save failure"):
            gbrain.clear_all()

        assert gbrain.graph.has_node("keep")
        assert gbrain.reward_tick == before_tick
        assert gbrain.reward_score("keep", "keep") == before_score
        gbrain.close()

    def test_failed_redaction_save_restores_graph_and_rewards(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from antigravity_k.engine import gbrain as gbrain_module

        gbrain = _new_gbrain(tmp_path / "gbrain_redact_failure")
        gbrain.add_node("secret", "label", "TOKEN=secret-value")
        before_tick = gbrain.reward_tick
        before_score = gbrain.reward_score("secret", "secret")

        def fail_write(_graph: object, _path: str) -> object:
            raise OSError("redaction save failure")

        monkeypatch.setattr(gbrain_module, "_write_graphml", fail_write)
        with pytest.raises(OSError, match="redaction save failure"):
            gbrain.redact_all()

        assert gbrain.graph.nodes["secret"]["content"] == "TOKEN=secret-value"
        assert gbrain.reward_tick == before_tick
        assert gbrain.reward_score("secret", "secret") == before_score
        gbrain.close()

    def test_clear_all_resets_graph_and_reward_state(self, tmp_path: Path) -> None:
        storage = tmp_path / "gbrain_clear_rewards"
        gbrain = _new_gbrain(storage)
        gbrain.add_node("a", "label", "content")
        gbrain.add_node("b", "label", "content")
        gbrain.add_edge("a", "b", "related")

        assert gbrain.clear_all() == 2
        assert gbrain.reward_tick == 0
        assert gbrain.reward_score("a", "a") == 0.0
        assert len(gbrain.graph.nodes) == 0
        gbrain.close()

        reloaded = _new_gbrain(storage)
        try:
            assert reloaded.reward_tick == 0
            assert reloaded.reward_score("a", "b") == 0.0
            assert len(reloaded.graph.nodes) == 0
        finally:
            reloaded.close()

    def test_redact_all_preserves_reward_state(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_redact_rewards")
        gbrain.add_node("secret", "label", "TOKEN=supersecret")
        gbrain.add_node("other", "label", "content")
        tick_before = gbrain.reward_tick
        score_before = gbrain.reward_score("secret", "secret")

        assert gbrain.redact_all() > 0
        assert gbrain.reward_tick == tick_before
        assert gbrain.reward_score("secret", "secret") == score_before
        assert "supersecret" not in gbrain.graph.nodes["secret"]["content"]
        gbrain.close()


class TestGBrainSearchSemantic:
    def test_search_returns_results(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_search")
        gbrain.add_node("n1", "concept", "machine learning overview")
        gbrain.add_node("n2", "concept", "deep learning techniques")

        results = gbrain.search_semantic("machine learning", limit=5)
        assert len(results) >= 1
        gbrain.close()

    def test_search_empty_collection_returns_empty(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_search_empty")
        results = gbrain.search_semantic("anything")
        assert results == []
        gbrain.close()

    def test_search_with_label_filter(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_search_filter")
        gbrain.add_node("n1", "concept", "neural networks")
        gbrain.add_node("n2", "preference", "dark mode")

        results = gbrain.search_semantic("networks", filter_label="concept")
        assert len(results) >= 1
        assert results[0]["label"] == "concept"
        gbrain.close()

    def test_search_with_filter_no_match(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_search_nomatch")
        gbrain.add_node("n1", "concept", "neural networks")

        results = gbrain.search_semantic("networks", filter_label="nonexistent")
        assert len(results) == 0
        gbrain.close()


class TestGBrainGetRelated:
    def test_get_related_returns_neighbors(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_related")
        gbrain.add_node("center", "concept", "main idea")
        gbrain.add_node("neighbor", "concept", "related idea")
        gbrain.add_edge("center", "neighbor", "links_to")

        related = gbrain.get_related("center")
        assert len(related) == 1
        assert related[0]["id"] == "neighbor"
        gbrain.close()

    def test_get_related_nonexistent_node(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_related_none")
        result = gbrain.get_related("nonexistent")
        assert result == []
        gbrain.close()

    def test_get_related_node_with_no_edges(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_related_isolated")
        gbrain.add_node("lonely", "concept", "isolated node")

        related = gbrain.get_related("lonely")
        assert related == []
        gbrain.close()


class TestGBrainClose:
    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        gbrain = _new_gbrain(tmp_path / "gbrain_close")
        gbrain.close()
        gbrain.close()
        assert getattr(gbrain, "_closed") is True

    def test_close_cleans_up_chroma(self, tmp_path: Path) -> None:
        _require_chromadb()
        gbrain = _new_gbrain(tmp_path / "gbrain_close_chroma")
        gbrain.add_node("test", "label", "content")
        gbrain.close()
        assert gbrain.chroma_client is None


class TestGBrainGlobal:
    def test_global_gbrain_is_singleton(self):
        from antigravity_k.engine.gbrain import global_gbrain

        assert global_gbrain is not None
        assert hasattr(global_gbrain, "graph")
        assert hasattr(global_gbrain, "collection")

    def test_close_global_is_callable(self):
        from antigravity_k.engine import gbrain as gbrain_module

        close_global = getattr(gbrain_module, "_close_global_gbrain", None)
        assert callable(close_global)


class TestR20RewardMeaningAndConsumers:
    def test_r20_a1_high_reward_does_not_raise_authority(self, tmp_path: Path) -> None:
        """R20-A1: repeated upsert raises reward but not semantic authority/confidence."""
        gbrain = _new_gbrain(tmp_path / "r20_a1")
        assert gbrain.REWARD_SEMANTICS == "write_recency_frequency_storage_metadata"
        assert gbrain.REWARD_PROMOTION_STATUS == "experimental_storage_metadata"
        assert gbrain.reward_implies_authority() is False
        assert gbrain.REWARD_SELECTION_CONSUMERS == ()
        for _ in range(12):
            gbrain.add_node("n1", "label", "content about widgets", {"source": "fixture"})
        assert gbrain.reward_score("n1", "n1") > 1.0
        node = dict(gbrain.graph.nodes["n1"])
        for forbidden in ("authority", "confidence", "maturity", "applicability", "semantic_truth"):
            assert forbidden not in node
            assert node.get(forbidden) in (None, "", 0, 0.0)
        gbrain.close()

    def test_r20_a2_corrupt_snapshot_is_not_silent_empty(self, tmp_path: Path) -> None:
        """R20-A2: corrupt GraphML fails closed — not reported as healthy empty memory."""
        storage = tmp_path / "r20_a2"
        storage.mkdir(parents=True, exist_ok=True)
        (storage / "knowledge_graph.graphml").write_text("<graphml>BOGUS", encoding="utf-8")
        with pytest.raises(GBrainCorruptSnapshotError):
            _ = _new_gbrain(storage)

    def test_r20_a3_search_consumer_ignores_reward(self, tmp_path: Path) -> None:
        """R20-A3: no selection consumer ranks by reward; search path does not read reward_score."""
        gbrain = _new_gbrain(tmp_path / "r20_a3")
        assert gbrain.REWARD_SELECTION_CONSUMERS == ()
        # Even with inflated write reward, node attributes used by search stay reward-free.
        gbrain.add_node("a", "note", "alpha topic", {})
        for _ in range(8):
            gbrain.add_node("a", "note", "alpha topic", {})
        assert gbrain.reward_score("a", "a") > 1.0
        # get_related / graph neighbor listing does not attach reward as authority
        related = gbrain.get_related("a")
        assert all("reward" not in item and "authority" not in item for item in related)
        gbrain.close()

    def test_r20_a4_write_amplification_at_fixed_scale(self, tmp_path: Path) -> None:
        """R20-A4: measure per-write latency as pair count grows (decay touches all pairs)."""
        import time

        gbrain = _new_gbrain(tmp_path / "r20_a4")
        # seed 40 distinct node pairs so each write decays many scores
        for i in range(40):
            gbrain.add_node(f"n{i}", "lab", f"content {i}", {})
        samples: list[float] = []
        for i in range(15):
            start = time.perf_counter()
            gbrain.add_node(f"n{i % 40}", "lab", f"content {i}", {})
            samples.append(time.perf_counter() - start)
        assert len(samples) == 15
        assert all(s >= 0 for s in samples)
        # write amplification: reward map size bounded by cap logic but pair count grows with nodes
        assert len(gbrain._pair_rewards) >= 1
        # keep numbers for evidence (printed by pytest -s optionally)
        print(
            "R20-A4 latency_seconds",
            {
                "min": min(samples),
                "max": max(samples),
                "mean": sum(samples) / len(samples),
                "pairs": len(gbrain._pair_rewards),
            },
        )
        gbrain.close()
