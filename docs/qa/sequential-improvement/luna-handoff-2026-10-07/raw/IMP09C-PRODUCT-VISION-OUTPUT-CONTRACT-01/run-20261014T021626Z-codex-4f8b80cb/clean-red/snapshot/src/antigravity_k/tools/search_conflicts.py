from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

type ConflictSet = tuple[str, str]

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^\W_]+", re.UNICODE)
_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:19|20)\d{2}\b")
_METRIC_FACT_PATTERN: Final[re.Pattern[str]] = re.compile(
    "".join(
        (
            r"\b(?P<label>",
            r"version|context\s+length|parameter\s+count|memory|price|latency|throughput",
            r"|버전|컨텍스트\s*길이|파라미터\s*수|메모리|가격|지연\s*시간|처리량",
            r")\s*(?:(?:is|was|are|were)|[=:]|은|는|이|가)?\s*",
            r"(?P<value>v?\d+(?:\.\d+){0,3}(?:\s*(?:[kmgt]?b|[kmgt]?\s*tokens?|ms|s|%|usd|dollars?|원|개|만|억))?)",
        ),
    ),
    re.IGNORECASE,
)
_TITLE_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "archive",
        "for",
        "in",
        "note",
        "notes",
        "official",
        "the",
        "update",
        "updates",
    },
)


class CitationEvidence(Protocol):
    @property
    def source_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class _MetricFact:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class _SourceFacts:
    source_id: str
    subject_terms: frozenset[str]
    years: frozenset[str]
    metric_facts: frozenset[_MetricFact]


def source_conflict_sets(sources: Iterable[CitationEvidence]) -> tuple[ConflictSet, ...]:
    facts = tuple(
        _SourceFacts(
            source_id=source.source_id,
            subject_terms=frozenset(
                token.casefold()
                for match in _TOKEN_PATTERN.finditer(source.title)
                for token in (match.group(0),)
                if len(token) >= 2 and not token.isdecimal() and token.casefold() not in _TITLE_STOPWORDS
            ),
            years=frozenset(_YEAR_PATTERN.findall(f"{source.title} {source.text}")),
            metric_facts=frozenset(
                _MetricFact(
                    label=re.sub(r"\s+", " ", match.group("label").casefold()),
                    value=re.sub(r"\s+", "", match.group("value").casefold()).removeprefix("v"),
                )
                for match in _METRIC_FACT_PATTERN.finditer(f"{source.title} {source.text}")
            ),
        )
        for source in sources
        if source.source_id
    )
    conflicts: list[ConflictSet] = []
    for index, current in enumerate(facts):
        for candidate in facts[index + 1 :]:
            shared_terms = current.subject_terms & candidate.subject_terms
            matching_subject = (
                len(shared_terms) >= 2
                and len(shared_terms)
                / min(
                    len(current.subject_terms),
                    len(candidate.subject_terms),
                )
                >= 0.5
            )
            contradictory_years = bool(current.years and candidate.years and current.years.isdisjoint(candidate.years))
            shared_labels = {fact.label for fact in current.metric_facts} & {
                fact.label for fact in candidate.metric_facts
            }
            contradictory_metric_values = any(
                {fact.value for fact in current.metric_facts if fact.label == label}.isdisjoint(
                    {fact.value for fact in candidate.metric_facts if fact.label == label},
                )
                for label in shared_labels
            )
            if matching_subject and (contradictory_years or contradictory_metric_values):
                conflicts.append((current.source_id, candidate.source_id))
    return tuple(conflicts)


__all__ = ["CitationEvidence", "ConflictSet", "source_conflict_sets"]
