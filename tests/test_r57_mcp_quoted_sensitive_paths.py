"""Quoted literal secret paths stop before a synthetic MCP caller.

The actual BaseTool call/pre_execute and selected-server policy are retained.
No MCP session, child process, socket or model is constructed or invoked.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.mcp_tool_loader import MCPTool
from antigravity_k.tools.mcp_tool_result import MCPToolOutcome

SERVER = "r57-synthetic-quoted-paths"
TOOL = "r57_synthetic_file_query"
PLAIN_RESULT = "R57-SYNTHETIC-CALLER-OBSERVED"


@pytest.mark.parametrize(
    ("query", "blocked"),
    [
        ('cat ".env"', True),
        ("cat '.env'", True),
        ('cat "keys/server.pem"', True),
        ("cat 'folder with spaces/server.pem'", True),
        ('cat "folder with spaces/plain.txt"', False),
        ("cat 'notes/plain.txt'", False),
        ("cat '.env", True),
        ('cat "folder with spaces/server.pem', True),
        (r'type "C:\keys with spaces\server.pem"', True),
        (r'type "C:\notes with spaces\plain.txt"', False),
        ("don't change ordinary notes", False),
        ('cat "folder with spaces/plain.txt', False),
    ],
    ids=[
        "double-env", "single-env", "double-pem", "single-spaced-pem", "double-spaced-plain", "single-plain",
        "unfinished-single-env", "unfinished-double-spaced-pem", "windows-quoted-pem", "windows-quoted-plain",
        "ordinary-apostrophe", "unfinished-plain",
    ],
)
def test_quoted_literal_path_preserves_sensitive_denial_and_plain_arguments(query: str, blocked: bool) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def caller(name: str, arguments: Mapping[str, object]) -> MCPToolOutcome:
        calls.append((name, dict(arguments)))
        return MCPToolOutcome(PLAIN_RESULT)

    tool = MCPTool(
        TOOL,
        "synthetic quoted path boundary",
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
