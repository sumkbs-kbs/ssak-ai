from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from antigravity_k.engine.memory_conflicts import (
    MemoryRecallFragment,
    MemoryResolution,
    resolve_memory_conflicts,
)
from antigravity_k.engine.memory_contracts import MemoryFact

DEFAULT_MEMORY_RECALL_MAX_CHARACTERS: Final[int] = 12_000


class InvalidMemoryRecallBudgetError(ValueError):
    def __init__(self, max_characters: int) -> None:
        super().__init__(f"max_characters must be non-negative, got {max_characters}")


@dataclass(frozen=True, slots=True)
class MemoryRecallBudget:
    max_characters: int = DEFAULT_MEMORY_RECALL_MAX_CHARACTERS

    def __post_init__(self) -> None:
        if self.max_characters < 0:
            raise InvalidMemoryRecallBudgetError(self.max_characters)


def compose_bounded_recall(
    query: str,
    provider_facts: tuple[MemoryFact, ...],
    fragments: tuple[MemoryRecallFragment, ...],
    budget: MemoryRecallBudget,
) -> MemoryResolution:
    if budget.max_characters == 0:
        return MemoryResolution(context="", conflicts=())

    selected: list[MemoryRecallFragment] = []
    seen_contents: set[str] = set()
    for fragment in fragments:
        if fragment.content in seen_contents:
            continue
        seen_contents.add(fragment.content)
        candidate = tuple(selected + [fragment])
        resolved = resolve_memory_conflicts(query, candidate, provider_facts)
        if len(resolved.context) <= budget.max_characters:
            selected.append(fragment)

    resolved = resolve_memory_conflicts(query, tuple(selected), provider_facts)
    if len(resolved.context) > budget.max_characters:
        return MemoryResolution(context="", conflicts=())
    return resolved
