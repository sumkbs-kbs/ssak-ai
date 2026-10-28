"""CONTEXT_ENRICH -> real RAGIndexer search -> context assembly -> chat messages (fake embedding only).

Only the embedding HTTP transport is faked (httpx.MockTransport); the handler, the wired
RAGIndexer/VectorStore search and the message assembly are the real code.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest import mock

import httpx
import pytest

from antigravity_k.api import dependencies
from antigravity_k.engine.model_registry import ModelProfile
from antigravity_k.engine.orchestrator_handlers import context_enrich_handler
from antigravity_k.engine.project_embedding_binding import (
    RAG_ALLOWED_ROOT_ENV,
    RAG_EMBEDDING_ENV,
    configured_embedding_binding,
)
from antigravity_k.engine.provider_adapters.embedding_providers import REQUEST_LIMIT_ENV, OllamaEmbeddingProvider
from antigravity_k.engine.state_graph import StateContext

if TYPE_CHECKING:
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent

MODEL = "nomic-embed-text:latest"
DIM = 8
QUESTION = "zebra ledger rule"


class FakeOllama:
    def __init__(self, fail_after: int | None = None) -> None:
        self.embed_inputs: list[list[str]] = []
        self.fail_after = fail_after

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail_after is not None and len(self.embed_inputs) >= self.fail_after:
            self.embed_inputs.append(["<failed>"])
            return httpx.Response(500, json={"error": "fake"})
        inputs = cast(list[str], cast(dict[str, object], json.loads(request.content))["input"])
        self.embed_inputs.append(inputs)
        return httpx.Response(200, json={"model": MODEL, "embeddings": [[1.0 + i] * DIM for i, _ in enumerate(inputs)]})


def _registry() -> mock.MagicMock:
    profile = ModelProfile(
        name=MODEL, repo=MODEL, role="embedding", provider="ollama", api_base="http://127.0.0.1:11434", dimensions=DIM
    )
    reg = mock.MagicMock()
    reg.get_default.return_value = profile
    reg.get_model.return_value = profile
    reg.get_provider_config.return_value = {}
    return reg


def _orch(project: Path, fake: FakeOllama | None) -> SimpleNamespace:
    orch = SimpleNamespace(
        ctx=SimpleNamespace(ki_engine=SimpleNamespace(build_ki_prompt=lambda: "")),
        vault_engine=None,
        project_root=str(project),
        manager=None,
        _rag_indexer=None,
    )
    binding = None
    if fake is not None:
        provider = OllamaEmbeddingProvider(transport=httpx.MockTransport(fake.handler))
        binding = configured_embedding_binding(_registry(), ollama_provider=provider)
    dependencies._attach_project_rag_indexer(  # pyright: ignore[reportPrivateUsage]
        cast("OrchestratorAgent", cast(object, orch)), str(project), embedding_binding=binding
    )
    return orch


def _chat(orch: SimpleNamespace) -> StateContext:
    msgs = [{"role": "user", "content": QUESTION}]
    ctx = StateContext(messages=msgs, user_message=QUESTION, custom_messages=list(msgs))
    context_enrich_handler(ctx, orch)
    return ctx


@pytest.fixture
def projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    allowed = tmp_path / "allowed"
    a, b = allowed / "project-a", allowed / "project-b"
    for p, word in ((a, "ALPHA-ONLY"), (b, "BETA-ONLY")):
        p.mkdir(parents=True)
        (p / "notes.md").write_text(f"# zebra ledger\n\nzebra ledger rule {word} synthetic\n")
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    monkeypatch.setenv(RAG_ALLOWED_ROOT_ENV, str(allowed))
    monkeypatch.setenv(REQUEST_LIMIT_ENV, "4")
    monkeypatch.setattr(OllamaEmbeddingProvider, "requests_sent", 0)
    return a, b


def test_rag_on_search_result_reaches_chat_input_only_from_selected_project(projects: tuple[Path, Path]) -> None:
    a, b = projects
    fake_b = FakeOllama()
    orch_b = _orch(b, fake_b)
    _ = orch_b._rag_indexer.index_project()
    fake = FakeOllama()
    orch_a = _orch(a, fake)
    _ = orch_a._rag_indexer.index_project()
    ctx = _chat(orch_a)
    final_input = ctx.custom_messages[-1]["content"]
    model_seen: list[str] = []

    def fake_answer_model(messages: list[dict[str, str]]) -> str:
        model_seen.append(messages[-1]["content"])
        return "fake answer"

    assert fake_answer_model(ctx.custom_messages) == "fake answer"
    assert final_input.startswith(QUESTION) and "<relevant_code>" in final_input
    assert "ALPHA-ONLY" in final_input and "BETA-ONLY" not in final_input
    assert "ALPHA-ONLY" in ctx.rag_context and model_seen == [final_input]
    assert len(fake.embed_inputs) == 2 and fake.embed_inputs[1] == [QUESTION]


def test_rag_off_makes_no_search_call(projects: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    a, _b = projects
    # recovery18: precondition changed — "RAG off" is now the explicit search policy
    # AGK_PROJECT_RAG_ENABLED=false (embedding provider setting stays on). recovery17 failure kept.
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    from antigravity_k.engine import vector_store

    calls: list[str] = []

    def spy(self: object, query: str, n_results: int = 5) -> list[dict[str, object]]:
        calls.append(query)
        return []

    monkeypatch.setattr(vector_store.VectorStore, "search", spy)
    ctx = _chat(_orch(a, None))
    assert ctx.custom_messages[-1]["content"] == QUESTION
    assert calls == [], f"RAG disabled but CONTEXT_ENRICH searched {len(calls)}x"


def test_empty_results_are_not_presented_as_evidence(projects: tuple[Path, Path]) -> None:
    a, _b = projects
    fake = FakeOllama()
    ctx = _chat(_orch(a, fake))  # nothing indexed -> empty collection
    assert ctx.rag_context == "" and ctx.custom_messages[-1]["content"] == QUESTION
    assert "<relevant_code>" not in ctx.custom_messages[-1]["content"]


def test_search_error_is_not_presented_as_evidence(projects: tuple[Path, Path]) -> None:
    a, _b = projects
    fake = FakeOllama(fail_after=1)
    orch = _orch(a, fake)
    _ = orch._rag_indexer.index_project()
    ctx = _chat(orch)
    assert fake.embed_inputs[-1] == ["<failed>"]
    assert ctx.rag_context == "" and ctx.custom_messages[-1]["content"] == QUESTION


def test_enabled_bound_rag_syncs_project_lazily_then_searches(
    projects: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # recovery27: bound (enabled) mode has no startup auto-index; CONTEXT_ENRICH must sync
    # the selected project incrementally before searching, without re-embedding unchanged files.
    a, _b = projects
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "true")
    fake = FakeOllama()
    orch = _orch(a, fake)
    ctx = _chat(orch)  # no explicit index_project()
    final_input = ctx.custom_messages[-1]["content"]
    assert "<relevant_code>" in final_input and "ALPHA-ONLY" in final_input and "BETA-ONLY" not in final_input
    assert len(fake.embed_inputs) == 2 and fake.embed_inputs[1] == [QUESTION]
    ctx2 = _chat(orch)
    assert "ALPHA-ONLY" in ctx2.custom_messages[-1]["content"]
    assert len(fake.embed_inputs) == 3 and fake.embed_inputs[2] == [QUESTION]


def test_enabled_bound_rag_deleted_document_stops_serving_as_evidence(
    projects: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, _b = projects
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "true")
    fake = FakeOllama()
    orch = _orch(a, fake)
    assert "ALPHA-ONLY" in _chat(orch).custom_messages[-1]["content"]
    (a / "notes.md").unlink()
    ctx = _chat(orch)
    assert "ALPHA-ONLY" not in ctx.custom_messages[-1]["content"] and "ALPHA-ONLY" not in ctx.rag_context
    # deletion re-embeds nothing; the now-empty bound index is not even queried
    assert len(fake.embed_inputs) == 2


def test_model_without_long_context_plan_still_injects_rag(projects: tuple[Path, Path]) -> None:
    """r28 app run: long_context_plan() returned None and enrichment aborted (AttributeError)."""
    a, _ = projects
    fake = FakeOllama()
    orch = _orch(a, fake)
    _ = orch._rag_indexer.index_project()
    orch.manager = SimpleNamespace(long_context_plan=lambda _name: None)
    msgs = [{"role": "user", "content": QUESTION}]
    ctx = StateContext(messages=msgs, user_message=QUESTION, custom_messages=list(msgs), target_model="qwen3.8")
    context_enrich_handler(ctx, orch)
    final_input = ctx.custom_messages[-1]["content"]
    assert "<relevant_code>" in final_input and "ALPHA-ONLY" in final_input
