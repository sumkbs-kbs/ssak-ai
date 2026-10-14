"""Browser Subagent Tool.

=====================
자율적으로 브라우저를 탐색하고 QA 테스트를 수행하는 Sub-Agent를 스폰합니다.
메인 에이전트의 컨텍스트를 보호하면서 독립된 공간에서 복잡한 웹 조작을 수행합니다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, override

from antigravity_k.engine.subagent_execution import start_subagent_stream
from antigravity_k.engine.task_runner import get_task_runner

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

if TYPE_CHECKING:
    from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class BrowserSubagentTool(BaseTool):
    """브라우저 전용 Sub-Agent를 스폰하여 복잡한 웹 조작 및 QA 테스트를 자율적으로 수행합니다.

    테스트가 완료되면 결과 리포트와 함께 생성된 녹화 비디오 경로를 반환합니다.
    """

    category: ToolCategory = ToolCategory.WEB
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.MEDIUM
    icon: str = "🤖🌐"
    tags: list[str] = ["browser", "subagent", "qa", "test", "automation", "video"]

    def __init__(self, model_manager: object | None = None, tool_registry: ToolRegistry | None = None) -> None:
        """Initialize the BrowserSubagentTool.

        Args:
            model_manager: model manager.
            tool_registry: tool registry.

        """
        super().__init__()
        self._name: str = "browser_subagent"
        self._description: str = (
            "Spawns an autonomous browser subagent to perform actions in the browser with the given task description. "
            "The subagent has access to browser automation tools to interact with web pages and read files. "
            "It automatically records a video of its session. "
            "Return a detailed QA report of its findings and actions. Use this for complex, multi-step browser interactions."  # noqa: E501
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "Task": {
                    "type": "string",
                    "description": "A clear, actionable task description for the browser QA subagent.",
                },
                "Url": {
                    "type": "string",
                    "description": "The initial URL to start testing from (optional).",
                },
            },
            "required": ["Task"],
        }
        self._model_manager: object | None = model_manager
        self._tool_registry: ToolRegistry | None = tool_registry

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
    def parameters_schema(self) -> Mapping[str, object]:
        """Parameters Schema.

        Returns:
            Mapping[str, object]: The tool parameter schema.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> object:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            object: The execution result.

        """
        task_value = kwargs.get("Task", "")
        url_value = kwargs.get("Url", "")
        task = task_value if isinstance(task_value, str) else ""
        url = url_value if isinstance(url_value, str) else ""

        if not task:
            return "Error: No Task description provided."

        if not self._model_manager:
            return self._fallback_execute(task, url)

        try:
            return self._spawn_browser_subagent(task, url)
        except Exception as e:
            logger.error("Browser Sub-Agent spawn failed: %s", e, exc_info=True)
            return f"Error: Browser Sub-Agent failed: {e}"

    def _spawn_browser_subagent(self, task: str, url: str) -> str:
        """실제 Orchestrator 루프를 통한 Browser Sub-Agent 실행."""
        start_time = time.time()

        from antigravity_k.api.dependencies import get_vault_engine
        from antigravity_k.engine.orchestrator import OrchestratorAgent

        # 메인 에이전트와 ToolRegistry를 공유하지만,
        # BrowserSubagent는 제한된 도구만 사용하도록 유도합니다.
        sub_orchestrator = OrchestratorAgent(
            model_manager=self._model_manager,
            vault_engine=get_vault_engine(),
            tool_registry=self._tool_registry,
        )

        target_model = sub_orchestrator.get_model_for_role("WORKER")

        system_prompt = (
            "You are an autonomous Browser QA Sub-Agent. Your primary objective is to navigate the web, "
            "test user interfaces, and rigorously verify functionality based on the user's task.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. You MUST use the 'browser' tool to interact with the web page. This tool provides actions like "
            "'goto', 'click', 'type', 'semantic_snapshot', 'click_by_intent', and 'read_dom'.\n"
            "2. If an initial URL is provided, start by navigating to it using action='goto'.\n"
            "3. Analyze the page DOM carefully before interacting.\n"
            "4. When your task is fully completed, you MUST use the 'browser' tool with action='close' "
            "to clean up the session and finalize the video recording.\n"
            "5. The 'close' action will return the path to the recorded video. YOU MUST include this video path "
            "in your final response so the user can watch the session.\n"
            "6. Return a comprehensive QA report detailing what you tested, any bugs found, and the final state."
        )

        user_content = f"Task: {task}"
        if url:
            user_content += f"\nInitial URL: {url}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        logger.info("Starting autonomous Browser Sub-Agent for task: %s...", task[:50])

        tracked_stream = start_subagent_stream(
            sub_orchestrator,
            task_runner=get_task_runner(),
            messages=messages,
            target_model=target_model,
            subagent_kind="browser_subagent",
        )
        output_parts = list(tracked_stream.chunks)

        elapsed = time.time() - start_time
        result = "".join(output_parts)

        return f"### 🤖🌐 Browser Sub-Agent QA Report (Completed in {elapsed:.1f}s)\n{result}"

    def _fallback_execute(self, task: str, url: str) -> str:
        """ModelManager 미연결 시 폴백 (작업 기록만)."""
        return (
            f"[Browser Sub-Agent Queued]\n"
            f"Task: {task}\n"
            f"URL: {url if url else 'N/A'}\n"
            f"Note: Sub-agent execution requires a connected ModelManager. "
            f"Task has been recorded for manual review."
        )
