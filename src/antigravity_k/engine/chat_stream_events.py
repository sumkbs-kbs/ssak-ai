from contextvars import ContextVar, Token
from typing import Final


class ProgressChunk(str):
    pass


class FinalChunk(str):
    pass


_CHAT_STREAM_EVENTS: Final[ContextVar[bool]] = ContextVar("chat_stream_events", default=False)


def set_chat_stream_events(enabled: bool) -> Token[bool]:
    return _CHAT_STREAM_EVENTS.set(enabled)


def reset_chat_stream_events(token: Token[bool]) -> None:
    _CHAT_STREAM_EVENTS.reset(token)


def chat_stream_events_enabled() -> bool:
    return _CHAT_STREAM_EVENTS.get()
