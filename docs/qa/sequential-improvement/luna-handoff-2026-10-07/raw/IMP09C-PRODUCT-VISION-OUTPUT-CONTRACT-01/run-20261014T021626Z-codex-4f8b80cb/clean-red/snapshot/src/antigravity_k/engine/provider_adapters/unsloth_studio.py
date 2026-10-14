from __future__ import annotations

import json
import logging
from typing import final, override

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, TextContent
from pydantic import JsonValue, TypeAdapter

from antigravity_k.engine.provider_adapters.unsloth_studio_contracts import (
    UNSLOTH_STUDIO_READ_TOOLS,
    UnslothStudioPermissionDenied,
    UnslothStudioReadTool,
    UnslothStudioSettings,
    UnslothStudioSnapshot,
    UnslothStudioToolResult,
)
from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from antigravity_k.tools.mcp_session_manager import MCPSessionManager
from antigravity_k.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_SERVER_NAME = "unsloth-studio"
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_CONNECTION_ERRORS = (
    httpx.HTTPError,
    McpError,
    anyio.BrokenResourceError,
    anyio.ClosedResourceError,
    anyio.EndOfStream,
    OSError,
    TimeoutError,
    RuntimeError,
    ExceptionGroup,
)


@final
class _ReadToolDescriptor(BaseTool):
    category: ToolCategory = ToolCategory.DATA
    render_in: RenderIn = RenderIn.BACKGROUND
    risk_level: RiskLevel = RiskLevel.SAFE
    tags: list[str] = ["unsloth", "studio", "mcp", "read-only"]
    _tool: UnslothStudioReadTool

    def __init__(self, tool: UnslothStudioReadTool) -> None:
        self._tool = tool

    @property
    @override
    def name(self) -> str:
        return self._tool.value

    @property
    @override
    def description(self) -> str:
        return "Read local Unsloth Studio status without changing server state."

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return {"type": "object", "additionalProperties": False}

    @override
    def execute(self, **kwargs: object) -> JsonValue:
        raise _DescriptorExecutionError(
            "Unsloth Studio descriptors cannot execute outside the guarded adapter.",
        )


class _DescriptorExecutionError(RuntimeError):
    pass


def _arguments_for(tool: UnslothStudioReadTool) -> dict[str, JsonValue]:
    if tool is UnslothStudioReadTool.TRAINING_RUNS:
        return {"limit": 50, "offset": 0}
    return {}


def _payload_from(result: CallToolResult) -> JsonValue | None:
    if result.structuredContent is not None:
        return _JSON_VALUE.validate_python(result.structuredContent)
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    if not texts:
        return None
    if len(texts) == 1:
        try:
            return _JSON_VALUE.validate_python(json.loads(texts[0]))
        except json.JSONDecodeError:
            return texts[0]
    return _JSON_VALUE.validate_python(texts)


@final
class UnslothStudioService:
    _settings: UnslothStudioSettings
    _manager: MCPSessionManager
    _registry: ToolRegistry

    def __init__(
        self,
        *,
        settings: UnslothStudioSettings,
        manager: MCPSessionManager,
        registry: ToolRegistry,
    ) -> None:
        self._settings = settings
        self._manager = manager
        self._registry = registry

    async def snapshot(self) -> UnslothStudioSnapshot:
        if not self._settings.configured:
            return self._snapshot(available=False, error="token_not_configured")

        self._authorize_all()
        connected = False
        try:
            token = self._settings.token
            if token is None:
                return self._snapshot(available=False, error="token_not_configured")
            session = await self._manager.connect_streamable_http(
                _SERVER_NAME,
                self._settings.endpoint,
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                timeout=self._settings.timeout_seconds,
                sse_read_timeout=self._settings.read_timeout_seconds,
            )
            connected = True
            advertised = {tool.name for tool in (await session.list_tools()).tools}
            available_tools = tuple(tool for tool in UNSLOTH_STUDIO_READ_TOOLS if tool.value in advertised)
            results: list[UnslothStudioToolResult] = []
            for tool in UNSLOTH_STUDIO_READ_TOOLS:
                if tool not in available_tools:
                    results.append(UnslothStudioToolResult(tool=tool, ok=False, error="not_advertised"))
                    continue
                results.append(await self._call(session, tool))
            return self._snapshot(available=True, available_tools=available_tools, results=tuple(results))
        except _CONNECTION_ERRORS:
            logger.warning("Unsloth Studio MCP snapshot failed at %s", self._settings.endpoint, exc_info=True)
            return self._snapshot(available=False, error="connection_failed")
        finally:
            if connected:
                try:
                    await self._manager.disconnect_server(_SERVER_NAME)
                except _CONNECTION_ERRORS:
                    logger.warning("Unsloth Studio MCP disconnect failed", exc_info=True)

    def _authorize_all(self) -> None:
        for tool in UNSLOTH_STUDIO_READ_TOOLS:
            decision = self._registry.authorize_tool(
                _ReadToolDescriptor(tool),
                _arguments_for(tool),
                objective="Read local Unsloth Studio status.",
            )
            if not decision.allows_execution:
                raise UnslothStudioPermissionDenied(tool=tool, source=decision.source)

    async def _call(self, session: ClientSession, tool: UnslothStudioReadTool) -> UnslothStudioToolResult:
        try:
            result = await session.call_tool(tool.value, arguments=_arguments_for(tool))
        except _CONNECTION_ERRORS:
            logger.warning("Unsloth Studio MCP read failed: %s", tool.value, exc_info=True)
            return UnslothStudioToolResult(tool=tool, ok=False, error="call_failed")
        if result.isError:
            return UnslothStudioToolResult(tool=tool, ok=False, error="remote_tool_error")
        return UnslothStudioToolResult(tool=tool, ok=True, data=_payload_from(result))

    def _snapshot(
        self,
        *,
        available: bool,
        available_tools: tuple[UnslothStudioReadTool, ...] = (),
        results: tuple[UnslothStudioToolResult, ...] = (),
        error: str | None = None,
    ) -> UnslothStudioSnapshot:
        return UnslothStudioSnapshot(
            configured=self._settings.configured,
            available=available,
            endpoint=self._settings.endpoint,
            allowed_tools=UNSLOTH_STUDIO_READ_TOOLS,
            available_tools=available_tools,
            results=results,
            error=error,
        )
