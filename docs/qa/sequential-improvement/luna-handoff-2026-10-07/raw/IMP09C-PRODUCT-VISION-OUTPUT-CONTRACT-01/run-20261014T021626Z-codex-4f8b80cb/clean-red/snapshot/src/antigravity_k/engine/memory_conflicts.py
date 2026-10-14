from __future__ import annotations

import re
import time
from dataclasses import dataclass

from antigravity_k.engine.identity_memory import extract_identity_facts
from antigravity_k.engine.memory_contracts import (
    MemoryFact,
    MemoryFactAuthority,
)
from antigravity_k.engine.preference_memory import extract_explicit_preference_facts
from antigravity_k.engine.project_memory import extract_project_memory_facts
from antigravity_k.engine.project_memory_keys import canonical_project_record_key

_IDENTITY_MARKER = re.compile(r"\[identity:(?P<key>[^\]]+)]\s*(?P<value>.+)")
_PREFERENCE_MARKER = re.compile(r"\[preference:(?P<key>[^\]]+)]\s*(?P<value>.+)")
_PROJECT_MARKER = re.compile(r"\[project:(?P<key>[^\]]+)]\s*(?P<value>.+)")
_RECORD_START = re.compile(r"(?:^|]\s*)Q:\s|^\s*(?:📌\s*)?user:\s", re.IGNORECASE)
_RECORD_END = re.compile(r"^\s*(?:A|assistant):\s", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MemoryRecallFragment:
    provider: str
    content: str


@dataclass(frozen=True, slots=True)
class MemoryConflict:
    key: str
    selected_source: str
    selected_scope: str
    suppressed_records: int


@dataclass(frozen=True, slots=True)
class MemoryDeduplication:
    key: str
    selected_source: str
    selected_scope: str
    suppressed_records: int


@dataclass(frozen=True, slots=True)
class MemoryResolution:
    context: str
    conflicts: tuple[MemoryConflict, ...]
    deduplications: tuple[MemoryDeduplication, ...] = ()


def resolve_memory_conflicts(
    query: str,
    fragments: tuple[MemoryRecallFragment, ...],
    provider_facts: tuple[MemoryFact, ...],
) -> MemoryResolution:
    candidates = provider_facts + _query_facts(query)
    winners = _select_winners(candidates)
    conflict_keys, duplicate_keys = _find_resolution_keys(fragments, candidates, winners)
    resolution_keys = conflict_keys | duplicate_keys
    if not resolution_keys:
        return MemoryResolution(
            context="\n\n".join(fragment.content for fragment in fragments),
            conflicts=(),
        )

    filtered: list[str] = []
    suppressed_by_key = {key: 0 for key in resolution_keys}
    for fragment in fragments:
        content, suppressed = _filter_fragment(fragment.content, resolution_keys)
        if content:
            filtered.append(content)
        for key, count in suppressed.items():
            suppressed_by_key[key] += count

    selected_facts = [winners[key] for key in sorted(resolution_keys)]
    prefix = ["[Resolved Memory Facts]"]
    prefix.extend(
        f"[resolved:{fact.key} source={fact.source} scope={fact.scope}] {fact.value}" for fact in selected_facts
    )
    conflicts = tuple(
        MemoryConflict(
            key=fact.key,
            selected_source=fact.source,
            selected_scope=fact.scope,
            suppressed_records=suppressed_by_key[fact.key],
        )
        for fact in selected_facts
        if fact.key in conflict_keys
    )
    prefix.extend(
        f"[memory_conflict key={conflict.key} suppressed={conflict.suppressed_records}]" for conflict in conflicts
    )
    deduplications = tuple(
        MemoryDeduplication(
            key=fact.key,
            selected_source=fact.source,
            selected_scope=fact.scope,
            suppressed_records=suppressed_by_key[fact.key],
        )
        for fact in selected_facts
        if fact.key in duplicate_keys
    )
    prefix.extend(f"[memory_dedupe key={item.key} suppressed={item.suppressed_records}]" for item in deduplications)
    return MemoryResolution(
        context="\n".join(prefix + ([""] + filtered if filtered else [])),
        conflicts=conflicts,
        deduplications=deduplications,
    )


def resolve_memory_fact_winners(
    query: str,
    provider_facts: tuple[MemoryFact, ...],
) -> dict[str, MemoryFact]:
    return _select_winners(provider_facts + _query_facts(query))


def _query_facts(query: str) -> tuple[MemoryFact, ...]:
    observed_at = time.time()
    identity_facts = tuple(
        MemoryFact(
            key=f"identity:{key}",
            value=value,
            source="current_user",
            scope="session",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=observed_at,
        )
        for key, value in extract_identity_facts(query).items()
    )
    preference_facts = tuple(
        MemoryFact(
            key=f"preference:{key}",
            value=value,
            source="current_user",
            scope="session",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=observed_at,
        )
        for key, value in extract_explicit_preference_facts(query).items()
    )
    project_facts = tuple(
        MemoryFact(
            key=f"project:{key}",
            value=value,
            source="current_user",
            scope="project",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=observed_at,
        )
        for key, value in extract_project_memory_facts(query).items()
    )
    return identity_facts + preference_facts + project_facts


def _select_winners(facts: tuple[MemoryFact, ...]) -> dict[str, MemoryFact]:
    winners: dict[str, MemoryFact] = {}
    for fact in facts:
        current = winners.get(fact.key)
        candidate_rank = (int(fact.authority), fact.observed_at, fact.source)
        current_rank = (
            (int(current.authority), current.observed_at, current.source) if current is not None else (-1, -1.0, "")
        )
        if candidate_rank > current_rank:
            winners[fact.key] = fact
    return winners


def _find_resolution_keys(
    fragments: tuple[MemoryRecallFragment, ...],
    candidates: tuple[MemoryFact, ...],
    winners: dict[str, MemoryFact],
) -> tuple[set[str], set[str]]:
    values: dict[str, set[str]] = {key: {winner.value} for key, winner in winners.items()}
    for fact in candidates:
        if fact.key in values:
            values[fact.key].add(fact.value)
    fragment_counts: dict[str, int] = {key: 0 for key in winners}
    for fragment in fragments:
        for key, value in _facts_in_text(fragment.content).items():
            if key in values:
                values[key].add(value)
                fragment_counts[key] += 1
    conflicts = {key for key, observed in values.items() if len(observed) > 1}
    duplicates = {key for key, count in fragment_counts.items() if count > 1 and key not in conflicts}
    return conflicts, duplicates


def _filter_fragment(content: str, conflict_keys: set[str]) -> tuple[str, dict[str, int]]:
    suppressed = {key: 0 for key in conflict_keys}
    kept: list[str] = []
    for record in _group_records(content.splitlines()):
        record_facts = _facts_in_text("\n".join(record))
        matched = conflict_keys.intersection(record_facts)
        if matched:
            for key in matched:
                suppressed[key] += 1
            continue
        kept.extend(record)
    if not [line for line in kept if line.strip() and not line.lstrip().startswith("[")]:
        return "", suppressed
    return "\n".join(kept).strip(), suppressed


def _group_records(lines: list[str]) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    pending: list[str] = []
    for line in lines:
        if _RECORD_START.search(line):
            if pending:
                groups.append(tuple(pending))
            pending = [line]
        elif pending and _RECORD_END.search(line):
            pending.append(line)
            groups.append(tuple(pending))
            pending = []
        else:
            if pending:
                groups.append(tuple(pending))
                pending = []
            groups.append((line,))
    if pending:
        groups.append(tuple(pending))
    return tuple(groups)


def _facts_in_text(text: str) -> dict[str, str]:
    facts = {f"identity:{key}": value for key, value in extract_identity_facts(text).items()}
    facts.update(
        {f"preference:{key}": value for key, value in extract_explicit_preference_facts(text).items()},
    )
    facts.update({f"project:{key}": value for key, value in extract_project_memory_facts(text).items()})
    for match in _IDENTITY_MARKER.finditer(text):
        facts[f"identity:{match.group('key')}"] = match.group("value").strip()
    for match in _PREFERENCE_MARKER.finditer(text):
        facts[f"preference:{match.group('key')}"] = match.group("value").strip()
    for match in _PROJECT_MARKER.finditer(text):
        key = canonical_project_record_key(match.group("key"))
        facts[f"project:{key}"] = match.group("value").strip()
    return facts
