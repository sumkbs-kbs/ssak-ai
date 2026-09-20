#!/usr/bin/env python
"""task 24 — 통합 검색의 **품질·비용·지연 회귀 gate**.

이 스크립트가 답하는 질문은 하나다: *"지금 트리의 검색 경로가, 승인된 기준선보다 나빠졌는가?"*
그래서 재는 방식도 하나로 고정한다 — 100개 고정 검색셋(한글 공식/최신/일반/개발/다국어)과 30개 본문
추출 fixture 를, **두 개의 실제 경로**에 같은 순서로 통과시킨다.

  - ``legacy``     : `WebSearchEngine.search()` — provider adapter · 캐시 · 랭킹 · 권위 · 포매터
  - ``integrated`` : `search_with_bundled_provider()` — MCP child → `CallToolResult` → provider adapter

두 arm 의 차이는 **주입된 전송 계층 하나뿐**이다(둘 다 실제 코드, 실제 프로토콜 경계를 지난다).

## 무엇을 재는가 (계획 §24 acceptance)

``recall@5`` · ``nDCG@5`` · ``valid_source_ratio``(유효 출처 비율) · ``authority_satisfied`` ·
``grounding``(추출 30) · ``empty_rate`` · ``errors`` · ``p95``(cold, 중앙값 기준) · ``tokens/query``(비용).
콜드/웜은 **구분해서** 잰다: 콜드는 캐시 우회(`force_refresh=True`), 웜은 같은 질의 재호출이다.
웜 호출이 provider 요청을 0건 늘리는지(캐시가 실제로 일했다), 웜 결과가 콜드와 같은지를 계약으로 고정한다.

## gate

기준선은 커밋된 ``anchor.json``(승인된 실행의 스냅숏)이고, 조건은 **코드 상수**다(CLI 로 완화 불가):

  - 결정적 계약 100%  (``contract_min_pass_rate = 1.0``)
  - ``nDCG@5`` 절대 하락 ≤ 0.02
  - 유효 출처 비율 저하 0
  - ``p95`` 증가 ≤ 10%   (같은 기계일 때만 절대 비교; 비율 비교는 기계 무관)
  - 비용(tokens/query) 증가 ≤ 5%
  - `--paired` 이면 같은 실행 안의 **legacy↔integrated 델타/비율**도 기준선과 비교한다(기계 무관).

자동 완화는 없다. 예외가 필요하면 원인·사용자 가치·승인자를 **모두** 적어야 하고(``--waiver-*``),
그 사실이 리포트에 남는다. 임계값을 낮추는 플래그는 존재하지 않는다.

## 주입 (실패를 실제로 검출하는지 확인하는 장치)

``--inject low-quality | slow | expensive | empty | noisy`` 는 **integrated arm 의 provider payload 만**
바꾼다. 각 주입은 대응하는 gate 조건을 무너뜨려야 한다(그러지 않으면 gate 는 장식이다).

## 사용

::

    uv run --frozen python scripts/benchmark_ssak_search.py --paired --runs 3 \
        --output .omo/evidence/ssak-ai-web-integration/<run>/task-24/results.json

    # 기준선 갱신은 사유가 있어야만 가능하다(자동 완화 금지)
    uv run --frozen python scripts/benchmark_ssak_search.py --paired --refresh-anchor --reason "..."

종료코드: 0 = PASS(또는 승인된 예외) · 1 = FAIL · 2 = 사용/환경 오류 · 3 = NOT_RUN(측정 불가).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import httpx  # noqa: E402

from antigravity_k.engine.tokenizer import TokenEstimator  # noqa: E402
from antigravity_k.tools import web_search_cache as _cache_module  # noqa: E402
from antigravity_k.tools.search_quality_evaluator import (  # noqa: E402
    SearchGoldenCase,
    evaluate_golden_case,
)
from antigravity_k.tools.ssak_search_provider import (  # noqa: E402
    SsakSearchSettings,
    search_with_bundled_provider,
)
from antigravity_k.tools.ssak_search_runtime import (  # noqa: E402
    SearchRuntimeConfig,
    SsakSearchRuntime,
)
from antigravity_k.tools.web_search_engine import WebSearchEngine, html_to_text  # noqa: E402
from antigravity_k.tools.web_search_models import SearchResponse, SearchResult  # noqa: E402
from antigravity_k.tools.web_search_quality import (  # noqa: E402
    authority_score,
    canonicalize_url,
    is_public_http_url,
)

# ── 임계값 (코드 상수. CLI 플래그로 낮출 수 없다 — 자동 완화 금지) ─────────────────
THRESHOLDS: Final[Mapping[str, float]] = {
    "contract_min_pass_rate": 1.0,
    "ndcg_drop_max": 0.02,
    "valid_source_drop_max": 0.0,
    "p95_increase_max": 0.10,
    "cost_increase_max": 0.05,
}

FIXTURE_DIR: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "ssak_search_eval"
ANCHOR_DEFAULT: Final[Path] = FIXTURE_DIR / "anchor.json"
CHILD_DEFAULT: Final[Path] = FIXTURE_DIR / "child.py"
OUTPUT_DEFAULT: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "ssak-search-gate.json"

#: 지연 회귀의 **잡음 하한**. hermetic fixture 라 네트워크가 없어 파이프라인 지연이 sub-ms 이고,
#: 그 스케일의 변화는 코드가 아니라 측정 잡음이다. 하한 미만의 증가를 "회귀"라 부르지 않는다.
LATENCY_NOISE_FLOOR_MS: Final[float] = 2.0

#: 유효 출처로 인정하는 최소 권위 점수(도메인 규칙). 이 아래는 "출처로 쓰지 않는" 주소다.
VALID_SOURCE_AUTHORITY_MIN: Final[float] = 0.5
#: 랭킹/포매터에 넘기는 최대 결과 수(제품 기본값과 같아야 비교가 의미를 갖는다).
ENGINE_MAX_RESULTS: Final[int] = 8
#: LLM 컨텍스트 상한(제품 기본값).
FORMAT_MAX_CHARS: Final[int] = 3000

INJECTIONS: Final[tuple[str, ...]] = ("low-quality", "slow", "expensive", "empty", "noisy")

#: 주입별로 "검출됐다"의 증거가 되는 gate 검사 이름. 주입은 **자기가 겨눈 지표**로 검출돼야 한다
#: (다른 이유로 실패하면 그건 검출이 아니라 우연이다).
CANARY_TARGETS: Final[Mapping[str, tuple[str, ...]]] = {
    "low-quality": ("integrated_ndcg_at_k", "paired_ndcg_gap", "contract_pass_rate"),
    "slow": ("integrated_p95_cold_ms", "paired_p95_ratio"),
    "expensive": ("integrated_cost_tokens", "paired_token_ratio"),
    "empty": ("integrated_valid_source_ratio", "paired_valid_source_gap", "integrated_ndcg_at_k"),
    "noisy": ("contract_pass_rate", "integrated_ndcg_at_k", "paired_ndcg_gap"),
}


class FixtureError(RuntimeError):
    """fixture 자체가 깨졌을 때(조용히 빈 집합으로 통과하지 않는다)."""


# ── fixture 로딩 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Hit:
    url: str
    title: str
    snippet: str
    grade: int


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    category: str
    query: str
    hits: tuple[Hit, ...]
    authority_expectation: str

    @property
    def relevant(self) -> tuple[tuple[str, int], ...]:
        return tuple((hit.url, hit.grade) for hit in self.hits if hit.grade > 0)

    @property
    def authority_urls(self) -> tuple[str, ...]:
        return tuple(hit.url for hit in self.hits if hit.grade > 0 and _is_authoritative(hit.url))


@dataclass(frozen=True, slots=True)
class ExtractionCase:
    case_id: str
    url: str
    html: str
    claim: str
    required_facts: tuple[str, ...]
    forbidden_markers: tuple[str, ...]
    expect_supported: bool


@dataclass(frozen=True, slots=True)
class EvalFixture:
    version: str
    k: int
    cases: tuple[EvalCase, ...]
    extraction: tuple[ExtractionCase, ...]
    sha256: str


def _is_authoritative(url: str) -> bool:
    """제품과 **같은 규칙**(권위 점수 ≥0.9, github 제외)을 그대로 쓴다."""
    canonical = canonicalize_url(url)
    host = (canonical.split("/", 3)[2] if canonical else "").split(":")[0].removeprefix("www.")
    return host != "github.com" and authority_score(canonical) >= 0.9


def _fixture_digest(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_fixture(limit: int | None = None) -> EvalFixture:
    manifest_path = FIXTURE_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FixtureError(f"manifest not found: {manifest_path}")
    manifest = cast(Mapping[str, object], json.loads(manifest_path.read_text(encoding="utf-8")))
    categories = cast(list[Mapping[str, object]], manifest.get("categories") or [])
    if not categories:
        raise FixtureError("manifest has no categories")
    files: list[Path] = [manifest_path]
    cases: list[EvalCase] = []
    for entry in categories:
        rel = str(entry.get("file") or "")
        path = FIXTURE_DIR / rel
        files.append(path)
        payload = cast(Mapping[str, object], json.loads(path.read_text(encoding="utf-8")))
        raw_cases = cast(list[Mapping[str, object]], payload.get("cases") or [])
        expected = int(cast(int, entry.get("expected_cases") or 0))
        if len(raw_cases) != expected:
            raise FixtureError(f"{rel}: expected {expected} cases, found {len(raw_cases)}")
        for raw in raw_cases:
            hits: list[Hit] = []
            for item in cast(list[object], raw.get("payload") or []):
                if not isinstance(item, list) or len(item) < 4:
                    raise FixtureError(f"{raw.get('case_id')}: payload entries must be [url, title, snippet, grade]")
                url, title, snippet, grade = item[:4]
                hits.append(Hit(str(url), str(title), str(snippet), int(cast(int, grade))))
            if not hits:
                raise FixtureError(f"{raw.get('case_id')}: empty payload")
            cases.append(
                EvalCase(
                    case_id=str(raw.get("case_id")),
                    category=str(payload.get("category") or ""),
                    query=str(raw.get("query")),
                    hits=tuple(hits),
                    authority_expectation=str(raw.get("authority_expectation") or "n/a"),
                ),
            )
    extraction_path = FIXTURE_DIR / str(manifest.get("extraction_file") or "extraction.json")
    files.append(extraction_path)
    extraction_payload = cast(Mapping[str, object], json.loads(extraction_path.read_text(encoding="utf-8")))
    raw_extraction = cast(list[Mapping[str, object]], extraction_payload.get("cases") or [])
    expected_extraction = int(cast(int, manifest.get("expected_extraction_cases") or 0))
    if len(raw_extraction) != expected_extraction:
        raise FixtureError(f"extraction: expected {expected_extraction}, found {len(raw_extraction)}")
    extraction = tuple(
        ExtractionCase(
            case_id=str(item.get("case_id")),
            url=str(item.get("url")),
            html=str(item.get("html")),
            claim=str(item.get("claim") or ""),
            required_facts=tuple(str(fact) for fact in cast(list[object], item.get("required_facts") or [])),
            forbidden_markers=tuple(str(mark) for mark in cast(list[object], item.get("forbidden_markers") or [])),
            expect_supported=bool(item.get("expect_supported")),
        )
        for item in raw_extraction
    )
    if limit is not None:
        cases = cases[: max(1, limit)]
    return EvalFixture(
        version=str(manifest.get("version") or "unknown"),
        k=int(cast(int, manifest.get("k") or 5)),
        cases=tuple(cases),
        extraction=extraction,
        sha256=_fixture_digest(files),
    )


# ── 주입 ─────────────────────────────────────────────────────────────────────


def _injected_hits(case: EvalCase, injection: str | None) -> tuple[Hit, ...]:
    """integrated arm 의 provider 가 돌려줄 payload 를 주입에 따라 바꾼다.

    여기서 바꾸는 것은 **provider 가 준 것**이지 우리 코드가 아니다 — 우리 코드가 그 열화를
    사용자에게 그대로 전달하는지(또는 완충하는지)를 gate 가 판정한다.
    """
    if injection == "low-quality":
        without_answer = tuple(hit for hit in case.hits if hit.grade == 0)
        return without_answer or case.hits[-1:]
    if injection == "expensive":
        return tuple(
            Hit(hit.url, f"{hit.title} (상세 안내)", f"{hit.snippet} 추가 안내 문구입니다. " * 3, hit.grade)
            for hit in case.hits
        )
    if injection == "empty":
        return ()
    return case.hits


def write_payload_file(cases: Sequence[EvalCase], injection: str | None, path: Path) -> None:
    queries: dict[str, object] = {}
    for case in cases:
        hits = _injected_hits(case, injection)
        queries[case.query] = {
            "hits": [[hit.url, hit.title, hit.snippet] for hit in hits],
            "took_ms": 140,
        }
    path.write_text(json.dumps({"queries": queries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── 관측 ─────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Observation:
    case_id: str
    cold_ms: float
    warm_ms: float
    results: tuple[tuple[str, str, str], ...]
    cold_results: tuple[str, ...]
    warm_results: tuple[str, ...]
    tokens: int
    error: str = ""
    cache_supported: bool = False
    warm_provider_requests: int = 0
    warm_cached_flag: bool | None = None

    @property
    def empty(self) -> bool:
        return not self.results


@dataclass(slots=True)
class ArmResult:
    name: str
    observations: list[Observation] = field(default_factory=list)
    not_run: str = ""


# ── 공용 계산 ────────────────────────────────────────────────────────────────


def _as_search_result(hit: tuple[str, str, str]) -> SearchResult:
    title, url, snippet = hit
    return SearchResult(title=title, url=url, snippet=snippet, source="fixture")


def _unique_returned_urls(urls: Sequence[str]) -> bool:
    canonical = [canonicalize_url(url) for url in urls]
    return len(canonical) == len(set(canonical)) and all(canonical)


def _valid_source(url: str) -> bool:
    canonical = canonicalize_url(url)
    return (
        bool(canonical) and is_public_http_url(canonical) and authority_score(canonical) >= VALID_SOURCE_AUTHORITY_MIN
    )


def _quality(case: EvalCase, results: Sequence[tuple[str, str, str]], k: int) -> tuple[float, float, float]:
    """(recall@k, nDCG@k, 유효 출처 비율) — nDCG/recall 은 제품과 같은 평가기를 쓴다."""
    golden = SearchGoldenCase(
        case_id=case.case_id,
        query=case.query,
        relevant_urls=tuple(url for url, _ in case.relevant),
        graded_relevance=case.relevant,
    )
    report = evaluate_golden_case(golden, [_as_search_result(hit) for hit in results], k=k)
    top = results[:k]
    ratio = (sum(1 for hit in top if _valid_source(hit[1])) / len(top)) if top else 0.0
    return report.recall_at_k, report.ndcg_at_k, ratio


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * percentile + 0.999999) - 1))
    return ordered[index]


# ── legacy arm ───────────────────────────────────────────────────────────────


class FixtureTransport:
    """provider 전송 계층만 갈아끼운다 — 엔진·캐시·랭킹·포매터는 전부 실제 코드다.

    - ``/api/search``(self-hosted): 그 케이스의 payload 를 **provider 순서 그대로** 돌려준다
    - searxng/jina/duckduckgo: 빈 결과(네트워크 없음). 엔진의 대체 경로도 여기로 지나간다.
    """

    def __init__(self, cases: Sequence[EvalCase]) -> None:
        self._by_query = {case.query: case for case in cases}
        self._current: EvalCase | None = None
        self.requests = 0

    def start_case(self, case: EvalCase) -> None:
        self._current = case

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        host = request.url.host or ""
        path = request.url.path
        if path.endswith("/api/search"):
            case = self._current
            hits = tuple(case.hits) if case is not None else ()
            results = [
                {"url": hit.url, "title": hit.title, "content": hit.snippet, "score": max(0.05, 0.95 - index * 0.1)}
                for index, hit in enumerate(hits)
            ]
            return httpx.Response(200, json={"results": results, "query": str(case.query) if case else ""})
        if "jina.ai" in host:
            return httpx.Response(200, json={"data": []})
        if "duckduckgo" in host:
            return httpx.Response(200, text="<html><body></body></html>")
        return httpx.Response(200, json={"results": []})


class LegacyArm:
    def __init__(self, cases: Sequence[EvalCase], k: int) -> None:
        self.k = k
        self.transport = FixtureTransport(cases)
        self.engine = WebSearchEngine(searxng_url="http://localhost:8080", max_results=ENGINE_MAX_RESULTS)
        self.engine._client = httpx.AsyncClient(  # noqa: SLF001 — 전송만 주입한다(계약 아님)
            transport=httpx.MockTransport(self.transport.handler),
            timeout=5.0,
        )

    async def close(self) -> None:
        await self.engine.close()

    def _response_results(self, response: SearchResponse) -> tuple[tuple[str, str, str], ...]:
        return tuple((result.title, result.url, result.snippet) for result in response.results)

    async def run_case(self, case: EvalCase) -> Observation:
        self.transport.start_case(case)
        cold_started = time.perf_counter()
        cold = await self.engine.search(case.query, use_cache=True, force_refresh=True)
        cold_ms = (time.perf_counter() - cold_started) * 1000
        after_cold = self.transport.requests
        cache_supported = self.engine.cache.get(case.query) is not None
        warm_started = time.perf_counter()
        warm = await self.engine.search(case.query, use_cache=True, force_refresh=False)
        warm_ms = (time.perf_counter() - warm_started) * 1000
        cold_hits = self._response_results(cold)
        warm_hits = self._response_results(warm)
        response = cold if cold_hits else warm
        return Observation(
            case_id=case.case_id,
            cold_ms=round(cold_ms, 3),
            warm_ms=round(warm_ms, 3),
            results=cold_hits,
            cold_results=tuple(url for _, url, _ in cold_hits[: self.k]),
            warm_results=tuple(url for _, url, _ in warm_hits[: self.k]),
            tokens=TokenEstimator.estimate_text(self.engine.format_for_llm(response, max_chars=FORMAT_MAX_CHARS)),
            error="" if cold_hits or warm_hits else "empty_result",
            cache_supported=cache_supported,
            warm_provider_requests=self.transport.requests - after_cold,
        )


# ── integrated arm ───────────────────────────────────────────────────────────


class IntegratedArm:
    """번들 provider 경로를 **실제 MCP child** 로 구동한다(기록 payload 를 돌려주는 fixture child)."""

    def __init__(self, payload_path: Path, child_path: Path, calls_file: Path, delay_ms: int, shuffle: bool) -> None:
        env: dict[str, str] = {
            "SSAK_SEARCH_EVAL_PAYLOAD": str(payload_path),
            "SSAK_SEARCH_EVAL_CALLS_FILE": str(calls_file),
        }
        if delay_ms > 0:
            env["SSAK_SEARCH_EVAL_DELAY_MS"] = str(delay_ms)
        if shuffle:
            env["SSAK_SEARCH_EVAL_SHUFFLE"] = "1"
        self.runtime = SsakSearchRuntime(
            SearchRuntimeConfig(
                command=sys.executable,
                args=(str(child_path),),
                require_manifest=False,
                enabled=True,
                env_allowlist=("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"),
                extra_env=env,
                call_timeout_seconds=60.0,
            ),
        )
        self.settings = SsakSearchSettings(
            enabled=True,
            artifact_path=str(child_path),
            extra_trusted_roots=(str(child_path.parent),),
        )
        self.engine_for_format = WebSearchEngine(max_results=ENGINE_MAX_RESULTS)
        self.k = ENGINE_MAX_RESULTS

    def close(self) -> None:
        _ = self.runtime.shutdown(timeout=20)

    def status(self) -> dict[str, object]:
        return self.runtime.status()

    def run_case(self, case: EvalCase) -> Observation:
        cold_started = time.perf_counter()
        cold = search_with_bundled_provider(
            case.query,
            max_results=ENGINE_MAX_RESULTS,
            settings=self.settings,
            runtime=self.runtime,
        )
        cold_ms = (time.perf_counter() - cold_started) * 1000
        warm_started = time.perf_counter()
        warm = search_with_bundled_provider(
            case.query,
            max_results=ENGINE_MAX_RESULTS,
            settings=self.settings,
            runtime=self.runtime,
        )
        warm_ms = (time.perf_counter() - warm_started) * 1000
        cold_hits = tuple(cold.results)
        warm_hits = tuple(warm.results)
        response = SearchResponse(
            query=case.query,
            results=[_as_search_result(hit) for hit in (cold_hits or warm_hits)],
            total_results=len(cold_hits or warm_hits),
            search_time_ms=round(cold_ms, 1),
            engine=cold.engine,
        )
        warm_evidence = warm.evidence
        return Observation(
            case_id=case.case_id,
            cold_ms=round(cold_ms, 3),
            warm_ms=round(warm_ms, 3),
            results=cold_hits,
            cold_results=tuple(url for _, url, _ in cold_hits[: self.k]),
            warm_results=tuple(url for _, url, _ in warm_hits[: self.k]),
            tokens=TokenEstimator.estimate_text(
                self.engine_for_format.format_for_llm(response, max_chars=FORMAT_MAX_CHARS)
            ),
            error="" if cold.ok or warm.ok else (cold.error_code or "provider_error"),
            warm_cached_flag=bool(warm_evidence.from_cache) if warm_evidence is not None else None,
        )


# ── 집계 ─────────────────────────────────────────────────────────────────────


def _median_by_case(observations: Sequence[Observation], attr: str) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for observation in observations:
        grouped.setdefault(observation.case_id, []).append(float(getattr(observation, attr)))
    return {case_id: statistics.median(values) for case_id, values in grouped.items()}


def aggregate(cases: Sequence[EvalCase], observations: Sequence[Observation], k: int) -> dict[str, object]:
    by_case: dict[str, Observation] = {}
    for observation in observations:
        by_case.setdefault(observation.case_id, observation)
    recalls: list[float] = []
    ndcgs: list[float] = []
    sources: list[float] = []
    authority_hits = 0
    authority_total = 0
    empties = 0
    tokens: list[float] = []
    errors = 0
    for case in cases:
        observation = by_case.get(case.case_id)
        if observation is None:
            continue
        recall, ndcg, ratio = _quality(case, observation.results, k)
        recalls.append(recall)
        ndcgs.append(ndcg)
        sources.append(ratio)
        tokens.append(float(observation.tokens))
        empties += int(observation.empty)
        errors += int(bool(observation.error))
        if case.authority_expectation == "satisfied" and case.authority_urls:
            authority_total += 1
            authority_hits += int(_has_authoritative(observation.results, case))
    cold = _median_by_case(observations, "cold_ms")
    warm = _median_by_case(observations, "warm_ms")
    count = max(1, len(by_case))
    return {
        "case_count": len(by_case),
        "recall_at_k": _mean(recalls),
        "ndcg_at_k": _mean(ndcgs),
        "valid_source_ratio": _mean(sources),
        "authority_satisfied_rate": (authority_hits / authority_total) if authority_total else 1.0,
        "grounding_rate": None,  # 추출 fixture 는 별도 블록에서 계산한다
        "empty_rate": empties / count,
        "error_count": errors,
        "tokens_per_query": _mean(tokens),
        "p95_cold_ms": _percentile(list(cold.values()), 0.95),
        "p50_cold_ms": _percentile(list(cold.values()), 0.50),
        "p95_warm_ms": _percentile(list(warm.values()), 0.95),
        "runs": len(observations) // count if count else 0,
    }


def _has_authoritative(results: Sequence[tuple[str, str, str]], case: EvalCase) -> bool:
    top5 = {canonicalize_url(url) for _, url, _ in results[:5]}
    return any(canonicalize_url(url) in top5 for url in case.authority_urls)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def extraction_block(fixture: EvalFixture) -> dict[str, object]:
    """본문 추출 30 fixture — 필요한 사실이 남고, 군더더기가 사라지고, 없는 근거를 만들지 않는가."""
    facts_pass = 0
    junk_pass = 0
    label_pass = 0
    failures: list[str] = []
    for case in fixture.extraction:
        text = html_to_text(case.html).casefold()
        # 사실/군더더기 판정은 대소문자를 구분하지 않는다 — 문장 첫머리 대문자로 "사실이 없다"가 되면
        # 추출 품질이 아니라 표기 문제를 재게 된다.
        facts_ok = all(fact.casefold() in text for fact in case.required_facts)
        junk_ok = not any(marker.casefold() in text for marker in case.forbidden_markers)
        facts_pass += int(facts_ok)
        junk_pass += int(junk_ok)
        label_ok = facts_ok == case.expect_supported
        label_pass += int(label_ok)
        if not (facts_ok == case.expect_supported and junk_ok):
            failures.append(case.case_id)
    total = max(1, len(fixture.extraction))
    return {
        "case_count": len(fixture.extraction),
        "facts_pass": facts_pass,
        "junk_pass": junk_pass,
        "grounding_label_pass": label_pass,
        "grounding_rate": facts_pass / total,
        "junk_rate": junk_pass / total,
        "label_rate": label_pass / total,
        "failures": failures,
    }


# ── 계약 검사 ────────────────────────────────────────────────────────────────


def contract_checks(
    fixture: EvalFixture,
    cases: Sequence[EvalCase],
    arms: Mapping[str, ArmResult],
    runs: int,
    extraction: Mapping[str, object],
    full_hits: Mapping[str, tuple[str, ...]],
    effective_hits: Mapping[str, tuple[str, ...]],
) -> dict[str, object]:
    """주입을 반영한 payload 로 잰다 — 주입이 지운 근거를 계약이 요구하면 안 된다.

    arm 별로 **허용 집합이 다르다**: legacy arm 은 주입되지 않은 원래 payload 를 보고,
    integrated arm 만 주입된 payload 를 본다(그걸 하나로 합치면 주입 실행이 거짓 계약 실패를 만든다).
    """
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    def allowed_for(arm_name: str, case_id: str) -> set[str]:
        source = effective_hits if arm_name == "integrated" else full_hits
        return {canonicalize_url(url) for url in source.get(case_id, ())}

    hits_by_case = {case.case_id: len(effective_hits.get(case.case_id, ())) for case in cases}
    authority_expected = {
        case.case_id: {
            "legacy": bool(
                {canonicalize_url(url) for url in case.authority_urls} & allowed_for("legacy", case.case_id)
            ),
            "integrated": bool(
                {canonicalize_url(url) for url in case.authority_urls} & allowed_for("integrated", case.case_id),
            ),
        }
        for case in cases
    }

    for name, arm in arms.items():
        if arm.not_run:
            continue
        fabricated: list[str] = []
        over_limit: list[str] = []
        duplicated: list[str] = []
        missing: list[str] = []
        bad_authority: list[str] = []
        warm_differs: list[str] = []
        warm_requests: list[str] = []
        warm_flag_missing: list[str] = []
        nondeterministic: list[str] = []
        for case in cases:
            observations = [o for o in arm.observations if o.case_id == case.case_id]
            if not observations:
                continue
            observation = observations[0]
            allowed = allowed_for(name, case.case_id)
            for _, url, _ in observation.results:
                if canonicalize_url(url) not in allowed:
                    fabricated.append(f"{case.case_id}:{url}")
            if len(observation.results) > ENGINE_MAX_RESULTS:
                over_limit.append(case.case_id)
            if not _unique_returned_urls([url for _, url, _ in observation.results]):
                duplicated.append(case.case_id)
            if hits_by_case[case.case_id] and observation.empty:
                missing.append(case.case_id)
            if case.authority_expectation == "satisfied" and authority_expected[case.case_id][name]:
                if not _has_authoritative(observation.results, case):
                    bad_authority.append(case.case_id)
            if observation.cold_results != observation.warm_results:
                warm_differs.append(case.case_id)
            if observation.cache_supported and observation.warm_provider_requests > 0:
                warm_requests.append(case.case_id)
            if name == "integrated" and observation.warm_cached_flag is False:
                warm_flag_missing.append(case.case_id)
            distinct = {o.cold_results for o in observations}
            if len(observations) >= min(2, runs) and len(distinct) > 1:
                nondeterministic.append(case.case_id)
        check(f"{name}:no_fabricated_sources", not fabricated, ",".join(fabricated[:5]))
        check(f"{name}:result_limit", not over_limit, ",".join(over_limit[:5]))
        check(f"{name}:unique_urls", not duplicated, ",".join(duplicated[:5]))
        check(f"{name}:non_empty_results", not missing, ",".join(missing[:5]))
        check(f"{name}:authority_required", not bad_authority, ",".join(bad_authority[:5]))
        check(f"{name}:warm_equals_cold", not warm_differs, ",".join(warm_differs[:5]))
        check(f"{name}:warm_adds_no_provider_requests", not warm_requests, ",".join(warm_requests[:5]))
        check(f"{name}:warm_cache_flag_preserved", not warm_flag_missing, ",".join(warm_flag_missing[:5]))
        check(f"{name}:deterministic_across_runs", not nondeterministic, ",".join(nondeterministic[:5]))

    check("extraction:facts_present_when_expected", int(cast(int, extraction["label_rate"]) * 1000) == 1000)
    check("extraction:no_boilerplate_leak", int(cast(int, extraction["junk_rate"]) * 1000) == 1000)
    check("fixture:cases_loaded", len(cases) == len(fixture.cases), f"{len(cases)}/{len(fixture.cases)}")
    passed = sum(1 for entry in checks if entry["passed"])
    return {
        "passed": passed,
        "total": len(checks),
        "pass_rate": passed / len(checks) if checks else 0.0,
        "failures": [entry["name"] for entry in checks if not entry["passed"]],
        "checks": checks,
    }


# ── gate ─────────────────────────────────────────────────────────────────────


def _ratio(candidate: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0 if candidate <= 0 else float("inf")
    return candidate / baseline


def evaluate_gate(
    report: Mapping[str, object],
    anchor: Mapping[str, object] | None,
    paired: bool,
) -> list[dict[str, object]]:
    thresholds = THRESHOLDS
    contract = cast(Mapping[str, object], report["contract"])
    arms = cast(Mapping[str, Mapping[str, object]], report["arms"])
    integrated = cast(Mapping[str, object], arms["integrated"]["metrics"])
    comparison = cast(Mapping[str, object], report["comparison"])
    canary = cast(Mapping[str, object], report["canary"])
    checks: list[dict[str, object]] = []

    def check(name: str, kind: str, observed: float, limit: float, ok: bool, detail: str = "") -> None:
        checks.append(
            {"name": name, "kind": kind, "observed": observed, "limit": limit, "passed": bool(ok), "detail": detail}
        )

    contract_rate = float(cast(float, contract["pass_rate"]))
    check(
        "contract_pass_rate",
        "contract",
        contract_rate,
        float(thresholds["contract_min_pass_rate"]),
        contract_rate >= float(thresholds["contract_min_pass_rate"]),
        ",".join(cast(list[str], contract["failures"])[:8]),
    )
    if anchor is None:
        check(
            "anchor_present", "anchor", 0.0, 1.0, False, "anchor.json 이 없다 — --refresh-anchor --reason 으로 만든다"
        )
        return checks

    anchor_fixture = str(anchor.get("fixture_sha256") or "")
    fixture = cast(Mapping[str, object], report["fixture"])
    fixture_match = anchor_fixture == str(fixture["sha256"])
    check(
        "anchor_fixture_unchanged",
        "anchor",
        1.0 if fixture_match else 0.0,
        1.0,
        fixture_match,
        "고정 검색셋이 바뀌었다 — 같은 사유를 적고 --refresh-anchor 로 기준선을 다시 뜬다",
    )
    anchor_arms = cast(Mapping[str, Mapping[str, object]], anchor.get("arms") or {})
    anchor_cmp = cast(Mapping[str, object], anchor.get("comparison") or {})
    anchor_integrated = anchor_arms.get("integrated", {}).get("metrics") if anchor_arms else None
    if not isinstance(anchor_integrated, Mapping):
        check("anchor_has_integrated", "anchor", 0.0, 1.0, False, "기준선에 integrated arm 이 없다")
        return checks
    anchor_metrics = cast(Mapping[str, object], anchor_integrated)

    def metric(mapping: Mapping[str, object], key: str) -> float:
        value = mapping.get(key)
        return float(value) if isinstance(value, (int, float)) else 0.0

    # 1) 절대 기준선 대비 (nDCG · 유효 출처 · 비용)
    ndcg = metric(integrated, "ndcg_at_k")
    anchor_ndcg = metric(anchor_metrics, "ndcg_at_k")
    check(
        "integrated_ndcg_at_k",
        "absolute",
        ndcg,
        anchor_ndcg - float(thresholds["ndcg_drop_max"]),
        ndcg >= anchor_ndcg - float(thresholds["ndcg_drop_max"]),
        f"기준선 {anchor_ndcg:.4f}",
    )
    sources = metric(integrated, "valid_source_ratio")
    anchor_sources = metric(anchor_metrics, "valid_source_ratio")
    check(
        "integrated_valid_source_ratio",
        "absolute",
        sources,
        anchor_sources - float(thresholds["valid_source_drop_max"]),
        sources >= anchor_sources - float(thresholds["valid_source_drop_max"]) - 1e-9,
        f"기준선 {anchor_sources:.4f}",
    )
    tokens = metric(integrated, "tokens_per_query")
    anchor_tokens = metric(anchor_metrics, "tokens_per_query")
    cost_limit = anchor_tokens * (1.0 + float(thresholds["cost_increase_max"]))
    check(
        "integrated_cost_tokens",
        "absolute",
        tokens,
        cost_limit,
        tokens <= cost_limit + 1e-9,
        f"기준선 {anchor_tokens:.1f} tokens/query",
    )
    p95 = metric(integrated, "p95_cold_ms")
    anchor_p95 = metric(anchor_metrics, "p95_cold_ms")
    machine = cast(Mapping[str, object], report["machine"])
    anchor_machine = cast(Mapping[str, object], anchor.get("machine") or {})
    same_machine = all(
        str(machine.get(key)) == str(anchor_machine.get(key)) for key in ("platform", "machine", "python", "cpu_count")
    )
    p95_limit = anchor_p95 * (1.0 + float(thresholds["p95_increase_max"]))
    p95_growth = p95 - anchor_p95
    if same_machine:
        check(
            "integrated_p95_cold_ms",
            "absolute",
            p95,
            p95_limit,
            p95 <= p95_limit or p95_growth <= LATENCY_NOISE_FLOOR_MS,
            f"기준선 {anchor_p95:.2f}ms · 증가 {p95_growth:+.2f}ms · 잡음 하한 {LATENCY_NOISE_FLOOR_MS:.1f}ms",
        )
    else:
        checks.append(
            {
                "name": "integrated_p95_cold_ms",
                "kind": "inconclusive",
                "observed": p95,
                "limit": p95_limit,
                "passed": True,
                "detail": "기계 지문이 기준선과 다르다 — 절대 지연 비교는 비율 비교로 대신한다(자동 완화 아님)",
            },
        )

    # 2) 같은 실행 안의 paired 비교(기계 무관) — 기준선의 같은 비율과 비교한다
    if paired:
        ndcg_gap = metric(comparison, "ndcg_gap")
        anchor_gap = metric(anchor_cmp, "ndcg_gap")
        check(
            "paired_ndcg_gap",
            "paired",
            ndcg_gap,
            anchor_gap - float(thresholds["ndcg_drop_max"]),
            ndcg_gap >= anchor_gap - float(thresholds["ndcg_drop_max"]),
            f"integrated − legacy · 기준선 {anchor_gap:+.4f}",
        )
        source_gap = metric(comparison, "valid_source_ratio_gap")
        anchor_source_gap = metric(anchor_cmp, "valid_source_ratio_gap")
        check(
            "paired_valid_source_gap",
            "paired",
            source_gap,
            anchor_source_gap - float(thresholds["valid_source_drop_max"]),
            source_gap >= anchor_source_gap - float(thresholds["valid_source_drop_max"]) - 1e-9,
            f"integrated − legacy · 기준선 {anchor_source_gap:+.4f}",
        )
        p95_ratio = metric(comparison, "p95_ratio")
        anchor_ratio = metric(anchor_cmp, "p95_ratio")
        ratio_limit = anchor_ratio * (1.0 + float(thresholds["p95_increase_max"]))
        check(
            "paired_p95_ratio",
            "paired",
            p95_ratio,
            ratio_limit,
            p95_ratio <= ratio_limit or (p95 - anchor_p95) <= LATENCY_NOISE_FLOOR_MS,
            f"integrated/legacy · 기준선 {anchor_ratio:.3f} · 증가 {p95 - anchor_p95:+.2f}ms",
        )
        token_ratio = metric(comparison, "token_ratio")
        anchor_token_ratio = metric(anchor_cmp, "token_ratio")
        token_ratio_limit = anchor_token_ratio * (1.0 + float(thresholds["cost_increase_max"]))
        check(
            "paired_token_ratio",
            "paired",
            token_ratio,
            token_ratio_limit,
            token_ratio <= token_ratio_limit,
            f"integrated/legacy · 기준선 {anchor_token_ratio:.3f}",
        )

    # 3) 주입이 실제로 검출되는지 — 주입은 **자기가 겨눈 지표**로 검출돼야 한다
    if canary:
        injection = str(cast(Mapping[str, object], report["config"])["inject"] or "")
        targets = CANARY_TARGETS.get(injection, ())
        failed = {str(entry["name"]) for entry in checks if not entry["passed"]}
        check(
            "canary_detected",
            "canary",
            1.0 if (set(targets) & failed) else 0.0,
            1.0,
            bool(set(targets) & failed),
            f"겨눈 검사 {list(targets)} · 실패 {sorted(set(targets) & failed)} · 물리 증거: {canary.get('detail', '')}",
        )
    return checks


def build_comparison(arms: Mapping[str, ArmResult], cases: Sequence[EvalCase], k: int) -> dict[str, object]:
    integrated = cast(dict[str, object], aggregate(cases, arms["integrated"].observations, k))
    legacy = cast(dict[str, object], aggregate(cases, arms["legacy"].observations, k))
    ndcg_gap = float(cast(float, integrated["ndcg_at_k"])) - float(cast(float, legacy["ndcg_at_k"]))
    source_gap = float(cast(float, integrated["valid_source_ratio"])) - float(cast(float, legacy["valid_source_ratio"]))
    return {
        "ndcg_gap": ndcg_gap,
        "valid_source_ratio_gap": source_gap,
        "p95_ratio": _ratio(float(cast(float, integrated["p95_cold_ms"])), float(cast(float, legacy["p95_cold_ms"]))),
        "token_ratio": _ratio(
            float(cast(float, integrated["tokens_per_query"])), float(cast(float, legacy["tokens_per_query"]))
        ),
    }


# ── 실행 ─────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class RunConfig:
    runs: int
    provider: str
    injection: str | None
    delay_ms: int
    k: int
    limit: int | None
    quiet: bool


def _machine() -> dict[str, object]:
    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 0,
    }


async def run_benchmark(
    fixture: EvalFixture, config: RunConfig
) -> tuple[dict[str, ArmResult], dict[str, object], list[str]]:
    cases = fixture.cases
    k = config.k
    arms: dict[str, ArmResult] = {}
    not_run: list[str] = []
    cache_dir = Path(tempfile.mkdtemp(prefix="ssak-search-eval-cache-"))
    original_cache_dir = _cache_module.CACHE_DIR
    _cache_module.CACHE_DIR = cache_dir  # 전역 캐시 디렉터리 격리(다른 실행·사용자 캐시와 섞이지 않게)
    legacy: LegacyArm | None = None
    integrated: IntegratedArm | None = None
    workdir = Path(tempfile.mkdtemp(prefix="ssak-search-eval-"))
    try:
        if config.provider in {"both", "legacy"}:
            legacy = LegacyArm(cases, k)
            arms["legacy"] = ArmResult(name="legacy")
        if config.provider in {"both", "integrated"}:
            payload = workdir / "payload.json"
            write_payload_file(cases, config.injection, payload)
            integrated = IntegratedArm(
                payload_path=payload,
                child_path=CHILD_DEFAULT,
                calls_file=workdir / "child-calls.json",
                delay_ms=config.delay_ms,
                shuffle=config.injection == "noisy",
            )
            arms["integrated"] = ArmResult(name="integrated")

        # 워밍업(측정 제외): child spawn 과 HTTP 클라이언트 생성은 **한 번** 드는 비용이다.
        # 그 한 번을 첫 케이스의 p95 에 얹으면 지연 회귀 판정이 "프로세스 시작 시간"을 재게 된다.
        if cases:
            if legacy is not None:
                _ = await legacy.run_case(cases[0])
            if integrated is not None:
                _ = integrated.run_case(cases[0])

        for run_index in range(config.runs):
            for case in cases:
                if legacy is not None:
                    arms["legacy"].observations.append(await legacy.run_case(case))
                if integrated is not None:
                    arms["integrated"].observations.append(integrated.run_case(case))
            if not config.quiet:
                print(f"  run {run_index + 1}/{config.runs} 완료", file=sys.stderr)

        if integrated is not None:
            status = integrated.status()
            observations = arms["integrated"].observations
            all_failed = (
                observations and all(o.error for o in observations) and not any(o.results for o in observations)
            )
            if all_failed:
                detail = f"child state={status.get('state')} last_error={status.get('last_error')}"
                arms["integrated"].not_run = detail
                not_run.append(f"integrated arm: {detail}")
        return arms, {"cache_dir": str(cache_dir), "workdir": str(workdir)}, not_run
    finally:
        if legacy is not None:
            await legacy.close()
        if integrated is not None:
            integrated.close()
        _cache_module.CACHE_DIR = original_cache_dir


def build_parser() -> argparse.ArgumentParser:
    """CLI 표면. **임계값을 낮추는 플래그는 여기에 없다**(그 사실도 시험이 잰다)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--paired", action="store_true", help="legacy↔integrated 짝 비교까지 gate 에 포함한다")
    _ = parser.add_argument("--runs", type=int, default=3)
    _ = parser.add_argument("--provider", choices=("both", "legacy", "integrated"), default="both")
    _ = parser.add_argument("--limit", type=int, default=None, help="앞에서 N 개 케이스만(시험/스모크용)")
    _ = parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    _ = parser.add_argument("--anchor", type=Path, default=ANCHOR_DEFAULT)
    _ = parser.add_argument(
        "--refresh-anchor", action="store_true", help="현재 실행을 새 기준선으로 기록한다(사유 필수)"
    )
    _ = parser.add_argument("--reason", default="", help="--refresh-anchor 사유(리포트·기준선에 기록)")
    _ = parser.add_argument(
        "--inject", choices=INJECTIONS, default=None, help="integrated arm provider 주입(음성 대조)"
    )
    _ = parser.add_argument("--inject-delay-ms", type=int, default=150)
    _ = parser.add_argument("--waiver-cause", default="")
    _ = parser.add_argument("--waiver-user-value", default="")
    _ = parser.add_argument("--waiver-approved-by", default="")
    _ = parser.add_argument("--print-json", action="store_true")
    _ = parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    waiver_values = [args.waiver_cause, args.waiver_user_value, args.waiver_approved_by]
    if any(waiver_values) and not all(waiver_values):
        print("waiver 는 원인·사용자 가치·승인자를 모두 적어야 한다(자동 완화 금지)", file=sys.stderr)
        return 2
    if args.refresh_anchor and not args.reason.strip():
        print("--refresh-anchor 에는 --reason 이 필요하다(기준선 갱신은 기록되는 행위다)", file=sys.stderr)
        return 2
    if args.paired and args.provider != "both":
        print("--paired 는 두 arm 이 모두 필요하다(--provider both)", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("--runs 는 1 이상이어야 한다", file=sys.stderr)
        return 2

    try:
        fixture = load_fixture(args.limit)
    except FixtureError as error:
        print(f"fixture 오류: {error}", file=sys.stderr)
        return 2

    config = RunConfig(
        runs=args.runs,
        provider=args.provider,
        injection=args.inject,
        # 지연은 **slow 주입일 때만** 건다 — 아니면 기준선 자체가 지연을 품어 주입이 가려진다(실제로 그럴 뻔했다).
        delay_ms=args.inject_delay_ms if args.inject == "slow" else 0,
        k=fixture.k,
        limit=args.limit,
        quiet=args.quiet,
    )
    started_at = time.time()
    arms, environment, not_run = asyncio.run(run_benchmark(fixture, config))
    finished_at = time.time()

    extraction = extraction_block(fixture)
    report: dict[str, object] = {
        "task": "task-24",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished_at)),
        "elapsed_seconds": round(finished_at - started_at, 2),
        "fixture": {
            "version": fixture.version,
            "sha256": fixture.sha256,
            "case_count": len(fixture.cases),
            "extraction_case_count": len(fixture.extraction),
        },
        "config": {
            "paired": bool(args.paired),
            "runs": args.runs,
            "provider": args.provider,
            "k": fixture.k,
            "limit": args.limit,
            "inject": args.inject,
            "inject_delay_ms": args.inject_delay_ms if args.inject == "slow" else 0,
        },
        "machine": _machine(),
        "environment": environment,
        "thresholds": dict(THRESHOLDS),
        "latency_noise_floor_ms": LATENCY_NOISE_FLOOR_MS,
        "extraction": extraction,
        "arms": {
            name: {
                "metrics": aggregate(fixture.cases, arm.observations, fixture.k),
                "not_run": arm.not_run,
                "cases": [
                    {
                        "case_id": observation.case_id,
                        "cold_ms": observation.cold_ms,
                        "warm_ms": observation.warm_ms,
                        "tokens": observation.tokens,
                        "error": observation.error,
                        "top_urls": [url for _, url, _ in observation.results[: fixture.k]],
                    }
                    for observation in arm.observations
                ],
            }
            for name, arm in arms.items()
        },
        "comparison": build_comparison(arms, fixture.cases, fixture.k) if len(arms) == 2 else {},
        "canary": _canary_block(args.inject, arms),
        "not_run": not_run,
    }
    full_hits = {case.case_id: tuple(hit.url for hit in case.hits) for case in fixture.cases}
    effective_hits = {
        case.case_id: tuple(hit.url for hit in _injected_hits(case, args.inject)) for case in fixture.cases
    }
    report["effective_hits"] = {case_id: list(urls) for case_id, urls in effective_hits.items()}
    report["contract"] = contract_checks(fixture, fixture.cases, arms, args.runs, extraction, full_hits, effective_hits)

    anchor: Mapping[str, object] | None = None
    if args.anchor.exists():
        anchor = cast(Mapping[str, object], json.loads(args.anchor.read_text(encoding="utf-8")))

    if args.refresh_anchor:
        refreshed = {
            "task": "task-24",
            "created_at": report["started_at"],
            "reason": args.reason.strip(),
            "actor": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "fixture_version": fixture.version,
            "fixture_sha256": fixture.sha256,
            "machine": report["machine"],
            "config": report["config"],
            "thresholds": dict(THRESHOLDS),
            "arms": {
                name: {"metrics": entry["metrics"]}  # type: ignore[union-attr]
                for name, entry in cast(Mapping[str, Mapping[str, object]], report["arms"]).items()
            },
            "comparison": report["comparison"],
            "extraction": {key: extraction[key] for key in ("case_count", "grounding_rate", "junk_rate", "label_rate")},
        }
        args.anchor.parent.mkdir(parents=True, exist_ok=True)
        args.anchor.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"⚠️  기준선을 갱신했다: {args.anchor} (사유: {args.reason.strip()})")
        anchor = refreshed

    checks = evaluate_gate(report, anchor, bool(args.paired))
    verdict = "PASS" if all(bool(entry["passed"]) for entry in checks) else "FAIL"
    waivers: list[dict[str, object]] = []
    if verdict == "FAIL" and all(waiver_values):
        waivers.append(
            {"cause": args.waiver_cause, "user_value": args.waiver_user_value, "approved_by": args.waiver_approved_by}
        )
        verdict = "PASS_WITH_WAIVER"
    report["waivers"] = waivers
    report["gate"] = {
        "verdict": verdict,
        "checks": checks,
        "failed": [entry["name"] for entry in checks if not entry["passed"]],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report)
    if not_run:
        print(f"NOT_RUN: {'; '.join(not_run)}", file=sys.stderr)
        return 3
    return 0 if verdict in {"PASS", "PASS_WITH_WAIVER"} else 1


def _canary_block(injection: str | None, arms: Mapping[str, ArmResult]) -> dict[str, object]:
    """주입 실행의 **물리 증거**(검출 판정은 gate 가 겨눈 검사로 한다)."""
    if not injection:
        return {}
    integrated = arms.get("integrated")
    block: dict[str, object] = {
        "injection": injection,
        "targets": list(CANARY_TARGETS.get(injection, ())),
        "arm_measured": bool(integrated is not None and integrated.observations and not integrated.not_run),
    }
    if integrated is None or not integrated.observations:
        block["detail"] = "integrated arm 을 측정하지 못했다"
        return block
    if injection == "empty":
        block["detail"] = f"빈 결과 {sum(1 for o in integrated.observations if o.empty)}건"
    elif injection == "noisy":
        per_case: dict[str, set[tuple[str, ...]]] = {}
        for observation in integrated.observations:
            per_case.setdefault(observation.case_id, set()).add(observation.cold_results)
            per_case[observation.case_id].add(observation.warm_results)
        block["detail"] = f"순서가 흔들린 케이스 {sum(1 for values in per_case.values() if len(values) > 1)}건"
    elif injection == "slow":
        block["detail"] = f"provider 지연 {os.environ.get('SSAK_SEARCH_EVAL_DELAY_MS', '주입값')}ms"
    else:
        block["detail"] = f"provider payload 를 {injection} 로 열화"
    return block


def _print_summary(report: Mapping[str, object]) -> None:
    fixture = cast(Mapping[str, object], report["fixture"])
    print(f"fixture {fixture['version']} · {fixture['case_count']} cases · sha256 {str(fixture['sha256'])[:12]}")
    for name, entry in cast(Mapping[str, Mapping[str, object]], report["arms"]).items():
        metrics = cast(Mapping[str, object], entry["metrics"])
        if entry.get("not_run"):
            print(f"  {name:11s} NOT_RUN {entry['not_run']}")
            continue
        print(
            f"  {name:11s} nDCG@k={float(cast(float, metrics['ndcg_at_k'])):.4f}"
            f" recall@k={float(cast(float, metrics['recall_at_k'])):.4f}"
            f" valid={float(cast(float, metrics['valid_source_ratio'])):.4f}"
            f" authority={float(cast(float, metrics['authority_satisfied_rate'])):.3f}"
            f" empty={float(cast(float, metrics['empty_rate'])):.3f}"
            f" err={metrics['error_count']}"
            f" p95={float(cast(float, metrics['p95_cold_ms'])):.1f}ms"
            f" tokens={float(cast(float, metrics['tokens_per_query'])):.0f}",
        )
    comparison = cast(Mapping[str, object], report["comparison"])
    if comparison:
        print(
            f"  paired      ΔnDCG={float(cast(float, comparison['ndcg_gap'])):+.4f}"
            f" Δvalid={float(cast(float, comparison['valid_source_ratio_gap'])):+.4f}"
            f" p95 ratio={float(cast(float, comparison['p95_ratio'])):.3f}"
            f" token ratio={float(cast(float, comparison['token_ratio'])):.3f}",
        )
    extraction = cast(Mapping[str, object], report["extraction"])
    print(
        f"  extraction  grounding={float(cast(float, extraction['grounding_rate'])):.3f}"
        f" junk-free={float(cast(float, extraction['junk_rate'])):.3f}"
        f" label={float(cast(float, extraction['label_rate'])):.3f}",
    )
    contract = cast(Mapping[str, object], report["contract"])
    print(
        f"  contract    {contract['passed']}/{contract['total']} (rate {float(cast(float, contract['pass_rate'])):.3f})"
    )
    gate = cast(Mapping[str, object], report["gate"])
    print(f"  gate        {gate['verdict']}")
    for entry in cast(list[Mapping[str, object]], gate["checks"]):
        if not entry["passed"]:
            print(
                f"    ✗ {entry['name']} observed={entry['observed']} limit={entry['limit']} {entry.get('detail', '')}"
            )
    for waiver in cast(list[Mapping[str, object]], report["waivers"]):
        print(f"    ⚠️ waiver: {waiver['cause']} · 가치: {waiver['user_value']} · 승인: {waiver['approved_by']}")


if __name__ == "__main__":
    raise SystemExit(main())
