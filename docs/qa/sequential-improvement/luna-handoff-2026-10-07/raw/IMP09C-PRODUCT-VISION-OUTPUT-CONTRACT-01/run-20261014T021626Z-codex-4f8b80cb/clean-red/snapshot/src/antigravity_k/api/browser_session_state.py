from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, final

from antigravity_k.tools.browser_session_owner import BrowserSessionLimitError

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


BrowserConsoleEntry = dict[str, str]

#: 예외는 **한 곳**(소유자 모듈)에만 있다 — 여기서는 기존 import 경로를 위해 재수출한다.
__all__ = [
    "BrowserConsoleEntry",
    "BrowserSessionLimitError",
    "BrowserSessionRegistry",
    "BrowserSessionState",
]


@final
class BrowserSessionState:
    """Mutable owner of one optional Playwright browser session."""

    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.console_errors: list[BrowserConsoleEntry] = []
        self.console_logs: list[BrowserConsoleEntry] = []


class BrowserSessionRegistry:
    """Owns isolated browser states with a bounded number of custom sessions."""

    def __init__(self, max_sessions: int = 2, default_state: BrowserSessionState | None = None) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        self._max_sessions: int = max_sessions
        self._sessions: OrderedDict[str, BrowserSessionState] = OrderedDict()
        self._sessions["default"] = default_state or BrowserSessionState()

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    @max_sessions.setter
    def max_sessions(self, value: int) -> None:
        """상한의 권위는 소유자 정책(`browser_session_owner`)이다 — 여기는 그 값을 받아 쓴다."""
        if value < 1:
            raise ValueError("max_sessions must be positive")
        self._max_sessions = value

    def get(self, session_id: str) -> BrowserSessionState:
        """Return a session state, creating it unless the custom-session cap is reached."""
        normalized_id = session_id.strip() or "default"
        state = self._sessions.get(normalized_id)
        if state is not None:
            self._sessions.move_to_end(normalized_id)
            return state
        custom_count = len(self._sessions) - 1
        if custom_count >= self._max_sessions:
            raise BrowserSessionLimitError("Too many active browser sessions")
        state = BrowserSessionState()
        self._sessions[normalized_id] = state
        return state

    def discard(self, session_id: str) -> BrowserSessionState | None:
        """Remove a custom session and return its state; keep the legacy default state."""
        normalized_id = session_id.strip() or "default"
        if normalized_id == "default":
            return None
        return self._sessions.pop(normalized_id, None)
