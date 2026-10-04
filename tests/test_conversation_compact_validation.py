from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from antigravity_k.api.error_handler import APIError, global_exception_handler, validation_exception_handler
from antigravity_k.api.routes import conversation_api
from antigravity_k.engine.conversation_store import ConversationStore
from antigravity_k.engine.project_registry import ProjectRegistry


@dataclass(frozen=True, slots=True)
class CompactBoundary:
    client: TestClient
    project_id: str
    storage: Path


@pytest.fixture()
def boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CompactBoundary]:
    # Given: the real store contains five turns in an isolated registered project.
    storage = tmp_path / "conversations"
    store = ConversationStore(storage_dir=storage)
    registry = ProjectRegistry(storage_path=tmp_path / "projects.json")
    project = tmp_path / "project"
    project.mkdir()
    record = registry.add_project(name="Compact validation QA", path=str(project))
    monkeypatch.setattr(conversation_api, "get_conversation_store", lambda: store)
    monkeypatch.setattr("antigravity_k.api.project_binding.get_conversation_store", lambda: store)
    monkeypatch.setattr("antigravity_k.api.project_binding.get_project_registry", lambda: registry)
    monkeypatch.setattr("antigravity_k.engine.request_execution_context.get_project_registry", lambda: registry)
    monkeypatch.setattr("antigravity_k.config.config.paths.project_root", project)
    monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(tmp_path))
    for revision in range(5):
        store.append(
            project_id=record.id,
            conversation_id="qa-conversation-source",
            expected_revision=revision,
            role="user",
            content=f"Synthetic compact turn {revision}",
        )

    app = FastAPI()
    app.add_exception_handler(APIError, global_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(conversation_api.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield CompactBoundary(client, record.id, storage)


@pytest.mark.parametrize("route", ["/v1/conversations/compact", "/compact"])
@pytest.mark.parametrize("retain_tail", [-1, 10_001])
def test_compact_returns_422_without_mutation_when_tail_is_outside_contract(
    boundary: CompactBoundary, retain_tail: int, route: str
) -> None:
    # Given: persist both the journal and view bytes before the invalid request.
    before = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }

    # When: an invalid tail size enters the actual HTTP route.
    response = boundary.client.post(
        route,
        json={
            "project_id": boundary.project_id,
            "conversation_id": "qa-conversation-source",
            "expected_revision": 5,
            "retain_tail": retain_tail,
        },
    )

    # Then: field-level validation rejects it and all stored bytes remain unchanged.
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert payload["errors"][0]["field"] == "body -> retain_tail"
    after = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize("route", ["/v1/conversations/compact", "/compact"])
@pytest.mark.parametrize("expected", [(0, 1), (2, 3), (6, 5)])
def test_compact_preserves_zero_and_positive_tail_contract(
    boundary: CompactBoundary, route: str, expected: tuple[int, int]
) -> None:
    # Given: the fixture has revision five and five original turns.
    retain_tail, message_count = expected
    # When: a valid tail size enters the same HTTP boundary.
    response = boundary.client.post(
        route,
        json={
            "project_id": boundary.project_id,
            "conversation_id": "qa-conversation-source",
            "expected_revision": 5,
            "retain_tail": retain_tail,
        },
    )

    # Then: CAS succeeds with the established summary/retained-message behavior.
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == boundary.project_id
    assert payload["conversation_id"] == "qa-conversation-source"
    assert payload["revision"] == 6
    assert payload["message_count"] == message_count
    assert len(payload["retained_message_ids"]) == message_count
