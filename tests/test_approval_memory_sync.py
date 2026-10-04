from collections.abc import Generator
from pathlib import Path

import pytest

from antigravity_k.engine.chat_stream_events import FinalChunk, reset_chat_stream_events, set_chat_stream_events
from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, StateContext
from tests.test_quality_context_approval import _Context, _Orchestrator


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class _MemorySync:
    def __init__(self) -> None:
        self.synced: list[tuple[str, str]] = []

    def authoritative_project_fact_for_query(self, user_text: str) -> None:
        return None

    def prefetch_all(self, user_text: str) -> str:
        return ""

    def sync_all(self, user_text: str, output: str, metadata: None = None) -> None:
        self.synced.append((user_text, output))


class _StreamingContext(_Context):
    user_model: None = None

    def __init__(self) -> None:
        super().__init__()
        self.memory_manager = _MemorySync()


class _StreamingOrchestrator(_Orchestrator):
    def __init__(self, project_root: Path, response: str, graph: AgentStateGraph) -> None:
        super().__init__(project_root, response)
        self.ctx = _StreamingContext()
        self._state_graph = graph

    def _latest_user_text(self, messages: list[dict[str, str]]) -> str:
        return messages[-1]["content"]

    def trajectory_compressor_for(self, target_model: str) -> None:
        return None


def _initialize(ctx: StateContext, orch: _StreamingOrchestrator) -> Generator[str, None, None]:
    ctx.custom_messages = ctx.messages
    yield "initialized"


def test_stream_preserves_permission_wait_without_memory_sync_when_tool_pauses(tmp_path: Path) -> None:
    from antigravity_k.engine.orchestrator.stream import run_stream
    from antigravity_k.engine.orchestrator_execution_handlers import agent_execute_handler

    graph = AgentStateGraph()
    graph.add_node(AgentState.INIT, _initialize)
    graph.add_node(AgentState.AGENT_EXECUTE, agent_execute_handler)
    graph.add_edge(AgentState.INIT, AgentState.AGENT_EXECUTE)
    response = '<tool_call>{"name":"write_artifact","arguments":{}}</tool_call>'
    orch = _StreamingOrchestrator(tmp_path, response, graph)
    token = set_chat_stream_events(True)
    try:
        chunks = list(run_stream(orch, [{"role": "user", "content": "create document"}], "local"))
    finally:
        reset_chat_stream_events(token)

    assert orch.ctx.memory_manager.synced == []
    assert isinstance(chunks[-1], FinalChunk)
    assert "[APPROVAL REQUIRED]" in chunks[-1]


def _plain_answer(ctx: StateContext, orch: _StreamingOrchestrator) -> Generator[str, None, None]:
    ctx.agent_output = orch.manager.response
    yield ctx.agent_output


@pytest.mark.parametrize("answer", ["answer", "[APPROVAL REQUIRED] is a quoted documentation marker"])
def test_stream_syncs_completed_answer_when_no_typed_pause_is_set(tmp_path: Path, answer: str) -> None:
    from antigravity_k.engine.orchestrator.stream import run_stream

    graph = AgentStateGraph()
    graph.set_entry(AgentState.AGENT_EXECUTE)
    graph.add_node(AgentState.AGENT_EXECUTE, _plain_answer)
    orch = _StreamingOrchestrator(tmp_path, answer, graph)

    chunks = list(run_stream(orch, [{"role": "user", "content": "explain"}], "local"))

    assert orch.ctx.memory_manager.synced == [("explain", answer)]
    assert chunks[-1] == answer
