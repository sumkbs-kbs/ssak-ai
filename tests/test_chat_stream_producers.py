from collections.abc import Generator
from contextvars import copy_context
from pathlib import Path

import pytest

from antigravity_k.engine.chat_stream_events import (
    FinalChunk,
    ProgressChunk,
    chat_stream_events_enabled,
    reset_chat_stream_events,
    set_chat_stream_events,
)
from antigravity_k.engine.quality_gate import QualityGate
from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, StateContext


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _status_node(ctx: StateContext, orch: None = None) -> Generator[str, None, None]:
    yield "analysis"


def _answer_node(ctx: StateContext, orch: None = None) -> Generator[str, None, None]:
    ctx.agent_output = '{"total": 10}'
    yield ctx.agent_output


def test_analysis_state_emits_progress_when_graph_runs() -> None:
    graph = AgentStateGraph()
    graph.set_entry(AgentState.CEO_ANALYZE)
    graph.add_node(AgentState.CEO_ANALYZE, _status_node)
    ctx = StateContext()

    chunks = list(graph.execute(ctx))

    assert isinstance(chunks[0], ProgressChunk)


def test_execution_state_keeps_answer_when_graph_runs() -> None:
    graph = AgentStateGraph()
    graph.set_entry(AgentState.AGENT_EXECUTE)
    graph.add_node(AgentState.AGENT_EXECUTE, _answer_node)
    ctx = StateContext()

    chunks = list(graph.execute(ctx))

    assert chunks == ['{"total": 10}']
    assert type(chunks[0]) is str


class _MemoryManager:
    def authoritative_project_fact_for_query(self, user_text: str) -> None:
        return None

    def prefetch_all(self, user_text: str) -> str:
        return ""

    def sync_all(self, user_text: str, output: str, metadata: None = None) -> None:
        return None


class _StreamContext:
    memory_manager = _MemoryManager()
    user_model: None = None


class _StreamOrchestrator:
    ctx = _StreamContext()
    manager: None = None
    task_execution_context: None = None
    _last_agent_output: str = ""

    def __init__(self, graph: AgentStateGraph) -> None:
        self._state_graph = graph

    def _latest_user_text(self, messages: list[dict[str, str]]) -> str:
        return messages[-1]["content"]

    def trajectory_compressor_for(self, target_model: str) -> None:
        return None

    def context_compressor_for(self, target_model: str) -> None:
        return None


def _revision_node(ctx: StateContext, orch: _StreamOrchestrator) -> Generator[str, None, None]:
    ctx.agent_output = '{"total": 12}'
    yield "revision"


def _revising_graph() -> AgentStateGraph:
    graph = AgentStateGraph()
    graph.set_entry(AgentState.AGENT_EXECUTE)
    graph.add_node(AgentState.AGENT_EXECUTE, _answer_node)
    graph.add_node(AgentState.QUALITY_CHECK, _revision_node)
    graph.add_edge(AgentState.AGENT_EXECUTE, AgentState.QUALITY_CHECK)
    return graph


def test_final_snapshot_uses_verified_revision_when_events_enabled() -> None:
    from antigravity_k.engine.orchestrator.stream import run_stream

    orch = _StreamOrchestrator(_revising_graph())
    token = set_chat_stream_events(True)
    try:
        chunks = list(run_stream(orch, [{"role": "user", "content": "calculate"}], "local"))
    finally:
        reset_chat_stream_events(token)

    assert isinstance(chunks[-1], FinalChunk)
    assert chunks[-1] == '{"total": 12}'


def test_legacy_stream_avoids_final_snapshot_duplication_when_events_disabled() -> None:
    from antigravity_k.engine.orchestrator.stream import run_stream

    orch = _StreamOrchestrator(_revising_graph())
    token = set_chat_stream_events(False)
    try:
        chunks = list(run_stream(orch, [{"role": "user", "content": "calculate"}], "local"))
    finally:
        reset_chat_stream_events(token)

    assert not any(isinstance(chunk, FinalChunk) for chunk in chunks)
    assert "".join(chunks).count('{"total": 10}') == 1


def test_event_mode_remains_scoped_when_context_is_copied() -> None:
    token = set_chat_stream_events(False)
    child = copy_context()

    child.run(set_chat_stream_events, True)
    active_in_parent = chat_stream_events_enabled()
    active_in_child = child.run(chat_stream_events_enabled)
    reset_chat_stream_events(token)

    assert active_in_parent is False
    assert active_in_child is True


class _QualityContext:
    cognitive_loop: None = None
    decision_anchor: None = None
    expected_tools: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.quality_gate = QualityGate(max_retries=0)


class _QualityOrchestrator:
    manager: None = None
    task_execution_context: None = None

    def __init__(self, project_root: Path) -> None:
        self.ctx = _QualityContext()
        self.project_root = project_root


def test_tool_loop_quality_status_is_progress_when_answer_is_evaluated(tmp_path: Path) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    engine = ToolLoopEngine(_QualityOrchestrator(tmp_path))

    chunks = list(engine._post_loop_checks([], "chat", "short", "explain the calculation"))

    assert chunks
    assert all(isinstance(chunk, ProgressChunk) for chunk in chunks)
    assert engine.last_output == "short"


def _failed_node(ctx: StateContext, orch: _StreamOrchestrator) -> Generator[str, None, None]:
    yield "verification_started"
    raise RuntimeError("provider_unavailable")


def test_graph_error_is_visible_when_execution_fails_after_draft() -> None:
    from antigravity_k.engine.orchestrator.stream import run_stream

    graph = _revising_graph()
    graph.add_node(AgentState.QUALITY_CHECK, _failed_node)
    orch = _StreamOrchestrator(graph)
    token = set_chat_stream_events(True)
    try:
        chunks = list(run_stream(orch, [{"role": "user", "content": "calculate"}], "local"))
    finally:
        reset_chat_stream_events(token)

    assert not any(isinstance(chunk, FinalChunk) for chunk in chunks)
    assert type(chunks[-1]) is str
    assert "provider_unavailable" in chunks[-1]
