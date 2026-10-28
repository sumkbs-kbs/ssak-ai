"""r38: resume continues from the first incomplete plan step (no re-plan, no regenerated steps).

Real r37 A failure: after approval/restart the CEO planned again and the pipeline restarted at
step 1, so the completed work was produced twice. These tests drive the REAL CEO/pipeline handlers
and the REAL BackgroundTaskRunner checkpoint store; only the model-facing tool loop is a stub.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast, final

import pytest

from antigravity_k.engine import task_plan_state as tps
from antigravity_k.engine import tool_loop as tool_loop_module
from antigravity_k.engine.orchestrator_analysis_handlers import ceo_analyze_handler, ceo_gate_decision
from antigravity_k.engine.orchestrator_execution_handlers import pipeline_execute_handler
from antigravity_k.engine.state_graph import AgentState, StateContext
from antigravity_k.engine.task_runner import BackgroundTaskRunner


@final
class _Calls:
    def __init__(self, approval_at: set[tuple[int, str]] | None = None) -> None:
        self.steps: list[str] = []
        self.inputs: list[list[dict[str, str]]] = []
        self.approval_at = approval_at or set()
        self.run = 0


def _install_stub_loop(monkeypatch: pytest.MonkeyPatch, calls: _Calls) -> None:
    @final
    class _StubLoop:
        def __init__(self, orch: object) -> None:
            _ = orch
            self.last_output = ""
            self.approval_required = False

        def run_loop(
            self, messages: list[dict[str, str]], role: str, task_type: str, max_steps: int, *a: object, **k: object
        ) -> Iterator[str]:
            _ = (task_type, max_steps, a, k)
            step_line = messages[-1]["content"].splitlines()[0]
            calls.inputs.append([dict(m) for m in messages])
            if (calls.run, step_line) in calls.approval_at:
                self.approval_required = True
                yield "[APPROVAL REQUIRED]"
                return
            calls.steps.append(step_line)
            self.last_output = f"output of {step_line} by {role}"
            yield self.last_output

    monkeypatch.setattr(tool_loop_module, "ToolLoopEngine", _StubLoop)


@final
class _CeoOrch:
    def __init__(self, pipeline: list[dict[str, object]]) -> None:
        self.pipeline = pipeline
        self.ceo_calls = 0

    def _ceo_analyze(self, user_message: str, target_model: str) -> Iterator[object]:
        _ = (user_message, target_model)
        self.ceo_calls += 1
        yield {"task_type": "complex", "delegate_to": "WORKER", "pipeline": list(self.pipeline)}


def _run_graph_once(orch: _CeoOrch, state: dict[str, object] | None) -> tuple[StateContext, str]:
    ctx = StateContext(user_message="synthetic r38 task", task_type="")
    ctx.custom_messages = [{"role": "user", "content": "synthetic r38 task"}]
    out: list[str] = []
    with tps.bind_plan_state(state):
        out.extend(str(c) for c in ceo_analyze_handler(ctx, orch))
        out.extend(str(c) for c in pipeline_execute_handler(ctx, cast(Any, orch)))
    return ctx, "".join(out)


def _checkpoint_roundtrip(state: dict[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(state))  # what the task checkpoint store persists


PIPE3 = [
    {"step": 1, "agent": "WORKER", "task": "write the artifact"},
    {"step": 2, "agent": "SELF", "task": "list items 1-30"},
    {"step": 3, "agent": "QA", "task": "check the list"},
]
PIPE2 = PIPE3[:2]
PIPE4 = [*PIPE3, {"step": 4, "agent": "WRITER", "task": "summarize"}]


def _line(step: dict[str, object]) -> str:
    return f"[Pipeline Step {step['step']} — role: {step['agent']}]"


@pytest.mark.parametrize(
    ("pipeline", "interrupt_step"),
    [(PIPE2, 1), (PIPE2, 2), (PIPE3, 2), (PIPE3, 3), (PIPE4, 1), (PIPE4, 4)],
)
def test_resume_runs_each_step_exactly_once(
    monkeypatch: pytest.MonkeyPatch, pipeline: list[dict[str, object]], interrupt_step: int
) -> None:
    interrupted = _line(pipeline[interrupt_step - 1])
    calls = _Calls(approval_at={(1, interrupted)})
    _install_stub_loop(monkeypatch, calls)
    orch = _CeoOrch(pipeline)
    state: dict[str, object] = {}

    calls.run = 1
    ctx1, _ = _run_graph_once(orch, state)
    assert ctx1.approval_required is True
    assert calls.steps == [_line(s) for s in pipeline[: interrupt_step - 1]]

    calls.run = 2
    restored = _checkpoint_roundtrip(state)
    orch.pipeline = [*pipeline, {"step": 99, "agent": "SELF", "task": "a different re-plan"}]  # must NOT be used
    ctx2, out2 = _run_graph_once(orch, restored)
    assert orch.ceo_calls == 1  # no re-plan on resume
    assert ctx2.approval_required is False
    # every step exactly once across both runs: no duplicate, no omission
    assert calls.steps == [_line(s) for s in pipeline]
    assert "(completed before resume)" in out2 or interrupt_step == 1
    # the first step run after resume sees prior completed outputs as assistant turns
    first_after = calls.inputs[interrupt_step]  # inputs: run1 = interrupt_step entries (incl. the paused one)
    prior = [m["content"] for m in first_after if m["role"] == "assistant"]
    assert len(prior) == interrupt_step - 1


def test_fresh_task_without_state_keeps_old_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _Calls()
    _install_stub_loop(monkeypatch, calls)
    orch = _CeoOrch(PIPE3)
    _run_graph_once(orch, None)
    _run_graph_once(orch, None)
    assert orch.ceo_calls == 2
    assert calls.steps == [_line(s) for s in PIPE3] * 2


def test_memory_recall_reaches_context_enrich() -> None:
    recall = StateContext(user_message="What badge colour did we agree on for the offsite?", task_type="simple_chat")
    assert ceo_gate_decision(recall) == AgentState.CONTEXT_ENRICH
    hello = StateContext(user_message="안녕하세요", task_type="simple_chat")
    assert ceo_gate_decision(hello) == AgentState.ROUTE


@final
class _StateOrch:
    """Fake orchestrator that executes a 3-step plan through the runner-bound plan state."""

    vault_engine: object | None = None

    def __init__(self, effects: list[str]) -> None:
        self.effects = effects
        self.gate = threading.Semaphore(0)
        self.saw_plan_in_prompt = False

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        _ = target_model
        self.saw_plan_in_prompt = any("plan_state" in m["content"] for m in messages)
        for i in range(3):
            if tps.completed_step_output("p1", i) is not None:
                continue
            assert self.gate.acquire(timeout=5)
            self.effects.append(f"step{i}")
            tps.mark_step_completed("p1", i, f"out{i}")
            yield f"step {i} done\n"


def _wait(pred, timeout: float = 5.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def test_runner_persists_step_state_across_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "tasks.db")
    effects: list[str] = []
    runner = BackgroundTaskRunner(db_path=db)
    orch = _StateOrch(effects)
    tid = runner.submit_task("Synthetic r38 task: do three steps.", orchestrator=orch, target_model="fake")
    _wait(lambda: runner.state_store.get_task(tid)["status"] == "running")  # type: ignore[index]
    orch.gate.release(1)
    _wait(lambda: effects == ["step0"])
    assert runner.pause_task(tid) == "pausing"
    orch.gate.release(1)
    _wait(lambda: runner.state_store.get_task(tid)["status"] == "paused")  # type: ignore[index]
    done_before = list(effects)

    runner2 = BackgroundTaskRunner(db_path=db)
    orch2 = _StateOrch(effects)
    assert runner2.resume_task(tid, orchestrator=orch2, target_model="fake")
    orch2.gate.release(3)
    _wait(lambda: runner2.state_store.get_task(tid)["status"] == "done")  # type: ignore[index]
    assert effects == ["step0", "step1", "step2"], (done_before, effects)
    assert orch.saw_plan_in_prompt is False and orch2.saw_plan_in_prompt is False
