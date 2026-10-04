"""웹 검색 엔진 — 비동기 Multi-Engine 검색.

WebSearchEngine (async search), PageScraper (URL 본문 추출).
web_search.py에서 분리됨 (Phase 23 리팩토링).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import cast, final, override
from urllib.parse import quote_plus, urljoin, urlsplit

import anyio
import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

from .crawler_policy import LegalTermsPolicy, RobotsRateLimitPolicy
from .egress_policy import validate_httpx_request, validate_httpx_request_async
from .search_auth import SEARCH_TOKEN_ENV, search_auth_headers
from .search_conflicts import source_conflict_sets
from .search_quality_evaluator import (
    CitationEvaluationReport,
    citation_sources_from_results,
    evaluate_citations,
)
from .web_html import html_to_text as html_to_text
from .web_reader import ReaderRejected, read_text_response, read_text_response_async
from .web_search_cache import SearchCache, _generate_fallback_queries
from .web_search_html import is_duckduckgo_challenge, parse_duckduckgo_results
from .web_search_models import SearchResponse, SearchResult
from .web_search_quality import (
    has_authoritative_query_result,
    has_query_relevant_result,
    is_public_http_url,
    official_source_hints,
    rank_search_results,
    requires_authoritative_sources,
    resolve_public_http_url,
    resolve_public_http_url_sync,
    sanitize_untrusted_text,
    source_id_for_url,
)

logger = logging.getLogger("web_search")


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw: dict[object, object] = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _json_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    raw: list[object] = cast(list[object], value)
    return list(raw)


def _json_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _json_float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


@final
class WebSearchEngine:
    """통합 웹 검색 엔진.

    검색 우선순위:
        1. 로컬 캐시 조회
        2. Tavily AI (API 키 설정 시)
        3. SearXNG (자체 호스팅)
        4. Jina Search (무료 시맨틱 검색)
        5. DuckDuckGo HTML (최종 폴백)

    Args:
        searxng_url: SearXNG 인스턴스 URL (선택)
        max_results: 최대 결과 수
        cache_ttl_hours: 캐시 유효 시간
    """

    def __init__(
        self,
        searxng_url: str | None = None,
        max_results: int = 8,
        cache_ttl_hours: int = 24,
    ) -> None:
        self.searxng_url = searxng_url or os.environ.get("SEARXNG_URL", "http://localhost:8080")
        self.tavily_api_key = os.environ.get("TAVILY_API_KEY")
        self.self_hosted_url = os.environ.get("AGK_SEARCH_ENGINE_URL", "").strip().rstrip("/") or None
        try:
            self.fallback_budget_ms = float(os.environ.get("AGK_SEARCH_FALLBACK_BUDGET_MS", "1500"))
        except ValueError:
            self.fallback_budget_ms = 1500.0
        self.max_results = max_results
        self.fetch_results = max(max_results, min(max_results * 3, 24))
        self.cache: SearchCache = SearchCache(ttl_hours=cache_ttl_hours)
        self._client: httpx.AsyncClient | None = None
        self._provider_cooldowns: dict[str, float] = {}

    def _provider_available(self, provider: str) -> bool:
        return time.monotonic() >= self._provider_cooldowns.get(provider, 0.0)

    def _provider_succeeded(self, provider: str) -> None:
        _ = self._provider_cooldowns.pop(provider, None)

    def _provider_failed(self, provider: str) -> None:
        self._provider_cooldowns[provider] = time.monotonic() + 30.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=15.0,
                event_hooks={"request": [validate_httpx_request_async]},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ─── DuckDuckGo 검색 ─────────────────────────────────────────

    def _is_captcha_response(self, html: str) -> bool:
        """DuckDuckGo CAPTCHA/봇 탐지 페이지인지 확인."""
        return is_duckduckgo_challenge(html)

    async def _search_duckduckgo(self, query: str) -> list[SearchResult]:
        """DuckDuckGo HTML 검색 (API 키 불필요)."""
        if not self._provider_available("duckduckgo"):
            return await self._search_duckduckgo_lite(query)
        client = await self._get_client()
        results: list[SearchResult] = []

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp: httpx.Response | None = None
            for attempt in range(3):
                resp = await client.get(url, timeout=5.0)
                if resp.status_code != 202 or attempt == 2:
                    break
                await anyio.sleep(0.25 * (attempt + 1))

            if resp is None:
                return results
            if resp.status_code != 200:
                self._provider_failed("duckduckgo")
                logger.warning("DuckDuckGo 응답 실패: %s", resp.status_code)
                return await self._search_duckduckgo_lite(query)

            html = resp.text
            # CAPTCHA 감지 시 바로 폴백으로 전환
            if self._is_captcha_response(html):
                self._provider_failed("duckduckgo")
                logger.warning("DuckDuckGo CAPTCHA 감지 - Lite 버전으로 폴백")
                return await self._search_duckduckgo_lite(query)

            self._provider_succeeded("duckduckgo")

            for index, result in enumerate(parse_duckduckgo_results(html, self.fetch_results)):
                results.append(
                    SearchResult(
                        title=result.title,
                        url=result.url,
                        snippet=result.snippet,
                        source="DuckDuckGo",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=1.0 - (index * 0.1),
                    ),
                )
            if not results:
                return await self._search_duckduckgo_lite(query)
        except httpx.RequestError:
            self._provider_failed("duckduckgo")
            logger.warning("DuckDuckGo 검색 오류")
            return await self._search_duckduckgo_lite(query)

        return results

    async def _search_duckduckgo_lite(self, query: str) -> list[SearchResult]:
        if not self._provider_available("duckduckgo_lite"):
            return []

        client = await self._get_client()
        try:
            response = await client.get(
                f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}",
                timeout=8.0,
            )
            if response.status_code != 200:
                self._provider_failed("duckduckgo_lite")
                return []

            response_text = response.text
            # CAPTCHA 감지 시 빈 결과 반환 (폴백 체인에서 다음 엔진 시도)
            if self._is_captcha_response(response_text):
                self._provider_failed("duckduckgo_lite")
                logger.warning("DuckDuckGo Lite CAPTCHA 감지")
                return []

            results: list[SearchResult] = []
            for index, result in enumerate(parse_duckduckgo_results(response_text, self.fetch_results)):
                results.append(
                    SearchResult(
                        title=result.title,
                        url=result.url,
                        snippet=result.snippet,
                        source="DuckDuckGo Lite",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=1.0 - (index * 0.08),
                    ),
                )
            self._provider_succeeded("duckduckgo_lite")
            return results
        except httpx.RequestError:
            self._provider_failed("duckduckgo_lite")
            logger.warning("DuckDuckGo Lite 검색 오류")
            return []

    # ─── Tavily AI 검색 ───────────────────────────────────────────

    async def _search_tavily(self, query: str) -> list[SearchResult]:
        """Tavily AI API — LLM-Ready 정제 데이터."""
        if not self.tavily_api_key:
            return []
        if not self._provider_available("tavily"):
            return []

        client = await self._get_client()
        results: list[SearchResult] = []

        try:
            payload = {
                "api_key": self.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": self.fetch_results,
            }
            resp = await client.post("https://api.tavily.com/search", json=payload, timeout=15.0)

            if resp.status_code != 200:
                self._provider_failed("tavily")
                return results
            self._provider_succeeded("tavily")

            data = _json_object(cast(object, resp.json()))
            for i, item in enumerate(_json_list(data.get("results"))[: self.fetch_results]):
                item_data = _json_object(item)
                results.append(
                    SearchResult(
                        title=_json_text(item_data.get("title")),
                        url=_json_text(item_data.get("url")),
                        snippet=_json_text(item_data.get("content")),
                        source="Tavily AI",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=_json_float(item_data.get("score"), 1.0 - i * 0.1),
                    ),
                )
        except httpx.RequestError:
            self._provider_failed("tavily")
            logger.warning("Tavily AI 검색 오류")

        return results

    async def _search_self_hosted(self, query: str) -> list[SearchResult]:
        if not self.self_hosted_url or not self._provider_available("self_hosted"):
            return []

        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.self_hosted_url}/api/search",
                json={
                    "query": query,
                    "max_results": max(self.fetch_results, 10),
                    "include_answer": False,
                    "include_raw_content": False,
                },
                headers=search_auth_headers(),
                timeout=15.0,
            )
            if response.status_code in (401, 403):
                # 이 백엔드는 기본 모드에서 bearer를 요구한다. 조용히 []로 강등하면
                # 모델은 "결과 없음"으로 읽고 원인을 알 수 없다(실제로 그랬다).
                self._provider_failed("self_hosted")
                logger.warning(
                    "Self-hosted search 인증 실패(HTTP %s) — %s(또는 %s)를 설정하세요",
                    response.status_code,
                    SEARCH_TOKEN_ENV,
                    f"{SEARCH_TOKEN_ENV}_FILE",
                )
                return []
            if response.status_code != 200:
                self._provider_failed("self_hosted")
                return []

            payload = _json_object(cast(object, response.json()))
            items = _json_list(payload.get("results"))
            results: list[SearchResult] = []
            for index, item in enumerate(items[: self.fetch_results]):
                item_data = _json_object(item)
                url = _json_text(item_data.get("url"))
                title = _json_text(item_data.get("title"))
                if not url or not title:
                    continue
                relevance_score = _json_float(item_data.get("score"), 1.0 - (index * 0.08))
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=_json_text(item_data.get("content")),
                        source="Ssak-Ai Search",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=max(0.0, min(1.0, relevance_score)),
                    ),
                )
            self._provider_succeeded("self_hosted")
            return results
        except (httpx.RequestError, json.JSONDecodeError, ValueError):
            self._provider_failed("self_hosted")
            logger.warning("Self-hosted search 오류", exc_info=True)
            return []

    # ─── SearXNG 검색 ────────────────────────────────────────────

    async def _search_searxng(self, query: str) -> list[SearchResult]:
        """SearXNG 자체 호스팅 검색 엔진."""
        if not self.searxng_url or not self._provider_available("searxng"):
            return []

        client = await self._get_client()
        results: list[SearchResult] = []

        try:
            params: dict[str, str | int] = {
                "q": query,
                "format": "json",
                "language": "ko-KR",
                "safesearch": 0,
            }
            resp = await client.get(f"{self.searxng_url}/search", params=params)

            if resp.status_code != 200:
                self._provider_failed("searxng")
                return results
            self._provider_succeeded("searxng")

            data = _json_object(cast(object, resp.json()))
            for i, item in enumerate(_json_list(data.get("results"))[: self.max_results]):
                item_data = _json_object(item)
                results.append(
                    SearchResult(
                        title=_json_text(item_data.get("title")),
                        url=_json_text(item_data.get("url")),
                        snippet=_json_text(item_data.get("content")),
                        source=f"SearXNG/{_json_text(item_data.get('engine'))}",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=_json_float(item_data.get("score"), 1.0 - i * 0.1),
                    ),
                )
        except httpx.RequestError:
            self._provider_failed("searxng")
            logger.warning("SearXNG 검색 오류")

        return results

    # ─── Jina Search ──────────────────────────────────────────────

    async def _search_jina(self, query: str) -> list[SearchResult]:
        """Jina AI Search Grounding (s.jina.ai) — 무료, API 키 선택적."""
        if not self._provider_available("jina"):
            return []
        client = await self._get_client()
        results: list[SearchResult] = []

        try:
            headers = {"Accept": "application/json"}
            jina_key = os.environ.get("JINA_API_KEY")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"

            resp = await client.get(
                f"https://s.jina.ai/{quote_plus(query)}",
                headers=headers,
                timeout=12.0,
            )

            if resp.status_code != 200:
                self._provider_failed("jina")
                return results
            self._provider_succeeded("jina")

            raw_data = cast(object, resp.json())
            data = _json_object(raw_data)
            items = (
                _json_list(cast(list[object], raw_data))
                if isinstance(raw_data, list)
                else _json_list(
                    data.get("data", data.get("results")),
                )
            )

            for i, item in enumerate(items[: self.fetch_results]):
                item_data = _json_object(item)
                results.append(
                    SearchResult(
                        title=_json_text(item_data.get("title")),
                        url=_json_text(item_data.get("url")),
                        snippet=_json_text(item_data.get("description", item_data.get("content")))[:300],
                        source="Jina Search",
                        timestamp=datetime.now(UTC).isoformat(),
                        relevance_score=1.0 - (i * 0.08),
                    ),
                )
        except (httpx.RequestError, json.JSONDecodeError):
            self._provider_failed("jina")
            logger.warning("Jina Search 오류 (폴백 전환)")

        return results

    # ─── Jina Reader ──────────────────────────────────────────────

    def extract_content_jina(self, url: str, max_chars: int = 2000) -> str:
        """Jina Reader (r.jina.ai) — URL을 클린 마크다운으로 변환."""
        if resolve_public_http_url_sync(url) is None:
            return ""
        try:
            headers = {"Accept": "text/markdown"}
            jina_key = os.environ.get("JINA_API_KEY")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"

            with httpx.Client(
                timeout=10.0,
                follow_redirects=False,
                event_hooks={"request": [validate_httpx_request]},
            ) as client:
                with client.stream("GET", f"https://r.jina.ai/{url}", headers=headers) as resp:
                    if resp.status_code == 200:
                        text = read_text_response(resp).strip()
                        if len(text) > 50:
                            return text[: max(0, max_chars)]
            return ""
        except ReaderRejected as exc:
            logger.warning("Jina Reader 본문 거부: %s", exc)
            return ""
        except httpx.RequestError:
            logger.warning("Jina Reader 오류", exc_info=True)
            return ""

    _extract_content_jina = extract_content_jina

    # ─── 통합 검색 ───────────────────────────────────────────────

    async def search(
        self,
        query: str,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> SearchResponse:
        """Multi-Engine 통합 웹 검색.

        엔진 우선순위:
            1. 캐시 조회 (force_refresh=False일 때)
            2. Tavily AI (LLM 친화적, 키 설정 시)
            3. 선택적 self-hosted search API
            4. SearXNG (메타 검색 — Google+Bing+DDG 집계)
            5. Jina Search (시맨틱 그라운딩, 무료)
            6. DuckDuckGo HTML/Lite (최종 폴백)
            7. Fallback: 대체 쿼리로 재시도

        Args:
            query: 검색 쿼리
            use_cache: 캐시 사용 여부
            force_refresh: True면 캐시 무시하고 새로 검색
        """
        start = time.time()

        # 1. 캐시 확인
        if use_cache and not force_refresh:
            cached = self.cache.get(query, force_refresh=False)
            if cached:
                logger.info("캐시 히트: '%s' (%d개 결과)", query, len(cached.results))
                return cached

        # 2. Multi-Engine 검색
        all_results: list[SearchResult] = []
        engines_used: list[str] = []
        self_hosted_elapsed_ms = 0.0

        # 2a. Tavily AI
        if self.tavily_api_key:
            tavily_results = await self._search_tavily(query)
            if tavily_results:
                all_results.extend(tavily_results)
                engines_used.append("tavily")

        if self.self_hosted_url:
            provider_started = time.perf_counter()
            self_hosted_results = await self._search_self_hosted(query)
            self_hosted_elapsed_ms = (time.perf_counter() - provider_started) * 1000
            if self_hosted_results:
                all_results.extend(self_hosted_results)
                engines_used.append("self-hosted")

        # 2b. SearXNG
        if self.searxng_url and (len(all_results) < self.max_results or len(engines_used) < 2):
            searxng_results = await self._search_searxng(query)
            if searxng_results:
                all_results.extend(searxng_results)
                engines_used.append("searxng")

        # 2c. Jina Search
        if len(all_results) < self.max_results or len(engines_used) < 2:
            jina_results = await self._search_jina(query)
            if jina_results:
                all_results.extend(jina_results)
                engines_used.append("jina")

        # 2d. DuckDuckGo (폴백)
        if len(all_results) < self.max_results or len(engines_used) < 2:
            ddg_results = await self._search_duckduckgo(query)
            if ddg_results:
                all_results.extend(ddg_results)
                engines_used.append("duckduckgo")

        all_results.extend(official_source_hints(query))
        candidate_target = max(self.max_results * 2, self.max_results)
        authority_rescue_needed = requires_authoritative_sources(query) and not has_authoritative_query_result(
            query,
            all_results,
        )
        if authority_rescue_needed:
            candidate_target = max(candidate_target, len(all_results) + self.max_results)
        fallback_allowed = (
            not self.self_hosted_url or self_hosted_elapsed_ms <= self.fallback_budget_ms or authority_rescue_needed
        )
        fallback_needed = (
            len(engines_used) < 2
            or (len(all_results) <= self.max_results and not has_query_relevant_result(query, all_results))
            or authority_rescue_needed
        )
        if fallback_allowed and fallback_needed:
            fallback_queries = _generate_fallback_queries(query)
            for fb_query in fallback_queries[1:4]:
                if len(all_results) >= candidate_target:
                    break
                fb_results = await self._search_self_hosted(fb_query)
                if not has_query_relevant_result(fb_query, fb_results):
                    fb_results.extend(await self._search_jina(fb_query))
                if not has_query_relevant_result(fb_query, fb_results):
                    fb_results.extend(await self._search_searxng(fb_query))
                if not has_query_relevant_result(fb_query, fb_results):
                    fb_results.extend(await self._search_duckduckgo(fb_query))
                if fb_results:
                    all_results.extend(fb_results)
                    engines_used.append("fallback")

        final_results = rank_search_results(all_results, max_results=self.max_results, query=query)

        elapsed = (time.time() - start) * 1000
        engine_label = "+".join(engines_used) if engines_used else "none"

        response = SearchResponse(
            query=query,
            results=final_results,
            total_results=len(final_results),
            search_time_ms=round(elapsed, 1),
            engine=engine_label,
        )

        if final_results:
            self.cache.set(query, response)
        elif use_cache and not force_refresh:
            stale = self.cache.get_stale(query)
            if stale and stale.results:
                stale.engine = f"stale-cache/{stale.engine or 'cache'}"
                stale.search_time_ms = round(elapsed, 1)
                logger.warning("provider 실패로 만료 캐시 사용: '%s'", query)
                return stale

        return response

    # ─── LLM 컨텍스트 생성 ──────────────────────────────────────

    def format_for_llm(self, response: SearchResponse, max_chars: int = 3000) -> str:
        """검색 결과를 LLM이 이해할 수 있는 포맷으로 변환합니다."""
        if not response.results:
            return f"[웹 검색] '{response.query}' — 결과 없음"

        lines = [
            f"[웹 검색 결과] 쿼리: '{response.query}' ({response.engine}, {len(response.results)}개)",
            "",
        ]

        conflict_sets = source_conflict_sets(citation_sources_from_results(response.results))
        if conflict_sets:
            lines.append("[search_conflicts]")
            lines.extend(f"[citation:{first}] [citation:{second}]" for first, second in conflict_sets)
            lines.extend(("[/search_conflicts]", ""))

        chars_used = sum(len(line) for line in lines)
        for i, r in enumerate(response.results, 1):
            citation = r.source_id or source_id_for_url(r.url)
            entry = (
                f"{i}. [citation:{citation}] **{sanitize_untrusted_text(r.title, 240)}**\n"
                "   [untrusted_web_content]\n"
                f"{sanitize_untrusted_text(r.snippet, wrap=False)}\n"
                "   [/untrusted_web_content]\n"
                f"   🔗 {r.url}\n"
            )
            if chars_used + len(entry) > max_chars:
                lines.append(f"... (나머지 {len(response.results) - i + 1}개 결과 생략)")
                break
            lines.append(entry)
            chars_used += len(entry)

        return "\n".join(lines)

    def evaluate_response(
        self,
        response_text: str,
        results: SearchResponse | Sequence[SearchResult],
        conflict_sets: Iterable[Iterable[str]] = (),
    ) -> CitationEvaluationReport:
        search_results = results.results if isinstance(results, SearchResponse) else results
        return evaluate_citations(
            response_text,
            citation_sources_from_results(search_results),
            conflict_sets=conflict_sets,
        )

    async def search_and_summarize(self, query: str) -> str:
        """검색 후 LLM 컨텍스트 포맷으로 반환하는 원스텝 API."""
        response = await self.search(query)
        return self.format_for_llm(response)


# ─── 신뢰 도메인 부스팅 ──────────────────────────────────────────


def _boost_by_trusted_domains(results: list[SearchResult], query: str):
    """신뢰 도메인 기반 relevance_score 부스팅."""
    trusted_domains = [
        "naver.com",
        "google.com",
        "daum.net",
        "kma.go.kr",
        "wikipedia.org",
        "namu.wiki",
    ]
    for r in results:
        if any(domain in r.url for domain in trusted_domains):
            r.relevance_score += 5.0
        if ("weather" in query or "날씨" in query) and ("weather.naver.com" in r.url or "kma.go.kr" in r.url):
            r.relevance_score += 15.0


# ─── 웹 페이지 스크래핑 ──────────────────────────────────────────


@final
class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, delegate: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._delegate = delegate or AutoBackend()
        self._pins: dict[str, str] = {}

    def pin(self, hostname: str, address: str) -> None:
        self._pins[hostname.rstrip(".").lower()] = address

    @override
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]]
        | None = None,
    ) -> httpcore.AsyncNetworkStream:
        address = self._pins.get(host.rstrip(".").lower())
        if address is None:
            raise httpcore.ConnectError(f"No pinned address for {host}")
        return await self._delegate.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    @override
    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]]
        | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._delegate.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    @override
    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


@final
class _PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pinned_backend: _PinnedNetworkBackend = _PinnedNetworkBackend()
        setattr(self._pool, "_network_backend", self._pinned_backend)

    def pin(self, hostname: str, address: str) -> None:
        self._pinned_backend.pin(hostname, address)


@final
class PageScraper:
    """검색 결과 URL의 본문을 추출합니다."""

    def __init__(self, legal_policy: LegalTermsPolicy | None = None) -> None:
        self._client: httpx.AsyncClient | None = None
        self._transport: _PinnedAsyncHTTPTransport | None = None
        self._crawl_policy = RobotsRateLimitPolicy()
        self._legal_policy = legal_policy or LegalTermsPolicy.from_env()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._transport = _PinnedAsyncHTTPTransport()
            self._client = httpx.AsyncClient(
                transport=self._transport,
                timeout=10.0,
                event_hooks={"request": [validate_httpx_request_async]},
                follow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Ssak-Ai/1.0)"},
            )
        return self._client

    async def extract_text(self, url: str, max_chars: int = 5000) -> str:
        """URL에서 본문 텍스트를 추출합니다."""
        if not is_public_http_url(url):
            return "[차단됨: public HTTP URL만 허용]"
        client = await self._get_client()

        current_url = url
        for _ in range(4):
            resolved = await resolve_public_http_url(current_url)
            if resolved is None:
                return "[차단됨: public HTTP URL만 허용]"
            current_url, addresses = resolved
            if self._transport is not None:
                self._transport.pin(urlsplit(current_url).hostname or "", addresses[0])
            legal_decision = self._legal_policy.evaluate(current_url)
            if legal_decision.reason != "policy_attested":
                logger.info(
                    "[CrawlerPolicy] domain=%s allowed=%s reason=%s",
                    legal_decision.domain,
                    legal_decision.allowed,
                    legal_decision.reason,
                )
            if not legal_decision.allowed:
                return f"[차단됨: 이용약관 정책 {legal_decision.reason}]"
            if not await self._crawl_policy.authorize(current_url, client):
                return "[차단됨: robots.txt 정책 또는 rate limit]"
            try:
                async with client.stream("GET", current_url, follow_redirects=False) as resp:
                    if 300 <= resp.status_code < 400:
                        location = resp.headers.get("location", "")
                        if not location:
                            return f"[HTTP {resp.status_code}]"
                        current_url = urljoin(current_url, location)
                        continue
                    if resp.status_code != 200:
                        return f"[HTTP {resp.status_code}]"
                    text = await read_text_response_async(resp)
                    media_type = resp.headers.get("content-type", "").partition(";")[0].strip().casefold()
                    if media_type and media_type not in {"text/html", "application/xhtml+xml"}:
                        return text.strip()[: max(0, max_chars)]
                    return html_to_text(text, max_chars=max_chars)
            except ReaderRejected as exc:
                return f"[차단됨: 웹 본문 {exc}]"
            except (httpx.RequestError, UnicodeError) as e:
                return f"[스크래핑 오류: {e}]"
        return "[차단됨: redirect limit 초과]"

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = [
    "PageScraper",
    "WebSearchEngine",
    "_boost_by_trusted_domains",
    "html_to_text",
]
