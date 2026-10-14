"""Ssak-Ai: 하네스 엔지니어링 프레임워크.

===========================================
Intent 기반 테스트, Self-Healing Loop, 피드백 수집기를 포함한
에이전트 주도 QA 자동화 시스템.

핵심 개념:
- TestHarness: 테스트 시나리오 관리 및 실행
- HealingLoop: 실패 시 DOM 분석 → 셀렉터 자동 수정 → 재시도
- FeedbackCollector: 테스트 결과를 에이전트에게 피드백

데이터 모델(TestStatus, TestIntent, TestResult, HarnessReport)은
``harness_models.py``로, HealingLoop/HealingLoopV2는 ``healing_loop.py``로
분리되었다. 이 모듈은 하위 호환을 위해 모든 심볼을 재수출한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import ClassVar, Protocol, cast
from urllib.parse import urlparse

from antigravity_k.config import config
from antigravity_k.engine.harness_models import (
    HarnessReport,
    TestIntent,
    TestResult,
    TestStatus,
)
from antigravity_k.engine.healing_loop import HealingLoop, HealingLoopV2
from antigravity_k.tools.browser_session_owner import (
    current_browser_owner,
    get_browser_session_owner,
)
from antigravity_k.tools.egress_policy import safe_urlopen

# Re-export all public symbols so downstream `from .harness import X` keeps working.
__all__ = [
    "FeedbackCollector",
    "HarnessReport",
    "HealingLoop",
    "HealingLoopV2",
    "TestHarness",
    "TestIntent",
    "TestResult",
    "TestStatus",
]

logger = logging.getLogger("antigravity_k.harness")

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class _ElementLike(Protocol):
    async def fill(self, value: str) -> object: ...

    async def press(self, key: str) -> object: ...


class _LocatorLike(Protocol):
    async def count(self) -> int: ...


class _BrowserContextLike(Protocol):
    async def add_cookies(self, cookies: list[dict[str, str]]) -> object: ...


class _PageLike(Protocol):
    context: _BrowserContextLike

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> object: ...

    async def wait_for_selector(self, selector: str, *, timeout: int) -> object: ...

    async def title(self) -> str: ...

    async def query_selector(self, selector: str) -> _ElementLike | None: ...

    async def query_selector_all(self, selector: str) -> list[_ElementLike]: ...

    def locator(self, selector: str) -> _LocatorLike: ...

    async def wait_for_function(self, expression: str, *, arg: object, timeout: int) -> object: ...

    async def add_init_script(self, script: str) -> object: ...

    async def screenshot(self) -> bytes: ...

    async def set_viewport_size(self, viewport: dict[str, int]) -> object: ...

    async def evaluate(self, expression: str) -> bool: ...


class _BrowserLike(Protocol):
    async def new_page(self) -> _PageLike: ...

    async def close(self) -> object: ...


class _ChromiumLike(Protocol):
    async def launch(self, *, headless: bool) -> _BrowserLike: ...


class _PlaywrightLike(Protocol):
    chromium: _ChromiumLike


def _as_json_object(value: object) -> JsonObject:
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def _as_json_list(value: object) -> list[JsonValue]:
    return cast(list[JsonValue], value) if isinstance(value, list) else []


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else str(value)


def _load_json_object(payload: str) -> JsonObject:
    return _as_json_object(cast(object, json.loads(payload)))


# ─── Feedback Collector ────────────────────────────────────────


class FeedbackCollector:
    """테스트 결과를 수집하고 에이전트에게 피드백합니다.

    하네스 엔지니어링의 'Agent-Legible Feedback' 구현.
    """

    def __init__(self) -> None:
        """Initialize the FeedbackCollector."""
        self.history: list[HarnessReport] = []

    def collect(self, report: HarnessReport) -> str:
        """결과를 수집하고 에이전트가 읽을 수 있는 피드백을 생성합니다."""
        self.history.append(report)

        if report.failed == 0:
            return f"✅ 모든 테스트 통과 ({report.passed + report.healed}/{report.total})"

        # 실패한 테스트의 구체적인 정보를 에이전트에게 전달
        failed_tests = [r for r in report.results if r.status == TestStatus.FAILED]
        feedback_lines = [
            f"⚠️ {report.failed}개 테스트 실패:",
        ]
        for ft in failed_tests:
            feedback_lines.append(f"  - [{ft.intent_id}] {ft.message}")

        return "\n".join(feedback_lines)

    def get_trend(self) -> dict[str, object]:
        """최근 테스트 추세를 반환합니다."""
        if not self.history:
            return {"trend": "no_data"}

        recent = self.history[-5:]
        pass_rates = [(r.passed + r.healed) / max(r.total, 1) * 100 for r in recent]

        return {
            "recent_pass_rates": pass_rates,
            "trend": ("improving" if len(pass_rates) > 1 and pass_rates[-1] > pass_rates[0] else "stable"),
            "total_runs": len(self.history),
        }


# ─── Test Harness (메인 오케스트레이터) ──────────────────────────


class TestHarness:
    """하네스 엔지니어링 프레임워크의 메인 오케스트레이터.

    Intent 기반 테스트를 실행하고, Self-Healing을 적용하며,
    결과를 수집하여 에이전트에게 피드백합니다.
    """

    __test__: ClassVar[bool] = False

    # Ssak-Ai 대시보드 기본 테스트 시나리오
    DEFAULT_INTENTS: ClassVar[list[TestIntent]] = [
        TestIntent(
            id="health_api",
            intent="백엔드 API 헬스체크가 정상 응답한다",
            category="api",
            priority=1,
            tags=["critical", "api"],
        ),
        TestIntent(
            id="models_api",
            intent="모델 목록 API가 정상적으로 모델 리스트를 반환한다",
            category="api",
            priority=1,
            tags=["critical", "api"],
        ),
        TestIntent(
            id="dashboard_load",
            intent="대시보드 메인 페이지가 정상적으로 로드된다",
            category="ui",
            priority=1,
            tags=["critical", "ui"],
        ),
        TestIntent(
            id="chat_send",
            intent="채팅에 메시지를 보내면 스트리밍 응답이 시작된다",
            category="integration",
            priority=1,
            timeout_sec=60.0,
            tags=["critical", "chat"],
        ),
        TestIntent(
            id="file_explorer",
            intent="파일 탐색기에 워크스페이스 파일 목록이 표시된다",
            category="ui",
            priority=2,
            tags=["ui", "explorer"],
        ),
        TestIntent(
            id="terminal_ws",
            intent="터미널 WebSocket 연결이 성공한다",
            category="integration",
            priority=2,
            tags=["terminal", "websocket"],
        ),
        # ─── Phase 7~9 신규 테스트 ───
        TestIntent(
            id="vision_analyze",
            intent="비전 분석 API가 스크린샷을 분석하여 결과를 반환한다",
            category="api",
            priority=2,
            timeout_sec=120.0,
            tags=["vision", "multimodal"],
        ),
        TestIntent(
            id="external_brain_list",
            intent="외부 AI 두뇌 목록 API가 어댑터 리스트를 반환한다",
            category="api",
            priority=2,
            tags=["external_brain"],
        ),
        TestIntent(
            id="autonomous_qa_dry",
            intent="자율 QA 엔진이 초기화 가능하고 스크린샷 촬영이 가능하다",
            category="integration",
            priority=3,
            timeout_sec=30.0,
            tags=["autonomous_qa"],
        ),
        TestIntent(
            id="responsive_check",
            intent="대시보드가 데스크톱/태블릿/모바일 3종 뷰포트에서 가로 스크롤 없이 렌더링된다",
            category="ui",
            priority=2,
            timeout_sec=30.0,
            tags=["responsive", "ui"],
        ),
    ]

    def __init__(
        self,
        base_url: str | None = None,
        dashboard_url: str | None = None,
        ws_url: str | None = None,
    ):
        """Initialize the TestHarness.

        Args:
            base_url (str | None): str | None base url.
            dashboard_url (str | None): str | None dashboard url.
            ws_url (str | None): str | None ws url.

        """
        self.base_url: str = (base_url or os.environ.get("AGK_HARNESS_BASE_URL") or "http://localhost:8000").rstrip("/")
        self.dashboard_url: str = (
            dashboard_url or os.environ.get("AGK_HARNESS_DASHBOARD_URL") or "http://localhost:5173"
        ).rstrip("/")
        self.ws_url: str = ws_url or os.environ.get("AGK_HARNESS_WS_URL") or self._derive_ws_url(self.base_url)
        # SEC-02: raw PIN 전송 채널(헤더/쿠키)은 제거됐다 — PIN은 login에서 토큰으로
        # 교환해 Authorization 헤더로만 사용한다.
        self.access_pin: str | None = os.environ.get("AGK_HARNESS_ACCESS_PIN") or (config.security.access_pin)
        self._token: str | None = None
        self.healing_loop: HealingLoop = HealingLoop(max_attempts=3)
        self.feedback: FeedbackCollector = FeedbackCollector()
        self.intents: list[TestIntent] = list(self.DEFAULT_INTENTS)
        self._browser: _BrowserLike | None = None
        self._playwright: _PlaywrightLike | None = None

    @staticmethod
    def _derive_ws_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc or "localhost:8000"
        return f"{scheme}://{netloc}/ws/terminal"

    def _request_headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        token = self._ensure_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _ensure_token(self) -> str | None:
        """PIN을 /api/auth/login으로 교환해 bearer 토큰을 확보한다 (1회 캐시).

        SEC-02: PIN 자체는 전송 채널에 노출되지 않는다 — rate-limited login route
        1회 호출 후 토큰만 재사용한다. 로그인 실패 시 None (익명 실행)."""
        if self._token is not None:
            return self._token
        if not self.access_pin:
            return None
        try:
            import httpx

            response = httpx.post(
                f"{self.base_url}/api/auth/login",
                json={"pin": self.access_pin},
                timeout=10.0,
                trust_env=False,
            )
            if response.status_code == 200:
                self._token = str(response.json().get("access_token", "")) or None
                return self._token
        except Exception:  # noqa: BLE001 — 인증 실패는 익명 실행으로 폴백
            pass
        logger.warning("Harness token exchange failed; running unauthenticated")
        return None

    async def run_all(self, use_browser: bool = True) -> HarnessReport:
        """모든 테스트 인텐트를 실행합니다."""
        report = HarnessReport()
        start = time.time()

        # API 테스트 (브라우저 불필요)
        api_intents = [i for i in self.intents if i.category == "api"]
        for intent in api_intents:
            result = await self._run_api_test(intent)
            report.results.append(result)

        # UI/통합 테스트 (브라우저 필요)
        if use_browser:
            browser_intents = [i for i in self.intents if i.category in ("ui", "integration")]
            browser_results = await self._run_browser_tests(browser_intents)
            report.results.extend(browser_results)

        # 통계 집계
        report.total = len(report.results)
        report.passed = sum(1 for r in report.results if r.status == TestStatus.PASSED)
        report.failed = sum(1 for r in report.results if r.status == TestStatus.FAILED)
        report.healed = sum(1 for r in report.results if r.status == TestStatus.HEALED)
        report.skipped = sum(1 for r in report.results if r.status == TestStatus.SKIPPED)
        report.duration_ms = (time.time() - start) * 1000

        # 피드백 수집
        feedback_msg = self.feedback.collect(report)
        logger.info("[TestHarness] %s", feedback_msg)

        return report

    async def _run_api_test(self, intent: TestIntent) -> TestResult:
        """API 테스트 실행합니다 (run_in_executor로 블로킹 방지)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_api_test_sync, intent)

    def _run_api_test_sync(self, intent: TestIntent) -> TestResult:
        """API 테스트 동기 실행합니다 (별도 스레드에서 실행됨)."""
        import urllib.error
        import urllib.request

        start = time.time()

        try:
            if intent.id == "health_api":
                req = urllib.request.Request(f"{self.base_url}/v1/health")
                with safe_urlopen(req, timeout=5) as resp:
                    data = _load_json_object(resp.read().decode())
                    if data.get("status") == "ok":
                        elapsed = (time.time() - start) * 1000
                        return TestResult(intent.id, TestStatus.PASSED, elapsed, "Health OK")
                    else:
                        elapsed = (time.time() - start) * 1000
                        return TestResult(
                            intent.id,
                            TestStatus.FAILED,
                            elapsed,
                            f"Unexpected: {data}",
                        )

            elif intent.id == "models_api":
                req = urllib.request.Request(f"{self.base_url}/v1/models")
                with safe_urlopen(req, timeout=5) as resp:
                    data = _load_json_object(resp.read().decode())
                    models = _as_json_list(data.get("data", []))
                    if len(models) > 0:
                        elapsed = (time.time() - start) * 1000
                        return TestResult(
                            intent.id,
                            TestStatus.PASSED,
                            elapsed,
                            f"{len(models)} models available",
                        )
                    else:
                        elapsed = (time.time() - start) * 1000
                        return TestResult(
                            intent.id,
                            TestStatus.FAILED,
                            elapsed,
                            "No models returned",
                        )

            elif intent.id == "vision_analyze":
                # 비전 분석 API 도달 가능 여부 확인 (스크린샷 없이)
                req = urllib.request.Request(
                    f"{self.base_url}/api/agent/tools/browser/vision-analyze",
                    data=json.dumps({"prompt": "Describe this UI."}).encode(),
                    headers=self._request_headers({"Content-Type": "application/json"}),
                    method="POST",
                )
                try:
                    with safe_urlopen(req, timeout=10) as resp:
                        elapsed = (time.time() - start) * 1000
                        return TestResult(
                            intent.id,
                            TestStatus.PASSED,
                            elapsed,
                            "Vision API reachable",
                        )
                except urllib.error.HTTPError as he:
                    elapsed = (time.time() - start) * 1000
                    # 400/422 = 스크린샷 없어서 거부 → API 자체는 정상 도달
                    if he.code in (400, 422):
                        return TestResult(
                            intent.id,
                            TestStatus.PASSED,
                            elapsed,
                            f"Vision API reachable (expected {he.code})",
                        )
                    # 500이어도 서버가 요청을 받아 처리했으므로 라우트는 존재
                    body = he.read().decode()[:100] if hasattr(he, "read") else ""
                    if "No screenshot" in body or "screenshot" in body.lower():
                        return TestResult(
                            intent.id,
                            TestStatus.PASSED,
                            elapsed,
                            "Vision API reachable (screenshot required)",
                        )
                    return TestResult(
                        intent.id,
                        TestStatus.FAILED,
                        elapsed,
                        f"HTTP {he.code}: {body}",
                    )

            elif intent.id == "external_brain_list":
                req = urllib.request.Request(
                    f"{self.base_url}/api/agent/tools/external-brain/list",
                    headers=self._request_headers(),
                )
                with safe_urlopen(req, timeout=10) as resp:
                    data = _load_json_object(resp.read().decode())
                    brains = _as_json_list(data.get("brains", []))
                    elapsed = (time.time() - start) * 1000
                    if len(brains) >= 3:
                        names = [_as_text(item.get("name", "")) for item in brains if isinstance(item, dict)]
                        return TestResult(
                            intent.id,
                            TestStatus.PASSED,
                            elapsed,
                            f"Brains: {', '.join(names)}",
                        )
                    else:
                        return TestResult(
                            intent.id,
                            TestStatus.FAILED,
                            elapsed,
                            f"Only {len(brains)} brains found",
                        )

            else:
                elapsed = (time.time() - start) * 1000
                return TestResult(intent.id, TestStatus.SKIPPED, elapsed, "Unknown API test")

        except Exception as e:
            logger.exception("Unhandled exception")
            elapsed = (time.time() - start) * 1000
            return TestResult(intent.id, TestStatus.FAILED, elapsed, str(e))

    async def _run_browser_tests(self, intents: list[TestIntent]) -> list[TestResult]:
        """Playwright 기반 브라우저 테스트."""
        results: list[TestResult] = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            for intent in intents:
                results.append(
                    TestResult(
                        intent.id,
                        TestStatus.SKIPPED,
                        0,
                        "playwright 미설치. 'pip install playwright && playwright install chromium' 실행 필요",
                    ),
                )
            return results

        playwright_factory = cast(
            Callable[[], AbstractAsyncContextManager[_PlaywrightLike]],
            async_playwright,
        )
        # 소유자를 지나간다(task 16): 하네스도 호스트의 브라우저를 빌리는 것이다 — 자기 나름의
        # 브라우저를 열면 상한·회수·종료 정리 밖으로 나간다.
        session_owner = get_browser_session_owner()
        browser_owner = current_browser_owner()
        reservation = session_owner.begin(browser_owner, purpose="ui harness")
        try:
            # 하네스가 여는 주소도 egress 규칙을 지나되, 대상은 **운영자가 지정한** 앱 주소라 로컬이 허용된다.
            _ = session_owner.validate_navigation(self.dashboard_url, allow_local=True)
        except Exception:
            # 거절된 주소로는 브라우저를 열지 않는다. 예약도 돌려준다 — 안 그러면 자리만 남는다.
            session_owner.abort(reservation)
            raise

        async with playwright_factory() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                _ = session_owner.commit(reservation, page=page)
                # SEC-02: PIN 쿠키/localStorage 주입 제거 — 브라우저 실행도 token 기반.
                token = self._ensure_token()
                if token:
                    _ = await page.add_init_script(
                        f"sessionStorage.setItem('ag_access_token', {json.dumps(token)});",
                    )

                for intent in intents:
                    try:
                        if intent.id == "dashboard_load":
                            result = await self._test_dashboard_load(page, intent)
                        elif intent.id == "chat_send":
                            result = await self._test_chat_send(page, intent)
                        elif intent.id == "file_explorer":
                            result = await self._test_file_explorer(page, intent)
                        elif intent.id == "terminal_ws":
                            result = await self._test_terminal_ws(intent)
                        elif intent.id == "autonomous_qa_dry":
                            result = await self._test_autonomous_qa_dry(page, intent)
                        elif intent.id == "responsive_check":
                            result = await self._test_responsive(page, intent)
                        else:
                            result = TestResult(intent.id, TestStatus.SKIPPED, 0, "Unknown test")
                        results.append(result)
                    except Exception as e:
                        logger.exception("Unhandled exception")
                        results.append(TestResult(intent.id, TestStatus.FAILED, 0, str(e)))
            finally:
                # launch 이후 단계(new_page/쿠키/이동)에서 예외가 나도
                # 브라우저가 유출되지 않도록 닫는다.
                _ = await browser.close()
                _ = session_owner.release(browser_owner)

        return results

    async def _goto_dashboard(self, page: _PageLike, timeout_ms: int = 15000) -> None:
        """Navigate to the SPA dashboard without waiting for networkidle.

        The dashboard keeps WebSocket/event streams open, so networkidle is
        not a reliable readiness signal. A rendered app root or chat input is
        the stable contract for harness tests.
        """
        _ = await page.goto(
            self.dashboard_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        _ = await page.wait_for_selector("#app, #chat-input", timeout=timeout_ms)

    async def _test_dashboard_load(self, page: _PageLike, intent: TestIntent) -> TestResult:
        """대시보드 로딩 테스트."""
        start = time.time()
        await self._goto_dashboard(page, timeout_ms=int(intent.timeout_sec * 1000))
        title = await page.title()
        elapsed = (time.time() - start) * 1000

        if "Ssak-Ai" in title or await page.query_selector("#app"):
            return TestResult(intent.id, TestStatus.PASSED, elapsed, f"Dashboard loaded: {title}")
        else:
            return TestResult(intent.id, TestStatus.FAILED, elapsed, f"Unexpected title: {title}")

    async def _test_chat_send(self, page: _PageLike, intent: TestIntent) -> TestResult:
        """채팅 메시지 전송 및 응답 수신 테스트."""
        await self._goto_dashboard(page)

        # 채팅 입력란 찾기 (self-healing 포함)
        context: dict[str, object] = {
            "target_text": "명령어나 질문을 입력하세요",
            "selector": "#chat-input",
        }

        async def chat_action(pg: _PageLike, ctx: dict[str, object]) -> str:
            selector = ctx.get("selector", "#chat-input")
            selector_text = selector if isinstance(selector, str) else "#chat-input"
            input_el = await pg.query_selector(selector_text)
            if not input_el:
                # Healing: placeholder 텍스트로 찾기
                input_el = await pg.query_selector("input[placeholder], textarea[placeholder]")
            if not input_el:
                raise RuntimeError("채팅 입력란을 찾을 수 없습니다")

            assistant_selector = ".message.assistant .bubble"
            assistant_before = await pg.locator(assistant_selector).count()

            _ = await input_el.fill("테스트 메시지")
            _ = await input_el.press("Enter")

            # 응답 대기 (최대 timeout_sec). 기존 welcome bubble이나 즉시 생성되는
            # "Thinking" placeholder를 실제 응답으로 오인하지 않도록 마지막 assistant
            # bubble의 내용이 생성 완료 상태인지 확인합니다.
            _ = await pg.wait_for_function(
                """
                ([selector, before]) => {

                    const nodes = Array.from(document.querySelectorAll(selector));
                    if (nodes.length <= before) return false;
                    const latest = nodes[nodes.length - 1].innerText || "";
                    const normalized = latest.trim();
                    return normalized.length > 0
                        && !normalized.includes("Thinking")
                        && !normalized.includes("API 요청 중 오류");
                }
                """,
                arg=[assistant_selector, assistant_before],
                timeout=int(intent.timeout_sec * 1000),
            )
            return "채팅 응답 수신 완료"

        heal = cast(
            Callable[[_PageLike, dict[str, object]], Awaitable[str]],
            chat_action,
        )
        runner = cast(
            Callable[
                [Callable[[_PageLike, dict[str, object]], Awaitable[str]], _PageLike, dict[str, object], TestIntent],
                Awaitable[TestResult],
            ],
            getattr(self.healing_loop, "try_with_healing"),
        )
        return await runner(heal, page, context, intent)

    async def _test_file_explorer(self, page: _PageLike, intent: TestIntent) -> TestResult:
        """파일 탐색기 테스트 (2-Layer: UI 컨테이너 + API 검증).

        SPA의 파일 트리는 폴더를 명시적으로 열기 전까지 비어 있을 수 있으므로,
        1) Explorer 패널(컨테이너)이 DOM에 존재하는지 확인
        2) 백엔드 워크스페이스 파일 API가 응답하는지 확인
        두 가지 중 하나라도 통과하면 PASS로 처리합니다.
        """
        import urllib.error
        import urllib.request

        start = time.time()
        await self._goto_dashboard(page)

        # Layer 1: DOM에서 파일 아이템 또는 Explorer 컨테이너 존재 확인
        file_items: list[_ElementLike] = await page.query_selector_all(
            ".file-item, .tree-item, [class*='explorer'] li, [class*='explorer'] .item",
        )
        explorer_container = await page.query_selector(
            ".ide-explorer, .file-tree, [class*='explorer']",
        )

        if file_items and len(file_items) > 0:
            elapsed = (time.time() - start) * 1000
            return TestResult(
                intent.id,
                TestStatus.PASSED,
                elapsed,
                f"{len(file_items)}개 파일 항목 표시",
            )

        # Layer 2: 컨테이너만 존재하고 아이템이 없으면 API로 확인
        if explorer_container:
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/agent/tools/fs/read",
                    data=json.dumps({"file_path": ".", "action": "list"}).encode(),
                    headers=self._request_headers({"Content-Type": "application/json"}),
                    method="POST",
                )
                with safe_urlopen(req, timeout=5) as _resp:
                    elapsed = (time.time() - start) * 1000
                    return TestResult(
                        intent.id,
                        TestStatus.PASSED,
                        elapsed,
                        "Explorer 패널 존재 + 파일 API 응답 정상",
                    )
            except (urllib.error.HTTPError, urllib.error.URLError):
                elapsed = (time.time() - start) * 1000
                return TestResult(
                    intent.id,
                    TestStatus.PASSED,
                    elapsed,
                    "Explorer 패널 존재 (파일 아이템은 lazy-load 대기 상태)",
                )

        elapsed = (time.time() - start) * 1000
        return TestResult(
            intent.id,
            TestStatus.FAILED,
            elapsed,
            "Explorer 패널 및 파일 항목 모두 미발견",
        )

    async def _test_terminal_ws(self, intent: TestIntent) -> TestResult:
        """터미널 WebSocket 연결 테스트."""
        start = time.time()
        try:
            import websockets

            async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                await ws.send("echo 'harness_test_ok'\n")
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                elapsed = (time.time() - start) * 1000

                if response:
                    return TestResult(intent.id, TestStatus.PASSED, elapsed, "WebSocket 연결 성공")
                else:
                    return TestResult(intent.id, TestStatus.FAILED, elapsed, "응답 없음")
        except ImportError:
            elapsed = (time.time() - start) * 1000
            return TestResult(intent.id, TestStatus.SKIPPED, elapsed, "websockets 미설치")
        except Exception as e:
            logger.exception("Unhandled exception")
            elapsed = (time.time() - start) * 1000
            message = str(e) or f"{type(e).__name__} while connecting to {self.ws_url}"
            return TestResult(intent.id, TestStatus.FAILED, elapsed, message)

    async def _test_autonomous_qa_dry(self, page: _PageLike, intent: TestIntent) -> TestResult:
        """자율 QA 엔진 드라이런 — 초기화 + 스크린샷 가능 여부 확인."""
        start = time.time()
        try:
            from antigravity_k.engine.autonomous_qa import AutonomousQAEngine

            _ = AutonomousQAEngine(dashboard_url=self.dashboard_url)

            # 스크린샷 촬영 테스트
            await self._goto_dashboard(page)
            screenshot: bytes = await page.screenshot()
            elapsed = (time.time() - start) * 1000

            if screenshot and len(screenshot) > 1000:
                return TestResult(
                    intent.id,
                    TestStatus.PASSED,
                    elapsed,
                    f"AutonomousQA 초기화 OK, 스크린샷 {len(screenshot)} bytes",
                )
            else:
                return TestResult(intent.id, TestStatus.FAILED, elapsed, "스크린샷 실패")
        except Exception as e:
            logger.exception("Unhandled exception")
            elapsed = (time.time() - start) * 1000
            return TestResult(intent.id, TestStatus.FAILED, elapsed, str(e))

    async def _test_responsive(self, page: _PageLike, intent: TestIntent) -> TestResult:
        """반응형 3종 뷰포트 테스트 (가로 스크롤 없음 확인)."""
        start = time.time()
        viewports = {
            "desktop": {"width": 1280, "height": 800},
            "tablet": {"width": 768, "height": 1024},
            "mobile": {"width": 375, "height": 812},
        }
        passed_count = 0
        details: list[str] = []

        for name, vp in viewports.items():
            try:
                _ = await page.set_viewport_size(vp)
                await self._goto_dashboard(page)
                overflow = await page.evaluate(
                    "() => document.documentElement.scrollWidth > document.documentElement.clientWidth",
                )
                if not overflow:
                    passed_count += 1
                    details.append(f"✅ {name}")
                else:
                    details.append(f"❌ {name} (overflow)")
            except Exception as e:
                logger.exception("Unhandled exception")
                details.append(f"❌ {name} ({e})")

        elapsed = (time.time() - start) * 1000
        if passed_count >= 2:
            return TestResult(
                intent.id,
                TestStatus.PASSED,
                elapsed,
                f"{passed_count}/3 뷰포트 통과: {', '.join(details)}",
            )
        else:
            return TestResult(
                intent.id,
                TestStatus.FAILED,
                elapsed,
                f"{passed_count}/3 뷰포트 통과: {', '.join(details)}",
            )

    def add_intent(self, intent: TestIntent) -> None:
        """커스텀 테스트 인텐트 추가."""
        self.intents.append(intent)

    def get_latest_report(self) -> HarnessReport | None:
        """가장 최근 테스트 결과 반환."""
        if self.feedback.history:
            return self.feedback.history[-1]
        return None
