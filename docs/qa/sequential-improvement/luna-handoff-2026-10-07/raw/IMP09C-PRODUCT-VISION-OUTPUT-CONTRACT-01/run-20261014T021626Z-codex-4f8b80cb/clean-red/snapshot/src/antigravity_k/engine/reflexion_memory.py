"""Episodic Reflexion & Negative-Constraint Memory — Self-Correction Engine for 27B.

When a 27B model makes a mistake (e.g. invalid import, wrong API call, failing test),
standard conversation history can cause it to repeat the mistake due to attention bias.

ReflexionMemory compiles failures into explicit Negative Constraints:
- "⚠️ NEGATIVE CONSTRAINT: In step X, attempting `foo()` failed because `bar`. DO NOT repeat this approach. Use `baz` instead."
"""

import time
from dataclasses import dataclass, field


@dataclass
class FailureEpisode:
    """A recorded failure and its diagnosed lesson."""

    context: str
    attempted_action: str
    failure_reason: str
    negative_constraint: str
    timestamp: float = field(default_factory=time.time)


class ReflexionMemory:
    """Stores and injects hard negative constraints from previous failures into future prompts."""

    def __init__(self, max_episodes: int = 5) -> None:
        self.episodes: list[FailureEpisode] = []
        self.max_episodes: int = max_episodes

    def record_failure(
        self,
        context: str,
        attempted_action: str,
        failure_reason: str,
        suggested_alternative: str = "",
    ) -> FailureEpisode:
        """Record an error and generate an explicit negative constraint."""
        constraint = f"DO NOT attempt '{attempted_action}'. It failed with error: '{failure_reason}'. "
        if suggested_alternative:
            constraint += f"Instead, use: '{suggested_alternative}'."

        episode = FailureEpisode(
            context=context,
            attempted_action=attempted_action,
            failure_reason=failure_reason,
            negative_constraint=constraint,
        )

        self.episodes.append(episode)
        if len(self.episodes) > self.max_episodes:
            _ = self.episodes.pop(0)

        return episode

    def render_negative_constraints_prompt(self) -> str:
        """Render active negative constraints block for LLM prompt injection."""
        if not self.episodes:
            return ""

        lines = [
            "<!-- REFLEXION_ACTIVE_NEGATIVE_CONSTRAINTS -->",
            "🚨 **CRITICAL: PAST MISTAKES TO AVOID (NEGATIVE CONSTRAINTS)**",
        ]
        for idx, ep in enumerate(self.episodes, 1):
            lines.append(f"{idx}. {ep.negative_constraint}")
        lines.append("<!-- END_REFLEXION_CONSTRAINTS -->")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all active reflexion episodes."""
        self.episodes.clear()
