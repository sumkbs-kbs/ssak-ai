"""Adaptive Test-Time Compute Scaler — Inference-Time Compute Scaling Law for 27B.

Technology Origin: OpenAI o-series (o1/o3) / DeepSeek-R1 Test-Time Scaling Laws.
Dynamically scales search compute (MCTS rollout depth, speculative branch factor,
and verification rigor) based on task complexity.

Ensures 27B spends more compute/time on hard tasks to match GPT-5/Claude 4.8.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputeBudget:
    """Allocated compute parameters for a specific engineering task."""

    complexity_tier: str  # "SIMPLE", "MODERATE", "COMPLEX", "EXTREME"
    branching_factor: int  # 1 to 5 candidate hypotheses
    mcts_depth: int  # 2 to 10 iterations
    reflection_max_retries: int  # 1 to 5 retries
    temperature: float  # 0.2 (deterministic) to 0.8 (exploratory)
    requires_speculative_worktree: bool


class TestTimeComputeScaler:
    """Evaluates task complexity and assigns optimal inference-time compute budget."""

    @staticmethod
    def evaluate_budget(
        user_task: str,
        impacted_files_count: int = 1,
        cyclomatic_hint: int = 1,
    ) -> ComputeBudget:
        """Calculate the required test-time compute allocation.

        Args:
            user_task: Natural language goal description.
            impacted_files_count: Number of files in the blast radius.
            cyclomatic_hint: Estimated complexity metric.

        Returns:
            ComputeBudget parameter set.
        """
        task_lower = user_task.lower()

        # Complexity Scoring Factors
        score = 0
        if any(w in task_lower for w in ("refactor", "architecture", "rewrite", "concurrency", "async", "security")):
            score += 3
        if any(w in task_lower for w in ("fix", "bug", "error", "failing", "broken")):
            score += 2
        if impacted_files_count > 3:
            score += 3
        elif impacted_files_count > 1:
            score += 1
        if cyclomatic_hint > 5:
            score += 2

        # 공통 복잡도 추정기(chain_of_verification.estimate_complexity)와
        # 정합 — 두 추정기가 상반된 판정을 내지 않도록, 공통 추정기가
        # 명확히 복잡(0.6+)으로 보는 과제는 최소 MODERATE(score 2)로 올린다.
        try:
            from antigravity_k.engine.chain_of_verification_models import estimate_complexity

            if estimate_complexity(user_task) >= 0.6:
                score = max(score, 2)
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - 선택적 신호
            pass

        # Map score to ComputeBudget
        if score >= 6:
            return ComputeBudget(
                complexity_tier="EXTREME",
                branching_factor=5,
                mcts_depth=10,
                reflection_max_retries=5,
                temperature=0.8,
                requires_speculative_worktree=True,
            )
        elif score >= 4:
            return ComputeBudget(
                complexity_tier="COMPLEX",
                branching_factor=3,
                mcts_depth=6,
                reflection_max_retries=3,
                temperature=0.7,
                requires_speculative_worktree=True,
            )
        elif score >= 2:
            return ComputeBudget(
                complexity_tier="MODERATE",
                branching_factor=2,
                mcts_depth=4,
                reflection_max_retries=2,
                temperature=0.4,
                requires_speculative_worktree=False,
            )
        else:
            return ComputeBudget(
                complexity_tier="SIMPLE",
                branching_factor=1,
                mcts_depth=2,
                reflection_max_retries=1,
                temperature=0.2,
                requires_speculative_worktree=False,
            )
