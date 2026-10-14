"""Ssak-Ai: 브라우저 자가 테스트 도구 (Self-Test Tool).

=========================================================
에이전트가 "시스템 자가 테스트 해줘"라고 요청하면,
Playwright로 대시보드 전체를 자동 순회하며 건강 검진합니다.

하네스 엔지니어링의 'Agent-Initiated Testing' 패턴 구현.
"""

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import TypedDict, cast, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger("antigravity_k.tools.self_test")


class _ParameterProperty(TypedDict, total=False):
    type: str
    enum: list[str]
    description: str
    default: str | bool


class _ParametersSchema(TypedDict):
    type: str
    properties: dict[str, _ParameterProperty]
    required: list[str]


class SelfTestTool(BaseTool):
    """시스템 자가 테스트 도구.

    에이전트가 브라우저를 열어 Ssak-Ai 대시보드의
    모든 기능(채팅, 탐색기, 터미널, API)을 자동으로 테스트합니다.
    """

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "🧪"

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = ["self-test", "harness", "qa", "browser"]

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "self_test"

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return (
            "시스템 자가 테스트를 실행합니다. "
            "브라우저를 열어 대시보드의 모든 기능(채팅, 파일 탐색기, 터미널, API)을 "
            "자동으로 검증하고 마크다운 리포트를 생성합니다. "
            "Playwright 기반 하네스 엔지니어링 프레임워크를 사용합니다."
        )

    @property
    @override
    def parameters_schema(self) -> _ParametersSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["full", "api_only", "ui_only"],
                    "description": "테스트 범위. full=전체, api_only=API만, ui_only=UI만",
                    "default": "full",
                },
                "verbose": {
                    "type": "boolean",
                    "description": "상세 결과 포함 여부",
                    "default": True,
                },
                "run_hygiene_scan": {
                    "type": "boolean",
                    "description": "파일 명명 규칙(test_ 접두어 방지 등) 스캔 여부",
                    "default": True,
                },
            },
            "required": [],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            str: The str result.

        """
        scope_value = kwargs.get("scope", "full")
        scope = scope_value if isinstance(scope_value, str) else "full"
        verbose_value = kwargs.get("verbose", True)
        verbose = verbose_value if isinstance(verbose_value, bool) else True

        # 동기 컨텍스트에서 비동기 하네스 실행
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 이벤트 루프가 돌고 있으면 새 스레드에서 실행
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_sync, scope)
                    report_dict = future.result(timeout=120)
            else:
                report_dict = loop.run_until_complete(self._run_async(scope))
        except RuntimeError:
            report_dict = asyncio.run(self._run_async(scope))

        run_hygiene_value = kwargs.get("run_hygiene_scan", True)
        run_hygiene = run_hygiene_value if isinstance(run_hygiene_value, bool) else True
        hygiene_issues: list[str] = []
        if run_hygiene:
            import os

            project_root = os.getcwd()
            src_dir = os.path.join(project_root, "src")
            for root, _, files in os.walk(src_dir):
                for file in files:
                    # Ignore tests directory if somehow inside src, but usually tests is at root.
                    if "tests/" in root or "/tests" in root:
                        continue
                    if file.startswith("test_") and file.endswith(".py"):
                        hygiene_issues.append(
                            os.path.relpath(os.path.join(root, file), project_root),
                        )
            report_dict["hygiene_issues"] = hygiene_issues

        if verbose:
            return self._format_markdown(report_dict)
        else:
            return json.dumps(report_dict, ensure_ascii=False, indent=2)

    def _run_sync(self, scope: str) -> dict[str, object]:
        """새 이벤트 루프에서 비동기 테스트 실행."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._run_async(scope))
        finally:
            loop.close()

    async def _run_async(self, scope: str) -> dict[str, object]:
        """비동기 테스트 실행."""
        from ..engine.harness import TestHarness

        harness = TestHarness()
        use_browser = scope != "api_only"

        if scope == "api_only":
            # API 테스트만 실행 (브라우저 불필요)
            harness.intents = [i for i in harness.intents if i.category == "api"]
        elif scope == "ui_only":
            # UI 테스트만 실행
            harness.intents = [i for i in harness.intents if i.category in ("ui", "integration")]

        report = await harness.run_all(use_browser=use_browser)
        return report.to_dict()

    def _format_markdown(self, report: Mapping[str, object]) -> str:
        """리포트를 마크다운으로 포맷."""
        total = report.get("total", 0)
        passed = report.get("passed", 0)
        healed = report.get("healed", 0)
        failed = report.get("failed", 0)
        skipped = report.get("skipped", 0)
        pass_rate_value = report.get("pass_rate", "0%")
        pass_rate = pass_rate_value if isinstance(pass_rate_value, str) else "0%"
        duration_value = report.get("duration_ms", 0)
        duration = float(duration_value) if isinstance(duration_value, (int, float)) else 0.0

        lines = [
            "# 🧪 Ssak-Ai Self-Test Report",
            "",
            "| 항목 | 결과 |",
            "|------|------|",
            f"| 총 테스트 | {total} |",
            f"| ✅ 통과 | {passed} |",
            f"| 🔧 자가치유 | {healed} |",
            f"| ❌ 실패 | {failed} |",
            f"| ⏭ 스킵 | {skipped} |",
            f"| 합격률 | {pass_rate} |",
            f"| 소요시간 | {duration:.0f}ms |",
            "",
            "## 🧹 Hygiene Scan (위생 검사)",
        ]

        hygiene_value = report.get("hygiene_issues", [])
        hygiene = (
            [item for item in cast(list[object], hygiene_value) if isinstance(item, str)]
            if isinstance(hygiene_value, list)
            else []
        )
        if hygiene:
            lines.append("> [!WARNING]")
            lines.append(
                "> **파일명 충돌 위험 발견!** 프로덕션 폴더(`src/`) 내에 `test_`로 시작하는 파일이 있습니다.",
            )
            lines.append(
                "> Pytest가 이를 테스트 케이스로 오인하여 무한 루프나 권한 오류를 발생시킬 수 있습니다. 즉시 리네임(Rename) 하십시오.",
            )
            for issue in hygiene:
                lines.append(f"- 🚨 `{issue}`")
        else:
            lines.append("✅ 프로덕션 코드 내 명명 규칙(test_ 접두어) 위반 사항 없음. 깔끔합니다.")

        lines.extend(
            [
                "",
                "## 상세 결과",
                "",
            ],
        )

        results_value = report.get("results", [])
        results = (
            [cast(dict[str, object], item) for item in cast(list[object], results_value) if isinstance(item, dict)]
            if isinstance(results_value, list)
            else []
        )
        for result in results:
            status_value = result.get("status", "unknown")
            status = status_value if isinstance(status_value, str) else "unknown"
            icon = {"passed": "✅", "failed": "❌", "healed": "🔧", "skipped": "⏭"}.get(
                status,
                "❓",
            )
            result_duration = result.get("duration_ms", 0)
            duration_ms = float(result_duration) if isinstance(result_duration, (int, float)) else 0.0
            lines.append(
                f"- {icon} **{result.get('intent_id')}**: {result.get('message')} ({duration_ms:.0f}ms)",
            )
            if result.get("healed") and result.get("heal_details"):
                lines.append(f"  - 🩹 치유: {result.get('heal_details')}")

        return "\n".join(lines)
