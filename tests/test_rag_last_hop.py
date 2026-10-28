"""Last hop: CONTEXT_ENRICH output -> real agent_execute_handler -> ToolLoopEngine.run_loop boundary.

Only the embedding transport and the ToolLoopEngine (the model-calling target) are fakes.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from antigravity_k.engine import tool_loop
from antigravity_k.engine.orchestrator_execution_handlers import agent_execute_handler
from antigravity_k.engine.project_embedding_binding import PROJECT_RAG_ENABLED_ENV
from tests.test_context_enrich_rag_chat_input import FakeOllama, _chat, _orch, projects  # noqa: F401


class _FakeToolLoop:
    seen: list[list[dict[str, str]]] = []

    def __init__(self, orch: object) -> None:
        self.last_output = "fake answer"
        self.approval_required = False

    def run_loop(self, messages: list[dict[str, str]], *args: object, **kwargs: object) -> Generator[str, None, None]:
        _FakeToolLoop.seen.append([dict(m) for m in messages])
        yield "fake"


def test_relevant_code_reaches_run_loop(projects: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "true")
    monkeypatch.setattr(tool_loop, "ToolLoopEngine", _FakeToolLoop)
    _FakeToolLoop.seen = []
    a, _b = projects
    fake = FakeOllama()
    orch = _orch(a, fake)
    _ = orch._rag_indexer.index_project()
    ctx = _chat(orch)
    out = list(agent_execute_handler(ctx, orch))  # pyright: ignore[reportArgumentType]
    assert out == ["fake"] and ctx.agent_output == "fake answer"
    assert len(_FakeToolLoop.seen) == 1
    last = _FakeToolLoop.seen[0][-1]["content"]
    assert "<relevant_code>" in last and "ALPHA-ONLY" in last and "BETA-ONLY" not in last
    assert len(fake.embed_inputs) == 2


def test_disabled_policy_delivers_no_relevant_code(
    projects: tuple[Path, Path],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: F811
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "false")
    monkeypatch.setattr(tool_loop, "ToolLoopEngine", _FakeToolLoop)
    _FakeToolLoop.seen = []
    a, _b = projects
    ctx = _chat(_orch(a, FakeOllama()))
    _ = list(agent_execute_handler(ctx, _orch(a, None)))  # pyright: ignore[reportArgumentType]
    assert "<relevant_code>" not in _FakeToolLoop.seen[0][-1]["content"]
