"""NX-05 잔여 — **이미 열려 있는** SSE 스트림의 폐기.

NX-05 는 PIN 변경이 WS 연결을 즉시(<=5초) 닫는다는 것까지 고정했지만, SSE 는
"새 요청은 401" 까지만 확인했다. 서버가 이미 열린 응답을 닫는 경로가 없었고,
`task_api._event_stream` 의 루프는 `request.is_disconnected()` 만 봤다 — 그래서 폐기
뒤에도 스트림이 종료 상태에 이를 때까지 이벤트를 계속 보냈다.
이 모듈이 그 공백을 닫는다.

계약:

* 대상은 `content-type: text/event-stream` 응답뿐이다(JSON·파일 응답은 건드리지 않는다).
* 판정은 **요청이 제시한 bearer 자격 증명이 지금 세대에서 유효한가** 이다. 토큰 서비스는
  프로세스 캐시를 쓰지 않고 epoch 을 파일에서 읽으므로, 다른 프로세스가 바꾼 PIN 도
  같은 주기 안에 반영된다.
* bearer 가 없는 연결(익명 `open_loopback`)은 폐기하지 않는다 — credential 이 없으면
  무효화할 세대가 없다(NX-05 정책). "폐기 미구현"과 구별되도록 시험으로 고정한다.
* 폐기 시 마지막 프레임은 `event: session.revoked` 이고, 그 뒤 스트림은 끝난다.
  클라이언트는 재연결(=401)이 아니라 **먼저 이유를 받고** 로그인 화면으로 갈 수 있다.
* 검사 주기는 `AGK_SSE_REVOCATION_CHECK_SECONDS`(기본 1초)로 조절한다. 주기 사이에
  돌아가는 검사는 **매 주기 1회**이고(열린 스트림마다), 본문 청크를 기다리는 동안에도
  돌아간다 — 청크가 오지 않는 유휴 스트림이 폐기를 피하지 못하게 하려는 것이다.

구현 위치가 미들웨어인 이유: SSE 를 여는 지점이 이 저장소에 16곳(`chat.py` 9곳,
`task_api`·`responses_api`·`messages_api`·`agent_stream_api`·`workspace_services` 등)이라
라우트별로 손대면 다음에 추가되는 스트림이 다시 빠진다. 응답 하나를 한 곳에서 감싼다.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol, cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("antigravity_k.api.sse_revocation")

SSE_MEDIA_TYPE = "text/event-stream"
REVOCATION_EVENT = "session.revoked"
REVOCATION_REASON = "auth_epoch_changed"
DEFAULT_CHECK_INTERVAL_SECONDS = 1.0
CHECK_INTERVAL_ENV = "AGK_SSE_REVOCATION_CHECK_SECONDS"


def check_interval_seconds() -> float:
    """폐기 검사 주기(초). 잘못된 값은 기본값으로 돌리고 이유를 남긴다."""
    raw = os.environ.get(CHECK_INTERVAL_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_CHECK_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r (using %s)", CHECK_INTERVAL_ENV, raw, DEFAULT_CHECK_INTERVAL_SECONDS)
        return DEFAULT_CHECK_INTERVAL_SECONDS
    if value <= 0:
        logger.warning(
            "Ignoring non-positive %s=%r (using %s)", CHECK_INTERVAL_ENV, raw, DEFAULT_CHECK_INTERVAL_SECONDS
        )
        return DEFAULT_CHECK_INTERVAL_SECONDS
    return value


def revocation_frame(reason: str = REVOCATION_REASON) -> bytes:
    """폐기를 알리는 마지막 SSE 프레임."""
    payload = json.dumps({"type": REVOCATION_EVENT, "reason": reason}, separators=(",", ":"))
    return f"event: {REVOCATION_EVENT}\ndata: {payload}\n\n".encode()


def request_credential_revoked(request: Request) -> bool:
    """이 요청의 bearer 자격 증명이 **지금** 세대에서 실효됐는가.

    bearer 가 없으면 False 다(익명 loopback 은 폐기 대상이 아니다). bearer 가 있으면
    매번 다시 검증한다 — 세대 비교는 파일에서 읽으므로 캐시가 없다.
    """
    from antigravity_k.api.auth_routes import extract_bearer_token, get_token_service

    token = extract_bearer_token(request)
    if token is None:
        return False
    try:
        return get_token_service().verify_token(token) is None
    except Exception:  # noqa: BLE001 — 검증기 자체가 터지면 폐기로 단정하지 않는다
        logger.warning("SSE revocation check failed to verify token", exc_info=True)
        return False


def _record_revocation(request: Request) -> None:
    """폐기 1건을 기록한다. 관측 실패가 폐기 자체를 막아서는 안 된다."""
    with contextlib.suppress(Exception):
        from antigravity_k.engine.operational_metrics import record_auth_event

        record_auth_event("stream_revoked")
    logger.info("sse.stream.revoked path=%s", request.url.path)


async def _next_chunk(iterator: AsyncIterator[Any]) -> Any:
    """async generator 의 `__anext__` 를 Task 로 감싸기 위한 얇은 코루틴.

    `asyncio.ensure_future(generator.__anext__())` 는 `async_generator_asend` 를
    받아들이지 않는다(coroutine 이 아니다) — 그래서 코루틴 이름을 한 겹 씌운다.
    """
    return await iterator.__anext__()


async def guard_sse_stream(
    iterator: AsyncIterator[Any],
    request: Request,
    *,
    interval: float | None = None,
) -> AsyncIterator[Any]:
    """SSE 본문 스트림을 세대 인지로 감싼다.

    청크를 `interval` 초까지만 기다리고, 기다리는 동안에도 폐기를 확인한다. 폐기가
    확인되면 `session.revoked` 프레임 하나를 내보내고 스트림을 끝낸다. 청크가 계속
    오는 스트림도 같은 주기로 검사하므로 폐기 지연은 체크 주기 안쪽이다.
    """
    check_every = check_interval_seconds() if interval is None else interval
    pending: asyncio.Task[Any] | None = None
    try:
        while True:
            if request_credential_revoked(request):
                _record_revocation(request)
                yield revocation_frame()
                return
            if pending is None:
                pending = asyncio.ensure_future(_next_chunk(iterator))
            try:
                chunk = await asyncio.wait_for(asyncio.shield(pending), timeout=check_every)
            except TimeoutError:
                continue
            except StopAsyncIteration:
                return
            pending = None
            yield chunk
    finally:
        # 취소된 청크 대기가 남은 채로 끝내면 내부 제너레이터가 정리되지 않는다.
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(BaseException):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()


def _is_sse_response(response: Response) -> bool:
    """`text/event-stream` 인가 — 미들웨어 체인을 지나며 media_type 이 비는 경우가 있어
    헤더로 판정한다(BaseHTTPMiddleware 의 `_StreamingResponse` 는 media_type=None 으로 만들어진다).
    """
    content_type = response.headers.get("content-type", "")
    return content_type.split(";", 1)[0].strip().lower() == SSE_MEDIA_TYPE


class _StreamingResponseLike(Protocol):
    """`body_iterator` 를 가진 스트리밍 응답(`StreamingResponse` / BaseHTTPMiddleware 의 래퍼)."""

    body_iterator: AsyncIterator[Any]


class SSERevocationMiddleware(BaseHTTPMiddleware):
    """`text/event-stream` 응답의 본문만 폐기 인지 스트림으로 바꾼다."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not _is_sse_response(response):
            return response
        iterator = cast(AsyncIterator[Any] | None, getattr(response, "body_iterator", None))
        if iterator is None:
            return response
        # `Response` 와 구조적 중첩이 없다고 보는 검사기가 있다(TypeVar 없는 Protocol) — 한 번 object 로
        # 좁혀 캐스팅한다. 실제 대상은 `StreamingResponse`/BaseHTTPMiddleware 의 `_StreamingResponse` 다.
        cast(_StreamingResponseLike, cast(object, response)).body_iterator = guard_sse_stream(iterator, request)
        return response


__all__ = [
    "CHECK_INTERVAL_ENV",
    "DEFAULT_CHECK_INTERVAL_SECONDS",
    "REVOCATION_EVENT",
    "REVOCATION_REASON",
    "SSE_MEDIA_TYPE",
    "SSERevocationMiddleware",
    "check_interval_seconds",
    "guard_sse_stream",
    "request_credential_revoked",
    "revocation_frame",
]
