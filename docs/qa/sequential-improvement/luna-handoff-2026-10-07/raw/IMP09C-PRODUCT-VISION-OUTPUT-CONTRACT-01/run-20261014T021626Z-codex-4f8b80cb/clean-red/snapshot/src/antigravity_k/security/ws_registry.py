"""인증된 WebSocket 연결 레지스트리와 폐기 헬퍼 (NX-05, NX-10 리팩터).

NX-05 에서 PIN 변경이 **이미 열려 있는** WS 를 즉시 끊어야 했다("활성 연결 폐기 한도
<=5초") — 세대(epoch) 검사만으로는 새 요청을 보내지 않는 소켓이 끊기지 않는다.

처음에는 이 레지스트리를 `api/routes/session_state.py` 에 두었는데, PIN 변경 라우트
(`api/auth_routes.py`)가 폐기 함수를 부르려면 `session_state` 를 임포트해야 했고
그 모듈은 이미 `auth_routes` 를 임포트한다(토큰 검증) → **순환 임포트**. 그래서
레지스트리를 leaf 모듈로 내렸다:

    auth_routes ─┐
                 ├─→ security.ws_registry   (leaf: stdlib + WebSocket 타입만)
    session_state┘

`session_state` 는 호환을 위해 이 이름들을 다시 내보낸다(기존 호출자/테스트 유지).

소켓은 **약한 참조**로만 보관한다. WS 핸들러가 끝나면 Starlette 이 소켓을 놓아주므로
별도 해제 훅 없이도 죽은 연결이 레지스트리에 남지 않는다(핸들러 5곳을 고치지 않는다).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref

from fastapi import WebSocket

logger = logging.getLogger("antigravity_k.security.ws_registry")

_authorized_ws: list[tuple[weakref.ReferenceType[WebSocket], asyncio.AbstractEventLoop]] = []
_ws_registry_lock = threading.Lock()


def register_authorized_ws(websocket: WebSocket) -> None:
    """인증된 WS 연결을 등록한다 (이벤트 루프를 함께 보관해 폐기 시 사용)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - WS 게이트는 항상 루프 안에서 실행된다
        logger.warning("Cannot register authorized WS outside an event loop")
        return
    with _ws_registry_lock:
        _prune_locked()
        if any(existing() is websocket for existing, _loop in _authorized_ws):
            return
        _authorized_ws.append((weakref.ref(websocket), loop))


def authorized_ws_count() -> int:
    """현재 등록된(살아 있는) 인증 WS 연결 수 — 테스트/관측용."""
    with _ws_registry_lock:
        _prune_locked()
        return len(_authorized_ws)


def reset_authorized_ws_registry() -> None:
    """테스트 헬퍼 — 레지스트리를 비운다(연결을 닫지는 않는다)."""
    with _ws_registry_lock:
        _authorized_ws.clear()


def _is_connected(websocket: WebSocket) -> bool:
    """이미 끊긴 소켓을 레지스트리에 남기지 않기 위한 판정."""
    state = getattr(websocket, "client_state", None)
    if state is None:
        return True  # 테스트 더블은 살아 있다고 본다
    name = getattr(state, "name", str(state))
    return name == "CONNECTED"


def _close_dispatched(websocket: WebSocket) -> bool:
    """close 프레임을 **보냈는가**(= 이 연결은 더 이상 정상 메시지를 처리할 수 없다).

    NX-09 실측: uvicorn+Starlette 에서 `close()` 는 프레임을 즉시 내보내지만 코루틴이
    반환하지 않는 경우가 있다 — 클라이언트는 4401 을 받았는데 서버 객체는
    `application_state=DISCONNECTED` / `client_state=CONNECTED` 로 남고 await 가 끝나지 않는다.
    그래서 "닫혔는가"의 판정은 client_state 가 아니라 **application_state** 로 한다(실측 근거:
    `nx09/repro_nx09_ws_revocation.py`).
    """
    state = getattr(websocket, "application_state", None)
    if state is None:
        return True  # 테스트 더블 — close 호출이 성공했으면 폐기로 본다
    return getattr(state, "name", str(state)) == "DISCONNECTED"


def _prune_locked() -> None:
    """죽은(GC 되었거나 끊긴) 연결을 제거한다(락 보유 필수)."""
    live: list[tuple[weakref.ReferenceType[WebSocket], asyncio.AbstractEventLoop]] = []
    for ref, loop in _authorized_ws:
        websocket = ref()
        if websocket is not None and _is_connected(websocket):
            live.append((ref, loop))
    _authorized_ws[:] = live


def _take_authorized_locked() -> list[tuple[WebSocket, asyncio.AbstractEventLoop]]:
    """살아 있는 연결을 꺼내고 레지스트리를 비운다(락 보유 필수)."""
    _prune_locked()
    taken: list[tuple[WebSocket, asyncio.AbstractEventLoop]] = []
    for ref, loop in _authorized_ws:
        websocket = ref()
        if websocket is not None:  # pragma: no cover - _prune_locked 가 이미 걸러낸다
            taken.append((websocket, loop))
    _authorized_ws.clear()
    return taken


def close_authorized_ws_blocking(code: int = 4401, reason: str = "Session revoked") -> int:
    """동기 라우트(PIN 변경)에서 인증 WS 를 닫는다.

    각 연결이 등록된 이벤트 루프로 close 코루틴을 넘기고 완료를 기다린다.
    즉시(수십 ms) 닫히므로 "다음 요청/폴링까지 기다리는" 폐기 공백이 없다.
    """
    with _ws_registry_lock:
        targets = _take_authorized_locked()
    closed = 0
    for websocket, loop in targets:
        # NX-09: 폐기 판정은 "close 를 **보냈는가**"로 한다. Starlette 의 `close()` 는 close 프레임을
        # 보낸 뒤에도 예외를 올린다(`WebSocketDisconnect` — `str()` 이 비어 있다). 그 예외까지 실패로
        # 세면 실제로 닫힌 연결이 `sessions_revoked: 0` 으로 보고되고 성공이 경고 로그로 남는다
        # (실측: 이 드라이버에서 클라이언트는 4401 을 받았는데 카운터는 0 이었다).
        try:
            future = asyncio.run_coroutine_threadsafe(websocket.close(code=code, reason=reason), loop)
        except Exception as exc:  # noqa: BLE001 — 루프가 죽어 **시도조차** 못한 경우만 실패다
            logger.warning("Could not schedule authorized WS close: %r", exc)
            continue
        try:
            # 완료를 끝까지 기다리지 않는다 — 위 `_close_dispatched` 주석의 이유로 영원히
            # 반환하지 않을 수 있고, 그러면 PIN 변경 응답이 그만큼 늦어진다(실측 5초 상한 소진).
            future.result(timeout=0.25)
            closed += 1
            continue
        except TimeoutError:
            pass
        except Exception as exc:  # noqa: BLE001 — close 프레임 이후의 예외는 폐기 실패가 아니다
            logger.debug("Authorized WS close raised after dispatch: %r", exc)
        if _close_dispatched(websocket) or not _is_connected(websocket):
            closed += 1
        else:
            logger.warning("Authorized WS close was not dispatched")
    return closed


async def aclose_authorized_ws(code: int = 4401, reason: str = "Session revoked") -> int:
    """비동기 경로용 폐기 헬퍼 (루프를 이미 들고 있는 경우)."""
    with _ws_registry_lock:
        targets = [websocket for websocket, _loop in _take_authorized_locked()]
    closed = 0
    for websocket in targets:
        try:
            # NX-09: close 는 프레임을 내보낸 뒤 반환하지 않을 수 있다(실측) — 상한을 둔다.
            await asyncio.wait_for(websocket.close(code=code, reason=reason), timeout=1.0)
            closed += 1
        except Exception as exc:  # noqa: BLE001
            if _close_dispatched(websocket) or not _is_connected(websocket):
                closed += 1
            else:
                logger.warning("Authorized WS close was not dispatched: %r", exc)
    return closed


__all__ = [
    "aclose_authorized_ws",
    "authorized_ws_count",
    "close_authorized_ws_blocking",
    "register_authorized_ws",
    "reset_authorized_ws_registry",
]
