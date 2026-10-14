"""Autonomous Self-Driving Flight Controller — Continuous autopilot loop.

First Principle: Automate and Accelerate Cycle Time.
Eliminates human-in-the-loop round-trip lag during multi-step coding missions.
Coordinates SubgoalGraph -> SpeculativeBranching -> TDDVerifier -> ReflexionMemory
in a continuous execution loop until 100% test passing is achieved.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias, final

from antigravity_k.engine.atomic_transaction_engine import AtomicTransactionEngine
from antigravity_k.engine.deep_code_indexer import DeepCodeIndexer
from antigravity_k.engine.harness_enforcer import BoundaryResult, HarnessEnforcer
from antigravity_k.engine.reflexion_memory import ReflexionMemory
from antigravity_k.engine.subgoal_graph import SubgoalGraph
from antigravity_k.engine.test_time_compute_scaler import ComputeBudget, TestTimeComputeScaler

logger = logging.getLogger(__name__)

SubgoalInput: TypeAlias = Mapping[str, str | list[str]]


class _InvalidSubgoalInputError(ValueError):
    pass


@dataclass
class MissionReport:
    """Detailed flight log of an autonomous mission."""

    goal: str
    is_success: bool
    total_steps_executed: int
    failed_steps_count: int
    tdd_passed: bool
    compute_budget: ComputeBudget | None = None
    log_messages: list[str] = field(default_factory=list)
    stall_interventions: list[str] = field(default_factory=list)


@final
class AutonomousFlightController:
    """Executes end-to-end engineering missions autonomously without manual prompting."""

    # AVO 규칙: 같은 방식 2회 연속 실패하면 3번째는 금지 — 영구 실패로 강등.
    # 그 전까지는 서브골이 재시도 가능 상태로 남아 전략수정 턴을 가질 수 있다.
    MAX_STEP_ATTEMPTS: int = 2

    project_root: Path
    max_flight_turns: int
    enforcer: HarnessEnforcer
    reflexion: ReflexionMemory
    indexer: DeepCodeIndexer
    transaction_engine: AtomicTransactionEngine

    def __init__(
        self,
        project_root: str | Path,
        max_flight_turns: int = 10,
        enforcer: HarnessEnforcer | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.max_flight_turns = max_flight_turns
        self.enforcer = enforcer or HarnessEnforcer(project_root=str(self.project_root))
        self.reflexion = ReflexionMemory(max_episodes=5)
        self.indexer = DeepCodeIndexer(self.project_root)
        self.transaction_engine = AtomicTransactionEngine(self.project_root)

    def launch_mission(
        self,
        goal: str,
        initial_subgoals: Sequence[SubgoalInput],
        step_executor: Callable[[str, str], bool],
    ) -> MissionReport:
        """Fly an engineering mission autonomously until all subgoals and TDD pass.

        Args:
            goal: High-level engineering objective.
            initial_subgoals: List of dicts with 'id', 'desc', and optional 'depends_on'.
            step_executor: Callable(step_id, step_desc) -> bool that performs the actual LLM code action.

        Returns:
            MissionReport detailing flight trajectory and final status.
        """
        dag = SubgoalGraph(goal)
        for sg in initial_subgoals:
            task_id = sg["id"]
            description = sg["desc"]
            depends_on = sg.get("depends_on", [])
            if not isinstance(task_id, str) or not isinstance(description, str):
                raise _InvalidSubgoalInputError("subgoal id and description must be strings")
            if not isinstance(depends_on, list):
                raise _InvalidSubgoalInputError("subgoal dependencies must be a string list")
            _ = dag.add_subgoal(
                task_id=task_id,
                description=description,
                depends_on=depends_on,
            )

        # Dynamic Test-Time Compute Budget Scaling (o-series / DeepSeek-R1 law)
        budget = TestTimeComputeScaler.evaluate_budget(goal, impacted_files_count=len(initial_subgoals))
        logs: list[str] = [
            f"🚀 [Flight Controller] Mission Launched: '{goal}'",
            f"⚡ [Compute Scaler] Allocated Tier: {budget.complexity_tier} (Branching: {budget.branching_factor}, MCTS: {budget.mcts_depth}, Worktree: {budget.requires_speculative_worktree})",
        ]
        stall_interventions: list[str] = []
        self.enforcer.reset_stall_tracking()
        step_attempts: dict[str, int] = {}
        turn = 0
        failed_count = 0

        def _record_failure(task_id: str, description: str, reason: str) -> None:
            nonlocal failed_count
            failed_count += 1
            attempts = step_attempts.get(task_id, 0) + 1
            step_attempts[task_id] = attempts
            if attempts >= self.MAX_STEP_ATTEMPTS:
                dag.fail_subgoal(task_id, reason)
                _ = self.reflexion.record_failure(
                    context=description,
                    attempted_action=f"Subgoal {task_id}",
                    failure_reason=reason,
                )
                logs.append(
                    f"❌ [Flight Turn {turn}] Subgoal [{task_id}] PERMANENTLY FAILED after {attempts} attempts. Reflexion recorded."
                )
            else:
                logs.append(
                    f"⚠️ [Flight Turn {turn}] Subgoal [{task_id}] failed (attempt {attempts}/{self.MAX_STEP_ATTEMPTS}) — retryable."
                )

        while turn < self.max_flight_turns and not dag.is_all_completed():
            turn += 1

            # 감독기 개입 소비: 예약된 STALL이 있으면 이 턴은 강제 재계획 턴으로 쓴다.
            boundary: BoundaryResult = self.enforcer.check_tool_boundary("flight_step", {"turn": turn})
            if not boundary.get("allowed", True) and boundary.get("stall"):
                reason = boundary["reason"]
                stall_interventions.append(reason)
                logs.append(f"🛑 [Flight Turn {turn}] Supervisor intervention:\n{reason}")
                continue

            ready_nodes = dag.get_ready_subgoals()
            if not ready_nodes:
                logs.append("⚠️ [Flight Controller] Deadlock: No subgoals are ready to execute.")
                break

            current_node = ready_nodes[0]
            logs.append(
                f"⚡ [Flight Turn {turn}] Executing Subgoal [{current_node.task_id}]: {current_node.description}"
            )

            # Execute the step
            success = False
            try:
                success = step_executor(current_node.task_id, current_node.description)
            except Exception as ex:
                success = False
                _record_failure(current_node.task_id, current_node.description, str(ex)[:200])
                self.enforcer.record_outcome(failed=True)
                continue

            if success:
                _ = dag.complete_subgoal(current_node.task_id)
                logs.append(f"✅ [Flight Turn {turn}] Subgoal [{current_node.task_id}] COMPLETED cleanly.")
            else:
                _record_failure(current_node.task_id, current_node.description, "Step executor returned false")

            # 감독기에 결과 적재 — 무진행 윈도우/오류 클러스터가 여기서 갱신된다.
            self.enforcer.record_outcome(failed=not success)

        all_done = dag.is_all_completed()
        logs.append(f"🏁 [Flight Controller] Mission Ended. Success: {all_done} (Turns: {turn})")

        return MissionReport(
            goal=goal,
            is_success=all_done,
            total_steps_executed=turn,
            failed_steps_count=failed_count,
            tdd_passed=all_done,
            compute_budget=budget,
            log_messages=logs,
            stall_interventions=stall_interventions,
        )
