from __future__ import annotations

from pathlib import Path
from typing import override

import anyio
import pytest
from pydantic import BaseModel
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send

from antigravity_k.api.chat_agent_stream_generator import AgentStreamingResponse
from tests.chat_boundary_helpers import Boundary
from tests.chat_boundary_helpers import boundary as boundary
from tests.test_chat_stream_cancel_cleanup import ClosableBody, actual_lane, assert_cancelled, request_body


class ResponseFrame(BaseModel):
    body: bytes = b""


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version,cancel_stage", [("2.3", "token"), ("2.4", "token"), ("2.4", "headers")])
async def test_asgi_send_disconnect_closes_runtime_before_response_released(
    boundary: Boundary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec_version: str, cancel_stage: str
) -> None:
    from antigravity_k.api.routes import chat

    lane = actual_lane(tmp_path, monkeypatch)
    retained: list[ClosableBody] = []

    class CapturingResponse(AgentStreamingResponse):
        @override
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            assert isinstance(self.body_iterator, ClosableBody)
            retained.append(self.body_iterator)
            await super().__call__(scope, receive, send)

    monkeypatch.setattr(chat, "AgentStreamingResponse", CapturingResponse)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
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
    sent_model_token = False
    disconnect = anyio.Event()
    request_received = False

    async def receive() -> Message:
        nonlocal request_received
        if request_received:
            await disconnect.wait()
            return {"type": "http.disconnect"}
        request_received = True
        return {"type": "http.request", "body": request_body(boundary), "more_body": False}

    async def send(message: Message) -> None:
        nonlocal sent_model_token
        if cancel_stage == "headers" and message["type"] == "http.response.start":
            raise OSError("client disconnected before response headers")
        body = ResponseFrame.model_validate(message).body
        if message["type"] == "http.response.body" and b'"content": "42"' in body:
            sent_model_token = True
            if spec_version == "2.4":
                raise OSError("client disconnected after a real model token")
            disconnect.set()
            await anyio.sleep_forever()

    try:
        if spec_version == "2.4":
            with pytest.raises(ClientDisconnect):
                await boundary.app(scope, receive, send)
        else:
            await boundary.app(scope, receive, send)
        assert len(retained) == 1
        if cancel_stage == "headers":
            assert lane.model.requests == []
            assert lane.runner.list_tasks() == []
            from antigravity_k.api.routes import session_state

            assert session_state.get_active_session().is_active is False
            assert session_state.get_active_session().error is None
        else:
            assert sent_model_token
            assert_cancelled(lane)
            task_id = str(lane.runner.list_tasks()[0]["task_id"])
            events = lane.runner.state_store.list_execution_events(task_id)
            await retained[0].aclose()
            assert lane.runner.state_store.list_execution_events(task_id) == events
    finally:
        for iterator in retained:
            await iterator.aclose()
