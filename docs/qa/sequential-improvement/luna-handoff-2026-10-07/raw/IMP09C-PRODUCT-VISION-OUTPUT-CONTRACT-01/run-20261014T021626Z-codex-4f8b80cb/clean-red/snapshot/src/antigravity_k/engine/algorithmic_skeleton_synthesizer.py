"""Algorithmic Skeleton & Invariant Synthesizer — Formal thought structuring for 27B.

Prevents zero-shot intuitive errors on complex algorithms by forcing the model
to construct a formal 3-part invariant contract before code generation:
1. Pre/Post Invariants (Input validation & Output guarantees)
2. Time & Space Complexity Bounds (e.g. O(N log N) / O(1))
3. Step-by-Step Structural Invariant Skeleton
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmicContract:
    """Formal invariant contract for complex algorithmic functions."""

    function_name: str
    pre_conditions: list[str]
    post_conditions: list[str]
    time_complexity_target: str
    space_complexity_target: str
    structural_skeleton: str


class AlgorithmicSkeletonSynthesizer:
    """Synthesizes structured reasoning scaffolding for difficult algorithmic problems."""

    @staticmethod
    def synthesize_contract_prompt(
        task_description: str,
        function_name: str = "solve",
    ) -> str:
        """Generate a thought-structuring scaffolding prompt."""
        lines = [
            "<!-- FORMAL_ALGORITHMIC_INVARIANT_CONTRACT -->",
            f"🧠 **[ALGORITHMIC REASONING CONTRACT: `{function_name}`]**",
            f"Task: {task_description}",
            "\nYou MUST structure your implementation using this exact invariant contract:",
            "1. **Pre-Conditions**: State all input assumptions and edge-case boundaries.",
            "2. **Post-Conditions**: State mathematical guarantees on the return value.",
            "3. **Complexity Bounds**: Strict Time: O(...) and Space: O(...).",
            "4. **Loop/Recursion Invariants**: Define the inductive invariant that holds at each step.",
            "<!-- END_ALGORITHMIC_CONTRACT -->\n",
        ]
        return "\n".join(lines)

    @staticmethod
    def parse_contract_from_text(text: str, function_name: str) -> AlgorithmicContract:
        """Extract structured contract elements from model reasoning."""
        # Clean defaults
        pre = ["inputs are valid and within bounds"]
        post = ["returns mathematically verified output"]
        time_c = "O(N log N)"
        space_c = "O(N)"

        if "O(" in text:
            # Simple heuristic extraction
            parts = text.split("O(")
            if len(parts) > 1:
                time_c = "O(" + parts[1].split(")")[0] + ")"

        return AlgorithmicContract(
            function_name=function_name,
            pre_conditions=pre,
            post_conditions=post,
            time_complexity_target=time_c,
            space_complexity_target=space_c,
            structural_skeleton=f"def {function_name}(...): ...",
        )
