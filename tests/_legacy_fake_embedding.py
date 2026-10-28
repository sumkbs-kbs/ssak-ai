"""Test-only deterministic embedding binding for legacy VectorStore suites (r29).

Production no longer has an implicit embedding (Chroma default ONNX was removed). Suites that test
chunk identity / provenance / memory behaviour, not embeddings, construct VectorStore without a
binding; this fixture gives them an explicit fake binding over a mocked Ollama HTTP transport so no
model is downloaded or contacted.
"""

from __future__ import annotations

import hashlib
import json
from typing import cast
from unittest import mock

import httpx
import pytest

MODEL = "nomic-embed-text:latest"
DIM = 64


def _vec(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in text.lower().split():
        v[int(hashlib.sha256(tok.encode()).hexdigest(), 16) % DIM] += 1.0
    v[0] += 0.01
    return v


def _handler(request: httpx.Request) -> httpx.Response:
    inputs = cast(list[str], cast(dict[str, object], json.loads(request.content))["input"])
    return httpx.Response(200, json={"model": MODEL, "embeddings": [_vec(t) for t in inputs]})


def build_fake_binding(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Real configured binding over a mocked Ollama transport (no model contacted), not installed globally."""
    from antigravity_k.engine.model_registry import ModelProfile
    from antigravity_k.engine.project_embedding_binding import configured_embedding_binding
    from antigravity_k.engine.provider_adapters.embedding_providers import REQUEST_LIMIT_ENV, OllamaEmbeddingProvider

    monkeypatch.setenv(REQUEST_LIMIT_ENV, "100000")
    monkeypatch.setenv("AGK_RAG_EMBEDDING", "ollama")
    profile = ModelProfile(
        name=MODEL, repo=MODEL, role="embedding", provider="ollama", api_base="http://127.0.0.1:11434", dimensions=DIM
    )
    reg = mock.MagicMock()
    reg.get_default.return_value = profile
    reg.get_model.return_value = profile
    reg.get_provider_config.return_value = {}
    binding = configured_embedding_binding(
        reg, ollama_provider=OllamaEmbeddingProvider(transport=httpx.MockTransport(_handler))
    )
    assert binding is not None
    return binding


@pytest.fixture
def legacy_fake_binding(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.engine import vector_store as vs

    binding = build_fake_binding(monkeypatch)
    original = vs.VectorStore.__init__

    def init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("embedding_binding") is None:
            kwargs["embedding_binding"] = binding
        original(self, *args, **kwargs)

    monkeypatch.setattr(vs.VectorStore, "__init__", init)
    return binding
