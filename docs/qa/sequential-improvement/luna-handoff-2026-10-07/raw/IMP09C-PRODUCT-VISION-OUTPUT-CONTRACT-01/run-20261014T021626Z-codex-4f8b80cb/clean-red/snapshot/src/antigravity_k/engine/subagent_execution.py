from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from antigravity_k.engine.direct_task_execution import (
    DirectTaskExecution,
    TaskExecutionBindingPort,
    TaskStoreRunnerPort,
    TrackedStream,
)
from antigravity_k.engine.task_state_store import TaskExecutionContext, current_task_execution_context

logger = logging.getLogger(__name__)


class SubagentOrchestratorPort(Protocol):
    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]: ...


def start_subagent_stream(
    orchestrator: SubagentOrchestratorPort,
    task_runner: TaskStoreRunnerPort | None,
    messages: Sequence[Mapping[str, str]],
    target_model: str,
    subagent_kind: str,
    max_steps: int = 15,
) -> TrackedStream:
    execution_context = current_task_execution_context()
    if execution_context is None:
        return DirectTaskExecution(orchestrator, task_runner).start_stream(
            messages,
            target_model=target_model,
            max_steps=max_steps,
            ephemeral_message=None,
            execution_type="subagent",
        )
    return TrackedStream(
        task_id=execution_context.task_id,
        chunks=_bound_subagent_stream(
            orchestrator,
            execution_context,
            messages,
            target_model,
            subagent_kind,
            max_steps,
        ),
    )


def _bound_subagent_stream(
    orchestrator: SubagentOrchestratorPort,
    execution_context: TaskExecutionContext,
    messages: Sequence[Mapping[str, str]],
    target_model: str,
    subagent_kind: str,
    max_steps: int,
) -> Iterator[str]:
    state_store = execution_context.state_store
    output_parts: list[str] = []
    outcome_recorded = False
    _ = state_store.append_execution_event(
        execution_context.task_id,
        "subagent_started",
        json.dumps({"kind": subagent_kind, "model": target_model}, sort_keys=True),
    )
    try:
        with _execution_binding(orchestrator, execution_context):
            for chunk in orchestrator.run_stream(
                [dict(message) for message in messages],
                target_model=target_model,
                max_steps=max_steps,
            ):
                output_parts.append(chunk)
                yield chunk
    except Exception as error:  # noqa: BLE001
        logger.exception("Subagent execution failed for task %s", execution_context.task_id)
        _ = state_store.append_execution_event(
            execution_context.task_id,
            "subagent_failed",
            json.dumps(
                {"error": str(error), "kind": subagent_kind, "output_length": len("".join(output_parts))},
                sort_keys=True,
            ),
        )
        outcome_recorded = True
        raise
    else:
        _ = state_store.append_execution_event(
            execution_context.task_id,
            "subagent_completed",
            json.dumps(
                {"kind": subagent_kind, "output_length": len("".join(output_parts))},
                sort_keys=True,
            ),
        )
        outcome_recorded = True
    finally:
        if not outcome_recorded:
            _ = state_store.append_execution_event(
                execution_context.task_id,
                "subagent_cancelled",
                json.dumps(
                    {"kind": subagent_kind, "output_length": len("".join(output_parts))},
                    sort_keys=True,
                ),
            )


def _execution_binding(
    orchestrator: SubagentOrchestratorPort,
    execution_context: TaskExecutionContext,
) -> AbstractContextManager[None]:
    if isinstance(orchestrator, TaskExecutionBindingPort):
        return orchestrator.bind_task_execution(
            execution_context.task_id,
            execution_context.state_store,
        )
    return nullcontext()
