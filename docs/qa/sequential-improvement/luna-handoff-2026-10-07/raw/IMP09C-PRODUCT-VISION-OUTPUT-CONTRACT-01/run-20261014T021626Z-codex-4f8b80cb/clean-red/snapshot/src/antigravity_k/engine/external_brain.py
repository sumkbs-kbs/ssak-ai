"""Ssak-Ai: 외부 AI 두뇌 어댑터 (ExternalBrainAdapter).

==========================================================
설치된 AI 앱(Gemini Desktop, ChatGPT Web)의 채팅 UI를
GUI 자동화로 제어하여 API 없이 추론 결과를 획득합니다.

아키텍처:
    Orchestrator → ExternalBrainRouter → GeminiAppAdapter (AppleScript)
                                       → ChatGPTWebAdapter (Playwright)
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, cast, final, override

from antigravity_k.tools.browser_session_owner import (
    PERSONAL_PROFILE_ENV,
    get_browser_session_owner,
    personal_profile_allowed,
)

logger = logging.getLogger("antigravity_k.external_brain")


class _ElementLike(Protocol):
    async def fill(self, value: str) -> None: ...

    async def press(self, key: str) -> None: ...

    async def inner_text(self) -> str: ...


class _PageLike(Protocol):
    async def query_selector(self, selector: str) -> _ElementLike | None: ...

    async def query_selector_all(self, selector: str) -> list[_ElementLike]: ...


# ─── 데이터 모델 ───────────────────────────────────────────────


@dataclass
class BrainResponse:
    """외부 두뇌로부터 받은 응답."""

    text: str
    source: str  # "gemini_app", "chatgpt_web", etc.
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""


# ─── 기반 클래스 ───────────────────────────────────────────────


class ExternalBrainAdapter(ABC):
    """외부 AI 두뇌 어댑터 기반 클래스."""

    def __init__(self, name: str, timeout_sec: float = 120.0):
        """Initialize the ExternalBrainAdapter.

        Args:
            name (str): str name.
            timeout_sec (float): float timeout sec.

        """
        self.name: str = name
        self.timeout_sec: float = timeout_sec
        self._available: bool | None = None

    @abstractmethod
    async def send(self, prompt: str) -> BrainResponse:
        """프롬프트를 전송하고 응답을 반환합니다."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """이 두뇌가 현재 사용 가능한지 확인합니다."""
        ...


# ─── Gemini Desktop App 어댑터 (AppleScript) ──────────────────


@final
class GeminiAppAdapter(ExternalBrainAdapter):
    """macOS Gemini 네이티브 앱을 AppleScript로 제어합니다.

    흐름:
    1. Gemini 앱 활성화 (AppleScript)
    2. 키보드 입력으로 프롬프트 전송 (keystroke)
    3. 응답 대기 → 클립보드를 통해 텍스트 추출
    """

    APP_NAME: str = "Gemini"
    BUNDLE_ID: str = "com.google.GeminiMacOS"

    def __init__(self, timeout_sec: float = 120.0):
        """Initialize the GeminiAppAdapter.

        Args:
            timeout_sec (float): float timeout sec.

        """
        super().__init__("gemini_app", timeout_sec)

    @override
    async def is_available(self) -> bool:
        """Gemini 앱이 설치되어 있는지 확인 (실행 중 아니어도 OK)."""
        try:
            # 1) 프로세스 실행 중 확인
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to (name of processes) contains "{self.APP_NAME}"',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "true" in result.stdout.lower():
                self._available = True
                return True
            # 2) 앱 번들 존재 확인 (.app 파일)
            check_app = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{self.BUNDLE_ID}'"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._available = bool(check_app.stdout.strip())
            return self._available
        except Exception:
            logger.exception("Gemini availability check failed")
            self._available = False
            return False

    async def _ensure_window(self):
        """Gemini 창이 없으면 새 채팅 창을 열어줍니다."""
        check_script = f"""tell application "System Events"

            tell process "{self.APP_NAME}"
                return count of windows
            end tell
        end tell"""
        result = subprocess.run(
            ["osascript", "-e", check_script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        win_count: float = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0.0
        if win_count == 0:
            logger.info("Gemini 창이 없으므로 새 대화 창을 엽니다.")
            _ = subprocess.run(
                ["osascript", "-e", f'tell application "{self.APP_NAME}" to activate'],
                capture_output=True,
                timeout=5,
            )
            await asyncio.sleep(1.5)
            _ = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to tell process "{self.APP_NAME}" to keystroke "n" using command down',  # noqa: E501
                ],
                capture_output=True,
                timeout=5,
            )
            await asyncio.sleep(2)

    @override
    async def send(self, prompt: str) -> BrainResponse:
        """Gemini 앱에 프롬프트를 보내고 응답을 받습니다."""
        start = time.time()

        try:
            if not await self.is_available():
                # 앱 실행 시도
                _ = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'tell application "{self.APP_NAME}" to activate',
                    ],
                    capture_output=True,
                    timeout=10,
                )
                await asyncio.sleep(3)

            # 0. 창이 없으면 열기
            await self._ensure_window()

            # 1. Gemini 앱 활성화 + 포커스
            _ = subprocess.run(
                ["osascript", "-e", f'tell application "{self.APP_NAME}" to activate'],
                capture_output=True,
                timeout=5,
            )
            await asyncio.sleep(0.5)

            # 2. 프롬프트 입력 (키보드 시뮬레이션)
            # 특수문자 이스케이프 처리
            escaped_prompt = prompt.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

            # 클립보드를 통한 안전한 텍스트 입력
            input_script = f"""
                set the clipboard to "{escaped_prompt}"

                tell application "System Events"
                    tell process "{self.APP_NAME}"
                        set frontmost to true
                        delay 0.3
                        keystroke "v" using command down
                        delay 0.3
                        keystroke return
                    end tell
                end tell
            """
            _ = subprocess.run(["osascript", "-e", input_script], capture_output=True, timeout=15)

            # 3. 응답 대기 (polling 방식)
            response_text = await self._wait_for_response(prompt)
            latency = (time.time() - start) * 1000

            if response_text:
                return BrainResponse(
                    text=response_text,
                    source=self.name,
                    latency_ms=latency,
                    success=True,
                )
            else:
                return BrainResponse(
                    text="",
                    source=self.name,
                    latency_ms=latency,
                    success=False,
                    error="Gemini 응답 추출 실패 (timeout)",
                )

        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.exception("GeminiApp send failed")
            return BrainResponse(
                text="",
                source=self.name,
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    async def _wait_for_response(self, prompt: str) -> str:
        """Gemini 앱의 응답을 Accessibility API로 추출합니다.

        응답이 안정화(스트리밍 완료)될 때까지 polling합니다.
        """
        max_wait = self.timeout_sec
        poll_interval = 2.0
        elapsed: float = 0.0
        last_text = ""
        stable_count = 0

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # 방법 1: Cmd+A → Cmd+C (전체 선택 → 클립보드)로 텍스트 추출
            extract_script = f"""tell application "System Events"

                tell process "{self.APP_NAME}"
                    set frontmost to true
                    keystroke "a" using command down
                    delay 0.3
                    keystroke "c" using command down
                    delay 0.3
                end tell
            end tell
            return (the clipboard as text)"""

            try:
                result = subprocess.run(
                    ["osascript", "-e", extract_script],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                current_text = result.stdout.strip()

                # 프롬프트 자체는 제외하고 응답만 추출
                if current_text and len(current_text) > len(prompt):
                    # 프롬프트 이후의 텍스트를 응답으로 간주
                    idx = current_text.find(prompt)
                    if idx >= 0:
                        response_part = current_text[idx + len(prompt) :].strip()
                    else:
                        response_part = current_text

                    if response_part and response_part == last_text:
                        stable_count += 1
                        if stable_count >= 2:
                            return response_part
                    else:
                        stable_count = 0
                        last_text = response_part
                elif current_text:
                    if current_text == last_text:
                        stable_count += 1
                        if stable_count >= 2:
                            return current_text
                    else:
                        stable_count = 0
                        last_text = current_text

            except Exception as e:
                logger.exception("Unhandled exception")
                logger.debug("Response extraction attempt failed: %s", e)
                continue

        return last_text or ""


# ─── ChatGPT Web 어댑터 (Playwright) ──────────────────────────


@final
class ChatGPTWebAdapter(ExternalBrainAdapter):
    """ChatGPT 웹 버전을 Playwright로 제어합니다.

    흐름:
    1. Chrome 프로필/쿠키로 자동 로그인
    2. chat.openai.com 접속
    3. textarea에 프롬프트 입력 → 전송
    4. 응답 DOM 요소 감시 → 텍스트 추출
    """

    CHATGPT_URL: str = "https://chatgpt.com"

    def __init__(self, timeout_sec: float = 120.0, cookies_path: str = ""):
        """Initialize the ChatGPTWebAdapter.

        Args:
            timeout_sec (float): float timeout sec.
            cookies_path (str): str cookies path.

        """
        super().__init__("chatgpt_web", timeout_sec)
        self.cookies_path: str = cookies_path
        self._browser: object | None = None
        self._page: _PageLike | None = None

    @override
    async def is_available(self) -> bool:
        """Playwright가 설치되어 있는지 확인."""
        self._available = importlib.util.find_spec("playwright.async_api") is not None
        return self._available

    @override
    async def send(self, prompt: str) -> BrainResponse:
        """ChatGPT 웹에 프롬프트를 보내고 응답을 받습니다."""
        from playwright.async_api import async_playwright

        start = time.time()

        try:
            async with async_playwright() as p:
                # Chrome 프로필 사용 시 잠금 방지: 별도 임시 프로필에 쿠키 복사
                import shutil
                import tempfile

                original_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
                # 임시 디렉토리에 Default 프로필 쿠키만 복사
                temp_dir = tempfile.mkdtemp(prefix="agk_chrome_")
                try:
                    cookie_src = os.path.join(original_dir, "Default", "Cookies")
                    if not personal_profile_allowed():
                        # 사용자 Chrome 쿠키를 읽는 것은 **개인 프로필 사용**이다(task 16).
                        # 기본은 격리된 빈 프로필이고, 쓰려면 명시 동의가 필요하다.
                        logger.info(
                            "[Browser] personal Chrome cookies were NOT read; set %s=1 to opt in",
                            PERSONAL_PROFILE_ENV,
                        )
                    elif os.path.exists(cookie_src):
                        os.makedirs(os.path.join(temp_dir, "Default"), exist_ok=True)
                        _ = shutil.copy2(cookie_src, os.path.join(temp_dir, "Default", "Cookies"))
                except Exception:
                    logger.exception("Unhandled exception")
                    pass  # 쿠키 복사 실패 시 빈 프로필 사용

                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=temp_dir,
                    headless=False,  # ChatGPT는 headless 차단 가능
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                )

                # 이미 열려 있는 페이지(사용자 개인 Chrome/CDP 탭)를 **채택하지 않는다**(task 16).
                # 남의 탭을 자동화에 끌어들이는 대신 항상 새 페이지를 열고, 무시한 탭은 기록한다.
                _ = get_browser_session_owner().remember_foreign_pages(list(browser.pages))
                page = await browser.new_page()
                _ = await page.goto(self.CHATGPT_URL, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # 입력란 찾기 (2026 ChatGPT UI 대응)
                input_sel = '#prompt-textarea, textarea[data-id], div[contenteditable="true"], div.ProseMirror'
                input_el = await page.wait_for_selector(input_sel, timeout=10000)

                if not input_el:
                    raise Exception("ChatGPT 입력란을 찾을 수 없습니다")

                # 프롬프트 입력
                await input_el.fill(prompt)
                await asyncio.sleep(0.5)

                # 전송 (Enter 또는 전송 버튼)
                await input_el.press("Enter")

                # 응답 대기 — 스트리밍 완료 시점 감지
                response_text = await self._wait_for_chatgpt_response(page)

                latency = (time.time() - start) * 1000
                await browser.close()
                # 임시 프로필 정리
                try:
                    _ = shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    logger.exception("Unhandled exception")
                    pass

                return BrainResponse(
                    text=response_text,
                    source=self.name,
                    latency_ms=latency,
                    success=bool(response_text),
                    error="" if response_text else "응답 추출 실패",
                )

        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.exception("ChatGPT web send failed")
            return BrainResponse(
                text="",
                source=self.name,
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    async def _wait_for_chatgpt_response(self, page: object) -> str:
        """ChatGPT 응답이 완료될 때까지 DOM을 polling합니다."""
        page_like = cast(_PageLike, page)
        max_wait = self.timeout_sec
        poll_interval = 2.0
        elapsed: float = 0.0
        last_text = ""
        stable_count = 0

        # 빠른 종료 조건: "Copy" 버튼 등이 나타나면 생성 완료로 간주
        completion_selectors = [
            'button[aria-label="Copy"]',
            'button[aria-label="Regenerate"]',
            ".result-streaming-stopped",
        ]

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                # 캡챠나 네트워크 에러 등 감지
                error_el = await page_like.query_selector(
                    '.text-red-500, .error-message, div[data-testid="captcha"]',
                )
                if error_el:
                    err_text = await error_el.inner_text()
                    raise Exception(f"ChatGPT Web Error detected: {err_text}")

                # 빠른 DOM 기반 생성 완료 체크
                for sel in completion_selectors:
                    if await page_like.query_selector(sel):
                        # 완료 마커를 찾았으므로 즉시 텍스트 추출
                        messages = await page_like.query_selector_all(
                            '[data-message-author-role="assistant"], .markdown.prose, .agent-turn',
                        )
                        if messages:
                            return (await messages[-1].inner_text()).strip()

                # Fallback: 기존의 Text Polling (길이 변화 없음 감지)
                messages = await page_like.query_selector_all(
                    '[data-message-author-role="assistant"], .markdown.prose, .agent-turn,'
                    + 'article[data-testid^="conversation-turn"]',
                )
                if messages:
                    last_msg = messages[-1]
                    current_text = (await last_msg.inner_text()).strip()

                    if current_text and current_text == last_text:
                        stable_count += 1
                        if stable_count >= 3:  # 2->3으로 늘려 안정성 증대
                            return current_text
                    else:
                        stable_count = 0
                        last_text = current_text
            except Exception as e:
                if "ChatGPT Web Error detected" in str(e):
                    raise
                continue

        return last_text or ""


# ─── Gemini Web 어댑터 (Playwright) ───────────────────────────


@final
class GeminiWebAdapter(ExternalBrainAdapter):
    """Gemini 웹 버전을 Playwright로 제어합니다 (앱 대안)."""

    GEMINI_URL: str = "https://gemini.google.com"

    def __init__(self, timeout_sec: float = 120.0):
        """Initialize the GeminiWebAdapter.

        Args:
            timeout_sec (float): float timeout sec.

        """
        super().__init__("gemini_web", timeout_sec)

    @override
    async def is_available(self) -> bool:
        """Check if available.

        Returns:
            bool: The bool result.

        """
        self._available = importlib.util.find_spec("playwright.async_api") is not None
        return self._available

    @override
    async def send(self, prompt: str) -> BrainResponse:
        """Send.

        Args:
            prompt (str): str prompt.

        Returns:
            BrainResponse: The brainresponse result.

        """
        from playwright.async_api import async_playwright

        start = time.time()

        try:
            async with async_playwright() as p:
                import tempfile

                if personal_profile_allowed():
                    user_data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
                else:
                    # 개인 프로필은 명시 동의가 있을 때만 연다(task 16) — 기본은 격리된 임시 프로필.
                    user_data_dir = tempfile.mkdtemp(prefix="agk_gemini_profile_")
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                )
                _ = get_browser_session_owner().remember_foreign_pages(list(browser.pages))
                page = await browser.new_page()
                _ = await page.goto(self.GEMINI_URL, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # 입력란
                input_el = await page.wait_for_selector(
                    'div[contenteditable="true"], .ql-editor, rich-textarea, .input-area-container textarea',
                    timeout=10000,
                )
                if not input_el:
                    raise Exception("Gemini 입력란을 찾을 수 없습니다")

                await input_el.fill(prompt)
                await asyncio.sleep(0.5)
                await input_el.press("Enter")

                # 응답 대기
                response_text = await self._wait_for_response(page)
                latency = (time.time() - start) * 1000
                await browser.close()

                return BrainResponse(
                    text=response_text,
                    source=self.name,
                    latency_ms=latency,
                    success=bool(response_text),
                )
        except Exception as e:
            logger.exception("Unhandled exception")
            latency = (time.time() - start) * 1000
            return BrainResponse(
                text="",
                source=self.name,
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    async def _wait_for_response(self, page: object) -> str:
        page_like = cast(_PageLike, page)
        max_wait = self.timeout_sec
        elapsed = 0
        last_text = ""
        stable_count = 0

        # Gemini 빠른 완료 체크용 셀렉터 (Thumb up/down 액션바)
        completion_selectors = [
            'button[aria-label="Good response"]',
            'button[aria-label="Bad response"]',
            'button[aria-label="Share"]',
            "div.action-bar",
        ]

        while elapsed < max_wait:
            await asyncio.sleep(2)
            elapsed += 2
            try:
                # 에러 감지
                error_el = await page_like.query_selector(".error-container, .alert-error")
                if error_el:
                    err_text = await error_el.inner_text()
                    raise Exception(f"Gemini Web Error detected: {err_text}")

                # 빠른 완료 감지
                for sel in completion_selectors:
                    if await page_like.query_selector(sel):
                        msgs = await page_like.query_selector_all(
                            ".model-response-text, .response-container, message-content, .response-content",
                        )
                        if msgs:
                            return (await msgs[-1].inner_text()).strip()

                msgs = await page_like.query_selector_all(
                    ".model-response-text, .response-container, message-content, .response-content",
                )
                if msgs:
                    current = (await msgs[-1].inner_text()).strip()
                    if current and current == last_text:
                        stable_count += 1
                        if stable_count >= 3:
                            return current
                    else:
                        stable_count = 0
                        last_text = current
            except Exception as e:
                if "Gemini Web Error detected" in str(e):
                    raise
                continue
        return last_text or ""


# ─── 외부 두뇌 라우터 ─────────────────────────────────────────


@final
class ExternalBrainRouter:
    """여러 외부 두뇌 어댑터를 관리하고 라우팅합니다.

    전략:
    - fallback: 첫 번째 가용 두뇌 사용, 실패 시 다음으로
    - round-robin: 순환 사용
    - compare: 여러 두뇌에 동시 전송, 결과 비교
    """

    def __init__(self, adapters: list[ExternalBrainAdapter] | None = None):
        """Initialize the ExternalBrainRouter.

        Args:
            adapters (list[ExternalBrainAdapter]): list[ExternalBrainAdapter] adapters.

        """
        self.adapters: list[ExternalBrainAdapter] = (
            adapters
            if adapters is not None
            else [
                GeminiAppAdapter(),
                ChatGPTWebAdapter(),
                GeminiWebAdapter(),
            ]
        )
        self._round_robin_idx: int = 0

    async def send(
        self,
        prompt: str,
        strategy: str = "fallback",
        target: str = "",
    ) -> BrainResponse:
        """프롬프트를 외부 두뇌에 전송합니다."""
        # 특정 타겟 지정
        if target:
            adapter = next((a for a in self.adapters if a.name == target), None)
            if adapter and await adapter.is_available():
                return await adapter.send(prompt)
            return BrainResponse(
                text="",
                source=target,
                success=False,
                error=f"'{target}' 어댑터를 찾을 수 없거나 사용 불가",
            )

        if strategy == "fallback":
            return await self._send_fallback(prompt)
        elif strategy == "round-robin":
            return await self._send_round_robin(prompt)
        elif strategy == "compare":
            return await self._send_compare(prompt)
        else:
            return await self._send_fallback(prompt)

    async def _send_fallback(self, prompt: str) -> BrainResponse:
        for adapter in self.adapters:
            if await adapter.is_available():
                response = await adapter.send(prompt)
                if response.success:
                    return response
                logger.warning("[%s] 실패, 다음 두뇌로 폴백", adapter.name)
        return BrainResponse(
            text="",
            source="none",
            success=False,
            error="모든 외부 두뇌 사용 불가",
        )

    async def _send_round_robin(self, prompt: str) -> BrainResponse:
        available = [a for a in self.adapters if await a.is_available()]
        if not available:
            return BrainResponse(text="", source="none", success=False, error="가용 두뇌 없음")

        idx = self._round_robin_idx % len(available)
        self._round_robin_idx += 1
        return await available[idx].send(prompt)

    async def _send_compare(self, prompt: str) -> BrainResponse:
        """여러 두뇌에 동시 전송하고 결과를 비교합니다."""
        available = [a for a in self.adapters if await a.is_available()]
        if not available:
            return BrainResponse(text="", source="none", success=False, error="가용 두뇌 없음")

        tasks = [a.send(prompt) for a in available]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful: list[BrainResponse] = []
        for r in results:
            if isinstance(r, BrainResponse) and r.success:
                successful.append(r)

        if not successful:
            return BrainResponse(text="", source="compare", success=False, error="모든 비교 실패")

        # 비교 리포트 생성
        compare_text = "## 🧠 외부 두뇌 비교 결과\n\n"
        for r in successful:
            compare_text += f"### [{r.source}] ({r.latency_ms:.0f}ms)\n{r.text}\n\n---\n\n"

        return BrainResponse(
            text=compare_text,
            source="compare",
            latency_ms=max(r.latency_ms for r in successful),
            success=True,
        )

    async def list_available(self) -> list[dict[str, object]]:
        """사용 가능한 외부 두뇌 목록을 반환합니다."""
        result: list[dict[str, object]] = []
        for adapter in self.adapters:
            available = await adapter.is_available()
            result.append(
                {
                    "name": adapter.name,
                    "available": available,
                    "timeout_sec": adapter.timeout_sec,
                },
            )
        return result
