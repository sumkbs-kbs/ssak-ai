"""웹 검색 도구 — 동기식 검색 + execute() 메서드.

WebSearchTool (BaseTool 래퍼), 동기식 검색 메서드들.
execute()의 큰 try 블록을 5개 private 메서드로 분해.
web_search.py에서 분리됨 (Phase 23 리팩토링).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Mapping
from typing import Callable, TypeAlias, cast, final, override
from urllib.parse import quote_plus

import httpx

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .egress_policy import validate_httpx_request
from .search_auth import SEARCH_TOKEN_ENV, search_auth_headers
from .ssak_search_provider import search_with_bundled_provider, settings_snapshot
from .web_search_cache import _generate_fallback_queries
from .web_search_engine import WebSearchEngine
from .web_search_html import parse_duckduckgo_results
from .web_search_models import SearchResult
from .web_search_quality import (
    canonicalize_url,
    has_authoritative_query_result,
    has_query_relevant_result,
    is_public_http_url,
    official_source_hints,
    rank_search_results,
    requires_authoritative_sources,
    sanitize_untrusted_text,
    source_id_for_url,
)

logger = logging.getLogger("web_search")

SearchResultTuple: TypeAlias = tuple[str, str, str]
SearchResults: TypeAlias = list[SearchResultTuple]


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {str(key): item for key, item in mapping.items()}


def _list_value(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text_value(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _number_value(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else default


@final
class WebSearchTool(BaseTool):
    """Multi-Engine 웹 검색 도구.

    무료 기술 조합: Jina Search + DuckDuckGo + Jina Reader + wttr.in
    """

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🔍"

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = ["search", "web", "jina", "duckduckgo", "multi-engine", "realtime"]
        self._name: str = "web_search"
        self._description: str = (
            "Performs a real-time web search using multiple search engines "
            "(SearxNG + Jina AI + DuckDuckGo) to find current information. Automatically "
            "extracts page content from top results for deep analysis."
        )
        self.searxng_url: str = os.environ.get("SEARXNG_URL", "http://localhost:8080")
        self.tavily_api_key: str | None = os.environ.get("TAVILY_API_KEY")
        self.max_results: int = 8
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. You MUST preserve the exact location names, "
                        "proper nouns, and keywords provided by the user without altering them."
                    ),
                },
                "depth": {
                    "type": "string",
                    "description": (
                        "Search depth. 'standard' for general search, "
                        "'deep' for comprehensive multi-page search. Default: 'standard'."
                    ),
                    "enum": ["standard", "deep"],
                },
            },
            "required": ["query"],
        }
        self.engine: WebSearchEngine = WebSearchEngine()
        # 어느 경로가 이 호출을 처리했는가(진단/시험용). legacy 면 위 `_run_bundled_provider` 가 채운다.
        self._last_route: str = "legacy (not evaluated)"

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        return self._schema

    # ════════════════════════════════════════════════════════════════
    # execute() — 메인 진입점 (분해된 메서드들로 구성)
    # ════════════════════════════════════════════════════════════════

    @override
    def execute(self, **kwargs: object) -> str:
        query_value = kwargs.get("query")
        if not isinstance(query_value, str) or not query_value:
            return "Error: Missing query"
        query = query_value

        depth = kwargs.get("depth", "standard")
        is_deep = depth == "deep"

        # 1. 종목코드 검증
        query = self._validate_stock_codes(query)

        # 2. 번들 provider 라우팅(opt-in, task 13) — 꺼져 있으면 None 이고 아래 기존 경로가 그대로 돈다.
        bundled = self._run_bundled_provider(query)
        if bundled is not None:
            return bundled

        try:
            # 2. Multi-Engine 검색
            all_results, engines_used = self._execute_multi_engine_search(query)

            official_results = official_source_hints(query)
            if official_results:
                all_results.extend(_to_result_tuples(official_results))
                engines_used.append("OfficialRegistry")

            candidate_results = _to_search_results(all_results)
            fallback_needed = not has_query_relevant_result(query, candidate_results)
            fallback_needed = fallback_needed or (
                requires_authoritative_sources(query) and not has_authoritative_query_result(query, candidate_results)
            )
            if fallback_needed:
                fallback_results, fallback_engines = self._execute_fallback(query)
                all_results.extend(fallback_results)
                engines_used.extend(fallback_engines)

            # 4. 중복 URL 제거
            results = _rank_results(query, all_results, self.max_results)

            # 5. Deep 모드: 추가 결과
            if is_deep:
                results = self._execute_deep_search(query, results)

            if not results:
                return f"[웹 검색] '{query}' — 결과 없음"

            # 6. 응답 포맷팅
            return self._format_search_response(query, results, engines_used)

        except (httpx.RequestError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.exception("Search pipeline error")
            return f"Search Error: {e}"

    # ─── 1-b. 번들 provider 라우팅 (opt-in) ──────────────────────

    def _run_bundled_provider(self, query: str) -> str | None:
        """opt-in 이면 번들 provider 로 **한 번** 가고, 그 결과를 최종 문자열로 돌려준다.

        반환값:
          - 문자열 → 이 호출은 여기서 끝난다(성공 또는 **결정적** 실패 — legacy 를 돌리지 않는다).
          - ``None`` → legacy 경로가 그대로 돈다(꺼져 있음, 또는 transient 실패로 ** 1회** 대체).

        대체를 None 으로 표현하는 이유: 호출자에게 한 번만 돌아가라는 뜻이고, 그 한 번이 곧
        "fallback 1회" 다. 결정적 실패(POLICY_DENIED/invalid/auth/설정 오류)에는 None 을 주지 않는다.
        """
        settings = settings_snapshot()
        if not settings.enabled:
            self._last_route = f"legacy ({settings.route_reason()})"
            return None
        if settings.problem or not settings.mode_supported:
            # 켰는데 설정이 잘못됐다 — 조용히 legacy 로 돌리면 그 결정이 사라진다(fail-closed).
            reason = settings.route_reason()
            self._last_route = f"blocked ({reason})"
            logger.error("번들 검색 설정이 올바르지 않습니다: %s", reason)
            return f"Search Error: {reason}"

        attempt = search_with_bundled_provider(query, max_results=self.max_results, settings=settings)
        if attempt.ok:
            self._last_route = f"bundled ({len(attempt.results)} hits)"
            if not attempt.results:
                return f"[웹 검색] '{query}' — 결과 없음"
            # legacy 와 **같은 포맷터**를 쓴다 — 경로가 바뀌어도 답변 계약은 하나다.
            return self._format_search_response(query, attempt.results, [attempt.engine])
        if attempt.transient and settings.fallback_on_transient:
            self._last_route = f"bundled→legacy (transient {attempt.error_code})"
            logger.warning(
                "번들 검색이 일시적으로 실패했습니다(%s) — legacy 로 1회 대체합니다: %s",
                attempt.error_code,
                attempt.message[:200],
            )
            return None
        self._last_route = f"bundled failed ({attempt.error_code})"
        logger.error(
            "번들 검색이 실패했고 대체하지 않습니다(%s): %s",
            attempt.error_code,
            attempt.message[:200],
        )
        return f"Search Error: {attempt.message[:400]}"

    # ─── 1. 종목코드 검증 ─────────────────────────────────────────

    def _validate_stock_codes(self, query: str) -> str:
        """종목코드 검증 및 쿼리 보강. 실패 시 원본 쿼리 반환."""
        try:
            from antigravity_k.engine.stock_code_validator import (
                enrich_search_query,
                validate_query_stock_codes,
            )

            stock_validation = validate_query_stock_codes(query)
            if stock_validation.needs_correction:
                original = query
                query = enrich_search_query(query, stock_validation)
                logger.info(
                    "종목코드 자동 교정: '%s' → '%s' (잘못된 코드: %s)",
                    original[:60],
                    query[:60],
                    [v.original_code for v in stock_validation.codes_found if v.needs_correction],
                )
        except Exception:
            logger.debug("종목코드 검증 실패 (non-critical)", exc_info=True)
        return query

    # ─── 2. Multi-Engine 검색 ─────────────────────────────────────

    def _execute_multi_engine_search(self, query: str) -> tuple[SearchResults, list[str]]:
        """4개 엔진을 순차적으로 호출하여 결과를 수집합니다."""
        all_results: SearchResults = []
        engines_used: list[str] = []

        # 0차: Self-Hosted Search Engine
        self_hosted_results = self._sync_search_self_hosted(query)
        if self_hosted_results:
            all_results.extend(self_hosted_results)
            engines_used.append("SelfHosted")

        # 1차: SearxNG
        if len(all_results) < self.max_results:
            searxng_results = self._sync_search_searxng(query)
            if searxng_results:
                all_results.extend(searxng_results)
                engines_used.append("SearxNG")

        # 2차: Jina Search
        if len(all_results) < self.max_results:
            jina_results = self._sync_search_jina(query)
            if jina_results:
                all_results.extend(jina_results)
                engines_used.append("Jina")

        # 3차: DuckDuckGo (최종 폴백)
        if len(all_results) < self.max_results:
            ddg_results = self._sync_search_duckduckgo(query)
            if ddg_results:
                all_results.extend(ddg_results)
                engines_used.append("DuckDuckGo")

        return all_results, engines_used

    # ─── 3. Fallback 검색 ─────────────────────────────────────────

    def _execute_fallback(self, query: str) -> tuple[SearchResults, list[str]]:
        fallback_queries = _generate_fallback_queries(query)
        logger.info(
            "검색 품질 보강용 fallback 쿼리 %d개 생성: %s",
            len(fallback_queries),
            fallback_queries[:3],
        )

        for fb_query in fallback_queries[1:4]:
            fb_results = self._sync_search_self_hosted(fb_query)
            if not has_query_relevant_result(fb_query, _to_search_results(fb_results)):
                fb_results.extend(self._sync_search_jina(fb_query))
            if not has_query_relevant_result(fb_query, _to_search_results(fb_results)):
                fb_results.extend(self._sync_search_searxng(fb_query))
            if not has_query_relevant_result(fb_query, _to_search_results(fb_results)):
                fb_results.extend(self._sync_search_duckduckgo(fb_query))
            if fb_results:
                logger.info("Fallback 성공: '%s' → %d개", fb_query[:40], len(fb_results))
                return fb_results, ["fallback"]
        return [], []

    # ─── 4. Deep 모드 검색 ────────────────────────────────────────

    def _execute_deep_search(self, query: str, results: SearchResults) -> SearchResults:
        """Deep 모드: Self-Hosted 추가 결과 요청."""
        logger.info("Deep 모드: 추가 결과 요청 (query=%s)", query[:40])
        extra_results = self._sync_search_self_hosted(query, deep=True)
        if extra_results:
            seen = {canonicalize_url(r[1]) for r in results}
            for r in extra_results:
                key = canonicalize_url(r[1])
                if key not in seen:
                    seen.add(key)
                    results.append((r[0], key, r[2]))
            logger.info("Deep 검색 추가 결과: %d개", len(extra_results))
        return results

    # ─── 5. 응답 포맷팅 ───────────────────────────────────────────

    def _format_search_response(
        self,
        query: str,
        results: SearchResults,
        engines_used: list[str],
    ) -> str:
        """검색 결과를 LLM 친화적 문자열로 포맷팅합니다.

        Args:
            query: 원본 검색 쿼리
            results: [(title, url, snippet), ...] 튜플 리스트
            engines_used: 사용된 엔진 이름 리스트

        Returns:
            포맷팅된 결과 문자열 (날씨 데이터, TOP 1 분석, 구조화 데이터 포함)
        """
        engine_label = "+".join(engines_used) if engines_used else "none"
        lines = [
            f"[웹 검색 결과] 쿼리: '{query}' ({engine_label}, {len(results)}개)",
            "",
        ]

        content = ""  # TOP 1 본문 저장용

        # ── 날씨 데이터 주입 ──
        self._inject_weather_data(query, lines)

        # ── TOP 1 심층 분석 ──
        if results:
            content = self._inject_top1_analysis(results[0], query, lines)

        # ── 나머지 결과 ──
        for i, (title, url, snippet) in enumerate(results[1:5], 2):
            citation = source_id_for_url(url)
            lines.append(
                f"{i}. [citation:{citation}] **{sanitize_untrusted_text(title, 240, wrap=False)}**\n"
                + f"   {sanitize_untrusted_text(snippet)}\n   🔗 {url}\n",
            )

        # ── 구조화 데이터 추출 ──
        self._inject_structured_data(results, content, lines, query=query)

        # ── 시스템 인스트럭션 ──
        lines.append(self._get_citation_instruction())

        return "\n".join(lines)

    def _inject_weather_data(self, query: str, lines: list[str]):
        """날씨 쿼리 시 wttr.in 직통 데이터 주입."""
        if "날씨" not in query:
            return

        loc_query = (
            query.replace("날씨", "")
            .replace("오늘", "")
            .replace("내일", "")
            .replace("모레", "")
            .replace("알려줘", "")
            .strip()
        )
        if not loc_query:
            loc_query = "Seoul"

        try:
            with httpx.Client(
                timeout=5.0,
                follow_redirects=True,
                event_hooks={"request": [validate_httpx_request]},
            ) as client:
                resp = client.get(f"https://wttr.in/{loc_query}?T&M")
                if resp.status_code == 200:
                    weather_ascii = re.sub(r"\x1b\[[0-9;]*m", "", resp.text)
                    lines.append(f"☁️ **[기상청/wttr.in 직통 데이터] 지역: {loc_query}**")
                    lines.append(f"```text\n{weather_ascii}\n```")
                    lines.append("")
        except httpx.RequestError:
            logger.warning("wttr.in 날씨 조회 실패 (non-critical)")

    def _inject_top1_analysis(self, top_result: SearchResultTuple, query: str, lines: list[str]) -> str:
        """TOP 1 결과의 본문을 분석하여 주입합니다."""
        top_title, top_url, top_snippet = top_result
        citation = source_id_for_url(top_url)
        lines.append(
            f"1. [citation:{citation}] **{sanitize_untrusted_text(top_title, 240, wrap=False)}**",
        )
        lines.append(f"🔗 {top_url}")

        if not is_public_http_url(top_url):
            lines.append("   (본문 스크래핑 차단: public HTTP URL이 아님)")
            lines.append(f"   {sanitize_untrusted_text(top_snippet)}")
            return ""

        # 1차: Jina Reader
        max_chars = 4000 if any(kw in query for kw in ("주가", "주식", "stock")) else 2000
        extract_content = cast(Callable[..., str], getattr(self.engine, "_extract_content_jina"))
        content = extract_content(top_url, max_chars=max_chars)
        if content:
            lines.append(f"   {sanitize_untrusted_text(content, max_chars=max_chars)}")
            return content

        lines.append("   (본문 스크래핑 실패: PageScraper-backed reader unavailable)")
        lines.append(f"   {sanitize_untrusted_text(top_snippet)}")

        lines.append("")
        return ""

    def _inject_structured_data(
        self,
        results: SearchResults,
        content: str,
        lines: list[str],
        query: str = "",
    ):
        """검색 결과에서 구조화 데이터를 추출하여 주입합니다."""
        try:
            from antigravity_k.engine.data_extractor import extract_structured_data

            all_texts = [snippet for (_, _, snippet) in results]
            if content:
                all_texts.append(content)

            structured = extract_structured_data(all_texts, query=query)
            if structured:
                lines.append("\n📊 **[구조화 데이터 추출]**:\n")
                lines.append(structured)
                lines.append(
                    "\n[중요] 위 구조화 데이터는 검색 결과에서 자동 추출된 값입니다. "
                    + "답변 시 반드시 이 값들을 우선적으로 사용하고, "
                    + "원본 검색 결과의 [N] 출처 번호도 함께 표기하세요.\n",
                )
        except Exception:
            logger.debug("데이터 추출 실패 (non-critical)", exc_info=True)

    @staticmethod
    def _get_citation_instruction() -> str:
        """Perplexity 스타일 인용 지시사항을 반환합니다."""
        return (
            "\n[SYSTEM INSTRUCTION: PERPLEXITY-STYLE SYNTHESIS & CITATION]\n"
            "위 검색 결과는 여러 출처에서 가져온 정보이며, "
            "특히 TOP 1 결과는 사이트 본문을 직접 읽어온 데이터입니다.\n"
            "1. **교차 검증 (Cross-validation)**: 반드시 여러 출처의 정보를 종합하여 "
            "모순이 없는지 확인하고, 단일 출처에만 의존하지 마세요.\n"
            "2. **인라인 인용구 (Inline Citations)**: 답변의 각 주장이나 팩트 끝에 "
            "해당 정보를 참조한 source id를 `[citation:<source_id>]` 형식으로 반드시 표기하세요.\n"
            "3. 날씨 정보 등 수치가 중요한 경우, 스니펫보다 "
            "**[TOP 1 심층 분석]** 본문의 구체적 수치를 우선적으로 신뢰하세요."
        )

    # ════════════════════════════════════════════════════════════════
    # 동기식 검색 메서드들
    # ════════════════════════════════════════════════════════════════

    def _sync_search_self_hosted(
        self,
        query: str,
        max_results: int | None = None,
        deep: bool = False,
    ) -> SearchResults:
        """자체 검색 엔진 (Cloudflare Pages 배포)을 통한 검색."""
        base_url = os.environ.get(
            "AGK_SEARCH_ENGINE_URL",
            "https://main.search-engine-api.pages.dev",
        ).rstrip("/")

        limit = max_results
        if limit is None:
            limit = self.max_results * 2 if deep else self.max_results

        timeout_sec = 20.0 if deep else 15.0
        snippet_max = 500 if deep else 300
        answer_label = "💡 AI Answer (Deep)" if deep else "💡 AI Answer"

        try:
            with httpx.Client(
                timeout=timeout_sec,
                follow_redirects=True,
                event_hooks={"request": [validate_httpx_request]},
            ) as client:
                resp = client.post(
                    f"{base_url}/api/search",
                    json={
                        "query": query,
                        "max_results": limit,
                        "include_answer": True,
                        "include_raw_content": deep,
                    },
                    # 같은 백엔드다 — 인증 헤더가 빠지면 기본 모드에서 항상 401이다.
                    headers={"Content-Type": "application/json", **search_auth_headers()},
                )
                if resp.status_code in (401, 403):
                    logger.warning(
                        "Self-hosted search 인증 실패(HTTP %s) — %s 를 설정하세요",
                        resp.status_code,
                        SEARCH_TOKEN_ENV,
                    )
                    return []
                if resp.status_code != 200:
                    return []

                data = _object_dict(cast(object, resp.json()))
                results: SearchResults = []

                answer = _object_dict(data.get("answer"))
                answer_text = _text_value(answer.get("text"))
                if answer_text:
                    results.append(
                        (
                            answer_label,
                            f"{base_url}/api/search?query={query}",
                            answer_text[: 1000 if deep else 500],
                        ),
                    )

                for item in _list_value(data.get("results"))[:limit]:
                    item_data = _object_dict(item)
                    title = _text_value(item_data.get("title"))
                    url = _text_value(item_data.get("url"))
                    snippet = _text_value(item_data.get("content"))[:snippet_max]

                    if deep:
                        raw = _text_value(item_data.get("raw_content"))
                        if raw:
                            snippet += f"\n[본문 발췌] {raw[:500]}"

                    stock = _object_dict(item_data.get("stock_data"))
                    if stock:
                        snippet = (
                            f"📊 {_text_value(stock.get('name'))} ({_text_value(stock.get('ticker'))}) "
                            f"{_number_value(stock.get('price')):,.0f}원 "
                            f"{_number_value(stock.get('change_percent')):+.2f}% "
                            f"({_text_value(stock.get('direction'))})\n{snippet}"
                        )

                    if title and url:
                        results.append((title, url, snippet))

                return results

        except httpx.RequestError:
            logger.warning("Self-hosted search 동기 오류", exc_info=True)
            return []

    def _sync_search_jina(self, query: str) -> SearchResults:
        """동기 Jina Search (s.jina.ai)."""
        try:
            headers = {"Accept": "application/json"}
            jina_key = os.environ.get("JINA_API_KEY")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"

            with httpx.Client(
                timeout=12.0,
                follow_redirects=True,
                event_hooks={"request": [validate_httpx_request]},
            ) as client:
                resp = client.get(
                    f"https://s.jina.ai/{quote_plus(query)}",
                    headers=headers,
                )
                if resp.status_code != 200:
                    return []

                raw_data = cast(object, resp.json())
                data = _object_dict(raw_data)
                items = (
                    _list_value(cast(object, raw_data)) if isinstance(raw_data, list) else _list_value(data.get("data"))
                )
                if not items:
                    items = _list_value(data.get("results"))

                results: SearchResults = []
                for item in items[:8]:
                    item_data = _object_dict(item)
                    title = _text_value(item_data.get("title"))
                    url = _text_value(item_data.get("url"))
                    snippet = _text_value(item_data.get("description"), _text_value(item_data.get("content")))[:300]
                    if title and url:
                        results.append((title, url, snippet))
                return results

        except (httpx.RequestError, json.JSONDecodeError, ConnectionError):
            logger.warning("Jina Search 동기 오류", exc_info=True)
            return []

    def _sync_search_searxng(self, query: str) -> SearchResults:
        """동기 SearxNG 메타 검색."""
        if not self.searxng_url:
            return []

        try:
            with httpx.Client(
                timeout=10.0,
                event_hooks={"request": [validate_httpx_request]},
            ) as client:
                resp = client.get(
                    f"{self.searxng_url}/search",
                    params={"q": query, "format": "json", "language": "ko-KR", "safesearch": 0},
                )
                if resp.status_code != 200:
                    return []

                data = _object_dict(cast(object, resp.json()))
                results: SearchResults = []
                for item in _list_value(data.get("results"))[: self.max_results]:
                    item_data = _object_dict(item)
                    title = _text_value(item_data.get("title"))
                    url = _text_value(item_data.get("url"))
                    snippet = _text_value(item_data.get("content"))
                    if title and url:
                        results.append((title, url, snippet))
                return results

        except httpx.RequestError:
            logger.debug("SearxNG 동기 검색 실패 (non-critical)")
            return []

    def _sync_search_duckduckgo(self, query: str) -> SearchResults:
        """동기 DuckDuckGo HTML 검색."""
        with httpx.Client(
            timeout=15.0,
            event_hooks={"request": [validate_httpx_request]},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            follow_redirects=True,
        ) as client:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp: httpx.Response | None = None
            for attempt in range(3):
                resp = client.get(url, timeout=5.0)
                if resp.status_code != 202 or attempt == 2:
                    break
                time.sleep(0.25 * (attempt + 1))
            if resp is None:
                return []
            if resp.status_code != 200:
                return []

            return [
                (result.title, result.url, result.snippet[:300]) for result in parse_duckduckgo_results(resp.text, 8)
            ]


# ─── 유틸리티 함수 ──────────────────────────────────────────────


def _deduplicate_results(results: SearchResults) -> SearchResults:
    """중복 URL을 제거합니다 (먼저 들어온 결과 우선).

    Args:
        results: [(title, url, snippet), ...] 튜플 리스트

    Returns:
        중복 제거된 리스트
    """
    best_by_url: dict[str, SearchResultTuple] = {}
    for r in results:
        key = canonicalize_url(r[1])
        if not key:
            continue
        candidate = (r[0], key, r[2])
        current = best_by_url.get(key)
        if current is None or len(candidate[2]) > len(current[2]):
            best_by_url[key] = candidate
    return list(best_by_url.values())


def _to_search_results(results: SearchResults) -> list[SearchResult]:
    return [SearchResult(title=title, url=url, snippet=snippet, relevance_score=1.0) for title, url, snippet in results]


def _to_result_tuples(results: list[SearchResult]) -> SearchResults:
    return [(result.title, result.url, result.snippet) for result in results]


def _rank_results(query: str, results: SearchResults, max_results: int) -> SearchResults:
    ranked = rank_search_results(_to_search_results(results), max_results=max_results, query=query)
    return _to_result_tuples(ranked)


__all__ = [
    "WebSearchTool",
    "_deduplicate_results",
]
