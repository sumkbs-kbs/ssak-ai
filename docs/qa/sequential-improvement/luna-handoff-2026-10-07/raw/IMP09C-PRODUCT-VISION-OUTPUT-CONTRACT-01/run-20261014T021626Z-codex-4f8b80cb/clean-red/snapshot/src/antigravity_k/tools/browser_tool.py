"""Ssak-Ai: 브라우저 자동화 도구 (Harness Engineering 적용).

=============================================================
Playwright 기반 브라우저 자동화 + Intent 기반 테스트 + Self-Healing.
에이전트가 브라우저를 열고, 클릭하고, 입력하고, 스크린샷을 찍고,
자연어 의도 기반으로 UI를 검증할 수 있습니다.

v2 업그레이드:
- semantic_snapshot: @ref 인덱싱된 시맨틱 DOM 스냅샷
- click_by_intent: 자연어 의도로 클릭 (CSS 셀렉터 불필요)
- vision_analyze: DOM + 스크린샷 동시 분석
- som_screenshot: Set-of-Mark 마킹된 스크린샷
- detect_obstacles: 팝업/모달/쿠키 배너 자동 감지
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .browser_session_owner import (
    BrowserOwner,
    BrowserSessionLimitError,
    BrowserSessionRefusedError,
    SessionReservation,
    current_browser_owner,
    get_browser_session_owner,
)

logger = logging.getLogger("antigravity_k.tools.browser")

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

    from .semantic_dom import SemanticSnapshot
    from .vision_dom_hybrid import HybridAnalysis

Params = dict[str, object]
A11yNode = Mapping[str, object]


class _DOMParserProtocol(Protocol):
    def snapshot_sync(self, page: Page) -> SemanticSnapshot: ...

    def enrich_with_a11y_sync(self, page: Page, snapshot: SemanticSnapshot) -> SemanticSnapshot: ...

    def to_llm_context(
        self,
        snapshot: SemanticSnapshot,
        max_elements: int = 50,
        include_bbox: bool = True,
        interactable_only: bool = False,
    ) -> str: ...

    def click_element_sync(self, page: Page, snapshot: SemanticSnapshot, ref_or_intent: str) -> str: ...


class _VisionHybridProtocol(Protocol):
    def analyze_sync(self, page: Page, snapshot: SemanticSnapshot | None = None) -> HybridAnalysis: ...

    def render_som_sync(self, page: Page, snapshot: SemanticSnapshot) -> str: ...


class _AccessibilityProtocol(Protocol):
    def snapshot(self) -> object: ...


def _param_text(params: Params, key: str, default: str = "") -> str:
    value = params.get(key)
    return value if isinstance(value, str) else default


def _param_int(params: Params, key: str, default: int) -> int:
    value = params.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _param_timeout(params: Params, default: int = 5000) -> int:
    return _param_int(params, "timeout", default)


def _a11y_children(value: object) -> list[A11yNode]:
    if not isinstance(value, list):
        return []
    children: list[A11yNode] = []
    raw: list[object] = cast(list[object], value)
    for item in raw:
        if isinstance(item, dict):
            raw_item: dict[object, object] = cast(dict[object, object], item)
            children.append({str(key): child for key, child in raw_item.items()})
    return children


def _a11y_node(value: object) -> A11yNode | None:
    if not isinstance(value, dict):
        return None
    raw: dict[object, object] = cast(dict[object, object], value)
    return {str(key): child for key, child in raw.items()}


@final
class BrowserTool(BaseTool):
    """Playwright 기반 브라우저 자동화 도구.

    하네스 엔지니어링 적용:
    - Intent 기반 테스트: CSS 셀렉터 대신 자연어 의도로 요소 탐색
    - Self-Healing: 셀렉터 실패 시 Accessibility Tree 기반 자동 복구
    - 스크린샷 + DOM 스냅샷 자동 캡처
    """

    category = ToolCategory.WEB
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.MEDIUM
    icon = "🌐"
    tags = ["browser", "playwright", "web", "test", "automation"]

    def __init__(self):
        """Initialize the BrowserTool."""
        self.page: Page | None = None
        self.context: BrowserContext | None = None
        self.browser: Browser | None = None
        self.playwright: Playwright | None = None
        self.is_running: bool = False
        # v2: 시맨틱 DOM + Vision 엔진
        self._dom_parser: _DOMParserProtocol | None = None
        self._vision_hybrid: _VisionHybridProtocol | None = None
        self._last_snapshot: SemanticSnapshot | None = None
        # task 16: 세션 자리를 **소유자에게** 받아 둔다(상한·유휴 회수·owner 가 여기에도 걸린다).
        self._reservation: SessionReservation | None = None
        self._owner: BrowserOwner | None = None
        self._video_path: str | None = None

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "browser"

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return (
            "브라우저를 조작하여 웹 페이지를 탐색하고 테스트합니다. "
            "기본 액션: 페이지 이동(goto), 클릭(click), 텍스트 입력(type), "
            "스크린샷(screenshot), DOM 읽기(read_dom), "
            "접근성 트리 분석(accessibility), 브라우저 종료(close). "
            "고급 액션: 시맨틱 스냅샷(semantic_snapshot), "
            "의도 기반 클릭(click_by_intent), 시각 분석(vision_analyze), "
            "SoM 스크린샷(som_screenshot), 장애물 감지(detect_obstacles)."
        )

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "goto",
                        "click",
                        "type",
                        "screenshot",
                        "read_dom",
                        "accessibility",
                        "wait",
                        "evaluate",
                        "close",
                        "semantic_snapshot",
                        "click_by_intent",
                        "vision_analyze",
                        "som_screenshot",
                        "detect_obstacles",
                    ],
                    "description": "실행할 브라우저 액션",
                },
                "url": {"type": "string", "description": "goto 액션 시 이동할 URL"},
                "selector": {
                    "type": "string",
                    "description": "click/type 액션 시 대상 CSS 셀렉터",
                },
                "text": {
                    "type": "string",
                    "description": "type 액션 시 입력할 텍스트, click 시 텍스트로 요소 찾기",
                },
                "path": {"type": "string", "description": "screenshot 저장 경로"},
                "timeout": {
                    "type": "integer",
                    "description": "대기 시간(ms)",
                    "default": 5000,
                },
                "script": {
                    "type": "string",
                    "description": "evaluate 액션 시 실행할 JavaScript 코드",
                },
                "intent": {
                    "type": "string",
                    "description": "click_by_intent 시 자연어 의도 (예: '로그인 버튼', '검색 입력란')",
                },
                "ref": {
                    "type": "string",
                    "description": "@ref 식별자 (예: '@ref3'). semantic_snapshot 후 사용.",
                },
                "max_elements": {
                    "type": "integer",
                    "description": "semantic_snapshot에서 반환할 최대 요소 수",
                    "default": 50,
                },
            },
            "required": ["action"],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            str: The str result.

        """
        params: Params = kwargs
        action = params.get("action")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return (
                "오류: playwright가 설치되어 있지 않습니다.\n"
                "'pip install playwright && playwright install chromium'을 실행하세요."
            )

        if not self.is_running:
            import os

            session_owner = get_browser_session_owner()
            browser_owner = current_browser_owner()
            try:
                reservation = session_owner.begin(browser_owner, purpose="browser 도구")
            except (BrowserSessionLimitError, BrowserSessionRefusedError) as e:
                return f"Error: {e}"
            if reservation.is_reuse:
                reuse = reservation.reuse
                assert reuse is not None
                self._reservation = reservation
                self._owner = browser_owner
                self.page = cast("Page", reuse.page)
                self.is_running = True
                return "Browser session reused (already open for this owner)."

            try:
                playwright = sync_playwright().start()
                browser = playwright.chromium.launch(headless=True)

                # 컨텍스트 기반으로 변경하여 record_video_dir 지원
                video_dir = os.path.abspath(".gstack/qa-reports/videos")
                os.makedirs(video_dir, exist_ok=True)
                context = browser.new_context(record_video_dir=video_dir)
                page = context.new_page()
            except Exception:
                session_owner.abort(reservation)
                raise
            self.playwright = playwright
            self.browser = browser
            self.context = context
            self.page = page
            self.is_running = True
            self._reservation = reservation
            self._owner = browser_owner
            _ = session_owner.commit(
                reservation,
                page=page,
                close=lambda: self._release_session(),
            )

        try:
            if action == "goto":
                return self._action_goto(params)
            elif action == "click":
                return self._action_click(params)
            elif action == "type":
                return self._action_type(params)
            elif action == "screenshot":
                return self._action_screenshot(params)
            elif action == "read_dom":
                return self._action_read_dom(params)
            elif action == "accessibility":
                return self._action_accessibility(params)
            elif action == "wait":
                return self._action_wait(params)
            elif action == "evaluate":
                return self._action_evaluate(params)
            elif action == "close":
                return self._action_close()
            # ─── v2: 시맨틱 DOM + Vision 액션 ───
            elif action == "semantic_snapshot":
                return self._action_semantic_snapshot(params)
            elif action == "click_by_intent":
                return self._action_click_by_intent(params)
            elif action == "vision_analyze":
                return self._action_vision_analyze(params)
            elif action == "som_screenshot":
                return self._action_som_screenshot(params)
            elif action == "detect_obstacles":
                return self._action_detect_obstacles(params)
            else:
                return f"Unknown action: {action}"

        except Exception as e:
            logger.exception("Browser action '%s' failed", action)
            return f"Error: {str(e)}"

    def _require_page(self) -> Page:
        page = self.page
        if page is None:
            raise RuntimeError("browser is not running")
        return page

    def _action_goto(self, params: Params) -> str:
        page = self._require_page()
        url = _param_text(params, "url")
        timeout = _param_timeout(params, 15000)
        if not url:
            return "Error: 'url' 파라미터가 필요합니다"
        try:
            # 다른 진입점과 같은 egress 규칙(task 16).
            _ = get_browser_session_owner().validate_navigation(url)
        except Exception as e:
            return f"Error: navigation target is not allowed: {e}"
        _ = page.goto(url, wait_until="networkidle", timeout=timeout)
        title = page.title()
        return f"Navigated to {url}. Title: {title}"

    def _action_click(self, params: Params) -> str:
        page = self._require_page()
        selector = _param_text(params, "selector")
        text = _param_text(params, "text")
        timeout = _param_timeout(params)

        if text and not selector:
            # Intent 기반 클릭: 텍스트로 요소 찾기 (Self-Healing 패턴)
            el = page.get_by_text(text, exact=False)
            el.click(timeout=timeout)
            return f"Clicked element with text '{text}'"
        elif selector:
            # 기존 CSS 셀렉터 클릭
            try:
                page.click(selector, timeout=timeout)
                return f"Clicked on {selector}"
            except Exception:
                # Self-Healing: CSS 실패 시 텍스트 기반으로 폴백
                if text:
                    el = page.get_by_text(text, exact=False)
                    el.click(timeout=timeout)
                    return f"[Healed] CSS '{selector}' failed → clicked by text '{text}'"
                raise
        else:
            return "Error: selector 또는 text 중 하나를 지정해야 합니다"

    def _action_type(self, params: Params) -> str:
        page = self._require_page()
        selector = _param_text(params, "selector")
        text = _param_text(params, "text")
        timeout = _param_timeout(params)

        if selector:
            page.fill(selector, text, timeout=timeout)
            return f"Typed '{text}' into {selector}"
        else:
            # 현재 포커스된 요소에 타이핑
            page.keyboard.type(text)
            return f"Typed '{text}' via keyboard"

    def _action_screenshot(self, params: Params) -> str:
        page = self._require_page()
        path = _param_text(params, "path", f"screenshot_{int(time.time())}.png")
        _ = page.screenshot(path=path, full_page=True)
        return f"Screenshot saved to {path}"

    def _action_read_dom(self, params: Params) -> str:
        page = self._require_page()
        """현재 페이지의 주요 DOM 구조를 읽습니다 (에이전트가 이해하기 쉬운 형태)."""
        selector = _param_text(params, "selector", "body")

        # 주요 인터랙티브 요소만 추출
        result = cast(
            object,
            page.evaluate(
                f"""() => {{

            const el = document.querySelector('{selector}');
            if (!el) return 'Element not found';

            const interactives = el.querySelectorAll(
                'button, input, textarea, select, a[href], [role="button"], [onclick]'
            );

            return Array.from(interactives).slice(0, 50).map(e => ({{
                tag: e.tagName.toLowerCase(),
                id: e.id || null,
                text: (e.textContent || '').trim().slice(0, 100),
                type: e.type || null,
                placeholder: e.placeholder || null,
                role: e.getAttribute('role') || null,
                ariaLabel: e.getAttribute('aria-label') || null,
            }}));
        }}""",
            ),
        )

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _action_accessibility(self, _params: Params) -> str:
        """Accessibility Tree 스냅샷을 생성합니다 (하네스 엔지니어링 핵심)."""
        page = self._require_page()
        accessibility = cast(_AccessibilityProtocol | None, getattr(page, "accessibility", None))
        if accessibility is None:
            return "Accessibility snapshot unavailable in this Playwright runtime"
        snapshot_fn: Callable[[], object] = accessibility.snapshot
        snapshot_raw = snapshot_fn()
        snapshot = _a11y_node(snapshot_raw)
        if not snapshot:
            return "Accessibility snapshot unavailable"

        # 트리를 간결하게 포맷
        return self._format_a11y_tree(snapshot, max_depth=3)

    def _action_wait(self, params: Params) -> str:
        page = self._require_page()
        selector = _param_text(params, "selector")
        timeout = _param_timeout(params)

        if selector:
            _ = page.wait_for_selector(selector, timeout=timeout)
            return f"Element '{selector}' appeared"
        else:
            page.wait_for_timeout(timeout)
            return f"Waited {timeout}ms"

    def _action_evaluate(self, params: Params) -> str:
        page = self._require_page()
        script = _param_text(params, "script")
        result = cast(object, page.evaluate(script))
        return json.dumps(result, ensure_ascii=False, default=str)

    def _release_session(self) -> None:
        """자원을 닫고 **소유자 원장에서도** 뺄다(안 빼면 다음 호출이 죽은 세션을 재사용한다)."""
        video_path = None
        page = self.page
        context = self.context
        browser = self.browser
        playwright = self.playwright
        if page and page.video:
            video_path = page.video.path()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.is_running = False
        self._reservation = None
        self._video_path = video_path if isinstance(video_path, str) else None

    def _action_close(self) -> str:
        if self.is_running:
            owner = self._owner
            if owner is not None:
                # 소유자가 닫기를 부른다(원장 정리 + 자원 정리).
                _ = get_browser_session_owner().release(owner)
            else:
                self._release_session()
            self._owner = None
            video_path = self._video_path
            self._video_path = None
            if video_path:
                return f"Browser closed. Video recorded at: {video_path}"
        return "Browser closed."

    def _format_a11y_tree(self, node: A11yNode, depth: int = 0, max_depth: int = 3) -> str:
        """Accessibility Tree를 읽기 쉬운 텍스트로 포맷합니다."""
        if depth > max_depth:
            return ""

        indent = "  " * depth
        role = node.get("role", "")
        name = node.get("name", "")

        line = f"{indent}[{role}]"
        if name:
            line += f' "{name}"'

        lines = [line]
        for child in _a11y_children(node.get("children")):
            child_text = self._format_a11y_tree(child, depth + 1, max_depth)
            if child_text:
                lines.append(child_text)

        return "\n".join(lines)

    # ─── v2: 시맨틱 DOM + Vision 확장 액션 ────────────────────

    def _ensure_dom_parser(self) -> _DOMParserProtocol:
        """SemanticDOMParser를 lazy 초기화합니다."""
        if self._dom_parser is None:
            from .semantic_dom import SemanticDOMParser

            self._dom_parser = cast(_DOMParserProtocol, SemanticDOMParser())
        return self._dom_parser

    def _ensure_vision_hybrid(self) -> _VisionHybridProtocol:
        """VisionDOMHybrid를 lazy 초기화합니다."""
        if self._vision_hybrid is None:
            from .semantic_dom import SemanticDOMParser
            from .vision_dom_hybrid import VisionDOMHybrid

            parser = cast(SemanticDOMParser, self._ensure_dom_parser())
            self._vision_hybrid = cast(_VisionHybridProtocol, cast(object, VisionDOMHybrid(parser)))
        return self._vision_hybrid

    def _action_semantic_snapshot(self, params: Params) -> str:
        """시맨틱 DOM 스냅샷: @ref 인덱싱된 페이지 구조 반환.

        LLM이 요소를 '@ref3 클릭' 같은 방식으로 정밀 참조할 수 있게 합니다.
        토큰 효율이 기존 read_dom 대비 약 70% 향상됩니다.
        """
        page = self._require_page()
        parser = self._ensure_dom_parser()
        max_elements = _param_int(params, "max_elements", 50)

        snapshot = parser.snapshot_sync(page)
        snapshot = parser.enrich_with_a11y_sync(page, snapshot)
        self._last_snapshot = snapshot

        context = parser.to_llm_context(snapshot, max_elements=max_elements, include_bbox=True)
        return context

    def _action_click_by_intent(self, params: Params) -> str:
        """자연어 의도 기반 클릭.

        CSS 셀렉터 없이 '로그인 버튼', '검색 입력란' 같은 의도로 클릭합니다.
        내부적으로 @ref → CSS → BBox → 텍스트 순서로 폴백합니다.
        """
        page = self._require_page()
        parser = self._ensure_dom_parser()
        intent = _param_text(params, "intent") or _param_text(params, "text")
        ref = _param_text(params, "ref")

        if not intent and not ref:
            return "Error: 'intent' 또는 'ref' 파라미터가 필요합니다"

        # 마지막 스냅샷이 없으면 새로 생성
        if self._last_snapshot is None:
            self._last_snapshot = parser.snapshot_sync(page)

        target = ref or intent
        return parser.click_element_sync(page, self._last_snapshot, target)

    def _action_vision_analyze(self, _params: Params) -> str:
        """Vision + DOM 융합 분석.

        DOM 구조와 스크린샷을 동시에 분석하여:
        - 페이지 상태 (normal/blocked/loading)
        - 장애물 목록 (팝업/모달/쿠키 배너)
        - 인터랙티브 요소 수
        를 반환합니다.
        """
        page = self._require_page()
        hybrid = self._ensure_vision_hybrid()
        analysis: HybridAnalysis = hybrid.analyze_sync(page, self._last_snapshot)
        self._last_snapshot = analysis.snapshot

        summary = analysis.to_llm_summary()
        if analysis.snapshot:
            parser = self._ensure_dom_parser()
            dom_ctx = parser.to_llm_context(
                analysis.snapshot,
                max_elements=30,
                interactable_only=True,
            )
            summary += "\n\n" + dom_ctx

        return summary

    def _action_som_screenshot(self, params: Params) -> str:
        """Set-of-Mark 스크린샷.

        인터랙티브 요소 위에 @ref 번호를 빨간색 오버레이로 마킹한
        스크린샷을 생성합니다. Vision LLM에 전달하면 시각적 그라운딩이 가능합니다.
        """
        page = self._require_page()
        hybrid = self._ensure_vision_hybrid()
        parser = self._ensure_dom_parser()

        if self._last_snapshot is None:
            self._last_snapshot = parser.snapshot_sync(page)

        som_b64 = hybrid.render_som_sync(page, self._last_snapshot)

        # 파일로 저장 (선택)
        path = _param_text(params, "path")
        if path:
            import base64 as b64_mod

            raw_bytes = b64_mod.b64decode(som_b64)
            with open(path, "wb") as f:
                _ = f.write(raw_bytes)
            return f"SoM screenshot saved to {path} ({len(self._last_snapshot.elements)} elements marked)"

        return (
            f"SoM screenshot generated ({len(self._last_snapshot.elements)} elements marked).\n"
            f"Image is available as base64 PNG ({len(som_b64)} chars).\n"
            f"Use semantic_snapshot to see @ref mappings."
        )

    def _action_detect_obstacles(self, _params: Params) -> str:
        """장애물 자동 감지.

        현재 페이지의 팝업, 모달, 쿠키 배너 등 장애물을 감지하고,
        각 장애물의 닫기 버튼 @ref를 함께 반환합니다.
        """
        page = self._require_page()
        hybrid = self._ensure_vision_hybrid()
        parser = self._ensure_dom_parser()

        if self._last_snapshot is None:
            self._last_snapshot = parser.snapshot_sync(page)

        analysis: HybridAnalysis = hybrid.analyze_sync(page, self._last_snapshot)

        if not analysis.obstacles:
            return "✅ 장애물 없음 — 페이지가 정상 상태입니다."

        lines = [f"⚠️ {len(analysis.obstacles)}개 장애물 감지:"]
        for obs in analysis.obstacles:
            line = f"  - [{obs.type}] {obs.description}"
            if obs.close_ref:
                line += f" → 닫기: {obs.close_ref}"
            if obs.blocking:
                line += " (차단 중)"
            lines.append(line)

        lines.append(f"\n페이지 상태: {analysis.page_state}")
        return "\n".join(lines)
