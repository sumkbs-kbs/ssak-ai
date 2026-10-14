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
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Protocol, cast, final

from antigravity_k.agents.browser_task_loop import (
    MODEL_UNAVAILABLE,
    BrowserTaskError,
    BrowserTaskLoop,
    LoopHost,
    ModelPlanner,
    PlannedAction,
    Planner,
    TaskBlocked,
    TaskBudget,
    TaskGoal,
    TaskMeasurement,
    TaskOutcome,
    TaskRetryable,
    TaskStatus,
    TaskStep,
)
from antigravity_k.engine.approval_manager import ApprovalStatus, get_approval_manager
from antigravity_k.tools.browser_approval import (
    ApprovalBinding,
    Effect,
    EffectDecision,
    classify_effect,
    detect_user_handoff,
    get_browser_approval_gate,
    origin_of,
    payload_fingerprint,
    summarize_effect,
)
from antigravity_k.tools.browser_observation import (
    ActionResult,
    BrowserObservationError,
    Observation,
    drop_browser_observer,
    observer_for_owner,
)
from antigravity_k.tools.browser_session_owner import (
    BrowserOwner,
    BrowserSessionOwner,
    SessionReservation,
    current_browser_owner,
    get_browser_session_owner,
)
from antigravity_k.tools.browser_task_journal import BrowserTaskJournal, ResumePlan
from antigravity_k.tools.browser_task_memory import site_of

# 승인 요청을 등록할 도구 이름(task 18). API 경로와 **같은 이름**을 쓴다 — 일반 도구 승인의
# "항상 허용" 목록에 이 이름이 있으면 브라우저 효과를 자동 승인해 버리므로, 그 경우에는
# 실행하지 않고 멈춘다.
_BROWSER_EFFECT_TOOL = "browser_effect"


class _ObserverFactLike(Protocol):
    """승인 판정에 필요한 **서버가 본 사실**만 요구한다(관찰자 전체를 요구하지 않는다)."""

    session_tag: str

    def element_fact(self, ref: str | None, page_key: str | None = None) -> dict[str, object] | None: ...


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


class _LoopObserverLike(Protocol):
    """루프 호스트가 쓰는 관찰자 표면 — 관찰·행동·사실 조회."""

    session_tag: str
    policy: object

    def element_fact(self, ref: str | None, page_key: str | None = None) -> dict[str, object] | None: ...

    async def observe(self) -> Observation: ...

    async def act(
        self,
        action: str,
        *,
        ref: str | None = None,
        url: str | None = None,
        text: str | None = None,
        value: str | None = None,
        path: str | None = None,
        delta: int = 800,
        page_key: str | None = None,
    ) -> ActionResult: ...


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


@dataclass
class _SurfSession:
    """`surf` 와 `run_task` 가 공유하는 세션 수명 상태(획득과 반납이 한 모양이 되게)."""

    owner: BrowserOwner
    session_owner: BrowserSessionOwner | None = None
    reservation: SessionReservation | None = None
    page: _PageLike | None = None
    observer: object | None = None
    context: object | None = None
    committed: bool = False
    reused: bool = False
    released: bool = False


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

    async def _open_session(self, url: str) -> _SurfSession:
        """egress 검사 → 소유자에게 자리 예약 → (재사용 또는 일회용 컨텍스트) → 관찰자.

        `surf` 와 `run_task` 가 **같은** 세션 수명 규칙을 지나게 한 곳으로 모은다(task 19).
        """
        session_owner = get_browser_session_owner()
        owner = current_browser_owner()
        # 다른 진입점과 같은 egress 규칙(task 16) — 서퍼가 아무 주소나 열게 두지 않는다.
        _ = session_owner.validate_navigation(url)
        # 세션 자리를 소유자에게 받는다(상한을 넘으면 여기서 거절된다).
        reservation = session_owner.begin(owner, purpose="browser_surfing_agent")
        session = _SurfSession(owner=owner, session_owner=session_owner, reservation=reservation)
        try:
            if reservation.is_reuse:
                reuse = reservation.reuse
                assert reuse is not None
                session.reused = True
                page = cast(_PageLike, reuse.page)
                lease = reuse
            else:
                if self._browser is None:
                    raise RuntimeError("Browser not initialized")
                # 격리된 일회용 컨텍스트 — 사용자 프로필/기존 페이지를 쓰지 않는다.
                context = await self._browser.new_context()
                _ = session_owner.remember_foreign_pages(list(getattr(context, "pages", []) or []))
                page = await context.new_page()
                lease = session_owner.commit(reservation, page=page)
                session.context = context
                session.committed = True
            # model 에게 보이는 것은 **관찰**과 그 관찰이 발급한 ref 뿐이다(selector·JS 는 계약에 없다).
            session.page = page
            session.observer = observer_for_owner(owner, lease=lease)
        except BaseException:
            await self._release_session(session)
            raise
        return session

    async def _release_session(self, session: _SurfSession) -> None:
        """이 번이 연 세션은 이 번에 닫는다(소유자 원장에서도 빠진다). 예약만 잡힌 경우도 돌려준다."""
        if session.reused or session.released:
            return
        session.released = True
        context = session.context
        if context is not None:
            closer = getattr(context, "close", None)
            if callable(closer):
                _ = await cast("Awaitable[object]", closer())
        _ = drop_browser_observer(session.owner)
        owner_sessions = session.session_owner
        if owner_sessions is None:  # 세션 소유자를 거치지 않은 시험용 세션(상위에서 자리를 쥐고 있다)
            return
        if session.committed:
            _ = owner_sessions.release(session.owner)
        elif session.reservation is not None:
            # launch/이동이 실패했으면 **예약만** 돌려준다 — 안 그러면 자리가 남은 채
            # deadline 까지 아무도 그 슬롯을 못 쓴다.
            owner_sessions.abort(session.reservation)

    async def run_task(
        self,
        url: str,
        goal: TaskGoal,
        *,
        budget: TaskBudget | None = None,
        planner: Planner | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_step: Callable[[TaskStep], None] | None = None,
        journal: BrowserTaskJournal | None = None,
        task_id: str = "",
        idempotency_key: str | None = None,
        memory: object | None = None,
        owner: str = "",
    ) -> TaskOutcome:
        """observe → plan → act → verify 루프를 돌리고 **검증된 결말**을 돌려준다(task 19).

        `surf` 와 다른 점: 결과가 문자열(모델의 주장)이 아니라 `TaskOutcome` 이고, 성공은 완료
        조건을 페이지에서 **측정**했을 때만이다. 모델이 없으면 `MODEL_UNAVAILABLE` 을 그대로 올린다
        (성공을 지어내지 않는다).

        저널을 넘기면(task 20) 작업은 **디스크에** 남는다: 같은 `idempotency_key` 의 두 번째 요청은
        실행되지 않고 기록된 결말을 돌려주고, 미확정인 행동(되돌릴 수 없는 효과를 보냈는데 결과를
        모르는 상태)이 있으면 **자동 재실행을 거부**하고 `UNKNOWN_OUTCOME` 으로 끝난다.

        `memory`(task 21)를 넘기면 **이전에 이 사이트에서 확인된 절차**를 계획의 참고로 올린다. 이때도
        기억은 근거가 아니라 참고다: 성공 판정은 여전히 페이지 측정(task 19)이 한다. 기억이 꺼져 있거나
        동의가 없으면 아무 일도 일어나지 않는다(힌트가 비고, `notes` 도 그대로다). 기억을 **남기는** 일은
        호출자의 몫이다(`record_from_outcome`) — 읽기와 쓰기의 동의는 다르다.
        """
        if planner is None and self.model_manager is None:
            # 브라우저를 띄우거나 세션 자리를 잡기 **전에** 말한다 — 계획할 주체가 없다.
            raise BrowserTaskError(
                MODEL_UNAVAILABLE,
                "no model is configured for browser tasks: set a model or inject a planner",
            )
        active_task_id = task_id or str(idempotency_key or "")
        if journal is not None and active_task_id:
            duplicate = self._resume_or_refuse(journal, active_task_id, goal, idempotency_key=idempotency_key)
            if duplicate is not None:
                return duplicate
        goal = self._goal_with_memory(goal, memory, url, owner=owner)
        active_planner: Planner = planner or ModelPlanner(self.model_manager, vision_model_name=self.vision_model_name)
        async with self.browser_task_host(url) as host:
            loop = BrowserTaskLoop(
                active_planner,
                budget=budget,
                should_cancel=should_cancel,
                on_step=on_step,
                journal=journal,
                task_id=active_task_id if journal is not None else "",
            )
            return await loop.run(goal, host)

    @asynccontextmanager
    async def browser_task_host(self, url: str) -> AsyncIterator[LoopHost]:
        """세션을 열고 주소로 이동한 뒤, 루프가 쓸 호스트를 넘긴다(수명은 이 컨텍스트가 소유한다).

        `run_task` 가 쓰는 것과 **같은** 수명 규칙이다 — 루프를 다른 방식으로 돌리는 호출자
        (재개 하네스·통합 시험)가 세션 획득/반납과 `goto` 를 따로 구현하지 않게 한다.
        """
        await self._init_browser()
        session = await self._open_session(url)
        try:
            page = session.page
            assert page is not None
            # goto **전에** 네트워크 가드를 장착한다(task 23) — 첫 문서 로드 때 이미 서브리소스가 나간다.
            arm = getattr(session.observer, "arm_network_guards", None)
            if callable(arm):
                result = arm()
                if hasattr(result, "__await__"):
                    await cast("Awaitable[None]", result)
            _ = await page.goto(url, wait_until="networkidle", timeout=15000)
            yield _ObserverLoopHost(self, session)
        finally:
            await self._release_session(session)
            await self._close_browser()

    @staticmethod
    def _goal_with_memory(goal: TaskGoal, memory: object | None, url: str, *, owner: str) -> TaskGoal:
        """같은 사이트에서 확인된 절차를 목표의 `notes` 로 올린다(task 21).

        실패해도 작업은 그대로 진행한다(기억은 있으면 좋은 것이지, 필요한 것이 아니다). 소유자 없이는
        물어보지 않는다 — 격리 단위가 없으면 남의 기억을 읽을 수 있기 때문이다.
        """
        hints = getattr(memory, "hints", None)
        if memory is None or not callable(hints) or not owner.strip():
            return goal
        try:
            found = tuple(
                str(line) for line in cast("Iterable[object]", hints(goal.goal, owner=owner, origin=site_of(url)))
            )
        except Exception:  # 기억을 읽지 못하는 것이 작업을 막지는 않는다
            logger.debug("browser task memory hints unavailable", exc_info=True)
            return goal
        if not found:
            return goal
        note = "\n".join(found)
        return replace(goal, notes=f"{goal.notes}\n{note}".strip() if goal.notes else note)

    def _resume_or_refuse(
        self,
        journal: BrowserTaskJournal,
        task_id: str,
        goal: TaskGoal,
        *,
        idempotency_key: str | None = None,
    ) -> TaskOutcome | None:
        """이 작업을 **이어받아도 되는가**. 이어받을 수 없으면 그 사실을 결말로 돌려준다.

        돌려주는 값이 `None` 이면 실행해도 된다(새 작업이거나, 미결 행동이 읽기뿐인 경우).
        돌려주는 값이 있으면 **브라우저를 열지 않는다** — 중복 실행과 자동 재실행을 막는 자리다.
        """
        opened = journal.open_task(
            task_id,
            goal=goal.goal,
            postconditions=[item.to_dict() for item in goal.postconditions],
            idempotency_key=idempotency_key or task_id,
        )
        if not opened.duplicate:
            return None
        # 중복은 **원래 작업**의 이야기를 읽어야 한다 — 방금 온 새 id 는 저널에 없다.
        plan = journal.resume_plan(opened.task_id)
        if plan.finished is not None:
            # 이미 끝난 요청을 다시 받았다 — **실행하지 않고** 그 결말을 그대로 돌려준다.
            return self._recorded_outcome(goal, plan)
        if plan.replay_allowed:
            journal.record_resumed(opened.task_id, must_reobserve=True)
            return None
        return self._recorded_outcome(goal, plan)

    @staticmethod
    def _recorded_outcome(goal: TaskGoal, plan: ResumePlan) -> TaskOutcome:
        """저널이 아는 결말로 `TaskOutcome` 을 만든다(모르는 것은 모른다고 적는다)."""
        finished = plan.finished or {}
        status = TaskStatus.UNKNOWN_OUTCOME
        if plan.phase == "finished" and finished:
            try:
                status = TaskStatus(str(finished.get("status", "")))
            except ValueError:  # 알 수 없는 상태 문자열은 실패로 읽는다(성공으로 승격하지 않는다)
                status = TaskStatus.FAILED
        return TaskOutcome(
            goal=goal.goal,
            status=status,
            code=plan.code,
            reason=plan.reason,
            postconditions=(),
            steps=(),
            actions_performed=int(cast("int", finished.get("actions") or 0)),
            elapsed_seconds=0.0,
            tokens_used=0,
            cancel_mode="" if plan.cancel is None else "cooperative",
            forced_shutdown=plan.phase == "unknown_outcome",
        )

    async def surf(self, url: str, goal: str, max_steps: int = 5) -> str:
        """주어진 URL로 이동하여 목표(goal)를 달성하기 위해 브라우저를 탐색합니다.

        Args:
            url: 시작 URL
            goal: 에이전트가 찾아야 하는 정보나 달성해야 하는 목표
            max_steps: 최대 행동 횟수

        Returns:
            추출된 텍스트 결과 — **모델의 주장**이다(측정으로 검증하지 않는다). 검증된 결말이
            필요한 호출자는 `run_task` 를 쓴다.

        """
        if self.model_manager is None:
            # 모델이 없으면 계획할 주체가 없다 — 브라우저를 띄우기 전에 그 사실을 말한다
            # (예전에는 `[Mock Data] <goal>` 을 돌려주며 성공한 척했다).
            return f"Error: {MODEL_UNAVAILABLE} — no model is configured for browser surfing: set a model and retry"
        await self._init_browser()
        final_result = ""

        session = await self._open_session(url)
        page = session.page
        assert page is not None
        observer = cast(_LoopObserverLike, session.observer)
        browser_owner = session.owner
        try:
            # goto 전 가드 장착(browser_task_host 와 같은 규칙).
            arm = getattr(observer, "arm_network_guards", None)
            if callable(arm):
                result = arm()
                if hasattr(result, "__await__"):
                    await cast("Awaitable[None]", result)
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
                    # 사람이 해야 하는 단계(MFA·CAPTCHA)면 멈춘다 — 자동으로 넘길 수 없는 일이다.
                    handoff = await detect_user_handoff(page)
                    if handoff is not None:
                        final_result = (
                            f"waiting_user({handoff.kind}): {handoff.reason} "
                            "(자동 재시도 없음 — 사람이 끝낸 뒤 다시 요청하세요)"
                        )
                        break
                    # 위험도를 **서버가** 요소의 의미로 판정한다(task 18). 승인이 필요한 효과는
                    # 스스로 누르지 않는다 — 사람의 승인 창을 띄우고 멈춘다.
                    blocked = await self._approval_block(
                        observer,
                        browser_owner,
                        action.target_ref,
                        PlannedAction(action="click", ref=action.target_ref),
                    )
                    if blocked is not None:
                        final_result = blocked
                        break
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
            await self._release_session(session)
            await self._close_browser()

        return final_result

    async def _approval_block(
        self,
        observer: _ObserverFactLike,
        browser_owner: BrowserOwner,
        ref: str,
        action: PlannedAction,
    ) -> str | None:
        """승인이 필요한 행동이면 요청을 등록하고 **사람에게 넘기는 문장**을 준다(아니면 None).

        이 에이전트는 자율 루프라 승인 창을 직접 띄울 수 없다. 그래서 할 수 있는 일은
        스스로 누르지 않고 멈추는 것이다 — 무엇을 승인해야 하는지(요청 ID·효과·위험도·문장)를
        남기면 대시보드/승인 API 가 그 요청을 처리하고, 재요청 시 이 ID 로 이어받는다.

        ref 를 가진 행동 전부(click·fill·select·upload)가 이 문을 지난다(task 23) — click 만
        검사하면 "메시지 칸 채우기"·"자동저장 칸 채우기"가 승인 없이 새어 나간다.
        """
        fact = observer.element_fact(ref)
        if fact is None:  # 사실을 못 얻으면 계약이 판정하게 둔다(낡은 ref 등)
            return None
        decision = _classify_fact(action.action, fact)
        if not decision.requires_approval:
            return None
        binding = ApprovalBinding(
            owner_key=browser_owner.key,
            session_tag=str(observer.session_tag),
            origin=origin_of(str(fact.get("url") or "")),
            action=action.action,
            ref=ref,
            payload_hash=payload_fingerprint(
                action=action.action, text=action.text, value=action.value, path=action.path
            ),
            generation=int(cast("int", fact.get("generation") or 0)),
            effect=decision.effect.value,
        )
        summary = summarize_effect(
            decision,
            action=action.action,
            origin=binding.origin,
            name=str(fact.get("name") or ""),
            role=str(fact.get("role") or ""),
        )
        manager_request = get_approval_manager().request_approval(
            tool_name=_BROWSER_EFFECT_TOOL,
            tool_args={
                "origin": binding.origin,
                "action": "click",
                "effect": decision.effect.value,
                "binding": binding.fingerprint[:16],
            },
            risk_level=decision.risk,
            description=summary,
        )
        if manager_request.status is not ApprovalStatus.PENDING:
            return (
                "blocked: every browser effect needs its own approval and 'always allow' is not accepted "
                f"(status={manager_request.status.value})"
            )
        requirement = get_browser_approval_gate().register(
            binding, decision, summary=summary, request_id=manager_request.request_id
        )
        logger.info("[BrowserSurfing] approval required: %s", requirement.summary)
        return (
            f"approval_required(request={requirement.request_id}, effect={decision.effect.value}, "
            f"risk={decision.risk}): {requirement.summary}"
        )

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
            # 예전에는 여기서 `[Mock Data] <goal>` 를 돌려주며 **성공한 척**했다(task 19 이전).
            # 그 문자열은 상위 계층(자율 학습기)에서 "학습한 내용" 으로 소비된다 — 모델이 없으면
            # 계획할 주체가 없다는 사실을 숨기지 않는다.
            raise BrowserTaskError(
                MODEL_UNAVAILABLE,
                "no model is configured for browser surfing: set a model before asking for a browsing task",
            )

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


#: 사후조건 판정에 쓰는 표식(`document.body.dataset.*`)을 그대로 읽는다.
_DATASET_JS: Final = (
    "(() => { const out = {}; const body = document.body; const data = body && body.dataset; "
    "if (data) { for (const key of Object.keys(data)) { out[key] = String(data[key]); } } return out; })()"
)
_BODY_TEXT_JS: Final = "document.body ? document.body.innerText : ''"


async def _evaluate(page: object, expression: str) -> object:
    """페이지 평가는 **실패해도 작업을 죽이지 않는다**(측정 불가 = 근거 없음 → partial/failed)."""
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return None
    try:
        value = evaluate(expression)
        if inspect.isawaitable(value):
            value = await cast("Awaitable[object]", value)
    except Exception:
        logger.debug("page evaluate failed: %s", expression, exc_info=True)
        return None
    return value


def _as_flags(value: object) -> Mapping[str, str]:
    """dataset 을 dict 로 정규화한다(문자열 JSON 도 받아 준다)."""
    if isinstance(value, Mapping):
        raw = cast("Mapping[object, object]", value)
        return {str(key): str(item) for key, item in raw.items()}
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        if isinstance(decoded, Mapping):
            raw = cast("Mapping[object, object]", decoded)
            return {str(key): str(item) for key, item in raw.items()}
    return {}


def _classify_fact(action: str, fact: Mapping[str, object]) -> EffectDecision:
    """요소의 **사실**로 효과를 판정하는 한 곳(task 18 의 분류를 승인과 저널이 함께 쓴다).

    두 곳이 각자 분류하면 "승인은 필요 없는데 저널은 위험하다고 보는" 어긋남이 생긴다.
    """
    return classify_effect(
        action,
        role=str(fact.get("role") or ""),
        name=str(fact.get("name") or ""),
        tag=str(fact.get("tag") or ""),
        url=str(fact.get("url") or ""),
        secret=bool(fact.get("secret")),
        disabled=bool(fact.get("disabled")),
        eager=bool(fact.get("eager")),
    )


@final
class _ObserverLoopHost:
    """루프가 브라우저를 만지는 유일한 통로: 관찰·행동·**측정**.

    `act` 는 사람이 필요한 경우(승인·MFA/CAPTCHA) `TaskBlocked` 를, 계약이 거절했지만 다시
    관찰하면 회복될 수 있는 경우(낡은 ref 등) `TaskRetryable` 을 던진다 — 루프는 그 둘을
    성공으로 접지 않는다.
    """

    def __init__(self, agent: BrowserSurfingAgent, session: _SurfSession) -> None:
        page = session.page
        assert page is not None
        self._agent = agent
        self._observer = cast(_LoopObserverLike, session.observer)
        self._page = page
        self._owner = session.owner

    async def observe(self) -> Observation:
        return await self._observer.observe()

    def effect_of(self, action: PlannedAction) -> str:
        """이 행동의 효과를 **요소의 사실**로 판정한다(task 18 의 분류를 그대로 쓴다).

        저널은 이 값을 `되돌릴 수 있는가` 로 읽는다. 사실을 얻지 못하면 빈 문자열을 돌려주고,
        루프가 `unknown`(되돌릴 수 없는 쪽)으로 처리한다 — 모르면 조용히 다시 누르지 않는다.
        """
        if action.action == "goto":
            return Effect.NAVIGATE.value
        if not action.ref:
            return ""
        fact = self._observer.element_fact(action.ref)
        if fact is None:
            return ""
        return _classify_fact(action.action, fact).effect.value

    async def act(self, action: PlannedAction) -> ActionResult:
        if action.action == "click":
            # 사람이 해야 하는 단계(MFA·CAPTCHA)면 수행하지 않는다.
            handoff = await detect_user_handoff(self._page)
            if handoff is not None:
                raise TaskBlocked(
                    f"waiting_user({handoff.kind}): {handoff.reason} — 사람이 끝낸 뒤 다시 요청하세요",
                    kind="handoff",
                )
        # 위험도를 **서버가** 요소의 의미로 판정한다(task 18). 승인이 필요한 효과는 스스로 누르지
        # 않는다 — ref 를 가진 행동 전부가 이 문을 지난다(task 23: fill·select·upload 포함).
        if action.ref and action.action in {"click", "fill", "select", "upload"}:
            blocked = await self._agent._approval_block(self._observer, self._owner, action.ref, action)
            if blocked is not None:
                raise TaskBlocked(blocked, kind="approval")
        try:
            return await self._observer.act(
                action.action,
                ref=action.ref,
                url=action.url,
                text=action.text,
                value=action.value,
                path=action.path,
                delta=action.delta,
            )
        except BrowserObservationError as exc:
            if exc.retryable:
                raise TaskRetryable(f"{exc.code}: {exc}", code=exc.code) from exc
            raise TaskBlocked(f"{exc.code}: {exc}", kind="contract") from exc

    async def measure(self) -> TaskMeasurement:
        """성공 판정의 근거를 **페이지에서** 읽어 온다(모델의 말이 아니라 관찰과 DOM 이다)."""
        observation = await self.observe()
        flags = _as_flags(await _evaluate(self._page, _DATASET_JS))
        text = await _evaluate(self._page, _BODY_TEXT_JS)
        return TaskMeasurement(
            url=observation.url,
            title=observation.title,
            text=text if isinstance(text, str) else "",
            flags=flags,
            ref_names=frozenset(item.name for item in observation.refs),
            downloads=self._downloads(),
            generation=observation.generation,
        )

    def _downloads(self) -> tuple[str, ...]:
        """세션 샌드박스에 실제로 생긴 파일만 센다(다운로드가 목표일 때의 근거)."""
        directory = getattr(getattr(self._observer, "policy", None), "download_dir", None)
        if directory is None:
            return ()
        try:
            return tuple(sorted(item.name for item in Path(directory).iterdir() if item.is_file()))
        except OSError:
            return ()
