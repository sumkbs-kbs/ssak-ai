"""Tests for EmbeddingEngine — embedding generation with fallback.

Covers initialization, model loading (test/mock prefix), fallback embedding
determinism/dimensionality/normalization, and the singleton accessor.
"""

import hashlib
import json
import sys
from collections.abc import Callable
from types import ModuleType

import numpy as np
import pytest

from antigravity_k.engine.embeddings import (
    EmbeddingEngine,
    EmbeddingModelUnavailableError,
    _EmbeddingModel,
    get_embedding_engine,
)

# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_embedding_engine_initialization():
    engine = EmbeddingEngine()
    assert engine.current_model is None
    assert engine.model is None
    assert engine.tokenizer is None


def test_get_embedding_engine_singleton():
    engine1 = get_embedding_engine()
    engine2 = get_embedding_engine()
    assert engine1 is engine2


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def test_load_model():
    engine = EmbeddingEngine()
    model_name = "test-embed-model"
    engine.load_model(model_name)
    assert engine.current_model == model_name


def test_load_mock_model_uses_fallback():
    engine = EmbeddingEngine()
    engine.load_model("mock-embed")
    assert engine.model is None
    assert engine.current_model == "mock-embed"


def test_load_dummy_model_uses_fallback():
    engine = EmbeddingEngine()
    engine.load_model("dummy-v1")
    assert engine.model is None


# ---------------------------------------------------------------------------
# Fallback embedding properties
# ---------------------------------------------------------------------------


def test_fallback_embedding_deterministic():
    engine = EmbeddingEngine()
    v1 = engine._fallback_embedding("test input")
    v2 = engine._fallback_embedding("test input")
    assert v1 == v2


def test_fallback_embedding_different_inputs_differ():
    engine = EmbeddingEngine()
    v1 = engine._fallback_embedding("apple")
    v2 = engine._fallback_embedding("banana")
    assert v1 != v2


def test_fallback_embedding_is_normalized():
    engine = EmbeddingEngine()
    vec = np.array(engine._fallback_embedding("normalize me"))
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 0.01


def test_fallback_embedding_values_in_range():
    engine = EmbeddingEngine()
    vec = engine._fallback_embedding("range check")
    assert all(-1.0 <= v <= 1.0 for v in vec)


def test_fallback_embedding_empty_string():
    engine = EmbeddingEngine()
    vec = engine._fallback_embedding("")
    assert len(vec) == EmbeddingEngine.fallback_dimensions


# ---------------------------------------------------------------------------
# Embed (high-level API)
# ---------------------------------------------------------------------------


def test_embed_single_string():
    engine = EmbeddingEngine()
    model_name = "test-embed-model"
    text = "Hello world"

    embeddings = engine.embed(text, model_name)

    assert isinstance(embeddings, list)
    assert len(embeddings) == 1
    assert isinstance(embeddings[0], list)
    assert len(embeddings[0]) == 1536  # Current dummy length


def test_embed_multiple_strings():
    engine = EmbeddingEngine()
    model_name = "test-embed-model"
    texts = ["Hello world", "Test sentence"]

    embeddings = engine.embed(texts, model_name)

    assert isinstance(embeddings, list)
    assert len(embeddings) == 2
    assert isinstance(embeddings[0], list)
    assert isinstance(embeddings[1], list)
    assert len(embeddings[0]) == 1536
    assert len(embeddings[1]) == 1536


def test_embed_different_strings_different_vectors():
    engine = EmbeddingEngine()
    result = engine.embed(["cat", "dog"], model_name="test-model")
    assert result[0] != result[1]


def test_embed_empty_list():
    engine = EmbeddingEngine()
    result = engine.embed([], model_name="test-model")
    assert result == []


@pytest.mark.parametrize("model_name", ["test-embed", "mock-embed", "dummy-embed"])
def test_strict_fallback_only_targets_raise_before_hashing(model_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = EmbeddingEngine()
    fallback_calls: list[str] = []
    original_fallback = engine._fallback_embedding

    def counted_fallback(text: str) -> list[float]:
        fallback_calls.append(text)
        return original_fallback(text)

    monkeypatch.setattr(engine, "_fallback_embedding", counted_fallback)
    with pytest.raises(EmbeddingModelUnavailableError) as caught:
        engine.embed("probe", model_name, allow_fallback=False)
    assert caught.value.model_name == model_name
    assert str(caught.value) == f"Embedding model '{model_name}' could not be loaded."
    assert engine.current_model == model_name and engine.model is None
    assert fallback_calls == []


def test_loader_failure_preserves_default_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    engine = EmbeddingEngine()
    model_name = "nomic-embed-text:latest"
    text = "SSAK_EM01_MODEL_IDENTITY_PROBE"
    factory_models: list[str] = []
    fallback_calls: list[str] = []
    original_fallback = engine._fallback_embedding

    def failing_factory(requested_model: str) -> _EmbeddingModel:
        factory_models.append(requested_model)
        raise RuntimeError("controlled-loader-failure")

    def counted_fallback(value: str) -> list[float]:
        fallback_calls.append(value)
        return original_fallback(value)

    module = ModuleType("sentence_transformers")
    setattr(module, "SentenceTransformer", failing_factory)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(engine, "_fallback_embedding", counted_fallback)
    first = engine.embed(text, model_name)
    second = engine.embed(text, model_name)
    assert factory_models == [model_name, model_name]
    assert fallback_calls == [text, text]
    assert first == second == [original_fallback(text)]
    assert len(first[0]) == engine.fallback_dimensions
    assert np.isfinite(first[0]).all()
    assert abs(np.linalg.norm(first[0]) - 1.0) < 1e-12
    record_property(
        "default_fallback_observation",
        json.dumps(
            {
                "factory_calls": len(factory_models),
                "fallback_calls": len(fallback_calls),
                "dimension": len(first[0]),
                "deterministic": first == second,
                "vector_sha256": hashlib.sha256(json.dumps(first[0], separators=(",", ":")).encode()).hexdigest(),
                "post_count": 0,
            },
            separators=(",", ":"),
        ),
    )
