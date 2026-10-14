"""웹 검색 데이터 모델.

SearchResult, SearchResponse 데이터클래스 정의.
web_search.py에서 분리됨 (Phase 23 리팩토링).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """단일 검색 결과."""

    title: str
    url: str
    snippet: str
    source: str = ""  # 검색 엔진 이름
    timestamp: str = ""  # 검색 시각
    relevance_score: float = 0.0
    canonical_url: str = ""
    source_id: str = ""
    domain: str = ""
    authority_score: float = 0.0
    ranking_score: float = 0.0


@dataclass
class SearchResponse:
    """검색 응답 전체."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    total_results: int = 0
    search_time_ms: float = 0.0
    engine: str = "searxng"
    cached: bool = False
    stale: bool = False


__all__ = [
    "SearchResponse",
    "SearchResult",
]
