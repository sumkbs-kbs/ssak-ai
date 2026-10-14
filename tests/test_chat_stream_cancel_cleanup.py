from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from pathlib import Path
from typing import Protocol, runtime_checkable

import anyio
import pytest
from anyio.to_thread import run_sync
from pydantic import BaseModel
from starlette.responses import Content

from tests.chat_boundary_helpers import Boundary, paused_chat_stream
from tests.chat_boundary_helpers import boundary as boundary
from tests.real_runtime_task_event_helpers import ExecutionLane, make_lane
from tests.test_real_runtime_task_events import LifecyclePayload


class Delta(BaseModel):
    content: str | None = None


class Choice(BaseModel):
    delta: Delta


class Frame(BaseModel):
    agk_final_content: str | None = None
    choices: tuple[Choice, ...] = ()


@runtime_checkable
class ClosableBody(Protocol):
    def __aiter__(self) -> AsyncIterator[Content]: ...
    async def __anext__(self) -> Content: ...
    def aclose(self) -> Awaitable[None]: ...


async def close_body(iterator: ClosableBody) -> None:
    await iterator.aclose()


def request_body(boundary: Boundary, *, revision: int = 0, prompt: str = "도구 없이 13+29의 숫자 하나") -> bytes:
    return json.dumps(
        {
            "model": "qa-local",
            "project_id": boundary.project_id,
            "conversation_id": "conv_cancel_owner",
            "conversation_revision": revision,
            "new_turn": {"role": "user", "content": prompt},
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
            "code_mode": False,
        }
    ).encode()


def actual_lane(root: Path, monkeypatch: pytest.MonkeyPatch, *, block: bool = False) -> ExecutionLane:
    from antigravity_k.api.routes import chat

    lane = make_lane(root, monkeypatch, block=block)
    monkeypatch.setattr(chat, "get_agent_runtime", lambda: lane.runtime)
    return lane


async def body_iterator(boundary: Boundary) -> ClosableBody:
    response = await paused_chat_stream(boundary, request_body(boundary))
    iterator = response.body_iterator
    assert isinstance(iterator, ClosableBody)
    return iterator


async def consume_model_chunk(iterator: ClosableBody) -> None:
    for _ in range(20):
        raw = await anext(iterator)
        text = raw if isinstance(raw, str) else bytes(raw).decode()
        if text.startswith("data: ") and "[DONE]" not in text:
            frame = Frame.model_validate_json(text[6:].strip())
            if any(choice.delta.content == "42" for choice in frame.choices):
                return
    raise AssertionError("actual ToolLoop must yield a model token before cancellation")


def assert_cancelled(lane: ExecutionLane) -> None:
    tasks = lane.runner.list_tasks(limit=20)
    assert len(tasks) == 1
    task_id = str(tasks[0]["task_id"])
    record = lane.runner.state_store.get_task(task_id)
    assert record is not None and record["status"] == "cancelled" and record["error"] is None
    assert record["output"] == "42"
    events = lane.runner.state_store.list_execution_events(task_id)
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    terminal = [event for event in events if event["event_type"] == "interactive_cancelled"]
    assert len(terminal) == 1
    statuses = [
        LifecyclePayload.model_validate_json(event["payload_json"])
        for event in events
        if event["event_type"] == "task.status"
    ]
    assert [status.to_status for status in statuses if status.terminal] == ["cancelled"]
    assert statuses[-1].to_version == record["version"]
    assert statuses[-1].from_status == "running"
    assert statuses[-1].to_version == statuses[-1].from_version + 1
    assert lane.orchestrator.task_execution_context is None
    from antigravity_k.api.routes import session_state
    from antigravity_k.engine.chat_stream_events import chat_stream_events_enabled
    from antigravity_k.engine.task_execution_context import current_task_execution_context

    assert chat_stream_events_enabled() is False
    assert current_task_execution_context() is None
    assert session_state.get_active_session().is_active is False
    assert session_state.get_active_session().error is None
    from antigravity_k.engine.tool_policy import tool_policy_denial

    assert tool_policy_denial("web_search", None) is None


@pytest.mark.asyncio
async def test_mid_token_aclose_from_other_task_closes_actual_runtime(
    boundary: Boundary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = actual_lane(tmp_path, monkeypatch)
    iterator = await body_iterator(boundary)
    await consume_model_chunk(iterator)
    async with anyio.create_task_group() as group:
        group.start_soon(close_body, iterator)
    assert_cancelled(lane)
    events = lane.runner.state_store.list_execution_events(str(lane.runner.list_tasks()[0]["task_id"]))
    await close_body(iterator)
    assert lane.runner.state_store.list_execution_events(str(lane.runner.list_tasks()[0]["task_id"])) == events
    response = await paused_chat_stream(boundary, request_body(boundary, revision=1, prompt="도구 없이 6*7 숫자 하나"))
    chunks = [chunk async for chunk in response.body_iterator]
    assert any('"agk_final_content": "42"' in str(chunk) for chunk in chunks)
    tasks = lane.runner.list_tasks(limit=20)
    assert sorted(str(task["status"]) for task in tasks) == ["cancelled", "done"]
    for task in tasks:
        record = lane.runner.state_store.get_task(str(task["task_id"]))
        assert record is not None and record["error"] is None
        if record["status"] == "done":
            assert record["output"] == "42"


@pytest.mark.asyncio
async def test_before_first_runtime_close_from_other_task_does_not_leak_policy(
    boundary: Boundary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = actual_lane(tmp_path, monkeypatch)
    iterator = await body_iterator(boundary)
    first = await anext(iterator)
    assert "agk_conversation" in str(first)
    async with anyio.create_task_group() as group:
        group.start_soon(close_body, iterator)
    assert lane.model.requests == []
    assert lane.runner.list_tasks() == []
    from antigravity_k.api.routes import session_state
    from antigravity_k.engine.chat_stream_events import chat_stream_events_enabled

    assert chat_stream_events_enabled() is False
    assert session_state.get_active_session().is_active is False


@pytest.mark.asyncio
async def test_inflight_model_pull_cancel_closes_owner_context_once(
    boundary: Boundary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = actual_lane(tmp_path, monkeypatch, block=True)
    iterator = await body_iterator(boundary)

    async def consume() -> None:
        async for _ in iterator:
            pass

    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        assert await run_sync(lane.model.entered.wait, 5)
        group.cancel_scope.cancel()
        lane.model.release.set()
    assert_cancelled(lane)
