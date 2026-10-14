"""Smart Breakpoint & Clarification Gate — Intelligent human-in-the-loop decision gate.

Prevents wasted loops when tasks encounter severe ambiguity, missing credentials,
or 3+ consecutive test failures by synthesizing a crisp, multiple-choice decision prompt.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClarificationOption:
    """A distinct option presented to the user."""

    option_id: str
    description: str
    action_payload: str


@dataclass
class BreakpointDecisionPrompt:
    """The synthesized structured decision prompt."""

    trigger_reason: str
    core_question: str
    options: list[ClarificationOption] = field(default_factory=list)

    def format_interactive_dialog(self) -> str:
        """Format a clean, keyboard-friendly terminal/UI prompt."""
        lines = [
            f"🛑 **[Agent Decision Breakpoint: {self.trigger_reason}]**",
            f"❓ {self.core_question}",
            "\nPlease select an option to proceed:",
        ]
        for opt in self.options:
            lines.append(f"  [{opt.option_id}] {opt.description}")
        return "\n".join(lines)


class SmartBreakpointGate:
    """Monitors consecutive failure counts and ambiguity to trigger smart breakpoints."""

    def __init__(self, max_consecutive_failures: int = 3) -> None:
        self.max_consecutive_failures: int = max_consecutive_failures
        self._consecutive_failures: int = 0

    def record_attempt(self, success: bool) -> bool:
        """Record attempt outcome. Returns True if a breakpoint must be triggered."""
        if success:
            self._consecutive_failures = 0
            return False
        else:
            self._consecutive_failures += 1
            return self._consecutive_failures >= self.max_consecutive_failures

    def generate_breakpoint(
        self,
        task_context: str,
        failing_error: str,
        possible_approaches: list[tuple[str, str]],
    ) -> BreakpointDecisionPrompt:
        """Construct a structured multiple-choice decision prompt."""
        options = [
            ClarificationOption(
                option_id=str(idx),
                description=desc,
                action_payload=payload,
            )
            for idx, (desc, payload) in enumerate(possible_approaches, 1)
        ]
        # Add default rollback/abort option
        options.append(
            ClarificationOption(
                option_id=str(len(options) + 1),
                description="Abort current subgoal and revert changes",
                action_payload="abort",
            )
        )

        return BreakpointDecisionPrompt(
            trigger_reason=f"Subgoal failed {self._consecutive_failures} times: {failing_error[:80]}",
            core_question=f"How should the agent resolve the impasse in '{task_context}'?",
            options=options,
        )
