"""r41 task 4: approval/egress boundaries (synthetic sinks only, nothing real executes)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from antigravity_k.engine import approval_manager as am
from antigravity_k.engine import gate_pipeline
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.tools.egress_policy import EgressPolicyError, validate_scrape_egress_url
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

EIGHT = (
    "memory_write",
    "store_knowledge",
    "run_tests",
    "auto_lint",
    "cowork_delegate",
    "send_command_input",
    "interactive_pty",
    "run_docker_bash",
)


@pytest.fixture
def mgr(monkeypatch: pytest.MonkeyPatch) -> am.ApprovalManager:
    manager = am.ApprovalManager()
    monkeypatch.setattr(am, "get_approval_manager", lambda: manager)
    monkeypatch.setattr("antigravity_k.engine.tool_executor.get_approval_manager", lambda: manager)
    return manager


def _executor(tmp_path: Path, names: tuple[str, ...], calls: list[str]) -> ToolExecutor:
    reg = MagicMock(spec=ToolRegistry)
    tools = {}
    for name in names:
        tool = MagicMock()
        tool.name = name
        tool.parameters_schema = {"required": []}
        tools[name] = tool
    reg.get = MagicMock(side_effect=tools.get)
    reg.get_tool = MagicMock(side_effect=tools.get)
    reg.__contains__ = lambda _s, n: n in tools

    def run(name: str, args: dict[str, object], objective: str = "") -> tuple[Permission, str]:
        calls.append(name + json.dumps(args, sort_keys=True))  # synthetic sink
        return Permission.ALLOW, "sink-ok"

    reg.execute_with_permission = run
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        ex = ToolExecutor(
            tool_registry=reg,
            permission_gate=MagicMock(spec=PermissionGate),
            project_root=str(tmp_path),
            gate_pipeline=gate_pipeline.create_default_pipeline(),
        )
    setattr(ex, "_immune_system", None)
    return ex


def test_eight_tools_are_governed_by_the_approval_gate() -> None:
    assert set(EIGHT) <= gate_pipeline.ApprovalGate.UNLESS_AUTO_APPROVED


def test_eight_tools_registered_names_match_policy(tmp_path: Path) -> None:
    """Names the policy governs are the names the real registry exposes (no alias bypass)."""
    from antigravity_k.engine.security_policy import _SEEDED_DEFAULTS

    for name in EIGHT:
        assert name in _SEEDED_DEFAULTS


@pytest.mark.parametrize("tool", EIGHT + ("web_scrape",))
def test_deny_allow_once_and_per_request(tmp_path: Path, mgr: am.ApprovalManager, tool: str) -> None:
    calls: list[str] = []
    ex = _executor(tmp_path, (tool,), calls)
    a1, a2 = {"x": "1"}, {"x": "2"}
    assert "[APPROVAL REQUIRED]" in ex.execute(tool, dict(a1))
    (req,) = mgr.get_pending()
    # deny -> nothing runs, retry pauses again
    assert mgr.resolve(req.request_id, am.ApprovalDecision.DENY)
    assert "[APPROVAL REQUIRED]" in ex.execute(tool, dict(a1)) and calls == []
    # allow once -> exactly one run, next identical call asks again
    req2 = [r for r in mgr.get_pending() if r.tool_name == tool][0]
    assert mgr.resolve(req2.request_id, am.ApprovalDecision.APPROVE)
    assert ex.execute(tool, dict(a1)) == "sink-ok"
    assert "[APPROVAL REQUIRED]" in ex.execute(tool, dict(a1))
    # approval is per request: other args are not covered
    assert "[APPROVAL REQUIRED]" in ex.execute(tool, dict(a2))
    assert len(calls) == 1


@pytest.mark.parametrize("tool", ["git_push", "deploy", "payment", "browser_effect"])
def test_engine_refuses_always_allow_for_always_ask_tools(mgr: am.ApprovalManager, tool: str) -> None:
    req = mgr.request_approval(tool_name=tool, tool_args={"x": "1"}, description="d")
    assert mgr.resolve(req.request_id, am.ApprovalDecision.ALWAYS_ALLOW) is False
    assert not mgr.is_always_allowed(tool)


def test_tool_wide_always_allow_does_not_cover_strict_layer(mgr: am.ApprovalManager) -> None:
    req = mgr.request_approval(tool_name="write_file", tool_args={"file_path": "a"}, description="d")
    assert mgr.resolve(req.request_id, am.ApprovalDecision.ALWAYS_ALLOW)
    strict = mgr.request_approval(
        tool_name="write_file", tool_args={"file_path": ".env"}, description="d", layer="strict:secret"
    )
    assert strict.status == am.ApprovalStatus.PENDING
    assert mgr.resolve(strict.request_id, am.ApprovalDecision.ALWAYS_ALLOW) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api/fs/write",
        "http://localhost/x",
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://a.localhost/",
    ],
)
def test_scrape_send_boundary_blocks_local_and_private(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("AGK_SEARCH_ENABLED", "true")
    with pytest.raises(EgressPolicyError):
        validate_scrape_egress_url(url)


def test_scrape_send_boundary_honours_search_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGK_SEARCH_ENABLED", "false")
    with pytest.raises(EgressPolicyError):
        validate_scrape_egress_url("https://example.com/")


def test_page_scraper_uses_scrape_hook() -> None:
    import inspect

    from antigravity_k.tools import web_search_engine

    src = inspect.getsource(web_search_engine.PageScraper)
    assert "validate_scrape_httpx_request_async" in src


@pytest.mark.parametrize(
    ("module", "tool", "key"),
    [
        ("antigravity_k.api.routes.filesystem", "fs_write", "path"),
        ("antigravity_k.api.routes.git_api", "git_add", "path"),
        ("antigravity_k.api.routes.vault_api", "vault_write", "path"),
    ],
)
def test_direct_ui_gate_still_denies_secret_paths(module: str, tool: str, key: str, tmp_path: Path) -> None:
    import importlib

    mod = importlib.import_module(module)
    with pytest.raises(HTTPException) as exc:
        mod._require_allowed(tool, {key: str(tmp_path / ".env")}, "medium")
    assert exc.value.status_code == 403
