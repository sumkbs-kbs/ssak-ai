from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypedDict, cast

import anyio
import httpx

from .search_quality_evaluator import (
    SearchGoldenCase,
    SearchQualityReport,
    evaluate_golden_case,
)
from .web_search_engine import WebSearchEngine
from .web_search_models import SearchResponse, SearchResult

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]


class SearchEngineProtocol(Protocol):
    async def search(
        self,
        query: str,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> SearchResponse: ...


class SearchResultJSON(TypedDict):
    title: str
    url: str
    snippet: str
    source: str
    relevance_score: float


class SearchCaseJSON(TypedDict):
    case_id: str
    engine: str
    search_time_ms: float
    error: str
    quality: dict[str, str | float | int]
    retrieved: list[SearchResultJSON]


class AggregateJSON(TypedDict):
    case_count: int
    error_count: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    mean_domain_diversity: float


class SearchBenchmarkJSON(TypedDict):
    started_at: str
    finished_at: str
    case_count: int
    aggregate: AggregateJSON
    results: list[SearchCaseJSON]


@dataclass(frozen=True, slots=True)
class BenchmarkArgs:
    fixture: Path
    output: Path
    k: int
    searxng_url: str | None


@dataclass(frozen=True, slots=True)
class SearchCaseResult:
    case_id: str
    engine: str
    search_time_ms: float
    quality: SearchQualityReport
    retrieved: tuple[SearchResult, ...] = ()
    error: str = ""

    def to_dict(self) -> SearchCaseJSON:
        quality = self.quality
        return {
            "case_id": self.case_id,
            "engine": self.engine,
            "search_time_ms": self.search_time_ms,
            "error": self.error,
            "retrieved": [
                {
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "source": result.source,
                    "relevance_score": result.relevance_score,
                }
                for result in self.retrieved
            ],
            "quality": {
                "case_id": quality.case_id,
                "k": quality.k,
                "retrieved_count": quality.retrieved_count,
                "relevant_count": quality.relevant_count,
                "retrieved_relevant": quality.retrieved_relevant,
                "precision_at_k": quality.precision_at_k,
                "recall_at_k": quality.recall_at_k,
                "reciprocal_rank": quality.reciprocal_rank,
                "ndcg_at_k": quality.ndcg_at_k,
                "domain_diversity": quality.domain_diversity,
            },
        }


@dataclass(frozen=True, slots=True)
class SearchBenchmarkReport:
    started_at: str
    finished_at: str
    results: tuple[SearchCaseResult, ...]

    @property
    def aggregate(self) -> AggregateJSON:
        count = len(self.results)
        errors = sum(bool(result.error) for result in self.results)
        if not count:
            return {
                "case_count": 0,
                "error_count": 0,
                "mean_precision_at_k": 0.0,
                "mean_recall_at_k": 0.0,
                "mean_reciprocal_rank": 0.0,
                "mean_ndcg_at_k": 0.0,
                "mean_domain_diversity": 0.0,
            }
        return {
            "case_count": count,
            "error_count": errors,
            "mean_precision_at_k": sum(r.quality.precision_at_k for r in self.results) / count,
            "mean_recall_at_k": sum(r.quality.recall_at_k for r in self.results) / count,
            "mean_reciprocal_rank": sum(r.quality.reciprocal_rank for r in self.results) / count,
            "mean_ndcg_at_k": sum(r.quality.ndcg_at_k for r in self.results) / count,
            "mean_domain_diversity": sum(r.quality.domain_diversity for r in self.results) / count,
        }

    def to_dict(self) -> SearchBenchmarkJSON:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "case_count": len(self.results),
            "aggregate": self.aggregate,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class SearchLoadSample:
    query: str
    iteration: int
    latency_ms: float
    result_count: int
    engine: str
    error: str = ""

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "query": self.query,
            "iteration": self.iteration,
            "latency_ms": self.latency_ms,
            "result_count": self.result_count,
            "engine": self.engine,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SearchLoadReport:
    repeats: int
    concurrency: int
    samples: tuple[SearchLoadSample, ...]

    @property
    def error_count(self) -> int:
        return sum(bool(sample.error) for sample in self.samples)

    @property
    def p50_ms(self) -> float:
        return _percentile([sample.latency_ms for sample in self.samples], 0.50)

    @property
    def p95_ms(self) -> float:
        return _percentile([sample.latency_ms for sample in self.samples], 0.95)

    @property
    def p99_ms(self) -> float:
        return _percentile([sample.latency_ms for sample in self.samples], 0.99)

    def to_dict(self) -> dict[str, object]:
        return {
            "repeats": self.repeats,
            "concurrency": self.concurrency,
            "sample_count": len(self.samples),
            "error_count": self.error_count,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "samples": [sample.to_dict() for sample in self.samples],
        }


async def run_search_load_benchmark(
    engine: SearchEngineProtocol,
    queries: Sequence[str],
    repeats: int = 3,
    concurrency: int = 1,
) -> SearchLoadReport:
    if repeats <= 0 or concurrency <= 0:
        raise ValueError("repeats and concurrency must be positive")
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(query: str, iteration: int) -> SearchLoadSample:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await engine.search(query, use_cache=False, force_refresh=True)
                error = "empty_result" if not response.results else ""
                return SearchLoadSample(
                    query=query,
                    iteration=iteration,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                    result_count=len(response.results),
                    engine=response.engine,
                    error=error,
                )
            except (httpx.HTTPError, OSError, TimeoutError, ValueError) as exc:
                return SearchLoadSample(
                    query=query,
                    iteration=iteration,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                    result_count=0,
                    engine="error",
                    error=str(exc),
                )

    samples = await asyncio.gather(
        *(run_one(query, iteration) for iteration in range(1, repeats + 1) for query in queries),
    )
    return SearchLoadReport(repeats=repeats, concurrency=concurrency, samples=tuple(samples))


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


async def run_search_benchmark(
    engine: SearchEngineProtocol,
    cases: Sequence[SearchGoldenCase],
    k: int = 3,
) -> SearchBenchmarkReport:
    if k <= 0:
        raise ValueError("k must be positive")
    started_at = datetime.now(UTC).isoformat()
    results: list[SearchCaseResult] = []
    for case in cases:
        try:
            response = await engine.search(case.query, use_cache=True, force_refresh=True)
            quality = evaluate_golden_case(case, response.results, k=k)
            results.append(
                SearchCaseResult(
                    case_id=case.case_id,
                    engine=response.engine,
                    search_time_ms=response.search_time_ms,
                    quality=quality,
                    retrieved=tuple(response.results),
                    error="empty_result" if not response.results else "",
                ),
            )
        except (httpx.HTTPError, OSError, TimeoutError, ValueError) as exc:
            results.append(
                SearchCaseResult(
                    case_id=case.case_id,
                    engine="error",
                    search_time_ms=0.0,
                    quality=evaluate_golden_case(case, (), k=k),
                    error=str(exc),
                ),
            )
    return SearchBenchmarkReport(
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        results=tuple(results),
    )


def _load_cases(path: Path) -> tuple[SearchGoldenCase, ...]:
    payload = cast(JSONValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, list):
        raise TypeError("search fixture must be a list")
    cases: list[SearchGoldenCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TypeError("search fixture entries must be objects")
        cases.append(SearchGoldenCase.from_dict(item))
    return tuple(cases)


def _parse_args() -> BenchmarkArgs:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/search_quality_cases.json"),
    )
    _ = parser.add_argument("--output", type=Path, default=Path("data/benchmarks/live-search.json"))
    _ = parser.add_argument("--k", type=int, default=3)
    _ = parser.add_argument("--searxng-url", default=None)
    namespace = parser.parse_args()
    return BenchmarkArgs(
        fixture=cast(Path, namespace.fixture),
        output=cast(Path, namespace.output),
        k=cast(int, namespace.k),
        searxng_url=cast(str | None, namespace.searxng_url),
    )


async def _run_live(engine: WebSearchEngine, cases: Sequence[SearchGoldenCase], k: int) -> SearchBenchmarkReport:
    try:
        return await run_search_benchmark(engine, cases, k=k)
    finally:
        await engine.close()


def main() -> int:
    args = _parse_args()
    cases = _load_cases(args.fixture)
    engine = WebSearchEngine(searxng_url=args.searxng_url, max_results=max(args.k, 3))
    report = anyio.run(_run_live, engine, cases, args.k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _ = args.output.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    return 0 if report.aggregate["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
