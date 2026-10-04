from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api.routes import system_api
from antigravity_k.tools import web_search_tool
from antigravity_k.tools.ssak_search_provider import SsakSearchSettings


@pytest.fixture
def client() -> Iterator[TestClient]:
    application = FastAPI()
    application.include_router(system_api.router)
    with TestClient(application) as test_client:
        yield test_client


def test_settings_use_active_config_when_override_differs_from_workspace(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: distinct explicit and workspace configurations with synthetic values.
    workspace = tmp_path / "workspace"
    module_path = workspace / "src/antigravity_k/api/routes/system_api.py"
    module_path.parent.mkdir(parents=True)
    (workspace / "config.yaml").write_text("qa_marker: workspace\n", encoding="utf-8")
    active_config = tmp_path / "active.yaml"
    active_config.write_text("qa_marker: active\n", encoding="utf-8")
    monkeypatch.setattr(system_api, "__file__", str(module_path))
    monkeypatch.setattr(system_api.config, "config_path", active_config)
    monkeypatch.setenv("AGK_CONFIG_FILE", str(active_config))
    monkeypatch.setenv("AGK_ENV_FILE", str(tmp_path / "absent.env"))

    # When: requesting settings through the real route.
    response = client.get("/api/settings")

    # Then: the active configuration wins over the repository-relative fallback.
    assert response.status_code == 200
    assert response.json()["settings"]["qa_marker"] == "active"


def test_settings_scrub_secrets_when_active_config_contains_credentials(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: synthetic secrets in an explicitly selected configuration.
    active_config = tmp_path / "active.yaml"
    active_config.write_text(
        "qa_marker: active\napi_keys:\n  fake: SYNTHETIC_SECRET\nsecurity:\n  access_pin: SYNTHETIC_PIN\n",
        encoding="utf-8",
    )
    module_path = tmp_path / "workspace/src/antigravity_k/api/routes/system_api.py"
    monkeypatch.setattr(system_api, "__file__", str(module_path))
    monkeypatch.setattr(system_api.config, "config_path", active_config)
    monkeypatch.setenv("AGK_ENV_FILE", str(tmp_path / "absent.env"))

    # When: requesting the selected configuration.
    response = client.get("/api/settings")

    # Then: source selection does not bypass the existing secret scrubber.
    assert response.json()["settings"]["qa_marker"] == "active"
    assert "SYNTHETIC_SECRET" not in response.text
    assert "SYNTHETIC_PIN" not in response.text


def test_extract_returns_failure_when_real_search_tool_rejects_provider_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the real producer emits Search Error: for an invalid provider setup.
    settings = SsakSearchSettings(enabled=True, problem="synthetic invalid provider configuration")
    monkeypatch.setattr(web_search_tool, "settings_snapshot", lambda: settings)

    # When: searching through the production extraction route.
    response = client.post("/api/search/extract", json={"query": "qa-provider-boundary"})

    # Then: unavailable search cannot masquerade as successfully extracted emptiness.
    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "search_unavailable"}


@pytest.mark.parametrize(
    "result",
    [
        "[웹 검색] 'qa-empty' — 결과 없음",
        '[웹 검색] qa-data\nArticle quotes Search Error: and {"error":"example"}.',
    ],
)
def test_extract_keeps_success_when_provider_returns_valid_empty_or_quoted_text(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    result: str,
) -> None:
    # Given: provider text has no data, or quotes a failure token inside a source.
    def provider_result(_tool: web_search_tool.WebSearchTool, **_kwargs: str) -> str:
        return result

    monkeypatch.setattr(web_search_tool.WebSearchTool, "execute", provider_result)

    # When: running the actual extraction parser and serialization route.
    response = client.post("/api/search/extract", json={"query": "qa-empty"})

    # Then: legitimate empty results and arbitrary article content remain successful.
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["extracted"]["numeric_data"] == []
