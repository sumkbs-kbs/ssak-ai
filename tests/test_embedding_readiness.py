"""Embedding readiness states with controlled Ollama responses (not real-model quality checks)."""

import httpx

from antigravity_k.engine.embedding_readiness import check_embedding_readiness
from antigravity_k.engine.model_registry import ModelProfile

MODEL = "nomic-embed-text:latest"


def _profile(dimensions: int = 3) -> ModelProfile:
    return ModelProfile(
        name=MODEL,
        repo=MODEL,
        role="embedding",
        provider="ollama",
        api_base="http://127.0.0.1:9",
        dimensions=dimensions,
    )


def _transport(tags: list[str] | None, embed_dim: int | None = 3, embed_status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            if tags is None:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={"models": [{"name": n} for n in tags]})
        if request.url.path == "/api/embed":
            if embed_status != 200:
                return httpx.Response(embed_status, json={"error": "x"})
            return httpx.Response(200, json={"model": MODEL, "embeddings": [[0.1] * (embed_dim or 0)]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_a_ollama_unreachable() -> None:
    r = check_embedding_readiness(_profile(), None, probe=True, transport=_transport(None))
    assert r["state"] == "ollama_unreachable" and r["rag_ready"] is False


def test_b_model_missing_never_ready() -> None:
    r = check_embedding_readiness(_profile(), None, probe=True, transport=_transport(["llama3:latest"]))
    assert r["state"] == "model_missing" and r["rag_ready"] is False and "ollama pull" in r["message"]


def test_c_embedding_call_failed() -> None:
    r = check_embedding_readiness(_profile(), None, probe=True, transport=_transport([MODEL], embed_status=500))
    assert r["state"] == "embedding_failed" and r["rag_ready"] is False


def test_c_dimension_mismatch() -> None:
    r = check_embedding_readiness(
        _profile(dimensions=768), None, probe=True, transport=_transport([MODEL], embed_dim=3)
    )
    assert r["state"] == "dimension_mismatch" and r["rag_ready"] is False


def test_d_embedding_works() -> None:
    r = check_embedding_readiness(_profile(), None, probe=True, transport=_transport([MODEL]))
    assert r["state"] == "ready" and r["rag_ready"] is True


def test_present_but_unprobed_is_not_ready() -> None:
    r = check_embedding_readiness(_profile(), None, probe=False, transport=_transport([MODEL]))
    assert r["state"] == "model_present_unprobed" and r["rag_ready"] is False
