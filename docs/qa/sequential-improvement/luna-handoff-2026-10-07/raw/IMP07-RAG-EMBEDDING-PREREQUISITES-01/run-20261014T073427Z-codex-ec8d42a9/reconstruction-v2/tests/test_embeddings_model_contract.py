from __future__ import annotations

import hashlib
import json
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import Response

from antigravity_k.api.dependencies import get_embedding_engine
from antigravity_k.api.error_handler import http_exception_handler
from antigravity_k.api.routes.models_api import router
from antigravity_k.engine.audit_logger import AuditLogger
from antigravity_k.engine.embeddings import EmbeddingEngine, _EmbeddingFactory, _EmbeddingModel

MODEL = "nomic-embed-text:latest"
PROBE = "SSAK_EM01_MODEL_IDENTITY_PROBE"
DETAIL = {
    "code": "embedding_model_unavailable",
    "model": MODEL,
    "message": f"Embedding model '{MODEL}' could not be loaded.",
}
RecordProperty = Callable[[str, object], None]


@dataclass
class _Boundary:
    engine: EmbeddingEngine
    factory_models: list[str] = field(default_factory=list)
    encode_inputs: list[tuple[list[str], bool]] = field(default_factory=list)
    fallback_calls: int = 0
    network_attempts: int = 0
    post_count: int = 0


@pytest.fixture
def boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Boundary:
    state = _Boundary(EmbeddingEngine())
    original_fallback = state.engine._fallback_embedding

    def counted_fallback(text: str) -> list[float]:
        state.fallback_calls += 1
        return original_fallback(text)

    def blocked_connect(sock: socket.socket, address: object) -> None:
        state.network_attempts += 1
        raise AssertionError(f"unexpected external network request: {address!r}")

    monkeypatch.setattr(state.engine, "_fallback_embedding", counted_fallback)
    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    audit = AuditLogger(tmp_path / "audit")
    monkeypatch.setattr("antigravity_k.api.routes.models_api.get_audit_logger", lambda: audit)
    return state


def _install_factory(monkeypatch: pytest.MonkeyPatch, factory: _EmbeddingFactory) -> None:
    assert isinstance(factory, _EmbeddingFactory)
    module = ModuleType("sentence_transformers")
    setattr(module, "SentenceTransformer", factory)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)


def _post(
    state: _Boundary,
    record_property: RecordProperty,
    *,
    case: str,
    inputs: list[str],
    shared_handler: bool = False,
) -> Response:
    app = FastAPI()
    app.include_router(router)
    if shared_handler:
        app.add_exception_handler(HTTPException, http_exception_handler)
    app.dependency_overrides[get_embedding_engine] = lambda: state.engine
    assert state.factory_models == []
    assert state.fallback_calls == state.network_attempts == state.post_count == 0
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            state.post_count += 1
            response = client.post("/v1/embeddings", json={"model": MODEL, "input": inputs})
    finally:
        app.dependency_overrides.clear()

    # The audit runner exports JUnit, not arbitrary files in its disposable checkout.
    # Preserve raw UTF-8 JSON there once; stdout and summaries contain hashes only.
    record_property("embedding_request_raw", response.request.content.decode("utf-8"))
    record_property("embedding_response_raw", response.content.decode("utf-8"))
    record_property(
        "embedding_observation",
        json.dumps(
            {
                "case": case,
                "post_count": state.post_count,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "request_bytes": len(response.request.content),
                "request_sha256": hashlib.sha256(response.request.content).hexdigest(),
                "response_bytes": len(response.content),
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "factory_calls": len(state.factory_models),
                "encode_calls": len(state.encode_inputs),
                "fallback_calls": state.fallback_calls,
                "network_attempts": state.network_attempts,
                "live_embedding": "NOT_RUN",
            },
            separators=(",", ":"),
        ),
    )
    return response


def _assert_unavailable(response: Response, state: _Boundary) -> None:
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["detail"] == DETAIL
    assert "data" not in body and "embedding" not in body
    assert "controlled-loader-failure" not in response.text
    assert state.fallback_calls == state.network_attempts == 0
    assert state.encode_inputs == []
    assert state.post_count == 1


@pytest.mark.parametrize("shared_handler", [False, True], ids=["default-handler", "shared-handler"])
def test_explicit_model_load_failure_does_not_return_hash_fallback_as_success(
    monkeypatch: pytest.MonkeyPatch,
    boundary: _Boundary,
    record_property: RecordProperty,
    shared_handler: bool,
) -> None:
    def failing_factory(model_name: str) -> _EmbeddingModel:
        boundary.factory_models.append(model_name)
        raise RuntimeError("controlled-loader-failure")

    _install_factory(monkeypatch, failing_factory)
    response = _post(
        boundary,
        record_property,
        case="runtime_shared" if shared_handler else "runtime_default",
        inputs=[PROBE],
        shared_handler=shared_handler,
    )
    _assert_unavailable(response, boundary)
    assert boundary.factory_models == [MODEL]
    if shared_handler:
        body = response.json()
        assert body["ok"] is False
        assert body["error"] == "http_503"
        assert isinstance(body["correlation_id"], str) and body["correlation_id"]
    else:
        assert response.json() == {"detail": DETAIL}


def test_dependency_import_failure_has_same_strict_contract(
    monkeypatch: pytest.MonkeyPatch, boundary: _Boundary, record_property: RecordProperty
) -> None:
    # A missing required external export causes ImportError in the real lazy import.
    monkeypatch.setitem(sys.modules, "sentence_transformers", ModuleType("sentence_transformers"))
    response = _post(boundary, record_property, case="import_default", inputs=[PROBE])
    _assert_unavailable(response, boundary)
    assert boundary.factory_models == []
    assert boundary.engine.current_model == MODEL


def test_external_encoder_success_preserves_inputs_vectors_and_indexes(
    monkeypatch: pytest.MonkeyPatch, boundary: _Boundary, record_property: RecordProperty
) -> None:
    inputs = ["first input", "second input"]
    vectors = ((0.25, -0.5), (0.75, 1.0))

    class Encoder:
        def encode(self, sentences: list[str], *, convert_to_numpy: bool) -> tuple[tuple[float, ...], ...]:
            boundary.encode_inputs.append((list(sentences), convert_to_numpy))
            return vectors

    def factory(model_name: str) -> _EmbeddingModel:
        boundary.factory_models.append(model_name)
        return Encoder()

    _install_factory(monkeypatch, factory)
    response = _post(boundary, record_property, case="backend_success", inputs=inputs)
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["model"] == MODEL
    assert body["data"] == [
        {"object": "embedding", "embedding": list(vector), "index": index} for index, vector in enumerate(vectors)
    ]
    assert boundary.factory_models == [MODEL]
    assert boundary.encode_inputs == [(inputs, True)]
    assert boundary.fallback_calls == boundary.network_attempts == 0
    assert boundary.post_count == 1
