"""System Tools module."""

import logging
import os
import subprocess
from typing import Any, Protocol, TypeAlias, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

ToolValue: TypeAlias = object
ToolSchema: TypeAlias = dict[str, Any]  # pyright: ignore[reportExplicitAny]


class _OrchestratorLike(Protocol):
    def run_sync(self, messages: list[dict[str, object]], *, target_model: object) -> str: ...


class _OrchestratorFactory(Protocol):
    def __call__(self, *, model_manager: object) -> _OrchestratorLike: ...


@final
class ReadFileTool(BaseTool):
    """Readfiletool.

    Bases: BaseTool
    """

    category = ToolCategory.FILE_IO
    render_in = RenderIn.TOOLBAR
    risk_level = RiskLevel.SAFE
    icon = "📄"
    tags = ["file", "read", "io", "view"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the ReadFileTool."""
        super().__init__()
        self._name = "read_file"
        self._description = (
            "Reads the content of a file. Supports optional line range selection "
            "with start_line and end_line for efficient partial reading of large files."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed). Omit to read from beginning.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-indexed, inclusive). Omit to read to end.",
                },
            },
            "required": ["file_path"],
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
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        file_path = cast(str | os.PathLike[str] | None, kwargs.get("file_path"))
        start_line = cast(int | None, kwargs.get("start_line"))
        end_line = cast(int | None, kwargs.get("end_line"))

        if not file_path or not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
        try:
            with open(file_path, encoding="utf-8") as f:
                if start_line or end_line:
                    lines = f.readlines()
                    total = len(lines)
                    s = max(1, start_line or 1) - 1
                    e = min(total, end_line or total)
                    selected = lines[s:e]
                    # 줄 번호 포함 출력
                    numbered = [f"{i + s + 1}: {line}" for i, line in enumerate(selected)]
                    header = f"[Showing lines {s + 1}-{e} of {total} total]\n"
                    return header + "".join(numbered)
                else:
                    content = f.read()
                    # 800줄 초과 시 자동 truncate (컨텍스트 절약)
                    lines = content.split("\n")
                    if len(lines) > 800:
                        truncated = "\n".join(lines[:800])
                        return (
                            f"{truncated}\n\n[... truncated, {len(lines)} total lines. "
                            f"Use start_line/end_line for specific ranges.]"
                        )

                    return content
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error reading file: {e}"


@final
class ReplaceFileContentTool(BaseTool):
    """Replacefilecontenttool.

    Bases: BaseTool
    """

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.LOW
    icon = "✏️"
    tags = ["file", "write", "edit"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the ReplaceFileContentTool."""
        super().__init__()
        self._name = "replace_file_content"
        self._description = "Replaces a specific block of text in a file with new content."
        self._schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to modify.",
                },
                "target_text": {
                    "type": "string",
                    "description": "Exact text to be replaced.",
                },
                "replacement_text": {
                    "type": "string",
                    "description": "New text to replace the target text.",
                },
            },
            "required": ["file_path", "target_text", "replacement_text"],
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
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        file_path = cast(str | os.PathLike[str] | None, kwargs.get("file_path"))
        target_text = cast(str, kwargs.get("target_text", ""))
        replacement_text = cast(str, kwargs.get("replacement_text", ""))

        if not file_path:
            return "Error: No file_path provided."
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            if target_text not in content:
                return "Error: Target text not found in file."

            new_content = content.replace(target_text, replacement_text)

            with open(file_path, "w", encoding="utf-8") as f:
                _ = f.write(new_content)

            return f"Successfully updated {file_path}."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error replacing content: {e}"


@final
class RunBashCommandTool(BaseTool):
    """Runbashcommandtool.

    Bases: BaseTool
    """

    category = ToolCategory.CODE_EXEC
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.HIGH
    icon = "⚡"
    tags = ["shell", "command", "bash", "exec"]
    _execution_permit: object
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the RunBashCommandTool."""
        super().__init__()
        self._execution_permit = object()
        self._name = "run_bash_command"
        self._description = (
            "Executes a shell command. Requires Human-In-The-Loop (HITL) approval unless Autopilot is enabled."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Absolute project working directory (injected by tool runtime).",
                },
            },
            "required": ["command"],
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
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        command = cast(str, kwargs.get("command", ""))
        if not command:
            return "Error: No command provided."

        if kwargs.get("_execution_permit") is not self._execution_permit:
            return "[APPROVAL REQUIRED] run_bash_command must be executed through the permission boundary."

        logger.info("Executing approved command: %s", command)

        try:
            # WS-02: explicit project cwd (rewritten by ToolRegistry); never ambient process cwd.
            from .tool_path import effective_project_root

            raw_cwd = kwargs.get("cwd")
            cwd = str(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd.strip() else effective_project_root()

            # FR-02/RP-02: 모델 제공 shell 명령은 항상 OS sandbox에서 실행한다.
            # sandbox를 보장할 수 없으면 명령을 거부하며 raw host 실행이 없다.
            return self._run_with_sandbox(command, cwd=cwd)
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error executing command: {e}"

    def _run_with_sandbox(
        self,
        command: str,
        *,
        cwd: str | None = None,
    ) -> str:
        """모델 제공 shell 명령을 OS sandbox로 실행하거나 거부한다 (P2-1, FR-02/RP-02).

        Returns:
            결과 문자열. sandbox 비활성/백엔드 부재는 거부 오류 문자열이며
            raw host 실행 폴백은 존재하지 않는다.
        """
        try:
            from ..config import config as app_config
            from ..engine.sandbox import SandboxRunner, _minimal_child_env
            from .tool_path import effective_project_root

            sandbox_enabled = getattr(app_config.security, "sandbox_enabled", False)
            if not sandbox_enabled:
                return (
                    "Error: run_bash_command requires an enabled OS sandbox "
                    "(security.sandbox_enabled=true); raw host execution is disabled."
                )

            project_cwd = cwd or effective_project_root(str(app_config.paths.project_root))
            from ..engine.sandbox import _python_runtime_read_paths

            runner = SandboxRunner(
                project_root=project_cwd,
                enabled=True,
                network=getattr(app_config.security, "sandbox_network", "none"),
                timeout=60,
                # FR-02: 사용자 트리/공유 임시 디렉토리 읽기와 root 밖 쓰기를 차단한다.
                restrict_reads=True,
                read_allow_paths=[project_cwd, *_python_runtime_read_paths()],
            )
            # 최소 자식 환경: 부모 os.environ/provider 시크릿을 상속하지 않는다.
            child_env = _minimal_child_env(runner.project_root)
            result = runner.execute(command, env=child_env, cwd=project_cwd)
            if not result.sandboxed:
                return "Error: sandbox could not be applied; raw host execution is disabled."
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.timed_out:
                return f"Error: {result.error}"
            if not result.success:
                output_part = result.error or result.stderr or "Sandbox execution failed."
                return f"[exit_code={result.return_code}]\n{output_part}"
            return (output if output else "Command executed successfully.") + " [sandboxed]"
        except Exception:
            logger.exception("Sandbox execution failed")
            return "Error: sandbox execution failed; raw execution is disabled."


@final
class ListDirectoryTool(BaseTool):
    """디렉토리 탐색 도구.

    프로젝트 구조를 파악하기 위한 필수 도구.
    """

    category = ToolCategory.SEARCH
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.SAFE
    icon = "📂"
    tags = ["directory", "list", "explore", "tree"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the ListDirectoryTool."""
        super().__init__()
        self._name = "list_directory"
        self._description = (
            "Lists files and directories in a path. Shows file sizes and types. "
            "Excludes common non-essential directories like node_modules, .git, __pycache__."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list.",
                    "default": ".",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively (max 3 levels).",
                    "default": False,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max recursion depth.",
                    "default": 3,
                },
            },
            "required": [],
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
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        path = cast(str, kwargs.get("path", "."))
        recursive = cast(bool, kwargs.get("recursive", False))
        max_depth = cast(int, kwargs.get("max_depth", 3))

        IGNORE = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".tox",
            "dist",
            "build",
            ".eggs",
            ".mypy_cache",
            ".pytest_cache",
            ".next",
        }

        if not os.path.isdir(path):
            return f"Error: '{path}' is not a directory."

        def _format_size(size: float) -> str:
            for unit in ["B", "KB", "MB", "GB"]:
                if size < 1024:
                    return f"{size:.0f}{unit}"
                size /= 1024
            return f"{size:.1f}TB"

        def _list(dir_path: str, depth: int = 0) -> list[str]:
            items: list[str] = []
            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                return [f"{'  ' * depth}[Permission denied]"]

            dirs: list[str] = []
            files: list[str] = []
            for e in entries:
                if e in IGNORE or e.startswith("."):
                    continue
                full = os.path.join(dir_path, e)
                if os.path.isdir(full):
                    dirs.append(e)
                else:
                    files.append(e)

            for d in dirs:
                full = os.path.join(dir_path, d)
                child_count = (
                    len([x for x in os.listdir(full) if x not in IGNORE and not x.startswith(".")])
                    if os.path.isdir(full)
                    else 0
                )
                items.append(f"{'  ' * depth}📁 {d}/ ({child_count} items)")
                if recursive and depth < max_depth:
                    items.extend(_list(full, depth + 1))

            for f_name in files:
                full = os.path.join(dir_path, f_name)
                try:
                    size = _format_size(os.path.getsize(full))
                except OSError:
                    size = "?"
                items.append(f"{'  ' * depth}📄 {f_name} ({size})")

            return items

        lines = _list(path)
        if not lines:
            return f"Directory '{path}' is empty or contains only hidden/ignored files."

        header = f"Directory: {os.path.abspath(path)}\n{'=' * 40}\n"
        return header + "\n".join(lines[:200])  # 최대 200항목


@final
class NaturalLanguageBashTool(BaseTool):
    """AiShell: Natural Language to Bash Command Tool.

    에이전트가 복잡한 bash 명령어의 문법을 고민하지 않고 자연어로 의도를 전달하면,
    LLM을 통해 정확한 쉘 명령어로 변환하여 실행합니다.
    """

    category = ToolCategory.SYSTEM
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.MEDIUM
    icon = "🤖"
    tags = ["bash", "shell", "nlp", "aishell"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the NaturalLanguageBashTool."""
        super().__init__()
        self._name = "aishell"
        self._description = (
            "Translate a natural language task into a macOS shell command and execute it. "
            "Use this when you want to run complex commands (awk, sed, ffmpeg, git) but are unsure of the exact syntax."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Natural language description of what you want to do (e.g. 'find all python files modified yesterday')",  # noqa: E501
                },
            },
            "required": ["intent"],
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
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        intent = cast(str, kwargs.get("intent", ""))
        if not intent:
            return "Error: No intent provided."

        try:
            from ..engine.model_manager import ModelManager

            prompt = (
                "Translate the following task to a macOS shell command. Users provide a text-query as input.\nProvide ONLY the"  # noqa: E501
                f"command in ONE LINE, with no explanation:\n\nOne-line command for: {intent}"
            )

            try:
                from ..engine.model_registry import ModelRegistry

                model_manager = ModelManager(registry=ModelRegistry())
                orchestrator_module = cast(
                    object,
                    __import__(
                        "antigravity_k.engine.orchestrator",
                        fromlist=["OrchestratorAgent"],
                    ),
                )
                module_dict = cast(dict[str, object], getattr(orchestrator_module, "__dict__", {}))
                orchestrator_factory = cast(_OrchestratorFactory, module_dict["OrchestratorAgent"])
                orchestrator = orchestrator_factory(model_manager=model_manager)
                target_model = model_manager.get_target_for_role("natural_language_bash", default_role="coding")

                messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
                command = orchestrator.run_sync(messages, target_model=target_model).strip()

                # Remove markdown code blocks if any
                if command.startswith("```"):
                    lines = command.split("\n")
                    command = (
                        "\n".join(lines[1:-1])
                        if len(lines) > 2
                        else command.replace("```bash", "").replace("```sh", "").replace("```", "")
                    )
            except Exception as e:
                logger.exception("Unhandled exception")
                return f"Error translating intent to bash via ModelManager: {e}"

            logger.info("AiShell translated '%s' -> `%s`", intent, command)

            output = RunBashCommandTool()._run_with_sandbox(command)
            return f"Executed Command: `{command}`\n\nOutput:\n{output}"

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"AiShell execution failed: {e}"
