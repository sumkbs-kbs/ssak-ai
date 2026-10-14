"""MCP OAuth 2.1 interactive authorization (authorization code + PKCE).

Implements the client side of the MCP Authorization spec for HTTP-based
transports: Protected Resource Metadata discovery, Authorization Server
metadata discovery, PKCE (S256), resource indicators (RFC 8707), token
exchange/refresh, and encrypted token persistence via ``secure_key`` vault.

Spec sources:
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- mcp_upgrade_report.md P1 / docs/BENCHMARK_UPGRADE_PLAN_2026-09.md §6
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger("antigravity_k.mcp_oauth")

_VAULT_PREFIX: Final[str] = "mcp_oauth:"
_DEFAULT_CLIENT_NAME: Final[str] = "Ssak-Ai MCP Client"
_PENDING_TTL_SECONDS: Final[float] = 600.0
_HTTP_TIMEOUT: Final[float] = 20.0

HttpGet = Callable[[str, dict[str, str] | None], httpx.Response]
HttpPostForm = Callable[[str, dict[str, str], dict[str, str] | None], httpx.Response]


class MCPOAuthError(Exception):
    """Raised when an OAuth step fails with a user-visible reason."""


@dataclass
class OAuthTokenSet:
    """Persisted OAuth tokens for one MCP server (never returned raw to UI)."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_at: float | None = None
    scope: str | None = None
    resource: str | None = None
    client_id: str | None = None
    authorization_server: str | None = None
    token_endpoint: str | None = None
    obtained_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "resource": self.resource,
            "client_id": self.client_id,
            "authorization_server": self.authorization_server,
            "token_endpoint": self.token_endpoint,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OAuthTokenSet:
        expires_at = data.get("expires_at")
        expires_val: float | None
        if expires_at is None:
            expires_val = None
        else:
            expires_val = float(expires_at)
        return cls(
            access_token=str(data["access_token"]),
            token_type=str(data.get("token_type") or "Bearer"),
            refresh_token=(str(data["refresh_token"]) if data.get("refresh_token") else None),
            expires_at=expires_val,
            scope=(str(data["scope"]) if data.get("scope") else None),
            resource=(str(data["resource"]) if data.get("resource") else None),
            client_id=(str(data["client_id"]) if data.get("client_id") else None),
            authorization_server=(str(data["authorization_server"]) if data.get("authorization_server") else None),
            token_endpoint=(str(data["token_endpoint"]) if data.get("token_endpoint") else None),
            obtained_at=float(data.get("obtained_at") or time.time()),
        )

    def is_expired(self, *, skew_seconds: float = 60.0) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - skew_seconds)

    def public_status(self, server_name: str) -> dict[str, Any]:
        return {
            "server_name": server_name,
            "connected": bool(self.access_token),
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "resource": self.resource,
            "has_refresh_token": bool(self.refresh_token),
            "obtained_at": self.obtained_at,
            "expired": self.is_expired(),
        }


@dataclass
class PendingAuth:
    """In-flight authorization code + PKCE session keyed by ``state``."""

    state: str
    server_name: str
    resource: str
    redirect_uri: str
    client_id: str
    code_verifier: str
    authorization_endpoint: str
    token_endpoint: str
    authorization_server: str
    scope: str | None = None
    created_at: float = field(default_factory=time.time)
    client_secret: str | None = None

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > _PENDING_TTL_SECONDS


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def canonical_resource_uri(url: str) -> str:
    """Normalize MCP server URL for the OAuth ``resource`` parameter (RFC 8707)."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise MCPOAuthError(f"Invalid MCP resource URL: {url!r}")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def parse_www_authenticate(header: str) -> dict[str, str]:
    """Parse a Bearer WWW-Authenticate challenge into key/value params."""
    result: dict[str, str] = {}
    if not header:
        return result
    # Strip scheme prefix if present.
    value = header.strip()
    if value.lower().startswith("bearer"):
        value = value[6:].lstrip()
    for part in value.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, raw = part.partition("=")
        result[key.strip().lower()] = raw.strip().strip('"')
    return result


def _vault_service_name(server_name: str) -> str:
    return f"{_VAULT_PREFIX}{server_name.strip()}"


def load_token_set(server_name: str) -> OAuthTokenSet | None:
    """Load encrypted tokens for ``server_name`` from the secure_key vault."""
    from antigravity_k.engine.secure_key import get_api_key

    raw = get_api_key(_vault_service_name(server_name))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "access_token" not in data:
            return None
        return OAuthTokenSet.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Corrupt MCP OAuth token blob for %s", server_name)
        return None


def save_token_set(server_name: str, tokens: OAuthTokenSet) -> bool:
    """Persist tokens encrypted via secure_key vault."""
    from antigravity_k.engine.secure_key import store_api_key

    return store_api_key(_vault_service_name(server_name), json.dumps(tokens.to_dict()))


def delete_token_set(server_name: str) -> bool:
    """Remove stored tokens for ``server_name``."""
    from antigravity_k.engine.secure_key import remove_api_key

    return remove_api_key(_vault_service_name(server_name))


def has_stored_tokens(server_name: str) -> bool:
    tokens = load_token_set(server_name)
    return tokens is not None and bool(tokens.access_token)


class PendingAuthStore:
    """Thread-safe in-memory store for pending PKCE authorizations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, PendingAuth] = {}

    def put(self, pending: PendingAuth) -> None:
        with self._lock:
            self._purge_locked()
            self._items[pending.state] = pending

    def pop(self, state: str) -> PendingAuth | None:
        with self._lock:
            self._purge_locked()
            return self._items.pop(state, None)

    def get(self, state: str) -> PendingAuth | None:
        with self._lock:
            self._purge_locked()
            return self._items.get(state)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _purge_locked(self) -> None:
        expired = [key for key, item in self._items.items() if item.is_expired()]
        for key in expired:
            del self._items[key]


pending_auth_store = PendingAuthStore()


def _default_http_get(url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.get(url, headers=headers, timeout=_HTTP_TIMEOUT, follow_redirects=True)


def _default_http_post_form(
    url: str,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    merged = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    return httpx.post(url, data=data, headers=merged, timeout=_HTTP_TIMEOUT, follow_redirects=True)


def _auth_config(server_config: Mapping[str, object]) -> dict[str, object]:
    auth = server_config.get("auth") or server_config.get("auth_profile")
    if isinstance(auth, Mapping):
        return {str(k): v for k, v in auth.items()}
    if isinstance(auth, str) and auth.strip():
        return {"type": auth.strip()}
    return {}


def _server_url(server_config: Mapping[str, object]) -> str:
    return str(server_config.get("url") or server_config.get("endpoint") or "").strip()


def discover_protected_resource_metadata(
    mcp_url: str,
    *,
    www_authenticate: str | None = None,
    http_get: HttpGet | None = None,
) -> dict[str, Any]:
    """Fetch OAuth Protected Resource Metadata (RFC 9728) for an MCP URL."""
    getter = http_get or _default_http_get
    candidates: list[str] = []

    if www_authenticate:
        params = parse_www_authenticate(www_authenticate)
        meta = params.get("resource_metadata")
        if meta:
            candidates.append(meta)

    parsed = urlparse(mcp_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = (parsed.path or "").rstrip("/")
    if path:
        candidates.append(f"{origin}/.well-known/oauth-protected-resource{path}")
    candidates.append(f"{origin}/.well-known/oauth-protected-resource")

    last_error: str | None = None
    for candidate in candidates:
        try:
            response = getter(candidate, {"Accept": "application/json"})
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return data
            last_error = f"{candidate} -> HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{candidate} -> {exc}"
            logger.debug("PRM probe failed: %s", last_error)

    raise MCPOAuthError(
        "Could not discover Protected Resource Metadata" + (f" ({last_error})" if last_error else ""),
    )


def discover_authorization_server_metadata(
    issuer: str,
    *,
    http_get: HttpGet | None = None,
) -> dict[str, Any]:
    """Discover AS metadata via RFC8414 / OIDC well-known endpoints."""
    getter = http_get or _default_http_get
    issuer = issuer.rstrip("/")
    parsed = urlparse(issuer)
    if not parsed.scheme or not parsed.netloc:
        raise MCPOAuthError(f"Invalid authorization server issuer: {issuer!r}")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = (parsed.path or "").rstrip("/")
    candidates: list[str] = []
    if path:
        candidates.append(f"{origin}/.well-known/oauth-authorization-server{path}")
        candidates.append(f"{origin}/.well-known/openid-configuration{path}")
        candidates.append(f"{issuer}/.well-known/openid-configuration")
    else:
        candidates.append(f"{origin}/.well-known/oauth-authorization-server")
        candidates.append(f"{origin}/.well-known/openid-configuration")

    last_error: str | None = None
    for candidate in candidates:
        try:
            response = getter(candidate, {"Accept": "application/json"})
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("authorization_endpoint") and data.get("token_endpoint"):
                    return data
            last_error = f"{candidate} -> HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{candidate} -> {exc}"
            logger.debug("AS metadata probe failed: %s", last_error)

    raise MCPOAuthError(
        "Could not discover Authorization Server metadata" + (f" ({last_error})" if last_error else ""),
    )


def _require_pkce_support(as_metadata: Mapping[str, Any]) -> None:
    methods = as_metadata.get("code_challenge_methods_supported")
    if not isinstance(methods, list) or not methods:
        raise MCPOAuthError(
            "Authorization server does not advertise PKCE "
            "(code_challenge_methods_supported missing); refusing OAuth 2.1 flow.",
        )
    normalized = {str(m).upper() for m in methods}
    if "S256" not in normalized:
        raise MCPOAuthError(
            f"Authorization server PKCE methods {sorted(normalized)} do not include S256.",
        )


def _select_scopes(
    auth_cfg: Mapping[str, object],
    prm: Mapping[str, Any],
    www_authenticate: str | None,
) -> str | None:
    if auth_cfg.get("scopes"):
        scopes = auth_cfg["scopes"]
        if isinstance(scopes, list):
            return " ".join(str(s) for s in scopes)
        return str(scopes)
    if www_authenticate:
        scope = parse_www_authenticate(www_authenticate).get("scope")
        if scope:
            return scope
    supported = prm.get("scopes_supported")
    if isinstance(supported, list) and supported:
        return " ".join(str(s) for s in supported)
    return None


def _pick_authorization_server(prm: Mapping[str, Any], auth_cfg: Mapping[str, object]) -> str:
    override = auth_cfg.get("authorization_server") or auth_cfg.get("issuer")
    if override:
        return str(override).rstrip("/")
    servers = prm.get("authorization_servers")
    if isinstance(servers, list) and servers:
        return str(servers[0]).rstrip("/")
    raise MCPOAuthError("Protected Resource Metadata has no authorization_servers.")


def _resolve_client_id(
    auth_cfg: Mapping[str, object],
    as_metadata: Mapping[str, Any],
    redirect_uri: str,
    *,
    http_post_form: HttpPostForm | None = None,
) -> tuple[str, str | None]:
    """Return (client_id, client_secret) via pre-reg or Dynamic Client Registration."""
    if auth_cfg.get("client_id"):
        secret = auth_cfg.get("client_secret")
        return str(auth_cfg["client_id"]), (str(secret) if secret else None)

    registration_endpoint = as_metadata.get("registration_endpoint")
    if not registration_endpoint:
        raise MCPOAuthError(
            "No client_id configured and authorization server has no registration_endpoint. "
            "Set auth.client_id in .mcp.json or use an AS that supports Dynamic Client Registration.",
        )

    _ = http_post_form  # reserved for injectable clients in tests
    client_name = str(auth_cfg.get("client_name") or _DEFAULT_CLIENT_NAME)
    # RFC7591 expects JSON body; use httpx directly for JSON registration.
    try:
        response = httpx.post(
            str(registration_endpoint),
            json={
                "client_name": client_name,
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
            headers={"Accept": "application/json"},
            timeout=_HTTP_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise MCPOAuthError(f"Dynamic client registration failed: {exc}") from exc

    if response.status_code not in {200, 201}:
        raise MCPOAuthError(
            f"Dynamic client registration failed: HTTP {response.status_code} {response.text[:200]}",
        )
    data = response.json()
    if not isinstance(data, dict) or not data.get("client_id"):
        raise MCPOAuthError("Dynamic client registration response missing client_id.")
    client_secret = data.get("client_secret")
    return str(data["client_id"]), (str(client_secret) if client_secret else None)


def build_default_redirect_uri(request_base: str | None = None) -> str:
    """Build localhost callback URL used by the dashboard OAuth flow."""
    if request_base:
        base = request_base.rstrip("/")
        return f"{base}/api/mcp/oauth/callback"
    host = "127.0.0.1"
    port = 8000
    try:
        from antigravity_k.config import config as app_config

        host = app_config.server.host or host
        # These wildcard values are replaced with loopback, never used for binding.
        if host in {"0.0.0.0", "::"}:  # nosec B104
            host = "127.0.0.1"
        port = int(app_config.server.port)
    except Exception:  # noqa: BLE001
        pass
    return f"http://{host}:{port}/api/mcp/oauth/callback"


def start_authorization(
    server_name: str,
    server_config: Mapping[str, object],
    *,
    redirect_uri: str | None = None,
    client_id: str | None = None,
    www_authenticate: str | None = None,
    http_get: HttpGet | None = None,
    store: PendingAuthStore | None = None,
) -> dict[str, Any]:
    """Start OAuth 2.1 authorization-code + PKCE for an MCP server.

    Returns a dict with ``authorization_url``, ``state``, and public metadata.
    """
    url = _server_url(server_config)
    if not url.startswith(("http://", "https://")):
        raise MCPOAuthError("OAuth is only supported for HTTP/SSE MCP servers with a url.")

    auth_cfg = _auth_config(server_config)
    if client_id:
        auth_cfg = {**auth_cfg, "client_id": client_id}

    resource = canonical_resource_uri(url)
    prm = discover_protected_resource_metadata(
        url,
        www_authenticate=www_authenticate,
        http_get=http_get,
    )
    issuer = _pick_authorization_server(prm, auth_cfg)
    as_metadata = discover_authorization_server_metadata(issuer, http_get=http_get)
    _require_pkce_support(as_metadata)

    redirect = redirect_uri or build_default_redirect_uri()
    resolved_client_id, client_secret = _resolve_client_id(auth_cfg, as_metadata, redirect)
    scope = _select_scopes(auth_cfg, prm, www_authenticate)
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    authorization_endpoint = str(as_metadata["authorization_endpoint"])
    token_endpoint = str(as_metadata["token_endpoint"])

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": resolved_client_id,
        "redirect_uri": redirect,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    if scope:
        params["scope"] = scope

    authorization_url = authorization_endpoint
    sep = "&" if "?" in authorization_endpoint else "?"
    authorization_url = f"{authorization_endpoint}{sep}{urlencode(params)}"

    pending = PendingAuth(
        state=state,
        server_name=server_name,
        resource=resource,
        redirect_uri=redirect,
        client_id=resolved_client_id,
        code_verifier=verifier,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        authorization_server=issuer,
        scope=scope,
        client_secret=client_secret,
    )
    (store or pending_auth_store).put(pending)

    return {
        "ok": True,
        "server_name": server_name,
        "authorization_url": authorization_url,
        "state": state,
        "redirect_uri": redirect,
        "resource": resource,
        "authorization_server": issuer,
        "scope": scope,
        "client_id": resolved_client_id,
        "expires_in_seconds": int(_PENDING_TTL_SECONDS),
    }


def complete_authorization(
    *,
    code: str,
    state: str,
    http_post_form: HttpPostForm | None = None,
    store: PendingAuthStore | None = None,
) -> dict[str, Any]:
    """Exchange authorization ``code`` + PKCE verifier for tokens and persist them."""
    if not code or not state:
        raise MCPOAuthError("Missing authorization code or state.")

    pending = (store or pending_auth_store).pop(state)
    if pending is None:
        raise MCPOAuthError("Unknown or expired OAuth state. Start the flow again.")
    if pending.is_expired():
        raise MCPOAuthError("OAuth authorization session expired. Start the flow again.")

    poster = http_post_form or _default_http_post_form
    form: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending.redirect_uri,
        "client_id": pending.client_id,
        "code_verifier": pending.code_verifier,
        "resource": pending.resource,
    }
    if pending.client_secret:
        form["client_secret"] = pending.client_secret

    try:
        response = poster(pending.token_endpoint, form, {"Accept": "application/json"})
    except Exception as exc:  # noqa: BLE001
        raise MCPOAuthError(f"Token exchange request failed: {exc}") from exc

    if response.status_code != 200:
        raise MCPOAuthError(
            f"Token exchange failed: HTTP {response.status_code} {response.text[:300]}",
        )

    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise MCPOAuthError(f"Token response was not JSON: {exc}") from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise MCPOAuthError("Token response missing access_token.")

    expires_in = payload.get("expires_in")
    expires_at: float | None = None
    if expires_in is not None:
        try:
            expires_at = time.time() + float(expires_in)
        except (TypeError, ValueError):
            expires_at = None

    tokens = OAuthTokenSet(
        access_token=str(payload["access_token"]),
        token_type=str(payload.get("token_type") or "Bearer"),
        refresh_token=(str(payload["refresh_token"]) if payload.get("refresh_token") else None),
        expires_at=expires_at,
        scope=(str(payload.get("scope") or pending.scope) if (payload.get("scope") or pending.scope) else None),
        resource=pending.resource,
        client_id=pending.client_id,
        authorization_server=pending.authorization_server,
        token_endpoint=pending.token_endpoint,
    )
    if not save_token_set(pending.server_name, tokens):
        raise MCPOAuthError("Failed to persist OAuth tokens in encrypted vault.")

    return {
        "ok": True,
        "server_name": pending.server_name,
        "connected": True,
        "status": tokens.public_status(pending.server_name),
    }


def refresh_tokens(
    server_name: str,
    *,
    http_post_form: HttpPostForm | None = None,
) -> OAuthTokenSet | None:
    """Refresh access token when expired; return updated set or None on failure."""
    current = load_token_set(server_name)
    if current is None:
        return None
    if not current.is_expired():
        return current
    if not current.refresh_token or not current.token_endpoint or not current.client_id:
        return current if not current.is_expired() else None

    poster = http_post_form or _default_http_post_form
    form: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": current.refresh_token,
        "client_id": current.client_id,
    }
    if current.resource:
        form["resource"] = current.resource

    try:
        response = poster(current.token_endpoint, form, {"Accept": "application/json"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP OAuth refresh failed for %s: %s", server_name, exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "MCP OAuth refresh HTTP %s for %s: %s",
            response.status_code,
            server_name,
            response.text[:200],
        )
        return None

    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        return None

    expires_in = payload.get("expires_in")
    expires_at: float | None = None
    if expires_in is not None:
        try:
            expires_at = time.time() + float(expires_in)
        except (TypeError, ValueError):
            expires_at = None

    updated = OAuthTokenSet(
        access_token=str(payload["access_token"]),
        token_type=str(payload.get("token_type") or current.token_type),
        refresh_token=(str(payload["refresh_token"]) if payload.get("refresh_token") else current.refresh_token),
        expires_at=expires_at if expires_at is not None else current.expires_at,
        scope=(str(payload["scope"]) if payload.get("scope") else current.scope),
        resource=current.resource,
        client_id=current.client_id,
        authorization_server=current.authorization_server,
        token_endpoint=current.token_endpoint,
    )
    save_token_set(server_name, updated)
    return updated


def get_authorization_header(server_name: str) -> str | None:
    """Return ``Authorization`` header value for an MCP server, refreshing if needed."""
    tokens = refresh_tokens(server_name) or load_token_set(server_name)
    if tokens is None or not tokens.access_token:
        return None
    if tokens.is_expired() and not tokens.refresh_token:
        return None
    scheme = tokens.token_type or "Bearer"
    if scheme.lower() == "bearer":
        scheme = "Bearer"
    return f"{scheme} {tokens.access_token}"


def revoke_authorization(server_name: str) -> dict[str, Any]:
    """Delete stored tokens for ``server_name``."""
    deleted = delete_token_set(server_name)
    return {"ok": True, "server_name": server_name, "revoked": deleted, "connected": False}


def oauth_status_for_configured(
    configured: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Build dashboard status for configured MCP servers (HTTP only highlighted)."""
    from antigravity_k.engine.mcp_health_cache import load_configured_mcp_servers

    rows: Sequence[Mapping[str, object]]
    if configured is None:
        rows, source = load_configured_mcp_servers()
    else:
        rows = configured
        source = "inline"

    servers: list[dict[str, Any]] = []
    connected = 0
    for row in rows:
        name = str(row.get("name") or "")
        if not name:
            continue
        transport = str(row.get("transport") or "stdio")
        cfg = row.get("config")
        config_map: dict[str, object] = {}
        if isinstance(cfg, Mapping):
            config_map = {str(k): v for k, v in cfg.items()}
        url = _server_url(config_map) or str(row.get("command") or "")
        supports_oauth = transport in {"http", "streamable-http", "sse"} or url.startswith(
            ("http://", "https://"),
        )
        auth_cfg = _auth_config(config_map)
        tokens = load_token_set(name) if supports_oauth else None
        entry: dict[str, Any] = {
            "name": name,
            "transport": transport,
            "url": url if supports_oauth else "",
            "supports_oauth": supports_oauth,
            "auth_type": str(auth_cfg.get("type") or ("oauth" if tokens else "")),
            "connected": bool(tokens and tokens.access_token),
            "has_client_id": bool(auth_cfg.get("client_id")),
            "status": None,
        }
        if tokens:
            entry["status"] = tokens.public_status(name)
            if entry["connected"]:
                connected += 1
        servers.append(entry)

    return {
        "ok": True,
        "servers": servers,
        "source": source,
        "summary": {
            "total": len(servers),
            "oauth_capable": sum(1 for s in servers if s["supports_oauth"]),
            "connected": connected,
        },
    }


def merge_oauth_headers(
    server_name: str,
    headers: dict[str, str] | None,
) -> dict[str, str]:
    """Merge stored OAuth Bearer token into request headers if Authorization absent."""
    merged = dict(headers or {})
    if any(key.lower() == "authorization" for key in merged):
        return merged
    auth_header = get_authorization_header(server_name)
    if auth_header:
        merged["Authorization"] = auth_header
    return merged


def callback_html(*, ok: bool, server_name: str = "", message: str = "") -> str:
    """Minimal HTML page shown after browser redirect callback."""
    title = "MCP OAuth 연결 완료" if ok else "MCP OAuth 연결 실패"
    color = "#10b981" if ok else "#ef4444"
    detail = message or (
        f"서버 <strong>{server_name}</strong> 인증이 완료되었습니다. 이 창을 닫고 대시보드로 돌아가세요."
        if ok
        else "인증에 실패했습니다. 대시보드에서 다시 시도하세요."
    )
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><title>{title}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e8eaf0;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{background:#1a1d27;border:1px solid #2a2f3d;border-radius:12px;padding:28px 32px;
max-width:420px;text-align:center;box-shadow:0 8px 32px #0006}}
h1{{font-size:18px;margin:0 0 12px;color:{color}}}
p{{font-size:13px;line-height:1.5;color:#a0a4b8;margin:0}}
</style></head><body><div class="card"><h1>{title}</h1><p>{detail}</p></div>
<script>try{{window.opener&&window.opener.postMessage({{type:'mcp-oauth',ok:{str(ok).lower()},
server:'{server_name}'}},'*');}}catch(e){{}}
setTimeout(function(){{try{{window.close();}}catch(e){{}}}},1500);</script>
</body></html>"""


# Re-export helpers used by audits / capability checks.
__all__ = [
    "MCPOAuthError",
    "OAuthTokenSet",
    "PendingAuth",
    "PendingAuthStore",
    "build_default_redirect_uri",
    "callback_html",
    "canonical_resource_uri",
    "complete_authorization",
    "delete_token_set",
    "discover_authorization_server_metadata",
    "discover_protected_resource_metadata",
    "generate_pkce_pair",
    "get_authorization_header",
    "has_stored_tokens",
    "load_token_set",
    "merge_oauth_headers",
    "oauth_status_for_configured",
    "parse_www_authenticate",
    "pending_auth_store",
    "refresh_tokens",
    "revoke_authorization",
    "save_token_set",
    "start_authorization",
]
