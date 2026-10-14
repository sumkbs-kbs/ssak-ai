"""WebSocket event streaming endpoint for real-time agent activity."""

import asyncio
import logging
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from antigravity_k.api.routes.session_state import close_unauthorized_ws
from antigravity_k.engine.event_bus import global_event_bus

logger = logging.getLogger("antigravity_k.api.events")

router = APIRouter()

type EventCallback = Callable[..., object]

# /v1/ws/events가 구독하여 대시보드로 포워딩하는 이벤트 목록.
# 프론트엔드 dashboard/src/hooks/useEventWebSocket.ts 의 discriminatedUnion과
# 정합해야 한다 — 계약 테스트(tests/test_events.py::
# test_events_to_track_covers_frontend_ws_contract)가 이 상수를 고정한다.
# 발행자 주석 (모든 항목은 실제 발행자가 있어야 한다 — 죽은 구독 금지):
#   ToolExecutionStarted/Finished: engine.tool_loop._publish_event
#   FailureDetected:               engine.tool_executor._broadcast_failure_event
#   AgentTurnStarted/Ended:        event_bus HOOK_KIND_TO_EVENT_NAME 브릿지 (autonomous_learner 발신)
#   QualityCheckPassed/Failed:     engine.tool_loop._publish_quality_event (QualityGate 결과)
#   AntiPatternsDetected:          engine.cognitive_loop._publish_anti_patterns (반복 실패 감지)
#   FileOpened/FileModified:       engine.tool_executor._broadcast_file_event
#   ModeChanged:                   engine.mode_manager._publish_to_eventbus
#   CognitiveAdaptation:           engine.cognitive_loop._publish_cognitive_adaptation
#   PlanningModeStarted:           engine.mode_manager._publish_planning_started
#   ApprovalRequired:              engine.tool_executor._broadcast_approval_required
TRACKED_EVENTS = [
    "ToolExecutionStarted",
    "ToolExecutionFinished",
    "FailureDetected",
    "AgentTurnStarted",
    "AgentTurnEnded",
    "QualityCheckPassed",
    "QualityCheckFailed",
    "AntiPatternsDetected",
    "FileOpened",
    "FileModified",
    "ModeChanged",  # Phase 1 D7: Dashboard 모드 인디케이터 실시간 업데이트
    "CognitiveAdaptation",
    "PlanningModeStarted",
    "ApprovalRequired",
]


async def _send_keepalive(websocket: WebSocket) -> bool:
    try:
        await websocket.send_json({"event": "ping", "data": {}})
    except WebSocketDisconnect:
        return False
    return True


@router.websocket("/v1/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """Websocket Events.

    Args:
        websocket (WebSocket): WebSocket websocket.

    """
    if await close_unauthorized_ws(websocket):
        return
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    # 핸들러의 이벤트 루프를 캡처한다. EventBus 발행자는 반드시 핸들러 스레드가 아니다
    # (HookEventBus watcher 스레드, ThreadPoolExecutor 워커 등 루프가 없는 스레드) —
    # call_soon_threadsafe로만 크로스-스레드에서 안전하게 큐에 전달할 수 있다.
    # 이전 구현(asyncio.get_running_loop() in _cb)은 루프 없는 스레드에서 RuntimeError로
    # 이벤트를 조용히 유실했다 (E2E 계약 검증에서 발견).
    event_loop = asyncio.get_running_loop()

    def make_callback(e_name: str) -> EventCallback:
        def _cb(**kwargs: object) -> None:
            try:
                event_payload: dict[str, object] = {"event": e_name, "data": kwargs}
                _ = event_loop.call_soon_threadsafe(
                    queue.put_nowait,
                    event_payload,
                )
            except Exception:
                logger.exception("Unhandled exception")

        return _cb

    callbacks: dict[str, EventCallback] = {e: make_callback(e) for e in TRACKED_EVENTS}
    for e, cb in callbacks.items():
        global_event_bus.subscribe(e, cb)

    # 전용 수신 워처가 클라이언트 연결 종료(및 서버 종료 시 transport close)를
    # 즉시 감지합니다. 이벤트 큐 대기만 하고 receive를 듣지 않으면 핸들러가
    # 30초 keepalive 타임아웃이 지나기 전까지 종료를 인지하지 못해
    # graceful shutdown이 최대 ~30초 지연됩니다.
    disconnect_event = asyncio.Event()

    async def _watch_disconnect() -> None:
        try:
            while not disconnect_event.is_set():
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            disconnect_event.set()

    watcher = asyncio.create_task(_watch_disconnect())
    try:
        while True:
            get_task: asyncio.Task[dict[str, object]] = asyncio.ensure_future(queue.get())
            wait_task: asyncio.Task[bool] = asyncio.ensure_future(disconnect_event.wait())
            done: set[asyncio.Task[object]] = set()
            pending: set[asyncio.Task[object]] = {get_task, wait_task}
            try:
                done, pending = await asyncio.wait(
                    {get_task, wait_task},
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=30.0,
                )
            finally:
                for task in pending:
                    task.cancel()
            if get_task in done:
                # 대기 중이던 이벤트를 우선 전송한다. 소켓이 이미 끊겼다면
                # send 실패(WebSocketDisconnect)로 즉시 종료된다.
                event = await get_task
                try:
                    await websocket.send_json(event)
                except WebSocketDisconnect:
                    break
                continue
            if wait_task in done:
                # 클라이언트가 끊겼으므로 즉시 종료 (keepalive 타임아웃 대기 불필요)
                break
            # 30초간 큐가 비어 있고 클라이언트는 연결됨 — keepalive ping
            if not await _send_keepalive(websocket):
                break
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("WebSocket disconnected from /v1/ws/events")
    except Exception as e:
        logger.exception("WebSocket /v1/ws/events unexpected error")
    finally:
        watcher.cancel()
        for ev_name, cb in callbacks.items():
            global_event_bus.unsubscribe(ev_name, cb)
