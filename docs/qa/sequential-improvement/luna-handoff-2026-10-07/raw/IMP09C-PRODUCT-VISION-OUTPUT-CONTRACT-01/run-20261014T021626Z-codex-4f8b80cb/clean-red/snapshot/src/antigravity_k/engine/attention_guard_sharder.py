"""Bidirectional Attention-Guarded Context Sharder — Lost-in-the-Middle immunity for 27B.

Technology Origin: "Lost in the Middle" Attention Distribution Studies.
27B Transformer attention is strongest at the extreme beginning (Primacy)
and extreme end (Recency) of the context window.

This module implements Bidirectional Sandwich Pinning:
1. Primacy Block (Top): Pinned system identity & architectural rules
2. Core Body (Middle): High-density code diffs and documentation
3. Recency Anchor (Bottom): Explicit final constraints and tool output schema
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ShardedPrompt:
    """A sandwich-structured prompt guaranteed to maximize 27B instruction adherence."""

    primacy_block: str
    body_content: str
    recency_anchor: str
    full_prompt: str


class AttentionGuardSharder:
    """Enforces bidirectional sandwich pinning to prevent attention dilution."""

    @staticmethod
    def create_sandwich_prompt(
        system_rules: str,
        body_context: str,
        critical_constraints: list[str],
        user_objective: str,
    ) -> ShardedPrompt:
        """Construct an attention-optimized bidirectional prompt.

        Args:
            system_rules: Base role identity and capabilities.
            body_context: Surrounding files, diffs, and tool history.
            critical_constraints: Hard negative rules that must never be broken.
            user_objective: The specific user goal.

        Returns:
            ShardedPrompt with sandwich pinning.
        """
        # 1. Primacy Block (Top of Context)
        primacy_lines = [
            "<!-- PRIMACY_ATTENTION_BLOCK: CRITICAL SYSTEM CONTRACT -->",
            "🛡️ **[SYSTEM CONTRACT & ARCHITECTURE RULES]**",
            system_rules.strip(),
            "<!-- END_PRIMACY_BLOCK -->\n",
        ]
        primacy_text = "\n".join(primacy_lines)

        # 2. Recency Anchor (Bottom of Context - Right before generation)
        recency_lines = [
            "\n<!-- RECENCY_ATTENTION_ANCHOR: FINAL MUST-FOLLOW DIRECTIVES -->",
            "🎯 **[IMMEDIATE TASK & HARD CONSTRAINTS]**",
            f"Objective: {user_objective}",
        ]
        if critical_constraints:
            recency_lines.append("🚨 ABSOLUTE CONSTRAINTS (DO NOT VIOLATE):")
            for c in critical_constraints:
                recency_lines.append(f"  ❌ {c}")

        recency_lines.append("⚡ Generate precise, surgical actions now.")
        recency_lines.append("<!-- END_RECENCY_ANCHOR -->")
        recency_text = "\n".join(recency_lines)

        full = f"{primacy_text}\n{body_context.strip()}\n{recency_text}"

        return ShardedPrompt(
            primacy_block=primacy_text,
            body_content=body_context,
            recency_anchor=recency_text,
            full_prompt=full,
        )
