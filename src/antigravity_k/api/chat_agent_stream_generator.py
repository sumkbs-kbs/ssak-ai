"""Drive and close synchronous agent streams inside one private execution context."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Iterator, Mapping, Sequence
from contextvars import Context, copy_context
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol, override

from anyio import CancelScope
from anyio.to_thread import run_sync
from starlette.responses import StreamingResponse
from starlette.types import Send

from antigravity_k.engine.chat_stream_events import reset_chat_stream_events, set_chat_stream_events
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy


class StreamingRuntime(Protocol):
    def stream(self, messages: Sequence[Mapping[str, str]], target_model: str) -> Iterator[str]: ...


class AgentStreamingResponse(StreamingResponse):
    def __init__(self, content: AsyncGenerator[str, None], *, media_type: str) -> None:
        super().__init__(content, media_type=media_type)
        self._agent_body: AsyncGenerator[str, None] = content

    @override
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with CancelScope(shield=True):
                await self._agent_body.aclose()


def _scoped_stream(
    runtime: StreamingRuntime,
    messages: Sequence[Mapping[str, str]],
    target_model: str,
    policy: ToolPolicy,
) -> Generator[str, None, None]:
    policy_token = set_tool_policy(policy)
    event_token = set_chat_stream_events(True)
    try:
        yield from runtime.stream(messages, target_model=target_model)
    finally:
        reset_chat_stream_events(event_token)
        reset_tool_policy(policy_token)


@dataclass(frozen=True, slots=True)
class _ContextStream:
    context: Context
    iterator: Generator[str, None, None]
    lock: Lock = field(default_factory=Lock)

    def _next(self) -> tuple[bool, str | None]:
        try:
            return False, next(self.iterator)
        except StopIteration:
            return True, None

    def pull(self) -> tuple[bool, str | None]:
        with self.lock:
            return self.context.run(self._next)

    def close(self) -> None:
        with self.lock:
            self.context.run(self.iterator.close)


async def contextual_agent_stream(
    runtime: StreamingRuntime,
    messages: Sequence[Mapping[str, str]],
    target_model: str,
    policy: ToolPolicy,
) -> AsyncGenerator[str, None]:
    stream = _ContextStream(copy_context(), _scoped_stream(runtime, messages, target_model, policy))
    try:
        while True:
            done, chunk = await run_sync(stream.pull)
            if done:
                return
            if chunk is not None:
                yield chunk
    finally:
        with CancelScope(shield=True):
            await run_sync(stream.close)
