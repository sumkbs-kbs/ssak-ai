"""Ssak-Ai: Browser Surfing Agent.

======================================
Vision-Language 기반 자율 웹 브라우징 에이전트.
Playwright를 제어하며 화면 스크린샷과 DOM 트리를 바탕으로
LLM(qwen3.6:latest)이 상호작용(클릭, 스크롤, 추출)을 판단합니다.
"""

import asyncio
import base64
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, cast, final

from antigravity_k.tools.browser_observation import (
    BrowserObservationError,
    drop_browser_observer,
    observer_for_owner,
)
from antigravity_k.tools.browser_session_owner import (
    current_browser_owner,
    get_browser_session_owner,
)


class _MouseLike(Protocol):
    async def wheel(self, delta_x: float, delta_y: float) -> object: ...


class _PageLike(Protocol):
    mouse: _MouseLike

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> object: ...

    async def screenshot(self, *, type: str, quality: int) -> object: ...

    async def wait_for_load_state(self, state: str, *, timeout: int) -> object: ...

    async def evaluate(self, expression: str) -> object: ...

    async def close(self) -> object: ...


class _ContextLike(Protocol):
    async def new_page(self) -> _PageLike: ...

    async def close(self) -> object: ...


class _BrowserLike(Protocol):
    async def new_page(self) -> _PageLike: ...

    async def new_context(self) -> _ContextLike: ...

    async def close(self) -> object: ...


class _ChromiumLike(Protocol):
    async def launch(self, *, headless: bool) -> _BrowserLike: ...


class _PlaywrightLike(Protocol):
    chromium: _ChromiumLike

    async def stop(self) -> object: ...


class _PlaywrightController(Protocol):
    async def start(self) -> _PlaywrightLike: ...


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> str: ...

    def generate(self, **kwargs: object) -> object: ...


async_playwright: Callable[[], _PlaywrightController] | None
try:
    from playwright.async_api import async_playwright as _async_playwright
except ImportError:
    async_playwright = None
else:
    async_playwright = cast(Callable[[], _PlaywrightController], _async_playwright)

logger = logging.getLogger("browser_agent")


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_action_data(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


async def _resolve_response(value: object) -> object:
    if inspect.isawaitable(value):
        return await cast(Awaitable[object], value)
    return value


def _response_text(value: object) -> str:
    if isinstance(value, str):
        return value
    text_value = getattr(value, "text", None)
    return text_value if isinstance(text_value, str) else str(value)


@dataclass
class BrowserAction:
    """Represents a single browser navigation or interaction action."""

    action: str  # "click", "scroll_down", "extract", "done"
    target_ref: str = ""
    reason: str = ""
    extracted_data: str = ""


@final
class BrowserSurfingAgent:
    """Playwright + Vision LLM 연동 자율 웹 서퍼."""

    def __init__(
        self,
        model_manager: _ModelManagerLike | None = None,
        vision_model_name: str = "qwen3.6:latest",
    ):
        """Initialize the BrowserSurfingAgent.

        Args:
            model_manager: model manager.
            vision_model_name (str): str vision model name.

        """
        self.model_manager: _ModelManagerLike | None = model_manager
        self.vision_model_name: str = vision_model_name
        self._browser: _BrowserLike | None = None
        self._playwright: _PlaywrightLike | None = None

    async def _init_browser(self) -> None:
        if async_playwright is None:
            raise ImportError("playwright is not installed. Run `pip install playwright`")

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None:
            assert self._playwright is not None
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def _close_browser(self) -> None:
        if self._browser:
            _ = await self._browser.close()
            self._browser = None
        if self._playwright:
            _ = await self._playwright.stop()
            self._playwright = None

    async def surf(self, url: str, goal: str, max_steps: int = 5) -> str:
        """주어진 URL로 이동하여 목표(goal)를 달성하기 위해 브라우저를 탐색합니다.

        Args:
            url: 시작 URL
            goal: 에이전트가 찾아야 하는 정보나 달성해야 하는 목표
            max_steps: 최대 행동 횟수

        Returns:
            추출된 텍스트 결과

        """
        await self._init_browser()
        final_result = ""

        page = None
        context = None
        session_owner = get_browser_session_owner()
        browser_owner = current_browser_owner()
        reservation = None
        committed = False
        try:
            # 다른 진입점과 같은 egress 규칙(task 16) — 서퍼가 아무 주소나 열게 두지 않는다.
            _ = session_owner.validate_navigation(url)
            # 세션 자리를 소유자에게 받는다(상한을 넘으면 여기서 거절된다).
            reservation = session_owner.begin(browser_owner, purpose="browser_surfing_agent")
            if reservation.is_reuse:
                reuse = reservation.reuse
                assert reuse is not None
                page = cast(_PageLike, reuse.page)
                lease = reuse
            else:
                if self._browser is None:
                    return "Error: Browser not initialized"
                # 격리된 일회용 컨텍스트 — 사용자 프로필/기존 페이지를 쓰지 않는다.
                context = await self._browser.new_context()
                _ = session_owner.remember_foreign_pages(list(getattr(context, "pages", []) or []))
                page = await context.new_page()
                lease = session_owner.commit(reservation, page=page)
                committed = True
            assert page is not None
            # model 에게 보이는 것은 **관찰**과 그 관찰이 발급한 ref 뿐이다(selector·JS 는 계약에 없다).
            observer = observer_for_owner(browser_owner, lease=lease)
            _ = await page.goto(url, wait_until="networkidle", timeout=15000)

            step = 0
            while step < max_steps:
                step += 1
                logger.info("[BrowserSurfing] Step %s: Analyzing page state...", step)

                # 1. 페이지 상태 분석 (스크린샷 및 관찰 요약)
                screenshot_value = await page.screenshot(type="jpeg", quality=60)
                screenshot_bytes = screenshot_value if isinstance(screenshot_value, bytes) else b""
                observation = await observer.observe()
                dom_summary = observation.to_summary()

                # 2. Vision 모델에 상태 전달 후 다음 행동 결정
                action = await self._decide_next_action(goal, dom_summary, screenshot_bytes)
                logger.info(
                    "[BrowserSurfing] Action decided: %s (Reason: %s)",
                    action.action,
                    action.reason,
                )

                # 3. 행동 실행 — ref 는 **방금 관찰**의 것이어야 한다(모델이 selector 를 지어내도 문이 없다).
                if action.action == "click" and action.target_ref:
                    try:
                        outcome = await observer.act("click", ref=action.target_ref)
                    except BrowserObservationError as exc:
                        # 낡은/없는 ref 는 계약이 거절한 것이다. 다음 루프에서 다시 관찰한다.
                        logger.warning("[BrowserSurfing] ref rejected (%s): %s", exc.code, exc)
                        continue
                    if not outcome.goal_verified:
                        logger.info("[BrowserSurfing] click performed without a verified effect: %s", outcome.detail)

                elif action.action == "scroll_down":
                    _ = await observer.act("scroll", delta=800)
                    await asyncio.sleep(1)

                elif action.action == "extract":
                    final_result = action.extracted_data
                    break

                elif action.action == "done":
                    break

                else:
                    logger.warning("Unknown action: %s", action.action)

            # 명시적 추출이 없었을 경우 대비 폴백
            if not final_result:
                evaluated = await page.evaluate("document.body.innerText")
                final_result = evaluated if isinstance(evaluated, str) else str(evaluated)

        except Exception as e:
            logger.exception("Browser surfing error on %s", url)
            final_result = f"Error during surfing: {e}"
        finally:
            if reservation is not None and not reservation.is_reuse:
                # 이 번 탐색이 연 세션은 이 번에 닫는다(소유자 원장에서도 빠진다).
                if context is not None:
                    _ = await context.close()
                _ = drop_browser_observer(browser_owner)
                if committed:
                    _ = session_owner.release(browser_owner)
                else:
                    # launch/이동이 실패했으면 **예약만** 돌려준다 — 안 그러면 자리가 남은 채
                    # deadline 까지 아무도 그 슬롯을 못 쓴다.
                    session_owner.abort(reservation)
            await self._close_browser()

        return final_result

    async def _decide_next_action(
        self,
        goal: str,
        dom_summary: str,
        screenshot_bytes: bytes,
    ) -> BrowserAction:
        """Vision 모델을 호출하여 다음 브라우저 액션을 결정합니다.

        실제 환경에서는 self.model_manager.generate()에 이미지를 첨부합니다.
        """
        if not self.model_manager:
            # Mock behavior if model manager is not injected
            return BrowserAction(action="extract", extracted_data="[Mock Data] " + goal)

        prompt = f"""
        당신은 자율 웹 서핑 에이전트입니다.

        현재 목표: {goal}

        아래는 현재 화면의 관찰 결과입니다(ref 는 **이 관찰에서만** 유효한 opaque 핸들입니다):
        {dom_summary}

        다음 중 하나의 액션을 JSON 형식으로 선택하세요:
        1. {{"action": "click", "ref": "<위 목록의 ref>", "reason": "..."}}
        2. {{"action": "scroll_down", "reason": "..."}}
        3. {{"action": "extract", "extracted_data": "<최종 텍스트 요약>", "reason": "..."}}
        4. {{"action": "done", "reason": "더 이상 진행할 수 없거나 목표 달성"}}

        ref 외의 selector·XPath·JavaScript 는 받아들여지지 않습니다.
        JSON 포맷으로만 응답하세요.
        """

        try:
            target = self.vision_model_name
            if target == "qwen3.6:latest":
                target = self.model_manager.get_target_for_role("vision", default_role="vision")
            raw_response = await asyncio.to_thread(
                self.model_manager.generate,
                prompt=prompt,
                target=target,
                system_prompt="You are a JSON-only visual browsing agent.",
                raw_messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [base64.b64encode(screenshot_bytes).decode("ascii")],
                    },
                ],
                max_tokens=512,
                temperature=0.2,
            )
            response = await _resolve_response(raw_response)

            # JSON 파싱 (간단화)
            text = _response_text(response)
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()

            decoded = cast(object, json.loads(text))
            data = _as_action_data(decoded)
            return BrowserAction(
                action=_as_text(data.get("action"), "done"),
                target_ref=_as_text(data.get("ref")),
                reason=_as_text(data.get("reason")),
                extracted_data=_as_text(data.get("extracted_data")),
            )
        except Exception as e:
            logger.exception("Vision model decision failed")
            return BrowserAction(action="done", reason=f"Model error: {e}")
