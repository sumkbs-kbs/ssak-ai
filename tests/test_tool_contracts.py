from __future__ import annotations

from pathlib import Path
from typing import override

from antigravity_k.tools.base_tool import BaseTool, RiskLevel, ToolCategory
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry


class _WriteTool(BaseTool):
    category: ToolCategory = ToolCategory.FILE_IO
    risk_level: RiskLevel = RiskLevel.LOW

    @property
    @override
    def name(self) -> str:
        return "write_file"

    @property
    @override
    def description(self) -> str:
        return "Write a project file."

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    @override
    def execute(self, **kwargs: object) -> str:
        return "written"


class _ShellTool(BaseTool):
    category: ToolCategory = ToolCategory.CODE_EXEC
    risk_level: RiskLevel = RiskLevel.HIGH

    @property
    @override
    def name(self) -> str:
        return "run_bash_command"

    @property
    @override
    def description(self) -> str:
        return "Run a shell command."

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    executions: int = 0

    @override
    def execute(self, **kwargs: object) -> str:
        type(self).executions += 1
        return "ran"


def test_registry_authorize_returns_spec_and_allow_decision_for_project_write(tmp_path: Path) -> None:
    registry = ToolRegistry(project_root=str(tmp_path))
    _ = registry.install(_WriteTool())

    decision = registry.authorize("write_file", {"path": str(tmp_path / "note.txt")})

    assert decision.permission is Permission.ALLOW
    assert decision.spec.name == "write_file"
    assert decision.spec.risk_level == "low"


def test_registry_authorize_returns_cognitive_protection_denial_for_dangerous_shell_command(
    tmp_path: Path,
) -> None:
    # 의도된 순서(permission_gate.decide 주석·docs/ssak-ai-core/evidence/T01b_protection.md):
    # cognitive protection 이 일반 shell 위험 명령 단계보다 먼저 판정한다. 실제 거부 주체를 그대로 검사한다.
    registry = ToolRegistry(project_root=str(tmp_path))
    _ShellTool.executions = 0
    _ = registry.install(_ShellTool())

    decision = registry.authorize("run_bash_command", {"command": "rm -rf /"})

    assert decision.permission is Permission.DENY
    assert decision.source == "cognitive_protection"
    assert "PATH_ESCAPE" in decision.reason.upper()
    assert _ShellTool.executions == 0  # 판정은 데이터로만 — 명령은 실행되지 않는다


def test_permission_gate_own_dangerous_command_policy_still_denies(tmp_path: Path) -> None:
    # cognitive protection 이 막지 않는(경로 없는) 위험 명령은 permission_gate 자체 정책이 거부한다.
    registry = ToolRegistry(project_root=str(tmp_path))
    _ShellTool.executions = 0
    _ = registry.install(_ShellTool())

    decision = registry.authorize("run_bash_command", {"command": "shutdown -h now"})

    assert decision.permission is Permission.DENY
    assert decision.source == "permission_gate"
    assert decision.reason == "The command matches a blocked dangerous-command policy."
    assert _ShellTool.executions == 0


def test_registry_authorize_tool_evaluates_unregistered_descriptor(tmp_path: Path) -> None:
    registry = ToolRegistry(project_root=str(tmp_path))
    tool = _WriteTool()

    decision = registry.authorize_tool(tool, {"path": str(tmp_path / "note.txt")})

    assert decision.permission is Permission.ALLOW
    assert decision.spec.name == "write_file"
    assert registry.get("write_file") is None
