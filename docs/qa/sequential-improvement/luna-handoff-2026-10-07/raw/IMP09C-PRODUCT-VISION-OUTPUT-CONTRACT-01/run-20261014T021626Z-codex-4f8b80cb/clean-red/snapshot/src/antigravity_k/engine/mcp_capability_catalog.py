import json

from antigravity_k.engine.mcp_capability_models import MCPCapability


def latest_capabilities() -> list[MCPCapability]:
    return [
        MCPCapability(
            name="Streamable HTTP transport",
            why_it_matters=(
                "The latest MCP transport model replaces legacy HTTP+SSE and "
                "supports POST/GET, streaming, resumability, and sessions."
            ),
            antigravity_action=(
                "Support `type: http` / `transport: streamable-http` in "
                "MCPSessionManager and prefer it for remote servers."
            ),
            priority="P0",
            evidence_url="https://modelcontextprotocol.io/specification/2025-11-25/basic/transports",
        ),
        MCPCapability(
            name="OAuth 2.1 authorization",
            why_it_matters=(
                "Remote MCP servers should authenticate clients rather than depending on ambient API keys."
            ),
            antigravity_action=(
                "Flag non-local HTTP MCP servers without auth; offer interactive OAuth 2.1 "
                "(authorization code + PKCE) via /api/mcp/oauth and Settings panel."
            ),
            priority="P0",
            evidence_url="https://modelcontextprotocol.io/specification/2025-03-26/changelog",
        ),
        MCPCapability(
            name="Tool annotations",
            why_it_matters=(
                "Annotations such as read-only or destructive help clients apply "
                "permission gates and avoid accidental side effects."
            ),
            antigravity_action="Map MCP annotations to BaseTool risk levels and dashboard metadata.",
            priority="P0",
            evidence_url="https://modelcontextprotocol.io/specification/2025-03-26/changelog",
        ),
        MCPCapability(
            name="JSON-RPC batching and completions",
            why_it_matters=(
                "Batching reduces round trips; completions improve parameter entry and tool-call accuracy."
            ),
            antigravity_action=("Expose batching/completions as optional server capabilities in the MCP audit report."),
            priority="P1",
            evidence_url="https://modelcontextprotocol.io/specification/2025-03-26/changelog",
        ),
        MCPCapability(
            name="HF MCPClient and Tiny Agents",
            why_it_matters=(
                "Hugging Face now exposes MCPClient/Tiny Agent patterns for "
                "connecting stdio, SSE, and HTTP MCP servers to tool-using agents."
            ),
            antigravity_action=(
                "Keep MCP config compatible with `stdio`, `sse`, and `http` "
                "server descriptors and surface a template command."
            ),
            priority="P1",
            evidence_url="https://huggingface.co/docs/huggingface_hub/package_reference/mcp",
        ),
        MCPCapability(
            name="Precomputed Relational Intelligence (GitNexus)",
            why_it_matters=(
                "Graph-based AST parsers like GitNexus precompute dependency chains, "
                "preventing LLMs from hallucinating blast radius or missing references."
            ),
            antigravity_action=(
                "Expose GitNexus MCP tools (`impact`, `context`) to the orchestration "
                "loop so the agent can safely explore dependencies before refactoring."
            ),
            priority="P1",
            evidence_url="https://github.com/abhigyanpatwari/GitNexus",
        ),
    ]


def render_template() -> str:
    template = {
        "mcpServers": {
            "playwright-local": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest"],
                "trust_level": "local",
                "timeout_ms": 30000,
                "tool_annotations": "required",
            },
            "example-remote": {
                "type": "http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer ${EXAMPLE_MCP_TOKEN}"},
                "trust_level": "verified",
                "timeout_ms": 30000,
                "tool_annotations": "required",
            },
            "gitnexus": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "gitnexus@latest", "mcp"],
                "trust_level": "local",
                "timeout_ms": 60000,
                "tool_annotations": "read-only",
            },
        },
    }
    return json.dumps(template, ensure_ascii=False, indent=2)
