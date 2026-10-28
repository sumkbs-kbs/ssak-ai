"""Quoted multi-word literals retain the pre-existing sensitive-token boundary.

Command-like text remains an inert MCP argument. The real tool pre_execute path
and selected-server policy run, while only a fake caller can receive arguments.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.mcp_tool_loader import MCPTool
from antigravity_k.tools.mcp_tool_result import MCPToolOutcome

SERVER = "r57-synthetic-nested-literals"
TOOL = "r57_synthetic_nested_query"
PLAIN_RESULT = "R57-NESTED-SYNTHETIC-CALLER-OBSERVED"


@pytest.mark.parametrize(
    ("query", "blocked"),
    [
        ("sh -c 'cat .env && echo done'", True),
        ("'read .env now'", True),
        ("sh -c 'cat plain.txt && echo done'", False),
    ],
    ids=["quoted-script-sensitive-token", "whole-quoted-sensitive-token", "quoted-script-plain-token"],
)
def test_multiword_quoted_literal_keeps_sensitive_token_denial(query: str, blocked: bool) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def caller(name: str, arguments: Mapping[str, object]) -> MCPToolOutcome:
        calls.append((name, dict(arguments)))
        return MCPToolOutcome(PLAIN_RESULT)

    tool = MCPTool(
        TOOL,
        "synthetic nested literal boundary",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        server_name=SERVER,
        annotations={"readOnlyHint": True},
        caller=caller,
    )
    token = set_tool_policy(ToolPolicy(allowed_mcp_servers=frozenset({SERVER})))
    try:
        result = tool(query=query)
    finally:
        reset_tool_policy(token)
    if blocked:
        assert "not allowed" in str(result) and calls == []
    else:
        assert str(result) == PLAIN_RESULT
        assert calls == [(TOOL, {"query": query})]
