from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, final

from pydantic import TypeAdapter, ValidationError

from antigravity_k.engine.direct_task_execution import (
    DirectTaskExecution,
    MaxEnginePort,
    MaxRunResultPort,
    TaskOutcomeRecorder,
    TaskStoreRunnerPort,
    TrackedStream,
)
from antigravity_k.engine.goal_runner import GoalReport, GoalRunner
from antigravity_k.engine.persistent_agency import Objective, ProjectedContext
from antigravity_k.engine.task_events import ExecutionEventRecord
from antigravity_k.engine.task_state_types import CancellationVerdict
from antigravity_k.engine.task_steering import TaskSteeringResult

if TYPE_CHECKING:
    from antigravity_k.engine.benchmark_harness import TaskOutcome
    from antigravity_k.engine.cognitive_surface import ShadowRun, SurfaceEpisodeRequest

logger = logging.getLogger(__name__)

_TASK_IDS_ADAPTER = TypeAdapter(list[str])


class CognitiveSurfaceLike(Protocol):
    """P11 opt-in surface(adapter)가 runtime에 노출하는 최소 계약."""

    @property
    def settings(self) -> object: ...

    def run_shadow(self, request: "SurfaceEpisodeRequest") -> "ShadowRun": ...


class ShadowObservation:
    """legacy 경로 옆에서 돈 shadow episode 요약. legacy 응답은 절대 담지 않는다."""

    def __init__(self, episode_id: str, termination: str, dispatched_actions: int, refused_actions: int) -> None:
        self.episode_id = episode_id
        self.termination = termination
        self.dispatched_actions = dispatched_actions
        self.refused_actions = refused_actions

    def __repr__(self) -> str:  # pragma: no cover - 진단용
        return f"ShadowObservation({self.episode_id!r}, {self.termination!r}, dispatch={self.dispatched_actions})"


class OrchestratorPort(Protocol):
    @property
    def max_engine(self) -> MaxEnginePort | None: ...

    def get_model_for_role(self, role: str) -> str: ...

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]: ...


class TaskRunnerPort(Protocol):
    def submit_task(
        self,
        prompt: str,
        context: dict[str, object] | None = None,
        orchestrator: OrchestratorPort | None = None,
        target_model: str = "",
        use_worktree: bool = False,
        idempotency_key: str | None = None,
        owner_subject: str = "loopback",
    ) -> str: ...

    def resume_task(
        self,
        task_id: str,
        orchestrator: OrchestratorPort | None = None,
        target_model: str = "",
        owner_subject: str | None = None,
    ) -> bool: ...

    def cancel_task(self, task_id: str, owner_subject: str | None = None) -> bool: ...

    def cancel_verdict(self, task_id: str, owner_subject: str | None = None) -> CancellationVerdict: ...

    def steer_task(
        self,
        task_id: str,
        instruction: str,
        owner_subject: str | None = None,
    ) -> TaskSteeringResult | None: ...

    def get_status(self, task_id: str, owner_subject: str | None = None) -> dict[str, object] | None: ...

    def list_tasks(self, limit: int = 20, owner_subject: str | None = None) -> list[dict[str, object]]: ...

    def get_output(self, task_id: str, owner_subject: str | None = None) -> str | None: ...

    def wait_task(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> dict[str, object] | None: ...


class GoalRunnerPort(Protocol):
    def run(self, objective: str, context: Mapping[str, object] | None = None) -> GoalReport: ...

    def render_markdown(self, report: GoalReport) -> str: ...


@final
class AgentRuntime:
    def __init__(
        self,
        orchestrator: OrchestratorPort,
        task_runner: TaskRunnerPort | None = None,
        goal_runner: GoalRunnerPort | None = None,
        task_outcome_recorder: TaskOutcomeRecorder | None = None,
        cognitive_surface: CognitiveSurfaceLike | None = None,
    ) -> None:
        self.is_canonical_runtime = True
        self.orchestrator = orchestrator
        self.task_runner = task_runner
        self.goal_runner = goal_runner or GoalRunner()
        self.cognitive_surface: CognitiveSurfaceLike | None = cognitive_surface
        self._base_outcome_recorder = task_outcome_recorder
        self._direct_tasks = DirectTaskExecution(
            orchestrator,
            task_runner if isinstance(task_runner, TaskStoreRunnerPort) else None,
            self._shadow_observing_recorder(),
        )
        if getattr(orchestrator, "agent_runtime", None) is None:
            setattr(orchestrator, "agent_runtime", self)

    # ── P11: legacy 옆의 opt-in shadow 관찰 ────────────
    def attach_cognitive_surface(self, surface: CognitiveSurfaceLike) -> None:
        """대화/과제 완료 관찰용 surface를 붙인다(설정 OFF면 아무 일도 하지 않는다)."""

        self.cognitive_surface = surface

    def observe_interaction(
        self,
        *,
        episode_id: str,
        context_ref: str,
        goal_ref: str,
        expected_outcome: str = "",
    ) -> ShadowObservation | None:
        """legacy 대화/과제가 **끝난 뒤** shadow episode를 돈다(선택·관찰만).

        surface가 없거나 설정이 OFF면 아무 일도 없고, shadow 실패는 legacy 경로를 절대
        깨지 않는다 — 관찰이 본체를 해치면 관찰이 아니다. ACTIVE는 사람 승인 경로
        (run_active)로만 실행하므로 여기서 조용히 돌지 않는다.
        """

        from antigravity_k.engine.cognitive_surface import SurfaceEpisodeRequest, SurfaceMode

        surface = self.cognitive_surface
        if surface is None:
            return None
        settings = getattr(surface.settings, "effective_mode", SurfaceMode.OFF)
        if str(settings) != str(SurfaceMode.SHADOW):
            return None
        request = SurfaceEpisodeRequest(
            episode_id=episode_id,
            context_ref=context_ref,
            goal_ref=goal_ref,
            expected_outcome=expected_outcome,
        )
        try:
            run = surface.run_shadow(request)
        except Exception:  # noqa: BLE001 — shadow는 legacy를 깨지 않는다(실패는 조용히 녹임)
            logger.warning("cognitive shadow observation failed for %s", episode_id, exc_info=True)
            return None
        return ShadowObservation(
            episode_id=run.episode_id,
            termination=run.termination,
            dispatched_actions=run.dispatched_actions,
            refused_actions=run.refused_actions,
        )

    def _shadow_observing_recorder(self) -> TaskOutcomeRecorder | None:
        """background 과제의 outcome 기록 뒤에 shadow 관찰을 붙인다(기록 자체는 그대로)."""

        base = self._base_outcome_recorder

        def wrapped(outcome: "TaskOutcome") -> "TaskOutcome | None":
            result = base(outcome) if base is not None else None
            case_id = str(getattr(outcome, "case_id", ""))
            self.observe_interaction(
                episode_id=f"task:{case_id}",
                context_ref=f"legacy:task:{case_id}",
                goal_ref=f"legacy:task:{case_id}",
                expected_outcome=str(getattr(outcome, "completion_reason", "")),
            )
            return result

        return wrapped

    def resolve_model(self, target_model: str = "") -> str:
        model = target_model.strip() if target_model else ""
        if model:
            return model
        resolved = self.orchestrator.get_model_for_role("default")
        if not resolved:
            raise RuntimeError("orchestrator did not provide a default model")
        return resolved

    def stream(
        self,
        messages: Sequence[Mapping[str, str]],
        target_model: str = "",
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        yield from self.start_stream(
            messages,
            target_model=target_model,
            max_steps=max_steps,
            ephemeral_message=ephemeral_message,
        ).chunks

    def start_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        target_model: str = "",
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> TrackedStream:
        return self._direct_tasks.start_stream(
            messages,
            target_model=self.resolve_model(target_model),
            max_steps=max_steps,
            ephemeral_message=ephemeral_message,
        )

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        target_model: str = "",
        max_steps: int = 15,
    ) -> str:
        return "".join(self.stream(messages, target_model=target_model, max_steps=max_steps))

    def goal_contract(self, objective: str, context: Mapping[str, object] | None = None) -> str:
        report = self.plan_task(objective, context=context)
        return self.goal_runner.render_markdown(report)

    def plan_task(self, objective: str, context: Mapping[str, object] | None = None) -> GoalReport:
        return self.goal_runner.run(objective, context=context)

    def run_max(self, task_spec: dict[str, object]) -> MaxRunResultPort:
        engine = self.orchestrator.max_engine
        if engine is None:
            raise RuntimeError("max engine is required for MAX execution")
        return self._direct_tasks.run_max(engine, task_spec)

    async def run_parallel_goals(
        self,
        goals: list[dict[str, object]],
        project_root: str,
        base_branch: str = "main",
    ) -> list[object]:
        from antigravity_k.engine.multiplexer import Multiplexer

        multiplexer = Multiplexer(project_root, agent_runtime=self)
        results: list[dict[str, str] | BaseException] = await multiplexer.run_parallel_goals(
            goals,
            base_branch=base_branch,
        )
        return list(results)

    def submit_task(
        self,
        prompt: str,
        context: dict[str, object] | None = None,
        target_model: str = "",
        use_worktree: bool = False,
        idempotency_key: str | None = None,
        owner_subject: str = "loopback",
    ) -> str:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for background task submission")
        execution_context = dict(context or {})
        execution_context["task_plan"] = self.plan_task(prompt, context=execution_context).to_dict()
        task_id = self.task_runner.submit_task(
            prompt=prompt,
            context=execution_context,
            orchestrator=self.orchestrator,
            target_model=self.resolve_model(target_model),
            use_worktree=use_worktree,
            idempotency_key=idempotency_key,
            owner_subject=owner_subject,
        )
        self._record_agency_task_event(task_id, "submitted", prompt, execution_context)
        return task_id

    def resume_task(self, task_id: str, target_model: str = "", owner_subject: str | None = None) -> bool:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for background task resume")
        resumed = self.task_runner.resume_task(
            task_id=task_id,
            orchestrator=self.orchestrator,
            target_model=self.resolve_model(target_model),
            owner_subject=owner_subject,
        )
        self._record_agency_task_event(task_id, "resumed" if resumed else "resume_failed")
        return resumed

    def get_task_status(self, task_id: str, owner_subject: str | None = None) -> dict[str, object] | None:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for task status")
        status = self.task_runner.get_status(task_id, owner_subject=owner_subject)
        if status is not None:
            self._reconcile_agency_task(task_id, status)
        return status

    def submit_next_objective(self, project_id: str, target_model: str = "", use_worktree: bool = False) -> str | None:
        controller = getattr(self.orchestrator, "persistent_agency", None)
        claim = getattr(controller, "claim_next_objective", None)
        binder = getattr(controller, "bind_objective_task", None)
        if not callable(claim) or not callable(binder):
            return None
        objective = claim(project_id)
        if not isinstance(objective, Objective):
            return None
        prompt = objective.title
        if objective.description.strip():
            prompt = f"{prompt}\n\n{objective.description}"
        context: dict[str, object] = {
            "trajectory_id": objective.trajectory_id,
            "persistent_objective_id": objective.objective_id,
        }
        project_context = getattr(controller, "project_context", None)
        if callable(project_context):
            try:
                projection = project_context(project_id, objective.trajectory_id, query=objective.title)
                if isinstance(projection, ProjectedContext) and projection.text:
                    prompt = f"Durable context:\n{projection.text}\n\nObjective:\n{prompt}"
                    context["persistent_context_event_ids"] = list(projection.event_ids)
            except Exception:
                logger.exception("[AgentRuntime] persistent context projection failed")
        try:
            task_id = self.submit_task(prompt, context=context, target_model=target_model, use_worktree=use_worktree)
            _ = binder(task_id, objective.objective_id, project_id, objective.trajectory_id)
            return task_id
        except Exception:
            requeue = getattr(controller, "requeue_objective", None)
            if callable(requeue):
                _ = requeue(objective.objective_id)
            raise

    def reconcile_persistent_objectives(self, project_id: str) -> int:
        if self.task_runner is None:
            return 0
        controller = getattr(self.orchestrator, "persistent_agency", None)
        list_tasks = getattr(controller, "list_objective_tasks", None)
        reconcile = getattr(controller, "reconcile_task_status", None)
        if not callable(list_tasks) or not callable(reconcile):
            return 0
        changed = 0
        try:
            task_ids = _TASK_IDS_ADAPTER.validate_python(list_tasks(project_id))
        except ValidationError:
            return 0
        for task_id in task_ids:
            status = self.task_runner.get_status(task_id)
            state = status.get("status") if status else None
            if isinstance(state, str):
                if state in {"done", "failed", "cancelled"}:
                    self._record_agency_task_result(task_id, state, status or {})
                if reconcile(task_id, state) is True:
                    changed += 1
        return changed

    def list_tasks(self, limit: int = 20, owner_subject: str | None = None) -> list[dict[str, object]]:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for task listing")
        return self.task_runner.list_tasks(limit=limit, owner_subject=owner_subject)

    def get_task_output(self, task_id: str, owner_subject: str | None = None) -> str | None:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for task output")
        return self.task_runner.get_output(task_id, owner_subject=owner_subject)

    def list_task_events(
        self,
        task_id: str,
        after_sequence: int = 0,
        limit: int = 1_000,
        owner_subject: str | None = None,
    ) -> list[ExecutionEventRecord]:
        from antigravity_k.engine.task_state_store import TaskStateStore

        state_store = getattr(self.task_runner, "state_store", None)
        if not isinstance(state_store, TaskStateStore):
            raise RuntimeError("task state store is required for event replay")
        return state_store.list_execution_events(
            task_id,
            after_sequence=after_sequence,
            limit=limit,
            owner_subject=owner_subject,
        )

    def wait_task(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> dict[str, object] | None:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for task wait")
        return self.task_runner.wait_task(task_id, timeout=timeout)

    def cancel_task(self, task_id: str, owner_subject: str | None = None) -> bool:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for background task cancellation")
        cancelled = self.task_runner.cancel_task(task_id, owner_subject=owner_subject)
        self._record_agency_task_event(task_id, "cancelled" if cancelled else "cancel_failed")
        return cancelled

    def cancel_verdict(self, task_id: str, owner_subject: str | None = None) -> CancellationVerdict:
        """취소의 상세 결과 — "활성 아님"과 "다른 살아 있는 프로세스가 실행 중"을 구분한다(F-35)."""
        if self.task_runner is None:
            raise RuntimeError("task runner is required for background task cancellation")
        verdict = self.task_runner.cancel_verdict(task_id, owner_subject=owner_subject)
        self._record_agency_task_event(task_id, "cancelled" if verdict == "cancelled" else "cancel_failed")
        return verdict

    def steer_task(
        self,
        task_id: str,
        instruction: str,
        owner_subject: str | None = None,
    ) -> TaskSteeringResult | None:
        if self.task_runner is None:
            raise RuntimeError("task runner is required for active-turn steering")
        return self.task_runner.steer_task(task_id, instruction, owner_subject=owner_subject)

    def _record_agency_task_event(
        self,
        task_id: str,
        status: str,
        prompt: str = "",
        context: Mapping[str, object] | None = None,
    ) -> None:
        controller = getattr(self.orchestrator, "persistent_agency", None)
        recorder = getattr(controller, "record_task_event", None)
        project_id = getattr(controller, "project_id", None) or getattr(self.orchestrator, "project_root", None)
        if not callable(recorder) or not isinstance(project_id, str) or not project_id.strip():
            return
        trajectory_id = context.get("trajectory_id", "main") if context else "main"
        if not isinstance(trajectory_id, str) or not trajectory_id.strip():
            trajectory_id = "main"
        try:
            _ = recorder(project_id, trajectory_id, task_id, status, prompt)
        except Exception:
            logger.exception("[AgentRuntime] persistent agency event record failed")

    def _reconcile_agency_task(self, task_id: str, status: Mapping[str, object]) -> None:
        controller = getattr(self.orchestrator, "persistent_agency", None)
        reconcile = getattr(controller, "reconcile_task_status", None)
        if not callable(reconcile):
            return
        state = status.get("status")
        if isinstance(state, str):
            try:
                if state in {"done", "failed", "cancelled"}:
                    self._record_agency_task_result(task_id, state, status)
                _ = reconcile(task_id, state)
            except Exception:
                logger.exception("[AgentRuntime] persistent agency objective reconciliation failed")

    def _record_agency_task_result(self, task_id: str, state: str, status: Mapping[str, object]) -> None:
        controller = getattr(self.orchestrator, "persistent_agency", None)
        recorder = getattr(controller, "record_task_result", None)
        if not callable(recorder):
            return
        output = self.task_runner.get_output(task_id) if self.task_runner is not None and state == "done" else ""
        error = status.get("error", "")
        try:
            _ = recorder(
                task_id, state, output if isinstance(output, str) else "", error if isinstance(error, str) else ""
            )
        except Exception:
            logger.exception("[AgentRuntime] persistent agency task result recording failed")


__all__ = ["AgentRuntime", "GoalRunnerPort", "OrchestratorPort", "TaskRunnerPort", "TrackedStream"]
