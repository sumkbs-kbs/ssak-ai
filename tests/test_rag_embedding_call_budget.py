"""App RAG store/search/reopen through the configured binding uses <=4 embedding requests (fake Ollama)."""

import json
import math
from pathlib import Path
from typing import cast
from unittest import mock

import httpx
import pytest

from antigravity_k.engine.model_registry import ModelProfile
from antigravity_k.engine.project_embedding_binding import RAG_EMBEDDING_ENV, configured_embedding_binding
from antigravity_k.engine.provider_adapters.embedding_providers import (
    REQUEST_LIMIT_ENV,
    OllamaEmbeddingProvider,
    OllamaEmbeddingUnavailableError,
)
from antigravity_k.engine.vector_store import VectorStore

MODEL = "nomic-embed-text:latest"
DOCS = ["사과는 빨간 과일이다", "바다는 파랗고 넓다", "숲에는 나무가 많다"]


def _registry() -> mock.MagicMock:
    profile = ModelProfile(
        name=MODEL, repo=MODEL, role="embedding", provider="ollama", api_base="http://127.0.0.1:11434"
    )
    reg = mock.MagicMock()
    reg.get_default.return_value = profile
    reg.get_model.return_value = profile
    reg.get_provider_config.return_value = {}
    return reg


class _FakeOllama:
    def __init__(self) -> None:
        self.embed_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1" and request.url.path == "/api/embed"
        self.embed_calls += 1
        inputs = json.loads(request.content)["input"]
        rows = [[float((len(t) + i) % 7) + 0.5 for i in range(8)] for t in inputs]
        return httpx.Response(200, json={"model": MODEL, "embeddings": rows})


@pytest.fixture(autouse=True)
def _reset_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OllamaEmbeddingProvider, "requests_sent", 0)
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    monkeypatch.setenv(REQUEST_LIMIT_ENV, "4")


def test_store_search_reopen_uses_two_requests_and_preserves_metadata(tmp_path: Path) -> None:
    fake = _FakeOllama()
    provider = OllamaEmbeddingProvider(transport=httpx.MockTransport(fake))
    binding = configured_embedding_binding(_registry(), ollama_provider=provider)
    assert binding is not None
    vs = VectorStore(str(tmp_path), collection_name="r15_nomic", embedding_binding=binding)
    vs.upsert_chunks(
        [{"id": f"d{i}", "text": t, "metadata": {"source": "synthetic", "n": i}} for i, t in enumerate(DOCS)]
    )
    hits = vs.search("파란 바다", n_results=1)
    vs.close()
    assert len(hits) == 1 and fake.embed_calls == 2
    vs2 = VectorStore(str(tmp_path), collection_name="r15_nomic", embedding_binding=binding)
    col = vs2._require_collection()  # pyright: ignore[reportPrivateUsage]
    assert col.count() == 3
    got = col.get(include=["metadatas", "embeddings"])
    metas = cast(list[dict[str, object]], got["metadatas"])
    assert sorted(cast(int, m["n"]) for m in metas) == [0, 1, 2]
    assert all(m["source"] == "synthetic" for m in metas)
    rows = cast(list[list[float]], got["embeddings"])
    assert all(len(r) == 8 and all(math.isfinite(float(v)) for v in r) for r in rows)
    vs2.close()
    assert fake.embed_calls == 2 and OllamaEmbeddingProvider.requests_sent == 2


def test_limit_blocks_fifth_request_without_sending() -> None:
    fake = _FakeOllama()
    provider = OllamaEmbeddingProvider(transport=httpx.MockTransport(fake))
    profile = _registry().get_default("embedding")
    for _ in range(4):
        _ = provider.embed(profile, None, "x", MODEL)
    with pytest.raises(OllamaEmbeddingUnavailableError, match="limit"):
        _ = provider.embed(profile, None, "x", MODEL)
    assert fake.embed_calls == 4
