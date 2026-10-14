"""MCP server health cache.

Caches per-server initialize / list_tools outcomes (and failure reasons) so the
dashboard can show MCP health without re-probing on every poll.

Spec source: mcp_upgrade_report.md P2 + docs/BENCHMARK_UPGRADE_PLAN_2026-09.md §6.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Literal

logger = logging.getLogger("antigravity_k.mcp_health_cache")

HealthStatus = Literal["healthy", "error", "blocked", "configured", "unknown"]


@dataclass
class MCPServerHealthEntry:
    """Cached health snapshot for one MCP server."""

    name: str
    transport: str = "stdio"
    status: HealthStatus = "unknown"
    tool_count: int = 0
    tools: list[str] = field(default_factory=list)
    error: str | None = None
    initialized: bool = False
    checked_at: float | None = None
    latency_ms: float | None = None
    source: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "transport": self.transport,
            "status": self.status,
            "tool_count": self.tool_count,
            "tools": list(self.tools),
            "error": self.error,
            "initialized": self.initialized,
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
            "source": self.source,
            "command": self.command,
        }


class MCPHealthCache:
    """Thread-safe in-memory cache of MCP server health probes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, MCPServerHealthEntry] = {}

    def record_success(
        self,
        name: str,
        *,
        transport: str = "stdio",
        tools: list[str] | None = None,
        latency_ms: float | None = None,
        source: str = "",
        command: str = "",
    ) -> MCPServerHealthEntry:
        tool_names = list(tools or [])
        entry = MCPServerHealthEntry(
            name=name,
            transport=transport,
            status="healthy",
            tool_count=len(tool_names),
            tools=tool_names[:50],
            error=None,
            initialized=True,
            checked_at=time.time(),
            latency_ms=latency_ms,
            source=source,
            command=command,
        )
        with self._lock:
            self._entries[name] = entry
        return entry

    def record_failure(
        self,
        name: str,
        error: str,
        *,
        transport: str = "stdio",
        latency_ms: float | None = None,
        source: str = "",
        command: str = "",
        status: HealthStatus = "error",
    ) -> MCPServerHealthEntry:
        entry = MCPServerHealthEntry(
            name=name,
            transport=transport,
            status=status,
            tool_count=0,
            tools=[],
            error=error[:500] if error else "unknown error",
            initialized=False,
            checked_at=time.time(),
            latency_ms=latency_ms,
            source=source,
            command=command,
        )
        with self._lock:
            self._entries[name] = entry
        return entry

    def record_blocked(
        self,
        name: str,
        reason: str,
        *,
        transport: str = "stdio",
        source: str = "",
        command: str = "",
    ) -> MCPServerHealthEntry:
        return self.record_failure(
            name,
            reason,
            transport=transport,
            source=source,
            command=command,
            status="blocked",
        )

    def get(self, name: str) -> MCPServerHealthEntry | None:
        with self._lock:
            return self._entries.get(name)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def entries(self) -> list[MCPServerHealthEntry]:
        with self._lock:
            return list(self._entries.values())

    def snapshot(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.entries()]

    def summary(self, servers: list[dict[str, object]] | None = None) -> dict[str, int]:
        rows = servers if servers is not None else self.snapshot()
        counts: dict[str, int] = {
            "healthy": 0,
            "error": 0,
            "blocked": 0,
            "configured": 0,
            "unknown": 0,
            "total": len(rows),
        }
        for row in rows:
            status = str(row.get("status") or "unknown")
            if status not in counts:
                status = "unknown"
            counts[status] = counts.get(status, 0) + 1
        return counts

    def merge_with_configured(
        self,
        configured: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Merge live cache entries over configured server stubs."""
        with self._lock:
            cached = {name: entry.to_dict() for name, entry in self._entries.items()}

        merged: list[dict[str, object]] = []
        seen: set[str] = set()
        for cfg in configured:
            name = str(cfg.get("name") or "")
            if not name:
                continue
            seen.add(name)
            if name in cached:
                row = dict(cached[name])
                if not row.get("command") and cfg.get("command"):
                    row["command"] = cfg["command"]
                if not row.get("transport") and cfg.get("transport"):
                    row["transport"] = cfg["transport"]
                if not row.get("source") and cfg.get("source"):
                    row["source"] = cfg["source"]
                merged.append(row)
            else:
                merged.append(
                    {
                        "name": name,
                        "transport": str(cfg.get("transport") or "stdio"),
                        "status": "configured",
                        "tool_count": 0,
                        "tools": [],
                        "error": None,
                        "initialized": False,
                        "checked_at": None,
                        "latency_ms": None,
                        "source": str(cfg.get("source") or ""),
                        "command": str(cfg.get("command") or ""),
                    }
                )

        for name, row in cached.items():
            if name not in seen:
                merged.append(row)
        return merged


mcp_health_cache = MCPHealthCache()


def load_configured_mcp_servers() -> tuple[list[dict[str, object]], str]:
    """Load configured MCP servers from .mcp.json / AGK_MCP_CONFIG / skill registry.

    Returns (servers, source_path_or_label). Does not connect.
    """
    config_path = os.environ.get("AGK_MCP_CONFIG") or str(Path.cwd() / ".mcp.json")
    servers: list[dict[str, object]] = []

    try:
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as handle:
                raw = json.load(handle)
            mcp_servers = raw.get("mcpServers") if isinstance(raw, dict) else None
            if isinstance(mcp_servers, Mapping):
                for name, cfg in mcp_servers.items():
                    if not isinstance(cfg, Mapping):
                        continue
                    servers.append(_config_row(str(name), cfg, source=config_path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse MCP config %s: %s", config_path, exc)

    if servers:
        return servers, config_path

    try:
        registry = import_module("antigravity_k.tools.mcp_tool_loader").MCPServerRegistry()
        for sid, scfg in registry.get_skill_mcp_servers().items():
            servers.append(_config_row(sid, scfg, source="skill-registry"))
        if servers:
            return servers, "skill-registry"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Skill MCP registry unavailable: %s", exc)

    return servers, config_path


def _config_row(name: str, cfg: Mapping[str, object], *, source: str) -> dict[str, object]:
    url = str(cfg.get("url") or cfg.get("endpoint") or "")
    transport = str(cfg.get("transport") or cfg.get("type") or "").lower()
    if transport in {"streamable_http", "streamable-http"}:
        transport = "streamable-http"
    elif not transport:
        if url.startswith(("http://", "https://")):
            transport = "http"
        elif cfg.get("command"):
            transport = "stdio"
        else:
            transport = "unknown"
    command = str(cfg.get("command") or url or "")
    return {
        "name": name,
        "transport": transport,
        "status": "configured",
        "command": command,
        "source": source,
        "config": dict((str(k), v) for k, v in cfg.items()),
    }


def _transport_for(server: Mapping[str, object]) -> str:
    transport = str(server.get("transport") or server.get("type") or "").lower()
    if transport in {"streamable_http", "streamable-http"}:
        return "streamable-http"
    if transport:
        return transport
    if server.get("command"):
        return "stdio"
    if server.get("url") or server.get("endpoint"):
        return "http"
    return "unknown"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string_dict(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _as_mapping(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    return {}


def _timeout_seconds(config: Mapping[str, object], default: float = 15.0) -> float:
    if "timeout" in config:
        try:
            return float(str(config["timeout"]))
        except (TypeError, ValueError):
            return default
    if "timeout_ms" in config:
        try:
            return float(str(config["timeout_ms"])) / 1000.0
        except (TypeError, ValueError):
            return default
    return default


async def probe_configured_servers(
    *,
    timeout_cap: float = 20.0,
    cache: MCPHealthCache | None = None,
) -> list[dict[str, object]]:
    """Probe configured MCP servers (initialize + list_tools) and update the cache.

    Each server is connected in isolation and disconnected afterwards so probes
    do not leak sessions into the long-lived agent loader.
    """
    from antigravity_k.tools.mcp_session_manager import MCPSessionManager

    health = cache or mcp_health_cache
    configured, source_label = load_configured_mcp_servers()
    if not configured:
        return []

    advisor = import_module("antigravity_k.engine.mcp_capability").MCPCapabilityAdvisor()
    mcp_servers = {str(row["name"]): _as_mapping(row.get("config")) for row in configured if row.get("name")}
    audit = advisor.audit_config({"mcpServers": mcp_servers}, source=source_label)
    blocked = {finding.server: finding.message for finding in audit.findings if finding.severity == "error"}

    results: list[dict[str, object]] = []
    for row in configured:
        name = str(row["name"])
        cfg = _as_mapping(row.get("config"))
        transport = _transport_for(cfg) if cfg else str(row.get("transport") or "stdio")
        command = str(row.get("command") or "")

        if name in blocked:
            entry = health.record_blocked(
                name,
                blocked[name],
                transport=transport,
                source=source_label,
                command=command,
            )
            results.append(entry.to_dict())
            continue

        manager = MCPSessionManager()
        started = time.perf_counter()
        try:
            session = await _connect_for_probe(manager, name, cfg, transport, timeout_cap)
            list_tools = getattr(session, "list_tools")
            tools_response = await list_tools()
            raw_tools = getattr(tools_response, "tools", []) or []
            tool_names = [str(getattr(tool, "name", "") or "") for tool in raw_tools]
            tool_names = [t for t in tool_names if t]
            latency_ms = (time.perf_counter() - started) * 1000.0
            entry = health.record_success(
                name,
                transport=transport,
                tools=tool_names,
                latency_ms=round(latency_ms, 1),
                source=source_label,
                command=command,
            )
            results.append(entry.to_dict())
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - started) * 1000.0
            entry = health.record_failure(
                name,
                str(exc),
                transport=transport,
                latency_ms=round(latency_ms, 1),
                source=source_label,
                command=command,
            )
            results.append(entry.to_dict())
            logger.info("MCP health probe failed for %s: %s", name, exc)
        finally:
            try:
                await manager.cleanup()
            except Exception:  # noqa: BLE001
                logger.debug("MCP probe cleanup failed for %s", name, exc_info=True)

    return results


async def _connect_for_probe(
    manager: object,
    server_name: str,
    server_config: Mapping[str, object],
    transport: str,
    timeout_cap: float,
) -> object:
    timeout = min(_timeout_seconds(server_config, default=15.0), timeout_cap)
    connect_server = getattr(manager, "connect_server")
    connect_http = getattr(manager, "connect_streamable_http", None)
    connect_sse = getattr(manager, "connect_sse", None)

    if transport == "stdio":
        command = str(server_config.get("command", "")).strip()
        args = _string_list(server_config.get("args", []))
        env_raw = server_config.get("env")
        env = _string_dict(env_raw) if env_raw is not None else None
        return await connect_server(server_name, command, args, env)

    headers = _string_dict(server_config.get("headers", {}))
    url = str(server_config.get("url") or server_config.get("endpoint") or "")
    sse_read_timeout = min(_timeout_seconds(server_config, default=30.0), timeout_cap * 2)

    if transport in {"http", "streamable-http"}:
        if connect_http is None:
            raise ValueError("Streamable HTTP connect is unavailable on session manager")
        return await connect_http(
            server_name,
            url,
            headers=headers or None,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
        )
    if transport == "sse":
        if connect_sse is None:
            raise ValueError("SSE connect is unavailable on session manager")
        return await connect_sse(
            server_name,
            url,
            headers=headers or None,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
        )
    raise ValueError(f"Unsupported MCP transport: {transport}")
