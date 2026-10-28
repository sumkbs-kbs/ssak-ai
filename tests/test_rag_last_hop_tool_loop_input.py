"""Last hop: CONTEXT_ENRICH output -> real agent/max execute handlers -> ToolLoopEngine.run_loop input.

The handlers under test run for real; only the ToolLoopEngine boundary (the model-calling
engine) is replaced by a capturing fake target, and embeddings use the fake transport.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.engine import tool_loop as tool_loop_module
from antigravity_k.engine.orchestrator_execution_handlers import agent_execute_handler, max_execute_handler
from antigravity_k.engine.project_embedding_binding import PROJECT_RAG_ENABLED_ENV
from tests.test_context_enrich_rag_chat_input import FakeOllama, _chat, _orch, projects  # noqa: F401


class _CapturingToolLoop:
    captured: list[list[dict[str, str]]] = []

    def __init__(self, orch: object) -> None:
        self.last_output = "fake output"
        self.approval_required = False

    def run_loop(self, messages: list[dict[str, str]], *args: object, **kwargs: object) -> Generator[str, None, None]:
        _CapturingToolLoop.captured.append([dict(m) for m in messages])
        yield "fake"


@pytest.mark.parametrize("handler", [agent_execute_handler, max_execute_handler])
def test_relevant_code_reaches_tool_loop_input(
    handler: Callable[..., Iterator[str]],
    projects: tuple[Path, Path],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "true")
    monkeypatch.setattr(tool_loop_module, "ToolLoopEngine", _CapturingToolLoop)
    _CapturingToolLoop.captured = []
    a, _b = projects
    fake = FakeOllama()
    orch = _orch(a, fake)
    _ = orch._rag_indexer.index_project()
    ctx = _chat(orch)
    exec_orch = SimpleNamespace(max_engine=None)
    _ = list(handler(ctx, exec_orch))
    assert len(_CapturingToolLoop.captured) == 1
    final = _CapturingToolLoop.captured[0][-1]["content"]
    assert "<relevant_code>" in final and "ALPHA-ONLY" in final and "BETA-ONLY" not in final
    assert len(fake.embed_inputs) == 2
