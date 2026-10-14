"""In-memory API Response Cache.

TTL 기반 응답 캐싱 레이어. Redis 같은 외부 의존성 없이
FastAPI 엔드포인트의 응답을 메모리에 캐싱합니다.

사용법:
    from antigravity_k.engine.api_cache import cached, api_cache

    @router.get("/api/slow-endpoint")
    @cached(ttl=60, tags=["system"])
    async def my_endpoint():
        return {"data": "expensive"}

    # 직접 사용
    api_cache.set("key", {"data": "value"}, ttl=30, tags=["system"])
    value = api_cache.get("key")

    # 태그 기반 무효화
    api_cache.invalidate_tag("filesystem")  # 모든 filesystem 캐시 삭제
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ParamSpec, Protocol, TypeVar, cast

logger = logging.getLogger("antigravity_k.api_cache")

P = ParamSpec("P")
R = TypeVar("R")


class _RequestURL(Protocol):
    path: str


class _RequestLike(Protocol):
    method: str
    query_params: object
    url: _RequestURL


# ---------------------------------------------------------------------------
# Default TTL constants (seconds)
# ---------------------------------------------------------------------------

CACHE_DEFAULT_TTL = 60  # 기본 60초

# 엔드포인트 카테고리별 TTL
CACHE_TTL = {
    "models": 60,  # 모델 목록 — 1분
    "settings": 30,  # 설정 — 30초
    "git": 10,  # Git 상태 — 10초
    "filesystem": 15,  # 파일 시스템 — 15초
    "skills": 60,  # 스킬 목록 — 1분
    "agent": 30,  # 에이전트 상태 — 30초
    "tasks": 15,  # 태스크 목록 — 15초
    "logs": 10,  # 로그 — 10초
}


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------


@dataclass
class ApiCacheEntry:
    """단일 캐시 엔트리.

    Attributes:
        key: 캐시 키 (일반적으로 URL path + query)
        value: 캐시된 응답 데이터 (직렬화 가능해야 함)
        ttl: TTL (초)
        tags: 연관 태그 (태그 기반 무효화용)
        created_at: 생성 시각 (time.time)
        last_accessed_at: 최종 접근 시각 (LRU eviction용, time.time)
        hit_count: 조회 횟수
    """

    key: str
    value: object
    ttl: float
    tags: frozenset[str] = field(default_factory=frozenset)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """TTL 만료 여부."""
        return time.time() - self.created_at > self.ttl

    @property
    def age(self) -> float:
        """현재 나이 (초)."""
        return time.time() - self.created_at

    @property
    def remaining_ttl(self) -> float:
        """남은 TTL (초). 음수면 만료."""
        return max(0.0, self.ttl - self.age)


# ---------------------------------------------------------------------------
# ApiCache — thread-safe in-memory cache
# ---------------------------------------------------------------------------


class ApiCache:
    """스레드 안전한 인메모리 응답 캐시.

    Thread-Safety:
        내부적으로 ``asyncio.Lock``을 사용하여 코루틴 레벨 동기화 제공.
        멀티스레드 환경에서는 추가 동기화 필요.

    Features:
        - TTL 기반 자동 만료 (``clear_expired``로 정리)
        - 태그 기반 무효화 (``invalidate_tag``)
        - 히트/미스 통계 수집
        - ``get_or_set``으로 lazy population
    """

    def __init__(self, default_ttl: float = CACHE_DEFAULT_TTL, max_size: int = 1000) -> None:
        self._default_ttl: float = default_ttl
        self._max_size: int = max_size
        self._entries: dict[str, ApiCacheEntry] = {}
        self._tag_index: dict[str, set[str]] = {}  # tag → set of keys
        self._lock: asyncio.Lock = asyncio.Lock()
        self._hits: int = 0
        self._misses: int = 0
        self._eviction_count: int = 0

    # ─── Core operations ─────────────────────────────────────────

    async def get(self, key: str) -> object | None:
        """캐시에서 값을 조회합니다.

        Args:
            key: 캐시 키

        Returns:
            캐시된 값 (없거나 만료됐으면 None)
        """
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                self._misses += 1
                _ = await self._remove(key)
                return None

            entry.hit_count += 1
            entry.last_accessed_at = time.time()
            self._hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: object,
        ttl: float | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """캐시에 값을 저장합니다.

        Args:
            key: 캐시 키
            value: 저장할 값
            ttl: TTL (초). None이면 기본 TTL 사용.
            tags: 연관 태그 리스트 (태그 기반 무효화용)
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        tag_set: frozenset[str] = frozenset(tags) if tags else frozenset()

        entry = ApiCacheEntry(
            key=key,
            value=value,
            ttl=effective_ttl,
            tags=tag_set,
        )

        async with self._lock:
            self._entries[key] = entry
            for tag in tag_set:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(key)

            # max_size 초과 시 가장 오래된 항목 제거 (LRU 근사)
            _ = await self._evict_if_over_limit()

    async def delete(self, key: str) -> bool:
        """캐시에서 키를 삭제합니다.

        Returns:
            삭제 성공 여부 (키가 없으면 False)
        """
        async with self._lock:
            return await self._remove(key)

    async def _remove(self, key: str) -> bool:
        """락을 획득한 상태에서 호출해야 함."""
        entry = self._entries.pop(key, None)
        if entry is None:
            return False
        # 태그 인덱스에서도 제거
        for tag in entry.tags:
            tag_keys = self._tag_index.get(tag)
            if tag_keys:
                tag_keys.discard(key)
                if not tag_keys:
                    _ = self._tag_index.pop(tag, None)
        return True

    # ─── Tag-based invalidation ──────────────────────────────────

    async def invalidate_tag(self, tag: str) -> int:
        """특정 태그가 달린 모든 캐시를 무효화합니다.

        Args:
            tag: 무효화할 태그

        Returns:
            삭제된 엔트리 개수
        """
        async with self._lock:
            keys = self._tag_index.pop(tag, set())
            count = 0
            for key in keys:
                entry = self._entries.pop(key, None)
                if entry is not None:
                    count += 1
                    # 다른 태그 인덱스에서도 제거
                    for other_tag in entry.tags:
                        if other_tag != tag:
                            other_keys = self._tag_index.get(other_tag)
                            if other_keys:
                                other_keys.discard(key)
            logger.debug("Cache invalidated tag='%s': %d entries removed", tag, count)
            return count

    async def invalidate_prefix(self, prefix: str) -> int:
        """특정 접두사로 시작하는 모든 캐시를 무효화합니다.

        Args:
            prefix: 키 접두사

        Returns:
            삭제된 엔트리 개수
        """
        async with self._lock:
            keys_to_delete = [k for k in self._entries if k.startswith(prefix)]
            count = 0
            for key in keys_to_delete:
                if await self._remove(key):
                    count += 1
            logger.debug("Cache invalidated prefix='%s': %d entries removed", prefix, count)
            return count

    # ─── Lazy population ─────────────────────────────────────────

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], object | Awaitable[object]],
        ttl: float | None = None,
        tags: list[str] | None = None,
    ) -> object:
        """캐시된 값이 없으면 factory를 호출하여 값을 생성하고 캐싱합니다.

        Args:
            key: 캐시 키
            factory: 값 생성 콜백 (동기 또는 비동기)
            ttl: TTL
            tags: 연관 태그

        Returns:
            캐시 또는 factory의 반환값
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = factory()
        if asyncio.iscoroutine(value):
            value = await cast(Awaitable[object], value)

        await self.set(key, value, ttl=ttl, tags=tags)
        return value

    # ─── Cache cleanup ───────────────────────────────────────────

    async def clear_expired(self) -> int:
        """만료된 모든 엔트리를 정리합니다.

        Returns:
            정리된 엔트리 개수
        """
        async with self._lock:
            expired_keys = [k for k, e in self._entries.items() if e.is_expired]
            count = 0
            for key in expired_keys:
                if await self._remove(key):
                    count += 1
            if count:
                logger.debug("Cache cleanup: %d expired entries removed", count)
            return count

    async def clear(self) -> int:
        """전체 캐시를 비웁니다.

        Returns:
            삭제된 엔트리 개수
        """
        async with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._tag_index.clear()
            logger.debug("Cache cleared: %d entries removed", count)
            return count

    # ─── Statistics ──────────────────────────────────────────────

    async def get_stats(self) -> dict[str, object]:
        """캐시 통계를 반환합니다.

        Returns:
            ``{
                "total_entries": ...,
                "total_tags": ...,
                "hits": ...,
                "misses": ...,
                "hit_ratio": ...,
                "memory_estimate_kb": ...,
                "entries": [{"key": ..., "ttl": ..., "age": ..., "tags": ..., "hits": ...}, ...]
            }``
        """
        async with self._lock:
            total = len(self._entries)
            total_tags = len(self._tag_index)
            hits = self._hits
            misses = self._misses
            hit_ratio = hits / (hits + misses) if (hits + misses) > 0 else 0.0

            # 메모리 추정 (대략적인 값)
            import sys

            mem_estimate = sum(sys.getsizeof(e.value, 0) for e in self._entries.values())

            entries_info = [
                {
                    "key": e.key,
                    "ttl": e.ttl,
                    "age": round(e.age, 1),
                    "remaining_ttl": round(e.remaining_ttl, 1),
                    "tags": list(e.tags),
                    "hits": e.hit_count,
                }
                for e in sorted(self._entries.values(), key=lambda x: x.created_at, reverse=True)
            ]

            return {
                "total_entries": total,
                "total_tags": total_tags,
                "max_size": self._max_size,
                "hits": hits,
                "misses": misses,
                "hit_ratio": round(hit_ratio, 3),
                "memory_estimate_kb": round(mem_estimate / 1024, 1),
                "eviction_count": self._eviction_count,
                "entries": entries_info,
            }

    @property
    def max_size(self) -> int:
        """최대 캐시 엔트리 수."""
        return self._max_size

    async def _evict_if_over_limit(self) -> int:
        """max_size 초과 시 가장 오래된 엔트리를 제거합니다.

        LRU 근사 전략: ``created_at``이 가장 오래된 엔트리부터
        ``max_size`` 이하가 될 때까지 제거합니다.

        Returns:
            제거된 엔트리 개수
        """
        over = len(self._entries) - self._max_size
        if over <= 0:
            return 0

        # LRU 근사: last_accessed_at이 가장 오래된 순으로 정렬
        sorted_by_access = sorted(
            self._entries.values(),
            key=lambda e: e.last_accessed_at,
        )

        evicted = 0
        for entry in sorted_by_access[:over]:
            if await self._remove(entry.key):
                evicted += 1

        if evicted:
            self._eviction_count += evicted
            logger.debug(
                "Cache max_size eviction: %d entries removed (now %d / %d)",
                evicted,
                len(self._entries),
                self._max_size,
            )

        return evicted


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

api_cache = ApiCache()


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


def cached(
    ttl: float | None = None,
    tags: list[str] | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, Awaitable[object]]]:
    """FastAPI 엔드포인트 응답을 캐싱하는 데코레이터.

    GET 엔드포인트에 적용하여 응답을 자동으로 캐싱합니다.
    POST 등 요청 본문이 있는 엔드포인트는 캐싱하지 않습니다
    (요청 본문을 키에 포함하지 않으므로 의도치 않은 동작 방지).

    Args:
        ttl: TTL (초). None이면 ApiCache 기본값(60초) 사용.
        tags: 연관 태그 리스트 (e.g. ``["git", "filesystem"]``)
        key_builder: 캐시 키 생성 함수. 없으면 ``request.url.path + str(request.query_params)``

    Usage::

        @router.get("/v1/models")
        @cached(ttl=30, tags=["models"])
        async def list_models():
            return await fetch_models()

        # 태그 기반 무효화 (models 업데이트 시):
        # await api_cache.invalidate_tag("models")
    """
    effective_ttl = ttl if ttl is not None else CACHE_DEFAULT_TTL

    def decorator(func: Callable[P, R]) -> Callable[P, Awaitable[object]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
            # POST/PUT/DELETE/PATCH는 캐싱하지 않음 (요청 본문 무시 방지)
            request = cast(_RequestLike | None, kwargs.get("request"))
            if request is not None and request.method != "GET":
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await cast(Awaitable[object], result)
                return result

            # 캐시 키 생성
            if key_builder is not None:
                cache_key = key_builder(*args, **kwargs)
            elif request is not None:
                query = str(request.query_params) if request.query_params else ""
                cache_key = f"{request.url.path}?{query}" if query else request.url.path
            else:
                # request 파라미터가 없으면 함수명 + 인자로 fallback
                arg_key = (
                    ":".join(str(a) for a in args)
                    + ":"
                    + ":".join(f"{k}={v}" for k, v in kwargs.items() if k != "request")
                )
                cache_key = f"{func.__name__}:{arg_key}"

            # 캐시 히트
            cached_value = await api_cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 캐시 미스 → 실제 함수 호출 (sync/async 모두 지원)
            raw_result = func(*args, **kwargs)
            if asyncio.iscoroutine(raw_result):
                resolved_result: object = await cast(Awaitable[object], raw_result)
            else:
                resolved_result = raw_result

            # 응답 캐싱
            await api_cache.set(cache_key, resolved_result, ttl=effective_ttl, tags=tags)

            return resolved_result

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 태그 상수 (일관된 태그 이름)
# ---------------------------------------------------------------------------

TAG_GIT = "git"
TAG_FILESYSTEM = "filesystem"
TAG_MODELS = "models"
TAG_SKILLS = "skills"
TAG_SETTINGS = "settings"
TAG_AGENT = "agent"
TAG_TASKS = "tasks"
TAG_SYSTEM = "system"


__all__ = [
    "ApiCache",
    "ApiCacheEntry",
    "CACHE_TTL",
    "CACHE_DEFAULT_TTL",
    "TAG_GIT",
    "TAG_FILESYSTEM",
    "TAG_MODELS",
    "TAG_SKILLS",
    "TAG_SETTINGS",
    "TAG_AGENT",
    "TAG_TASKS",
    "TAG_SYSTEM",
    "api_cache",
    "cached",
]
