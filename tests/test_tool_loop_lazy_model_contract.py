from __future__ import annotations

from collections.abc import Iterator
from typing import TypedDict
from unittest.mock import MagicMock

import pytest

from antigravity_k.engine.tool_loop import ToolLoopEngine
from tests.test_tool_loop import mock_orch


class State(TypedDict):
    ready: bool
    loads: list[str]
    generation: list[str]


def setup_engine(
    *, ready: bool = False, combo: bool = False, failure: Exception | None = None, stays_unloaded: bool = False
):
    orch = mock_orch._get_wrapped_function()()
    orch.manager.router.get_combo.return_value = object() if combo else None
    state: State = {"ready": ready, "loads": [], "generation": []}
    orch.task_execution_context = None
    orch._capacity_checkpoint = None
    orch.manager.is_loaded.side_effect = lambda name: state["ready"]

    def get(name):
        state["loads"].append(name)
        if failure is not None:
            raise failure
        if not stays_unloaded:
            state["ready"] = True
        return MagicMock()

    def stream(prompt, target, **kwargs) -> Iterator[str]:
        state["generation"].append(target)
        yield "synthetic-token"

    orch.manager.get.side_effect = get
    orch.manager.stream_generate.side_effect = stream
    orch._prepare_agent_prompt.return_value = (
        "selected-model",
        "",
        "",
        "",
        "fixture prompt",
        [{"role": "user", "content": "fixture"}],
    )
    engine = ToolLoopEngine(orch)
    engine._native_tools_kwargs = lambda *args, **kwargs: {}
    return engine, state


def consume_to_generation(engine, state):
    output = engine.run_loop([{"role": "user", "content": "fixture"}], "CODER", "code", 3, "selected-model")
    try:
        for _ in range(30):
            try:
                next(output)
            except StopIteration:
                break
            if state["generation"]:
                break
    finally:
        output.close()


def test_registered_unloaded_target_is_prepared_before_generation():
    engine, state = setup_engine()
    consume_to_generation(engine, state)
    assert state["loads"] == ["selected-model"]
    assert state["generation"] == ["selected-model"]


@pytest.mark.parametrize("ready,combo", [(True, False), (False, True)])
def test_already_loaded_or_combo_does_not_force_preparation(ready, combo):
    engine, state = setup_engine(ready=ready, combo=combo)
    consume_to_generation(engine, state)
    assert state["loads"] == [] and state["generation"] == ["selected-model"]


@pytest.mark.parametrize(
    "failure", [RuntimeError("load failed"), PermissionError("denied"), MemoryError("budget exhausted")]
)
def test_preparation_failure_preserves_original_error_without_retry(failure):
    engine, state = setup_engine(failure=failure)
    with pytest.raises(type(failure), match=str(failure)):
        consume_to_generation(engine, state)
    assert state["loads"] == ["selected-model"] and state["generation"] == []


def test_preparation_that_does_not_load_is_still_a_failure():
    engine, state = setup_engine(stays_unloaded=True)
    consume_to_generation(engine, state)
    assert state["loads"] == ["selected-model"] and state["generation"] == []
