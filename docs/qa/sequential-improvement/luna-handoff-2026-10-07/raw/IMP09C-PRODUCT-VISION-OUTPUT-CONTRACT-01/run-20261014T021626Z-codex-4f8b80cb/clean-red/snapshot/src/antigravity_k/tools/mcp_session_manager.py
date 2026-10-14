"""Mcp Session Manager module."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from datetime import timedelta
from importlib import import_module
from typing import Protocol, runtime_checkable

import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.message import SessionMessage

logger = logging.getLogger(__name__)


@runtime_checkable
class _LegacySseClient(Protocol):
    def __call__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5,
        sse_read_timeout: float = 300,
        auth: httpx.Auth | None = None,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[SessionMessage | Exception],
            MemoryObjectSendStream[SessionMessage],
        ]
    ]: ...


@runtime_checkable
class _LegacyStreamableHttpClient(Protocol):
    def __call__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | timedelta = 30,
        sse_read_timeout: float | timedelta = 300,
        auth: httpx.Auth | None = None,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[SessionMessage | Exception],
            MemoryObjectSendStream[SessionMessage],
            Callable[[], str | None],
        ]
    ]: ...


def _legacy_sse_client() -> _LegacySseClient:
    candidate = getattr(import_module("mcp.client.sse"), "sse_client", None)
    if not isinstance(candidate, _LegacySseClient):
        raise RuntimeError("MCP legacy SSE client is unavailable")
    return candidate


def _legacy_streamable_http_client() -> _LegacyStreamableHttpClient:
    candidate = getattr(import_module("mcp.client.streamable_http"), "streamablehttp_client", None)
    if not isinstance(candidate, _LegacyStreamableHttpClient):
        raise RuntimeError("MCP streamable HTTP client is unavailable")
    return candidate


def streamablehttp_client(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 300,
    auth: httpx.Auth | None = None,
) -> AbstractAsyncContextManager[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
        Callable[[], str | None],
    ]
]:
    return _legacy_streamable_http_client()(url, headers, timeout, sse_read_timeout, auth)


def sse_client(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    sse_read_timeout: float = 300,
    auth: httpx.Auth | None = None,
) -> AbstractAsyncContextManager[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
    ]
]:
    return _legacy_sse_client()(url, headers=headers, timeout=timeout, sse_read_timeout=sse_read_timeout, auth=auth)


class MCPSessionManager:
    """Manages MCP sessions with external plugins/servers.

    Handles the asynchronous lifecycle of MCP servers running over stdio,
    Streamable HTTP, and legacy SSE transports.
    """

    def __init__(self) -> None:
        """Initialize the MCPSessionManager."""
        self.sessions: dict[str, ClientSession] = {}
        self.exit_stacks: dict[str, AsyncExitStack] = {}
        self.session_ids: dict[str, str | None] = {}
        # 세션의 anyio 스트림은 **생성된 루프에 묶인다**. 다른 스레드/루프에서 call_tool 을
        # 돌리면 응답이 영원히 오지 않는다(실측 hang) — 그래서 소유 루프를 기록해 두고
        # 호출을 그 루프로 돌려보낸다.
        self.session_loops: dict[str, asyncio.AbstractEventLoop] = {}

    async def connect_server(
        self,
        server_name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> ClientSession:
        """Connect to an MCP server over stdio."""
        logger.info(
            "Connecting to MCP server '%s' using command: %s %s",
            server_name,
            command,
            " ".join(args),
        )

        stack = AsyncExitStack()
        self.exit_stacks[server_name] = stack

        server_params = StdioServerParameters(command=command, args=args, env=env)
        self.session_loops[server_name] = asyncio.get_running_loop()

        try:
            # Connect to the stdio server
            read, write = await stack.enter_async_context(stdio_client(server_params))

            # Create and initialize the session
            session = await stack.enter_async_context(ClientSession(read, write))
            _ = await session.initialize()

            self.sessions[server_name] = session
            logger.info("Successfully connected and initialized MCP server '%s'", server_name)
            return session

        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", server_name, e)
            await stack.aclose()
            if server_name in self.exit_stacks:
                del self.exit_stacks[server_name]
            self.session_loops.pop(server_name, None)
            raise

    async def connect_streamable_http(
        self,
        server_name: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30,
        sse_read_timeout: float = 300,
        auth: httpx.Auth | None = None,
    ) -> ClientSession:
        """Connect to an MCP server using the current Streamable HTTP transport."""
        logger.info("Connecting to MCP server '%s' over Streamable HTTP: %s", server_name, url)

        stack = AsyncExitStack()
        self.exit_stacks[server_name] = stack
        self.session_loops[server_name] = asyncio.get_running_loop()

        try:
            read, write, get_session_id = await stack.enter_async_context(
                streamablehttp_client(
                    url,
                    headers=headers,
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    auth=auth,
                ),
            )

            session = await stack.enter_async_context(ClientSession(read, write))
            _ = await session.initialize()

            self.sessions[server_name] = session
            self.session_ids[server_name] = get_session_id()
            logger.info(
                "Successfully connected and initialized MCP server '%s' over Streamable HTTP",
                server_name,
            )
            return session

        except Exception as e:
            logger.error(
                "Failed to connect to MCP server '%s' over Streamable HTTP: %s",
                server_name,
                e,
            )
            await stack.aclose()
            if server_name in self.exit_stacks:
                del self.exit_stacks[server_name]
            if server_name in self.session_ids:
                del self.session_ids[server_name]
            self.session_loops.pop(server_name, None)
            raise

    async def connect_sse(
        self,
        server_name: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 5,
        sse_read_timeout: float = 300,
        auth: httpx.Auth | None = None,
    ) -> ClientSession:
        """Connect to an MCP server using the legacy HTTP+SSE transport.

        Prefer connect_streamable_http for new remote servers.
        """
        logger.info("Connecting to MCP server '%s' over legacy SSE: %s", server_name, url)

        stack = AsyncExitStack()
        self.exit_stacks[server_name] = stack
        self.session_loops[server_name] = asyncio.get_running_loop()

        try:
            read, write = await stack.enter_async_context(
                sse_client(
                    url,
                    headers=headers,
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    auth=auth,
                ),
            )

            session = await stack.enter_async_context(ClientSession(read, write))
            _ = await session.initialize()

            self.sessions[server_name] = session
            logger.info(
                "Successfully connected and initialized MCP server '%s' over SSE",
                server_name,
            )
            return session

        except Exception as e:
            logger.error("Failed to connect to MCP server '%s' over SSE: %s", server_name, e)
            await stack.aclose()
            if server_name in self.exit_stacks:
                del self.exit_stacks[server_name]
            self.session_loops.pop(server_name, None)
            raise

    async def disconnect_server(self, server_name: str) -> None:
        """Disconnects from an MCP server and cleans up resources."""
        if server_name in self.exit_stacks:
            logger.info("Disconnecting MCP server '%s'", server_name)
            await self.exit_stacks[server_name].aclose()
            del self.exit_stacks[server_name]

        if server_name in self.sessions:
            del self.sessions[server_name]

        if server_name in self.session_ids:
            del self.session_ids[server_name]

        self.session_loops.pop(server_name, None)

    def get_session(self, server_name: str) -> ClientSession | None:
        """Retrieve session.

        Args:
            server_name (str): str server name.

        Returns:
            ClientSession | None: The clientsession | none result.

        """
        return self.sessions.get(server_name)

    async def cleanup(self) -> None:
        """Disconnects all active MCP servers."""
        servers = list(self.exit_stacks.keys())
        for server in servers:
            await self.disconnect_server(server)
