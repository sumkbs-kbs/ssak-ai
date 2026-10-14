from __future__ import annotations

import io
import json
import os
import socket
import uuid
from dataclasses import replace
from pathlib import Path

import pytest


@pytest.fixture
def product(monkeypatch, tmp_path, request):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGK_AUTO_DISCOVER_LOCAL_MODELS", "false")
    monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(tmp_path))

    def denied(*args, **kwargs):
        pytest.fail("unexpected socket connection")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from antigravity_k.api import dependencies, project_binding
    from antigravity_k.api.routes import chat
    from antigravity_k.config import config
    from antigravity_k.engine.audit_logger import AuditLogger
    from antigravity_k.engine.model_manager import ModelManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.project_registry import ProjectRegistry
    from antigravity_k.engine.protocol_translator import ProtocolTranslator
    from antigravity_k.engine.provider_adapters import inference_providers
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.engine.usage_tracker import UsageTracker
    from antigravity_k.engine.user_model import global_gbrain

    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    registry = ProjectRegistry(storage_path=tmp_path / "projects.json")
    project = registry.add_project("structured-output", str(tmp_path))
    monkeypatch.setattr(project_binding, "get_project_registry", lambda: registry)
    sessions = SessionManager(base_dir=str(tmp_path / "sessions"))
    effects = []
    start_session = sessions.start_session
    apply_conversation = chat._apply_authoritative_conversation

    def record_session(*args, **kwargs):
        effects.append("session")
        return start_session(*args, **kwargs)

    def record_conversation(*args, **kwargs):
        effects.append("conversation")
        return apply_conversation(*args, **kwargs)

    monkeypatch.setattr(sessions, "start_session", record_session)
    monkeypatch.setattr(chat, "_apply_authoritative_conversation", record_conversation)
    monkeypatch.setattr(dependencies, "get_session_manager", lambda: sessions)
    monkeypatch.setattr(chat, "get_audit_logger", lambda: AuditLogger(log_dir=tmp_path / "audit"))
    monkeypatch.setattr(global_gbrain, "add_node", lambda **kwargs: None)
    manager = ModelManager(ModelRegistry(), tracker=UsageTracker(db_path=None))
    monkeypatch.setattr(ModelManager, "_load_mlx_model", lambda *args: (None, None))
    calls = []
    generations = []
    responses = []
    content = ['{"red_circles":2,"blue_squares":1}']
    generate = manager.generate

    def record_generate(*args, **kwargs):
        generations.append(kwargs)
        return generate(*args, **kwargs)

    monkeypatch.setattr(manager, "generate", record_generate)

    def terminal(request, **kwargs):
        calls.append(json.loads(request.data))
        return io.BytesIO((json.dumps({"message": {"content": content[0]}, "done": True}) + "\n").encode())

    monkeypatch.setattr(inference_providers, "safe_urlopen", terminal)
    app = FastAPI()
    app.include_router(chat.router)
    app.dependency_overrides[chat.get_model_manager] = lambda: manager
    app.dependency_overrides[chat.get_translator] = ProtocolTranslator
    body = {
        "model": "qwen3.8",
        "project_id": project.id,
        "messages": [{"role": "user", "content": "Count the shapes and return JSON."}],
    }
    with TestClient(app) as client:
        client.contract_effects = effects
        client.contract_manager = manager
        original_post = client.post

        def record_post(*args, **kwargs):
            response = original_post(*args, **kwargs)
            responses.append({"status": response.status_code, "body": response.text, "request": kwargs.get("json")})
            return response

        monkeypatch.setattr(client, "post", record_post)
        yield client, body, calls, generations, content
    export = os.environ.get("STRUCTURED_OUTPUT_CAPTURE_ROOT")
    if export:
        capture = Path(export) / (uuid.uuid4().hex + ".json")
        capture.parent.mkdir(parents=True, exist_ok=True)
        capture.write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "wire": calls,
                    "manager_calls": len(generations),
                    "provider_calls": len(calls),
                    "upstream_content": content[0],
                    "responses": responses,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


SCHEMA = {
    "type": "object",
    "properties": {"red_circles": {"type": "integer"}, "blue_squares": {"type": "integer"}},
    "required": ["red_circles", "blue_squares"],
    "additionalProperties": False,
}
ENVELOPE = {"type": "json_schema", "json_schema": {"name": "shapes", "strict": True, "schema": SCHEMA}}


@pytest.mark.parametrize("format_value,native", [({"type": "json_object"}, "json"), (ENVELOPE, SCHEMA)])
def test_structured_image_reaches_native_wire_once(product, format_value, native):
    client, body, calls, generations, content = product
    image = (Path(__file__).parent / "fixtures/vision_shapes_384x256.png.b64").read_text().strip()
    body["messages"][0]["content"] = [
        {"type": "text", "text": "Count the shapes and return JSON."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}},
    ]
    response = client.post("/v1/chat/completions", json={**body, "response_format": format_value})
    assert response.status_code == 200, response.text
    assert len(calls) == len(generations) == 1
    assert calls[0]["format"] == native
    assert calls[0]["messages"][-1]["images"] == [image]
    assert response.json()["choices"][0]["message"]["content"] == content[0]


@pytest.mark.parametrize(
    "value",
    [
        "json",
        {},
        {"type": "bogus"},
        {"type": "json_schema"},
        {"type": "json_schema", "json_schema": {"name": "x", "strict": "true", "schema": SCHEMA}},
        {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "bogus"}}},
        {"type": "json_schema", "json_schema": {"name": "x", "schema": {"$ref": "https://example.com/schema"}}},
    ],
)
def test_bad_format_rejected_before_inference(product, value):
    client, body, calls, generations, _ = product
    response = client.post("/v1/chat/completions", json={**body, "response_format": value})
    assert response.status_code == 400
    assert response.json()["detail"]["type"] == "invalid_request_error"
    assert calls == generations == []
    assert client.contract_effects == []


@pytest.mark.parametrize(
    "extra",
    [
        {"agent_mode": True},
        {"plan_mode": True},
        {"tdd_mode": True},
        {"web_search": True},
        {"tools": []},
        {"stream": True},
        {"model": "unknown-provider"},
    ],
)
def test_unsupported_path_rejected_before_inference(product, extra):
    client, body, calls, generations, _ = product
    response = client.post("/v1/chat/completions", json={**body, "response_format": ENVELOPE, **extra})
    assert response.status_code == 400
    assert calls == generations == []
    assert client.contract_effects == []


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"red_circles":2,"blue_squares":1}\n```',
        "invalid",
        '{"red_circles":true,"blue_squares":1}',
        '{"red_circles":2,"blue_squares":1,"extra":0}',
        '{"red_circles":NaN,"blue_squares":1}',
        '{"red_circles":0,"red_circles":2,"blue_squares":1}',
    ],
)
def test_invalid_output_is_not_success(product, raw):
    client, body, calls, generations, content = product
    content[0] = raw
    response = client.post("/v1/chat/completions", json={**body, "response_format": ENVELOPE})
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["type"] == "structured_output_error"
    assert len(calls) == len(generations) == 1


@pytest.mark.parametrize("format_value", [None, {"type": "text"}, "omitted"])
def test_text_format_preserves_legacy_output(product, format_value):
    client, body, calls, _, content = product
    body["messages"][0]["content"] = "안녕"
    content[0] = "ordinary text"
    payload = {**body, "agent_mode": False}
    if format_value != "omitted":
        payload["response_format"] = format_value
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "format" not in calls[0]
    assert response.json()["choices"][0]["message"]["content"] == content[0]


@pytest.mark.parametrize("provider", ["openrouter", "mlx", "anthropic", "ollama"])
def test_registered_other_provider_is_rejected(product, provider):
    client, body, calls, generations, _ = product
    registry = client.contract_manager._registry
    original = registry.get_model("qwen3.8")
    registry._models["other"] = replace(original, name="other", provider=provider)
    response = client.post("/v1/chat/completions", json={**body, "model": "other", "response_format": ENVELOPE})
    assert response.status_code == 400
    assert calls == generations == client.contract_effects == []


def test_explicit_model_survives_image_default_routing(product):
    client, body, calls, generations, _ = product
    registry = client.contract_manager._registry
    original = registry.get_model("qwen3.8")
    registry._models["qwen3.8:explicit"] = replace(original, name="qwen3.8:explicit", repo="qwen3.8:explicit")
    image = (Path(__file__).parent / "fixtures/vision_shapes_384x256.png.b64").read_text().strip()
    body["messages"][0]["content"] = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}]
    response = client.post(
        "/v1/chat/completions", json={**body, "model": "qwen3.8:explicit", "response_format": ENVELOPE}
    )
    assert response.status_code == 200, response.text
    assert len(calls) == len(generations) == 1
    assert calls[0]["model"] == "qwen3.8:explicit"


def test_reference_named_property_is_ordinary_json(product):
    client, body, calls, _, content = product
    schema = {
        "type": "object",
        "properties": {"$ref": {"type": "string"}},
        "required": ["$ref"],
        "additionalProperties": False,
    }
    content[0] = '{"$ref":"ordinary data"}'
    response = client.post(
        "/v1/chat/completions",
        json={
            **body,
            "response_format": {"type": "json_schema", "json_schema": {"name": "reference", "schema": schema}},
        },
    )
    assert response.status_code == 200, response.text
    assert calls[0]["format"] == schema


def test_nested_schema_reference_is_rejected(product):
    client, body, calls, generations, _ = product
    schema = {"type": "object", "properties": {"child": {"$ref": "https://example.com/schema"}}}
    response = client.post(
        "/v1/chat/completions",
        json={
            **body,
            "response_format": {"type": "json_schema", "json_schema": {"name": "reference", "schema": schema}},
        },
    )
    assert response.status_code == 400
    assert calls == generations == client.contract_effects == []


@pytest.mark.parametrize(
    "child",
    [
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "dependencies": {"x": {"$ref": "https://example.com/schema"}},
        },
        {"type": "object", "dependencies": {"x": {"$ref": "https://example.com/schema"}}},
    ],
)
def test_nested_dialect_and_legacy_dependencies_rejected_before_dispatch(product, child):
    client, body, calls, generations, _ = product
    schema = {"type": "object", "properties": {"child": child}}
    response = client.post(
        "/v1/chat/completions",
        json={**body, "response_format": {"type": "json_schema", "json_schema": {"name": "nested", "schema": schema}}},
    )
    assert response.status_code == 400
    assert calls == generations == client.contract_effects == []


def test_schema_named_property_and_annotation_do_not_switch_dialect(product):
    client, body, calls, _, content = product
    schema = {
        "type": "object",
        "properties": {"$schema": {"type": "string"}},
        "examples": [{"$schema": "http://json-schema.org/draft-07/schema#"}],
    }
    content[0] = '{"$schema":"ordinary data"}'
    response = client.post(
        "/v1/chat/completions",
        json={**body, "response_format": {"type": "json_schema", "json_schema": {"name": "data", "schema": schema}}},
    )
    assert response.status_code == 200, response.text
    assert calls[0]["format"] == schema


def test_closed_registry_maps_resolution_failure_without_transport(monkeypatch):
    import urllib.request

    from antigravity_k.engine.structured_output import OutputContract, StructuredOutputError

    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(args)
        pytest.fail("schema retrieval attempted")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    schema = {
        "type": "object",
        "properties": {
            "child": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "dependencies": {"x": {"$ref": "https://example.com/schema"}},
            }
        },
    }
    contract = OutputContract(schema_text=json.dumps(schema))
    with pytest.raises(StructuredOutputError, match="resolution is disabled"):
        contract.validate_content('{"child":{"x":1}}')
    assert attempts == []
