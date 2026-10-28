"""r41 A: executor-enforced per-task allowlist + completed-call reuse (fake tools only).

Replays the r40 hA model behaviour against a real ToolExecutor, real gate pipeline, real
ApprovalManager and a real TaskStateStore: write -> approval -> executes once -> the model
re-emits the identical write (must be reused, no 2nd approval/overwrite) -> drifts to
run_bash_command / web_search (must be blocked at the executor without an approval request).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from antigravity_k.engine import approval_manager as am
from antigravity_k.engine import gate_pipeline
from antigravity_k.engine.task_execution_context import TaskExecutionContext, bind_task_execution_context
from antigravity_k.engine.task_state_store import TaskStateStore
from antigravity_k.engine.task_tool_contract import normalize_allowed_tools
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

TOOLS = ("write_artifact", "run_bash_command", "web_search", "read_file", "web_scrape", "memory_write")


def _registry(calls: list[tuple[str, str]]) -> MagicMock:
    reg = MagicMock(spec=ToolRegistry)
    tools: dict[str, MagicMock] = {}
    for name in TOOLS:
        tool = MagicMock()
        tool.name = name
        tool.parameters_schema = {"required": []}
        tools[name] = tool
    reg.get = MagicMock(side_effect=tools.get)
    reg.get_tool = MagicMock(side_effect=tools.get)
    reg.__contains__ = lambda _self, name: name in tools

    def execute_with_permission(name: str, args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        _ = objective
        calls.append((name, json.dumps(args, sort_keys=True)))  # side-effect boundary
        return Permission.ALLOW, f"{name} done"

    reg.execute_with_permission = execute_with_permission
    return reg


def _executor(reg: MagicMock, root: Path) -> ToolExecutor:
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        ex = ToolExecutor(
            tool_registry=reg,
            permission_gate=MagicMock(spec=PermissionGate),
            project_root=str(root),
            gate_pipeline=gate_pipeline.create_default_pipeline(),
        )
    setattr(ex, "_immune_system", None)
    return ex


@pytest.fixture
def mgr(monkeypatch: pytest.MonkeyPatch) -> am.ApprovalManager:
    manager = am.ApprovalManager()
    monkeypatch.setattr(am, "get_approval_manager", lambda: manager)
    monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: manager)
    return manager


def _task(store: TaskStateStore, task_id: str, context: dict[str, object]) -> TaskExecutionContext:
    _ = store.create_task(task_id, "synthetic", "running", "2026-10-27T00:00:00")
    store.save_checkpoint(task_id, 0, json.dumps(context), "")
    return TaskExecutionContext(task_id, store)


WRITE = {"filename": "r41-note.md", "content": "synthetic r41 note"}


def test_r40_replay_single_execution_reuse_and_blocked_drift(tmp_path: Path, mgr: am.ApprovalManager) -> None:
    calls: list[tuple[str, str]] = []
    ex = _executor(_registry(calls), tmp_path)
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    tctx = _task(store, "task_a", {"allowed_tools": {"write_artifact": 1}})
    with bind_task_execution_context(tctx):
        first = ex.execute("write_artifact", dict(WRITE))
        assert "[APPROVAL REQUIRED]" in first and calls == []
        (req,) = mgr.get_pending()
        assert mgr.resolve(req.request_id, am.ApprovalDecision.APPROVE)
        assert ex.execute("write_artifact", dict(WRITE)) == "write_artifact done"
        again = ex.execute("write_artifact", dict(WRITE))
        assert again.startswith("[ALREADY COMPLETED]")
        bash = ex.execute("run_bash_command", {"command": "ls"})
        web = ex.execute("web_search", {"query": "x"})
        other_write = ex.execute("write_artifact", {"filename": "r41-note.md", "content": "changed"})
    assert "[BLOCKED]" in bash and "not in this task's allowed tools" in bash
    assert "[BLOCKED]" in web
    assert "[BLOCKED]" in other_write and "allowed 1 call" in other_write  # no batch 2nd overwrite
    assert calls == [("write_artifact", json.dumps(WRITE, sort_keys=True))]
    assert mgr.get_pending() == []  # extra/duplicate requests created NO approval request


def test_reuse_survives_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    db = str(tmp_path / "tasks.db")
    m1 = am.ApprovalManager()
    monkeypatch.setattr(am, "get_approval_manager", lambda: m1)
    monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: m1)
    ex = _executor(_registry(calls), tmp_path)
    with bind_task_execution_context(_task(TaskStateStore(db), "task_b", {"allowed_tools": ["write_artifact"]})):
        ex.execute("write_artifact", dict(WRITE))
        assert m1.resolve(m1.get_pending()[0].request_id, am.ApprovalDecision.APPROVE)
        assert ex.execute("write_artifact", dict(WRITE)) == "write_artifact done"
    # "restart": fresh store object, fresh executor, fresh (empty) approval manager
    m2 = am.ApprovalManager()
    monkeypatch.setattr(am, "get_approval_manager", lambda: m2)
    monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: m2)
    ex2 = _executor(_registry(calls), tmp_path)
    with bind_task_execution_context(TaskExecutionContext("task_b", TaskStateStore(db))):
        resumed = ex2.execute("write_artifact", dict(WRITE))
    assert resumed.startswith("[ALREADY COMPLETED]")
    assert len(calls) == 1 and m2.get_pending() == []


def test_empty_allowlist_blocks_everything_without_approval(tmp_path: Path, mgr: am.ApprovalManager) -> None:
    calls: list[tuple[str, str]] = []
    ex = _executor(_registry(calls), tmp_path)
    with bind_task_execution_context(_task(TaskStateStore(str(tmp_path / "t.db")), "task_c", {"allowed_tools": []})):
        for name in TOOLS:
            assert "[BLOCKED]" in ex.execute(name, {"x": 1})
    assert calls == [] and mgr.get_pending() == []


def test_prompt_contract_does_not_bypass_approval(tmp_path: Path, mgr: am.ApprovalManager) -> None:
    """expected_tools (tool named in prompt / client context) is NOT approval (r41 fix)."""
    calls: list[tuple[str, str]] = []
    ex = _executor(_registry(calls), tmp_path)
    ctx = {"expected_tools": ["web_scrape", "run_bash_command", "memory_write"]}
    with bind_task_execution_context(_task(TaskStateStore(str(tmp_path / "t.db")), "task_d", ctx)):
        for name in ("web_scrape", "run_bash_command", "memory_write"):
            assert "[APPROVAL REQUIRED]" in ex.execute(name, {"url": "https://example.invalid/"})
    assert calls == []
    assert sorted(r.tool_name for r in mgr.get_pending()) == ["memory_write", "run_bash_command", "web_scrape"]


def test_no_task_context_keeps_existing_behaviour(tmp_path: Path, mgr: am.ApprovalManager) -> None:
    calls: list[tuple[str, str]] = []
    ex = _executor(_registry(calls), tmp_path)
    assert ex.execute("read_file", {"path": "a"}) == "read_file done"
    assert "[APPROVAL REQUIRED]" in ex.execute("write_artifact", dict(WRITE))


@pytest.mark.parametrize(
    "raw",
    [{"x": 9}, {"x": True}, {"": 1}, [""], [1], "write_artifact", {"x": -1}],
)
def test_malformed_allowlist_rejected(raw: object) -> None:
    with pytest.raises(ValueError):
        normalize_allowed_tools(raw)
