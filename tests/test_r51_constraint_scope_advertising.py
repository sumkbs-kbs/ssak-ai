"""Only immutable constraints from the current trusted turn affect tool descriptors."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.engine.execution_mode import ExecutionMode
from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
from antigravity_k.engine.turn_tool_constraints import TurnToolConstraints, bind_turn_tool_constraints, current_turn_tool_constraints
from antigravity_k.tools.ast_grep_tool import ASTGrepTool
from antigravity_k.tools.binary_tools import HexDumpTool
from antigravity_k.tools.file_tools import GrepSearchTool
from antigravity_k.tools.git_tools import GitDiffTool
from antigravity_k.tools.hashline_tools import ReadHashFileTool
from antigravity_k.tools.system_tools import ReadFileTool
from antigravity_k.tools.tool_registry import ToolRegistry

READERS = {"read_file", "read_hash_file", "hex_dump", "grep_search", "ast_grep", "git_diff"}


def prompt_orchestrator(root: Path) -> OrchestratorAgent:
    tools = ToolRegistry(project_root=str(root))
    for tool in (ReadFileTool(), ReadHashFileTool(), HexDumpTool(), GrepSearchTool(), ASTGrepTool(), GitDiffTool()):
        tools.install(tool)
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.tool_registry = tools
    orch.project_root = str(root)
    orch.manager = SimpleNamespace()
    orch.mode_manager = SimpleNamespace(current_mode=ExecutionMode.BUILD)
    orch.ctx = SimpleNamespace(prompt_builder=SimpleNamespace(response_contract=lambda: ""), skill_loader=SimpleNamespace(loaded_skills={}), slash_commands=SimpleNamespace(_commands={}))
    return orch


@pytest.mark.parametrize(("request_text", "expected"), [("파일을 읽지 마세요.", set()), ("read_file을 호출하지 마세요.", READERS - {"read_file"}), ("현재 파일 내용을 확인해줘.", READERS)])
def test_structural_xml_descriptors_follow_current_trusted_scope(tmp_path: Path, request_text: str, expected: set[str]) -> None:
    # Given: actual registered reader schemas and one parsed original-user constraint.
    orch = prompt_orchestrator(tmp_path)
    constraints = TurnToolConstraints.from_request(request_text)
    # When: only prompt construction is bound to that immutable current turn.
    with bind_turn_tool_constraints(constraints):
        rendered = orch._build_tool_prompt("simple_chat")
    # Then: named versus global bans select different advertised tool sets.
    names = set(re.findall(r"^- \*\*([a-z_]+)\*\*:", rendered, re.MULTILINE))
    assert names == expected


def test_scope_reset_prevents_previous_subject_constraints_from_leaking_after_error(tmp_path: Path) -> None:
    # Given: an earlier synthetic subject has a global prohibition during prompt work.
    orch = prompt_orchestrator(tmp_path)
    with pytest.raises(RuntimeError):
        with bind_turn_tool_constraints(TurnToolConstraints.from_request("파일을 읽지 마세요.")):
            assert current_turn_tool_constraints().denial("hex_dump") is not None
            raise RuntimeError("synthetic prompt failure")
    # When: a later subject starts neutral prompt construction on the same orchestrator.
    with bind_turn_tool_constraints(TurnToolConstraints.from_request("현재 자료를 확인해줘.")):
        rendered = orch._build_tool_prompt("simple_chat")
    # Then: neither previous request state nor a shared mutable task goal controls it.
    assert current_turn_tool_constraints().denial("hex_dump") is None
    assert set(re.findall(r"^- \*\*([a-z_]+)\*\*:", rendered, re.MULTILINE)) == READERS


def test_nested_scope_restores_only_its_own_trusted_request() -> None:
    # Given: an outer current request and a narrower nested prompt operation.
    outer = TurnToolConstraints.from_request("파일을 읽지 마세요.")
    inner = TurnToolConstraints.from_request("read_file을 호출하지 마세요.")
    # When: nested immutable scopes are entered and exited.
    with bind_turn_tool_constraints(outer):
        with bind_turn_tool_constraints(inner):
            assert current_turn_tool_constraints().denial("hex_dump") is None
        # Then: the outer prohibition returns, and is finally removed at its boundary.
        assert current_turn_tool_constraints().denial("hex_dump") is not None
    assert current_turn_tool_constraints().denial("hex_dump") is None
