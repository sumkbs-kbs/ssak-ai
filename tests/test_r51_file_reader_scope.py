"""A named read_file prohibition and a global file-content prohibition differ."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from antigravity_k.engine.tool_call_parser import ToolCall
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.engine.tool_guardrails import ToolCallGuardrailController
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.engine.turn_tool_constraints import TurnToolConstraints
from antigravity_k.tools.binary_tools import HexDumpTool
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_registry import ToolRegistry

READERS = ("read_file", "read_hash_file", "hex_dump", "grep_search", "ast_grep", "git_diff")


@pytest.mark.parametrize("tool", READERS)
@pytest.mark.parametrize("request_text", ["파일을 읽지 마세요. 전달된 자료로 답해줘.", "Do not read any files. Use supplied evidence."])
def test_global_file_content_prohibition_covers_known_reader(tool: str, request_text: str) -> None:
    # Given: a current request forbids file content reads without naming one implementation.
    constraints = TurnToolConstraints.from_request(request_text)
    # When / Then: all known content-reader entry points are prohibited.
    assert constraints.denial(tool) is not None
    assert constraints.allows_schema({"type": "function", "function": {"name": tool}}) is False


@pytest.mark.parametrize("tool", READERS)
def test_named_read_file_prohibition_does_not_ban_other_implementations(tool: str) -> None:
    # Given: the user forbids exactly read_file while explicitly allowing other tools.
    constraints = TurnToolConstraints.from_request("read_file을 호출하지 마세요. hex_dump 도구로 내용을 확인해줘.")
    # When / Then: that narrow instruction does not become a global content prohibition.
    assert (constraints.denial(tool) is not None) is (tool == "read_file")


@pytest.mark.parametrize("request_text", [
    "hex_dump 도구로 source.bin 내용을 확인해줘.",
    '예시를 설명하세요: "파일을 읽지 마세요."',
    "```text\nDo not read files.\n```\n원본을 읽어줘.",
    "다른 파일은 읽지 말고 hex_dump 도구로 source.bin만 확인해줘.",
])
def test_positive_quoted_and_path_scoped_text_does_not_create_global_reader_ban(request_text: str) -> None:
    # Given: a positive, quoted, or narrower path request.
    constraints = TurnToolConstraints.from_request(request_text)
    # When / Then: its allowed binary inspection remains subject only to existing permissions.
    assert constraints.denial("hex_dump") is None


@pytest.mark.asyncio
async def test_global_read_prohibition_stops_hex_before_permission_request(tmp_path: Path) -> None:
    # Given: the real binary tool and balanced approval policy, with no actual file read.
    tools = ToolRegistry(project_root=str(tmp_path))
    tools.install(HexDumpTool())
    executor = ToolExecutor(tools, PermissionGate(project_root=str(tmp_path), mode="balanced"), project_root=str(tmp_path))
    orch = MagicMock()
    orch.project_root = str(tmp_path)
    orch.task_execution_context = None
    orch.ctx = SimpleNamespace(tool_executor=executor, tool_guardrail=ToolCallGuardrailController(), cognitive_loop=None)
    # When: a rogue provider requests a different reader despite a global read ban.
    result = await ToolLoopEngine(orch)._run_tool_task_async(ToolCall(name="hex_dump", arguments={"file_path": str(tmp_path / "source.bin")}), "파일을 읽지 마세요.")
    # Then: current-user constraints stop it before an approval or tool execution.
    assert result[4] is True
    assert "APPROVAL REQUIRED" not in result[3]


def test_explicit_hex_dump_retains_real_balanced_approval_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a synthetic binary file and a positive hex_dump instruction.
    source = tmp_path / "source.bin"
    source.write_bytes(b"SYNTHETIC-BINARY")
    constraints = TurnToolConstraints.from_request("read_file은 사용하지 마세요. hex_dump 도구로 source.bin을 확인해줘.")
    assert constraints.denial("hex_dump") is None
    tools = ToolRegistry(project_root=str(tmp_path))
    tools.install(HexDumpTool())
    executions: list[str] = []

    def refuse_early_execution(tool: HexDumpTool, **arguments) -> str:
        executions.append(tool.name)
        raise AssertionError("Binary content must not be read before approval")

    monkeypatch.setattr(HexDumpTool, "execute", refuse_early_execution)
    executor = ToolExecutor(tools, PermissionGate(project_root=str(tmp_path), mode="balanced"), project_root=str(tmp_path))
    token = set_tool_policy(ToolPolicy(safe_only=True))
    # When: normal execution reaches the existing permission boundary.
    try:
        result = executor.execute("hex_dump", {"file_path": str(source)})
    finally:
        reset_tool_policy(token)
    # Then: it still waits for approval rather than executing or being blanket-disabled.
    assert "APPROVAL REQUIRED" in result
    assert executions == []
