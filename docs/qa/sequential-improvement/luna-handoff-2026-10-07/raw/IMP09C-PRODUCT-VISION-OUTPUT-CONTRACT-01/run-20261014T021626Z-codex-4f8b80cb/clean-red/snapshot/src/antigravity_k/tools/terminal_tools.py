from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from io import TextIOBase
from pathlib import Path
from typing import ClassVar, TypeAlias, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
ToolValue: TypeAlias = str | int | float | bool | None


def _string_arg(kwargs: Mapping[str, object], key: str, default: str = "") -> str:
    value = kwargs.get(key)
    return value if isinstance(value, str) else default


def _wait_seconds(kwargs: Mapping[str, object], key: str = "wait_ms", default: int = 500) -> float:
    value = kwargs.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, value) / 1000.0
    return default / 1000.0


def build_sandbox_argv(command: str, project_root: str | None = None) -> tuple[list[str], Path] | None:
    """모델 제공 명령을 seatbelt 샌드박스 argv로 래핑한다.

    config의 security.sandbox_enabled가 true이고 macOS sandbox-exec을 쓸 수
    있으면 (argv, profile_path)를 반환하고, 아니면 None을 반환한다.
    profile 파일은 호출자가 프로세스 종료 후 삭제해야 한다.

    ``project_root``는 요청 스코프 루트다. 생략하면 config의 전역 루트로
    폴백하되, 권한 판정에 쓰인 루트와 실행 프로파일의 루트가 같아야 한다
    (FR-02/RP-02: 판정 root == 실행 root).

    이 헬퍼가 필요한 이유: system_tools의 단발 execute는 SandboxRunner로
    샌드박스되지만, persistent terminal/PTY 같은 장수명 프로세스는
    execute() 계약(호출 즉시 종료)과 맞지 않아 우회 경로가 됐다.
    """
    try:
        from ..config import config as app_config
        from ..engine.sandbox import SandboxRunner
    except ImportError:
        return None

    if not getattr(app_config.security, "sandbox_enabled", False):
        return None

    import platform as _platform
    import shutil as _shutil

    if _platform.system() != "Darwin" or _shutil.which("sandbox-exec") is None:
        return None

    root = project_root or str(getattr(app_config.paths, "project_root", "."))
    from ..engine.sandbox import _python_runtime_read_paths

    runner = SandboxRunner(
        project_root=root,
        enabled=True,
        network=getattr(app_config.security, "sandbox_network", "none"),
        # FR-02: 사용자 트리/공유 임시 디렉토리 읽기와 root 밖 쓰기를 차단한다.
        restrict_reads=True,
        read_allow_paths=[root, *_python_runtime_read_paths()],
    )
    try:
        profile_text = runner.build_seatbelt_profile()
    except Exception:
        logger.exception("seatbelt 프로파일 생성 실패 — 실행 거부")
        return None

    fd = tempfile.NamedTemporaryFile(mode="w", suffix=".sb", prefix="agk_term_", delete=False, encoding="utf-8")
    with fd:
        _ = fd.write(profile_text)
    profile_path = Path(fd.name)
    return ["sandbox-exec", "-f", str(profile_path), "/bin/sh", "-c", command], profile_path


def _cleanup_sandbox_profile(profile_path: Path | None) -> None:
    """샌드박스 프로파일 임시 파일을 정리한다."""
    if profile_path is not None:
        try:
            profile_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("profile cleanup failed: %s", profile_path)


class PersistentTerminalManager:
    _instance: ClassVar[PersistentTerminalManager | None] = None
    terminals: dict[str, subprocess.Popen[str]] = {}
    _profiles: dict[str, Path | None] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PersistentTerminalManager, cls).__new__(cls)
            cls._instance.terminals = {}
            cls._instance._profiles = {}
        return cls._instance

    def create_terminal(self, command: str, cwd: str) -> str:
        term_id = str(uuid.uuid4())[:8]

        wrapped = build_sandbox_argv(command, project_root=cwd)
        profile_path: Path | None = None
        if wrapped is None:
            # FR-02/RP-02: sandbox를 보장할 수 없으면 raw shell 실행을 하지 않는다.
            raise RuntimeError(
                "Persistent terminal requires an available OS sandbox "
                "(security.sandbox_enabled=true and sandbox-exec); raw host execution is disabled."
            )
        argv, profile_path = wrapped
        # FR-02: 부모 os.environ/provider 시크릿을 상속하지 않는 최소 환경.
        from ..engine.sandbox import _minimal_child_env

        process = subprocess.Popen(
            argv,
            shell=False,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_minimal_child_env(os.path.realpath(os.path.abspath(cwd))),
        )
        logger.info("[terminal %s] sandboxed execution enabled", term_id)
        # Using non-blocking IO for stdout/stderr would be better, but for simplicity:
        stdout = process.stdout
        stderr = process.stderr
        assert isinstance(stdout, TextIOBase)
        assert isinstance(stderr, TextIOBase)
        os.set_blocking(stdout.fileno(), False)
        os.set_blocking(stderr.fileno(), False)

        self.terminals[term_id] = process
        self._profiles[term_id] = profile_path
        return term_id

    def get_output(self, term_id: str) -> str:
        if term_id not in self.terminals:
            return f"Error: Terminal {term_id} not found."

        process = self.terminals[term_id]
        stdout = process.stdout
        stderr = process.stderr
        assert isinstance(stdout, TextIOBase)
        assert isinstance(stderr, TextIOBase)
        output = ""
        try:
            while True:
                line = f"{stdout.readline()}"
                if not line:
                    break
                output += line
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to read stdout for term_id %s: %s", term_id, e)

        try:
            while True:
                line = f"{stderr.readline()}"
                if not line:
                    break
                output += line
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to read stderr for term_id %s: %s", term_id, e)

        if process.poll() is not None:
            output += f"\n[Process exited with code {process.returncode}]"
            del self.terminals[term_id]
            profile = self._profiles.pop(term_id, None)
            if profile is not None:
                _cleanup_sandbox_profile(profile)

        return output

    def send_input(self, term_id: str, text: str) -> str:
        if term_id not in self.terminals:
            return f"Error: Terminal {term_id} not found."

        process = self.terminals[term_id]
        if process.poll() is not None:
            return "Error: Process already exited."

        try:
            assert process.stdin is not None
            _ = process.stdin.write(text + "\n")
            _ = process.stdin.flush()
            return "Input sent."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error sending input: {e}"


class RunPersistentCommandTool(BaseTool):
    """Run a long-running command in a persistent terminal."""

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.HIGH
    icon: str = "🖥️"
    tags: list[str] = ["terminal", "bash", "shell", "run", "background"]

    def __init__(self):
        super().__init__()
        self._name: str = "run_persistent_command"
        self._description: str = (
            "Run a long-running bash command in the background (e.g., servers, watchers). Returns a Terminal ID."
        )
        self._schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to run.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory. Default is current.",
                    "default": ".",
                },
            },
            "required": ["command"],
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        from .tool_path import effective_project_root

        command = _string_arg(kwargs, "command")
        cwd = _string_arg(kwargs, "cwd", "") or effective_project_root()

        manager = PersistentTerminalManager()
        try:
            term_id = manager.create_terminal(command, os.path.abspath(cwd))
            return f"Started command '{command}' in background. Terminal ID: {term_id}\nUse check_command_status tool to view output."  # noqa: E501
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error starting command: {e}"


class CheckCommandStatusTool(BaseTool):
    """Check output of a persistent terminal."""

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "👁️"
    tags: list[str] = ["terminal", "status", "output", "log"]

    def __init__(self):
        super().__init__()
        self._name: str = "check_command_status"
        self._description: str = (
            "Check the recent standard output and error of a persistent terminal by its Terminal ID."
        )
        self._schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {
                "terminal_id": {
                    "type": "string",
                    "description": "The Terminal ID returned by run_persistent_command.",
                }
            },
            "required": ["terminal_id"],
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        term_id = _string_arg(kwargs, "terminal_id")
        manager = PersistentTerminalManager()
        output = manager.get_output(term_id)
        return output if output.strip() else "[No new output]"


class SendCommandInputTool(BaseTool):
    """Send input to a persistent terminal."""

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.MEDIUM
    icon: str = "⌨️"
    tags: list[str] = ["terminal", "input", "stdin"]

    def __init__(self):
        super().__init__()
        self._name: str = "send_command_input"
        self._description: str = "Send standard input (stdin) to a running persistent terminal."
        self._schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "The Terminal ID."},
                "input_text": {"type": "string", "description": "The text to send."},
            },
            "required": ["terminal_id", "input_text"],
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        term_id = _string_arg(kwargs, "terminal_id")
        text = _string_arg(kwargs, "input_text")
        manager = PersistentTerminalManager()
        return manager.send_input(term_id, text)


class InteractivePTYTool(BaseTool):
    """
    PTY(가상 터미널)를 할당하여 대화형 프로그램(GDB, python -i 등)을 실행하고 상호작용합니다.
    단순 subprocess 파이프에서 발생하는 출력 깨짐이나 행(Hang) 현상을 방지합니다.
    """

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.MEDIUM
    icon: str = "📟"
    tags: list[str] = ["pty", "interactive", "gdb", "shell"]

    # Class-level state for simplicity. In a real system, use a manager.
    _active_pid: int | None = None
    _active_fd: int | None = None
    _active_profile: Path | None = None

    def __init__(self):
        super().__init__()
        self._name: str = "interactive_pty"
        self._description: str = (
            "Execute an interactive command (like GDB, radare2, or python REPL) within a pseudo-terminal (PTY) "
            "and wait for its output. Automatically strips ANSI escape sequences so the output is clean for the LLM. "
            "You can send continuous input to an ongoing session."
        )
        self._schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The interactive command to run (e.g., 'gdb ./a.out'). If a session is already running, this creates a NEW session.",  # noqa: E501
                },
                "input_text": {
                    "type": "string",
                    "description": "Text to send to the running PTY session. Include \n if you want to press Enter. Use this instead of 'command' to interact with an active session.",  # noqa: E501
                },
                "wait_ms": {
                    "type": "integer",
                    "description": "Milliseconds to wait for the output to settle. Default is 500ms.",
                    "default": 500,
                },
            },
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        command = _string_arg(kwargs, "command")
        input_text = _string_arg(kwargs, "input_text")
        wait_time = _wait_seconds(kwargs)

        if not command and not input_text:
            return "Error: You must provide either 'command' (to start) or 'input_text' (to interact)."

        import os
        import pty

        # Start a new session
        if command:
            if InteractivePTYTool._active_pid:
                self._cleanup_session()

            from .tool_path import effective_project_root

            wrapped = build_sandbox_argv(command, project_root=effective_project_root())
            if wrapped is None:
                # FR-02/RP-02: sandbox를 보장할 수 없으면 PTY raw exec를 하지 않는다.
                return (
                    "Error: interactive PTY requires an available OS sandbox "
                    "(security.sandbox_enabled=true and sandbox-exec); raw host execution is disabled."
                )
            pid, fd = pty.fork()
            if pid == 0:
                # Child process
                try:
                    argv, _profile_path = wrapped
                    os.execvp(argv[0], argv)
                except Exception as e:
                    logger.exception("Unhandled exception")
                    print(f"Exec failed: {e}")
                    import sys

                    sys.exit(1)
            else:
                # Parent process
                InteractivePTYTool._active_pid = pid
                InteractivePTYTool._active_fd = fd
                InteractivePTYTool._active_profile = wrapped[1] if wrapped is not None else None
                return self._read_until_settled(wait_time)

        # Interact with existing session
        if input_text:
            if not InteractivePTYTool._active_pid or InteractivePTYTool._active_fd is None:
                return "Error: No active PTY session. Start one by providing a 'command'."

            try:
                _ = os.write(InteractivePTYTool._active_fd, input_text.encode("utf-8"))
                return self._read_until_settled(wait_time)
            except OSError as e:
                self._cleanup_session()
                return f"Error writing to PTY: {e}. Session closed."

        return "Error: PTY session did not start."

    def _read_until_settled(self, timeout: float) -> str:
        import os
        import select
        import time

        output = b""
        start_time = time.time()

        while True:
            if InteractivePTYTool._active_fd is None:
                break
            r, _, _ = select.select([InteractivePTYTool._active_fd], [], [], timeout)
            if not r:
                break
            try:
                data = os.read(InteractivePTYTool._active_fd, 4096)
                if not data:
                    break
                output += data
            except OSError as e:
                logger.debug("PTY read interrupted or finished: %s", e)
                break
            if time.time() - start_time > 5.0:
                break

        text = output.decode("utf-8", errors="replace")
        return self._strip_ansi(text)

    def _strip_ansi(self, text: str) -> str:
        import re

        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def _cleanup_session(self):
        import os

        if InteractivePTYTool._active_pid:
            try:
                os.kill(InteractivePTYTool._active_pid, 9)
            except OSError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
            InteractivePTYTool._active_pid = None
        if InteractivePTYTool._active_fd:
            try:
                os.close(InteractivePTYTool._active_fd)
            except OSError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
            InteractivePTYTool._active_fd = None
        if InteractivePTYTool._active_profile is not None:
            _cleanup_sandbox_profile(InteractivePTYTool._active_profile)
            InteractivePTYTool._active_profile = None
