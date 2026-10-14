from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import log2
from pathlib import Path
from typing import Protocol, TypedDict


class RAGMetadata(TypedDict, total=False):
    source: str


class RAGProvenance(TypedDict, total=False):
    freshness: str


RAGField = str | RAGMetadata | RAGProvenance
RAGResultMapping = Mapping[str, RAGField]
type RAGJSON = str | int | float | bool | None | list[RAGJSON] | dict[str, RAGJSON]


class RAGSearchProvider(Protocol):
    def search(self, query: str, n_results: int = 5, mode: str = "hybrid") -> Sequence[RAGResultMapping]: ...


@dataclass(frozen=True, slots=True)
class RAGGoldenCase:
    case_id: str
    query: str
    relevant_sources: tuple[str, ...]
    graded_relevance: tuple[tuple[str, int], ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, RAGJSON]) -> RAGGoldenCase:
        case_id = payload.get("case_id")
        query = payload.get("query")
        relevant_sources = payload.get("relevant_sources")
        graded_relevance = payload.get("graded_relevance", {})
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("RAG golden case requires a non-empty case_id")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("RAG golden case requires a non-empty query")
        if not isinstance(relevant_sources, list):
            raise ValueError("RAG golden case relevant_sources must be a list of strings")
        sources: list[str] = []
        for source in relevant_sources:
            if not isinstance(source, str):
                raise ValueError("RAG golden case relevant_sources must be a list of strings")
            sources.append(source)
        if not sources:
            raise ValueError("RAG golden case requires at least one relevant source")
        if not isinstance(graded_relevance, dict):
            raise TypeError("RAG golden case graded_relevance must be an object")
        grades: dict[str, int] = {source: 1 for source in sources}
        for source, grade in graded_relevance.items():
            if not isinstance(grade, int) or isinstance(grade, bool) or grade < 0:
                raise ValueError("RAG golden case grades must be non-negative integers")
            grades[source] = grade
        positive_sources = tuple(source for source, grade in grades.items() if grade > 0)
        if not positive_sources:
            raise ValueError("RAG golden case requires at least one positive relevance grade")
        return cls(case_id, query, positive_sources, tuple(grades.items()))


@dataclass(frozen=True, slots=True)
class RAGQualityReport:
    case_id: str
    k: int
    retrieved_count: int
    relevant_count: int
    retrieved_relevant: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    source_diversity: float
    freshness_ratio: float

    def to_dict(self) -> dict[str, RAGJSON]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RAGFixtureAudit:
    case_id: str
    source: str
    query_tokens: tuple[str, ...]
    matched_tokens: tuple[str, ...]
    coverage: float
    discoverable: bool
    reason: str

    def to_dict(self) -> dict[str, RAGJSON]:
        return {
            "case_id": self.case_id,
            "source": self.source,
            "query_tokens": list(self.query_tokens),
            "matched_tokens": list(self.matched_tokens),
            "coverage": self.coverage,
            "discoverable": self.discoverable,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RAGCaseResult:
    case_id: str
    query: str
    quality: RAGQualityReport
    retrieved_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, RAGJSON]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "quality": self.quality.to_dict(),
            "retrieved_sources": list(self.retrieved_sources),
        }


@dataclass(frozen=True, slots=True)
class RAGBenchmarkReport:
    results: tuple[RAGCaseResult, ...]

    @property
    def aggregate(self) -> dict[str, RAGJSON]:
        count = len(self.results)
        if not count:
            return {
                "case_count": 0,
                "mean_precision_at_k": 0.0,
                "mean_recall_at_k": 0.0,
                "mean_reciprocal_rank": 0.0,
                "mean_ndcg_at_k": 0.0,
                "mean_source_diversity": 0.0,
                "mean_freshness_ratio": 0.0,
            }
        reports = [result.quality for result in self.results]
        return {
            "case_count": count,
            "mean_precision_at_k": sum(report.precision_at_k for report in reports) / count,
            "mean_recall_at_k": sum(report.recall_at_k for report in reports) / count,
            "mean_reciprocal_rank": sum(report.reciprocal_rank for report in reports) / count,
            "mean_ndcg_at_k": sum(report.ndcg_at_k for report in reports) / count,
            "mean_source_diversity": sum(report.source_diversity for report in reports) / count,
            "mean_freshness_ratio": sum(report.freshness_ratio for report in reports) / count,
        }

    def to_dict(self) -> dict[str, RAGJSON]:
        return {
            "case_count": len(self.results),
            "aggregate": self.aggregate,
            "results": [result.to_dict() for result in self.results],
        }


def _source_for_result(result: RAGResultMapping) -> str:
    metadata = result.get("metadata") or {}
    if isinstance(metadata, dict):
        source = metadata.get("source")
        if isinstance(source, str) and source:
            return source
    identifier = result.get("id")
    return identifier if isinstance(identifier, str) else ""


_FIXTURE_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _fixture_tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_FIXTURE_TOKEN_RE.findall(value.casefold())))


def audit_rag_fixture(project_root: str | Path, cases: Sequence[RAGGoldenCase]) -> tuple[RAGFixtureAudit, ...]:
    root = Path(project_root)
    audits: list[RAGFixtureAudit] = []
    for case in cases:
        query_tokens = _fixture_tokens(case.query)
        for source in case.relevant_sources:
            source_path = root / source
            try:
                source_text = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                audits.append(
                    RAGFixtureAudit(
                        case_id=case.case_id,
                        source=source,
                        query_tokens=query_tokens,
                        matched_tokens=(),
                        coverage=0.0,
                        discoverable=False,
                        reason="source file is missing or unreadable",
                    ),
                )
                continue
            source_tokens = set(_fixture_tokens(source_path.stem)) | set(_fixture_tokens(source_text))
            matched_tokens = tuple(token for token in query_tokens if token in source_tokens)
            coverage = len(matched_tokens) / len(query_tokens) if query_tokens else 0.0
            discoverable = coverage >= 0.5
            reason = (
                "strong lexical evidence"
                if discoverable
                else f"weak lexical evidence ({len(matched_tokens)}/{len(query_tokens)} query tokens matched)"
            )
            audits.append(
                RAGFixtureAudit(
                    case_id=case.case_id,
                    source=source,
                    query_tokens=query_tokens,
                    matched_tokens=matched_tokens,
                    coverage=coverage,
                    discoverable=discoverable,
                    reason=reason,
                ),
            )
    return tuple(audits)


def evaluate_rag_case(
    case: RAGGoldenCase, results: Sequence[RAGResultMapping], k: int | None = None
) -> RAGQualityReport:
    limit = len(results) if k is None else k
    if limit <= 0:
        raise ValueError("k must be positive")
    ranked_sources = tuple(_source_for_result(result) for result in results[:limit] if _source_for_result(result))
    unique_sources = tuple(dict.fromkeys(ranked_sources))
    relevant = set(case.relevant_sources)
    grades = dict(case.graded_relevance) or {source: 1 for source in relevant}
    relevant_hits = sum(source in relevant for source in unique_sources)
    relevance = [grades.get(source, 0) > 0 for source in unique_sources]
    reciprocal_rank = next((1.0 / rank for rank, hit in enumerate(relevance, 1) if hit), 0.0)
    dcg = sum(grades.get(source, 0) / log2(rank + 1) for rank, source in enumerate(unique_sources, 1))
    ideal = sorted((grade for grade in grades.values() if grade > 0), reverse=True)[:limit]
    ideal_dcg = sum(grade / log2(rank + 1) for rank, grade in enumerate(ideal, 1))
    freshness_by_source: dict[str, str] = {}
    for result in results[:limit]:
        source = _source_for_result(result)
        provenance = result.get("provenance")
        if source and isinstance(provenance, dict):
            freshness = provenance.get("freshness")
            if isinstance(freshness, str):
                freshness_by_source[source] = freshness
    fresh_count = sum(freshness_by_source.get(source) == "fresh" for source in unique_sources)
    return RAGQualityReport(
        case_id=case.case_id,
        k=limit,
        retrieved_count=len(unique_sources),
        relevant_count=len(relevant),
        retrieved_relevant=relevant_hits,
        precision_at_k=relevant_hits / limit,
        recall_at_k=relevant_hits / len(relevant),
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=dcg / ideal_dcg if ideal_dcg else 0.0,
        source_diversity=len(unique_sources) / len(ranked_sources) if ranked_sources else 0.0,
        freshness_ratio=fresh_count / len(unique_sources) if unique_sources else 0.0,
    )


def run_rag_benchmark(indexer: RAGSearchProvider, cases: Sequence[RAGGoldenCase], k: int = 5) -> RAGBenchmarkReport:
    if k <= 0:
        raise ValueError("k must be positive")
    case_results: list[RAGCaseResult] = []
    for case in cases:
        results = indexer.search(case.query, n_results=k, mode="hybrid")
        case_results.append(
            RAGCaseResult(
                case_id=case.case_id,
                query=case.query,
                quality=evaluate_rag_case(case, results, k),
                retrieved_sources=tuple(_source_for_result(result) for result in results if _source_for_result(result)),
            ),
        )
    return RAGBenchmarkReport(tuple(case_results))


__all__ = [
    "RAGBenchmarkReport",
    "RAGCaseResult",
    "RAGFixtureAudit",
    "RAGGoldenCase",
    "RAGQualityReport",
    "audit_rag_fixture",
    "evaluate_rag_case",
    "run_rag_benchmark",
]
