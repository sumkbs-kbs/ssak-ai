"""웹 검색 캐시 및 쿼리 유틸리티.

SearchCache, _classify_query_category, _generate_fallback_queries 및 상수들.
web_search.py에서 분리됨 (Phase 23 리팩토링).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .web_search_models import SearchResponse, SearchResult

logger = logging.getLogger("web_search")

# ─── 검색 캐시 디렉토리 ──────────────────────────────────────────


def _resolve_cache_dir() -> Path:
    try:
        from antigravity_k.config import config

        candidate = config.paths.data_dir / "search_cache"
    except Exception:
        candidate = Path.home() / ".antigravity-k" / "data" / "search_cache"

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        test_file = candidate / f".agk_write_test_{os.getpid()}"
        test_file.touch()
        test_file.unlink()
        return candidate
    except OSError:
        fallback = Path.home() / ".antigravity-k" / "data" / "search_cache"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except OSError:
            tmp = Path(tempfile.gettempdir()) / "antigravity-k" / "search_cache"
            tmp.mkdir(parents=True, exist_ok=True)
            return tmp


CACHE_DIR = _resolve_cache_dir()


# ─── 실시간 키워드 ──────────────────────────────────────────────

_REALTIME_KEYWORDS = frozenset(
    {
        # 날씨/기상 (매우 짧은 TTL)
        "날씨",
        "기온",
        "비",
        "맑음",
        "흐림",
        "눈",
        "태풍",
        "미세먼지",
        "기상",
        "weather",
        "temperature",
        "forecast",
        # 시간/날짜 (매우 짧은 TTL)
        "시간",
        "오늘",
        "내일",
        "모레",
        "어제",
        "요일",
        "현재",
        "지금",
        "방금",
        "시각",
        "몇 시",
        "today",
        "now",
        "current",
        # 주식/금융 (짧은 TTL, 30분)
        "주가",
        "주식",
        "시세",
        "환율",
        "코스피",
        "코스닥",
        "상장",
        "공시",
        "stock",
        "price",
        "market",
        "exchange",
        # 뉴스/속보 (짧은 TTL, 1시간)
        "뉴스",
        "속보",
        "실시간",
        "최신",
        "news",
        "latest",
        "breaking",
        # 검색 의도 (직접 캐시 저장 방지)
        "검색",
        "찾아줘",
        "알려줘",
        "조회",
    },
)

# ─── 카테고리별 TTL (시간) ───────────────────────────────────────

_CATEGORY_TTL_HOURS: dict[str, float] = {
    "realtime_weather": 0,  # 날씨 — 캐시 금지
    "realtime_news": 1,  # 뉴스 — 1시간
    "realtime_finance": 0.5,  # 주식/환율 — 30분
    "realtime_general": 0,  # 시간/날짜 — 캐시 금지
    "general": 24,  # 일반 — 24시간
    "technical": 72,  # 기술 문서 — 72시간
}


# ─── 쿼리 카테고리 분류 ──────────────────────────────────────────


def _classify_query_category(query: str) -> str:
    """쿼리를 카테고리로 분류하여 적절한 TTL을 결정합니다."""
    q = query.lower()
    # 날씨/기상
    if any(kw in q for kw in ("날씨", "weather", "기온", "미세먼지", "일기예보")):
        return "realtime_weather"
    # 주식/금융
    if any(kw in q for kw in ("주가", "주식", "시세", "환율", "코스피", "코스닥", "stock", "exchange")):
        return "realtime_finance"
    # 시간/날짜
    if any(kw in q for kw in ("오늘", "내일", "어제", "지금", "현재 시각", "몇 시")):
        return "realtime_general"
    # 뉴스
    if any(kw in q for kw in ("뉴스", "속보", "news", "breaking")):
        return "realtime_news"
    # 기술 문서 쿼리
    if any(kw in q for kw in ("python", "react", "api", "tutorial", "documentation", "example", "how to")):
        return "technical"
    return "general"


# ─── Fallback 쿼리 생성 ─────────────────────────────────────────


def _generate_fallback_queries(query: str) -> list[str]:
    candidates: list[str] = []

    # 원본 그대로
    candidates.append(query)

    normalized = " ".join(query.split())
    lowered = normalized.casefold()
    if "ollama" in lowered and "tool" in lowered and "call" in lowered:
        candidates.append("site:docs.ollama.com tool calling")
    elif "429" in lowered and "mdn" in lowered:
        candidates.append("429 Too Many Requests MDN Web Docs")
    elif "robots" in lowered and re.search(r"\brfc[-\s]?\d+\b", lowered):
        rfc_match = re.search(r"\brfc[-\s]?(\d+)\b", normalized, re.IGNORECASE)
        if rfc_match:
            candidates.append(f"robots exclusion protocol RFC {rfc_match.group(1)}")
    elif "qwen3.6" in lowered:
        candidates.append("Qwen3.6 model")

    documentation_variant = re.sub(
        r"\bofficial\s+documentation\b",
        "official docs",
        normalized,
        flags=re.IGNORECASE,
    )
    if documentation_variant != normalized:
        candidates.append(documentation_variant)
    elif re.search(r"\bdocumentation\b", normalized, re.IGNORECASE):
        candidates.append(
            re.sub(r"\bdocumentation\b", "docs", normalized, flags=re.IGNORECASE),
        )

    # 1. 한국어 조사 제거
    cleaned = re.sub(
        r"(?<=\S)(은|는|이|가|을|를|의|에|에서)(?=\s|$|[.!?,\n])",
        " ",
        query,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned != query and len(cleaned) > 1:
        candidates.append(cleaned)

    # 2. 요청 동사 제거
    cleaned2 = re.sub(
        r"(알려줘|찾아줘|조회해|알려 주|찾아 주|말해줘|검색해|보여줘|궁금해|뭐야|뭔지|설명해|분석해|정리해|추천해|비교해)",
        "",
        query,
    )
    cleaned2 = re.sub(r"\s+", " ", cleaned2).strip()
    if cleaned2 and cleaned2 != query and len(cleaned2) > 1:
        candidates.append(cleaned2)

    # 3. 구두점/따옴표 제거
    no_punct = re.sub(
        r"['\"「」『』\[\](){}「」【】『』《》!?,.:;\-_+=~`@#$%^&*|\\/<>'\"‘’“”]",
        " ",
        query,
    )
    no_punct = re.sub(r"\s+", " ", no_punct).strip()
    if no_punct and no_punct != query and len(no_punct) > 1:
        candidates.append(no_punct)

    # 4. 축약형 (공백 제거)
    condensed = re.sub(r"\s+", "", query)
    if condensed and condensed != query and len(condensed) > 1:
        candidates.append(condensed)

    # 5. 영어 조사 제거
    eng_cleaned = re.sub(
        r"\b(the|a|an|of|for|in|at|on|to|by|with|from|about|into|through|during)\b",
        "",
        query,
        flags=re.IGNORECASE,
    )
    eng_cleaned = re.sub(r"\s+", " ", eng_cleaned).strip()
    if eng_cleaned and eng_cleaned != query and len(eng_cleaned) > 1:
        candidates.append(eng_cleaned)

    # 중복 제거 (순서 유지)
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        c_norm = c.lower().strip()
        if c_norm and len(c_norm) >= 2 and c_norm not in seen:
            seen.add(c_norm)
            unique.append(c)

    return unique


# ─── 검색 캐시 ────────────────────────────────────────────────────


class SearchCache:
    """검색 결과 로컬 캐시 (디스크 기반).

    카테고리별 TTL을 지원하며, force_refresh=True로 캐시를 우회할 수 있습니다.
    """

    def __init__(self, ttl_hours: int = 24) -> None:
        self.ttl_hours: int = ttl_hours
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _cache_key(self, query: str) -> str:
        """쿼리를 안전한 파일명으로 변환."""
        safe = re.sub(r"[^\w\s-]", "", query.lower()).strip()
        safe = re.sub(r"\s+", "_", safe)
        return safe[:80]

    def _get_effective_ttl(self, query: str) -> float:
        """쿼리 카테고리에 따른 유효 TTL을 반환합니다 (시간 단위)."""
        category = _classify_query_category(query)
        return _CATEGORY_TTL_HOURS.get(category, self.ttl_hours)

    def _read(self, query: str, *, allow_expired: bool) -> SearchResponse | None:
        key = self._cache_key(query)
        cache_file = CACHE_DIR / f"{key}.json"

        if not cache_file.exists() or any(kw in query for kw in _REALTIME_KEYWORDS):
            return None

        try:
            data = cast(dict[str, object], json.loads(cache_file.read_text(encoding="utf-8")))
            cached_time = datetime.fromisoformat(str(data.get("cached_at", "")))
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - cached_time).total_seconds() / 3600
            effective_ttl = self._get_effective_ttl(query)
            if age_hours > effective_ttl and (not allow_expired or age_hours > max(effective_ttl * 7, 24)):
                cache_file.unlink(missing_ok=True)
                return None

            raw_results = data.get("results", [])
            result_items = cast(list[object], raw_results) if isinstance(raw_results, list) else []
            results: list[SearchResult] = []
            for item in result_items:
                if not isinstance(item, dict):
                    continue
                payload = cast(dict[str, object], item)
                results.append(
                    SearchResult(
                        title=str(payload.get("title", "")),
                        url=str(payload.get("url", "")),
                        snippet=str(payload.get("snippet", "")),
                        source=str(payload.get("source", "")),
                        timestamp=str(payload.get("timestamp", "")),
                        relevance_score=float(str(payload.get("relevance_score", 0.0) or 0.0)),
                        canonical_url=str(payload.get("canonical_url", "")),
                        source_id=str(payload.get("source_id", "")),
                        domain=str(payload.get("domain", "")),
                        authority_score=float(str(payload.get("authority_score", 0.0) or 0.0)),
                        ranking_score=float(str(payload.get("ranking_score", 0.0) or 0.0)),
                    )
                )
            return SearchResponse(
                query=str(data["query"]),
                results=results,
                total_results=len(results),
                engine=str(data.get("engine", "cache")),
                cached=True,
                stale=age_hours > effective_ttl,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("캐시 읽기 실패: %s", e)
            return None

    def get(self, query: str, force_refresh: bool = False) -> SearchResponse | None:
        """캐시에서 결과 조회.

        Args:
            query: 검색 쿼리
            force_refresh: True면 캐시를 완전히 무시하고 None 반환
        """
        if force_refresh:
            return None
        return self._read(query, allow_expired=False)

    def get_stale(self, query: str) -> SearchResponse | None:
        return self._read(query, allow_expired=True)

    def set(self, query: str, response: SearchResponse):
        """검색 결과를 캐시에 저장.

        실시간성이 높은 키워드는 캐시에 저장하지 않습니다.
        """
        effective_ttl = self._get_effective_ttl(query)
        if effective_ttl <= 0:
            return

        key = self._cache_key(query)
        cache_file = CACHE_DIR / f"{key}.json"

        data = {
            "query": query,
            "cached_at": datetime.now(UTC).isoformat(),
            "engine": response.engine,
            "ttl_hours": effective_ttl,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": r.source,
                    "timestamp": r.timestamp,
                    "relevance_score": r.relevance_score,
                    "canonical_url": r.canonical_url,
                    "source_id": r.source_id,
                    "domain": r.domain,
                    "authority_score": r.authority_score,
                    "ranking_score": r.ranking_score,
                }
                for r in response.results
            ],
        }
        _ = cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self, query: str | None = None):
        """캐시를 정리합니다.

        Args:
            query: 특정 쿼리만 정리하려면 지정. None이면 전체 정리.
        """
        if query:
            key = self._cache_key(query)
            cache_file = CACHE_DIR / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()
                logger.info("캐시 삭제: %s", key)
        else:
            import shutil

            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                logger.info("캐시 전체 삭제 완료")

    def get_cache_stats(self) -> dict[str, object]:
        """캐시 통계를 반환합니다."""
        if not CACHE_DIR.exists():
            return {"total_files": 0, "total_size_kb": 0}

        total_size = 0
        count = 0
        for f in CACHE_DIR.glob("*.json"):
            total_size += f.stat().st_size
            count += 1
        return {
            "total_files": count,
            "total_size_kb": round(total_size / 1024, 1),
            "cache_dir": str(CACHE_DIR),
        }


__all__ = [
    "CACHE_DIR",
    "_CATEGORY_TTL_HOURS",
    "_REALTIME_KEYWORDS",
    "SearchCache",
    "_classify_query_category",
    "_generate_fallback_queries",
]
