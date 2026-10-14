"""Execution Mode — Plan/Build/Interactive 실행 모드 열거형 및 정책.

========================================================
Phase 1: 명시적 Plan/Build 모드 분리.

Plan Mode:
    - 읽기 전용 도구(read_file, grep, glob) + 분석 도구만 허용
    - 쓰기/실행 도구는 "PLAN 모드에서는 차단" 응답
    - Agent가 implementation_plan.md 생성 유도

Build Mode:
    - 모든 도구 실행 허용
    - Plan 아티팩트 검증 완료 후 자동 진입

Interactive Mode:
    - 기존 동작 (Plan/Build 미사용)
"""

from __future__ import annotations

from enum import Enum

# ─── PLAN 모드에서 허용되는 읽기 전용 도구 ─────────────────────────
PLAN_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "glob_search",
        "grep_search",
        "list_directory",
        "hex_dump",
        "git_status",
        "git_log",
        "git_diff",
        "web_search",
        "web_scrape",
        "fetch_dom",
        "search_knowledge",
        "impact_analyzer",
        "write_artifact",  # Plan 아티팩트 생성을 위해 허용
    },
)

# ─── BUILD 모드에서 제한되는 위험 도구 (추가 approval 필요) ────────
BUILD_RESTRICTED_TOOLS: frozenset[str] = frozenset(
    {
        "db_migration",
        "deploy",
        "payment",
        "computer_use",
        "agent_spawn",
    },
)


class ExecutionMode(str, Enum):
    """실행 모드 열거형.

    Plan  : 계획 수립 모드 — 읽기 전용 도구 + 분석 + write_artifact만 허용
    Build : 빌드 모드 — 모든 도구 허용 (Plan 승인 후 자동 진입)
    Interactive : 기존 대화형 모드 (Plan/Build 미사용)
    """

    PLAN = "plan"
    BUILD = "build"
    INTERACTIVE = "interactive"

    @property
    def is_plan(self) -> bool:
        return self == ExecutionMode.PLAN

    @property
    def is_build(self) -> bool:
        return self == ExecutionMode.BUILD

    @property
    def is_interactive(self) -> bool:
        return self == ExecutionMode.INTERACTIVE

    def tool_is_allowed(self, tool_name: str) -> bool:
        """현재 모드에서 도구 실행이 허용되는지 확인합니다.

        Args:
            tool_name: 도구 이름

        Returns:
            True이면 허용, False이면 차단/거부
        """
        if self == ExecutionMode.PLAN:
            # PLAN 모드: 읽기 전용 도구 + write_artifact만 허용
            return tool_name in PLAN_ALLOWED_TOOLS

        if self == ExecutionMode.BUILD:
            # BUILD 모드: 모든 도구 허용 (restricted 도구는 별도 approval)
            return True  # restricted 도구는 GatePipeline에서 처리

        # INTERACTIVE 모드: 모든 도구 허용
        return True

    def tool_requires_approval(self, tool_name: str) -> bool:
        """현재 모드에서 도구 실행 시 사용자 승인이 필요한지 확인합니다.

        Args:
            tool_name: 도구 이름

        Returns:
            True이면 사용자 승인 필요
        """
        if self == ExecutionMode.BUILD:
            # BUILD 모드에서 restricted 도구는 승인 필요
            return tool_name in BUILD_RESTRICTED_TOOLS

        if self == ExecutionMode.PLAN:
            # PLAN 모드: 허용 도구 외에는 모두 차단되므로 승인은 의미 없음
            return False

        # INTERACTIVE 모드: 기본 정책 따름
        return False

    def get_block_reason(self, tool_name: str) -> str:
        """현재 모드에서 도구가 차단된 이유를 반환합니다.

        Args:
            tool_name: 도구 이름

        Returns:
            차단 사유 문자열 (허용되는 도구면 빈 문자열)
        """
        if self == ExecutionMode.PLAN and not self.tool_is_allowed(tool_name):
            return (
                f"[PLAN MODE] '{tool_name}' 도구는 계획 수립 모드에서 실행할 수 없습니다. "
                f"읽기 전용 도구(read_file, grep, glob 등)와 write_artifact만 허용됩니다. "
                f"/build 명령어로 빌드 모드로 전환하거나 Plan 작성을 완료하세요."
            )
        return ""
