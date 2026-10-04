from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Callable, cast, override
from unittest.mock import MagicMock, patch

from antigravity_k.engine.self_capability import (
    SelfCapabilityEngine,
    is_self_capability_request,
)
from antigravity_k.engine.skill_loader import SkillLoader
from antigravity_k.engine.slash_commands import SlashCommandRegistry
from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, StateContext
from antigravity_k.tools.base_tool import BaseTool, RiskLevel, ToolCategory
from antigravity_k.tools.tool_registry import ToolRegistry


def _install(registry: ToolRegistry, tool: BaseTool) -> None:
    installer = cast(Callable[[object], ToolRegistry], getattr(registry, "install"))
    _ = installer(tool)


class DummyWriteTool(BaseTool):
    category: ToolCategory = ToolCategory.FILE_IO
    risk_level: RiskLevel = RiskLevel.LOW

    @property
    @override
    def name(self) -> str:
        return "write_file"

    @property
    @override
    def description(self) -> str:
        return "Write a file in the current project"

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    @override
    def execute(self, **_kwargs: object) -> str:
        return "ok"


class DummyDomTool(BaseTool):
    category: ToolCategory = ToolCategory.WEB
    risk_level: RiskLevel = RiskLevel.SAFE

    @property
    @override
    def name(self) -> str:
        return "fetch_dom"

    @property
    @override
    def description(self) -> str:
        return "Inspect browser DOM for QA"

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    @override
    def execute(self, **_kwargs: object) -> str:
        return "ok"


def test_self_capability_request_detection():
    assert is_self_capability_request("너를 소개하고 니가 할 수 있는 일을 알려줘")
    assert is_self_capability_request("what can you do?")
    assert is_self_capability_request("현재 모델이 뭐야?")
    assert is_self_capability_request("등록된 도구 목록을 알려줘")
    assert is_self_capability_request("설정 상태를 보여줘")
    assert is_self_capability_request("어떤 도구를 사용할 수 있어?")
    assert is_self_capability_request("어떤 모델을 사용하고 있어?")
    assert not is_self_capability_request("GCD 함수를 작성해줘")
    assert not is_self_capability_request("외부 API 기능을 사용해 상태를 정리해줘")
    assert not is_self_capability_request("이 모델의 기능 요구사항을 구현해줘")
    assert not is_self_capability_request("어떤 모델을 사용해 구현할지 비교해줘")
    assert not is_self_capability_request("/capabilities DOM browser testing")
    assert not is_self_capability_request("/goal DOM 기능을 테스트해줘")


def _provider_stream_node(ctx: StateContext, orch: MagicMock) -> Generator[str, None, None]:
    response = "provider dispatched response"
    ctx.agent_output = response
    yield from orch.manager.stream_generate(prompt=ctx.messages[-1]["content"], target=ctx.target_model)


def test_generic_feature_task_reaches_provider_in_stream_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from antigravity_k.engine.engine_profile import EngineProfile
    from antigravity_k.engine.orchestrator.stream import run_stream

    graph = AgentStateGraph()
    graph.set_entry(AgentState.AGENT_EXECUTE)
    graph.add_node(AgentState.AGENT_EXECUTE, _provider_stream_node)
    provider = MagicMock()
    provider.stream_generate.return_value = iter(["provider dispatched response"])
    orch = MagicMock()
    orch.manager = provider
    orch.task_execution_context = None
    orch._state_graph = graph
    orch._latest_user_text.side_effect = lambda messages: messages[-1]["content"]
    orch.ctx.memory_manager.authoritative_project_fact_for_query.return_value = None
    orch.ctx.memory_manager.prefetch_all.return_value = ""
    orch.trajectory_compressor_for.return_value = None
    orch.context_compressor_for.return_value = None

    with patch(
        "antigravity_k.engine.preflight_validator.PreflightValidator.validate",
        return_value=(True, "", EngineProfile.FAST_PROTOTYPER),
    ):
        chunks = list(
            run_stream(
                orch,
                [{"role": "user", "content": "외부 API 기능을 사용해 상태를 정리해줘"}],
                "test-model",
            )
        )

    assert chunks[-1] == "provider dispatched response"
    provider.stream_generate.assert_called_once_with(
        prompt="외부 API 기능을 사용해 상태를 정리해줘", target="test-model"
    )
    orch._render_self_capability_response.assert_not_called()


def test_self_capability_report_uses_runtime_tools_and_skills(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agent" / "skills" / "browser-qa"
    skill_dir.mkdir(parents=True)
    _ = (skill_dir / "SKILL.md").write_text(
        """---
name: Browser QA
description: DOM browser testing
risk_level: safe
trust_level: local
---
Inspect DOM and console state.
""",
        encoding="utf-8",
    )
    registry = ToolRegistry(project_root=str(tmp_path))
    _install(registry, DummyWriteTool())
    _install(registry, DummyDomTool())
    loader = SkillLoader(project_root=str(tmp_path), include_global=False)

    snapshot = SelfCapabilityEngine().build(
        tool_registry=registry,
        skill_loader=loader,
        project_root=str(tmp_path),
        slash_commands=["self", "capabilities"],
    )
    rendered = SelfCapabilityEngine().render_markdown(snapshot)

    assert "등록 도구: `2`개" in rendered
    assert "등록 Skills: `1`개" in rendered
    assert "`fetch_dom`" in rendered
    assert "`write_file`" in rendered
    assert "`browser-qa`" in rendered
    assert "WiFi" not in rendered
    assert "볼륨" not in rendered


def test_self_slash_command_reports_runtime_capabilities(tmp_path: Path) -> None:
    registry = ToolRegistry(project_root=str(tmp_path))
    _install(registry, DummyDomTool())
    loader = SkillLoader(project_root=str(tmp_path), include_global=False)
    slash = SlashCommandRegistry(tool_registry=registry, skill_loader=loader)

    result = slash.execute("/self")

    assert "Ssak-Ai Self Capability Report" in result
    assert "등록 도구: `1`개" in result
    assert "`fetch_dom`" in result
    assert "/capabilities <목표>" in result
