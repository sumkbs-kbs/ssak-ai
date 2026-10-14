import re
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path

from pydantic import JsonValue


def transport_for(server: Mapping[str, JsonValue]) -> str:
    transport = str(server.get("transport") or server.get("type") or "").lower()
    if transport:
        if transport in {"streamable_http", "streamable-http"}:
            return "streamable-http"
        return transport
    if server.get("command"):
        return "stdio"
    if server.get("url") or server.get("endpoint"):
        return "http"
    return "unknown"


def has_auth(server: Mapping[str, JsonValue]) -> bool:
    if server.get("auth") or server.get("auth_profile"):
        return True
    headers = server.get("headers", {})
    if isinstance(headers, dict):
        if any(key.lower() == "authorization" for key in headers):
            return True
    name = server.get("name") or server.get("_name")
    if isinstance(name, str) and name:
        try:
            if import_module("antigravity_k.engine.mcp_oauth").has_stored_tokens(name):
                return True
        except Exception:
            pass
    return False


def is_local_url(url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def uses_unpinned_npx(command: str, args: list[str]) -> bool:
    if Path(command).name != "npx":
        return False
    joined = " ".join(args)
    if "@latest" in joined:
        return True
    package_args = [arg for arg in args if not arg.startswith("-")]
    for arg in package_args:
        if "/" in arg and not re.search(r"@[^/\s]+$", arg):
            return True
    return False


def string_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
