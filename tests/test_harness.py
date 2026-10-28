"""Tests for harness — TestHarness, FeedbackCollector, URL derivation, headers.

Extends existing test_harness_config.py with unit tests for the main
TestHarness class methods and FeedbackCollector.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from email.message import Message
from typing import Final, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from antigravity_k.engine.harness import (
    FeedbackCollector,
    HarnessReport,
    TestHarness,
    TestIntent,
    TestResult,
    TestStatus,
)


def test_harness_domain_types_are_not_pytest_test_classes():
    assert all(
        getattr(domain_type, "__test__", True) is False
        for domain_type in (TestHarness, TestIntent, TestResult, TestStatus)
    )


@pytest.fixture(autouse=True)
def _allow_fake_test_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(url: str) -> tuple[str, tuple[str, ...]] | None:
        if "://test" in url:
            return url, ("203.0.113.1",)
        return None

    monkeypatch.setattr("antigravity_k.tools.egress_policy.resolve_public_http_url_sync", resolve)


_AUTOUSE_FIXTURE: Final = _allow_fake_test_hostname


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class _MockPage:
    """A simple page mock for Playwright method testing.

    All async methods are AsyncMocks by default. Override any method by
    passing it as a keyword argument to the constructor.
    """

    _ASYNC_METHODS: Final = (
        "goto",
        "title",
        "query_selector",
        "query_selector_all",
        "fill",
        "press",
        "screenshot",
        "set_viewport_size",
        "evaluate",
        "wait_for_selector",
        "wait_for_function",
        "add_init_script",
    )

    goto: AsyncMock
    wait_for_selector: AsyncMock
    context: MagicMock
    locator: MagicMock

    def __init__(self, **overrides: object) -> None:
        for method in self._ASYNC_METHODS:
            setattr(self, method, AsyncMock(return_value=None))
        self.goto = AsyncMock(return_value=None)
        self.wait_for_selector = AsyncMock(return_value=None)
        # context
        context: MagicMock = MagicMock()
        self.context = context
        setattr(context, "add_cookies", AsyncMock(return_value=None))
        # locator
        loc = MagicMock()
        loc.count = AsyncMock(return_value=3)
        self.locator = MagicMock(return_value=loc)
        # Apply overrides
        for key, val in overrides.items():
            setattr(self, key, val)


class _MockHttpResponse:
    def __init__(self, body: bytes) -> None:
        self._body: bytes = body

    def __enter__(self) -> _MockHttpResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self._body


def _request_headers(harness: TestHarness, extra: dict[str, object] | None = None) -> dict[str, object]:
    method = cast(Callable[[dict[str, object] | None], dict[str, object]], getattr(harness, "_request_headers"))
    return method(extra)


def _run_api_test_sync(harness: TestHarness, intent: TestIntent) -> TestResult:
    method = cast(Callable[[TestIntent], TestResult], getattr(harness, "_run_api_test_sync"))
    return method(intent)


async def _run_api_test(harness: TestHarness, intent: TestIntent) -> TestResult:
    method = cast(Callable[[TestIntent], Awaitable[TestResult]], getattr(harness, "_run_api_test"))
    return await method(intent)


async def _goto_dashboard(harness: TestHarness, page: object, timeout_ms: int = 15000) -> None:
    method = cast(Callable[[object, int], Awaitable[None]], getattr(harness, "_goto_dashboard"))
    await method(page, timeout_ms)


async def _test_dashboard_load(harness: TestHarness, page: object, intent: TestIntent) -> TestResult:
    method = cast(Callable[[object, TestIntent], Awaitable[TestResult]], getattr(harness, "_test_dashboard_load"))
    return await method(page, intent)


async def _test_chat_send(harness: TestHarness, page: object, intent: TestIntent) -> TestResult:
    method = cast(Callable[[object, TestIntent], Awaitable[TestResult]], getattr(harness, "_test_chat_send"))
    return await method(page, intent)


async def _test_file_explorer(harness: TestHarness, page: object, intent: TestIntent) -> TestResult:
    method = cast(Callable[[object, TestIntent], Awaitable[TestResult]], getattr(harness, "_test_file_explorer"))
    return await method(page, intent)


async def _test_terminal_ws(harness: TestHarness, intent: TestIntent) -> TestResult:
    method = cast(Callable[[TestIntent], Awaitable[TestResult]], getattr(harness, "_test_terminal_ws"))
    return await method(intent)


async def _test_autonomous_qa_dry(harness: TestHarness, page: object, intent: TestIntent) -> TestResult:
    method = cast(Callable[[object, TestIntent], Awaitable[TestResult]], getattr(harness, "_test_autonomous_qa_dry"))
    return await method(page, intent)


async def _test_responsive(harness: TestHarness, page: object, intent: TestIntent) -> TestResult:
    method = cast(Callable[[object, TestIntent], Awaitable[TestResult]], getattr(harness, "_test_responsive"))
    return await method(page, intent)


async def _run_browser_tests(harness: TestHarness, intents: list[TestIntent]) -> list[TestResult]:
    method = cast(Callable[[list[TestIntent]], Awaitable[list[TestResult]]], getattr(harness, "_run_browser_tests"))
    return await method(intents)


# ---------------------------------------------------------------------------
# FeedbackCollector
# ---------------------------------------------------------------------------


class TestFeedbackCollector:
    def test_collect_all_pass(self):
        fc = FeedbackCollector()
        report = HarnessReport()
        report.passed = 5
        report.failed = 0
        report.healed = 0
        report.total = 5
        report.results = [TestResult("t1", TestStatus.PASSED, 100, "ok")]
        msg = fc.collect(report)
        assert "\u2705" in msg
        assert "5/5" in msg or "5\uac1c" in msg
        assert len(fc.history) == 1

    def test_collect_with_failures(self):
        fc = FeedbackCollector()
        report = HarnessReport()
        report.passed = 3
        report.failed = 2
        report.total = 5
        report.results = [
            TestResult("t1", TestStatus.PASSED, 100, "ok"),
            TestResult("t2", TestStatus.FAILED, 200, "connection error"),
            TestResult("t3", TestStatus.FAILED, 300, "timeout"),
        ]
        msg = fc.collect(report)
        assert "\u26a0\ufe0f" in msg
        assert "connection error" in msg
        assert "timeout" in msg

    def test_get_trend_no_data(self):
        fc = FeedbackCollector()
        trend = fc.get_trend()
        assert trend["trend"] == "no_data"

    def test_get_trend_with_data(self):
        fc = FeedbackCollector()
        for _ in range(3):
            r = HarnessReport()
            r.passed = 4
            r.failed = 1
            r.total = 5
            _ = fc.collect(r)
        trend = fc.get_trend()
        assert trend["total_runs"] == 3
        pass_rates = cast(list[float], trend["recent_pass_rates"])
        assert len(pass_rates) == 3


# ---------------------------------------------------------------------------
# TestHarness — init & URL derivation
# ---------------------------------------------------------------------------


class TestHarnessInit:
    def test_default_init(self):
        harness = TestHarness()
        assert harness.base_url == "http://localhost:8000"
        assert harness.dashboard_url == "http://localhost:5173"
        assert "ws://" in harness.ws_url
        assert harness.access_pin is not None

    def test_custom_urls(self):
        harness = TestHarness(
            base_url="http://api.test:8080",
            dashboard_url="http://dashboard.test:3000",
        )
        assert harness.base_url == "http://api.test:8080"
        assert harness.dashboard_url == "http://dashboard.test:3000"

    def test_ws_url_derives_from_base(self):
        harness = TestHarness(base_url="http://api.test:8080")
        assert harness.ws_url == "ws://api.test:8080/ws/terminal"

    def test_ws_url_https_uses_wss(self):
        harness = TestHarness(base_url="https://api.test:443")
        assert harness.ws_url == "wss://api.test:443/ws/terminal"


class TestRequestHeaders:
    def test_without_access_pin_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGK_HARNESS_ACCESS_PIN", raising=False)
        harness = TestHarness()
        harness.access_pin = ""
        harness._token = None
        assert _request_headers(harness) == {}

    def test_with_token_sends_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SEC-02: PIN 헤더는 사라지고 토큰 교환 후 Bearer만 전송된다."""
        monkeypatch.setenv("AGK_HARNESS_ACCESS_PIN", "test-pin")
        harness = TestHarness()
        harness._token = "jwt-token"
        headers = _request_headers(harness)
        assert headers["Authorization"] == "Bearer jwt-token"
        assert "X-Access-Pin" not in headers, "raw PIN 헤더가 남아 있다 — SEC-02 위반"

    def test_with_extra_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGK_HARNESS_ACCESS_PIN", "pin123")
        harness = TestHarness()
        harness._token = "jwt-token"
        headers = _request_headers(harness, {"Content-Type": "application/json"})
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer jwt-token"
        assert "X-Access-Pin" not in headers


class TestDefaultIntents:
    def test_has_required_intents(self):
        intents = TestHarness.DEFAULT_INTENTS
        ids = {i.id for i in intents}
        assert "health_api" in ids
        assert "models_api" in ids
        assert "dashboard_load" in ids
        assert "chat_send" in ids
        assert "file_explorer" in ids
        assert "terminal_ws" in ids
        assert "vision_analyze" in ids
        assert "external_brain_list" in ids
        assert "autonomous_qa_dry" in ids
        assert "responsive_check" in ids

    def test_intent_priorities(self):
        for intent in TestHarness.DEFAULT_INTENTS:
            assert intent.priority in (1, 2, 3)
            assert intent.category in ("api", "ui", "integration")


class TestAddIntent:
    def test_add_intent_appends(self):
        harness = TestHarness()
        original_count = len(harness.intents)
        new_intent = TestIntent(id="custom_test", intent="Custom test", category="api", priority=3)
        harness.add_intent(new_intent)
        assert len(harness.intents) == original_count + 1

    def test_get_latest_report_empty(self):
        harness = TestHarness()
        assert harness.get_latest_report() is None


# ---------------------------------------------------------------------------
# TestHarness — _run_api_test_sync (mocked urllib)
# ---------------------------------------------------------------------------


class TestRunApiTestSync:
    def test_health_api_ok(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="health_api", intent="health", category="api", priority=1)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"status": "ok"}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.PASSED
            assert "Health OK" in result.message

    def test_health_api_unexpected(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="health_api", intent="health", category="api", priority=1)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"status": "error"}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.FAILED

    def test_models_api_ok(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="models_api", intent="models", category="api", priority=1)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"data": [{"id": "gpt-4"}]}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.PASSED
            assert "1 models" in result.message

    def test_models_api_no_models(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="models_api", intent="models", category="api", priority=1)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"data": []}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.FAILED
            assert "No models" in result.message

    def test_vision_analyze_http_400(self):
        import urllib.error

        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="vision_analyze", intent="vision", category="api", priority=2)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "http://test/api",
                400,
                "Bad Request",
                Message(),
                None,
            )

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.PASSED
            assert "reachable" in result.message

    def test_vision_analyze_http_500_no_screenshot(self):
        import io
        import urllib.error

        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="vision_analyze", intent="vision", category="api", priority=2)

        body = b'{"error": "No screenshot provided"}'
        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "http://test/api",
                500,
                "Internal Server Error",
                Message(),
                io.BytesIO(body),
            )

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.PASSED
            assert "screenshot required" in result.message

    def test_external_brain_list_ok(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="external_brain_list", intent="brains", category="api", priority=2)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"brains": [{"name": "gemini"}, {"name": "chatgpt"}, {"name": "local"}]}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.PASSED
            assert "gemini" in result.message

    def test_external_brain_list_few_brains(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="external_brain_list", intent="brains", category="api", priority=2)

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"brains": [{"name": "gemini"}]}')
            mock_urlopen.return_value = mock_resp

            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.FAILED
            assert "Only 1 brains" in result.message

    def test_unknown_intent_skipped(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="unknown_test", intent="unknown", category="api", priority=3)

        result = _run_api_test_sync(harness, intent)
        assert result.status == TestStatus.SKIPPED
        assert "Unknown API test" in result.message

    def test_run_api_test_sync_exception_returns_failed(self):
        import urllib.error

        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="health_api", intent="health", category="api", priority=1)

        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("connection refused")):
            result = _run_api_test_sync(harness, intent)
            assert result.status == TestStatus.FAILED
            assert "connection refused" in result.message


# ---------------------------------------------------------------------------
# TestHarness — _run_api_test (async wrapper via run_in_executor)
# ---------------------------------------------------------------------------


class TestRunApiTest:
    def test_run_api_test_wraps_sync(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="health_api", intent="health", category="api", priority=1)

        with patch.object(
            harness, "_run_api_test_sync", return_value=TestResult("health_api", TestStatus.PASSED, 50, "ok")
        ):
            import asyncio

            result = asyncio.run(_run_api_test(harness, intent))
            assert result.status == TestStatus.PASSED


# ---------------------------------------------------------------------------
# TestHarness — Playwright page method tests (mocked)
# ---------------------------------------------------------------------------


class TestGotoDashboard:
    def test_goto_waits_for_selector(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        page = _MockPage()

        import asyncio

        asyncio.run(_goto_dashboard(harness, page))
        goto = cast(AsyncMock, getattr(page, "goto"))
        wait_for_selector = cast(AsyncMock, getattr(page, "wait_for_selector"))
        goto.assert_awaited_once_with("http://test:5173", wait_until="domcontentloaded", timeout=15000)
        wait_for_selector.assert_awaited_once_with("#app, #chat-input", timeout=15000)


class TestDashboardLoad:
    def test_load_success_by_title(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="dashboard_load", intent="load", category="ui", priority=1, timeout_sec=15)
        page = _MockPage(title=AsyncMock(return_value="Ssak-Ai Dashboard"))

        import asyncio

        result = asyncio.run(_test_dashboard_load(harness, page, intent))
        assert result.status == TestStatus.PASSED
        assert "Ssak-Ai" in result.message

    def test_load_success_by_app_selector(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="dashboard_load", intent="load", category="ui", priority=1, timeout_sec=15)
        page = _MockPage(
            title=AsyncMock(return_value="Custom Title"),
            query_selector=AsyncMock(return_value=object()),
        )

        import asyncio

        result = asyncio.run(_test_dashboard_load(harness, page, intent))
        assert result.status == TestStatus.PASSED
        assert "Custom Title" in result.message

    def test_load_fails(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="dashboard_load", intent="load", category="ui", priority=1, timeout_sec=15)
        page = _MockPage(
            title=AsyncMock(return_value="Other Page"),
            query_selector=AsyncMock(return_value=None),
        )

        import asyncio

        result = asyncio.run(_test_dashboard_load(harness, page, intent))
        assert result.status == TestStatus.FAILED
        assert "Other Page" in result.message


class TestChatSend:
    def test_send_success(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="chat_send", intent="chat", category="integration", priority=1, timeout_sec=60)
        page = _MockPage()

        with patch.object(
            harness.healing_loop,
            "try_with_healing",
            new=AsyncMock(
                return_value=TestResult(
                    "chat_send", TestStatus.PASSED, 5000, "\ucc44\ud305 \uc751\ub2f5 \uc218\uc2e0 \uc644\ub8cc"
                )
            ),
        ):
            import asyncio

            result = asyncio.run(_test_chat_send(harness, page, intent))
            assert result.status == TestStatus.PASSED

    def test_send_healing_failure(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="chat_send", intent="chat", category="integration", priority=1, timeout_sec=60)
        page = _MockPage()

        with patch.object(
            harness.healing_loop,
            "try_with_healing",
            new=AsyncMock(return_value=TestResult("chat_send", TestStatus.FAILED, 60000, "Timeout")),
        ):
            import asyncio

            result = asyncio.run(_test_chat_send(harness, page, intent))
            assert result.status == TestStatus.FAILED


class TestFileExplorer:
    def test_explorer_with_file_items(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="file_explorer", intent="explorer", category="ui", priority=2)
        page = _MockPage(
            query_selector_all=AsyncMock(return_value=[object(), object()]),
        )

        import asyncio

        result = asyncio.run(_test_file_explorer(harness, page, intent))
        assert result.status == TestStatus.PASSED
        assert "2\uac1c \ud30c\uc77c" in result.message

    def test_explorer_no_items_but_container_with_api_ok(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="file_explorer", intent="explorer", category="ui", priority=2)
        page = _MockPage(
            query_selector_all=AsyncMock(return_value=[]),
            query_selector=AsyncMock(return_value=object()),
        )

        with patch("urllib.request.OpenerDirector.open") as mock_urlopen:
            mock_resp = _MockHttpResponse(b'{"files": []}')
            mock_urlopen.return_value = mock_resp

            import asyncio

            result = asyncio.run(_test_file_explorer(harness, page, intent))
            assert result.status == TestStatus.PASSED
            assert "Explorer \ud328\ub110 \uc874\uc7ac" in result.message

    def test_explorer_no_items_container_with_api_error(self):
        import urllib.error

        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="file_explorer", intent="explorer", category="ui", priority=2)
        page = _MockPage(
            query_selector_all=AsyncMock(return_value=[]),
            query_selector=AsyncMock(return_value=object()),
        )

        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("API error")):
            import asyncio

            result = asyncio.run(_test_file_explorer(harness, page, intent))
            assert result.status == TestStatus.PASSED
            assert "lazy-load" in result.message

    def test_explorer_no_container_no_items(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="file_explorer", intent="explorer", category="ui", priority=2)
        page = _MockPage(
            query_selector_all=AsyncMock(return_value=[]),
            query_selector=AsyncMock(return_value=None),
        )

        import asyncio

        result = asyncio.run(_test_file_explorer(harness, page, intent))
        assert result.status == TestStatus.FAILED
        assert "\ubc1c\uacac" in result.message


class TestTerminalWs:
    @staticmethod
    def _make_mock_ws_module(recv_return: str, connect_side_effect: BaseException | None = None) -> MagicMock:
        """Create a mock websockets module that works with local import."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=recv_return)
        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)
        if connect_side_effect:
            mock_connect.__aenter__ = AsyncMock(side_effect=connect_side_effect)
        mock_module = MagicMock()
        mock_module.connect = MagicMock(return_value=mock_connect)
        return mock_module

    def test_terminal_ws_success(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="terminal_ws", intent="terminal", category="integration", priority=2, timeout_sec=30)

        mock_ws_mod = self._make_mock_ws_module(recv_return="harness_test_ok response")

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            import asyncio

            result = asyncio.run(_test_terminal_ws(harness, intent))
            assert result.status == TestStatus.PASSED
            assert "WebSocket" in result.message

    def test_terminal_ws_response_empty(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="terminal_ws", intent="terminal", category="integration", priority=2, timeout_sec=30)

        mock_ws_mod = self._make_mock_ws_module(recv_return="")

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            import asyncio

            result = asyncio.run(_test_terminal_ws(harness, intent))
            # Source code returns FAILED for empty responses
            assert result.status == TestStatus.FAILED

    def test_terminal_ws_import_error(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="terminal_ws", intent="terminal", category="integration", priority=2, timeout_sec=30)

        with patch.dict("sys.modules", {"websockets": None}):
            import asyncio

            result = asyncio.run(_test_terminal_ws(harness, intent))
            assert result.status == TestStatus.SKIPPED
            assert "websockets" in result.message or "playwright" in result.message

    def test_terminal_ws_connection_error(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="terminal_ws", intent="terminal", category="integration", priority=2, timeout_sec=30)

        mock_ws_mod = self._make_mock_ws_module(
            recv_return="",
            connect_side_effect=Exception("Connection refused"),
        )

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            import asyncio

            result = asyncio.run(_test_terminal_ws(harness, intent))
            assert result.status == TestStatus.FAILED
            assert "Connection refused" in result.message


class TestAutonomousQaDry:
    def test_qa_dry_success(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="autonomous_qa_dry", intent="qa_dry", category="integration", priority=3, timeout_sec=30)
        page = _MockPage(screenshot=AsyncMock(return_value=b"x" * 2000))

        mock_engine = MagicMock()
        with patch("antigravity_k.engine.autonomous_qa.AutonomousQAEngine", return_value=mock_engine):
            import asyncio

            result = asyncio.run(_test_autonomous_qa_dry(harness, page, intent))
            assert result.status == TestStatus.PASSED
            assert "2000 bytes" in result.message

    def test_qa_dry_screenshot_too_small(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="autonomous_qa_dry", intent="qa_dry", category="integration", priority=3, timeout_sec=30)
        page = _MockPage(screenshot=AsyncMock(return_value=b"small"))

        mock_engine = MagicMock()
        with patch("antigravity_k.engine.autonomous_qa.AutonomousQAEngine", return_value=mock_engine):
            import asyncio

            result = asyncio.run(_test_autonomous_qa_dry(harness, page, intent))
            assert result.status == TestStatus.FAILED
            assert "\uc2a4\ud06c\ub9b0\uc0f7 \uc2e4\ud328" in result.message

    def test_qa_dry_exception(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="autonomous_qa_dry", intent="qa_dry", category="integration", priority=3, timeout_sec=30)
        page = _MockPage()

        with patch(
            "antigravity_k.engine.autonomous_qa.AutonomousQAEngine", side_effect=Exception("Engine init failed")
        ):
            import asyncio

            result = asyncio.run(_test_autonomous_qa_dry(harness, page, intent))
            assert result.status == TestStatus.FAILED
            assert "Engine init failed" in result.message


class TestResponsive:
    def test_responsive_all_pass(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="responsive_check", intent="responsive", category="ui", priority=2, timeout_sec=30)
        page = _MockPage(
            set_viewport_size=AsyncMock(),
            evaluate=AsyncMock(return_value=False),
        )

        import asyncio

        result = asyncio.run(_test_responsive(harness, page, intent))
        assert result.status == TestStatus.PASSED
        assert "3/3" in result.message

    def test_responsive_one_overflow_but_passes(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="responsive_check", intent="responsive", category="ui", priority=2, timeout_sec=30)
        evaluate = AsyncMock()
        evaluate.side_effect = [True, False, False]
        page = _MockPage(
            set_viewport_size=AsyncMock(),
            evaluate=evaluate,
        )

        import asyncio

        result = asyncio.run(_test_responsive(harness, page, intent))
        assert result.status == TestStatus.PASSED
        assert "2/3" in result.message

    def test_responsive_fails(self):
        harness = TestHarness(base_url="http://test:8000", dashboard_url="http://test:5173")
        intent = TestIntent(id="responsive_check", intent="responsive", category="ui", priority=2, timeout_sec=30)
        evaluate = AsyncMock()
        evaluate.side_effect = [True, True, True]
        page = _MockPage(
            set_viewport_size=AsyncMock(),
            evaluate=evaluate,
        )

        import asyncio

        result = asyncio.run(_test_responsive(harness, page, intent))
        assert result.status == TestStatus.FAILED
        assert "0/3" in result.message


# ---------------------------------------------------------------------------
# TestHarness — run_all & browser tests (mocked)
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_run_all_api_only(self):
        harness = TestHarness(base_url="http://test:8000")
        harness.intents = [
            TestIntent(id="health_api", intent="health", category="api", priority=1),
        ]

        with patch.object(
            harness, "_run_api_test", new=AsyncMock(return_value=TestResult("health_api", TestStatus.PASSED, 100, "ok"))
        ):
            import asyncio

            report = asyncio.run(harness.run_all(use_browser=False))
            assert report.total == 1
            assert report.passed == 1

    def test_run_all_with_browser_intents(self):
        harness = TestHarness(base_url="http://test:8000")
        harness.intents = [
            TestIntent(id="health_api", intent="health", category="api", priority=1),
            TestIntent(id="dashboard_load", intent="load", category="ui", priority=1),
        ]

        with patch.object(
            harness, "_run_api_test", new=AsyncMock(return_value=TestResult("health_api", TestStatus.PASSED, 100, "ok"))
        ):
            with patch.object(
                harness,
                "_run_browser_tests",
                new=AsyncMock(return_value=[TestResult("dashboard_load", TestStatus.PASSED, 200, "loaded")]),
            ):
                import asyncio

                report = asyncio.run(harness.run_all(use_browser=True))
                assert report.total == 2
                assert report.passed == 2

    def test_run_browser_tests_playwright_not_installed(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="dashboard_load", intent="load", category="ui", priority=1)

        with patch.dict("sys.modules", {"playwright.async_api": None}):
            import asyncio

            result = asyncio.run(_run_browser_tests(harness, [intent]))
            assert len(result) == 1
            assert result[0].status == TestStatus.SKIPPED
            assert "playwright" in result[0].message

    def test_run_browser_tests_executes_methods(self):
        harness = TestHarness(base_url="http://test:8000")
        intents = [
            TestIntent(id="dashboard_load", intent="load", category="ui", priority=1),
            TestIntent(id="chat_send", intent="chat", category="integration", priority=1),
            TestIntent(id="file_explorer", intent="explorer", category="ui", priority=2),
            TestIntent(id="terminal_ws", intent="terminal", category="integration", priority=2),
            TestIntent(id="autonomous_qa_dry", intent="qa", category="integration", priority=3),
            TestIntent(id="responsive_check", intent="responsive", category="ui", priority=2),
            TestIntent(id="unknown_test", intent="unknown", category="ui", priority=3),
        ]

        for method_name in (
            "_test_dashboard_load",
            "_test_chat_send",
            "_test_file_explorer",
            "_test_terminal_ws",
            "_test_autonomous_qa_dry",
            "_test_responsive",
        ):
            setattr(harness, method_name, AsyncMock(return_value=TestResult(method_name, TestStatus.PASSED, 100, "ok")))

        mock_p = MagicMock()
        chromium = AsyncMock()
        setattr(mock_p, "chromium", chromium)
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        setattr(chromium, "launch", AsyncMock(return_value=mock_browser))

        mock_playwright_cls = MagicMock()
        mock_playwright_cls.__aenter__ = AsyncMock(return_value=mock_p)
        mock_playwright_cls.__aexit__ = AsyncMock(return_value=None)

        with patch("playwright.async_api.async_playwright", return_value=mock_playwright_cls):
            import asyncio

            results = asyncio.run(_run_browser_tests(harness, intents))
            assert len(results) == 7
            passed = [r for r in results if r.status == TestStatus.PASSED]
            assert len(passed) == 6
            skipped = [r for r in results if r.status == TestStatus.SKIPPED]
            assert len(skipped) == 1
            assert skipped[0].intent_id == "unknown_test"

    def test_run_browser_tests_method_exception_returns_failed(self):
        harness = TestHarness(base_url="http://test:8000")
        intent = TestIntent(id="dashboard_load", intent="load", category="ui", priority=1)

        setattr(harness, "_test_dashboard_load", AsyncMock(side_effect=Exception("Unexpected error")))

        mock_p = MagicMock()
        chromium = AsyncMock()
        setattr(mock_p, "chromium", chromium)
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        setattr(chromium, "launch", AsyncMock(return_value=mock_browser))

        mock_playwright_cls = MagicMock()
        mock_playwright_cls.__aenter__ = AsyncMock(return_value=mock_p)
        mock_playwright_cls.__aexit__ = AsyncMock(return_value=None)

        with patch("playwright.async_api.async_playwright", return_value=mock_playwright_cls):
            import asyncio

            results = asyncio.run(_run_browser_tests(harness, [intent]))
            assert len(results) == 1
            assert results[0].status == TestStatus.FAILED
            assert "Unexpected error" in results[0].message
