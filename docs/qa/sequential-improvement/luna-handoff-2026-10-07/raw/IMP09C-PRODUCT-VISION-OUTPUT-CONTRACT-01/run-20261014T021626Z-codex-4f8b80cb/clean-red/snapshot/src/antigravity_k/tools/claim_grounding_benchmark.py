from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from .search_quality_evaluator import CitationEvaluationReport, CitationSource, evaluate_citations

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ClaimGroundingCase:
    case_id: str
    response: str
    sources: tuple[CitationSource, ...]
    conflict_sets: tuple[tuple[str, ...], ...] = ()
    min_overlap: float = 0.6
    expected: Mapping[str, int | float] = field(default_factory=lambda: dict[str, int | float]())
    question: str = ""
    query: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ClaimGroundingCase:
        case_id = payload.get("case_id")
        response = payload.get("response")
        raw_sources = payload.get("sources")
        question = payload.get("question", "")
        query = payload.get("query", "")
        raw_conflicts = payload.get("conflict_sets", [])
        raw_expected = payload.get("expected", {})
        min_overlap = payload.get("min_overlap", 0.6)
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("claim grounding case requires a non-empty case_id")
        if not isinstance(response, str):
            raise TypeError("claim grounding case response must be a string")
        if not isinstance(question, str):
            raise TypeError("claim grounding case question must be a string")
        if not isinstance(query, str):
            raise TypeError("claim grounding case query must be a string")
        if not isinstance(raw_sources, list):
            raise TypeError("claim grounding case sources must be a list")
        if not isinstance(raw_conflicts, list):
            raise TypeError("claim grounding case conflict_sets must be a list")
        if not isinstance(raw_expected, dict):
            raise TypeError("claim grounding case expected must be an object")
        if not isinstance(min_overlap, (int, float)) or not 0.0 < min_overlap <= 1.0:
            raise ValueError("claim grounding case min_overlap must be between 0 and 1")

        sources: list[CitationSource] = []
        for raw_source in cast(list[object], raw_sources):
            if not isinstance(raw_source, dict):
                raise TypeError("claim grounding sources must be objects")
            source = cast(Mapping[str, object], raw_source)
            source_id = source.get("source_id")
            title = source.get("title")
            text = source.get("text")
            if not isinstance(source_id, str) or not isinstance(title, str) or not isinstance(text, str):
                raise TypeError("claim grounding source requires source_id, title, and text")
            raw_url = source.get("url", "")
            raw_freshness = source.get("freshness", "")
            sources.append(
                CitationSource(
                    source_id=source_id,
                    title=title,
                    text=text,
                    url=raw_url if isinstance(raw_url, str) else "",
                    freshness=raw_freshness if isinstance(raw_freshness, str) else "",
                ),
            )

        conflict_sets: list[tuple[str, ...]] = []
        for raw_group in cast(list[object], raw_conflicts):
            if not isinstance(raw_group, list):
                raise ValueError("claim grounding conflict_sets must contain string lists")
            group = cast(list[object], raw_group)
            if not all(isinstance(value, str) for value in group):
                raise ValueError("claim grounding conflict_sets must contain string lists")
            conflict_sets.append(tuple(value for value in group if isinstance(value, str)))

        expected: dict[str, int | float] = {}
        for key, value in cast(Mapping[object, object], raw_expected).items():
            if not isinstance(key, str) or not isinstance(value, (int, float)):
                raise TypeError("claim grounding expected values must be numeric")
            expected[key] = value
        return cls(
            case_id=case_id,
            response=response,
            sources=tuple(sources),
            question=question,
            conflict_sets=tuple(conflict_sets),
            min_overlap=float(min_overlap),
            expected=expected,
            query=query,
        )


@dataclass(frozen=True, slots=True)
class ClaimGroundingResult:
    case_id: str
    passed: bool
    failures: tuple[str, ...]
    report: CitationEvaluationReport

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "failures": list(self.failures),
            "report": self.report.to_dict(),
        }


def evaluate_claim_grounding_case(
    case: ClaimGroundingCase,
    response: str | None = None,
) -> ClaimGroundingResult:
    report = evaluate_citations(
        response if response is not None else case.response,
        case.sources,
        min_overlap=case.min_overlap,
        conflict_sets=case.conflict_sets,
    )
    actual = report.to_dict()
    failures = tuple(
        f"{key}: expected {expected!r}, got {actual.get(key)!r}"
        for key, expected in case.expected.items()
        if actual.get(key) != expected
    )
    return ClaimGroundingResult(case.case_id, not failures, failures, report)


def evaluate_live_grounding_case(
    case: ClaimGroundingCase,
    response: str,
    sources: Sequence[CitationSource] | None = None,
) -> ClaimGroundingResult:
    report = evaluate_citations(
        response,
        sources if sources is not None else case.sources,
        min_overlap=case.min_overlap,
        conflict_sets=case.conflict_sets,
    )
    failures: list[str] = []
    if not sources and not case.sources:
        failures.append("no_sources")
    if report.claim_count == 0:
        failures.append("no_claims")
    if report.citation_coverage < 1.0:
        failures.append("incomplete_citation_coverage")
    if report.unsupported_claim_count > 0:
        failures.append("unsupported_claims")
    if report.unknown_citation_count > 0:
        failures.append("unknown_citations")
    if report.unacknowledged_conflict_count > 0:
        failures.append("unacknowledged_conflict")
    return ClaimGroundingResult(case.case_id, not failures, tuple(failures), report)


def run_claim_grounding_benchmark(
    cases: Sequence[ClaimGroundingCase],
    responses: Mapping[str, str] | None = None,
) -> tuple[ClaimGroundingResult, ...]:
    return tuple(
        evaluate_claim_grounding_case(case, responses.get(case.case_id) if responses else None) for case in cases
    )


def load_claim_grounding_cases(path: Path) -> tuple[ClaimGroundingCase, ...]:
    payload = cast(JSONValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, list):
        raise TypeError("claim grounding fixture must be a list")
    cases: list[ClaimGroundingCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TypeError("claim grounding fixture entries must be objects")
        cases.append(ClaimGroundingCase.from_dict(item))
    return tuple(cases)


def load_claim_responses(path: Path) -> dict[str, str]:
    payload = cast(JSONValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        raise TypeError("claim response file must be an object mapping case ids to strings")
    responses: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            raise TypeError("claim response file must be an object mapping case ids to strings")
        responses[key] = value
    return responses


__all__ = [
    "ClaimGroundingCase",
    "ClaimGroundingResult",
    "evaluate_claim_grounding_case",
    "evaluate_live_grounding_case",
    "load_claim_grounding_cases",
    "load_claim_responses",
    "run_claim_grounding_benchmark",
]
