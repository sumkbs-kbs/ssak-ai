"""Impact Analyzer Tool.

=====================
파일 수정 전후로 해당 파일/심볼을 의존하는 다른 파일과 테스트를 검색하여 영향도를 분석하는 도구.
"""

import logging
import os
import subprocess
from typing import TypeAlias, final, override

from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

JsonMap: TypeAlias = dict[str, object]


@final
class ImpactAnalyzerTool(BaseTool):
    """특정 파일이나 키워드의 변경이 프로젝트 내 다른 파일에 미치는 영향을 분석합니다."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🕸️"
    tags: list[str] = ["impact", "analysis", "dependency", "search"]

    def __init__(self):
        """Initialize the ImpactAnalyzerTool."""
        super().__init__()
        self._name: str = "impact_analyzer"
        self._description: str = (
            "Analyzes the impact of a file change by searching for its dependencies, "
            "usages, and related tests across the project."
        )
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "The file path that was or will be modified (e.g., src/utils.py)",
                },
                "symbol_name": {
                    "type": "string",
                    "description": "(Optional) Specific class or function name to search for usages.",
                },
            },
            "required": ["target_path"],
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
    def parameters_schema(self) -> JsonMap:
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
        raw_target_path = kwargs.get("target_path")
        target_path = raw_target_path if isinstance(raw_target_path, str) else ""
        raw_symbol_name = kwargs.get("symbol_name")
        symbol_name = raw_symbol_name if isinstance(raw_symbol_name, str) else ""

        if not target_path:
            return "Error: target_path is required."

        base_name = os.path.basename(target_path)
        module_name = os.path.splitext(base_name)[0]

        search_terms: list[str] = []
        if symbol_name:
            search_terms.append(symbol_name)
        else:
            search_terms.append(module_name)

        # 1. 의존성 검색 (git grep 활용)
        affected_files: set[str] = set()
        for term in search_terms:
            try:
                # git grep은 빠른 전체 검색 제공
                result = subprocess.run(
                    ["git", "grep", "-l", term],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and result.stdout:
                    files: list[str] = result.stdout.strip().split("\n")
                    affected_files.update(files)
                else:
                    # fallback to standard grep if git is not available or no results
                    result = subprocess.run(
                        [
                            "grep",
                            "-rl",
                            "--exclude-dir=.git",
                            "--exclude-dir=node_modules",
                            "--exclude-dir=__pycache__",
                            term,
                            ".",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout:
                        files = [f.removeprefix("./") for f in result.stdout.strip().split("\n")]
                        affected_files.update(files)
            except Exception:
                logger.exception("Unhandled exception")
                pass

        # 2. 관련 테스트 파일 추론
        test_files: list[str] = []
        source_files: list[str] = []
        for f in affected_files:
            if "test" in f.lower() or "spec" in f.lower():
                test_files.append(f)
            else:
                if f != target_path:
                    source_files.append(f)

        # 3. 결과 리포트 포맷팅
        report: list[str] = []
        report.append(f"📊 Impact Analysis Report for: {target_path}")
        if symbol_name:
            report.append(f"🔍 Tracing symbol: {symbol_name}")
        report.append("=" * 50)

        report.append(f"\n📂 Total files potentially affected: {len(affected_files)}")

        report.append(f"\n🧩 Dependent Source Files ({len(source_files)}):")
        if source_files:
            for sf in sorted(source_files)[:15]:
                report.append(f"  - {sf}")
            if len(source_files) > 15:
                report.append(f"  ... and {len(source_files) - 15} more")
        else:
            report.append("  None found.")

        report.append(f"\n🧪 Related Test Files ({len(test_files)}):")
        if test_files:
            for tf in sorted(test_files)[:10]:
                report.append(f"  - {tf}")
            if len(test_files) > 10:
                report.append(f"  ... and {len(test_files) - 10} more")
        else:
            report.append("  None found. (Warning: This change might not be covered by tests)")

        report.append("\n⚠️ Recommendation:")
        if test_files:
            report.append("  Please run the related tests above to ensure no breaking changes.")
        else:
            report.append("  Consider adding unit tests for the modified component.")

        return "\n".join(report)
