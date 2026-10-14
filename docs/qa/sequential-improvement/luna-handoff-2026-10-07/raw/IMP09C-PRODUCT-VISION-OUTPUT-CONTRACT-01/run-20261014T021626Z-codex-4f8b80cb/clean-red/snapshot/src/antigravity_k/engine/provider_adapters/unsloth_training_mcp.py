from __future__ import annotations

import logging
from dataclasses import dataclass

import anyio
import httpx
from mcp.shared.exceptions import McpError
from pydantic import ValidationError

from antigravity_k.engine.provider_adapters.unsloth_studio_contracts import UnslothStudioSettings
from antigravity_k.engine.provider_adapters.unsloth_training_contracts import (
    UnslothRemoteTrainingJob,
    UnslothTrainingMCPConfig,
)
from antigravity_k.tools.mcp_session_manager import MCPSessionManager

logger = logging.getLogger(__name__)

_SERVER_NAME = "unsloth-studio-training"
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


@dataclass(frozen=True, slots=True)
class RemoteTrainingStarted:
    job: UnslothRemoteTrainingJob


@dataclass(frozen=True, slots=True)
class RemoteTrainingRejected:
    reason: str


@dataclass(frozen=True, slots=True)
class RemoteTrainingUncertain:
    reason: str


type RemoteTrainingResult = RemoteTrainingStarted | RemoteTrainingRejected | RemoteTrainingUncertain


class UnslothTrainingMCPClient:
    def __init__(self, settings: UnslothStudioSettings, manager: MCPSessionManager) -> None:
        self._settings: UnslothStudioSettings = settings
        self._manager: MCPSessionManager = manager

    async def start(self, config: UnslothTrainingMCPConfig) -> RemoteTrainingResult:
        token = self._settings.token
        if token is None:
            return RemoteTrainingRejected(reason="token_not_configured")

        connected = False
        call_started = False
        try:
            session = await self._manager.connect_streamable_http(
                _SERVER_NAME,
                self._settings.endpoint,
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                timeout=self._settings.timeout_seconds,
                sse_read_timeout=self._settings.read_timeout_seconds,
            )
            connected = True
            advertised = {tool.name for tool in (await session.list_tools()).tools}
            if "start_training" not in advertised:
                return RemoteTrainingRejected(reason="tool_not_advertised")
            call_started = True
            result = await session.call_tool(
                "start_training",
                arguments={"config": config.model_dump(mode="json", exclude_none=True)},
            )
            if result.isError:
                return RemoteTrainingRejected(reason="remote_tool_error")
            if result.structuredContent is None:
                return RemoteTrainingUncertain(reason="missing_structured_content")
            try:
                job = UnslothRemoteTrainingJob.model_validate(result.structuredContent)
            except ValidationError:
                return RemoteTrainingUncertain(reason="invalid_remote_response")
            match job.status:
                case "pending" | "queued":
                    return RemoteTrainingStarted(job=job)
                case "error":
                    return RemoteTrainingRejected(reason=job.error_code or "remote_rejected")
        except _CONNECTION_ERRORS:
            logger.warning("Unsloth training MCP start failed", exc_info=True)
            if call_started:
                return RemoteTrainingUncertain(reason="connection_lost_after_call")
            return RemoteTrainingRejected(reason="connection_failed_before_call")
        finally:
            if connected:
                try:
                    await self._manager.disconnect_server(_SERVER_NAME)
                except _CONNECTION_ERRORS:
                    logger.warning("Unsloth training MCP disconnect failed", exc_info=True)
