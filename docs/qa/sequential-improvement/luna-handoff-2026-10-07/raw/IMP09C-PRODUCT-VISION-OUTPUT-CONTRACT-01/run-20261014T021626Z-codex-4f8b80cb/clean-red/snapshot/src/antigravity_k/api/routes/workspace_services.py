"""작업공간 서비스 레지스트리와 HTTP/WebSocket 프록시 API."""

from __future__ import annotations

from typing import ClassVar

import httpx
from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request, WebSocket, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from antigravity_k.api.routes.session_state import close_unauthorized_ws
from antigravity_k.api.routes.workspace_websocket import relay_workspace_websocket
from antigravity_k.engine.workspace_service_registry import (
    InvalidServiceTargetError,
    ServiceConflictError,
    ServiceNotFoundError,
    ServiceRecord,
    ServiceState,
    WorkspaceServiceRegistry,
    validate_service_target,
)
from antigravity_k.engine.workspace_service_runtime import (
    ServiceHealth,
    ServiceProcessError,
    WorkspaceServiceRuntime,
)

router = APIRouter(prefix="/api/workspace/services", tags=["workspaces"])
_registry = WorkspaceServiceRegistry()
_runtime = WorkspaceServiceRuntime(_registry)
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ServiceRegistration(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    service: str = Field(min_length=1, max_length=80)
    branch: str = Field(min_length=1, max_length=160)
    project: str = Field(min_length=1, max_length=120)
    host: str = Field(default="127.0.0.1", min_length=1, max_length=80)
    port: int = Field(ge=1, le=65535)
    status: ServiceState = "ready"
    command: tuple[str, ...] | None = Field(default=None, min_length=1)
    health_path: str = Field(default="/health", max_length=200)

    @field_validator("service", "branch", "project", "host")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("host")
    @classmethod
    def local_target_only(cls, value: str) -> str:
        try:
            return validate_service_target(value)
        except InvalidServiceTargetError as exc:
            raise ValueError(str(exc)) from exc


class ServiceStateUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    status: ServiceState


class ServiceResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    service: str
    branch: str
    project: str
    host: str
    port: int
    hostname: str
    status: ServiceState
    http_url: str
    websocket_url: str
    health_url: str
    managed: bool


class ServiceHealthResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    hostname: str
    status: ServiceState
    managed: bool
    process_running: bool
    process_id: int | None


def get_service_registry() -> WorkspaceServiceRegistry:
    return _registry


def get_service_runtime() -> WorkspaceServiceRuntime:
    return _runtime


def _response(record: ServiceRecord) -> ServiceResponse:
    http_url = f"http://{record.hostname}/api/workspace/services/{record.hostname}/proxy"
    return ServiceResponse(
        service=record.service,
        branch=record.branch,
        project=record.project,
        host=record.host,
        port=record.port,
        hostname=record.hostname,
        status=record.status,
        http_url=http_url,
        websocket_url=f"ws://{record.hostname}/api/workspace/services/{record.hostname}/ws",
        health_url=f"{http_url}{record.health_path}",
        managed=record.command is not None,
    )


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def register_service(request: ServiceRegistration) -> ServiceResponse:
    try:
        record = _registry.register(
            service=request.service,
            branch=request.branch,
            project=request.project,
            host=request.host,
            port=request.port,
            status=request.status,
            command=request.command,
            health_path=request.health_path,
        )
    except (ServiceConflictError, InvalidServiceTargetError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _response(record)


@router.get("", response_model=list[ServiceResponse])
async def list_services() -> list[ServiceResponse]:
    return [_response(record) for record in _registry.list()]


@router.patch("/{hostname}", response_model=ServiceResponse)
async def update_service(hostname: str, request: ServiceStateUpdate) -> ServiceResponse:
    try:
        record = _registry.set_status(hostname, request.status)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(record)


@router.post("/{hostname}/start", response_model=ServiceResponse)
async def start_service(hostname: str) -> ServiceResponse:
    try:
        record = await to_thread.run_sync(_runtime.start, hostname)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ServiceProcessError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _response(record)


@router.post("/{hostname}/stop", response_model=ServiceResponse)
async def stop_service(hostname: str) -> ServiceResponse:
    try:
        record = await to_thread.run_sync(_runtime.stop, hostname)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _response(record)


@router.get("/{hostname}/health", response_model=ServiceHealthResponse)
async def health_service(hostname: str) -> ServiceHealthResponse:
    try:
        health: ServiceHealth = await to_thread.run_sync(_runtime.health, hostname)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ServiceHealthResponse(
        hostname=health.hostname,
        status=health.status,
        managed=health.managed,
        process_running=health.process_running,
        process_id=health.process_id,
    )


@router.delete("/{hostname}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_service(hostname: str) -> None:
    try:
        _ = await to_thread.run_sync(_runtime.stop, hostname)
        _registry.remove(hostname)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _require_ready(hostname: str) -> ServiceRecord:
    try:
        record = _registry.get(hostname)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if record.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"service is {record.status}")
    return record


def _forward_request_headers(request: Request, record: ServiceRecord) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP and key.lower() not in {"host", "content-length"}
    }
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    headers["x-workspace-service"] = record.service
    headers["x-workspace-branch"] = record.branch
    headers["x-workspace-project"] = record.project
    return headers


def _forward_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in _HOP_BY_HOP and key.lower() not in {"content-length"}
    }


async def _close_proxy_resources(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


@router.api_route(
    "/{hostname}/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/{hostname}/proxy",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_http(hostname: str, request: Request, path: str = "") -> StreamingResponse:
    record = _require_ready(hostname)
    target = f"{record.base_url}/{path.lstrip('/')}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    upstream_request = client.build_request(
        request.method,
        target,
        headers=_forward_request_headers(request, record),
        content=request.stream(),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="workspace service unavailable") from exc
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=_forward_response_headers(upstream),
        background=BackgroundTask(_close_proxy_resources, upstream, client),
    )


async def _proxy_websocket(websocket: WebSocket, hostname: str, path: str) -> None:
    if await close_unauthorized_ws(websocket):
        return
    try:
        record = _require_ready(hostname)
    except HTTPException:
        await websocket.close(code=1008, reason="workspace service unavailable")
        return
    await relay_workspace_websocket(websocket, record, path)


@router.websocket("/{hostname}/ws")
async def proxy_websocket(hostname: str, websocket: WebSocket) -> None:
    await _proxy_websocket(websocket, hostname, "")


@router.websocket("/{hostname}/ws/{path:path}")
async def proxy_websocket_path(hostname: str, path: str, websocket: WebSocket) -> None:
    await _proxy_websocket(websocket, hostname, path)


__all__ = ["get_service_registry", "get_service_runtime", "router"]
