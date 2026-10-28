"""r38: which layer refuses c07 (web_scrape loopback) and c12 (run_persistent_command curl)?

Real ToolRegistry / PermissionGate / PlanGuard / default GatePipeline / ToolExecutor. Only the side-effect
sinks are replaced by counters (PageScraper.extract_text, PersistentTerminalManager.create_terminal), so a
call that passes every layer is COUNTED instead of touching the network or spawning a shell.
Permission checks are NOT mocked. The layer is read from the executor's structured refusal tag.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
from antigravity_k.engine.gate_pipeline import create_default_pipeline
from antigravity_k.engine.plan_guard import PlanGuard
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.engine.tool_guardrails import ToolCallGuardrailController
from antigravity_k.tools import terminal_tools, web_search_engine
from antigravity_k.tools.tool_registry import ToolRegistry

CASES = {
    "c07_web_scrape_loopback": ("web_scrape", {"url": "http://127.0.0.1:18999/fetch"}),
    "c12_persistent_shell": ("run_persistent_command", {"command": "curl -s -m 3 http://127.0.0.1:18999/p"}),
}
_TAGS = ("[APPROVAL REQUIRED]", "[DENIED]", "[BLOCKED]", "[POLICY", "[GOVERNANCE", "Permission denied", "권한")


def _layer(text: str) -> str:
    for tag in _TAGS:
        if tag in text:
            return tag
    m = re.match(r"\s*(\[[A-Z_ ]+\]|Error[^:]*:)", text)
    return m.group(1) if m else "other"


@pytest.mark.parametrize("mode", [AccessMode.FULL_ACCESS, AccessMode.READ_ONLY])
@pytest.mark.parametrize("case", sorted(CASES))
def test_layer_and_sink_counter(tmp_path: Path, case: str, mode: AccessMode) -> None:
    sink = {"scrape": 0, "terminal": 0}

    async def _scrape(self: object, url: str, max_chars: int = 0) -> str:
        _ = (self, url, max_chars)
        sink["scrape"] += 1
        return "fake page"

    def _term(self: object, command: str, cwd: str) -> str:
        _ = (self, command, cwd)
        sink["terminal"] += 1
        return "term-1"

    previous = get_access_mode()
    set_access_mode(mode)
    try:
        with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
            registry = ToolRegistry(project_root=str(tmp_path))
            executor = ToolExecutor(
                tool_registry=registry,
                permission_gate=registry.permission_gate,
                project_root=str(tmp_path),
                plan_guard=PlanGuard(),
                gate_pipeline=create_default_pipeline(guardrails=cast(Any, ToolCallGuardrailController())),
            )
            setattr(executor, "_immune_system", None)
            executor.register_default_tools()
        with (
            patch.object(web_search_engine.PageScraper, "extract_text", _scrape),
            patch.object(terminal_tools.PersistentTerminalManager, "create_terminal", _term),
        ):
            name, args = CASES[case]
            result = executor.execute(name, dict(args))
    finally:
        set_access_mode(previous)
    record = {
        "case": case,
        "mode": mode.value,
        "layer": _layer(result),
        "sink": sink,
        "result_len": len(result),
        "head": result[:120],
    }
    out = os.environ.get("R38_LAYER_LOG")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    print("R38LAYER", json.dumps(record))
    # Observation test: it must not reach a sink silently. Executed => counted; refused => tagged.
    assert sum(sink.values()) == 0 or record["layer"] == "other"
