import logging
from urllib.parse import urlencode

import anyio
from anyio.abc import TaskGroup
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from antigravity_k.engine.workspace_service_registry import ServiceRecord

logger = logging.getLogger(__name__)


async def _client_to_upstream(websocket: WebSocket, upstream: ClientConnection, task_group: TaskGroup) -> None:
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            text_message = message.get("text")
            raw_bytes = message.get("bytes")
            bytes_message: bytes | None = raw_bytes if isinstance(raw_bytes, bytes) else None
            if isinstance(text_message, str):
                await upstream.send(text_message)
            elif bytes_message is not None:
                await upstream.send(bytes_message)
    except WebSocketDisconnect:
        return
    finally:
        task_group.cancel_scope.cancel()


async def _upstream_to_client(websocket: WebSocket, upstream: ClientConnection, task_group: TaskGroup) -> None:
    try:
        async for message in upstream:
            if isinstance(message, str):
                await websocket.send_text(message)
            else:
                await websocket.send_bytes(message)
    except WebSocketDisconnect:
        return
    finally:
        task_group.cancel_scope.cancel()


def _websocket_headers(websocket: WebSocket, record: ServiceRecord) -> dict[str, str]:
    return {
        "x-forwarded-host": websocket.headers.get("host", ""),
        "x-forwarded-proto": "ws",
        "x-workspace-service": record.service,
        "x-workspace-branch": record.branch,
        "x-workspace-project": record.project,
    }


async def relay_workspace_websocket(websocket: WebSocket, record: ServiceRecord, path: str) -> None:
    target = f"{record.websocket_base_url}/{path.lstrip('/')}"
    query_string = urlencode(
        [
            (key, value)
            for key, value in websocket.query_params.multi_items()
            if key not in {"token", "pin", "ticket"}  # SEC-02/03: credential 쿼리는 upstream에 전달 금지
        ]
    )
    if query_string:
        target = f"{target}?{query_string}"
    try:
        async with connect(target, additional_headers=_websocket_headers(websocket, record)) as upstream:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(_client_to_upstream, websocket, upstream, task_group)
                task_group.start_soon(_upstream_to_client, websocket, upstream, task_group)
    except* (ConnectionClosed, InvalidStatus, OSError):
        logger.warning("Workspace WebSocket upstream unavailable", extra={"service": record.service})
        if websocket.client_state == websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="workspace service unavailable")
    else:
        if websocket.client_state == websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=1000)
