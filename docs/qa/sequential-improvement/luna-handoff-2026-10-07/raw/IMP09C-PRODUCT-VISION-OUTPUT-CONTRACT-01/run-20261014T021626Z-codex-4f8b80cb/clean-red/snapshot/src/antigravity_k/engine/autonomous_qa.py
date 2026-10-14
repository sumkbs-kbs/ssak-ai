"""Ssak-Ai: 완전 자율 QA 루프 엔진 (AutonomousQA).

=====================================================
비전 분석 → 코드 수정 생성 → 자동 적용 → 재테스트 → 검증
의 완전 자율 폐쇄 루프를 구현합니다.

흐름:
  1. Playwright로 스크린샷 촬영
  2. 멀티모달 비전 LLM(qwen3.6:latest)에 UI 결함 분석 요청
  3. 코딩 LLM에 코드 수정 패치 생성 요청
  4. fs/write API로 코드 패치 자동 적용
  5. 페이지 리로드 후 재스크린샷 → 비전 재분석
  6. 결함 해소 확인 (Visual Regression 비교)
  7. 실패 시 최대 N회 반복
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import time
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, TypedDict, cast, final

from antigravity_k.tools.browser_session_owner import (
    current_browser_owner,
    get_browser_session_owner,
)
from antigravity_k.tools.egress_policy import validate_httpx_request_async

logger = logging.getLogger("antigravity_k.autonomous_qa")

if TYPE_CHECKING:
    from playwright.async_api import Page


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role_name: str, default_role: str = "reasoning") -> str: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class _AttemptReport(TypedDict):
    iteration: int
    defects: int
    patches: int
    resolved: bool
    visual_diff: float
    duration_ms: float


class _ReportDict(TypedDict):
    url: str
    status: str
    total_iterations: int
    total_defects_found: int
    total_fixes_applied: int
    total_resolved: int
    performance: dict[str, object]
    viewport_results: dict[str, "_ViewportResult"]
    console_errors_count: int
    duration_ms: float
    attempts: list[_AttemptReport]


_ViewportResult = TypedDict(
    "_ViewportResult",
    {
        "viewport": dict[str, int],
        "horizontal_overflow": bool,
        "app_visible": bool,
        "pass": bool,
        "summary": str,
    },
)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {str(key): item for key, item in mapping.items()}


def _text_field(value: object, key: str, default: str = "") -> str:
    candidate = _object_dict(value).get(key, default)
    return candidate if isinstance(candidate, str) else default


def _bool_field(value: object, key: str, default: bool = False) -> bool:
    candidate = _object_dict(value).get(key, default)
    return candidate if isinstance(candidate, bool) else default


def _defects_from_json(value: object) -> list["UIDefect"]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    defects: list[UIDefect] = []
    for item in items:
        description = _text_field(item, "description")
        if description:
            defects.append(
                UIDefect(
                    description=description,
                    severity=_text_field(item, "severity", "medium"),
                    suggested_fix=_text_field(item, "suggested_fix"),
                    file_path=_text_field(item, "file_hint"),
                ),
            )
    return defects


def _json_array_text(value: str) -> object:
    import re

    json_match = re.search(r"\[.*\]", value, re.DOTALL)
    return cast(object, json.loads(json_match.group())) if json_match else []


def _patches_from_json(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    patches: list[dict[str, str]] = []
    for item in items:
        patch = {
            "file": _text_field(item, "file"),
            "search": _text_field(item, "search"),
            "replace": _text_field(item, "replace"),
        }
        if patch["file"] and patch["search"]:
            patches.append(patch)
    return patches


# ─── 데이터 모델 ───────────────────────────────────────────────


class FixStatus(str, Enum):
    """Fixstatus.

    Bases: str, Enum
    """

    PENDING = "pending"
    ANALYZING = "analyzing"
    FIXING = "fixing"
    VERIFYING = "verifying"
    FIXED = "fixed"
    FAILED = "failed"
    NO_ISSUES = "no_issues"


@dataclass
class UIDefect:
    """비전 모델이 감지한 UI 결함."""

    description: str
    severity: str = "medium"  # critical, high, medium, low
    suggested_fix: str = ""
    file_path: str = ""
    code_patch: str = ""


@dataclass
class FixAttempt:
    """코드 수정 시도 기록."""

    iteration: int
    defects_found: list[UIDefect]
    patches_applied: list[dict[str, str]]
    before_screenshot_hash: str = ""
    after_screenshot_hash: str = ""
    visual_diff_score: float = 0.0
    resolved: bool = False
    duration_ms: float = 0


@dataclass
class AutonomousQAReport:
    """자율 QA 루프 전체 보고서."""

    url: str = ""
    total_iterations: int = 0
    total_defects_found: int = 0
    total_fixes_applied: int = 0
    total_resolved: int = 0
    status: FixStatus = FixStatus.PENDING
    attempts: list[FixAttempt] = field(default_factory=list)
    performance_metrics: dict[str, object] = field(default_factory=dict)
    viewport_results: dict[str, dict[str, object]] = field(default_factory=dict)
    console_errors: list[dict[str, object]] = field(default_factory=list)
    duration_ms: float = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> _ReportDict:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return {
            "url": self.url,
            "status": self.status.value,
            "total_iterations": self.total_iterations,
            "total_defects_found": self.total_defects_found,
            "total_fixes_applied": self.total_fixes_applied,
            "total_resolved": self.total_resolved,
            "performance": self.performance_metrics,
            "viewport_results": {
                name: cast(_ViewportResult, cast(object, result)) for name, result in self.viewport_results.items()
            },
            "console_errors_count": len(self.console_errors),
            "duration_ms": round(self.duration_ms, 1),
            "attempts": [
                {
                    "iteration": a.iteration,
                    "defects": len(a.defects_found),
                    "patches": len(a.patches_applied),
                    "resolved": a.resolved,
                    "visual_diff": round(a.visual_diff_score, 3),
                    "duration_ms": round(a.duration_ms, 1),
                }
                for a in self.attempts
            ],
        }

    def to_markdown(self) -> str:
        """To Markdown.

        Returns:
            str: The str result.

        """
        icon = "✅" if self.status == FixStatus.FIXED or self.status == FixStatus.NO_ISSUES else "❌"
        lines = [
            f"# {icon} Autonomous QA Report",
            "",
            "| 항목 | 값 |",
            "|------|------|",
            f"| URL | {self.url} |",
            f"| 상태 | {self.status.value} |",
            f"| 반복 횟수 | {self.total_iterations} |",
            f"| 발견된 결함 | {self.total_defects_found} |",
            f"| 적용된 수정 | {self.total_fixes_applied} |",
            f"| 해결됨 | {self.total_resolved} |",
            f"| 소요시간 | {self.duration_ms:.0f}ms |",
            "",
        ]
        if self.performance_metrics:
            lines.append("## ⚡ 성능 메트릭")
            for k, v in self.performance_metrics.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

        if self.viewport_results:
            lines.append("## 📱 반응형 테스트")
            for vp, result in self.viewport_results.items():
                vp_icon = "✅" if _bool_field(result, "pass") else "⚠️"
                lines.append(f"- {vp_icon} **{vp}**: {_text_field(result, 'summary', 'N/A')}")
            lines.append("")

        for attempt in self.attempts:
            lines.append(f"### 반복 {attempt.iteration}")
            for d in attempt.defects_found:
                lines.append(f"- 🔍 [{d.severity}] {d.description}")
                if d.file_path:
                    lines.append(f"  - 파일: `{d.file_path}`")
            if attempt.resolved:
                lines.append(f"- ✅ Visual Diff: {attempt.visual_diff_score:.3f} (해결됨)")
            lines.append("")

        return "\n".join(lines)


# ─── 자율 QA 루프 엔진 ────────────────────────────────────────


@final
class AutonomousQAEngine:
    """완전 자율 폐쇄 루프 QA 엔진.

    Screenshot → Vision → CodeFix → Apply → Re-test → Verify
    """

    VIEWPORTS: Final[dict[str, dict[str, int]]] = {
        "desktop": {"width": 1280, "height": 800},
        "tablet": {"width": 768, "height": 1024},
        "mobile": {"width": 375, "height": 812},
    }

    def __init__(
        self,
        dashboard_url: str = "http://localhost:5173",
        ollama_url: str = "http://127.0.0.1:11434",
        vision_model: str = "qwen3.6:latest",
        coding_model: str = "qwen3.6:latest",
        max_iterations: int = 3,
        project_root: str = "",
        model_manager: _ModelManagerLike | None = None,
    ):
        """Initialize the AutonomousQAEngine.

        Args:
            dashboard_url (str): str dashboard url.
            ollama_url (str): str ollama url.
            vision_model (str): str vision model.
            coding_model (str): str coding model.
            max_iterations (int): int max iterations.
            project_root (str): str project root.

        """
        self.dashboard_url: str = dashboard_url
        self.ollama_url: str = ollama_url
        self.vision_model: str = vision_model
        self.coding_model: str = coding_model
        self.max_iterations: int = max_iterations
        self.model_manager: _ModelManagerLike | None = model_manager
        self.project_root: str = project_root or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )

    def _resolve_model_target(self, requested: str, role: str, default_role: str) -> str:
        if self.model_manager is None or requested not in {"", "qwen3.6:latest"}:
            return requested
        try:
            return self.model_manager.get_target_for_role(role, default_role=default_role)
        except Exception:
            logger.warning("ModelManager target resolution failed for %s", role, exc_info=True)
            return requested

    async def run_full_loop(self, url: str = "") -> AutonomousQAReport:
        """완전 자율 루프를 실행합니다."""
        from playwright.async_api import async_playwright

        target_url = url or self.dashboard_url
        report = AutonomousQAReport(url=target_url)
        start = time.time()

        # 소유자를 지나간다(task 16): 이 엔진도 호스트의 브라우저를 빌린다.
        session_owner = get_browser_session_owner()
        browser_owner = current_browser_owner()
        reservation = session_owner.begin(browser_owner, purpose="autonomous qa")
        try:
            # 대상은 운영자가 지정한 앱 주소다 — 로컬 허용을 **여기서 명시**한다(task 16).
            _ = session_owner.validate_navigation(target_url, allow_local=True)
        except Exception:
            # 열지 못할 주소로 브라우저를 시작하지 않고, 예약도 돌려준다.
            session_owner.abort(reservation)
            raise

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            from typing import cast

            from playwright.async_api import ViewportSize

            context = await browser.new_context(
                viewport=cast(ViewportSize, cast(object, self.VIEWPORTS["desktop"])),
            )
            page = await context.new_page()
            _ = session_owner.commit(reservation, page=page)

            # 콘솔 에러 수집
            console_errors: list[dict[str, object]] = []

            def capture_console(message: object) -> None:
                message_type = getattr(message, "type", "")
                if message_type in ("error", "warning"):
                    console_errors.append(
                        {
                            "type": message_type,
                            "text": getattr(message, "text", ""),
                        },
                    )

            page.on("console", capture_console)

            _ = await page.goto(target_url, wait_until="networkidle", timeout=30000)

            # ── 성능 메트릭 수집 ──
            report.performance_metrics = await self._collect_performance(page)

            # ── 자율 수정 루프 ──
            for iteration in range(1, self.max_iterations + 1):
                report.total_iterations = iteration
                report.status = FixStatus.ANALYZING

                attempt = FixAttempt(iteration=iteration, defects_found=[], patches_applied=[])
                attempt_start = time.time()

                # Step 1: 스크린샷
                screenshot_bytes = await page.screenshot(full_page=True)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                attempt.before_screenshot_hash = hashlib.md5(screenshot_bytes, usedforsecurity=False).hexdigest()

                # Step 2: 비전 분석
                defects = await self._vision_analyze(screenshot_b64)
                attempt.defects_found = defects
                report.total_defects_found += len(defects)

                if not defects:
                    report.status = FixStatus.NO_ISSUES
                    attempt.resolved = True
                    attempt.duration_ms = (time.time() - attempt_start) * 1000
                    report.attempts.append(attempt)
                    logger.info("[AutonomousQA] Iteration %s: No defects found ✅", iteration)
                    break

                # Step 3: 코드 수정 생성
                report.status = FixStatus.FIXING
                patches = await self._generate_code_fixes(defects)
                attempt.patches_applied = patches
                report.total_fixes_applied += len(patches)

                # Step 4: 패치 적용
                for patch in patches:
                    _ = self._apply_patch(patch)

                # Step 5: 리로드 후 재검증
                _ = await page.reload(wait_until="networkidle", timeout=15000)
                await asyncio.sleep(1)

                report.status = FixStatus.VERIFYING
                after_bytes = await page.screenshot(full_page=True)
                attempt.after_screenshot_hash = hashlib.md5(after_bytes, usedforsecurity=False).hexdigest()

                # Step 6: Visual Regression 비교
                attempt.visual_diff_score = self._compare_screenshots(screenshot_bytes, after_bytes)

                # 변화가 있으면 재분석하여 해결 여부 확인
                if attempt.visual_diff_score > 0.01:
                    after_b64 = base64.b64encode(after_bytes).decode("utf-8")
                    remaining_defects = await self._vision_analyze(after_b64)
                    if len(remaining_defects) < len(defects):
                        report.total_resolved += len(defects) - len(remaining_defects)
                        if not remaining_defects:
                            attempt.resolved = True
                            report.status = FixStatus.FIXED

                attempt.duration_ms = (time.time() - attempt_start) * 1000
                report.attempts.append(attempt)

                if attempt.resolved:
                    logger.info("[AutonomousQA] All defects resolved at iteration %s ✅", iteration)
                    break

            # ── 반응형 테스트 ──
            # 루프가 끝나면 세션을 소유자에게 돌려준다(예약만 남기면 deadline 까지 자리를 잡는다).
            _ = session_owner.release(browser_owner)
            report.viewport_results = cast(
                dict[str, dict[str, object]],
                cast(object, await self._test_viewports(page, target_url)),
            )

            report.console_errors = console_errors
            await browser.close()

        report.duration_ms = (time.time() - start) * 1000
        if report.status not in (FixStatus.FIXED, FixStatus.NO_ISSUES):
            report.status = FixStatus.FAILED

        return report

    # ─── 비전 분석 ─────────────────────────────────────────────

    async def _vision_analyze(self, screenshot_b64: str) -> list[UIDefect]:
        """멀티모달 비전 LLM으로 UI 결함을 분석합니다."""
        import httpx

        prompt = (
            "You are a UI/UX QA expert. Analyze this screenshot for defects.\n"
            "Look for: layout issues, overlapping elements, clipped text, alignment errors, "
            "broken styling, invisible elements, color contrast issues.\n\n"
            "For each defect found, respond in this JSON format:\n"
            '```json\n[\n  {"description": "...", "severity": "high|medium|low", '
            '"suggested_fix": "...", "file_hint": "css|js filename if guessable"}\n]\n```\n'
            "If NO defects are found, respond with: `[]`"
        )

        try:
            if self.model_manager is not None:
                target = self._resolve_model_target(self.vision_model, "vision", "vision")
                try:
                    content: object = await asyncio.to_thread(
                        self.model_manager.generate,
                        prompt,
                        target=target,
                        raw_messages=[
                            {"role": "user", "content": prompt, "images": [screenshot_b64]},
                        ],
                        max_tokens=2048,
                        temperature=0.2,
                    )
                    if inspect.isawaitable(content):
                        content = await cast(Awaitable[object], content)
                    if isinstance(content, str) and content.strip():
                        return _defects_from_json(_json_array_text(content))
                except Exception:
                    logger.warning("ModelManager vision analysis failed, HTTP fallback", exc_info=True)

            async with httpx.AsyncClient(
                timeout=120.0,
                event_hooks={"request": [validate_httpx_request_async]},
            ) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.vision_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [screenshot_b64],
                            },
                        ],
                        "stream": False,
                    },
                )

            if resp.status_code != 200:
                logger.error("Vision API error: %s", resp.status_code)
                return []

            response_data = _object_dict(cast(object, resp.json()))
            content = _text_field(response_data.get("message"), "content", "[]")
            return _defects_from_json(_json_array_text(content))

        except (httpx.RequestError, json.JSONDecodeError, KeyError):
            logger.warning("Vision analysis failed", exc_info=True)
            return []

    # ─── 코드 수정 생성 ───────────────────────────────────────

    async def _generate_code_fixes(self, defects: list[UIDefect]) -> list[dict[str, str]]:
        """코딩 LLM으로 코드 수정 패치를 생성합니다."""
        import httpx

        defect_descriptions = "\n".join(f"- [{d.severity}] {d.description} (제안: {d.suggested_fix})" for d in defects)

        prompt = (
            f"다음 UI 결함을 수정하는 코드 패치를 생성하세요:\n{defect_descriptions}\n\n"
            f"프로젝트 루트: {self.project_root}\n"
            f"대시보드 CSS: dashboard/src/styles/index.css\n"
            f"대시보드 JS: dashboard/src/pages/chat.js\n\n"
            "각 수정을 아래 JSON 형식으로 출력하세요:\n"
            '```json\n[\n  {"file": "상대경로", "search": "찾을 텍스트", "replace": "바꿀 텍스트"}\n]\n```'
        )

        try:
            if self.model_manager is not None:
                target = self._resolve_model_target(self.coding_model, "coding", "coding")
                try:
                    content: object = await asyncio.to_thread(
                        self.model_manager.generate,
                        prompt,
                        target=target,
                        max_tokens=2048,
                        temperature=0.2,
                    )
                    if inspect.isawaitable(content):
                        content = await cast(Awaitable[object], content)
                    if isinstance(content, str) and content.strip():
                        return _patches_from_json(_json_array_text(content))
                except Exception:
                    logger.warning("ModelManager code-fix generation failed, HTTP fallback", exc_info=True)

            async with httpx.AsyncClient(
                timeout=120.0,
                event_hooks={"request": [validate_httpx_request_async]},
            ) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.coding_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                    },
                )

            if resp.status_code != 200:
                return []

            response_data = _object_dict(cast(object, resp.json()))
            content = _text_field(response_data.get("message"), "content", "[]")
            return _patches_from_json(_json_array_text(content))

        except (httpx.RequestError, json.JSONDecodeError, KeyError):
            logger.warning("Code fix generation failed", exc_info=True)
            return []

    # ─── 패치 적용 ─────────────────────────────────────────────

    def _apply_patch(self, patch: dict[str, str]) -> bool:
        """코드 패치를 파일에 적용합니다."""
        project_root = Path(self.project_root).resolve()
        candidate = Path(patch.get("file", ""))
        if candidate.is_absolute():
            logger.warning("Patch skip: absolute paths are not allowed — %s", candidate)
            return False
        file_path = (project_root / candidate).resolve()
        try:
            _ = file_path.relative_to(project_root)
        except ValueError:
            logger.warning("Patch skip: path escapes project root — %s", candidate)
            return False
        search = patch.get("search", "")
        replace = patch.get("replace", "")

        if not os.path.exists(file_path) or not search:
            logger.warning("Patch skip: file not found or empty search — %s", file_path)
            return False

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            if search not in content:
                logger.warning("Patch skip: search text not found in %s", file_path)
                return False

            new_content = content.replace(search, replace, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                _ = f.write(new_content)

            logger.info("[AutonomousQA] Patch applied: %s", file_path)
            return True

        except (OSError, IOError, ValueError):
            logger.warning("Patch apply failed", exc_info=True)
            return False

    # ─── Visual Regression ─────────────────────────────────────

    def _compare_screenshots(self, before: bytes, after: bytes) -> float:
        """두 스크린샷의 차이를 0~1 스코어로 반환 (0=동일, 1=완전 다름)."""
        if before == after:
            return 0.0

        # 바이트 해시 기반 빠른 비교
        h1 = hashlib.md5(before, usedforsecurity=False).hexdigest()
        h2 = hashlib.md5(after, usedforsecurity=False).hexdigest()

        if h1 == h2:
            return 0.0

        # 바이트 레벨 차이 비율 (근사)
        min_len = min(len(before), len(after))
        if min_len == 0:
            return 1.0

        sample_size = min(10000, min_len)
        step = max(1, min_len // sample_size)
        diff_count = sum(1 for i in range(0, min_len, step) if before[i] != after[i])
        return diff_count / sample_size

    # ─── 성능 메트릭 ───────────────────────────────────────────

    async def _collect_performance(self, page: object) -> dict[str, object]:
        """Core Web Vitals 및 로딩 성능을 측정합니다."""
        try:
            typed_page = cast("Page", page)
            metrics: object = cast(
                object,
                await typed_page.evaluate(
                    """() => {

                const perf = performance.getEntriesByType('navigation')[0];
                const paint = performance.getEntriesByType('paint');
                const fcp = paint.find(p => p.name === 'first-contentful-paint');
                return {
                    dom_content_loaded_ms: perf ? Math.round(perf.domContentLoadedEventEnd - perf.startTime) : null,
                    load_complete_ms: perf ? Math.round(perf.loadEventEnd - perf.startTime) : null,
                    first_contentful_paint_ms: fcp ? Math.round(fcp.startTime) : null,
                    dom_nodes: document.querySelectorAll('*').length,
                    js_heap_mb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null,
                };
            }""",
                ),
            )
            return _object_dict(metrics)
        except (TimeoutError, AttributeError, TypeError, ValueError) as e:
            logger.warning("Performance collection failed: %s", e, exc_info=True)
            return {}

    # ─── 반응형 테스트 ─────────────────────────────────────────

    async def _test_viewports(self, page: object, url: str) -> dict[str, _ViewportResult]:
        """다중 뷰포트에서 레이아웃 검증을 수행합니다."""
        from playwright.async_api import ViewportSize

        typed_page = cast("Page", page)
        results: dict[str, _ViewportResult] = {}
        for name, vp in self.VIEWPORTS.items():
            try:
                await typed_page.set_viewport_size(cast(ViewportSize, cast(object, vp)))
                _ = await typed_page.goto(url, wait_until="networkidle", timeout=15000)

                # 가로 스크롤 발생 여부 확인 (레이아웃 깨짐 지표)
                overflow_value = cast(
                    object,
                    await typed_page.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth",
                    ),
                )
                overflow = bool(overflow_value)
                # 주요 요소 가시성 확인
                app_visible = await typed_page.query_selector("#app")

                results[name] = cast(
                    _ViewportResult,
                    cast(
                        object,
                        {
                            "viewport": vp,
                            "horizontal_overflow": overflow,
                            "app_visible": app_visible is not None,
                            "pass": not overflow and app_visible is not None,
                            "summary": (
                                "OK"
                                if (not overflow and app_visible)
                                else "Overflow detected"
                                if overflow
                                else "App not visible"
                            ),
                        },
                    ),
                )
            except (TimeoutError, ConnectionError, AttributeError, ValueError) as e:
                logger.warning("Viewport test failed for %s: %s", name, e, exc_info=True)
                results[name] = cast(_ViewportResult, cast(object, {"pass": False, "summary": str(e)}))

        return results
