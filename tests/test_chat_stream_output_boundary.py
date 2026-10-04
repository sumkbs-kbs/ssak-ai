from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest
from httpx import Response
from pydantic import BaseModel, ConfigDict
from starlette.types import Message, Scope

from antigravity_k.api.contracts import ConversationSnapshot
from antigravity_k.engine.chat_stream_events import (
    FinalChunk,
    ProgressChunk,
    chat_stream_events_enabled,
    reset_chat_stream_events,
    set_chat_stream_events,
)
from tests.chat_boundary_helpers import Boundary, paused_chat_stream
from tests.chat_boundary_helpers import boundary as boundary


class _Status(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str


class _Delta(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str = ""


class _Choice(BaseModel):
    model_config = ConfigDict(frozen=True)
    delta: _Delta


class _Frame(BaseModel):
    model_config = ConfigDict(frozen=True)
    agk_status: _Status | None = None
    agk_final_content: str | None = None
    agk_conversation: ConversationSnapshot | None = None
    choices: tuple[_Choice, ...] = ()


def _frames(response: Response) -> list[_Frame]:
    return [
        _Frame.model_validate_json(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


@pytest.fixture
def completed_stream(boundary: Boundary) -> tuple[Boundary, Response]:
    boundary.runtime.chunks = [ProgressChunk("progress"), "draft-a", "draft-b", FinalChunk("corrected-final")]
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_output",
            "conversation_revision": 0,
            "new_turn": {"role": "user", "content": "날씨 조회"},
            "messages": [{"role": "user", "content": "날씨 조회"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )
    return boundary, response


def test_progress_and_final_use_separate_sse_channels(completed_stream: tuple[Boundary, Response]) -> None:
    _, response = completed_stream

    frames = _frames(response)

    assert response.status_code == 200
    assert [frame.agk_status.text for frame in frames if frame.agk_status is not None] == ["progress"]
    assert [frame.agk_final_content for frame in frames if frame.agk_final_content is not None] == ["corrected-final"]
    assert "".join(choice.delta.content for frame in frames for choice in frame.choices) == "draft-adraft-b"


def test_store_persists_authoritative_final_only(completed_stream: tuple[Boundary, Response]) -> None:
    boundary, _ = completed_stream

    stored = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_output")

    assert stored is not None
    assert stored.revision == 2
    assert [message.role for message in stored.messages] == ["user", "assistant"]
    assert stored.messages[-1].content == "corrected-final"


def test_next_turn_uses_corrected_final_in_authoritative_history(completed_stream: tuple[Boundary, Response]) -> None:
    boundary, previous = completed_stream
    snapshots = [frame.agk_conversation for frame in _frames(previous) if frame.agk_conversation is not None]
    next_revision = snapshots[-1].revision
    boundary.runtime.chunks = ["next-answer"]

    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_output",
            "conversation_revision": next_revision,
            "new_turn": {"role": "user", "content": "Explain a concept in detail"},
            "messages": [{"role": "user", "content": "Explain a concept in detail"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )

    assert response.status_code == 200
    assert [message["content"] for message in boundary.runtime.calls[-1]] == [
        "날씨 조회",
        "corrected-final",
        "Explain a concept in detail",
    ]


def test_completed_stream_keeps_final_history_for_reconnect(completed_stream: tuple[Boundary, Response]) -> None:
    boundary, _ = completed_stream
    from antigravity_k.api.routes.session_state import get_active_session

    response = boundary.client.get("/v1/chat/completions/reconnect")

    assert response.status_code == 200
    assert get_active_session().history == ["corrected-final"]
    assert response.text == "data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_mode", [False, True])
@pytest.mark.parametrize("stream_error", [False, True])
async def test_event_mode_is_restored_after_completion_or_error(
    boundary: Boundary, initial_mode: bool, stream_error: bool
) -> None:
    boundary.runtime.chunks = ["draft"]
    if stream_error:
        boundary.runtime.error = RuntimeError("stream-failure")
    body = json.dumps(
        {
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_scope",
            "conversation_revision": 0,
            "new_turn": {"role": "user", "content": "날씨 조회"},
            "messages": [{"role": "user", "content": "날씨 조회"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        }
    ).encode()
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        del message

    token = set_chat_stream_events(initial_mode)
    try:
        await boundary.app(scope, receive, send)

        assert boundary.runtime.event_modes == [True]
        assert chat_stream_events_enabled() is initial_mode
    finally:
        reset_chat_stream_events(token)


@pytest.mark.asyncio
async def test_accepted_revision_precedes_runtime_and_survives_stream_close(boundary: Boundary) -> None:
    body = json.dumps(
        {
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_cancel",
            "conversation_revision": 0,
            "new_turn": {"role": "user", "content": "original-question"},
            "messages": [{"role": "user", "content": "original-question"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        }
    ).encode()
    response = await paused_chat_stream(boundary, body)
    iterator = response.body_iterator
    assert isinstance(iterator, AsyncGenerator)
    try:
        first = await anext(iterator)
        assert isinstance(first, str)
        frame = _Frame.model_validate_json(first[6:])
        assert frame.agk_conversation is not None
        accepted = frame.agk_conversation
        assert accepted.revision == 1
        assert boundary.runtime.calls == []
    finally:
        await iterator.aclose()

    stopped = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_cancel")
    assert stopped is not None
    assert stopped.revision == accepted.revision
    assert [(message.role, message.content) for message in stopped.messages] == [("user", "original-question")]
    follow_up = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "conversation_id": "conv_cancel",
            "conversation_revision": accepted.revision,
            "new_turn": {"role": "user", "content": "new-question"},
            "messages": [{"role": "user", "content": "new-question"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )

    assert follow_up.status_code == 200
    assert [message["content"] for message in boundary.runtime.calls[-1]] == ["original-question", "new-question"]
    updated = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_cancel")
    assert updated is not None
    assert updated.revision == 3
    assert [(message.role, message.content) for message in updated.messages] == [
        ("user", "original-question"),
        ("user", "new-question"),
        ("assistant", "runtime-answer"),
    ]


def test_legacy_stream_has_no_conversation_snapshot_frame(boundary: Boundary) -> None:
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "messages": [{"role": "user", "content": "original-question"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )

    assert response.status_code == 200
    frames = _frames(response)
    assert all(frame.agk_conversation is None for frame in frames)
    assert "".join(choice.delta.content for frame in frames for choice in frame.choices) == "runtime-answer"
