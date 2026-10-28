"""Model-visible tool structures must obey the same request policy as execution."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.engine.execution_mode import ExecutionMode
from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.system_tools import ReadFileTool
from antigravity_k.tools.file_tools import WriteFileTool
from antigravity_k.tools.tool_registry import ToolRegistry
from tests.test_tool_loop import mock_orch


def registry(root: Path) -> ToolRegistry:
    tools = ToolRegistry(project_root=str(root))
    tools.install(ReadFileTool())
    tools.install(WriteFileTool())
    return tools


@pytest.mark.parametrize("safe_only", [False, True])
def test_native_tool_schemas_match_actual_readonly_policy(mock_orch, tmp_path: Path, safe_only: bool) -> None:
    # Given: real read/write tools and an allowed native-capable provider surface.
    mock_orch.tool_registry = registry(tmp_path)
    mock_orch.config = {"tool_loop": {"native_function_calling": True}}
    mock_orch.manager._registry.get_model.return_value = SimpleNamespace(provider="ollama")
    mock_orch.manager.provider_capability.return_value = {"native_tool_calling": "supported"}
    token = set_tool_policy(ToolPolicy(safe_only=safe_only))
    # When: the production loop constructs native schemas.
    try:
        kwargs = ToolLoopEngine(mock_orch)._native_tools_kwargs("synthetic-model")
    finally:
        reset_tool_policy(token)
    # Then: writing is exposed only when that request can execute it.
    names = {schema["function"]["name"] for schema in kwargs.get("tools", [])}
    assert names == ({"read_file"} if safe_only else {"read_file", "write_file"})


@pytest.mark.parametrize("safe_only", [False, True])
def test_xml_tool_descriptors_match_actual_readonly_policy(tmp_path: Path, safe_only: bool) -> None:
    # Given: the real prompt builder method and registry, without a model process.
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.tool_registry = registry(tmp_path)
    orch.project_root = str(tmp_path)
    orch.manager = SimpleNamespace()
    orch.mode_manager = SimpleNamespace(current_mode=ExecutionMode.BUILD)
    orch.ctx = SimpleNamespace(prompt_builder=SimpleNamespace(response_contract=lambda: ""), skill_loader=SimpleNamespace(loaded_skills={}), slash_commands=SimpleNamespace(_commands={}))
    token = set_tool_policy(ToolPolicy(safe_only=safe_only))
    # When: descriptors used as the model's tool protocol are rendered.
    try:
        rendered = orch._build_tool_prompt("simple_chat")
    finally:
        reset_tool_policy(token)
    # Then: tool names inside the structural descriptor list obey the policy.
    names = set(re.findall(r"^- \*\*([a-z_]+)\*\*:", rendered, re.MULTILINE))
    assert names == ({"read_file"} if safe_only else {"read_file", "write_file"})


def test_request_toggle_denial_applies_to_native_schemas(mock_orch, tmp_path: Path) -> None:
    # Given: a safe read tool is explicitly disabled for this request.
    mock_orch.tool_registry = registry(tmp_path)
    mock_orch.config = {"tool_loop": {"native_function_calling": True}}
    mock_orch.manager._registry.get_model.return_value = SimpleNamespace(provider="ollama")
    mock_orch.manager.provider_capability.return_value = {"native_tool_calling": "supported"}
    token = set_tool_policy(ToolPolicy(safe_only=True, denied_tools=frozenset({"read_file"})))
    # When: native schemas are collected under the same policy.
    try:
        kwargs = ToolLoopEngine(mock_orch)._native_tools_kwargs("synthetic-model")
    finally:
        reset_tool_policy(token)
    # Then: an empty allowed set stays empty rather than restoring all tools.
    assert kwargs == {}
