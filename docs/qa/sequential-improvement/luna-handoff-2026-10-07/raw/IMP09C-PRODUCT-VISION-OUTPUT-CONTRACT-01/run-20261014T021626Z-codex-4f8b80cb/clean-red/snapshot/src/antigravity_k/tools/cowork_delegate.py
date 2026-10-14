"""Cowork Delegate module."""

import logging
from collections.abc import Mapping
from importlib import import_module
from typing import Protocol, cast, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

# 주의: task_runner와 orchestrator는 순환 참조 방지를 위해 execute() 내부에서 지연 import

logger = logging.getLogger(__name__)


class _ModelManagerLike(Protocol):
    pass


class _TaskRunnerLike(Protocol):
    def submit_task(
        self,
        prompt: str,
        context: Mapping[str, object] | None = None,
        orchestrator: object | None = None,
        target_model: str = "",
        use_worktree: bool = False,
    ) -> str: ...


class _OrchestratorFactory(Protocol):
    def __call__(self, *, model_manager: _ModelManagerLike | None) -> object: ...


class CoworkDelegateTool(BaseTool):
    """Claude Cowork 철학을 반영하여, 메인 에이전트가 복잡한 백그라운드 태스크(정보 수집, 파일 수정, 분석 등)를.

    격리된 워크트리 환경에서 수행할 '서브 에이전트(Sub-Agent)'를 스폰합니다.
    """

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🤝"
    tags: list[str] = ["cowork", "delegate", "subagent", "background", "worktree"]

    def __init__(self, project_root: str | None = None, model_manager: _ModelManagerLike | None = None) -> None:
        """Initialize the CoworkDelegateTool.

        Args:
            project_root (str): str project root.
            model_manager: model manager.

        """
        super().__init__()
        self._name: str = "cowork_delegate"
        self._description: str = (
            "Delegate a complex, multi-step task (like research, mass file reading, or refactoring) to an autonomous Sub-Agent. "
            "The Sub-Agent will run in the background in an isolated Git Worktree so it won't block the main chat or conflict with current files. Returns a background Task ID."
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Highly detailed instructions for the Sub-Agent. What it needs to do, read, or write.",  # noqa: E501
                },
                "use_worktree": {
                    "type": "boolean",
                    "description": "Set to true to isolate the Sub-Agent in a separate git worktree (prevents git conflicts). Default true.",  # noqa: E501
                    "default": True,
                },
            },
            "required": ["prompt"],
        }
        self.project_root: str | None = project_root
        self.model_manager: _ModelManagerLike | None = model_manager

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
    def parameters_schema(self) -> dict[str, object]:
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
        raw_prompt = kwargs.get("prompt", "")
        prompt = raw_prompt if isinstance(raw_prompt, str) else ""
        raw_use_worktree = kwargs.get("use_worktree", True)
        use_worktree = raw_use_worktree if isinstance(raw_use_worktree, bool) else True

        if not prompt:
            return "Error: Prompt is required."

        try:
            if not self.model_manager:
                return "Error: model_manager is not initialized in CoworkDelegateTool."

            # 지연 import (순환 참조 방지)
            from antigravity_k.engine.task_runner import get_task_runner

            runner = cast(_TaskRunnerLike, get_task_runner())
            # Create a dedicated Orchestrator for the sub-agent
            orchestrator_module = import_module("antigravity_k.engine.orchestrator")
            orchestrator_factory = cast(_OrchestratorFactory, getattr(orchestrator_module, "OrchestratorAgent"))
            sub_orchestrator = orchestrator_factory(model_manager=self.model_manager)

            # Context can carry over some current path info
            context = {"cowork_mode": True, "project_root": self.project_root}

            task_id = runner.submit_task(
                prompt=(
                    f"[Coworker Sub-Agent] You are a delegated background agent. Goal:\n{prompt}\n\n"
                    "Please complete this task autonomously using your tools. When done, create an artifact with your final report so the main user can see it."
                ),
                context=context,
                orchestrator=sub_orchestrator,
                use_worktree=use_worktree,
            )

            return (
                f"[COWORK DELEGATED]\n"
                f"Successfully spawned a Sub-Agent to handle the task in the background.\n"
                f"Task ID: {task_id}\n"
                f"Worktree Isolated: {use_worktree}\n"
                f"You can continue chatting with the user while the coworker finishes the task."
            )
        except Exception as e:
            logger.exception("Cowork delegation failed")
            return f"Error spawning sub-agent: {e}"
