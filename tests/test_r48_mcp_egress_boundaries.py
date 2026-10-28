"""MCP send boundaries, exercised only with fake clients and in-memory transports."""

from __future__ import annotations

import asyncio
import builtins
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from antigravity_k.engine import mcp_health_cache as health
from antigravity_k.engine import mcp_oauth as oauth
from antigravity_k.engine import tool_policy
from antigravity_k.tools import mcp_session_manager as sessions
from antigravity_k.tools import mcp_tool_loader as loader
from antigravity_k.tools.egress_policy import EgressPolicyError


@pytest.mark.parametrize("failure", ["import", "evaluation"])
def test_unavailable_request_policy_denies_before_mcp_caller(monkeypatch, failure):
    called = MagicMock(return_value="ok")
    tool = loader.MCPTool("synthetic", "test", {}, server_name="synthetic", caller=called)
    if failure == "import":
        original = builtins.__import__

        def failed_import(name, *args, **kwargs):
            if name == "antigravity_k.engine.tool_policy":
                raise ImportError("synthetic policy unavailable")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", failed_import)
    else:
        monkeypatch.setattr(tool_policy, "mcp_server_policy_denial", MagicMock(side_effect=RuntimeError("unavailable")))

    result = tool.execute(query="synthetic")
    assert result.is_error
    assert result.error_code == "POLICY_DENIED"
    called.assert_not_called()


def test_mcp_arguments_and_exception_text_are_absent_from_logs(monkeypatch, caplog):
    secret = "synthetic-secret-DO-NOT-LOG"
    monkeypatch.setattr(tool_policy, "mcp_server_policy_denial", lambda *_: None)
    tool = loader.MCPTool("synthetic", "test", {}, server_name="synthetic", caller=MagicMock(return_value="ok"))
    with caplog.at_level(logging.INFO, logger=loader.__name__):
        assert tool.execute(query=secret) == "ok"
    assert secret not in caplog.text
    tool._caller = MagicMock(side_effect=ValueError(secret))
    with caplog.at_level(logging.INFO, logger=loader.__name__):
        assert tool.execute(query=secret).is_error
    assert secret not in caplog.text


def test_stdio_connection_logs_omit_arguments_and_exception_text(monkeypatch, caplog):
    secret = "synthetic-stdio-secret"
    stack = AsyncMock()
    stack.enter_async_context.side_effect = ValueError(secret)
    monkeypatch.setattr(sessions, "AsyncExitStack", lambda: stack)
    monkeypatch.setattr(sessions, "stdio_client", MagicMock())
    with caplog.at_level(logging.INFO, logger=sessions.__name__), pytest.raises(ValueError):
        asyncio.run(sessions.MCPSessionManager().connect_server("synthetic", "python", [secret]))
    assert secret not in caplog.text


@pytest.mark.parametrize("transport", ["streamable_http", "sse"])
def test_local_only_blocks_remote_mcp_before_sdk_factory(monkeypatch, transport):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    factory = MagicMock(side_effect=AssertionError("SDK factory must not run"))
    name = "streamablehttp_client" if transport == "streamable_http" else "sse_client"
    monkeypatch.setattr(sessions, name, factory)
    manager = sessions.MCPSessionManager()
    with pytest.raises(EgressPolicyError):
        asyncio.run(getattr(manager, "connect_" + transport)("synthetic", "https://mcp.example.com/mcp"))
    factory.assert_not_called()
    assert manager.exit_stacks == manager.session_loops == manager.sessions == {}


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_health_probe_reaches_same_remote_send_boundary(monkeypatch, transport):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    config = {
        "url": "https://mcp.example.com/mcp", "transport": transport,
        "headers": {"Authorization": "Bearer synthetic"},
    }
    monkeypatch.setattr(health, "load_configured_mcp_servers", lambda: ([{
        "name": "synthetic", "config": config, "transport": transport,
    }], "synthetic-config"))
    factory = MagicMock(side_effect=AssertionError("Probe must not reach SDK factory"))
    monkeypatch.setattr(sessions, "streamablehttp_client" if transport == "http" else "sse_client", factory)
    result = asyncio.run(health.probe_configured_servers(cache=health.MCPHealthCache()))
    assert len(result) == 1
    assert result[0]["status"] == "error"
    assert "EgressPolicyError" in result[0]["error"]
    factory.assert_not_called()


def test_loader_does_not_log_or_cache_raw_connection_exception(monkeypatch, caplog):
    secret = "synthetic-connection-secret"
    cache = MagicMock()
    monkeypatch.setattr(loader, "mcp_health_cache", cache)
    instance = loader.MCPToolLoader(config_path=None, include_system_tools=False, load_skill_servers=False)
    instance._connect_server = AsyncMock(side_effect=ValueError(secret))
    with caplog.at_level(logging.INFO, logger=loader.__name__):
        asyncio.run(instance._connect_and_load_servers({"synthetic": {"url": "http://127.0.0.1/mcp"}}, "synthetic-config"))
    assert secret not in caplog.text
    assert secret not in str(cache.record_failure.call_args)


def test_probe_does_not_log_or_cache_raw_connection_exception(monkeypatch, caplog):
    secret = "synthetic-probe-secret"
    config = {"url": "http://127.0.0.1/mcp"}
    monkeypatch.setattr(health, "load_configured_mcp_servers", lambda: ([{
        "name": "synthetic", "config": config, "transport": "http",
    }], "synthetic-config"))
    monkeypatch.setattr(sessions, "streamablehttp_client", MagicMock(side_effect=ValueError(secret)))
    with caplog.at_level(logging.INFO, logger=health.logger.name):
        result = asyncio.run(health.probe_configured_servers(cache=health.MCPHealthCache()))
    assert result[0]["status"] == "error"
    assert secret not in result[0]["error"]
    assert secret not in caplog.text


@pytest.mark.parametrize("transport", ["streamablehttp", "sse"])
def test_sdk_wrappers_pass_guarded_factory_and_auth_by_keyword(monkeypatch, transport):
    auth = MagicMock(spec=httpx.Auth)
    sdk = MagicMock()
    selector = "_legacy_streamable_http_client" if transport == "streamablehttp" else "_legacy_sse_client"
    monkeypatch.setattr(sessions, selector, lambda: sdk)
    getattr(sessions, transport + "_client")("http://127.0.0.1/mcp", auth=auth)
    assert sdk.call_args.args == ("http://127.0.0.1/mcp",)
    assert sdk.call_args.kwargs["auth"] is auth
    assert callable(sdk.call_args.kwargs["httpx_client_factory"])


@pytest.mark.parametrize("operation", ["get", "form", "register"])
def test_oauth_local_only_denies_before_http_factory(monkeypatch, operation):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    factory = MagicMock(side_effect=AssertionError("HTTP factory must not run"))
    monkeypatch.setattr(httpx, "Client", factory)
    monkeypatch.setattr(httpx, "get", factory)
    monkeypatch.setattr(httpx, "post", factory)
    if operation == "get":
        with pytest.raises(EgressPolicyError):
            oauth._default_http_get("https://auth.example.com/metadata")
    elif operation == "form":
        with pytest.raises(EgressPolicyError):
            oauth._default_http_post_form("https://auth.example.com/token", {"refresh_token": "synthetic"})
    else:
        with pytest.raises(oauth.MCPOAuthError):
            oauth._resolve_client_id({}, {"registration_endpoint": "https://auth.example.com/register"}, "http://127.0.0.1/cb")
    factory.assert_not_called()


def _pending():
    return oauth.PendingAuth(
        state="synthetic-state", server_name="synthetic", resource="http://127.0.0.1/mcp",
        redirect_uri="http://127.0.0.1/cb", client_id="synthetic", code_verifier="synthetic",
        authorization_endpoint="http://127.0.0.1/authorize", token_endpoint="https://auth.example.com/token",
        authorization_server="http://127.0.0.1",
    )


def test_injected_discovery_cannot_bypass_local_only(monkeypatch):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    getter = MagicMock(side_effect=AssertionError("No injected sender may run"))
    with pytest.raises(oauth.MCPOAuthError):
        oauth.discover_protected_resource_metadata("https://mcp.example.com/mcp", http_get=getter)
    with pytest.raises(oauth.MCPOAuthError):
        oauth.discover_authorization_server_metadata("https://auth.example.com", http_get=getter)
    getter.assert_not_called()


def test_injected_token_exchange_and_refresh_cannot_bypass_local_only(monkeypatch):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    poster = MagicMock(side_effect=AssertionError("No token sender may run"))
    store = oauth.PendingAuthStore()
    store.put(_pending())
    with pytest.raises(oauth.MCPOAuthError):
        oauth.complete_authorization(code="synthetic", state="synthetic-state", store=store, http_post_form=poster)
    monkeypatch.setattr(oauth, "load_token_set", lambda _: oauth.OAuthTokenSet(
        access_token="synthetic", refresh_token="synthetic", expires_at=time.time()-100,
        client_id="synthetic", token_endpoint="https://auth.example.com/token",
    ))
    assert oauth.refresh_tokens("synthetic", http_post_form=poster) is None
    poster.assert_not_called()


def test_remote_authorization_endpoint_is_not_returned_in_local_only_mode(monkeypatch):
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    monkeypatch.setattr(oauth, "discover_protected_resource_metadata", lambda *_a, **_kw: {
        "authorization_servers": ["http://127.0.0.1"],
    })
    monkeypatch.setattr(oauth, "discover_authorization_server_metadata", lambda *_a, **_kw: {
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "http://127.0.0.1/token", "code_challenge_methods_supported": ["S256"],
    })
    store = oauth.PendingAuthStore()
    with pytest.raises(oauth.MCPOAuthError):
        oauth.start_authorization("synthetic", {"url": "http://127.0.0.1/mcp", "auth": {"client_id": "synthetic"}}, store=store)
    assert store._items == {}


def test_oauth_refresh_response_and_discovery_errors_do_not_log_secrets(monkeypatch, caplog):
    secret = "synthetic-oauth-secret"
    monkeypatch.setattr(oauth, "load_token_set", lambda _: oauth.OAuthTokenSet(
        access_token="synthetic", refresh_token="synthetic", expires_at=time.time()-100,
        client_id="synthetic", token_endpoint="http://127.0.0.1/token",
    ))
    with caplog.at_level(logging.DEBUG, logger=oauth.logger.name):
        assert oauth.refresh_tokens("synthetic", http_post_form=lambda *_: httpx.Response(400, text=secret)) is None
        with pytest.raises(oauth.MCPOAuthError):
            oauth.discover_protected_resource_metadata("http://127.0.0.1/mcp", http_get=MagicMock(side_effect=ValueError(secret)))
    assert secret not in caplog.text


@pytest.mark.parametrize("asynchronous", [False, True])
def test_http_send_hook_blocks_redirect_without_second_send(monkeypatch, asynchronous):
    from antigravity_k.tools import mcp_http_policy

    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", "1")
    sent = []

    def respond(request):
        sent.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://remote.example.com/token"})

    transport = httpx.MockTransport(respond)
    if asynchronous:
        original = httpx.AsyncClient

        def fake_client(**kwargs):
            assert kwargs["trust_env"] is False
            return original(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", fake_client)

        async def run():
            async with mcp_http_policy.create_mcp_http_client() as client:
                await client.get("http://127.0.0.1/metadata", follow_redirects=True)

        with pytest.raises(EgressPolicyError):
            asyncio.run(run())
    else:
        original = httpx.Client

        def fake_client(**kwargs):
            assert kwargs["trust_env"] is False
            return original(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "Client", fake_client)
        with pytest.raises(EgressPolicyError):
            mcp_http_policy.mcp_http_request("GET", "http://127.0.0.1/metadata")
    assert sent == ["http://127.0.0.1/metadata"]


def test_authorized_public_and_local_requests_keep_working_without_local_only(monkeypatch):
    from antigravity_k.tools import egress_policy, mcp_http_policy

    monkeypatch.delenv("AGK_EGRESS_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(egress_policy, "resolve_public_http_url_sync", lambda url: url)
    sent = []

    def respond(request):
        sent.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    assert mcp_http_policy.mcp_http_request("GET", "https://mcp.example.com/metadata").json() == {"ok": True}
    assert mcp_http_policy.mcp_http_request("GET", "http://127.0.0.1/metadata").status_code == 200
    assert len(sent) == 2
