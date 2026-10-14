"""BrowserTools — DOM 파싱 및 브라우저 검증 도구.

==============================================
SPA(React, Vue 등)의 동적 렌더링 요소를 에이전트가 직접 파싱할 수 있도록 지원.

포함 도구:
- FetchDOMTool: Playwright를 사용하여 URL에 접속하고 렌더링된 후의 DOM 텍스트를 반환합니다.

**소유권(task 16)**: 이 모듈의 전역 `_page` 는 이제 **호스트 소유자**(`browser_session_owner`)가
관리하는 세션의 캐시다. 페이지를 새로 열기 전에 반드시 `begin()`(자리 확인)을 지나므로, 세션 상한·
유휴 회수·owner 확인이 이 경로에도 똑같이 걸린다. 예전에는 이 도구만 정책 밖에 있었다.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import Callable, Protocol, cast, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .browser_session_owner import (
    BrowserSessionLimitError,
    BrowserSessionRefusedError,
    current_browser_owner,
    get_browser_session_owner,
)

logger = logging.getLogger(__name__)

# ─── 전역 브라우저 세션 (소유자 경유 캐시) ───


class _LocatorLike(Protocol):
    def inner_text(self) -> str: ...


class _PageLike(Protocol):
    def is_closed(self) -> bool: ...

    def goto(self, url: str, *, wait_until: str) -> object: ...

    def new_page(self) -> _PageLike: ...

    def click(self, selector: str) -> None: ...

    def wait_for_timeout(self, timeout: int) -> None: ...

    def fill(self, selector: str, value: str) -> None: ...

    def wait_for_selector(self, selector: str, *, timeout: int) -> object | None: ...

    def content(self) -> str: ...

    def locator(self, selector: str) -> _LocatorLike: ...

    def screenshot(self, *, path: str) -> bytes: ...

    def close(self) -> None: ...


class _ContextLike(Protocol):
    def new_page(self) -> _PageLike: ...

    def close(self) -> None: ...


class _BrowserLike(Protocol):
    def is_connected(self) -> bool: ...

    def new_page(self) -> _PageLike: ...

    def new_context(self) -> _ContextLike: ...

    def close(self) -> None: ...


class _ChromiumLike(Protocol):
    def launch(self, *, headless: bool) -> _BrowserLike: ...


class _PlaywrightLike(Protocol):
    chromium: _ChromiumLike

    def start(self) -> _PlaywrightLike: ...

    def stop(self) -> None: ...


_playwright: _PlaywrightLike | None = None
_browser: _BrowserLike | None = None
_page: _PageLike | None = None


def _browser_headless() -> bool:
    """기본은 headless. 에이전트 도구가 호출마다 사용자 화면에 창을 띄우던 동작은 `AGK_BROWSER_HEADLESS=0` 으로만."""
    raw = os.environ.get("AGK_BROWSER_HEADLESS", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def get_browser_page() -> _PageLike:
    """브라우저 페이지를 유지합니다 — **호스트 소유자를 거쳐서**(task 16).

    소유자에게 자리를 먼저 확인받는다(상한·회수·owner). 그래서 이 도구가 아무리 많이 호출돼도
    호스트 전체 세션 수는 정책 상한을 넘지 않는다.
    """
    global _playwright, _browser, _page
    owner = get_browser_session_owner()
    browser_owner = current_browser_owner()
    reservation = owner.begin(browser_owner, purpose="fetch_dom 도구")
    if reservation.is_reuse:
        reuse = reservation.reuse
        assert reuse is not None
        _page = cast(_PageLike, reuse.page)
        return _page

    if _page is not None and not _page.is_closed():
        _ = owner.commit(reservation, page=_page, close=_close_resources)
        return _page

    try:
        from playwright.sync_api import sync_playwright

        if _playwright is None:
            start_playwright = cast(Callable[[], _PlaywrightLike], sync_playwright)
            _playwright = start_playwright().start()
        playwright = _playwright
        assert playwright is not None
        if _browser is None or not _browser.is_connected():
            _browser = playwright.chromium.launch(headless=_browser_headless())
        browser = _browser
        assert browser is not None
        # 격리된 일회용 컨텍스트 — 사용자 프로필을 쓰지 않는다(그 선택은 명시 연결일 때만).
        context = browser.new_context()
        _page = context.new_page()
    except ImportError:
        owner.abort(reservation)
        raise ImportError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium",
        )
    except Exception:
        owner.abort(reservation)
        raise

    page = _page
    assert page is not None
    _ = owner.commit(reservation, page=page, close=_close_resources)
    return page


def _close_resources() -> None:
    """소유자가 부르는 닫기(전역 캐시만 정리 — 소유자 원장은 소유자가 관리한다)."""
    global _playwright, _browser, _page
    if _page:
        with suppress(Exception):
            _page.close()
        _page = None
    if _browser:
        with suppress(Exception):
            _browser.close()
        _browser = None
    if _playwright:
        with suppress(Exception):
            _playwright.stop()
        _playwright = None


def close_browser() -> None:
    """브라우저 세션을 명시적으로 닫습니다(소유자 원장에서도 빠진다)."""
    _ = get_browser_session_owner().release(current_browser_owner())
    _close_resources()


class BrowserDOMTool(BaseTool):
    """Stateful 브라우저 세션을 관리하며 자바스크립트 기반 웹 페이지와 상호작용합니다."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🌐"
    tags: list[str] = ["browser", "stateful", "qa", "test", "interact"]

    def __init__(self) -> None:
        """Initialize the BrowserDOMTool."""
        super().__init__()
        self._name: str = "fetch_dom"
        self._description: str = (
            "A stateful browser tool. It keeps the browser open across multiple tool calls. "
            "Use actions sequentially: 'goto' a URL, 'fill' forms, 'click' buttons, then 'extract' the DOM. "
            "Finally, use 'close' to clean up."
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["goto", "click", "fill", "extract", "screenshot", "close"],
                    "description": "The browser action to perform.",
                },
                "url": {
                    "type": "string",
                    "description": "URL to visit (required for 'goto').",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to click or fill, or wait for before extraction.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (required for 'fill').",
                },
                "extract_html": {
                    "type": "boolean",
                    "description": "If true during 'extract', returns raw HTML instead of text.",
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": "File path to save the screenshot (required for 'screenshot').",
                },
            },
            "required": ["action"],
        }

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        action_value = kwargs.get("action")
        action = action_value if isinstance(action_value, str) else ""
        if not action:
            return "Error: 'action' parameter is required."

        if action == "close":
            close_browser()
            return "Browser session closed successfully."

        try:
            page = get_browser_page()
        except ImportError as e:
            return f"Error: {e}"
        except BrowserSessionLimitError as e:
            # 상한은 기다리지 않고 거절한다 — 줄 세우면 결국 같은 수의 브라우저가 뜨고, 사용자는
            # 아무 대답도 못 받은 채 멈춘 것처럼 보인다.
            return f"Error: {e}"
        except BrowserSessionRefusedError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error starting browser: {e}"

        try:
            if action == "goto":
                url_value = kwargs.get("url")
                url = url_value if isinstance(url_value, str) else ""
                if not url:
                    return "Error: 'url' required for goto action."
                try:
                    # 다른 진입점과 **같은** egress 규칙(task 1·4·7 계층).
                    _ = get_browser_session_owner().validate_navigation(url)
                except Exception as e:
                    return f"Error: navigation target is not allowed for this tool: {e}"
                _ = page.goto(url, wait_until="networkidle")
                return f"Successfully navigated to {url}."

            elif action == "click":
                selector_value = kwargs.get("selector")
                selector = selector_value if isinstance(selector_value, str) else ""
                if not selector:
                    return "Error: 'selector' required for click action."
                page.click(selector)
                page.wait_for_timeout(500)
                return f"Clicked element: {selector}"

            elif action == "fill":
                selector_value = kwargs.get("selector")
                selector = selector_value if isinstance(selector_value, str) else ""
                text_value = kwargs.get("text", "")
                text = text_value if isinstance(text_value, str) else ""
                if not selector:
                    return "Error: 'selector' required for fill action."
                page.fill(selector, text)
                return f"Filled '{text}' into {selector}"

            elif action == "extract":
                selector_value = kwargs.get("selector")
                selector = selector_value if isinstance(selector_value, str) else ""
                extract_html_value = kwargs.get("extract_html", False)
                extract_html = extract_html_value if isinstance(extract_html_value, bool) else False
                if selector:
                    try:
                        _ = page.wait_for_selector(selector, timeout=5000)
                    except Exception:
                        logger.exception("Timeout waiting for selector '%s'", selector)

                if extract_html:
                    return page.content()
                else:
                    return page.locator("body").inner_text()

            elif action == "screenshot":
                path_value = kwargs.get("path", "browser_screenshot.png")
                path = path_value if isinstance(path_value, str) else "browser_screenshot.png"
                _ = page.screenshot(path=path)
                return f"Screenshot successfully saved to {path}."

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Browser error during '{action}': {str(e)}"
