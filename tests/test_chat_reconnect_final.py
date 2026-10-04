from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest
from pydantic import BaseModel, ConfigDict
from starlette.responses import StreamingResponse

from antigravity_k.engine.chat_stream_events import FinalChunk
from tests.chat_boundary_helpers import Boundary
from tests.chat_boundary_helpers import boundary as boundary

if TYPE_CHECKING:
    from antigravity_k.api.routes.session_state import ActiveAgentSession


class _Delta(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str = ""


class _Choice(BaseModel):
    model_config = ConfigDict(frozen=True)
    delta: _Delta


class _Frame(BaseModel):
    model_config = ConfigDict(frozen=True)
    agk_final_content: str | None = None
    choices: tuple[_Choice, ...] = ()


@dataclass(frozen=True, slots=True)
class _Gate:
    reached: anyio.Event
    release: anyio.Event


@dataclass(frozen=True, slots=True)
class _Poller:
    gates: Iterator[_Gate]

    async def __call__(self, delay: float) -> None:
        assert delay == 0.5
        gate = next(self.gates)
        gate.reached.set()
        await gate.release.wait()


@dataclass(frozen=True, slots=True)
class _Reconnect:
    session: ActiveAgentSession
    route: Callable[[], Awaitable[StreamingResponse]]
    install_poller: Callable[[_Poller], None]


@pytest.fixture
def reconnect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Reconnect:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from antigravity_k.api.routes import chat, session_state

    session = session_state.ActiveAgentSession()
    monkeypatch.setattr(session_state, "_active_session", session)

    def install_poller(poller: _Poller) -> None:
        monkeypatch.setattr(chat.asyncio, "sleep", poller)

    return _Reconnect(session, chat.chat_reconnect, install_poller)


async def _collect(response: StreamingResponse, chunks: list[str]) -> None:
    async for chunk in response.body_iterator:
        assert isinstance(chunk, str)
        chunks.append(chunk)


def _frames(chunks: list[str]) -> list[_Frame]:
    return [_Frame.model_validate_json(chunk[6:]) for chunk in chunks if chunk != "data: [DONE]\n\n"]


@pytest.mark.asyncio
@pytest.mark.parametrize("draft_count", [1, 3])
@pytest.mark.parametrize("complete_on_replace", [False, True])
async def test_reconnect_observes_final_snapshot_after_history_shrinks(
    reconnect: _Reconnect, draft_count: int, complete_on_replace: bool
) -> None:
    session = reconnect.session
    session.is_active = True
    session.history[:] = [f"draft-{index}" for index in range(draft_count)]
    gates = [_Gate(anyio.Event(), anyio.Event()), _Gate(anyio.Event(), anyio.Event())]
    reconnect.install_poller(_Poller(iter(gates)))
    response = await reconnect.route()
    chunks: list[str] = []

    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(_collect, response, chunks)
            await gates[0].reached.wait()
            session.history[:] = [FinalChunk("corrected-final")]
            session.is_active = not complete_on_replace
            gates[0].release.set()
            if not complete_on_replace:
                await gates[1].reached.wait()
                session.is_active = False
                gates[1].release.set()

    frames = _frames(chunks)
    assert [frame.agk_final_content for frame in frames if frame.agk_final_content is not None] == ["corrected-final"]
    assert [choice.delta.content for frame in frames for choice in frame.choices] == [
        f"draft-{index}" for index in range(draft_count)
    ]
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_active_reconnect_replays_initial_final_as_replacement(reconnect: _Reconnect) -> None:
    session = reconnect.session
    session.is_active = True
    session.history[:] = [FinalChunk("corrected-final")]
    gate = _Gate(anyio.Event(), anyio.Event())
    reconnect.install_poller(_Poller(iter([gate])))
    response = await reconnect.route()
    chunks: list[str] = []

    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(_collect, response, chunks)
            await gate.reached.wait()
            session.is_active = False
            gate.release.set()

    frames = _frames(chunks)
    assert [frame.agk_final_content for frame in frames] == ["corrected-final"]
    assert all(not frame.choices for frame in frames)
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [None, "stream-failure"])
async def test_reconnect_flushes_legacy_tail_before_completion_or_error(
    reconnect: _Reconnect, error: str | None
) -> None:
    session = reconnect.session
    session.is_active = True
    session.history[:] = ["draft"]
    gate = _Gate(anyio.Event(), anyio.Event())
    reconnect.install_poller(_Poller(iter([gate])))
    response = await reconnect.route()
    chunks: list[str] = []

    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(_collect, response, chunks)
            await gate.reached.wait()
            session.history.append("tail")
            session.error = error
            session.is_active = False
            gate.release.set()

    expected = ["draft", "tail"]
    if error is not None:
        expected.append(f"\n\n[Error: {error}]")
    assert [choice.delta.content for frame in _frames(chunks) for choice in frame.choices] == expected
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [None, "stream-failure"])
async def test_initially_completed_reconnect_preserves_done_only(reconnect: _Reconnect, error: str | None) -> None:
    reconnect.session.history[:] = [FinalChunk("corrected-final")]
    reconnect.session.error = error
    response = await reconnect.route()
    chunks: list[str] = []

    await _collect(response, chunks)

    assert chunks == ["data: [DONE]\n\n"]


def test_stream_producer_preserves_final_chunk_marker_in_history(boundary: Boundary) -> None:
    from antigravity_k.api.routes.session_state import get_active_session

    final = FinalChunk("corrected-final")
    boundary.runtime.chunks = ["draft", final]
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "messages": [{"role": "user", "content": "Explain a concept"}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
        },
    )

    assert response.status_code == 200
    assert get_active_session().history[0] is final
