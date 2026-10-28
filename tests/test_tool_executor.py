"""Tests for ToolExecutor — the core tool dispatch and permission engine.

Covers the main execution paths:
- Unknown tool handling
- Readonly auto-approval (bypasses gates)
- PlanGuard blocking (plan mode denies write tools)
- GatePipeline deny / pause (approval required)
- Schema validation (missing required args)
- Preflight directory auto-creation for write tools
- Permission DENY / PROMPT from execute_with_permission
- Tool call history recording and capping
- Consecutive error tracking and recovery trigger
- File event broadcasting (FileOpened / FileModified)
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.tools.mcp_tool_result import MCPToolOutcome
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _registry_tools(registry: MagicMock) -> dict[str, MagicMock]:
    return cast(dict[str, MagicMock], getattr(registry, "_tools"))


def _lookup_tool(registry: MagicMock, name: str) -> MagicMock | None:
    return _registry_tools(registry).get(name)


def _contains_tool(_registry: object, name: str) -> bool:
    return name in _registry_tools(cast(MagicMock, _registry))


def _make_tool(
    name: str = "dummy",
    *,
    required: list[str] | None = None,
    schema: dict[str, object] | None = None,
) -> MagicMock:
    """Create a mock tool object with a parameters_schema."""
    tool = MagicMock()
    tool.name = name
    tool.parameters_schema = schema or {"required": required or []}
    return tool


@pytest.fixture
def tool_registry() -> MagicMock:
    """A minimal ToolRegistry with one registered 'dummy' tool and readonly tools."""
    reg = MagicMock(spec=ToolRegistry)
    reg._tools = {}

    # Register a dummy tool
    dummy = _make_tool("dummy", required=["x"])
    _registry_tools(reg)["dummy"] = dummy
    reg.get = MagicMock(side_effect=partial(_lookup_tool, reg))
    reg.get_tool = MagicMock(side_effect=partial(_lookup_tool, reg))
    reg.__contains__ = _contains_tool

    def execute_with_permission(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.ALLOW, "ok"

    reg.execute_with_permission = execute_with_permission
    return reg


@pytest.fixture
def permission_gate() -> MagicMock:
    return MagicMock(spec=PermissionGate)


@pytest.fixture
def executor(tool_registry: MagicMock, permission_gate: MagicMock, tmp_path: Path) -> ToolExecutor:
    """Create a ToolExecutor with mocked ImmuneSystem (disabled)."""
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        ex = ToolExecutor(
            tool_registry=tool_registry,
            permission_gate=permission_gate,
            project_root=str(tmp_path),
        )
    # Disable immune system for deterministic tests.
    setattr(ex, "_immune_system", None)
    return ex


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


def test_execute_unknown_tool_returns_error(executor: ToolExecutor):
    """Calling an unregistered tool must return a structured error."""
    result = executor.execute("nonexistent", {})
    assert "Unknown tool" in result
    assert "nonexistent" in result
    # 스키마 실수는 롤백 임계 카운터에 가산되지 않는다 (과잉 볼트 롤백 방지)
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def test_readonly_tool_uses_permission_boundary(executor: ToolExecutor, tool_registry: MagicMock):
    readonly_tool = MagicMock()
    readonly_tool.parameters_schema = {"required": []}
    readonly_tool.return_value = "file content"
    _registry_tools(tool_registry)["read_file"] = readonly_tool
    tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))

    called: list[str] = []

    def execute_with_permission(name: str, args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        called.append(name)
        return Permission.ALLOW, readonly_tool(**args)

    tool_registry.execute_with_permission = execute_with_permission

    result = executor.execute("read_file", {"file_path": "/tmp/test.txt"})
    assert result == "file content"
    assert called == ["read_file"]


def test_readonly_protected_path_is_denied_by_permission_gate(tmp_path: Path):
    from antigravity_k.engine.tool_executor import ToolExecutor
    from antigravity_k.tools.system_tools import ReadFileTool

    registry = ToolRegistry(project_root=str(tmp_path))
    install = cast(Callable[..., ToolRegistry], getattr(registry, "install"))
    _ = install(ReadFileTool())
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        executor = ToolExecutor(
            tool_registry=registry,
            permission_gate=registry.permission_gate,
            project_root=str(tmp_path),
        )

    result = executor.execute("read_file", {"file_path": "/etc/passwd"})

    assert "[DENIED]" in result


def test_approved_execution_rechecks_permission_boundary(tmp_path: Path):
    from antigravity_k.tools.system_tools import ReadFileTool

    target = tmp_path / "protected-by-override.txt"
    _ = target.write_text("must not be read", encoding="utf-8")
    registry = ToolRegistry(project_root=str(tmp_path))
    install = cast(Callable[..., ToolRegistry], getattr(registry, "install"))
    _ = install(ReadFileTool())
    registry.permission_gate.set_override("read_file", Permission.DENY)

    result = registry.execute_approved("read_file", {"file_path": str(target)})

    assert "[DENIED]" in result


def test_readonly_tool_records_history(executor: ToolExecutor, tool_registry: MagicMock):
    """Readonly tool execution must be recorded in tool_call_history."""
    readonly_tool = MagicMock(return_value="content")
    readonly_tool.parameters_schema = {"required": []}
    _registry_tools(tool_registry)["read_file"] = readonly_tool
    tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))

    _ = executor.execute("read_file", {"file_path": "/tmp/x"})
    assert len(executor.tool_call_history) == 1
    assert executor.tool_call_history[0]["name"] == "read_file"
    assert executor.tool_call_history[0]["success"] is True


# ---------------------------------------------------------------------------
# PlanGuard blocking
# ---------------------------------------------------------------------------


def test_plan_guard_blocks_tool(executor: ToolExecutor, tool_registry: MagicMock):
    """When PlanGuard denies execution, a [BLOCKED] error is returned."""
    # Register write_file so it passes the 'name not in tool_registry' check.
    write_tool = _make_tool("write_file", required=["file_path"])
    _registry_tools(tool_registry)["write_file"] = write_tool

    guard = MagicMock()
    decision = MagicMock()
    decision.allows_execution = False
    decision.message = "Write tools not allowed in PLAN mode"
    setattr(guard, "evaluate_tool_call", MagicMock(return_value=decision))
    executor.plan_guard = guard

    result = executor.execute("write_file", {"file_path": "x"})
    assert "[BLOCKED]" in result
    assert "PLAN mode" in result
    # 정책 차단은 롤백 임계 카운터에 가산되지 않는다
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0


def test_plan_guard_allows_tool(executor: ToolExecutor):
    """When PlanGuard allows, execution proceeds normally."""
    guard = MagicMock()
    decision = MagicMock()
    decision.allows_execution = True
    setattr(guard, "evaluate_tool_call", MagicMock(return_value=decision))
    executor.plan_guard = guard

    # The dummy tool is not readonly, so it goes through the full path.
    result = executor.execute("dummy", {"x": 1})
    assert result == "ok"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_missing_required_args_returns_error(executor: ToolExecutor):
    """Missing required arguments must produce a structured error."""
    result = executor.execute("dummy", {})
    assert "Missing required arguments" in result
    assert "x" in result
    # 스키마 실수는 롤백 임계 카운터에 가산되지 않는다
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0


# ---------------------------------------------------------------------------
# Preflight directory creation
# ---------------------------------------------------------------------------


def test_preflight_validation_has_no_write_side_effect(
    executor: ToolExecutor, tool_registry: MagicMock, tmp_path: Path
):
    """검증 단계는 디렉터리를 생성하지 않는다 — 생성은 실제 쓰기 도구의 책임.

    (오타 경로가 조용히 잘못된 디렉터리 트리를 만드는 부수효과 방지)
    """
    # no-op 도구로 등록 (실제 쓰기는 일어나지 않음)
    write_tool = _make_tool("write_file", required=[])
    _registry_tools(tool_registry)["write_file"] = write_tool
    tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))

    target = str(tmp_path / "newdir" / "subdir" / "file.txt")
    result = executor.execute("write_file", {"file_path": target})
    assert result == "ok"
    # 검증만 거친 시점에는 디렉터리가 생성되지 않는다.
    assert not os.path.isdir(os.path.dirname(target))


# ---------------------------------------------------------------------------
# Permission DENY / PROMPT
# ---------------------------------------------------------------------------


def test_permission_deny_returns_blocked(executor: ToolExecutor, tool_registry: MagicMock):
    """When execute_with_permission returns DENY, a [DENIED] error is returned."""

    def deny_execution(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.DENY, "blocked"

    tool_registry.execute_with_permission = deny_execution
    result = executor.execute("dummy", {"x": 1})
    assert "[DENIED]" in result
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0  # 정책 차단은 카운터 제외
    assert executor.tool_call_history[-1]["permission"] == "deny"


def test_permission_prompt_returns_approval_required(executor: ToolExecutor, tool_registry: MagicMock):
    """When execute_with_permission returns PROMPT, an [APPROVAL REQUIRED] message is returned."""

    def prompt_execution(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.PROMPT, "needs approval"

    tool_registry.execute_with_permission = prompt_execution
    result = executor.execute("dummy", {"x": 1})
    assert "[APPROVAL REQUIRED]" in result
    assert executor.tool_call_history[-1]["permission"] == "prompt"


# ---------------------------------------------------------------------------
# Error tracking and recovery
# ---------------------------------------------------------------------------


def test_consecutive_error_reset_on_success(executor: ToolExecutor):
    """A successful tool call resets the consecutive error counter."""
    setattr(executor, "_consecutive_errors", 2)
    _ = executor.execute("dummy", {"x": 1})
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0


def test_three_consecutive_errors_trigger_recovery(executor: ToolExecutor, tool_registry: MagicMock):
    """Three consecutive errors trigger the recovery path (_trigger_recovery)."""

    # Make execute_with_permission return errors.
    def failing_execution(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.ALLOW, "Error: something failed"

    tool_registry.execute_with_permission = failing_execution
    # Mock _trigger_recovery to verify it's called.
    recovery = MagicMock(return_value="recovery result")
    setattr(executor, "_trigger_recovery", recovery)

    _ = executor.execute("dummy", {"x": 1})  # error 1
    _ = executor.execute("dummy", {"x": 1})  # error 2
    result = executor.execute("dummy", {"x": 1})  # error 3 → trigger

    assert result == "recovery result"
    recovery.assert_called_once()


# ---------------------------------------------------------------------------
# History capping
# ---------------------------------------------------------------------------


def test_tool_call_history_capped_at_20(executor: ToolExecutor, tool_registry: MagicMock):
    """The history list must not exceed 20 entries."""
    readonly_tool = MagicMock(return_value="ok")
    readonly_tool.parameters_schema = {"required": []}
    _registry_tools(tool_registry)["read_file"] = readonly_tool
    tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))

    for i in range(25):
        _ = executor.execute("read_file", {"file_path": f"/tmp/{i}"})

    assert len(executor.tool_call_history) == 20
    # The oldest entries should have been dropped; the last should be the most recent.
    assert executor.tool_call_history[-1]["arguments"]["file_path"] == "/tmp/24"


# ---------------------------------------------------------------------------
# Helper methods (extracted during refactor)
# ---------------------------------------------------------------------------


def test_validate_and_preflight_returns_none_on_success(executor: ToolExecutor):
    """_validate_and_preflight returns None when validation passes."""
    validate = cast(
        Callable[[str, dict[str, object]], str | None],
        getattr(executor, "_validate_and_preflight"),
    )
    result = validate("dummy", {"x": 1})
    assert result is None


def test_validate_and_preflight_missing_args(executor: ToolExecutor):
    """_validate_and_preflight returns an error string for missing args."""
    validate = cast(
        Callable[[str, dict[str, object]], str | None],
        getattr(executor, "_validate_and_preflight"),
    )
    result = validate("dummy", {})
    assert result is not None
    assert "Missing required arguments" in result


def test_record_tool_call_adds_entry(executor: ToolExecutor):
    """_record_tool_call appends a single history entry."""
    initial = len(executor.tool_call_history)
    record = cast(
        Callable[[str, dict[str, object], str], None],
        getattr(executor, "_record_tool_call"),
    )
    record("test_tool", {"k": "v"}, "result")
    assert len(executor.tool_call_history) == initial + 1
    entry = executor.tool_call_history[-1]
    assert entry["name"] == "test_tool"
    assert entry["success"] is True


def test_record_tool_call_error_result_marked_unsuccessful(executor: ToolExecutor):
    """An error result string must be marked as unsuccessful in history."""
    record = cast(
        Callable[[str, dict[str, object], str], None],
        getattr(executor, "_record_tool_call"),
    )
    record("bad_tool", {}, "Error: failed")
    assert executor.tool_call_history[-1]["success"] is False


# ---------------------------------------------------------------------------
# File event broadcasting
# ---------------------------------------------------------------------------


def test_broadcast_file_event_skips_non_file_tools(executor: ToolExecutor):
    """_broadcast_file_event does nothing for non-file tools."""
    # Should not raise even if the tool is not a file tool.
    broadcast = cast(
        Callable[[str, dict[str, object]], None],
        getattr(executor, "_broadcast_file_event"),
    )
    _ = broadcast("web_search", {"query": "test"})


def test_broadcast_file_event_publishes_for_read_file(executor: ToolExecutor, tmp_path: Path):
    """_broadcast_file_event publishes FileOpened for read_file on an existing file."""
    test_file = tmp_path / "test.txt"
    _ = test_file.write_text("hello")

    published: list[tuple[str, dict[str, object]]] = []
    with patch("antigravity_k.engine.event_bus.global_event_bus") as mock_bus:

        def publish(event_type: str, **kwargs: object) -> None:
            published.append((event_type, kwargs))

        mock_bus.publish = publish
        broadcast = cast(
            Callable[[str, dict[str, object]], None],
            getattr(executor, "_broadcast_file_event"),
        )
        _ = broadcast("read_file", {"file_path": str(test_file)})

    assert len(published) == 1
    assert published[0][0] == "FileOpened"
    assert published[0][1]["filepath"] == str(test_file)


def test_broadcast_file_event_publishes_for_write_file(executor: ToolExecutor, tmp_path: Path):
    """_broadcast_file_event publishes FileModified for write_file."""
    test_file = tmp_path / "output.txt"
    _ = test_file.write_text("data")

    published: list[tuple[str, dict[str, object]]] = []
    with patch("antigravity_k.engine.event_bus.global_event_bus") as mock_bus:

        def publish(event_type: str, **kwargs: object) -> None:
            published.append((event_type, kwargs))

        mock_bus.publish = publish
        broadcast = cast(
            Callable[[str, dict[str, object]], None],
            getattr(executor, "_broadcast_file_event"),
        )
        _ = broadcast("write_file", {"file_path": str(test_file)})

    assert published[0][0] == "FileModified"


def test_post_execute_failure_publishes_failure_detected(executor: ToolExecutor, monkeypatch: pytest.MonkeyPatch):
    """실패한 도구 결과는 Dashboard용 FailureDetected 이벤트로 브로드캐스트된다."""
    published: list[tuple[str, dict[str, object]]] = []

    class _FakeBus:
        def publish(self, event_name: str, **kwargs: object) -> None:
            published.append((event_name, kwargs))

    monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())

    executor._post_execute("dummy", {"x": 1}, "Error: boom", permission=Permission.ALLOW)

    assert published, "FailureDetected 이벤트가 발행되어야 한다"
    event_name, kwargs = published[0]
    assert event_name == "FailureDetected"
    assert kwargs["tool"] == "dummy"
    assert "boom" in str(kwargs["error"])
    assert kwargs["message"]


def test_post_execute_success_does_not_publish_failure_detected(
    executor: ToolExecutor, monkeypatch: pytest.MonkeyPatch
):
    """성공한 도구 결과는 FailureDetected를 발행하지 않는다."""
    published: list[tuple[str, dict[str, object]]] = []

    class _FakeBus:
        def publish(self, event_name: str, **kwargs: object) -> None:
            published.append((event_name, kwargs))

    monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())

    executor._post_execute("read_file", {"path": "x"}, "ok", permission=Permission.ALLOW)

    assert all(name != "FailureDetected" for name, _ in published)


def test_broadcast_file_event_skips_nonexistent_file(executor: ToolExecutor):
    """_broadcast_file_event does nothing for a non-existent file path."""
    # Should not raise.
    broadcast = cast(
        Callable[[str, dict[str, object]], None],
        getattr(executor, "_broadcast_file_event"),
    )
    _ = broadcast("read_file", {"file_path": "/nonexistent/path/file.txt"})


def test_explicitly_contracted_tool_still_requires_approval(tmp_path: Path):
    # Given: a task whose checkpoint records write_file as a tool the user explicitly requested.
    from antigravity_k.engine import gate_pipeline
    from antigravity_k.engine.task_state_store import (
        TaskExecutionContext,
        TaskStateStore,
        bind_task_execution_context,
    )

    store = TaskStateStore(str(tmp_path / "tasks.db"))
    _ = store.create_task("task-contract", "write and run", "pending", "2026-08-13T00:00:00+00:00")
    store.save_checkpoint("task-contract", 0, '{"expected_tools": ["write_file"]}', "")

    reg = MagicMock(spec=ToolRegistry)
    reg._tools = {}
    write_tool = _make_tool("write_file", required=["file_path"])
    write_tool.return_value = "wrote"
    _registry_tools(reg)["write_file"] = write_tool
    reg.get = MagicMock(side_effect=partial(_lookup_tool, reg))
    reg.__contains__ = _contains_tool

    def write_execution(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.ALLOW, "wrote"

    reg.execute_with_permission = write_execution

    gate = MagicMock(spec=PermissionGate)
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        ex = ToolExecutor(
            tool_registry=reg,
            permission_gate=gate,
            project_root=str(tmp_path),
            gate_pipeline=cast(Callable[[], object], getattr(gate_pipeline, "create_default_pipeline"))(),
        )
    setattr(ex, "_immune_system", None)

    # When: write_file executes inside a task that explicitly contracted it.
    with bind_task_execution_context(TaskExecutionContext("task-contract", store)):
        result = ex.execute("write_file", {"file_path": str(tmp_path / "out.txt"), "content": "x"})

    # Then (r41 contract change): naming a tool in the prompt is NOT approval. The former
    # behaviour (contracted tool ran without asking) let a prompt bypass ASK_EACH_TIME.
    assert "[APPROVAL REQUIRED]" in str(result)


def test_nonzero_exit_code_result_is_classified_as_failure(executor: ToolExecutor, tool_registry: MagicMock):
    # Given: a tool whose result carries the [exit_code=N] failure marker surfaced by
    # run_bash_command when a command exits non-zero.
    failing_tool = _make_tool("run_bash_command", required=["command"])
    failing_tool.return_value = "[exit_code=2]\nSTDERR:\nboom"
    _registry_tools(tool_registry)["run_bash_command"] = failing_tool
    tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))

    def failing_command_execution(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.ALLOW, "[exit_code=2]\nSTDERR:\nboom"

    tool_registry.execute_with_permission = failing_command_execution

    # When: the executor runs the tool and records the outcome.
    _ = executor.execute("run_bash_command", {"command": "false"})

    # Then: the result is classified as a failure so the consecutive-error counter
    # advances and the recovery loop can trigger — the exit-code marker must not mask it.
    assert executor.tool_call_history[-1]["success"] is False
    assert cast(int, getattr(executor, "_consecutive_errors")) == 1


def test_dangerous_command_is_denied_even_when_run_bash_is_user_contracted(tmp_path: Path):
    # Given: a task that explicitly contracted run_bash_command (auto-approved via the
    # user-contract path), so the ApprovalGate is bypassed.
    from antigravity_k.tools.permission_gate import PermissionGate
    from antigravity_k.tools.tool_contracts import ToolInvocation, ToolSpec

    # When: a destructive command runs inside the contracted task — the permission gate
    # must still deny it regardless of the ApprovalGate pre-approval.
    real_gate = PermissionGate(project_root=str(tmp_path), mode="auto-pilot")
    spec = ToolSpec(name="run_bash_command", risk_level="high", category="code_exec")
    decision = real_gate.decide(ToolInvocation(spec=spec, arguments={"command": "rm -rf /"}))

    # Then: the dangerous-command policy denies it — pre-approval authorizes *which tool*
    # but never *which destructive payload*.
    assert decision.is_denied


class TestApprovalWiring:
    """게이트 일시정지 ↔ ApprovalManager 연동.

    r41: 가짜 관리자 대신 **실제 ApprovalManager**(새 인스턴스)를 쓴다 — r40 증빙 계약
    (find_approved_evidence 검증 / 실행 직전 1회 consume)을 그대로 통과해야 하며, 항상 성공하는
    가짜 증빙은 두지 않는다. 승인은 실제 resolve() 로만 생긴다.
    """

    @staticmethod
    def _executor_with_pipeline(tool_registry, permission_gate, tmp_path):
        from antigravity_k.engine import gate_pipeline
        from antigravity_k.engine.tool_executor import ToolExecutor

        with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
            ex = ToolExecutor(
                tool_registry=tool_registry,
                permission_gate=permission_gate,
                project_root=str(tmp_path),
                gate_pipeline=cast(Callable[[], object], getattr(gate_pipeline, "create_default_pipeline"))(),
            )
        setattr(ex, "_immune_system", None)
        return ex

    @staticmethod
    def _real_manager(monkeypatch):
        from antigravity_k.engine import approval_manager as am

        mgr = am.ApprovalManager()
        monkeypatch.setattr(am, "get_approval_manager", lambda: mgr)
        # tool_executor binds the name at import; both lookups must see the same real manager
        monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: mgr)
        return am, mgr

    @staticmethod
    def _install_write(tool_registry):
        write_tool = _make_tool("write_file", required=[])
        _registry_tools(tool_registry)["write_file"] = write_tool
        tool_registry.get = MagicMock(side_effect=partial(_lookup_tool, tool_registry))
        calls: list[str] = []
        inner = tool_registry.execute_with_permission

        def counting(name: str, args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
            calls.append(name)  # the real side-effect boundary in this harness
            return inner(name, args, objective=objective)

        tool_registry.execute_with_permission = counting
        return calls

    def test_pause_registers_approval_request(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        """게이트 일시정지 시 실제 승인 요청이 등록되고 그 요청 ID가 결과에 포함된다(실행 없음)."""
        _am, mgr = self._real_manager(monkeypatch)
        write_tool = self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)

        result = ex.execute("write_file", {"file_path": str(tmp_path / "a.txt"), "content": "x"})

        pending = mgr.get_pending()
        assert "[APPROVAL REQUIRED]" in result
        assert len(pending) == 1 and pending[0].tool_name == "write_file"
        assert pending[0].request_id in result
        assert pending[0].binding  # bound to target/action/content
        assert write_tool == []

    def test_pause_publishes_approval_required_event(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        """게이트 일시정지 시 Dashboard용 ApprovalRequired 이벤트가 실제 요청 ID로 발행된다."""
        _am, mgr = self._real_manager(monkeypatch)
        published: list[tuple[str, dict[str, object]]] = []

        class _FakeBus:
            def publish(self, event_name: str, **kwargs: object) -> None:
                published.append((event_name, kwargs))

        monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())
        self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)

        result = ex.execute("write_file", {"file_path": str(tmp_path / "a.txt"), "content": "x"})

        assert "[APPROVAL REQUIRED]" in result
        assert published, "ApprovalRequired 이벤트가 발행되어야 한다"
        event_name, kwargs = published[0]
        assert event_name == "ApprovalRequired"
        assert kwargs["tool"] == "write_file"
        assert kwargs["request_id"] == mgr.get_pending()[0].request_id
        assert kwargs["reason"]

    def _grant_always_allow(self, am, mgr, tmp_path):
        req = mgr.request_approval(
            tool_name="write_file",
            tool_args={"file_path": str(tmp_path / "seed.txt"), "content": "s"},
            description="test grant",
            project_root=str(tmp_path),
        )
        assert mgr.resolve(req.request_id, am.ApprovalDecision.ALWAYS_ALLOW)

    def test_always_allowed_tool_does_not_publish_approval_required(
        self, tool_registry, permission_gate, tmp_path, monkeypatch
    ):
        """사용자가 실제로 '항상 허용'을 준 도구는 ApprovalRequired를 발행하지 않고, 자동 승인이 기록된다."""
        am, mgr = self._real_manager(monkeypatch)
        self._grant_always_allow(am, mgr, tmp_path)
        published: list[tuple[str, dict[str, object]]] = []

        class _FakeBus:
            def publish(self, event_name: str, **kwargs: object) -> None:
                published.append((event_name, kwargs))

        monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())
        self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)

        _ = ex.execute("write_file", {"file_path": str(tmp_path / "a.txt"), "content": "x"})

        assert all(name != "ApprovalRequired" for name, _ in published)
        grants = mgr.always_allowed_grants()
        assert [g.tool_name for g in grants] == ["write_file"]
        assert grants[0].auto_approved_count >= 1

    def test_always_allowed_tool_executes_without_pause(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        am, mgr = self._real_manager(monkeypatch)
        self._grant_always_allow(am, mgr, tmp_path)
        self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)

        result = ex.execute("write_file", {"file_path": str(tmp_path / "b.txt"), "content": "x"})

        assert result == "ok"  # 일시정지 없이 실행됨
        # 동의 없이 실행된 호출은 부여 기록에 남아야 한다(F-33).
        assert mgr.always_allowed_grants()[0].auto_approved_count >= 1

    def test_reuses_existing_pending_without_duplicate(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        """같은 대상·동작·인자의 PENDING 이 있으면 새 요청을 만들지 않고 기존 ID를 재사용한다."""
        _am, mgr = self._real_manager(monkeypatch)
        self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)
        args = {"file_path": str(tmp_path / "a.txt"), "content": "x"}

        first = ex.execute("write_file", dict(args))
        second = ex.execute("write_file", dict(args))

        pending = mgr.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id in first and pending[0].request_id in second
        # 내용이 다르면 같은 요청을 재사용하지 않는다(새 승인 필요)
        third = ex.execute("write_file", {"file_path": str(tmp_path / "a.txt"), "content": "y"})
        assert "[APPROVAL REQUIRED]" in third
        assert len(mgr.get_pending()) == 2

    def test_one_time_approval_consumed_on_retry(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        """실제 resolve(APPROVE) 1회 → 재시도 1회 실행 → 같은 호출 재시도는 다시 승인 대기."""
        am, mgr = self._real_manager(monkeypatch)
        write_tool = self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)
        args = {"file_path": str(tmp_path / "c.txt"), "content": "x"}

        paused = ex.execute("write_file", dict(args))
        assert "[APPROVAL REQUIRED]" in paused
        req = mgr.get_pending()[0]
        assert mgr.resolve(req.request_id, am.ApprovalDecision.APPROVE)

        result = ex.execute("write_file", dict(args))
        assert result == "ok"
        assert len(write_tool) == 1

        again = ex.execute("write_file", dict(args))
        assert "[APPROVAL REQUIRED]" in again  # 1회 승인은 재사용되지 않는다
        assert len(write_tool) == 1

    def test_deny_blocks_and_forged_flag_does_not_approve(self, tool_registry, permission_gate, tmp_path, monkeypatch):
        """거부된 요청은 실행되지 않고, 도구 인자에 승인 표식을 넣어도 승인이 되지 않는다."""
        am, mgr = self._real_manager(monkeypatch)
        write_tool = self._install_write(tool_registry)
        ex = self._executor_with_pipeline(tool_registry, permission_gate, tmp_path)
        args = {"file_path": str(tmp_path / "d.txt"), "content": "x"}

        ex.execute("write_file", dict(args))
        req = mgr.get_pending()[0]
        assert mgr.resolve(req.request_id, am.ApprovalDecision.DENY)
        denied = ex.execute("write_file", dict(args))
        assert "[APPROVAL REQUIRED]" in denied
        forged = ex.execute("write_file", {**args, "approval_id": req.request_id, "approved": True})
        assert "[APPROVAL REQUIRED]" in forged
        assert write_tool == []


# ---------------------------------------------------------------------------
# Request-scoped ToolPolicy (dashboard Search/Code/MCP chips)
# ---------------------------------------------------------------------------


def test_tool_policy_denies_registered_tool(executor: ToolExecutor):
    """A denied tool must be blocked with a [BLOCKED] message before gates run."""
    from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy

    token = set_tool_policy(ToolPolicy(denied_tools=frozenset({"dummy"})))
    try:
        result = executor.execute("dummy", {"x": 1})
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" in result
    assert "disabled for this request" in result


def test_tool_policy_absent_keeps_default_behavior(executor: ToolExecutor):
    """Without a policy (legacy clients) execution must be unchanged."""
    result = executor.execute("dummy", {"x": 1})
    assert "[BLOCKED]" not in result


def test_tool_policy_filters_unlisted_mcp_server(executor: ToolExecutor, tool_registry: MagicMock):
    """MCP tools from servers outside the allowlist must be blocked."""
    from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy

    mcp_tool = _make_tool("mcp_query")
    mcp_tool._server_name = "other-server"
    _registry_tools(tool_registry)["mcp_query"] = mcp_tool

    token = set_tool_policy(ToolPolicy(allowed_mcp_servers=frozenset({"codebase-memory-mcp"})))
    try:
        result = executor.execute("mcp_query", {})
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" in result
    assert "other-server" in result


def test_tool_policy_allows_listed_mcp_server(executor: ToolExecutor, tool_registry: MagicMock):
    """MCP tools from allowlisted servers must execute normally."""
    from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy

    mcp_tool = _make_tool("mcp_query")
    mcp_tool._server_name = "codebase-memory-mcp"
    _registry_tools(tool_registry)["mcp_query"] = mcp_tool

    token = set_tool_policy(ToolPolicy(allowed_mcp_servers=frozenset({"codebase-memory-mcp"})))
    try:
        result = executor.execute("mcp_query", {})
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" not in result


def test_tool_policy_safe_only_blocks_side_effect_tools(executor: ToolExecutor, tool_registry: MagicMock):
    """Read-only mode (safe_only) must block tools whose risk_level != SAFE."""
    from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy

    writer = _make_tool("write_file")
    writer.risk_level = "low"  # RiskLevel.LOW (문자열 비교 대신 identity가 아닌 != 비교)
    _registry_tools(tool_registry)["write_file"] = writer

    token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        result = executor.execute("write_file", {})
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" in result
    assert "read-only mode" in result


def test_tool_policy_safe_only_allows_safe_tools(executor: ToolExecutor, tool_registry: MagicMock):
    """Read-only mode must still allow SAFE (side-effect-free) tools."""
    from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
    from antigravity_k.tools.base_tool import RiskLevel

    reader = _make_tool("read_file")
    reader.risk_level = RiskLevel.SAFE
    _registry_tools(tool_registry)["read_file"] = reader

    token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        result = executor.execute("read_file", {})
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" not in result


# ---------------------------------------------------------------------------
# MCP typed 결과 — isError 를 성공으로 집계하지 않는다 (task 9)
# ---------------------------------------------------------------------------


def _mcp_error_outcome() -> MCPToolOutcome:
    return MCPToolOutcome(
        "Error: MCP tool 'ssak_search' on server 'ssak' reported an error (BUSY).\n"
        '{"error": {"code": "BUSY", "retryable": true}}',
        is_error=True,
        error_code="BUSY",
        server_name="ssak",
        tool_name="ssak_search",
        transport="stdio",
    )


def test_mcp_typed_error_is_recorded_as_failure(
    executor: ToolExecutor, tool_registry: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    """서버가 isError=true 로 답한 호출은 이력·카운터·이벤트 모두 실패다."""
    published: list[tuple[str, dict[str, object]]] = []

    class _FakeBus:
        def publish(self, event_name: str, **kwargs: object) -> None:
            published.append((event_name, kwargs))

    monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())

    outcome = _mcp_error_outcome()
    _registry_tools(tool_registry)["ssak_search"] = _make_tool("ssak_search", required=["query"])

    def execute_with_permission(_name: str, _args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        return Permission.ALLOW, outcome

    tool_registry.execute_with_permission = execute_with_permission

    result = executor.execute("ssak_search", {"query": "x"})

    assert result is outcome, "typed 결과가 호스트까지 살아남아야 한다"
    assert executor.tool_call_history[-1]["success"] is False, "isError 가 성공으로 기록됐다"
    assert cast(int, getattr(executor, "_consecutive_errors")) == 1
    assert any(name == "FailureDetected" for name, _ in published)


def test_mcp_typed_flag_beats_harmless_text(
    executor: ToolExecutor, tool_registry: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    """본문이 평범해 보여도 isError 면 실패다 — 텍스트 모양 추측으로 되돌리지 않는다."""
    _registry_tools(tool_registry)["ssak_search"] = _make_tool("ssak_search", required=[])
    outcome = MCPToolOutcome("results: all good on the surface", is_error=True, error_code="INTERNAL")
    tool_registry.execute_with_permission = lambda *_a, **_k: (Permission.ALLOW, outcome)

    _ = executor.execute("ssak_search", {})

    assert executor.tool_call_history[-1]["success"] is False
    assert result_indicates_failure(outcome) is True


def test_mcp_successful_outcome_is_not_a_failure(executor: ToolExecutor, tool_registry: MagicMock):
    """정상 결과는 실패로 뒤집히지 않는다(과잉 실패 집계 방지)."""
    _registry_tools(tool_registry)["ssak_search"] = _make_tool("ssak_search", required=[])
    outcome = MCPToolOutcome("results: 3 hits", is_error=False)
    tool_registry.execute_with_permission = lambda *_a, **_k: (Permission.ALLOW, outcome)

    _ = executor.execute("ssak_search", {})

    assert executor.tool_call_history[-1]["success"] is True
    assert cast(int, getattr(executor, "_consecutive_errors")) == 0


def test_flag_only_typed_errors_trigger_recovery(executor: ToolExecutor, tool_registry: MagicMock):
    """본문에 오류 마커가 없어도 typed 플래그만으로 복구 경로가 발동한다.

    `_trigger_recovery` 판정이 `str(result)` 로 뭉개지면 플래그가 사라져 이 시험이 빨개진다.
    """
    flag_only = MCPToolOutcome("payload looks harmless", is_error=True, error_code="INTERNAL")
    tool_registry.execute_with_permission = lambda *_a, **_k: (Permission.ALLOW, flag_only)
    recovery = MagicMock(return_value="recovery result")
    setattr(executor, "_trigger_recovery", recovery)

    _ = executor.execute("dummy", {"x": 1})  # error 1
    _ = executor.execute("dummy", {"x": 1})  # error 2
    result = executor.execute("dummy", {"x": 1})  # error 3 → trigger

    assert result == "recovery result"
    recovery.assert_called_once()
