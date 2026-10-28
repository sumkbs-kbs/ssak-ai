from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.system_tools import NaturalLanguageBashTool, RunBashCommandTool
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry


@pytest.fixture(autouse=True)
def _r39_explicit_autopilot():
    """r39: PermissionGate() without a mode no longer implies auto-pilot (default is balanced).
    This module's assertions were written for auto-pilot, so they now run under the EXPLICIT opt-in."""
    from antigravity_k.engine.access_mode import ExecutionPolicy, set_execution_policy

    set_execution_policy(ExecutionPolicy.AUTO_PILOT)
    yield
    set_execution_policy(None)


def _approved_output(_command: str, *, cwd: str | None = None) -> str:
    # FR-02/RP-02: env 인자는 제거됐고 sandbox는 항상 적용되거나 거부된다.
    _ = cwd
    return "approved-output"


def _execution_permit(tool: RunBashCommandTool) -> object:
    return cast(object, getattr(tool, "_execution_permit"))


def test_run_bash_tool_cannot_execute_directly():
    tool = RunBashCommandTool()

    result = tool.execute(command="echo should-not-run")

    assert result.startswith("[APPROVAL REQUIRED]")


def test_tool_registry_injects_execution_permit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tool = RunBashCommandTool()
    monkeypatch.setattr(tool, "_run_with_sandbox", _approved_output)
    registry = ToolRegistry(project_root=str(tmp_path))
    install = cast(Callable[[object], ToolRegistry], getattr(registry, "install"))
    _ = install(tool)

    permission, result = registry.execute_with_permission(
        "run_bash_command",
        {"command": "echo approved"},
        objective="run a local verification command",
    )

    assert permission is Permission.ALLOW
    assert result == "approved-output"


def test_permission_gate_rejects_sibling_prefix_and_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    sibling = tmp_path / "project-sibling"
    sibling.mkdir()
    outside = tmp_path / "outside.txt"
    _ = outside.write_text("secret", encoding="utf-8")
    link = project_root / "linked.txt"
    link.symlink_to(outside)
    gate = PermissionGate(project_root=str(project_root), mode="auto-pilot")

    assert gate.check("write_file", {"path": str(sibling / "file.txt")}, risk_level="low") is Permission.DENY
    assert gate.check("write_file", {"path": str(link)}, risk_level="low") is Permission.DENY


def test_failed_command_surfaces_exit_code_so_model_can_detect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a command that exits non-zero with a specific message on stderr.
    # FR-02/RP-02: raw subprocess fallback no longer exists; the sandboxed path
    # itself must surface the exit code.
    tool = RunBashCommandTool()
    monkeypatch.setattr(tool, "_execution_permit", object(), raising=False)

    # When: the tool runs a failing command through the sandbox boundary.
    result = tool.execute(
        command="python3 -c 'import sys; sys.stderr.write(\"boom\"); sys.exit(3)'",
        _execution_permit=_execution_permit(tool),
    )

    # Then: the exit code is surfaced so the model can definitively detect failure and
    # trigger a correction — inferring failure from stderr content is unreliable.
    assert "exit_code=3" in result
    assert "boom" in result


def test_successful_command_does_not_surface_exit_code_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a command that succeeds (exit 0).
    tool = RunBashCommandTool()
    monkeypatch.setattr(tool, "_execution_permit", object(), raising=False)

    # When: the tool runs a succeeding command.
    result = tool.execute(command="python3 -c 'print(42)'", _execution_permit=_execution_permit(tool))

    # Then: success output is returned without a failure marker cluttering the context.
    assert "42" in result
    assert "exit_code" not in result


def test_sandbox_disabled_refuses_instead_of_raw_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-02/RP-02: sandbox가 비활성화되면 raw host 실행 대신 거부한다.
    from antigravity_k.config import config as app_config

    tool = RunBashCommandTool()
    monkeypatch.setattr(app_config.security, "sandbox_enabled", False)
    monkeypatch.setattr(tool, "_execution_permit", object(), raising=False)

    result = tool.execute(command="echo must-not-run", _execution_permit=_execution_permit(tool))

    assert result.startswith("Error: run_bash_command requires an enabled OS sandbox")
    assert "raw host execution is disabled" in result


def test_natural_language_bash_routes_generated_command_through_sandbox() -> None:
    tool = NaturalLanguageBashTool()
    with (
        patch("antigravity_k.engine.model_manager.ModelManager") as manager_factory,
        patch("antigravity_k.engine.model_registry.ModelRegistry"),
        patch("antigravity_k.engine.orchestrator.OrchestratorAgent") as orchestrator_factory,
        patch.object(RunBashCommandTool, "_run_with_sandbox", return_value="safe [sandboxed]") as sandbox,
        patch("antigravity_k.tools.system_tools.subprocess.run") as raw_run,
    ):
        manager_factory.return_value.get_target_for_role.return_value = object()
        orchestrator_factory.return_value.run_sync.return_value = "echo safe"
        result = tool.execute(intent="print safe")

    sandbox.assert_called_once_with("echo safe")
    raw_run.assert_not_called()
    assert result.endswith("safe [sandboxed]")
