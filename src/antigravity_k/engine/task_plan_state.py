"""r38: durable plan/step state for resumable tasks.

Root cause (r37 real A): the task checkpoint stored only (step=chunk count, context, output, tool_loop).
On resume the orchestrator graph ran CEO_ANALYZE again (new plan) and PIPELINE_EXECUTE restarted at
step 1, so completed steps were regenerated. The runner now binds a mutable ``plan_state`` dict that
lives inside ``task.context`` (persisted by every ``_save_checkpoint``). CEO_ANALYZE reuses the stored
analysis and PIPELINE_EXECUTE skips steps recorded as completed for the same plan id.
Only structured state is kept here; it is never rendered into model-visible task context.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Generator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar

PLAN_STATE_KEY = "plan_state"
PLAN_STATE_VERSION = 1
STEP_OUTPUT_MAX_CHARS = 4000

_plan_state: ContextVar[MutableMapping[str, object] | None] = ContextVar("task_plan_state", default=None)


@contextmanager
def bind_plan_state(state: MutableMapping[str, object] | None) -> Generator[None, None, None]:
    token = _plan_state.set(state)
    try:
        yield
    finally:
        _plan_state.reset(token)


def current_plan_state() -> MutableMapping[str, object] | None:
    return _plan_state.get()


def _json_safe(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def plan_id_for(pipeline: object) -> str:
    canonical = json.dumps(_json_safe(pipeline), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def stored_analysis() -> dict[str, object] | None:
    state = current_plan_state()
    if state is None:
        return None
    analysis = state.get("analysis")
    if isinstance(analysis, Mapping) and state.get("version") == PLAN_STATE_VERSION:
        return {str(k): v for k, v in analysis.items()}
    return None


def store_analysis(analysis: Mapping[str, object]) -> None:
    state = current_plan_state()
    if state is None:
        return
    safe = _json_safe(dict(analysis))
    state["version"] = PLAN_STATE_VERSION
    state["analysis"] = safe
    state["plan_id"] = plan_id_for(dict(analysis).get("pipeline") or [])
    state["steps"] = {}


def _steps() -> MutableMapping[str, object] | None:
    state = current_plan_state()
    if state is None:
        return None
    steps = state.get("steps")
    if not isinstance(steps, dict):
        steps = {}
        state["steps"] = steps
    return steps


def step_key(plan_id: str, index: int) -> str:
    return f"{plan_id}:{index}"


def completed_step_output(plan_id: str, index: int) -> str | None:
    steps = _steps()
    if steps is None:
        return None
    entry = steps.get(step_key(plan_id, index))
    if isinstance(entry, Mapping) and entry.get("status") == "completed":
        output = entry.get("output")
        return output if isinstance(output, str) else ""
    return None


def mark_step_completed(plan_id: str, index: int, output: str) -> None:
    steps = _steps()
    if steps is None:
        return
    steps[step_key(plan_id, index)] = {"status": "completed", "output": output[-STEP_OUTPUT_MAX_CHARS:]}


def reset_plan_state(state: MutableMapping[str, object] | None) -> None:
    if state is not None:
        state.clear()


def context_without_plan_state(context: Mapping[str, object]) -> dict[str, object]:
    return {k: v for k, v in context.items() if k != PLAN_STATE_KEY}


__all__ = [
    "PLAN_STATE_KEY",
    "bind_plan_state",
    "completed_step_output",
    "context_without_plan_state",
    "current_plan_state",
    "mark_step_completed",
    "plan_id_for",
    "reset_plan_state",
    "store_analysis",
    "stored_analysis",
]
