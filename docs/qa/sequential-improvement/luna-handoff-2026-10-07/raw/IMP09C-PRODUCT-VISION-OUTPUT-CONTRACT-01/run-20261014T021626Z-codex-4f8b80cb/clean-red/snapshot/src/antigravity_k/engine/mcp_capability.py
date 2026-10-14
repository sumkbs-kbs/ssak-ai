"""MCP capability and safety advisor.

This module keeps MCP adoption inside Ssak-Ai evidence-driven: it can
inspect MCP server configuration, map it to the latest protocol capabilities,
and produce a concrete upgrade plan before any external server is connected.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol

from pydantic import JsonValue, TypeAdapter, ValidationError

from antigravity_k.engine.mcp_capability_catalog import (
    latest_capabilities as _latest_capabilities,
)
from antigravity_k.engine.mcp_capability_catalog import (
    render_template as _render_template,
)
from antigravity_k.engine.mcp_capability_models import (
    MCPAuditReport,
    MCPCapability,
    MCPFinding,
)
from antigravity_k.engine.mcp_capability_parsing import (
    has_auth as _has_auth,
)
from antigravity_k.engine.mcp_capability_parsing import (
    is_local_url as _is_local_url,
)
from antigravity_k.engine.mcp_capability_parsing import (
    string_list as _string_list,
)
from antigravity_k.engine.mcp_capability_parsing import (
    transport_for as _transport_for,
)
from antigravity_k.engine.mcp_capability_parsing import (
    uses_unpinned_npx as _uses_unpinned_npx,
)

_JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


class _ConfigValue(Protocol): ...


def _parse_json_value(value: _ConfigValue | None) -> JsonValue | None:
    if value is None:
        return None
    try:
        return _JSON_VALUE_ADAPTER.validate_python(value)
    except ValidationError:
        return None


class MCPCapabilityAdvisor:
    """Audit MCP configs and render latest-technology upgrade guidance."""

    def latest_capabilities(self) -> list[MCPCapability]:
        return _latest_capabilities()

    def load_config(self, path: str | Path) -> Mapping[str, JsonValue]:
        config_path = Path(path)
        if not config_path.exists():
            return {}
        parsed = _JSON_VALUE_ADAPTER.validate_json(config_path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def audit_config(
        self,
        config: Mapping[str, _ConfigValue] | None,
        source: str = "inline",
    ) -> MCPAuditReport:
        config = {} if config is None else config
        servers_value: JsonValue | None
        if "mcpServers" in config:
            servers_value = _parse_json_value(config["mcpServers"])
        else:
            servers_value = {}
        if not isinstance(servers_value, dict):
            return MCPAuditReport(
                source=source,
                servers_total=0,
                servers_ready=0,
                findings=[
                    MCPFinding(
                        "*",
                        "error",
                        "invalid_config",
                        "`mcpServers` must be an object.",
                        "Use a Claude/HF-compatible MCP config with `mcpServers`.",
                    ),
                ],
                capabilities=_latest_capabilities(),
            )

        servers = servers_value
        findings: list[MCPFinding] = []
        ready = 0
        for name, raw_server in servers.items():
            server = raw_server if isinstance(raw_server, Mapping) else {}
            server_findings = self._audit_server(str(name), server)
            findings.extend(server_findings)
            if not any(item.severity == "error" for item in server_findings):
                ready += 1

        if not servers:
            findings.append(
                MCPFinding(
                    "*",
                    "info",
                    "no_servers",
                    "No MCP servers are configured.",
                    "Use `/mcp template` to start with a guarded local/remote setup.",
                ),
            )

        return MCPAuditReport(
            source=source,
            servers_total=len(servers),
            servers_ready=ready,
            findings=findings,
            capabilities=_latest_capabilities(),
        )

    def _audit_server(self, name: str, server: Mapping[str, JsonValue]) -> list[MCPFinding]:
        findings: list[MCPFinding] = []
        transport = _transport_for(server)

        if transport not in {"stdio", "http", "streamable-http", "sse"}:
            findings.append(
                MCPFinding(
                    name,
                    "error",
                    "unknown_transport",
                    f"Unknown MCP transport `{transport}`.",
                    "Use `stdio`, `http`/`streamable-http`, or legacy `sse`.",
                ),
            )
            return findings

        if transport == "stdio":
            command = str(server.get("command", "")).strip()
            if not command:
                findings.append(
                    MCPFinding(
                        name,
                        "error",
                        "missing_command",
                        "stdio MCP server is missing `command`.",
                        "Set a fixed executable command and args.",
                    ),
                )
            args = _string_list(server.get("args", []))
            if _uses_unpinned_npx(command, args):
                findings.append(
                    MCPFinding(
                        name,
                        "warning",
                        "unpinned_npx_package",
                        "npx MCP server package is not pinned.",
                        "Pin package versions instead of using `@latest` or floating package names.",
                    ),
                )
        else:
            url = str(server.get("url", "") or server.get("endpoint", "")).strip()
            if not url:
                findings.append(
                    MCPFinding(
                        name,
                        "error",
                        "missing_url",
                        "Remote MCP server is missing `url`.",
                        "Set a single MCP endpoint URL such as `https://host/mcp`.",
                    ),
                )
            elif transport == "sse":
                findings.append(
                    MCPFinding(
                        name,
                        "warning",
                        "legacy_sse",
                        "SSE is supported for compatibility but is no longer the preferred transport.",
                        "Prefer Streamable HTTP (`type: http`) for new remote MCP servers.",
                    ),
                )

            auth_view = dict(server)
            auth_view["name"] = name
            if url and not _is_local_url(url) and not _has_auth(auth_view):
                findings.append(
                    MCPFinding(
                        name,
                        "error",
                        "remote_without_auth",
                        "Remote MCP server has no auth profile or Authorization header.",
                        "Use interactive OAuth 2.1 (/api/mcp/oauth) or API auth metadata before enabling remote tool execution.",
                    ),
                )

        if not server.get("trust_level"):
            findings.append(
                MCPFinding(
                    name,
                    "warning",
                    "missing_trust_level",
                    "MCP server has no trust label.",
                    "Set `trust_level` to local, verified, partner, or experimental.",
                ),
            )

        if not server.get("timeout_ms") and not server.get("timeout"):
            findings.append(
                MCPFinding(
                    name,
                    "warning",
                    "missing_timeout",
                    "MCP server has no timeout.",
                    "Set `timeout_ms` to prevent hung tool calls.",
                ),
            )

        if not server.get("tool_annotations") and not server.get("annotations"):
            findings.append(
                MCPFinding(
                    name,
                    "info",
                    "missing_tool_annotations",
                    "No declared tool annotation policy was found.",
                    "Prefer MCP tools that provide read-only/destructive/open-world annotations.",
                ),
            )

        return findings

    def render_markdown(self, report: MCPAuditReport) -> str:
        lines = [
            "# MCP Upgrade Radar",
            "",
            f"**Source:** `{report.source}`",
            f"**Servers:** {report.servers_ready}/{report.servers_total} ready",
            f"**Findings:** errors={report.blocking_count}, warnings={report.warning_count}",
            "",
            "## Latest Capability Matrix",
            "",
            "| Capability | Why it matters | Ssak-Ai action | Priority |",
            "| --- | --- | --- | --- |",
        ]
        for capability in report.capabilities:
            lines.append(
                "| "
                + " | ".join(
                    [
                        capability.name,
                        capability.why_it_matters,
                        capability.antigravity_action,
                        capability.priority,
                    ],
                )
                + " |",
            )

        lines.extend(["", "## Findings", ""])
        if not report.findings:
            lines.append("- No MCP config findings.")
        else:
            for finding in report.findings:
                lines.append(
                    f"- **{finding.severity.upper()} `{finding.code}`** ({finding.server}): {finding.message} → {finding.recommendation}",
                )

        lines.extend(["", "## Evidence Sources", ""])
        for capability in report.capabilities:
            lines.append(f"- **{capability.name}:** {capability.evidence_url}")

        return "\n".join(lines)

    def render_template(self) -> str:
        return _render_template()
