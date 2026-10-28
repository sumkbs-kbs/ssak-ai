import io
import json
import os
import uuid
from dataclasses import replace
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from tests.test_chat_structured_output_contract import product as product


@pytest.fixture(params=["lmstudio", "openrouter", "ollama"])
def compat_case(product, monkeypatch, request):
    from antigravity_k.api.routes import messages_api
    from antigravity_k.engine import provider_capability_probe_runtime
    from antigravity_k.engine.provider_adapters import inference_providers
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.tools import egress_policy

    client, body, _, _, _ = product
    client.app.include_router(messages_api.router)
    manager = client.contract_manager
    provider = request.param
    original = manager._registry.get_model(body["model"])
    assert original is not None
    name = "gemma4:compat" if provider == "ollama" else "contract-" + provider
    manager._registry._models[name] = replace(
        original,
        name=name,
        repo=name,
        provider=provider,
        api_base="http://127.0.0.1:19191/v1",
        api_key_env="COMPAT_CONTRACT_KEY",
    )
    monkeypatch.setenv("COMPAT_CONTRACT_KEY", "owned-fixture-key")
    metadata_terminal = provider_capability_probe_runtime._urlopen_provider
    assert metadata_terminal is not None

    def metadata(request, **kwargs):
        if provider == "lmstudio":
            assert request.full_url == "http://127.0.0.1:19191/v1/models"
            assert request.get_method() == "GET"
            return io.BytesIO(json.dumps({"data": [{"id": name}]}).encode())
        return metadata_terminal(request, **kwargs)

    monkeypatch.setattr(provider_capability_probe_runtime, "_urlopen_provider", metadata)
    body.update(model=name, agent_mode=False, max_tokens=128)
    body["messages"][0]["content"] = "안녕"
    state = {"wire": [], "usage": [], "persisted": [], "sleeps": [], "outcome": []}
    record = manager.tracker.record
    add = SessionManager.add_turn

    def terminal(_opener, target, **kwargs):
        state["wire"].append(
            {"url": target.full_url, "body": json.loads(target.data), "timeout": kwargs.get("timeout")}
        )
        outcome = state["outcome"][0]
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome) if isinstance(outcome, bytes) else outcome

    def record_usage(*args, **kwargs):
        state["usage"].append(kwargs)
        return record(*args, **kwargs)

    def add_turn(self, *args, **kwargs):
        state["persisted"].append(args)
        return add(self, *args, **kwargs)

    monkeypatch.setattr(inference_providers, "safe_urlopen", egress_policy.safe_urlopen)
    monkeypatch.setattr(egress_policy.urllib.request.OpenerDirector, "open", terminal)
    monkeypatch.setattr(egress_policy, "_retry_sleep", state["sleeps"].append)
    monkeypatch.setattr(manager.tracker, "record", record_usage)
    monkeypatch.setattr(SessionManager, "add_turn", add_turn)
    yield client, body, state, provider
    export = os.environ.get("COMPAT_CAPTURE_ROOT")
    if export:
        target = Path(export)
        target.mkdir(parents=True, exist_ok=True)
        (target / (uuid.uuid4().hex + ".json")).write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "wire": state["wire"],
                    "usage": state["usage"],
                    "persisted_turns": len(state["persisted"]),
                    "sleeps": state["sleeps"],
                },
                indent=2,
            )
        )


def fault(kind):
    if kind == "http503":
        return HTTPError(
            "http://127.0.0.1:19191/v1/chat/completions",
            503,
            "private endpoint",
            Message(),
            io.BytesIO(b"private body"),
        )
    if kind == "refused":
        return URLError(ConnectionRefusedError("private endpoint"))
    return TimeoutError("private timeout")


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize("kind,status", [("http503", 502), ("refused", 503), ("timeout", 504)])
def test_compatible_direct_transport_failure_once(compat_case, route, kind, status):
    client, body, state, _ = compat_case
    state["outcome"] = [fault(kind)]
    response = client.post(route, json=body)
    assert response.status_code == status, response.text
    payload = response.json()
    error = payload.get("detail", payload.get("error"))
    assert error["type"] == "provider_transport_error"
    assert error.get("upstream_status") == (503 if kind == "http503" else None)
    assert "private" not in response.text
    assert len(state["wire"]) == 1 and state["sleeps"] == []
    assert [r["success"] for r in state["usage"]] == [False]
    assert state["persisted"] == []


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize("kind", ["http503", "refused", "timeout"])
def test_compatible_stream_transport_failure_has_no_done(compat_case, route, kind):
    client, body, state, _ = compat_case
    state["outcome"] = [fault(kind)]
    response = client.post(route, json={**body, "stream": True})
    assert response.status_code == 200
    assert "provider_transport_error" in response.text and "private" not in response.text
    assert "[DONE]" not in response.text and "message_stop" not in response.text
    assert len(state["wire"]) == 1 and state["sleeps"] == []
    assert [r["success"] for r in state["usage"]] == [False]
    assert state["persisted"] == []


class InterruptedSSE(io.BytesIO):
    def __next__(self):
        line = self.readline()
        if line:
            return line
        raise TimeoutError("private partial failure")


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
def test_compatible_midstream_failure_is_not_success(compat_case, route):
    client, body, state, _ = compat_case
    state["outcome"] = [InterruptedSSE(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')]
    response = client.post(route, json={**body, "stream": True})
    assert "partial" in response.text and "provider_transport_error" in response.text
    assert "[DONE]" not in response.text and "message_stop" not in response.text
    assert [r["success"] for r in state["usage"]] == [False]
    assert len(state["wire"]) == 1 and state["persisted"] == []


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
def test_compatible_literal_error_prefix_is_normal_content(compat_case, route):
    client, body, state, provider = compat_case
    text = "[API Error] is the requested literal answer"
    if provider == "ollama":
        state["outcome"] = [json.dumps({"choices": [{"message": {"content": text}}]}).encode()]
    else:
        state["outcome"] = [
            b"data: " + json.dumps({"choices": [{"delta": {"content": text}}]}).encode() + b"\ndata: [DONE]\n"
        ]
    response = client.post(route, json=body)
    assert response.status_code == 200
    payload = response.json()
    actual = (
        payload["choices"][0]["message"]["content"] if route.endswith("completions") else payload["content"][0]["text"]
    )
    assert actual == text
    assert [r["success"] for r in state["usage"]] == [True]
    assert len(state["wire"]) == 1
