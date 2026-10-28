"""r39 contracts: execution policy split, tool registration, c07/c12 layers, journal re-plan, non-agent memory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from antigravity_k.engine import access_mode as am
from antigravity_k.engine import tool_execution_journal as tej
from antigravity_k.engine.past_memory import build_past_memory_block
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

MODES = {
    "read_only": (am.AccessMode.READ_ONLY, None),
    "full_balanced": (am.AccessMode.FULL_ACCESS, None),
    "full_explicit_autopilot": (am.AccessMode.FULL_ACCESS, am.ExecutionPolicy.AUTO_PILOT),
}


@pytest.fixture()
def policy_reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(am.EXECUTION_POLICY_ENV, raising=False)
    prev_mode = am.get_access_mode()
    yield
    am.set_access_mode(prev_mode)
    am.set_execution_policy(None)


def _apply(mode_key: str) -> None:
    access, policy = MODES[mode_key]
    am.set_access_mode(access)
    am.set_execution_policy(policy)


def _decide(gate: PermissionGate, name: str, risk: str, args: dict[str, object]) -> Permission:
    return gate.decide(ToolInvocation(ToolSpec(name=name, risk_level=risk, category="api"), cast(Any, args))).permission


EXPECT = {
    # mode: (file read, shell, write)
    "read_only": (Permission.ALLOW, Permission.PROMPT, Permission.PROMPT),
    "full_balanced": (Permission.ALLOW, Permission.PROMPT, Permission.PROMPT),
    "full_explicit_autopilot": (Permission.ALLOW, Permission.ALLOW, Permission.ALLOW),
}


def test_default_is_balanced_not_autopilot(policy_reset: None) -> None:
    am.set_access_mode(am.AccessMode.FULL_ACCESS)
    assert am.get_execution_policy() is am.ExecutionPolicy.BALANCED
    assert am.effective_permission_mode() == "balanced"
    assert PermissionGate(project_root="/tmp").mode == "balanced"


def test_env_opt_in_and_readonly_override(policy_reset: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(am.EXECUTION_POLICY_ENV, "auto-pilot")
    am.set_access_mode(am.AccessMode.FULL_ACCESS)
    assert am.effective_permission_mode() == "auto-pilot"
    am.set_access_mode(am.AccessMode.READ_ONLY)
    assert am.effective_permission_mode() == "balanced"
    am.set_access_mode(am.AccessMode.FULL_ACCESS)
    am.set_execution_policy(am.ExecutionPolicy.BALANCED)  # explicit API choice beats env
    assert am.effective_permission_mode() == "balanced"


@pytest.mark.parametrize("mode_key", sorted(MODES))
def test_matrix_file_shell_write(policy_reset: None, tmp_path: Path, mode_key: str) -> None:
    _apply(mode_key)
    gate = PermissionGate(project_root=str(tmp_path))
    target = str(tmp_path / "note.txt")
    got = (
        _decide(gate, "read_file", "safe", {"path": target}),
        _decide(gate, "run_bash_command", "high", {"command": "echo synthetic", "cwd": str(tmp_path)}),
        _decide(gate, "write_file", "medium", {"path": target, "content": "synthetic"}),
    )
    assert got == EXPECT[mode_key], (mode_key, got)


@pytest.mark.parametrize("mode_key", sorted(MODES))
def test_shell_api_mode(policy_reset: None, mode_key: str) -> None:
    from antigravity_k.api.routes import agent_tools

    _apply(mode_key)
    assert agent_tools._permission_mode() == ("auto-pilot" if mode_key == "full_explicit_autopilot" else "balanced")


# ── 2. tool registration ────────────────────────────────────────────────


def _executor(tmp_path: Path, registry: object | None = None):
    from antigravity_k.engine.gate_pipeline import create_default_pipeline
    from antigravity_k.engine.plan_guard import PlanGuard
    from antigravity_k.engine.tool_executor import ToolExecutor
    from antigravity_k.engine.tool_guardrails import ToolCallGuardrailController
    from antigravity_k.tools.tool_registry import ToolRegistry

    reg = registry or ToolRegistry(project_root=str(tmp_path))
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        ex = ToolExecutor(
            tool_registry=cast(Any, reg),
            permission_gate=cast(Any, reg).permission_gate,
            project_root=str(tmp_path),
            plan_guard=PlanGuard(),
            gate_pipeline=create_default_pipeline(guardrails=cast(Any, ToolCallGuardrailController())),
        )
    setattr(ex, "_immune_system", None)
    return ex, reg


def test_register_default_tools_isolates_failures(tmp_path: Path) -> None:
    from antigravity_k.tools import binary_tools

    ex, reg = _executor(tmp_path)
    with patch.object(binary_tools, "HexDumpTool", side_effect=RuntimeError("synthetic")):
        ex.register_default_tools()
    names = set(reg.get_names())
    assert ex.registration_failures.get("HexDumpTool") == "RuntimeError"
    assert {"read_file", "write_file", "run_bash_command", "write_artifact"} <= names
    report = {"registered": len(names), "failures": ex.registration_failures}
    out = os.environ.get("R39_LOG")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"registration_injected": report}) + "\n")


def test_register_default_tools_clean(tmp_path: Path) -> None:
    ex, reg = _executor(tmp_path)
    ex.register_default_tools()
    assert ex.registration_failures == {}
    names = set(reg.get_names())
    # web_scrape / run_persistent_command are NOT default tools; the app registers them via auto_discover.
    record = {
        "default_count": len(names),
        "web_scrape": "web_scrape" in names,
        "run_persistent_command": "run_persistent_command" in names,
    }
    out = os.environ.get("R39_LOG")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"registration_clean": record}) + "\n")


# ── c07 / c12 through the app's auto_discover registry ────────────────

CASES = {
    "c07_web_scrape_loopback": ("web_scrape", {"url": "http://127.0.0.1:18999/fetch"}),
    "c12_persistent_shell": ("run_persistent_command", {"command": "curl -s -m 3 http://127.0.0.1:18999/p"}),
}
_TAGS = ("[APPROVAL REQUIRED]", "[DENIED]", "[BLOCKED]", "[차단됨: public HTTP URL만 허용]", "Unknown tool")


@pytest.mark.parametrize("mode_key", sorted(MODES))
@pytest.mark.parametrize("case", sorted(CASES))
def test_c07_c12_layers(policy_reset: None, tmp_path: Path, case: str, mode_key: str) -> None:
    from antigravity_k.tools import terminal_tools, web_search_engine
    from antigravity_k.tools.tool_registry import ToolRegistry

    _apply(mode_key)
    reg = ToolRegistry(project_root=str(tmp_path))
    discovered = reg.auto_discover("antigravity_k.tools")
    ex, _ = _executor(tmp_path, reg)
    # sinks = the network client / DNS resolution (PageScraper.extract_text itself stays REAL) and the
    # subprocess-spawning terminal manager. Reaching them is counted instead of connecting/spawning.
    sink = {"http_client": 0, "dns": 0, "terminal": 0}

    async def _client(self: object) -> object:
        sink["http_client"] += 1
        raise RuntimeError("synthetic sink: no network in tests")

    async def _resolve(url: str) -> None:
        sink["dns"] += 1
        return None

    def _term(self: object, command: str, cwd: str) -> str:
        sink["terminal"] += 1
        return "term-1"

    name, args = CASES[case]
    registered = name in reg.get_names()
    with (
        patch.object(web_search_engine.PageScraper, "_get_client", _client),
        patch.object(web_search_engine, "resolve_public_http_url", _resolve),
        patch.object(terminal_tools.PersistentTerminalManager, "create_terminal", _term),
    ):
        result = ex.execute(name, dict(args))
    layer = next((t for t in _TAGS if t in result), "executed_or_other")
    record = {
        "case": case,
        "mode": mode_key,
        "discovered": discovered,
        "registered": registered,
        "layer": layer,
        "sink": sink,
        "head": result[:160],
    }
    out = os.environ.get("R39_LOG")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"c07c12": record}, ensure_ascii=False) + "\n")
    assert registered, record  # an unregistered tool is never counted as a block PASS
    # every mode, including explicit auto-pilot: loopback scrape is refused inside PageScraper before any
    # client/DNS use; the persistent shell pauses at ApprovalGate (PermissionGate auto-pilot does not bypass it).
    assert sum(sink.values()) == 0, record
    # r40: web_scrape is now governed by ApprovalGate (declared ASK_EACH_TIME) -> pauses in every mode.
    assert layer == "[APPROVAL REQUIRED]", record


# ── 3A. side effects across steering re-plan (journal) ────────────────


def test_steering_replan_does_not_rewrite_completed(tmp_path: Path) -> None:
    target = str(tmp_path / "out.md")
    with tej.task_scope("task-r39", False):
        assert tej.journaled_write(str(tmp_path), target, "body")[0] == "written"
    # steering → re-plan within the same task (not a resume) produces the same write again
    with tej.task_scope("task-r39", False):
        assert tej.journaled_write(str(tmp_path), target, "body")[0] == "skipped_completed"
    writes = [json.loads(x) for x in (tmp_path / ".tool_journal.jsonl").read_text().splitlines()]
    assert sum(1 for r in writes if r.get("state") == "executed" and not r.get("recovered")) == 1


def test_unknown_state_is_held_not_rerun(tmp_path: Path) -> None:
    target = str(tmp_path / "out.md")
    with tej.task_scope("task-r39u", False):
        assert tej.journaled_write(str(tmp_path), target, "body")[0] == "written"
    Path(target).write_text("externally modified")
    with tej.task_scope("task-r39u", True):
        assert tej.journaled_write(str(tmp_path), target, "body")[0] == "held_unknown"
    assert Path(target).read_text() == "externally modified"


# ── 3B. non-agent past_memory ─────────────────────────────────────────


class _Store:
    def __init__(self, rows: list[Any] | None = None, exc: bool = False) -> None:
        self.rows, self.exc, self.calls = rows or [], exc, 0

    def search(self, query: str, n_results: int = 5) -> list[Any]:
        self.calls += 1
        if self.exc:
            raise RuntimeError("synthetic")
        return self.rows


def _vault(store: _Store, sync: bool = True) -> SimpleNamespace:
    return SimpleNamespace(sync_rag=sync, vector_store=store)


def test_block_statuses() -> None:
    row = {"text": "synthetic memo", "metadata": {"source": "wiki/memo.md"}}
    assert build_past_memory_block(_vault(_Store([row])), "q")[1:] == ("hit", 1)
    assert build_past_memory_block(_vault(_Store([])), "q")[1:] == ("empty", 0)
    assert build_past_memory_block(_vault(_Store(exc=True)), "q")[1:] == ("error", 0)
    assert build_past_memory_block(_vault(_Store([row]), sync=False), "q")[1:] == ("disabled", 0)
    assert build_past_memory_block(None, "q")[1:] == ("disabled", 0)


RECALL_Q = "우리가 정한 배포 코드명이 뭐였지?"


def test_non_agent_attach_uses_request_project(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.api import dependencies
    from antigravity_k.api.routes import chat

    stores = {
        "proj-a": _Store([{"text": "memo-a", "metadata": {"source": "a.md"}}]),
        "proj-b": _Store([{"text": "memo-b", "metadata": {"source": "b.md"}}]),
    }
    seen: list[str | None] = []

    def _acquire(*, project_id: str | None = None, project_root: str | None = None) -> SimpleNamespace:
        seen.append(project_id)
        return SimpleNamespace(vault_engine=_vault(stores[str(project_id)]))

    monkeypatch.setattr(dependencies, "acquire_project_runtime", _acquire)
    ctx = cast(Any, SimpleNamespace(project_id="proj-b", canonical_project_root="/tmp/b"))
    msgs = cast(Any, [{"role": "user", "content": RECALL_Q}])
    out, status = chat._attach_non_agent_past_memory(msgs, ctx, True)
    assert status == "hit" and seen == ["proj-b"]
    content = str(out[-1]["content"])
    assert "memo-b" in content and "memo-a" not in content
    assert stores["proj-a"].calls == 0 and msgs[-1]["content"] == RECALL_Q  # input list not mutated


@pytest.mark.parametrize(
    ("store", "question", "allowed", "expect"),
    [
        (_Store([]), RECALL_Q, True, "empty"),
        (_Store(exc=True), RECALL_Q, True, "error"),
        (_Store([{"text": "x"}]), "hello", True, "not_recall"),
        (_Store([{"text": "x"}]), RECALL_Q, False, "skipped"),
    ],
)
def test_non_agent_attach_statuses(
    monkeypatch: pytest.MonkeyPatch, store: _Store, question: str, allowed: bool, expect: str
) -> None:
    from antigravity_k.api import dependencies
    from antigravity_k.api.routes import chat

    monkeypatch.setattr(
        dependencies, "acquire_project_runtime", lambda **_: SimpleNamespace(vault_engine=_vault(store))
    )
    ctx = cast(Any, SimpleNamespace(project_id="p", canonical_project_root="/tmp/p"))
    msgs = cast(Any, [{"role": "user", "content": question}])
    out, status = chat._attach_non_agent_past_memory(msgs, ctx, allowed)
    assert status == expect
    assert out[-1]["content"] == question
