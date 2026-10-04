from __future__ import annotations

import pytest

from .test_conversation_compact_validation import CompactBoundary
from .test_conversation_compact_validation import boundary as boundary


@pytest.mark.parametrize("invalid", [("expected_revision", -1), ("role", "moderator")])
def test_append_returns_422_without_mutation_when_request_is_invalid(
    boundary: CompactBoundary, invalid: tuple[str, str | int]
) -> None:
    # Given: a real persisted source and an invalid declared request field.
    field, value = invalid
    before = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }
    body = {
        "project_id": boundary.project_id,
        "conversation_id": "qa-conversation-source",
        "expected_revision": 5,
        "role": "user",
        "content": "QA_REJECTED_INPUT",
    }
    body[field] = value

    # When: the invalid payload enters the production append route.
    response = boundary.client.post("/v1/conversations/append", json=body)

    # Then: validation identifies the field and journal/view bytes stay unchanged.
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert payload["errors"][0]["field"] == "body -> " + field
    after = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }
    assert after == before


def test_fork_returns_422_without_mutation_when_revision_is_negative(boundary: CompactBoundary) -> None:
    # Given: both source view and original journal exist at revision five.
    before = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }

    # When: a negative expected revision enters the production fork route.
    response = boundary.client.post(
        "/v1/conversations/fork",
        json={
            "project_id": boundary.project_id,
            "conversation_id": "qa-conversation-source",
            "expected_revision": -1,
            "new_conversation_id": "qa-invalid-fork",
        },
    )

    # Then: validation rejects the revision without creating a fork or changing originals.
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert payload["errors"][0]["field"] == "body -> expected_revision"
    after = {
        path.relative_to(boundary.storage): path.read_bytes() for path in boundary.storage.rglob("*") if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_append_preserves_valid_role_and_cas_revision(boundary: CompactBoundary, role: str) -> None:
    # Given: an existing registered conversation is at revision five.
    # When: a valid role and matching revision enter the typed boundary.
    response = boundary.client.post(
        "/v1/conversations/append",
        json={
            "project_id": boundary.project_id,
            "conversation_id": "qa-conversation-source",
            "expected_revision": 5,
            "role": role,
            "content": "QA_ACCEPTED_APPEND",
        },
    )

    # Then: the existing append contract advances that conversation by one turn.
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == boundary.project_id
    assert payload["conversation_id"] == "qa-conversation-source"
    assert payload["revision"] == 6
    assert payload["message_count"] == 6
    persisted = boundary.client.get(f"/v1/conversations/qa-conversation-source?project_id={boundary.project_id}")
    assert persisted.status_code == 200, persisted.text
    latest = persisted.json()["messages"][-1]
    assert (latest["role"], latest["content"]) == (role, "QA_ACCEPTED_APPEND")


def test_fork_preserves_explicit_target_and_source_snapshot(boundary: CompactBoundary) -> None:
    # Given: an existing source contains five original turns.
    # When: a valid matching revision and explicit target enter the fork boundary.
    response = boundary.client.post(
        "/v1/conversations/fork",
        json={
            "project_id": boundary.project_id,
            "conversation_id": "qa-conversation-source",
            "expected_revision": 5,
            "new_conversation_id": "qa-valid-fork",
        },
    )

    # Then: the new fork preserves all source turns and starts at revision zero.
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == boundary.project_id
    assert payload["conversation_id"] == "qa-valid-fork"
    assert payload["revision"] == 0
    assert payload["message_count"] == 5
    persisted = boundary.client.get(f"/v1/conversations/qa-valid-fork?project_id={boundary.project_id}")
    assert persisted.status_code == 200, persisted.text
    copied = [(message["role"], message["content"]) for message in persisted.json()["messages"]]
    assert copied == [("user", f"Synthetic compact turn {revision}") for revision in range(5)]
