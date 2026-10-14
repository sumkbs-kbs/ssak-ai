"""Self-Evolving Prompt Compiler — Autonomous DSPy-style prompt optimizer for 27B.

Analyzes passed task trajectories and failure reflexions to continuously refine,
specialize, and compile role prompt markdown files in `prompts/roles/`.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import final

logger = logging.getLogger(__name__)


@dataclass
class TrajectoryRecord:
    """A recorded task trajectory and its test outcome."""

    role: str
    user_prompt: str
    successful_action: str
    failing_action: str = ""
    lesson_learned: str = ""


@final
class PromptCompiler:
    """Compiles golden task trajectories into optimized, high-density system prompts."""

    def __init__(self, prompts_dir: str | Path):
        self.prompts_dir: Path = Path(prompts_dir).resolve()
        self.trajectories: list[TrajectoryRecord] = []

    def record_trajectory(
        self,
        role: str,
        user_prompt: str,
        successful_action: str,
        failing_action: str = "",
        lesson: str = "",
    ) -> None:
        """Record a successful execution pattern."""
        self.trajectories.append(
            TrajectoryRecord(
                role=role,
                user_prompt=user_prompt,
                successful_action=successful_action,
                failing_action=failing_action,
                lesson_learned=lesson,
            )
        )

    def compile_optimized_prompt(self, role: str, base_instructions: str) -> str:
        """Compile base instructions with extracted few-shot patterns and negative rules."""
        role_trajectories = [t for t in self.trajectories if t.role.lower() == role.lower()]

        lines = [
            "---",
            f"role: {role.lower()}",
            "optimized_by: Ssak-Ai PromptCompiler (27B Tuning)",
            "---",
            base_instructions.strip(),
        ]

        if role_trajectories:
            lines.append("\n## Proven Golden Execution Patterns (Few-Shot)")
            for idx, t in enumerate(role_trajectories[-3:], 1):
                lines.append(f"### Pattern {idx}: {t.user_prompt[:80]}")
                lines.append(f"Action: `{t.successful_action}`")
                if t.failing_action:
                    lines.append(f"Avoid: `{t.failing_action}`")
                if t.lesson_learned:
                    lines.append(f"Constraint: {t.lesson_learned}")

        return "\n".join(lines)

    def save_compiled_prompt(self, role: str, compiled_content: str) -> Path:
        """Save the compiled prompt to disk under prompts/roles/."""
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.prompts_dir / f"{role.lower()}.md"
        _ = target_path.write_text(compiled_content, encoding="utf-8")
        logger.info("Compiled and updated prompt for role '%s' at %s", role, target_path)
        return target_path
