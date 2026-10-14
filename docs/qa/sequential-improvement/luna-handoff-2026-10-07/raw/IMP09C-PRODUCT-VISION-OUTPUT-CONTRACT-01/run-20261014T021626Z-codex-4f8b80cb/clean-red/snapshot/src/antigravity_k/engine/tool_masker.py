"""Active Tool Masker — Dynamic tool schema filtering for 30B model context optimization.

30B-class models experience significant attention drift and degraded instruction-following
when presented with 50+ tool schemas simultaneously.

ActiveToolMasker filters the active toolset based on:
1. Current ExecutionMode (PLAN, BUILD, INTERACTIVE)
2. Task Phase (Exploration/Research, Code Modification, Testing/Verification)
3. Safety and Security constraints
"""

import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from antigravity_k.engine.execution_mode import ExecutionMode

logger = logging.getLogger(__name__)

# Core tool categories for phase-based masking
PLAN_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "glob_search",
        "grep_search",
        "list_directory",
        "git_status",
        "git_log",
        "git_diff",
        "web_search",
        "web_scrape",
        "search_knowledge",
        "impact_analyzer",
        "read_context_artifact",
        "write_artifact",
    }
)

CODE_EDIT_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "write_file",
        "replace_file_content",
        "multi_replace_file_content",
        "glob_search",
        "grep_search",
        "list_directory",
        "git_status",
        "git_diff",
        "run_command",
        "read_context_artifact",
        "write_artifact",
    }
)

VERIFICATION_TOOLS: frozenset[str] = frozenset(
    {
        "run_command",
        "read_file",
        "read_context_artifact",
        "git_status",
        "git_diff",
        "write_artifact",
    }
)

EDIT_TASK_TYPES: frozenset[str] = frozenset({"CODE", "CODING", "IMPLEMENTATION", "REFACTOR", "FIX"})
VERIFICATION_TASK_TYPES: frozenset[str] = frozenset({"TEST", "TESTING", "VERIFY", "VERIFICATION", "VALIDATE"})


@runtime_checkable
class _ToolMapping(Protocol):
    def get(self, key: str, default: object = None) -> object: ...


class ActiveToolMasker:
    """Masks and slims the toolset exposed to LLM prompts to prevent attention dilution."""

    def __init__(self, mode: ExecutionMode = ExecutionMode.BUILD) -> None:
        self.current_mode: ExecutionMode = mode

    @staticmethod
    def phase_for_task_type(task_type: str) -> str | None:
        normalized = task_type.strip().upper()
        if normalized in EDIT_TASK_TYPES:
            return "edit"
        if normalized in VERIFICATION_TASK_TYPES:
            return "test"
        return None

    def filter_tools(
        self,
        all_tools: Sequence[object],
        mode: ExecutionMode | None = None,
        phase: str | None = None,
    ) -> list[object]:
        """Filter a list of tool objects or dict schemas according to active constraints.

        Args:
            all_tools: List of Tool instances or JSON schema dicts.
            mode: Optional override for ExecutionMode.
            phase: Optional subtask phase ('explore', 'edit', 'test').

        Returns:
            Filtered list of tools.
        """
        active_mode = mode or self.current_mode
        allowed_names: frozenset[str] | None = None

        if active_mode == ExecutionMode.PLAN:
            allowed_names = PLAN_TOOLS
        elif phase == "edit":
            allowed_names = CODE_EDIT_TOOLS
        elif phase == "test":
            allowed_names = VERIFICATION_TOOLS

        if allowed_names is None:
            return list(all_tools)

        filtered: list[object] = []
        for tool in all_tools:
            name = _tool_name(tool)

            if name and name in allowed_names:
                filtered.append(tool)

        # Fallback: never return completely empty tools list if original was non-empty
        if not filtered and all_tools:
            logger.warning("ActiveToolMasker filtered all tools, falling back to original.")
            return list(all_tools)

        return filtered


def _tool_name(tool: object) -> str | None:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if not isinstance(tool, _ToolMapping):
        return None
    direct_name = tool.get("name")
    if isinstance(direct_name, str):
        return direct_name
    function = tool.get("function")
    if not isinstance(function, _ToolMapping):
        return None
    nested_name = function.get("name")
    return nested_name if isinstance(nested_name, str) else None
