"""HTTP send boundaries shared by MCP transports and OAuth discovery/token requests."""

import os

import httpx

from .egress_policy import validate_egress_url, validate_httpx_request, validate_httpx_request_async


def _trust_environment() -> bool:
    # An environment proxy must not turn a permitted loopback URL into remote egress.
    return str(os.environ.get("AGK_EGRESS_LOCAL_ONLY", "")).strip().lower() not in {"1", "true", "yes", "on"}


def create_mcp_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """SDK-compatible factory; hooks also check SDK retries, redirects and SSE endpoints."""
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout if timeout is not None else httpx.Timeout(30.0, read=300.0),
        auth=auth,
        follow_redirects=False,
        trust_env=_trust_environment(),
        event_hooks={"request": [validate_httpx_request_async]},
    )


def mcp_http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json: object = None,
) -> httpx.Response:
    """Check before client construction and again before every redirect/send."""
    _ = validate_egress_url(url)
    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        trust_env=_trust_environment(),
        event_hooks={"request": [validate_httpx_request]},
    ) as client:
        return client.request(method, url, headers=headers, data=data, json=json)
