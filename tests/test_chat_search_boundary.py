from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.api.contracts import ConversationSnapshot
from tests.chat_boundary_helpers import Boundary
from tests.chat_boundary_helpers import boundary as boundary


class _ConversationFrame(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot: ConversationSnapshot = Field(alias="agk_conversation")


@pytest.mark.parametrize("text", ["날씨 조회", "Explain a concept in detail"], ids=["keyword", "llm"])
@pytest.mark.parametrize("disabled", [False, "false", "true", 0, 1])
def test_explicit_disabled_search_uses_policy_runtime(
    boundary: Boundary, text: str, disabled: bool | str | int
) -> None:
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "messages": [{"role": "user", "content": text}],
            "stream": True,
            "agent_mode": True,
            "web_search": disabled,
        },
    )

    assert response.status_code == 200
    assert boundary.searches == []
    assert len(boundary.runtime.calls) == 1
    assert boundary.runtime.search_denials[0] is not None


@pytest.mark.parametrize("enabled", [None, True])
@pytest.mark.parametrize("text", ["날씨 조회", "Explain a concept in detail"], ids=["keyword", "llm"])
def test_legacy_search_remains_available_when_omitted_or_enabled(
    boundary: Boundary, enabled: bool | None, text: str
) -> None:
    payload = {
        "model": "test-model",
        "project_id": boundary.project_id,
        "messages": [{"role": "user", "content": text}],
        "stream": True,
        "agent_mode": True,
    }
    if enabled is not None:
        payload["web_search"] = enabled

    response = boundary.client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert boundary.searches == [text]
    assert boundary.runtime.calls == []
    assert "provider-answer" in response.text


def test_revision_search_stream_persists_answer_and_publishes_current_revision(boundary: Boundary) -> None:
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_search",
            "conversation_revision": 0,
            "new_turn": {"role": "user", "content": "날씨 조회"},
            "messages": [{"role": "user", "content": "날씨 조회"}],
            "stream": True,
            "agent_mode": True,
            "web_search": True,
        },
    )

    assert response.status_code == 200
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    snapshots = [_ConversationFrame.model_validate_json(line).snapshot for line in frames if "agk_conversation" in line]
    assert [snapshot.revision for snapshot in snapshots] == [1, 2]
    assert snapshots[0].message_count == 1
    assert snapshots[1].message_count == 2
    stored = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_search")
    assert stored is not None
    assert [(message.role, message.content) for message in stored.messages] == [
        ("user", "날씨 조회"),
        ("assistant", "runtime-answer"),
    ]
    assert boundary.searches == []
    assert boundary.runtime.search_denials == [None]


def test_next_turn_accepts_revision_published_by_search_stream(boundary: Boundary) -> None:
    previous = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_next",
            "conversation_revision": 0,
            "new_turn": {"role": "user", "content": "날씨 조회"},
            "messages": [{"role": "user", "content": "날씨 조회"}],
            "stream": True,
            "agent_mode": True,
            "web_search": True,
        },
    )
    frames = [line[6:] for line in previous.text.splitlines() if line.startswith("data: ")]
    snapshots = [_ConversationFrame.model_validate_json(line).snapshot for line in frames if "agk_conversation" in line]
    next_revision = snapshots[-1].revision if snapshots else 0

    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_next",
            "conversation_revision": next_revision,
            "new_turn": {"role": "user", "content": "Explain a concept in detail"},
            "messages": [{"role": "user", "content": "Explain a concept in detail"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )

    assert response.status_code == 200
    assert len(boundary.runtime.calls) == 2
    assert [message["role"] for message in boundary.runtime.calls[-1]] == ["user", "assistant", "user"]
    stored = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_next")
    assert stored is not None
    assert stored.revision == 4
