from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from antigravity_k.api.dependencies import get_model_manager
from antigravity_k.api.routes.models_api import router
from antigravity_k.engine.local_model_discovery import DiscoveredLocalModel, LocalModelDiscovery
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.model_registry import ModelRegistry


@pytest.fixture
def model_registry(tmp_path: Path) -> ModelRegistry:
    config_path = tmp_path / "models.yaml"
    config_path.write_text(
        """models:
  reasoning:
    - name: qwen3.8
      repo: qwen3.8:latest
      provider: ollama
      parameter_count_b: 27
    - name: qwen3.8:125b
      repo: qwen3.8:125b
      provider: ollama
      parameter_count_b: 125
defaults:
  reasoning: qwen3.8
""",
        encoding="utf-8",
    )
    return ModelRegistry(str(config_path))


@pytest.fixture
def model_client(model_registry: ModelRegistry) -> Iterator[TestClient]:
    manager = ModelManager(model_registry)
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_model_manager] = lambda: manager
    with TestClient(application) as client:
        yield client


@pytest.fixture
def discovered_models(monkeypatch: MonkeyPatch) -> list[DiscoveredLocalModel]:
    models = [
        DiscoveredLocalModel(
            name="qwen3.8:125b",
            repo="qwen3.8:125b",
            provider="ollama",
            api_base="http://localhost:11434",
            role="reasoning",
            parameter_count_b=125,
            status="running",
        ),
        DiscoveredLocalModel(
            name="qwen3.8:latest",
            repo="qwen3.8:latest",
            provider="ollama",
            api_base="http://localhost:11434",
            role="reasoning",
            parameter_count_b=27,
            status="running",
        ),
    ]
    monkeypatch.setattr(LocalModelDiscovery, "discover", lambda self: models)
    return models


@pytest.mark.parametrize("model_name", ["qwen3.8", "qwen3.8:latest"])
@pytest.mark.parametrize("status", ["running", "installed", "cached"])
def test_recommends_configured_model_when_larger_model_is_discovered(
    model_client: TestClient,
    discovered_models: list[DiscoveredLocalModel],
    model_name: str,
    status: str,
) -> None:
    # Given: the configured 27B model is present alongside a running 125B model.
    discovered_models[1] = replace(discovered_models[1], name=model_name, status=status)

    # When: a client without a saved preference asks for a recommendation.
    response = model_client.get("/api/models/local")

    # Then: the configured alias resolves to the discovered ID, and both remain selectable.
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_default"] == model_name
    assert {model["id"] for model in data["models"]} == {model_name, "qwen3.8:125b"}


@pytest.mark.parametrize("role", ["coding", "general"])
def test_recommends_configured_model_when_discovered_with_chat_role(
    model_client: TestClient,
    discovered_models: list[DiscoveredLocalModel],
    role: str,
) -> None:
    # Given: discovery identifies the configured model as a compatible chat role.
    discovered_models[1] = replace(discovered_models[1], role=role)

    # When: the local-model endpoint recommends a default.
    response = model_client.get("/api/models/local")

    # Then: the configured 27B model retains precedence.
    assert response.status_code == 200
    assert response.json()["recommended_default"] == "qwen3.8:latest"


@pytest.mark.parametrize("default_name", ["qwen3.8", "missing-model", None])
def test_preserves_fallback_when_configured_model_is_unavailable(
    model_registry: ModelRegistry,
    model_client: TestClient,
    discovered_models: list[DiscoveredLocalModel],
    default_name: str | None,
) -> None:
    # Given: no discovered model matches the configured reasoning default.
    model_registry.defaults.reasoning = default_name
    discovered_models.pop()

    # When: the local-model endpoint recommends a default.
    response = model_client.get("/api/models/local")

    # Then: the existing recommendation remains the available 125B model.
    assert response.status_code == 200
    assert response.json()["recommended_default"] == "qwen3.8:125b"


@pytest.mark.parametrize("role", ["embedding", "vision"])
def test_preserves_fallback_when_configured_model_has_incompatible_role(
    model_client: TestClient,
    discovered_models: list[DiscoveredLocalModel],
    role: str,
) -> None:
    # Given: the configured model is discovered for a non-chat role.
    discovered_models[1] = replace(discovered_models[1], role=role)

    # When: the local-model endpoint recommends a default.
    response = model_client.get("/api/models/local")

    # Then: the usable reasoning model remains the fallback.
    assert response.status_code == 200
    assert response.json()["recommended_default"] == "qwen3.8:125b"
