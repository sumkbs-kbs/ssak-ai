"""Docker Tools module."""

import logging
import subprocess
from typing import override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[str] | list[JsonValue] | dict[str, JsonValue]


class DockerBashCommandTool(BaseTool):
    """Docker 컨테이너 격리 환경(샌드박스)에서 Bash 명령을 실행합니다.

    위험한 코드 실행이나 악성코드 동적 분석 시 호스트 환경을 보호합니다.
    """

    category: ToolCategory = ToolCategory.CODE_EXEC
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.HIGH
    icon: str = "🐳"
    tags: list[str] = ["docker", "sandbox", "security", "execution"]

    def __init__(self) -> None:
        """Initialize the DockerBashCommandTool."""
        super().__init__()
        self._name: str = "run_docker_bash"
        self._description: str = (
            "Run a bash command strictly inside a Docker sandbox container. "
            "Use this for compiling unverified code, running suspicious binaries, or anything "
            "that might damage the host OS. By default, it uses 'ubuntu:latest'."
        )
        self._schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute in the container.",
                },
                "image": {
                    "type": "string",
                    "description": "Docker image to use. Default is 'ubuntu:latest'.",
                    "default": "ubuntu:latest",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds.",
                    "default": 30,
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
    def parameters_schema(self) -> dict[str, JsonValue]:
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
            str: The str result.

        """
        command_value = kwargs.get("command")
        command = command_value if isinstance(command_value, str) else ""
        image_value = kwargs.get("image", "ubuntu:latest")
        image = image_value if isinstance(image_value, str) else "ubuntu:latest"
        timeout_value = kwargs.get("timeout_seconds", 30)
        timeout = (
            float(timeout_value)
            if isinstance(timeout_value, (int, float)) and not isinstance(timeout_value, bool)
            else 30.0
        )

        if not command:
            return "Error: command is required."

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--memory=512m",
            "--cpus=1.0",
            image,
            "bash",
            "-c",
            command,
        ]

        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)

            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            if result.returncode != 0:
                output = f"Command failed with return code {result.returncode}.\n" + output

            return output if output else "Command executed successfully with no output."

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds."
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            logger.exception("Unhandled exception")
            return f"Error executing docker command: {e}\n(Is Docker running on the host?)"
