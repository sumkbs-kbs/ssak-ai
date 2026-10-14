from __future__ import annotations

import io
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import replace
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from tests.test_chat_structured_output_contract import product as product


@pytest.fixture
def transport_case(product, monkeypatch, request):
    from antigravity_k.api.routes import messages_api
    from antigravity_k.engine.provider_adapters import inference_providers
    from antigravity_k.engine.session_manager import SessionManager

    client, body, _, _, _ = product
    client.app.include_router(messages_api.router)
    manager = client.contract_manager
    records = []
    persistence = []
    attempts = []
    outcome = ["ok"]
    original_record = manager.tracker.record
    original_add = SessionManager.add_turn

    def record(*args, **kwargs):
        records.append(kwargs)
        return original_record(*args, **kwargs)

    def add(self, *args, **kwargs):
        persistence.append(args)
        return original_add(self, *args, **kwargs)

    def terminal(request, **kwargs):
        attempts.append(request.full_url)
        if isinstance(outcome[0], Exception):
            raise outcome[0]
        return io.BytesIO(json.dumps({"message": {"content": outcome[0]}, "done": True}).encode())

    monkeypatch.setattr(manager.tracker, "record", record)
    monkeypatch.setattr(SessionManager, "add_turn", add)
    monkeypatch.setattr(inference_providers, "safe_urlopen", terminal)
    body["messages"][0]["content"] = "안녕"
    body["agent_mode"] = False
    body["max_tokens"] = 128
    yield client, body, records, persistence, attempts, outcome
    export = os.environ.get("TRANSPORT_CAPTURE_ROOT")
    if export:
        target = Path(export)
        target.mkdir(parents=True, exist_ok=True)
        (target / (uuid.uuid4().hex + ".json")).write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "native_attempts": attempts,
                    "usage": records,
                    "persisted_turns": len(persistence),
                },
                indent=2,
            )
        )


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize(
    "failure,status,upstream",
    [
        (HTTPError("http://secret.invalid", 503, "private server detail", Message(), None), 502, 503),
        (URLError(ConnectionRefusedError("private endpoint")), 503, None),
        (ConnectionRefusedError("private endpoint"), 503, None),
        (TimeoutError("private endpoint"), 504, None),
        (URLError(TimeoutError("private endpoint")), 504, None),
    ],
)
def test_native_transport_failure_is_non_success_once(transport_case, route, failure, status, upstream):
    client, body, records, persistence, attempts, outcome = transport_case
    outcome[0] = failure
    response = client.post(route, json=body)
    assert response.status_code == status, response.text
    error = response.json().get("detail", response.json().get("error"))
    assert error["type"] == "provider_transport_error"
    assert error.get("upstream_status") == upstream
    assert "private" not in response.text and "secret.invalid" not in response.text
    assert len(attempts) == 1
    assert [record["success"] for record in records] == [False]
    assert persistence == []


def test_transport_error_is_distinct_from_structured_validation(transport_case):
    client, body, records, persistence, attempts, outcome = transport_case
    outcome[0] = HTTPError("http://secret.invalid", 503, "private", Message(), None)
    response = client.post("/v1/chat/completions", json={**body, "response_format": {"type": "json_object"}})
    assert response.status_code == 502
    assert response.json()["detail"]["type"] == "provider_transport_error"
    assert [record["success"] for record in records] == [False]
    assert len(attempts) == 1 and persistence == []


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize("text", ["ordinary reply", "[API Error for qwen3.8] this is valid requested text"])
def test_native_success_is_not_classified_by_prefix(transport_case, route, text):
    client, body, records, _, attempts, outcome = transport_case
    outcome[0] = text
    response = client.post(route, json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    actual = (
        payload["choices"][0]["message"]["content"] if route.endswith("completions") else payload["content"][0]["text"]
    )
    assert actual == text
    assert [record["success"] for record in records] == [True]
    assert len(attempts) == 1


def test_transport_error_preserves_exception_through_generator_context():
    from antigravity_k.engine.provider_adapters.transport_errors import NativeTransportError, TransportFailure

    @contextmanager
    def boundary():
        yield

    error = NativeTransportError(TransportFailure.HTTP, upstream_status=503)
    with pytest.raises(NativeTransportError) as captured, boundary():
        raise error
    assert captured.value is error
    assert captured.value.upstream_status == 503


def test_explicit_combo_keeps_existing_fallback(transport_case, monkeypatch):
    from antigravity_k.engine.model_router import ModelCombo
    from antigravity_k.engine.provider_adapters import inference_providers

    client, body, records, _, attempts, _ = transport_case
    manager = client.contract_manager
    original = manager._registry.get_model(body["model"])
    assert original is not None
    alternate = "qwen3.8:fallback"
    manager._registry._models[alternate] = replace(original, name=alternate, repo=alternate)
    manager.router.register_combo(ModelCombo(name="transport-fallback", models=[original.name, alternate]))

    def terminal(request, **kwargs):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise HTTPError(request.full_url, 503, "unavailable", Message(), None)
        return io.BytesIO(b'{"message":{"content":"fallback succeeded"},"done":true}')

    monkeypatch.setattr(inference_providers, "safe_urlopen", terminal)
    assert manager.generate("hello", "transport-fallback") == "fallback succeeded"
    assert [record["success"] for record in records] == [False, True]
    assert len(attempts) == 2


def test_native_failure_through_real_safe_helper_has_no_retry(transport_case, monkeypatch):
    from antigravity_k.engine.provider_adapters import inference_providers
    from antigravity_k.tools import egress_policy

    client, body, records, persistence, attempts, _ = transport_case
    sleeps = []
    error = HTTPError("http://127.0.0.1:11434/api/chat", 503, "private", Message(), None)

    def terminal(request, **kwargs):
        attempts.append(request.full_url)
        raise error

    monkeypatch.setattr(inference_providers, "safe_urlopen", egress_policy.safe_urlopen)
    monkeypatch.setattr(egress_policy.urllib.request, "urlopen", terminal)
    monkeypatch.setattr(egress_policy, "_retry_sleep", sleeps.append)
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == 502
    assert len(attempts) == 1
    assert sleeps == []
    assert [record["success"] for record in records] == [False]
    assert persistence == []


def test_safe_helper_no_retry_preserves_original_http_error(monkeypatch):
    from antigravity_k.tools import egress_policy

    calls, sleeps = [], []
    error = HTTPError("http://127.0.0.1/api/chat", 503, "private", Message(), None)

    def terminal(*args, **kwargs):
        calls.append(args)
        raise error

    monkeypatch.setattr(egress_policy.urllib.request, "urlopen", terminal)
    monkeypatch.setattr(egress_policy, "_retry_sleep", sleeps.append)
    with pytest.raises(HTTPError) as captured:
        egress_policy.safe_urlopen(Request(error.url, data=b"{}"), max_retries=0)
    assert captured.value is error
    assert len(calls) == 1 and sleeps == []


def test_safe_helper_default_get_keeps_two_retries(monkeypatch):
    from antigravity_k.tools import egress_policy

    calls, sleeps = [], []
    error = HTTPError("http://127.0.0.1/health", 503, "private", Message(), None)

    def terminal(*args, **kwargs):
        calls.append(args)
        raise error

    monkeypatch.setattr(egress_policy.urllib.request, "urlopen", terminal)
    monkeypatch.setattr(egress_policy, "_retry_sleep", sleeps.append)
    with pytest.raises(HTTPError) as captured:
        egress_policy.safe_urlopen(error.url)
    assert captured.value is error
    assert len(calls) == 3 and sleeps == [1.0, 2.0]
