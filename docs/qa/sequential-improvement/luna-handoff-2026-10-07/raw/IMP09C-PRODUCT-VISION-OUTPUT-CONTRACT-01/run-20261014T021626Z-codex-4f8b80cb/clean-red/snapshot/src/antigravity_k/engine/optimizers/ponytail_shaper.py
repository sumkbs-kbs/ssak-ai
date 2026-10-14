"""Ponytail Shaper — Lazy-Senior-Developer system directive injector.

Inspired by DietrichGebert/ponytail.
Suppresses over-engineering by enforcing a strict YAGNI -> reuse -> stdlib -> minimal code ladder.
"""

from __future__ import annotations

from typing import cast

LAZY_SENIOR_DIRECTIVE: str = (
    "You operate in lazy-senior-developer mode. Lazy means efficient, never careless. "
    "The best code is the code never written. Before writing any code, climb this ladder "
    "and stop at the first rung that holds:\n"
    "1. Does this need to be built at all? (YAGNI)\n"
    "2. Does it already exist in this codebase? Reuse the existing helper or pattern.\n"
    "3. Does the standard library already do this? Use it.\n"
    "4. Does an installed dependency solve it? Use it.\n"
    "5. Can this be one line? Make it one line.\n"
    "6. Only then: write the minimum code that works.\n"
    "Rules: no abstractions that were not explicitly requested; no new dependency if "
    "avoidable; deletion over addition; fewest files possible; shortest working diff wins. "
    "A bug fix targets the root cause, not the symptom. Not lazy about: understanding the "
    "problem fully, input validation at trust boundaries, error handling that prevents "
    "data loss, security."
)


def ponytail_system_prefix() -> str:
    """Return the raw lazy-senior-developer directive string."""
    return LAZY_SENIOR_DIRECTIVE


def apply_ponytail(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Inject lazy-senior-developer thinking ladder into message history.

    Idempotent: will not duplicate if already present.
    """
    if not messages:
        return messages
    directive = LAZY_SENIOR_DIRECTIVE
    first = messages[0]
    if first.get("role") == "system":
        existing = cast(str, first.get("content", ""))
        if "lazy-senior-developer" not in existing:
            updated_first: dict[str, object] = {**first, "content": f"{existing}\n\n{directive}"}
            return [updated_first, *messages[1:]]
        return list(messages)

    system_msg: dict[str, object] = {"role": "system", "content": directive}
    return [system_msg, *messages]
