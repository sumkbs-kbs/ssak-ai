from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from http.client import HTTPResponse
from typing import cast
from urllib.parse import urlsplit
from urllib.request import Request

import httpx

from .web_search_quality import (
    canonicalize_url,
    is_public_http_url,
    resolve_public_http_url_sync,
)

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "localhost.localdomain", "127.0.0.1", "::1"})

# 재시도 가능한 일시적 HTTP 상태 — 요청이 처리되지 않고 거부된 경우라
# 재시도가 안전하다 (응답 스트리밍 중 오류는 여기서 다루지 않는다).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES: int = 2
_RETRY_AFTER_CAP_SEC: float = 20.0
_BASE_BACKOFF_SEC: float = 1.0

# 테스트 주입용 sleep (실제 대기 없이 재시도 로직 검증)
_retry_sleep = time.sleep


class EgressPolicyError(ValueError):
    pass


def _target_url(target: str | Request) -> str:
    return target.full_url if isinstance(target, Request) else target


def _is_local_host(hostname: str) -> bool:
    return hostname.casefold() in _LOCAL_HOSTS or hostname.casefold().endswith(".localhost")


def validate_egress_url(
    url: str,
    *,
    allow_local: bool = True,
    resolve_dns: bool = True,
) -> str:
    canonical = canonicalize_url(url)
    if not canonical:
        raise EgressPolicyError("egress URL must be an unauthenticated HTTP(S) URL")

    hostname = urlsplit(canonical).hostname or ""
    if _is_local_host(hostname):
        if allow_local:
            return canonical
        raise EgressPolicyError("local egress is disabled for this connector")

    if not is_public_http_url(canonical):
        raise EgressPolicyError(f"private or non-public egress blocked: {hostname}")
    if resolve_dns and resolve_public_http_url_sync(canonical) is None:
        raise EgressPolicyError(f"egress DNS resolution is not public: {hostname}")
    return canonical


def _retry_delay(attempt: int, error: urllib.error.HTTPError) -> float:
    """Retry-After 헤더 우선, 없으면 지수 백오프. 상한 20초."""
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after:
        try:
            return min(float(retry_after), _RETRY_AFTER_CAP_SEC)
        except ValueError:
            pass
    return min(_BASE_BACKOFF_SEC * (2**attempt), _RETRY_AFTER_CAP_SEC)


def safe_urlopen(
    target: str | Request,
    allow_local: bool = True,
    timeout: float | None = None,
) -> HTTPResponse:
    """egress 정책 검증 후 urlopen — 일시적 HTTP 오류(429/5xx)는 재시도한다.

    재시도는 연결 설정 단계에서 거부된 경우에만 안전하므로 여기서만
    수행한다 (응답 소비 중 오류는 호출자 몫). Retry-After 헤더를 존중하고
    최대 2회 재시도한다.
    """
    _ = validate_egress_url(_target_url(target), allow_local=allow_local)
    last_error: urllib.error.HTTPError | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            # validate_egress_url above allowlists HTTP(S) before this sink.
            if timeout is None:
                return cast(HTTPResponse, urllib.request.urlopen(target))  # nosec B310
            return cast(HTTPResponse, urllib.request.urlopen(target, timeout=timeout))  # nosec B310
        except urllib.error.HTTPError as error:
            if error.code not in _RETRYABLE_STATUS or attempt >= _MAX_RETRIES:
                raise
            last_error = error
            delay = _retry_delay(attempt, error)
            logger.warning(
                "[egress] HTTP %s — %.1f초 후 재시도 (%d/%d) %s",
                error.code,
                delay,
                attempt + 1,
                _MAX_RETRIES,
                _target_url(target)[:120],
            )
            _retry_sleep(delay)
    assert last_error is not None  # 재시도 루프를 통과했으면 반드시 설정됨
    raise last_error


def validate_httpx_request(request: httpx.Request) -> None:
    _ = validate_egress_url(str(request.url))


async def validate_httpx_request_async(request: httpx.Request) -> None:
    validate_httpx_request(request)


def validate_public_httpx_request(request: httpx.Request) -> None:
    """Reject local/private destinations for untrusted outbound requests."""
    _ = validate_egress_url(str(request.url), allow_local=False)


async def validate_public_httpx_request_async(request: httpx.Request) -> None:
    """Async event-hook variant of :func:`validate_public_httpx_request`."""
    validate_public_httpx_request(request)


__all__ = [
    "EgressPolicyError",
    "safe_urlopen",
    "validate_egress_url",
    "validate_httpx_request",
    "validate_httpx_request_async",
    "validate_public_httpx_request",
    "validate_public_httpx_request_async",
]
