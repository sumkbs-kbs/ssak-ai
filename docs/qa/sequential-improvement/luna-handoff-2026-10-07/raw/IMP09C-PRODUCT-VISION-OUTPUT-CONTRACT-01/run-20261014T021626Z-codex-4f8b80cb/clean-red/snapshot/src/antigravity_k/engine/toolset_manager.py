"""ToolsetManager — 시나리오별 도구 그룹 관리 시스템.

=================================================
Hermes Agent의 toolsets.py 패턴을 Ssak-Ai에 이식.

시나리오별 도구 조합을 프리셋으로 관리:
- coding: 파일 + 터미널 + 테스트 + Git
- research: 웹 검색 + 브라우저 + 파일
- debugging: 파일 + 터미널 + Git + 검색
- safe: 읽기 전용 도구만
- full: 모든 도구

사용법:
    manager = ToolsetManager()
    tools = manager.resolve("coding")     # ['read_file', 'write_file', ...]
    manager.set_active("debugging")       # 활성 toolset 변경
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TypedDict, TypeVar

from pydantic import JsonValue, TypeAdapter, ValidationError

logger = logging.getLogger("antigravity_k.engine.toolset_manager")

ToolsetDefinition = TypedDict(
    "ToolsetDefinition", {"description": str, "tools": list[str], "includes": list[str]}, total=False
)
ToolsetSummary = TypedDict(
    "ToolsetSummary",
    {"description": str, "tools": list[str], "includes": list[str], "resolved_count": int, "is_active": bool},
)


_ConfigValue = TypeVar("_ConfigValue")
_TOOLSET_ADAPTER: TypeAdapter[ToolsetDefinition] = TypeAdapter(ToolsetDefinition)
_CONFIG_MAP_ADAPTER: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


# ── 기본 Toolset 정의 ──

_BUILTIN_TOOLSETS: dict[str, ToolsetDefinition] = {
    "coding": {
        "description": "코딩 및 개발 도구 (파일 편집, 터미널, 테스트, Git)",
        "tools": [
            "read_file",
            "write_file",
            "edit_file",
            "replace_file_content",
            "glob_search",
            "grep_search",
            "list_directory",
            "run_bash_command",
            "interactive_pty",
            "git_status",
            "git_diff",
            "git_commit",
            "git_log",
            "test_runner",
            "auto_lint",
            "impact_analyzer",
        ],
        "includes": [],
    },
    "research": {
        "description": "리서치 및 정보 수집 도구 (웹 검색, 브라우저, 파일 읽기)",
        "tools": [
            "web_search",
            "browser_dom",
            "read_file",
            "list_directory",
            "glob_search",
            "grep_search",
        ],
        "includes": [],
    },
    "debugging": {
        "description": "디버깅 및 문제 해결 도구",
        "tools": [
            "read_file",
            "grep_search",
            "glob_search",
            "list_directory",
            "run_bash_command",
            "interactive_pty",
            "git_status",
            "git_diff",
            "git_log",
            "test_runner",
        ],
        "includes": ["research"],
    },
    "safe": {
        "description": "읽기 전용 안전 도구 (파일 수정/명령 실행 불가)",
        "tools": [
            "read_file",
            "list_directory",
            "glob_search",
            "grep_search",
            "git_status",
            "git_diff",
            "git_log",
            "web_search",
        ],
        "includes": [],
    },
    "agentic": {
        "description": "에이전틱 작업 도구 (서브에이전트, 위임, 아티팩트)",
        "tools": [
            "agent_spawn",
            "cowork_delegate",
            "write_artifact",
            "pr_creation",
        ],
        "includes": ["coding"],
    },
    "browser": {
        "description": "브라우저 자동화 도구",
        "tools": [
            "browser_dom",
            "web_search",
        ],
        "includes": [],
    },
    "docker": {
        "description": "Docker 컨테이너 도구",
        "tools": [
            "docker_bash_command",
        ],
        "includes": ["coding"],
    },
    "vision": {
        "description": "비전 및 이미지 분석 도구",
        "tools": [
            "computer_use",
            "vision_analyze",
        ],
        "includes": [],
    },
    "full": {
        "description": "모든 도구 (전체 접근)",
        "tools": [],
        "includes": [
            "coding",
            "research",
            "agentic",
            "browser",
            "docker",
            "vision",
        ],
    },
}


class ToolsetManager:
    """시나리오별 도구 그룹을 관리합니다.

    config.yaml에서 활성 toolset을 설정하거나,
    런타임에 동적으로 전환할 수 있습니다.
    """

    def __init__(
        self,
        custom_toolsets: Mapping[str, ToolsetDefinition] | None = None,
        active_toolset: str = "full",
    ):
        """Initialize the ToolsetManager.

        Args:
            custom_toolsets (dict[str, dict[str, Any]] | None): dict[str, dict[str, Any]] | None custom toolsets.
            active_toolset (str): str active toolset.

        """
        self._toolsets: dict[str, ToolsetDefinition] = dict(_BUILTIN_TOOLSETS)
        self._toolsets.update(custom_toolsets or {})
        self._active: str = active_toolset

    @property
    def active_toolset(self) -> str:
        """Active Toolset.

        Returns:
            str: The str result.

        """
        return self._active

    def set_active(self, name: str) -> bool:
        """활성 toolset을 변경합니다."""
        if name not in self._toolsets and name not in {"all", "*"}:
            logger.warning("Unknown toolset: %s", name)
            return False
        self._active = name
        logger.info("Active toolset changed to: %s", name)
        return True

    def resolve(self, name: str | None = None, visited: set[str] | None = None) -> list[str]:
        """Toolset 이름을 재귀적으로 해석하여 도구 목록을 반환합니다.

        includes 합성을 지원하며, 순환 참조를 감지합니다.
        """
        name = name or self._active
        if visited is None:
            visited = set()

        if name in {"all", "*", "full"}:
            all_tools: set[str] = set()
            for ts_name in self._toolsets:
                if ts_name != "full":
                    all_tools.update(self.resolve(ts_name, visited.copy()))
            return sorted(all_tools)

        if name in visited:
            return []
        visited.add(name)

        toolset = self._toolsets.get(name)
        if not toolset:
            logger.debug("Toolset not found: %s", name)
            return []

        tools: set[str] = set(toolset.get("tools", []))

        for included in toolset.get("includes", []):
            tools.update(self.resolve(included, visited))

        return sorted(tools)

    def get_active_tools(self) -> list[str]:
        """현재 활성 toolset의 도구 목록을 반환합니다."""
        return self.resolve(self._active)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """도구가 현재 활성 toolset에 포함되어 있는지 확인합니다."""
        if self._active in {"all", "*", "full"}:
            return True
        return tool_name in self.resolve(self._active)

    def list_toolsets(self) -> dict[str, ToolsetSummary]:
        """등록된 모든 toolset 정보를 반환합니다."""
        result: dict[str, ToolsetSummary] = {}
        for name, ts in self._toolsets.items():
            result[name] = {
                "description": ts.get("description", ""),
                "tools": ts.get("tools", []),
                "includes": ts.get("includes", []),
                "resolved_count": len(self.resolve(name)),
                "is_active": name == self._active,
            }
        return result

    def add_toolset(
        self,
        name: str,
        description: str,
        tools: list[str] | None = None,
        includes: list[str] | None = None,
    ) -> None:
        """런타임에 커스텀 toolset을 추가합니다."""
        self._toolsets[name] = {
            "description": description,
            "tools": tools or [],
            "includes": includes or [],
        }
        logger.info("Custom toolset added: %s", name)

    @classmethod
    def from_config(cls, config: Mapping[str, _ConfigValue] | None = None) -> "ToolsetManager":
        """config.yaml의 `toolsets` 섹션에서 인스턴스를 생성합니다."""
        if not isinstance(config, Mapping):
            return cls()

        active_value = config.get("active")
        active = active_value if isinstance(active_value, str) else "full"
        custom_value = config.get("custom")
        custom: dict[str, ToolsetDefinition] = {}
        try:
            config_items = _CONFIG_MAP_ADAPTER.validate_python(custom_value)
        except ValidationError:
            config_items = {}
        for raw_name, raw_definition in config_items.items():
            if not isinstance(raw_definition, dict):
                continue
            try:
                custom[raw_name] = _TOOLSET_ADAPTER.validate_python(raw_definition)
            except ValidationError:
                logger.warning("Invalid toolset definition ignored: %s", raw_name)

        return cls(custom_toolsets=custom, active_toolset=active)
