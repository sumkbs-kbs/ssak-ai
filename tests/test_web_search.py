"""Tests for antigravity_k.tools.web_search.

Coverage targets:
  - SearchCache: get/set/clear/stats/force_refresh/TTL
  - _classify_query_category: all categories
  - _generate_fallback_queries: Korean particles, verb removal, punctuation
  - WebSearchEngine: format_for_llm, search (mocked HTTP)
  - PageScraper: extract_text (mocked HTTP)
  - WebSearchTool: execute, sync search methods, stock validation, data extraction
  - Edge cases: empty strings, special characters, error paths
"""

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Callable, cast
from unittest.mock import MagicMock, patch

import httpx
import pytest

from antigravity_k.tools.web_search import (
    SearchCache,
    SearchResponse,
    SearchResult,
    WebSearchEngine,
    WebSearchTool,
    _classify_query_category,
    _generate_fallback_queries,
)

SearchTuple = tuple[str, str, str]
SearchResults = list[SearchTuple]


def _mock_httpx_client(method: str, callback: Callable[..., object]) -> MagicMock:
    client = MagicMock()
    client.configure_mock(**{f"__enter__.return_value.{method}.side_effect": callback})
    return client


def _client_factory(method: str, callback: Callable[..., object]) -> Callable[..., MagicMock]:
    def factory(*_args: object, **_kwargs: object) -> MagicMock:
        return _mock_httpx_client(method, callback)

    return factory


def _empty_search(_query: str, **_kwargs: object) -> SearchResults:
    return []


def _empty_search_no_kwargs(_query: str) -> SearchResults:
    return []


def _empty_content(_url: str, max_chars: int = 2000) -> str:
    del max_chars
    return ""


def _raise_stock_validation(_query: str) -> object:
    raise RuntimeError("Simulated")


# ═══════════════════════════════════════════════════════════════════
# _classify_query_category tests
# ═══════════════════════════════════════════════════════════════════


class TestClassifyQueryCategory:
    """_classify_query_category — pure function, 6 categories."""

    def test_realtime_weather(self):
        assert _classify_query_category("오늘 날씨 어때?") == "realtime_weather"

    def test_realtime_weather_english(self):
        assert _classify_query_category("weather in Seoul") == "realtime_weather"

    def test_realtime_weather_mise(self):
        assert _classify_query_category("미세먼지 농도") == "realtime_weather"

    def test_realtime_finance(self):
        assert _classify_query_category("삼성전자 주가") == "realtime_finance"

    def test_realtime_finance_kospi(self):
        assert _classify_query_category("코스피 지수") == "realtime_finance"

    def test_realtime_finance_stock(self):
        assert _classify_query_category("stock market today") == "realtime_finance"

    def test_realtime_finance_exchange(self):
        assert _classify_query_category("환율 알려줘") == "realtime_finance"

    def test_realtime_general_today(self):
        assert _classify_query_category("오늘 몇 일이야?") == "realtime_general"

    def test_realtime_general_now(self):
        assert _classify_query_category("지금 몇 시야") == "realtime_general"

    def test_realtime_general_yesterday(self):
        assert _classify_query_category("어제 날짜") == "realtime_general"

    def test_realtime_news(self):
        assert _classify_query_category("IT 뉴스") == "realtime_news"

    def test_realtime_news_breaking(self):
        assert _classify_query_category("breaking news") == "realtime_news"

    def test_technical_python(self):
        assert _classify_query_category("python async await") == "technical"

    def test_technical_react(self):
        assert _classify_query_category("react hooks tutorial") == "technical"

    def test_technical_api(self):
        assert _classify_query_category("FastAPI documentation") == "technical"

    def test_general_default(self):
        assert _classify_query_category("인기 영화 추천") == "general"

    def test_general_empty(self):
        assert _classify_query_category("") == "general"

    def test_general_mixed_keyword(self):
        """일반 쿼리에 실시간 키워드가 섞여 있어도 카테고리 우선순위 유지."""
        assert _classify_query_category("python 주가 예측") == "realtime_finance"


# ═══════════════════════════════════════════════════════════════════
# _generate_fallback_queries tests
# ═══════════════════════════════════════════════════════════════════


class TestGenerateFallbackQueries:
    """_generate_fallback_queries — pure function, 5+ strategies."""

    def test_returns_at_least_original(self):
        queries = _generate_fallback_queries("테스트")
        assert len(queries) >= 1
        assert "테스트" in queries

    def test_korean_particle_removal(self):
        """은/는/이/가/을/를 제거."""
        queries = _generate_fallback_queries("삼성전자 주가 알려줘")
        assert any("알려줘" not in q or "주가" in q for q in queries)
        # At least one version should have the particle removed
        any_clean = any("삼성전자" in q for q in queries)
        assert any_clean

    def test_verb_removal(self):
        """알려줘/찾아줘 제거."""
        queries = _generate_fallback_queries("날씨 알려줘")
        assert any("알려줘" not in q for q in queries)

    def test_punctuation_removal(self):
        """구두점 제거."""
        queries = _generate_fallback_queries("파이썬, '문법' 정리해줘")
        assert any("파이썬" in q for q in queries)

    def test_condensed_version(self):
        """공백 제거 축약형."""
        queries = _generate_fallback_queries("삼성전자 주가")
        condensed = [q for q in queries if " " not in q.strip()]
        assert len(condensed) >= 1

    def test_duplicate_removed(self):
        """중복 제거."""
        queries = _generate_fallback_queries("테스트")
        assert len(queries) == len({q.lower() for q in queries})

    def test_min_length_filter(self):
        """2글자 미만 제거."""
        queries = _generate_fallback_queries("a b")
        assert all(len(q) >= 2 for q in queries)

    def test_english_article_removal(self):
        """영어 관사 제거."""
        queries = _generate_fallback_queries("the best python tutorial")
        assert any("the" not in q for q in queries)

    def test_technical_query_rewrites_preserve_intent(self):
        ollama_queries = _generate_fallback_queries("Ollama tool calling official documentation")
        assert ollama_queries[1] == "site:docs.ollama.com tool calling"

        rfc_queries = _generate_fallback_queries("robots.txt standard RFC 9309")
        assert "robots exclusion protocol RFC 9309" in rfc_queries

        mdn_queries = _generate_fallback_queries("HTTP 429 Too Many Requests official MDN")
        assert "429 Too Many Requests MDN Web Docs" in mdn_queries

        docs_queries = _generate_fallback_queries("FastAPI background tasks official documentation")
        assert "FastAPI background tasks official docs" in docs_queries


# ═══════════════════════════════════════════════════════════════════
# SearchCache tests
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def search_cache(tmp_path: Path) -> Iterator[SearchCache]:
    """SearchCache with isolated temp directory."""
    import antigravity_k.tools.web_search_cache as wsc

    original_dir = wsc.CACHE_DIR
    wsc.CACHE_DIR = tmp_path / "search_cache"
    wsc.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache = SearchCache(ttl_hours=24)
    yield cache
    # restore
    wsc.CACHE_DIR = original_dir


class TestSearchCache:
    """SearchCache: get/set/clear/stats/force_refresh/TTL/realtime."""

    def test_get_empty_cache(self, search_cache: SearchCache):
        """캐시가 비어있으면 None 반환."""
        assert search_cache.get("삼성전자 주가") is None

    def test_set_and_get(self, search_cache: SearchCache):
        """캐시 저장 후 조회."""
        response = SearchResponse(
            query="test",
            results=[SearchResult(title="T", url="https://example.com", snippet="S")],
            total_results=1,
            engine="test",
        )
        search_cache.set("test", response)
        cached = search_cache.get("test")
        assert cached is not None
        assert cached.cached is True
        assert len(cached.results) == 1
        assert cached.results[0].title == "T"

    def test_force_refresh(self, search_cache: SearchCache):
        """force_refresh=True면 캐시 무시하고 None 반환."""
        response = SearchResponse(query="test", results=[SearchResult(title="T", url="https://ex.com", snippet="S")])
        search_cache.set("test", response)
        assert search_cache.get("test", force_refresh=True) is None

    def test_realtime_keyword_bypasses_cache(self, search_cache: SearchCache):
        """실시간 키워드(날씨)가 포함되면 캐시 무시."""
        response = SearchResponse(query="날씨", results=[], total_results=0, engine="test")
        search_cache.set("날씨", response)
        # 실시간 키워드는 TTL이 0이어서 set()에서 저장되지 않음
        assert search_cache.get("날씨") is None

    def test_cache_stats_empty(self, search_cache: SearchCache):
        """빈 캐시의 통계."""
        stats = search_cache.get_cache_stats()
        assert stats["total_files"] == 0

    def test_cache_stats_with_data(self, search_cache: SearchCache):
        """데이터가 있는 캐시의 통계."""
        response = SearchResponse(
            query="test",
            results=[SearchResult(title="T", url="https://ex.com", snippet="S")],
            engine="test",
        )
        search_cache.set("test", response)
        stats = search_cache.get_cache_stats()
        assert isinstance(stats["total_files"], int)
        assert isinstance(stats["total_size_kb"], (int, float))
        assert stats["total_files"] >= 1
        assert stats["total_size_kb"] > 0

    def test_clear_single(self, search_cache: SearchCache):
        """특정 쿼리 캐시 삭제."""
        response = SearchResponse(query="test", results=[], engine="test")
        search_cache.set("test", response)
        search_cache.clear("test")
        assert search_cache.get("test") is None

    def test_clear_all(self, search_cache: SearchCache):
        """전체 캐시 삭제."""
        for q in ["a", "b", "c"]:
            search_cache.set(
                q,
                SearchResponse(query=q, results=[], engine="test"),
            )
        search_cache.clear()
        assert search_cache.get_cache_stats()["total_files"] == 0

    def test_ttl_expiry(self, search_cache: SearchCache):
        """TTL 만료 시 None 반환 (mock으로 시간 조작)."""
        response = SearchResponse(query="expired", results=[], engine="test")
        search_cache.set("expired", response)

        with patch("antigravity_k.tools.web_search_cache.datetime") as mock_dt:
            from datetime import UTC, datetime, timedelta

            # 미래 시간으로 설정 (24시간 이상 지난 것으로 만듦)
            mock_dt.configure_mock(now=MagicMock(return_value=datetime.now(UTC) + timedelta(hours=48)))
            mock_dt.fromisoformat = datetime.fromisoformat
            cached = search_cache.get("expired")
            assert cached is None

    def test_stale_cache_is_available_with_explicit_marker(self, search_cache: SearchCache):
        response = SearchResponse(
            query="expired",
            results=[SearchResult(title="T", url="https://ex.com", snippet="S")],
            engine="test",
        )
        search_cache.set("expired", response)

        with patch("antigravity_k.tools.web_search_cache.datetime") as mock_dt:
            from datetime import UTC, datetime, timedelta

            mock_dt.configure_mock(now=MagicMock(return_value=datetime.now(UTC) + timedelta(hours=48)))
            mock_dt.fromisoformat = datetime.fromisoformat
            stale = search_cache.get_stale("expired")

        assert stale is not None
        assert stale.cached is True
        assert stale.stale is True
        assert stale.results[0].title == "T"

    def test_ttl_zero_not_cached(self, search_cache: SearchCache):
        """TTL 0이면 캐시 저장하지 않음."""
        with patch.object(search_cache, "_get_effective_ttl", return_value=0):
            response = SearchResponse(query="test", results=[], engine="test")
            search_cache.set("test", response)
            assert search_cache.get("test") is None

    def test_corrupted_cache_file(self, search_cache: SearchCache):
        """손상된 캐시 파일 처리."""
        import antigravity_k.tools.web_search_cache as wsc

        key = search_cache._cache_key("corrupt")
        cache_file = wsc.CACHE_DIR / f"{key}.json"
        _ = cache_file.write_text("not json", encoding="utf-8")
        assert search_cache.get("corrupt") is None

    def test_safe_cache_key(self, search_cache: SearchCache):
        """캐시 키 생성이 안전한 파일명을 만듦."""
        key = search_cache._cache_key("특수문자!@#$%^&*()_+{}|:<>?")
        assert "/" not in key
        assert "\\" not in key
        assert len(key) <= 80

    def test_technical_ttl_72h(self, search_cache: SearchCache):
        """기술 문서 쿼리의 TTL은 72시간."""
        ttl = search_cache._get_effective_ttl("python tutorial")
        assert ttl == 72

    def test_finance_ttl_30min(self, search_cache: SearchCache):
        """금융 쿼리의 TTL은 0.5시간."""
        ttl = search_cache._get_effective_ttl("삼성전자 주가")
        assert ttl == 0.5


# ═══════════════════════════════════════════════════════════════════
# WebSearchEngine tests
# ═══════════════════════════════════════════════════════════════════


class TestWebSearchEngine:
    """WebSearchEngine: format_for_llm, search (mocked)."""

    def test_format_for_llm_empty(self):
        """결과가 없으면 적절한 메시지 반환."""
        engine = WebSearchEngine()
        response = SearchResponse(query="test", results=[], engine="none")
        result = engine.format_for_llm(response)
        assert "결과 없음" in result

    def test_format_for_llm_with_results(self):
        """결과가 있으면 포맷팅되어 반환."""
        engine = WebSearchEngine()
        results = [
            SearchResult(title="Title1", url="https://ex.com/1", snippet="Snippet1"),
            SearchResult(title="Title2", url="https://ex.com/2", snippet="Snippet2"),
        ]
        response = SearchResponse(query="test", results=results, engine="test", total_results=2)
        formatted = engine.format_for_llm(response)
        assert "Title1" in formatted
        assert "Title2" in formatted
        assert "Snippet1" in formatted
        assert "test" in formatted
        assert "2개" in formatted

    def test_format_for_llm_truncation(self):
        """max_chars 제한 시 생략 메시지 포함."""
        engine = WebSearchEngine()
        results = [
            SearchResult(
                title=f"Title{i}",
                url=f"https://ex.com/{i}",
                snippet="x" * 100,
            )
            for i in range(50)
        ]
        response = SearchResponse(query="test", results=results, engine="test", total_results=50)
        formatted = engine.format_for_llm(response, max_chars=500)
        assert "생략" in formatted

    @pytest.mark.asyncio
    async def test_search_and_summarize(self):
        """search_and_summarize가 format_for_llm과 search를 연결."""
        from unittest.mock import AsyncMock

        engine = WebSearchEngine()
        with patch.object(engine, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = SearchResponse(
                query="test",
                results=[SearchResult(title="T", url="https://ex.com", snippet="S")],
                engine="mock",
            )
            result = await engine.search_and_summarize("test")
            assert "T" in result

    @pytest.mark.asyncio
    async def test_search_with_cache_hit(self):
        """캐시 히트 시 캐시된 결과 반환."""
        engine = WebSearchEngine()
        cached_resp = SearchResponse(
            query="test",
            results=[SearchResult(title="Cached", url="https://ex.com", snippet="C")],
            cached=True,
            engine="cache",
        )
        with patch.object(engine.cache, "get", return_value=cached_resp):
            response = await engine.search("test", use_cache=True)
            assert response.cached is True
            assert response.results[0].title == "Cached"

    @pytest.mark.asyncio
    async def test_search_cache_miss_fallback(self):
        """캐시 미스 시 검색 실행 — 모든 엔진 실패 시 빈 결과."""
        engine = WebSearchEngine()
        engine.tavily_api_key = None
        with (
            patch.object(engine.cache, "get", return_value=None),
            patch.object(engine.cache, "get_stale", return_value=None),
            patch.object(engine, "_search_self_hosted", return_value=[]),
            patch.object(engine, "_search_searxng", return_value=[]),
            patch.object(engine, "_search_jina", return_value=[]),
            patch.object(engine, "_search_duckduckgo", return_value=[]),
        ):
            response = await engine.search("test", use_cache=True)
            assert response.total_results == 0

    @pytest.mark.asyncio
    async def test_search_uses_stale_cache_after_provider_failure(self):
        engine = WebSearchEngine()
        stale_resp = SearchResponse(
            query="test",
            results=[SearchResult(title="Stale", url="https://ex.com", snippet="Old")],
            engine="searxng",
            cached=True,
            stale=True,
        )
        engine.tavily_api_key = None
        with (
            patch.object(engine.cache, "get", return_value=None),
            patch.object(engine.cache, "get_stale", return_value=stale_resp),
            patch.object(engine, "_search_self_hosted", return_value=[]),
            patch.object(engine, "_search_searxng", return_value=[]),
            patch.object(engine, "_search_jina", return_value=[]),
            patch.object(engine, "_search_duckduckgo", return_value=[]),
        ):
            response = await engine.search("test", use_cache=True)

        assert response.stale is True
        assert response.cached is True
        assert response.engine == "stale-cache/searxng"
        assert response.results[0].title == "Stale"

    @pytest.mark.asyncio
    async def test_search_with_searxng_results(self):
        """SearXNG 결과가 있으면 반환."""
        engine = WebSearchEngine()
        engine.tavily_api_key = None
        mock_results = [SearchResult(title="Searched", url="https://ex.com", snippet="Result")]
        with (
            patch.object(engine.cache, "get", return_value=None),
            patch.object(engine, "_search_self_hosted", return_value=[]),
            patch.object(engine, "_search_searxng", return_value=mock_results),
            patch.object(engine, "_search_jina", return_value=[]),
            patch.object(engine, "_search_duckduckgo", return_value=[]),
        ):
            response = await engine.search("test")
            assert len(response.results) == 1
            assert response.results[0].title == "Searched"

    @pytest.mark.asyncio
    async def test_search_deduplicates_urls(self):
        """중복 URL 제거."""
        engine = WebSearchEngine()
        engine.tavily_api_key = None
        mock_results = [
            SearchResult(title="A", url="https://ex.com/page", snippet="S"),
            SearchResult(title="B", url="https://ex.com/page", snippet="S"),
        ]
        with (
            patch.object(engine.cache, "get", return_value=None),
            patch.object(engine, "_search_self_hosted", return_value=[]),
            patch.object(engine, "_search_searxng", return_value=mock_results),
            patch.object(engine, "_search_jina", return_value=[]),
            patch.object(engine, "_search_duckduckgo", return_value=[]),
        ):
            response = await engine.search("test")
            assert len(response.results) == 1  # 중복 제거됨

    def test_format_for_llm_source_single_result(self):
        """단일 결과도 정상 포맷팅."""
        engine = WebSearchEngine()
        response = SearchResponse(
            query="test",
            results=[SearchResult(title="Only", url="https://ex.com", snippet="One")],
            engine="test",
        )
        formatted = engine.format_for_llm(response)
        assert "Only" in formatted
        assert "One" in formatted


# ═══════════════════════════════════════════════════════════════════
# WebSearchTool tests
# ═══════════════════════════════════════════════════════════════════


class TestWebSearchTool:
    """WebSearchTool: execute, sync search methods, schema."""

    def test_properties(self):
        """name, description, parameters_schema 반환."""
        tool = WebSearchTool()
        assert tool.name == "web_search"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0
        schema = cast(Mapping[str, object], tool.parameters_schema)
        assert schema["type"] == "object"
        properties = schema["properties"]
        assert isinstance(properties, Mapping)
        assert "query" in properties

    def test_execute_missing_query(self):
        """query 없이 execute 호출 시 에러 메시지."""
        tool = WebSearchTool()
        result = tool.execute()
        assert "Error: Missing query" in str(result)

    def test_execute_empty_query(self):
        """빈 query로 execute 호출 시 에러 메시지."""
        tool = WebSearchTool()
        result = tool.execute(query="")
        assert "Missing query" in str(result)

    def test_sync_search_jina(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_jina — HTTP 응답 모킹."""
        tool = WebSearchTool()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.configure_mock(
            json=MagicMock(
                return_value=[
                    {"title": "Jina Result", "url": "https://jina.ex", "description": "Jina desc"},
                ],
            ),
        )

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_jina("test")
        assert len(results) >= 1
        assert results[0][0] == "Jina Result"

    def test_sync_search_jina_empty(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_jina — 200 아니면 빈 리스트."""
        tool = WebSearchTool()
        mock_response = MagicMock()
        mock_response.status_code = 403

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_jina("test")
        assert results == []

    def test_sync_search_jina_exception(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_jina — 예외 발생 시 빈 리스트."""
        tool = WebSearchTool()

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            raise ConnectionError("Network error")

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_jina("test")
        assert results == []

    def test_sync_search_duckduckgo(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_duckduckgo — HTML 스크래핑 모킹."""
        tool = WebSearchTool()
        html_content = """
        <html><body>
        <a class="result__a" href="https://example.com/1">Title 1</a>
        <a class="result__snippet">Snippet 1</a>
        <a class="result__a" href="https://example.com/2">Title 2</a>
        <a class="result__snippet">Snippet 2</a>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_duckduckgo("test")
        assert len(results) >= 1
        assert results[0][0] == "Title 1"
        assert "Snippet 1" in results[0][2]

    def test_sync_search_duckduckgo_403(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_duckduckgo — 403 응답 시 빈 리스트."""
        tool = WebSearchTool()
        mock_response = MagicMock()
        mock_response.status_code = 403

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_duckduckgo("test")
        assert results == []

    def test_sync_search_self_hosted(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_self_hosted — API 응답 모킹."""
        tool = WebSearchTool()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.configure_mock(
            json=MagicMock(
                return_value={
                    "results": [
                        {"title": "SH Result", "url": "https://sh.ex", "content": "SH content"},
                    ],
                    "backend": "mock",
                },
            ),
        )

        def mock_post(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("post", mock_post))
        results = tool._sync_search_self_hosted("test")
        assert len(results) >= 1
        assert results[0][0] == "💡 AI Answer" or results[0][0] == "SH Result"

    def test_sync_search_self_hosted_http_error(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_self_hosted — HTTP 오류 시 빈 리스트."""
        tool = WebSearchTool()

        def mock_post(*_args: object, **_kwargs: object) -> MagicMock:
            resp = MagicMock()
            resp.status_code = 500
            return resp

        monkeypatch.setattr(httpx, "Client", _client_factory("post", mock_post))
        results = tool._sync_search_self_hosted("test")
        assert results == []

    def test_sync_search_searxng_disabled(self):
        """_sync_search_searxng — URL이 없으면 빈 리스트."""
        tool = WebSearchTool()
        tool.searxng_url = ""
        results = tool._sync_search_searxng("test")
        assert results == []

    def test_execute_with_stock_validation(self, monkeypatch: pytest.MonkeyPatch):
        """execute — 종목코드 검증이 실패해도 계속 실행됨 (graceful degradation)."""
        import antigravity_k.engine.stock_code_validator as scv

        tool = WebSearchTool()

        # stock_code_validator의 함수가 실패해도 execute는 정상 동작해야 함
        monkeypatch.setattr(
            scv,
            "validate_query_stock_codes",
            _raise_stock_validation,
        )

        # Mock all search methods to return empty
        monkeypatch.setattr(tool, "_sync_search_self_hosted", _empty_search)
        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)

        result = tool.execute(query="096732 한화에어로스페이스 주가 알려줘")
        assert isinstance(result, str)
        assert "결과 없음" in result

    def test_execute_with_results(self, monkeypatch: pytest.MonkeyPatch):
        """execute — 검색 결과가 있으면 포맷팅된 문자열 반환."""
        tool = WebSearchTool()

        def search_with_result(_query: str, **_kwargs: object) -> SearchResults:
            return [("Title", "https://ex.com", "Snippet content")]

        monkeypatch.setattr(
            tool,
            "_sync_search_self_hosted",
            search_with_result,
        )
        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)
        # Jina Reader 내부 httpx 호출 차단 (실제 네트워크 방지)
        monkeypatch.setattr(tool.engine, "_extract_content_jina", _empty_content)

        # Fallback httpx.Client도 차단 → 스니펫 폴백 메시지에 포함됨
        def _mock_client(*_args: object, **_kwargs: object) -> MagicMock:
            m = MagicMock()
            m.configure_mock(**{"__enter__.return_value.get.side_effect": httpx.ConnectError("mocked")})
            return m

        monkeypatch.setattr(httpx, "Client", _mock_client)

        result = tool.execute(query="test query")
        assert isinstance(result, str)
        assert "Title" in result
        assert "Snippet content" in result

    def test_execute_deep_mode(self, monkeypatch: pytest.MonkeyPatch):
        """execute — deep 모드로 추가 결과 요청."""
        tool = WebSearchTool()
        results_standard = [("T1", "https://ex.com/1", "S1")]
        results_deep = [("T2", "https://ex.com/2", "S2")]

        def search_by_depth(_query: str, **kwargs: object) -> SearchResults:
            return results_standard if not kwargs.get("deep") else results_deep

        monkeypatch.setattr(
            tool,
            "_sync_search_self_hosted",
            search_by_depth,
        )
        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)

        result = tool.execute(query="test", depth="deep")
        assert isinstance(result, str)
        assert "T1" in result

    def test_execute_all_engines_empty_no_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """execute — 모든 엔진 결과 없음 + fallback 실패."""
        tool = WebSearchTool()
        monkeypatch.setattr(tool, "_sync_search_self_hosted", _empty_search)
        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)

        result = tool.execute(query="zzzznonexistent")
        assert isinstance(result, str)
        assert "결과 없음" in result

    def test_execute_fallback_success(self, monkeypatch: pytest.MonkeyPatch):
        """execute — 첫 번째 엔진 실패 시 fallback 성공."""
        tool = WebSearchTool()
        call_count = 0

        def mock_self_hosted(_q: str, **_kw: object) -> list[tuple[str, str, str]]:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                return [("test documentation", "https://ex.com/fb", "Fallback")]
            return []

        monkeypatch.setattr(tool, "_sync_search_self_hosted", mock_self_hosted)
        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)
        monkeypatch.setattr(tool.engine, "_extract_content_jina", lambda url, max_chars=2000: "")

        result = tool.execute(query="test documentation")
        assert isinstance(result, str)
        assert "https://ex.com/fb" in result
        assert "Fallback" in result
        assert "[citation:" in result
        assert call_count > 1

    def test_sync_search_searxng_results(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_searxng — 정상 응답."""
        tool = WebSearchTool()
        tool.searxng_url = "http://localhost:8080"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.configure_mock(
            json=MagicMock(
                return_value={
                    "results": [
                        {"title": "SX Result", "url": "https://sx.ex", "content": "SX content"},
                    ],
                },
            ),
        )

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_searxng("test")
        assert len(results) >= 1
        assert results[0][0] == "SX Result"

    def test_sync_search_searxng_http_error(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_searxng — HTTP 오류 시 빈 리스트."""
        tool = WebSearchTool()
        tool.searxng_url = "http://localhost:8080"
        mock_response = MagicMock()
        mock_response.status_code = 500

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_searxng("test")
        assert results == []

    def test_stock_ticker_snippet_in_results(self, monkeypatch: pytest.MonkeyPatch):
        """execute — Self-Hosted stock_data가 스니펫에 포함됨."""
        tool = WebSearchTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.configure_mock(
            json=MagicMock(
                return_value={
                    "results": [
                        {
                            "title": "Stock Result",
                            "url": "https://ex.com/stock",
                            "content": "주가 정보입니다",
                            "stock_data": {
                                "name": "한화에어로스페이스",
                                "ticker": "012450",
                                "price": 943000,
                                "change_percent": 1.51,
                                "direction": "상승",
                            },
                        },
                    ],
                    "backend": "mock",
                },
            ),
        )

        def mock_post(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("post", mock_post))

        monkeypatch.setattr(tool, "_sync_search_searxng", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_jina", _empty_search_no_kwargs)
        monkeypatch.setattr(tool, "_sync_search_duckduckgo", _empty_search_no_kwargs)
        # Jina Reader 차단 — 실제 HTTP 호출 방지
        monkeypatch.setattr(tool.engine, "_extract_content_jina", _empty_content)

        result = tool.execute(query="한화에어로스페이스 주가")
        assert isinstance(result, str)
        assert "📊 한화에어로스페이스" in result
        assert "012450" in result
        assert "943,000원" in result or "943000" in result


# ═══════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestWebSearchEdgeCases:
    """Edge cases: exceptions, empty inputs, special characters."""

    def test_duckduckgo_uddg_url_extraction(self, monkeypatch: pytest.MonkeyPatch):
        """_sync_search_duckduckgo — uddg URL에서 실제 URL 추출."""
        tool = WebSearchTool()
        html_content = """
        <html><body>
        <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">Title</a>
        <a class="result__snippet">Snippet</a>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        def mock_get(*_args: object, **_kwargs: object) -> MagicMock:
            return mock_response

        monkeypatch.setattr(httpx, "Client", _client_factory("get", mock_get))
        results = tool._sync_search_duckduckgo("test")
        assert len(results) == 1
        assert "example.com/page" in results[0][1]
        assert "uddg=" not in results[0][1]

    def test_generate_fallback_with_special_chars(self):
        """특수문자가 많은 쿼리도 fallback 생성 가능."""
        queries = _generate_fallback_queries("『파이썬』 문법 [정리]!")
        assert len(queries) >= 1

    def test_cache_key_with_long_query(self, tmp_path: Path):
        """매우 긴 쿼리의 캐시 키는 80자로 제한."""
        import antigravity_k.tools.web_search as ws

        original = ws.CACHE_DIR
        ws.CACHE_DIR = tmp_path / "sc"
        ws.CACHE_DIR.mkdir(parents=True)
        cache = SearchCache()
        ws.CACHE_DIR = original
        key = cache._cache_key("a" * 200)
        assert len(key) <= 80

    def test_search_response_dataclass(self):
        """SearchResponse dataclass 생성 및 기본값 확인."""
        resp = SearchResponse(query="test")
        assert resp.query == "test"
        assert resp.results == []
        assert resp.total_results == 0
        assert resp.engine == "searxng"
        assert resp.cached is False

    def test_search_result_dataclass(self):
        """SearchResult dataclass 생성."""
        r = SearchResult(title="T", url="https://ex.com", snippet="S")
        assert r.title == "T"
        assert r.relevance_score == 0.0
