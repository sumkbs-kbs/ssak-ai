"""App RAG embedding binding factory: opt-in, loopback-only, no fallback (no real Ollama calls)."""

from pathlib import Path
from unittest import mock

import pytest

from antigravity_k.engine.model_registry import ModelProfile
from antigravity_k.engine.project_embedding_binding import (
    RAG_EMBEDDING_ENV,
    ProjectEmbeddingBindingError,
    configured_embedding_binding,
)

MODEL = "nomic-embed-text:latest"


def _registry(api_base: str) -> mock.MagicMock:
    profile = ModelProfile(name=MODEL, repo=MODEL, role="embedding", provider="ollama", api_base=api_base)
    reg = mock.MagicMock()
    reg.get_default.return_value = profile
    reg.get_model.return_value = profile
    reg.get_provider_config.return_value = {}
    return reg


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RAG_EMBEDDING_ENV, raising=False)
    assert configured_embedding_binding(_registry("http://127.0.0.1:11434")) is None


def test_opt_in_loopback_binds_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    binding = configured_embedding_binding(_registry("http://127.0.0.1:11434"))
    assert binding is not None
    assert binding.identity.wire_model == MODEL and binding.identity.endpoint == "http://127.0.0.1:11434"


def test_opt_in_rejects_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    with pytest.raises(ProjectEmbeddingBindingError):
        _ = configured_embedding_binding(_registry("http://10.0.0.5:11434"))


def test_binding_never_falls_back_to_fake_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    binding = configured_embedding_binding(_registry("http://127.0.0.1:9"))
    assert binding is not None
    with pytest.raises(Exception) as exc:
        _ = binding.embed(["x"])
    assert "fallback" not in type(exc.value).__name__.lower()


def test_project_rag_path_uses_configured_binding() -> None:
    src = (Path(__file__).resolve().parents[1] / "src/antigravity_k/api/dependencies.py").read_text()
    # r31: the runtime factory goes through the setup-pending gate, which still passes the
    # configured binding (never a substitute) to the bound indexer.
    assert "_attach_rag_or_mark_setup_pending(orchestrator, project_id, project_root)" in src
    assert "binding = configured_embedding_binding()" in src
    assert "_attach_project_rag_indexer(orchestrator, project_root, embedding_binding=binding)" in src
