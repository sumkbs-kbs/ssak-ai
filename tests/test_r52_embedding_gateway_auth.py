"""Embedding authentication uses explicit endpoint configuration and fake HTTP only."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from antigravity_k.engine import call_ledger
from antigravity_k.engine.model_registry import ModelProfile, ModelRegistry
from antigravity_k.engine.provider_adapters.embedding_providers import (
    OllamaEmbeddingProvider,
    OllamaEmbeddingUnavailableError,
)

MODEL = "nomic-embed-text:latest"
GATEWAY = "http://127.0.0.1:11435"
KEY_ENV = "R52_SYNTHETIC_EMBED_TOKEN"
PROVIDER_KEY_ENV = "R52_SYNTHETIC_PROVIDER_TOKEN"
TOKEN = "synthetic-profile-key-do-not-log"
PROVIDER_TOKEN = "synthetic-provider-key-do-not-log"
TEXT = "synthetic-request-body-do-not-log"


@pytest.fixture(autouse=True)
def synthetic_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    for kind in ("llm", "embed"):
        (ledger / f"{kind}.count").write_text("0\n")
    monkeypatch.setenv("AGK_TEST_CALL_LEDGER_DIR", str(ledger))
    monkeypatch.setenv("AGK_TEST_EMBED_TOTAL_LIMIT", "6")
    monkeypatch.setenv("AGK_EMBEDDING_REQUEST_LIMIT", "6")
    monkeypatch.setenv("AGK_EMBED_MODEL_ALLOWLIST", MODEL)
    monkeypatch.setenv("AGK_LLM_INPUT_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("OLLAMA_API_KEY", "implicit-global-key-must-not-be-used")
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(PROVIDER_KEY_ENV, raising=False)
    monkeypatch.setattr(OllamaEmbeddingProvider, "requests_sent", 0)


def profile(*, base: str = GATEWAY, key_env: str = "") -> ModelProfile:
    return ModelProfile(
        name=MODEL, repo=MODEL, role="embedding", provider="ollama",
        api_base=base, api_key_env=key_env, dimensions=2,
    )


def registry(tmp_path: Path, *, base: str = GATEWAY, key_env: str = PROVIDER_KEY_ENV) -> ModelRegistry:
    path = tmp_path / "registry.yaml"
    path.write_text(json.dumps({
        "models": {"embedding": [{"name": MODEL, "repo": MODEL, "role": "embedding", "provider": "ollama", "dimensions": 2}]},
        "providers": {"ollama": {"base_url": base, "api_key_env": key_env}},
    }))
    return ModelRegistry(str(path))


def success(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"model": MODEL, "embeddings": [[0.25, -0.5]]}, request=request)


@pytest.mark.parametrize("base", [GATEWAY, GATEWAY + "/v1/"])
def test_explicit_profile_key_authenticates_the_actual_embedding_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, base: str
) -> None:
    monkeypatch.setenv(KEY_ENV, TOKEN)
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers.get("authorization") != "Bearer " + TOKEN:
            return httpx.Response(401, request=request)
        return success(request)

    with caplog.at_level(logging.DEBUG):
        result = OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(base=base, key_env=KEY_ENV), None, TEXT, MODEL)

    assert result == [[0.25, -0.5]] and len(requests) == 1
    assert str(requests[0].url) == GATEWAY + "/api/embed"
    assert json.loads(requests[0].content) == {"model": MODEL, "input": [TEXT], "truncate": False}
    assert TOKEN not in caplog.text and TEXT not in caplog.text
    audit = (tmp_path / "audit.jsonl").read_text()
    assert TOKEN not in audit and TEXT not in audit
    observed = call_ledger.summary("embed")
    assert observed["reserved"] == observed["dispatched"] == observed["succeeded"] == 1
    assert observed["failed"] == observed["aborted_unknown"] == 0


@pytest.mark.parametrize("per_model_key", [False, True])
def test_registry_endpoint_fallback_uses_only_its_explicit_auth_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_model_key: bool
) -> None:
    monkeypatch.setenv(PROVIDER_KEY_ENV, PROVIDER_TOKEN)
    monkeypatch.setenv(KEY_ENV, TOKEN)
    headers: list[str | None] = []

    def serve(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == GATEWAY + "/api/embed"
        headers.append(request.headers.get("authorization"))
        return success(request)

    adapter = OllamaEmbeddingProvider(transport=httpx.MockTransport(serve))
    adapter.embed(profile(base="", key_env=KEY_ENV if per_model_key else ""), registry(tmp_path, base=GATEWAY + "/v1"), TEXT, MODEL)

    assert headers == ["Bearer " + (TOKEN if per_model_key else PROVIDER_TOKEN)]


@pytest.mark.parametrize("base", [GATEWAY, "http://127.0.0.1:11436"])
def test_explicit_endpoint_override_does_not_inherit_registry_or_global_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    monkeypatch.setenv(PROVIDER_KEY_ENV, PROVIDER_TOKEN)
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success(request)

    OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(base=base), registry(tmp_path), TEXT, MODEL)

    assert len(requests) == 1 and str(requests[0].url) == base + "/api/embed"
    assert "authorization" not in requests[0].headers


def test_no_explicit_key_preserves_unauthenticated_legacy_request(tmp_path: Path) -> None:
    headers: list[str | None] = []

    def serve(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers.get("authorization"))
        return success(request)

    OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(base=""), registry(tmp_path, key_env=""), TEXT, MODEL)

    assert headers == [None]


def test_missing_explicit_key_does_not_substitute_global_key_or_log_error_body(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, text=TOKEN + TEXT, request=request)

    with caplog.at_level(logging.DEBUG), pytest.raises(OllamaEmbeddingUnavailableError) as error:
        OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(key_env=KEY_ENV), None, TEXT, MODEL)

    assert len(requests) == 1 and "authorization" not in requests[0].headers
    assert "HTTP 401" in str(error.value)
    assert TOKEN not in str(error.value) + caplog.text and TEXT not in str(error.value) + caplog.text
    observed = call_ledger.summary("embed")
    assert observed["reserved"] == observed["dispatched"] == observed["failed"] == 1


def test_authenticated_post_never_follows_redirect_to_another_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, TOKEN)
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/api/embed"}, request=request)

    with pytest.raises(OllamaEmbeddingUnavailableError, match="HTTP 307"):
        OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(key_env=KEY_ENV), None, TEXT, MODEL)

    assert len(requests) == 1 and requests[0].url.host == "127.0.0.1"


@pytest.mark.parametrize("base", [GATEWAY + "?token=value", GATEWAY + "#secret", "http://user:password@127.0.0.1:11435"])
def test_invalid_authenticated_endpoint_is_rejected_before_any_post(monkeypatch: pytest.MonkeyPatch, base: str) -> None:
    monkeypatch.setenv(KEY_ENV, TOKEN)
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success(request)

    with pytest.raises(OllamaEmbeddingUnavailableError, match="base URL is invalid"):
        OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(base=base, key_env=KEY_ENV), None, TEXT, MODEL)

    assert requests == [] and call_ledger.summary("embed")["reserved"] == 0


def test_authentication_does_not_bypass_embedding_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, TOKEN)
    monkeypatch.setenv("AGK_EMBED_MODEL_ALLOWLIST", "different-model")
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success(request)

    with pytest.raises(OllamaEmbeddingUnavailableError, match="not allowlisted"):
        OllamaEmbeddingProvider(transport=httpx.MockTransport(serve)).embed(profile(key_env=KEY_ENV), None, TEXT, MODEL)

    assert requests == [] and call_ledger.summary("embed")["reserved"] == 0
