"""성장 benchmark(LIVE_PILOT 아님, deterministic fixture) 도구 wiring — adapter 계층.

계약(architecture guard, ``tests/cognitive/test_models.py``):

- ``antigravity_k.engine.cognitive``는 provider/UI/도구 계층(``antigravity_k.tools``,
  ``antigravity_k.engine.tool_executor``)을 import하지 않는다. Brain 교체성이 깨지기 때문이다.
- 그래서 fixture 도구·실제 ``ToolExecutor`` 결선은 **여기**에 둔다. cognitive는 ``ToolExecutorPort``만 받는다.
- 실제 파일 IO와 실제 ``ToolRegistry``/``ToolExecutor``를 쓴다. mock executor가 아니다.
  ``ImmuneSystem``은 무거우므로 이 fixture 표면에서만 연결을 끊는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final
from unittest.mock import patch

from antigravity_k.engine.cognitive.actions import ToolExecutorPort
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.tools.base_tool import BaseTool
from antigravity_k.tools.tool_registry import ToolRegistry

READ_TOOL_NAME: Final[str] = "fixture_read"
WRITE_TOOL_NAME: Final[str] = "fixture_write"

__all__ = [
    "READ_TOOL_NAME",
    "WRITE_TOOL_NAME",
    "FixtureReadTool",
    "FixtureWriteTool",
    "fixture_executor",
    "fixture_registry",
    "fixture_tool_port",
]


class FixtureReadTool(BaseTool):
    """fixture evidence 파일을 읽는 결정적 도구. 누락 evidence 하나당 1회 재시도로 쓰인다."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def name(self) -> str:
        return READ_TOOL_NAME

    @property
    def description(self) -> str:
        return "read a fixture evidence file (deterministic benchmark tool)"

    @property
    def parameters_schema(self) -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        }

    def execute(self, **kwargs: object) -> object:
        path = Path(str(kwargs["file_path"]))
        if not path.exists():
            return f"missing evidence file: {path.name}"
        return path.read_text(encoding="utf-8")


class FixtureWriteTool(BaseTool):
    """fixture 결과를 append하는 결정적 도구. 실제 파일 IO를 쓴다."""

    @property
    def name(self) -> str:
        return WRITE_TOOL_NAME

    @property
    def description(self) -> str:
        return "append a fixture line (deterministic benchmark tool)"

    @property
    def parameters_schema(self) -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    def execute(self, **kwargs: object) -> object:
        path = Path(str(kwargs["file_path"]))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(str(kwargs.get("content", "")) + "\n")
        return f"appended {path.name}"


def fixture_registry(root: Path) -> ToolRegistry:
    registry = ToolRegistry(project_root=str(root))
    getattr(registry, "install")(FixtureReadTool(root))
    getattr(registry, "install")(FixtureWriteTool())
    return registry


def fixture_executor(root: Path, registry: ToolRegistry) -> ToolExecutor:
    """실제 ToolExecutor를 쓴다. ImmuneSystem은 무거우므로 fixture에서는 연결을 끊는다."""

    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        executor = ToolExecutor(
            tool_registry=registry,
            permission_gate=registry.permission_gate,
            project_root=str(root),
        )
    setattr(executor, "_immune_system", None)
    return executor


def fixture_tool_port(root: Path) -> ToolExecutorPort:
    """실제 executor를 감싼 포트. 성장 harness는 이 포트만 받는다(도구 계층 결합 없음)."""

    path = Path(root)
    return ToolExecutorPort(
        executor=fixture_executor(path, fixture_registry(path)),
        failure_predicate=result_indicates_failure,
    )
