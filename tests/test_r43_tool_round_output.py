"""Tool-round prose is progress; only a terminal provider round is the answer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from antigravity_k.engine.chat_stream_events import ProgressChunk, reset_chat_stream_events, set_chat_stream_events
from antigravity_k.engine.provider_adapters.transport_errors import NativeTransportError, TransportFailure
from tests.test_tool_loop import _engine, _set_mock_return, _set_mock_side_effect
from tests.test_tool_loop import mock_orch as mock_orch


@pytest.mark.parametrize("split", [False, True])
def test_tool_round_prose_does_not_become_answer(mock_orch: MagicMock, split: bool) -> None:
    first = [
        "draft differs from final",
        '<tool_call>{"name":"read_file","arguments":{"file_path":"note.md"}}</tool_call>',
    ]
    if split:
        first = [
            "draft differs ",
            "from final<tool_",
            'call>{"name":"read_file","arguments":{"file_path":"note.md"}}</tool_',
            "call>",
        ]
    _set_mock_side_effect(mock_orch, ("manager", "stream_generate"), [iter(first), iter(["FINAL-7342"])])
    engine = _engine(mock_orch)

    async def execute(tc, user_task=""):
        return tc, None, None, "tool result seam", False

    engine._run_tool_task_async = AsyncMock(side_effect=execute)
    token = set_chat_stream_events(True)
    try:
        chunks = list(
            engine.run_loop(
                [{"role": "user", "content": "Recall badge identifier"}], "SELF", "chat", target_model="test-model"
            )
        )
    finally:
        reset_chat_stream_events(token)
    assert "".join(c for c in chunks if not isinstance(c, ProgressChunk)) == "FINAL-7342"
    assert engine.last_output == "FINAL-7342"
    assert "draft differs from final" in "".join(c for c in chunks if isinstance(c, ProgressChunk))


def test_terminal_repeated_text_is_preserved(mock_orch: MagicMock) -> None:
    text = "same identifier\n\nsame identifier"
    _set_mock_return(mock_orch, ("manager", "stream_generate"), iter([text]))
    token = set_chat_stream_events(True)
    try:
        engine = _engine(mock_orch)
        chunks = list(
            engine.run_loop([{"role": "user", "content": "Echo twice"}], "SELF", "chat", target_model="test-model")
        )
    finally:
        reset_chat_stream_events(token)
    assert "".join(c for c in chunks if not isinstance(c, ProgressChunk)) == text
    assert engine.last_output == text


@pytest.mark.parametrize("approval", [False, True], ids=["step-limit", "approval"])
def test_nonterminal_tool_round_never_commits_its_draft(mock_orch: MagicMock, approval: bool) -> None:
    _set_mock_return(
        mock_orch,
        ("manager", "stream_generate"),
        iter(["UNCOMMITTED-DRAFT", '<tool_call>{"name":"read_file","arguments":{"file_path":"note.md"}}</tool_call>']),
    )
    engine = _engine(mock_orch)

    async def execute(tc, user_task=""):
        return tc, None, None, "[APPROVAL REQUIRED] confirm" if approval else "tool result seam", False

    engine._run_tool_task_async = AsyncMock(side_effect=execute)
    token = set_chat_stream_events(True)
    try:
        chunks = list(
            engine.run_loop(
                [{"role": "user", "content": "Recall"}], "SELF", "chat", max_steps=1, target_model="test-model"
            )
        )
    finally:
        reset_chat_stream_events(token)
    assert "UNCOMMITTED-DRAFT" not in engine.last_output
    assert "UNCOMMITTED-DRAFT" not in "".join(c for c in chunks if not isinstance(c, ProgressChunk))
    assert engine.approval_required is approval


def test_failed_provider_round_does_not_publish_partial_answer(mock_orch: MagicMock) -> None:
    def broken():
        yield "partial unverified draft"
        raise NativeTransportError(TransportFailure.UNAVAILABLE)

    _set_mock_return(mock_orch, ("manager", "stream_generate"), broken())
    token = set_chat_stream_events(True)
    try:
        engine = _engine(mock_orch)
        chunks = list(
            engine.run_loop([{"role": "user", "content": "Recall"}], "SELF", "chat", target_model="test-model")
        )
    finally:
        reset_chat_stream_events(token)
    assert "".join(c for c in chunks if not isinstance(c, ProgressChunk)) == ""


@pytest.mark.parametrize("events", [False, True], ids=["legacy-task", "completed-contract"])
def test_final_or_legacy_stream_remains_eager(mock_orch: MagicMock, events: bool) -> None:
    consumed: list[str] = []

    def live():
        consumed.append("first")
        yield "first chunk.\n"
        consumed.append("last")
        yield "last chunk.\n"

    _set_mock_return(mock_orch, ("manager", "stream_generate"), live())
    token = set_chat_stream_events(events)
    engine = _engine(mock_orch)
    if events:
        engine._expected_tools = lambda: ("read_file",)
        engine._resumed_tool_loop_state = lambda: (["read_file"], "persisted evidence")
    stream = engine.run_loop([{"role": "user", "content": "Recall"}], "SELF", "chat", target_model="test-model")
    try:
        while True:
            chunk = next(stream)
            if not isinstance(chunk, ProgressChunk):
                break
        assert chunk and "first chunk.\n".startswith(chunk) and consumed == ["first"]
    finally:
        stream.close()
        reset_chat_stream_events(token)
