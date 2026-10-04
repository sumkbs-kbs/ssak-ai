from __future__ import annotations

from collections.abc import Generator, Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal, assert_never

import pytest
from pydantic import JsonValue, TypeAdapter

from antigravity_k.engine.quality_gate import QualityGrade, QualityScore
from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, StateContext
from antigravity_k.engine.tool_guardrails import ToolGuardrailDecision

if TYPE_CHECKING:
    from antigravity_k.engine.benchmark_harness import TaskOutcome


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class _Router:
    def get_combo(self, name: str) -> None:
        return None


class _Model:
    router = _Router()

    def __init__(self, response: str) -> None:
        self.response = response
        self.generations: list[list[dict[str, str]]] = []

    def is_loaded(self, name: str) -> bool:
        return True

    def stream_generate(self, **kwargs: JsonValue) -> Iterator[str]:
        yield self.response

    def generate(self, prompt: str, target: str, **kwargs: JsonValue) -> str:
        history = TypeAdapter(list[dict[str, str]]).validate_python(kwargs.get("raw_messages", []))
        self.generations.append(history)
        return "revised"


class _Gate:
    max_retries = 1

    def __init__(self) -> None:
        self.outputs: list[str] = []

    def reset(self) -> None:
        self.outputs.clear()

    def mark_retry(self) -> None:
        return None

    def evaluate(
        self,
        task_type: str,
        user_request: str,
        agent_output: str,
        execution_mode: str | None = None,
    ) -> QualityScore:
        self.outputs.append(agent_output)
        improved = len(self.outputs) > 1
        return QualityScore(
            grade=QualityGrade.A if improved else QualityGrade.C,
            score=1.0 if improved else 0.2,
            feedback="repair",
            user_message="",
            should_retry=not improved,
            issues=[],
        )


class _Guardrail:
    def reset_for_turn(self) -> None:
        return None

    def before_call(self, tool_name: str, args: Mapping[str, JsonValue] | None = None) -> ToolGuardrailDecision:
        return ToolGuardrailDecision(tool_name=tool_name)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, JsonValue] | None = None,
        result: str | None = None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        return ToolGuardrailDecision(tool_name=tool_name)


class _ApprovalExecutor:
    async def execute_async(self, name: str, args: dict[str, JsonValue], *, guardrail_prechecked: bool = False) -> str:
        return "[APPROVAL REQUIRED]"


class _Context:
    cognitive_loop: None = None
    decision_anchor: None = None
    expected_tools: tuple[str, ...] = ()
    tool_guardrail = _Guardrail()
    tool_executor = _ApprovalExecutor()

    def __init__(self) -> None:
        self.quality_gate = _Gate()


class _Orchestrator:
    task_execution_context: None = None
    max_engine: None = None
    agent_runtime: None = None
    tool_registry: None = None

    def __init__(self, project_root: Path, response: str) -> None:
        self.project_root = project_root
        self.manager = _Model(response)
        self.ctx = _Context()
        self.config: dict[str, JsonValue] = {}

    def context_compressor_for(self, target_model: str) -> None:
        return None

    def _get_model_for_role(self, role: str) -> str:
        return "local"

    def _prepare_agent_prompt(
        self, messages: list[dict[str, str]], delegate_to: str, task_type: str
    ) -> tuple[str, str, str, str, str, list[dict[str, str]]]:
        return "local", "", "", "", "Assistant: ", [dict(message) for message in messages]


class _Outcomes:
    def __init__(self) -> None:
        self.values: list[TaskOutcome] = []

    def __call__(self, outcome: TaskOutcome) -> None:
        self.values.append(outcome)


def test_quality_revision_preserves_prior_constraints_when_latest_turn_is_short(tmp_path: Path) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    orch = _Orchestrator(tmp_path, "draft")
    history = [
        {"role": "user", "content": "project=종달새;budget=900000;deadline=2026-10-20"},
        {"role": "assistant", "content": "confirmed"},
        {"role": "user", "content": "budget=600000;deadline=2026-10-18"},
        {"role": "assistant", "content": "confirmed"},
        {"role": "user", "content": "latest conditions"},
    ]
    engine = ToolLoopEngine(orch)

    list(engine._post_loop_checks(history, "chat", "draft", "latest conditions", "local"))

    assert orch.manager.generations[0][:-1] == history
    assert orch.manager.generations[0][-1]["role"] == "user"


@pytest.mark.parametrize("partial", ["", "partial answer\n"])
def test_approval_wait_does_not_run_quality_rewrite_when_tool_requires_permission(tmp_path: Path, partial: str) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    response = partial + '<tool_call>{"name":"write_artifact","arguments":{}}</tool_call>'
    orch = _Orchestrator(tmp_path, response)
    outcomes = _Outcomes()
    engine = ToolLoopEngine(orch, outcome_recorder=outcomes)

    chunks = list(engine.run_loop([{"role": "user", "content": "create document"}], "SELF", "chat"))

    assert orch.manager.generations == []
    assert orch.ctx.quality_gate.outputs == []
    assert outcomes.values[0].completion_reason == "approval_required"
    assert outcomes.values[0].success is False
    assert "[APPROVAL REQUIRED]" in engine.last_output
    assert engine.last_output.startswith(partial)
    assert any("[APPROVAL REQUIRED]" in chunk for chunk in chunks)


def _unexpected_next_node(ctx: StateContext, orch: _Orchestrator) -> Generator[str, None, None]:
    ctx.error = "post_pause_execution"
    yield "unexpected"


@pytest.mark.parametrize("mode", ["agent", "max_fallback", "pipeline", "debate"])
def test_graph_stops_before_memory_when_execution_requires_approval(
    tmp_path: Path, mode: Literal["agent", "max_fallback", "pipeline", "debate"]
) -> None:
    from antigravity_k.engine.orchestrator_execution_handlers import (
        agent_execute_handler,
        debate_execute_handler,
        max_execute_handler,
        pipeline_execute_handler,
    )

    response = '<tool_call>{"name":"write_artifact","arguments":{}}</tool_call>'
    orch = _Orchestrator(tmp_path, response)
    ctx = StateContext(
        custom_messages=[{"role": "user", "content": "create document"}],
        target_model="local",
        analysis={"pipeline": [{"step": 1, "agent": "WORKER", "task": "create document"}]},
    )
    graph = AgentStateGraph()
    match mode:
        case "agent":
            state, handler = AgentState.AGENT_EXECUTE, agent_execute_handler
        case "max_fallback":
            state, handler = AgentState.MAX_EXECUTE, max_execute_handler
        case "pipeline":
            state, handler = AgentState.PIPELINE_EXECUTE, pipeline_execute_handler
        case "debate":
            state, handler = AgentState.DEBATE_EXECUTE, debate_execute_handler
        case unreachable:
            assert_never(unreachable)
    graph.set_entry(state)
    graph.add_node(state, handler)
    graph.add_node(AgentState.MEMORY_SAVE, _unexpected_next_node)
    graph.add_edge(state, AgentState.MEMORY_SAVE)

    list(graph.execute(ctx, orch))

    assert ctx.error is None
    assert ctx.current_state is AgentState.COMPLETE
    assert "[APPROVAL REQUIRED]" in ctx.agent_output


def test_approval_flag_resets_when_loop_instance_runs_another_turn(tmp_path: Path) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    response = '<tool_call>{"name":"write_artifact","arguments":{}}</tool_call>'
    orch = _Orchestrator(tmp_path, response)
    engine = ToolLoopEngine(orch)
    list(engine.run_loop([{"role": "user", "content": "create document"}], "SELF", "chat"))
    orch.manager.response = "answer"

    list(engine.run_loop([{"role": "user", "content": "explain"}], "SELF", "chat"))

    assert engine.approval_required is False
    assert engine.last_output == "revised"
