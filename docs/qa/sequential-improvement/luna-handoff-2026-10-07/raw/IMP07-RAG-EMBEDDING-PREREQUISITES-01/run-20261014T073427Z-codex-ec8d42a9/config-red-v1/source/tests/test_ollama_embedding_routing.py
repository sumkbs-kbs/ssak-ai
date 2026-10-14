from __future__ import annotations

import hashlib
import json
import math
import socket
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import cast

import httpx
import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from antigravity_k.api.error_handler import http_exception_handler
from antigravity_k.api.routes.models_api import router
from antigravity_k.engine.audit_logger import AuditLogger
from antigravity_k.engine.embeddings import EmbeddingEngine, EmbeddingModelUnavailableError
from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.provider_adapters.embedding_providers import OllamaEmbeddingProvider

RecordProperty = Callable[[str, object], None]
MODEL_NAME = "nomic-embed-text:latest"
MODEL_REPO = "nomic-embed-text:v1"
VECTORS = [[0.25, -0.5], [0.75, 1.0]]
PROTOCOL_DETAIL = {
    "code": "embedding_provider_invalid_response",
    "model": MODEL_NAME,
    "message": "Embedding provider returned an invalid response.",
}
_LIVE_NETWORK_ATTEMPTS: list[str] = []


class _Counter:
    def __init__(self) -> None:
        self.api_posts = 0
        self.mock_posts = 0
        self.live_network_attempts = 0
        self.factory_calls = 0
        self.encode_calls = 0
        self.fallback_calls = 0
        self.observations: list[dict[str, object]] = []


def _registry_file(
    path: Path,
    *,
    provider: str = "ollama",
    roles: list[str] | None = None,
    api_base: str = "",
    dimensions: int = 2,
    provider_base: object = "http://provider-host:11434/v1/",
    include_model: bool = True,
    role: str = "embedding",
) -> Path:
    profile: dict[str, object] = {
        "name": MODEL_NAME,
        "repo": MODEL_REPO,
        "role": role,
        "provider": provider,
        "api_base": api_base,
        "dimensions": dimensions,
    }
    if roles is not None:
        profile["roles"] = roles
    value: dict[str, object] = {"models": {role: [profile] if include_model else []}, "providers": {}}
    providers: dict[str, object] = {}
    if provider_base is not None:
        providers["base_url"] = provider_base
    value["providers"] = {"ollama": providers}
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _response(
    request: httpx.Request, body: object, *, status: int = 200, content_type: str = "application/json"
) -> httpx.Response:
    content = body if isinstance(body, bytes) else json.dumps(body, allow_nan=True).encode()
    return httpx.Response(status, content=content, headers={"content-type": content_type}, request=request)


def _transport(
    counter: _Counter,
    handler: Callable[[httpx.Request], httpx.Response],
    records: list[dict[str, object]],
) -> httpx.MockTransport:
    def serve(request: httpx.Request) -> httpx.Response:
        counter.mock_posts += int(request.method == "POST")
        raw = request.read()
        record: dict[str, object] = {
            "method": request.method,
            "url": str(request.url),
            "request_body": raw.decode("utf-8"),
            "request_sha256": hashlib.sha256(raw).hexdigest(),
            "request_bytes": len(raw),
            "has_authorization_header": "authorization" in request.headers,
        }
        records.append(record)
        try:
            response = handler(request)
        except httpx.RequestError as exc:
            record.update(response_status=None, transport_error=type(exc).__name__, response_body="")
            raise
        record["response_status"] = response.status_code
        record["response_body"] = response.content.decode("utf-8", errors="replace")
        record["response_sha256"] = hashlib.sha256(response.content).hexdigest()
        record["response_bytes"] = len(response.content)
        return response

    return httpx.MockTransport(serve)


def _record_httpx_options(kwargs: dict[str, object], tmp_path: Path) -> httpx.Client:
    options_path = tmp_path / "httpx-options.json"
    options_path.write_text(
        json.dumps({key: value for key, value in kwargs.items() if key != "transport"}, default=str), encoding="utf-8"
    )
    return httpx.Client(**kwargs)


def _app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    transport: httpx.MockTransport,
    counter: _Counter,
) -> FastAPI:
    monkeypatch.setenv("AGK_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("OLLAMA_API_KEY", "sentinel-never-transmitted")

    def provider_factory() -> OllamaEmbeddingProvider:
        return OllamaEmbeddingProvider(transport=transport)

    monkeypatch.setattr("antigravity_k.engine.embeddings.OllamaEmbeddingProvider", provider_factory)

    def client_factory(**kwargs: object) -> httpx.Client:
        return _record_httpx_options(kwargs, tmp_path)

    monkeypatch.setattr("antigravity_k.engine.provider_adapters.embedding_providers.HttpxClient", client_factory)

    def forbidden_factory(model_name: str) -> object:
        counter.factory_calls += 1
        raise RuntimeError(f"unexpected SentenceTransformer use for {model_name}")

    module = ModuleType("sentence_transformers")
    setattr(module, "SentenceTransformer", forbidden_factory)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    original_fallback = EmbeddingEngine._fallback_embedding

    def counted_fallback(engine: EmbeddingEngine, text: str) -> list[float]:
        counter.fallback_calls += 1
        return original_fallback(engine, text)

    monkeypatch.setattr(EmbeddingEngine, "_fallback_embedding", counted_fallback)
    monkeypatch.setattr("antigravity_k.api.routes.models_api.get_audit_logger", lambda: AuditLogger(tmp_path / "audit"))
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def _block_any_real_socket(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []
    monkeypatch.setattr(sys.modules[__name__], "_LIVE_NETWORK_ATTEMPTS", attempts)

    def deny(sock: socket.socket, address: object) -> None:
        attempts.append(repr(address))
        raise AssertionError(f"live network is prohibited: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", deny)
    yield


def _call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    counter: _Counter,
    record_property: RecordProperty,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str = MODEL_NAME,
    inputs: str | list[str] = ("first", "second"),
    transport_records: list[dict[str, object]] | None = None,
    shared_handler: bool = False,
) -> tuple[httpx.Response, list[dict[str, object]]]:
    records = transport_records if transport_records is not None else []
    transport = _transport(counter, handler, records)
    app = _app(monkeypatch, tmp_path, config_path, transport, counter)
    if shared_handler:
        app.add_exception_handler(HTTPException, http_exception_handler)
    request_body = {"model": model, "input": inputs}
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            counter.api_posts += 1
            response = client.post("/v1/embeddings", json=request_body)
    finally:
        app.dependency_overrides.clear()
    options_path = tmp_path / "httpx-options.json"
    options = json.loads(options_path.read_text()) if options_path.is_file() else None
    counter.live_network_attempts = len(_LIVE_NETWORK_ATTEMPTS)
    counter.observations.append(
        {
            "request": request_body,
            "api_status": response.status_code,
            "api_response": response.text,
            "api_request_bytes": len(response.request.content),
            "api_request_sha256": hashlib.sha256(response.request.content).hexdigest(),
            "api_response_bytes": len(response.content),
            "api_response_sha256": hashlib.sha256(response.content).hexdigest(),
            "api_post_count": 1,
            "mock_native_post_count": counter.mock_posts,
            "live_network_attempts": counter.live_network_attempts,
            "live_network_addresses": list(_LIVE_NETWORK_ATTEMPTS),
            "transport_attempt_count": len(records),
            "mock_native_post_count_this_call": sum(record.get("method") == "POST" for record in records),
            "api_post_count_this_call": 1,
            "httpx_options": options,
        }
    )
    record_property("routing_case_raw", json.dumps(counter.observations[-1], separators=(",", ":")))
    record_property("routing_transport_raw", json.dumps(records, separators=(",", ":")))
    return response, records


def test_real_dependency_registry_engine_route_uses_one_native_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, record_property: RecordProperty
) -> None:
    config_path = _registry_file(tmp_path / "config.yaml", roles=["reasoning", "embedding"])
    counter = _Counter()
    transport_records: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, {"model": MODEL_REPO, "embeddings": VECTORS})

    response, records = _call(
        monkeypatch, tmp_path, config_path, counter, record_property, handler, transport_records=transport_records
    )
    body = response.json()
    assert response.status_code == 200
    assert body["model"] == MODEL_NAME
    assert body["data"] == [
        {"object": "embedding", "embedding": vector, "index": index} for index, vector in enumerate(VECTORS)
    ]
    assert body["usage"]["prompt_tokens"] == 2
    assert body["usage"]["completion_tokens"] == 0
    assert body["usage"]["total_tokens"] == 2
    assert counter.api_posts == counter.mock_posts == 1
    assert counter.live_network_attempts == counter.factory_calls == counter.encode_calls == counter.fallback_calls == 0
    assert counter.observations[-1]["httpx_options"] == {
        "timeout": 55.0,
        "follow_redirects": False,
        "trust_env": False,
    }
    assert json.loads(cast(str, records[0]["request_body"])) == {
        "model": MODEL_REPO,
        "input": ["first", "second"],
        "truncate": False,
    }
    assert records[0]["url"] == "http://provider-host:11434/api/embed"
    assert records[0]["has_authorization_header"] is False
    assert "keep_alive" not in cast(str, records[0]["request_body"])
    assert len(records) == 1
    assert records[0]["method"] == "POST"


def test_registered_repo_alias_single_string_and_embedding_among_roles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, record_property: RecordProperty
) -> None:
    path = _registry_file(tmp_path / "config.yaml", roles=["reasoning", "embedding"])
    counter = _Counter()
    response, records = _call(
        monkeypatch,
        tmp_path,
        path,
        counter,
        record_property,
        lambda request: _response(request, {"model": MODEL_REPO, "embeddings": [VECTORS[0]]}),
        model=MODEL_REPO,
        inputs="single input",
    )
    assert response.status_code == 200 and response.json()["model"] == MODEL_REPO
    assert json.loads(cast(str, records[0]["request_body"]))["model"] == MODEL_REPO
    assert response.json()["data"][0]["embedding"] == VECTORS[0]
    assert json.loads(cast(str, records[0]["request_body"]))["input"] == ["single input"]
    assert counter.api_posts == counter.mock_posts == 1


@pytest.mark.parametrize(
    ("api_base", "provider_base", "expected"),
    [
        ("http://profile-host:9000/v1/", "http://provider-host:11434/v1", "http://profile-host:9000/api/embed"),
        ("", "http://proxy-host:9999/proxy/v1/", "http://proxy-host:9999/proxy/api/embed"),
        ("", None, "http://localhost:11434/api/embed"),
        ("", "http://proxy-host:9999/prefix/", "http://proxy-host:9999/prefix/api/embed"),
    ],
    ids=["profile-priority", "provider-v1-proxy", "default", "proxy-prefix"],
)
def test_endpoint_resolution_and_normalization(
    api_base: str,
    provider_base: object,
    expected: str,
    tmp_path: Path,
    record_property: RecordProperty,
) -> None:
    registry_path = _registry_file(
        tmp_path / f"{len(list(tmp_path.iterdir()))}.yaml", api_base=api_base, provider_base=provider_base
    )
    registry = ModelRegistry(str(registry_path))
    profile = registry.get_model(MODEL_NAME)
    assert profile is not None
    records: list[dict[str, object]] = []
    provider = OllamaEmbeddingProvider(
        transport=_transport(
            _Counter(), lambda request: _response(request, {"model": MODEL_REPO, "embeddings": [VECTORS[0]]}), records
        )
    )
    result = provider.embed(profile, registry, "single", MODEL_REPO)
    assert result == [VECTORS[0]]
    assert records[0]["url"] == expected
    record_property("endpoint_case", json.dumps({"expected": expected, "actual": records[0]["url"], "post_count": 1}))


@pytest.mark.parametrize(
    ("provider", "roles", "registered", "requested", "role"),
    [
        ("openai", ["embedding"], True, MODEL_NAME, "embedding"),
        ("ollama", ["reasoning"], True, MODEL_NAME, "reasoning"),
        ("ollama", ["embedding"], False, "unregistered:embedding", "embedding"),
    ],
    ids=["wrong-provider", "wrong-role", "unregistered-tag"],
)
def test_non_matching_registry_profiles_do_not_select_native(
    provider: str,
    roles: list[str],
    registered: bool,
    requested: str,
    role: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_property: RecordProperty,
) -> None:
    path = _registry_file(tmp_path / "config.yaml", provider=provider, roles=roles, include_model=registered, role=role)
    registry = ModelRegistry(str(path))
    calls: list[str] = []

    def factory(name: str) -> object:
        calls.append(name)
        raise RuntimeError("fixture-loader-unavailable")

    module = ModuleType("sentence_transformers")
    setattr(module, "SentenceTransformer", factory)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    engine = EmbeddingEngine(registry=registry)
    with pytest.raises(EmbeddingModelUnavailableError):
        engine.embed("input", requested, allow_fallback=False)
    assert calls == [requested]
    record_property(
        "nonmatch_observation",
        json.dumps({"registry_match": registered, "native_post_count": 0, "legacy_factory_calls": len(calls)}),
    )


def test_invalid_base_url_is_unavailable_without_network_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_property: RecordProperty,
) -> None:
    path = _registry_file(tmp_path / "config.yaml", api_base="http://profile-host:9000/?query=bad")
    counter = _Counter()
    response, records = _call(
        monkeypatch,
        tmp_path,
        path,
        counter,
        record_property,
        lambda request: _response(request, {"model": MODEL_REPO, "embeddings": VECTORS}),
        shared_handler=True,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "embedding_model_unavailable"
    assert records == []
    assert counter.api_posts == 1 and counter.mock_posts == 0
    assert counter.fallback_calls == counter.factory_calls == counter.encode_calls == counter.live_network_attempts == 0


@pytest.mark.parametrize(
    ("failure", "status"),
    [("timeout", 503), ("connection", 503), ("redirect", 503), ("http400", 503), ("http500", 503)],
)
def test_transport_failures_are_single_attempt_503_without_fallback(
    failure: str,
    status: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_property: RecordProperty,
) -> None:
    path = _registry_file(tmp_path / "config.yaml")
    counter = _Counter()

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("controlled timeout", request=request)
        if failure == "connection":
            raise httpx.ConnectError("controlled connection", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "http://must-not-follow/api/embed"}, request=request)
        return _response(request, {"error": "controlled"}, status=400 if failure == "http400" else 500)

    response, records = _call(monkeypatch, tmp_path, path, counter, record_property, handler, shared_handler=True)
    body = response.json()
    assert response.status_code == status
    assert body["detail"] == {
        "code": "embedding_model_unavailable",
        "model": MODEL_NAME,
        "message": f"Embedding model '{MODEL_NAME}' could not be loaded.",
    }
    assert counter.api_posts == counter.mock_posts == 1
    assert len(records) == 1
    assert counter.fallback_calls == counter.factory_calls == counter.encode_calls == counter.live_network_attempts == 0
    assert response.json()["error"] == "http_503"
    assert counter.observations[-1]["httpx_options"] == {
        "timeout": 55.0,
        "follow_redirects": False,
        "trust_env": False,
    }


@pytest.mark.parametrize(
    "case",
    [
        "invalid-json",
        "content-type",
        "model",
        "count",
        "empty",
        "unequal",
        "dimension",
        "bool",
        "string",
        "nan",
        "infinity",
        "overflow",
        "zero",
    ],
)
def test_invalid_upstream_protocol_maps_only_to_structured_502(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_property: RecordProperty,
) -> None:
    path = _registry_file(tmp_path / "config.yaml", dimensions=2)

    def handler(request: httpx.Request) -> httpx.Response:
        if case == "invalid-json":
            return _response(request, b"not json")
        if case == "content-type":
            return _response(request, {"model": MODEL_REPO, "embeddings": VECTORS}, content_type="text/plain")
        bodies: dict[str, object] = {
            "model": {"model": "other-model", "embeddings": VECTORS},
            "count": {"model": MODEL_REPO, "embeddings": [VECTORS[0]]},
            "empty": {"model": MODEL_REPO, "embeddings": [[], VECTORS[1]]},
            "unequal": {"model": MODEL_REPO, "embeddings": [[1.0, 2.0], [1.0]]},
            "dimension": {"model": MODEL_REPO, "embeddings": [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]]},
            "bool": {"model": MODEL_REPO, "embeddings": [[True, 0.5], VECTORS[1]]},
            "string": {"model": MODEL_REPO, "embeddings": [["0.25", 0.5], VECTORS[1]]},
            "nan": {"model": MODEL_REPO, "embeddings": [[float("nan"), 0.5], VECTORS[1]]},
            "infinity": {"model": MODEL_REPO, "embeddings": [[float("inf"), 0.5], VECTORS[1]]},
            "overflow": {"model": MODEL_REPO, "embeddings": [[10**400, 0.5], VECTORS[1]]},
            "zero": {"model": MODEL_REPO, "embeddings": [[0.0, 0.0], VECTORS[1]]},
        }
        return _response(request, bodies[case])

    counter = _Counter()
    response, records = _call(monkeypatch, tmp_path, path, counter, record_property, handler, shared_handler=True)
    body = response.json()
    assert response.status_code == 502
    assert body["detail"] == PROTOCOL_DETAIL
    assert body["error"] == "http_502"
    assert counter.observations[-1]["httpx_options"] == {
        "timeout": 55.0,
        "follow_redirects": False,
        "trust_env": False,
    }
    assert counter.api_posts == counter.mock_posts == 1 and len(records) == 1
    assert counter.fallback_calls == counter.factory_calls == counter.encode_calls == counter.live_network_attempts == 0


def test_unregistered_dimensions_allow_other_consistent_positive_size(tmp_path: Path) -> None:
    registry = ModelRegistry(str(_registry_file(tmp_path / "config.yaml", dimensions=0)))
    profile = registry.get_model(MODEL_NAME)
    assert profile is not None
    provider = OllamaEmbeddingProvider(
        transport=httpx.MockTransport(
            lambda request: _response(request, {"model": MODEL_REPO, "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]})
        )
    )
    result = provider.embed(profile, registry, ["a", "b"], MODEL_REPO)
    assert len(result) == 2 and all(len(row) == 3 for row in result)
    assert all(math.isclose(a, b) for a, b in zip(result[0], [0.1, 0.2, 0.3], strict=True))


def test_profile_dimensions_rejects_non_integer_or_non_positive_configuration(tmp_path: Path) -> None:
    path = _registry_file(tmp_path / "config.yaml")
    registry = ModelRegistry(str(path))
    profile = registry.get_model(MODEL_NAME)
    assert profile is not None
    assert type(profile.dimensions) is int and profile.dimensions == 2
