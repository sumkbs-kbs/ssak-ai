"""Ssak-Ai: Multi-Engine 웹 서칭 엔진 (Web Search Tool)
==========================================================
Phase 23 리팩토링: 4개 모듈로 분할됨.
이 파일은 하위 호환성을 위한 re-export 모듈입니다.

분할된 모듈:
  - web_search_models.py: SearchResult, SearchResponse 데이터 모델
  - web_search_cache.py: SearchCache, 쿼리 분류/폴백 유틸리티
  - web_search_engine.py: WebSearchEngine (비동기), PageScraper
  - web_search_tool.py: WebSearchTool (동기식 execute) + sync 검색 메서드
"""

from __future__ import annotations

# ─── 모델 re-export ─────────────────────────────────────────────
from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

# ─── 캐시 re-export ─────────────────────────────────────────────
from .web_search_cache import (  # noqa: E501
    _CATEGORY_TTL_HOURS,
    _REALTIME_KEYWORDS,
    CACHE_DIR,
    SearchCache,
    _classify_query_category,
    _generate_fallback_queries,
)

# ─── 엔진 re-export ─────────────────────────────────────────────
from .web_search_engine import PageScraper, WebSearchEngine

# ─── 모델 re-export ─────────────────────────────────────────────
from .web_search_models import SearchResponse, SearchResult

# ─── 도구 re-export ─────────────────────────────────────────────
from .web_search_tool import WebSearchTool, _deduplicate_results

# ─── CLI 테스트 ──────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def main():
        engine = WebSearchEngine()
        result = await engine.search("Python 3.13 새로운 기능")
        print(engine.format_for_llm(result))
        print(f"\n사용 엔진: {result.engine}")
        await engine.close()

    asyncio.run(main())


__all__ = [
    # 모델
    "SearchResult",
    "SearchResponse",
    # 캐시
    "CACHE_DIR",
    "SearchCache",
    "_classify_query_category",
    "_generate_fallback_queries",
    "_REALTIME_KEYWORDS",
    "_CATEGORY_TTL_HOURS",
    # 엔진
    "WebSearchEngine",
    "PageScraper",
    # 도구
    "WebSearchTool",
    "_deduplicate_results",
    # BaseTool 호환
    "BaseTool",
    "RenderIn",
    "RiskLevel",
    "ToolCategory",
]
