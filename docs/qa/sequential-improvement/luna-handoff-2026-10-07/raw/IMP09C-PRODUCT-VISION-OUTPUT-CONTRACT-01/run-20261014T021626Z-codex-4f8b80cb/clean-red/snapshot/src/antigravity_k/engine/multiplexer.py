"""Token-stream multiplexer for merging parallel model outputs."""

import asyncio
import logging
from collections.abc import Awaitable, Mapping, Sequence
from typing import Protocol

from antigravity_k.engine.goal_runner import GoalRunner
from antigravity_k.engine.worktree_manager import WorktreeManager

logger = logging.getLogger(__name__)
_MAX_PARALLEL_GOALS = 32


class AgentRuntime(Protocol):
    def goal_contract(self, objective: str, context: Mapping[str, object] | None = None) -> object: ...


class Multiplexer:
    """다중 에이전트를 병렬로 스폰(Spawn)하고 관리하는 오케스트레이터입니다.

    각 에이전트는 자신만의 격리된 Git Worktree 샌드박스에서 실행됩니다.
    """

    def __init__(self, project_root: str, agent_runtime: AgentRuntime | None = None):
        """Initialize the Multiplexer.

        Args:
            project_root (str): str project root.

        """
        self.project_root: str = project_root
        self.agent_runtime: AgentRuntime | None = agent_runtime
        self.worktree_manager: WorktreeManager = WorktreeManager(base_repo_path=project_root)
        self.active_runners: list[GoalRunner] = []

    async def run_parallel_goals(
        self,
        goals: Sequence[Mapping[str, object]],
        base_branch: str = "main",
    ) -> list[dict[str, str] | BaseException]:
        """주어진 여러 목표(Goal)들을 각각 독립된 에이전트(GoalRunner)에게 할당하여.

        비동기적으로 동시에 실행합니다.

        goals 예시:
        [
            {"task_id": "feature-ui", "instruction": "Make login page"},
            {"task_id": "feature-api", "instruction": "Write backend logic"}
        ]
        """
        if len(goals) > _MAX_PARALLEL_GOALS:
            raise ValueError(f"병렬 목표 수는 최대 {_MAX_PARALLEL_GOALS}개까지 허용됩니다")
        logger.info("[Multiplexer] Spawning %s parallel agents...", len(goals))

        tasks: list[Awaitable[dict[str, str]]] = []
        for goal in goals:
            raw_task_id = goal.get("task_id")
            task_id = raw_task_id if isinstance(raw_task_id, str) and raw_task_id else f"task-{id(goal)}"
            raw_instruction = goal.get("instruction", "")
            instruction = raw_instruction if isinstance(raw_instruction, str) else str(raw_instruction)

            # 1. 샌드박스(Worktree) 생성
            worktree_path = self.worktree_manager.create_worktree(
                branch_name=task_id,
                base_branch=base_branch,
            )

            if self.agent_runtime is None:
                runner = GoalRunner(instruction=instruction)
                runner.workspace_dir = worktree_path
                self.active_runners.append(runner)
                tasks.append(self._run_single_agent(runner, worktree_path))
            else:
                tasks.append(self._run_runtime_goal(task_id, instruction, worktree_path))

        # 모든 에이전트 동시 실행 대기
        results: list[dict[str, str] | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("[Multiplexer] All parallel agents have completed their tasks.")
        return results

    async def _run_runtime_goal(self, task_id: str, instruction: str, worktree_path: str) -> dict[str, str]:
        try:
            runtime = self.agent_runtime
            if runtime is None:
                raise RuntimeError("agent runtime is not configured")
            _ = await asyncio.to_thread(
                runtime.goal_contract,
                instruction,
                {"task_id": task_id, "workspace_dir": worktree_path},
            )
            return {"task_id": task_id, "status": "success"}
        except Exception as e:
            logger.exception("[%s] Runtime goal failed", task_id)
            return {"task_id": task_id, "status": "failed", "error": str(e)}

    async def _run_single_agent(self, runner: GoalRunner, worktree_path: str) -> dict[str, str]:
        """개별 에이전트 실행 래퍼 로직."""
        try:
            logger.info("[%s] Agent started in %s", runner.task_id, worktree_path)
            # 기존 GoalRunner의 비동기 실행 훅 (예: execute_plan)
            # 현재 GoalRunner 구현체에 맞춰 run() 혹은 execute()를 호출
            _ = await asyncio.to_thread(runner.run, runner.instruction)
            logger.info("[%s] Agent successfully finished.", runner.task_id)
            return {"task_id": runner.task_id, "status": "success"}
        except Exception as e:
            logger.exception("[%s] Agent failed", runner.task_id)
            return {"task_id": runner.task_id, "status": "failed", "error": str(e)}
        finally:
            # 작업이 끝났으므로 해당 워크트리 정리 가능 (옵션에 따라 유지)
            # 여기서는 히스토리 보존을 위해 삭제하지 않거나 옵셔널로 남겨둠
            pass
