from __future__ import annotations

import json
from typing import Self
from unittest.mock import patch
from urllib.request import Request

import pytest
from pydantic import JsonValue

from antigravity_k.engine.local_model_discovery import LocalModelDiscovery


class _Body:
    _payload: bytes

    def __init__(self, payload: JsonValue) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: None) -> None:
        return None


def _discover_statuses(process_payload: JsonValue) -> dict[str, str]:
    def respond(request: Request, timeout: float) -> _Body:
        assert timeout > 0
        if request.full_url.endswith("/api/tags"):
            return _Body({"models": [{"name": "qa-running:latest"}, {"name": "qa-installed:latest"}]})
        assert request.full_url.endswith("/api/ps")
        return _Body(process_payload)

    discovery = LocalModelDiscovery(model_dirs=(), openai_endpoints=())
    with patch("antigravity_k.engine.local_model_discovery.safe_urlopen", side_effect=respond):
        return {model.name: model.status for model in discovery.discover()}


def test_only_resident_model_is_running_when_catalog_contains_two_models() -> None:
    # Given a catalog with two installed models and one resident process.
    processes: JsonValue = {"models": [{"name": "qa-running:latest"}]}
    # When production discovery reads the runtime catalogs.
    statuses = _discover_statuses(processes)
    # Then only the resident model is running.
    assert statuses == {"qa-running:latest": "running", "qa-installed:latest": "installed"}


def test_models_remain_installed_when_process_list_is_empty() -> None:
    # Given an installed catalog with no resident process.
    # When production discovery reads a valid empty process list.
    statuses = _discover_statuses({"models": []})
    # Then no model is represented as running.
    assert set(statuses.values()) == {"installed"}


MALFORMED_PROCESSES: tuple[JsonValue, ...] = (
    None,
    {},
    {"models": None},
    {"models": [42]},
    {"models": [{}]},
    {"models": [{"name": "   "}]},
)


@pytest.mark.parametrize("payload", MALFORMED_PROCESSES)
def test_runtime_status_is_unknown_when_process_response_is_malformed(payload: JsonValue) -> None:
    # Given a process response whose resident inventory cannot be established.
    # When production discovery reads it.
    statuses = _discover_statuses(payload)
    # Then inventory remains visible without asserting runtime readiness.
    assert set(statuses.values()) == {"unknown"}


def test_model_alias_is_recognized_when_process_response_uses_model_field() -> None:
    # Given Ollama's alternate model identity field.
    # When discovery parses the actual process response.
    statuses = _discover_statuses({"models": [{"model": "qa-running:latest"}]})
    # Then the matching model is resident and the other is installed.
    assert statuses == {"qa-running:latest": "running", "qa-installed:latest": "installed"}


def test_runtime_status_is_unknown_when_process_request_is_unavailable() -> None:
    # Given a readable installed catalog and an unavailable process endpoint.
    discovery = LocalModelDiscovery(model_dirs=(), openai_endpoints=())
    responses = [_Body({"models": [{"name": "qa-installed:latest"}]}), OSError("Synthetic runtime unavailable")]
    # When production discovery makes the read-only HTTP requests.
    with patch("antigravity_k.engine.local_model_discovery.safe_urlopen", side_effect=responses):
        models = discovery.discover()
    # Then installed inventory remains visible with unknown runtime status.
    assert [(model.name, model.status) for model in models] == [("qa-installed:latest", "unknown")]
