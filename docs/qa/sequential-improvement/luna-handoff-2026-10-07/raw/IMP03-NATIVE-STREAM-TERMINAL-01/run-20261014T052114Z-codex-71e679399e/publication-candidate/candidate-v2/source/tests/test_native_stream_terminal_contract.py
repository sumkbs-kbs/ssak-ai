import io
import json
import os
import uuid
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from tests.test_chat_structured_output_contract import product as product

TOOLS = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]
CALL = {
    "message": {"tool_calls": [{"function": {"name": "read_file", "arguments": {"file_path": "sentinel"}}}]},
    "done": False,
}


def ndjson(*chunks):
    return b"".join(json.dumps(chunk).encode() + b"\n" for chunk in chunks)


@pytest.fixture
def stream_case(product, monkeypatch, request):
    from antigravity_k.api.routes import messages_api
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.tools import egress_policy

    client, body, _, _, _ = product
    client.app.include_router(messages_api.router)
    manager = client.contract_manager
    original_record = manager.tracker.record
    original_add = SessionManager.add_turn
    state = {"responses": [], "wire": [], "raw": [], "usage": [], "persisted": [], "sleeps": []}

    def terminal(request, **kwargs):
        state["wire"].append(json.loads(request.data))
        result = state["responses"].pop(0)
        state["raw"].append(result.hex() if isinstance(result, bytes) else type(result).__name__)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)

    def record(*args, **kwargs):
        state["usage"].append(kwargs)
        return original_record(*args, **kwargs)

    def add(self, *args, **kwargs):
        state["persisted"].append(args)
        return original_add(self, *args, **kwargs)

    from antigravity_k.engine.provider_adapters import inference_providers

    monkeypatch.setattr(inference_providers, "safe_urlopen", egress_policy.safe_urlopen)
    monkeypatch.setattr(egress_policy.urllib.request, "urlopen", terminal)
    monkeypatch.setattr(egress_policy, "_retry_sleep", state["sleeps"].append)
    monkeypatch.setattr(manager.tracker, "record", record)
    monkeypatch.setattr(SessionManager, "add_turn", add)
    body.update(stream=True, agent_mode=False, max_tokens=128)
    body["messages"][0]["content"] = "안녕"
    yield client, body, manager, state
    export = os.environ.get("NATIVE_STREAM_CAPTURE_ROOT")
    if export:
        target = Path(export)
        target.mkdir(parents=True, exist_ok=True)
        (target / (uuid.uuid4().hex + ".json")).write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "wire": state["wire"],
                    "upstream_hex_or_error_type": state["raw"],
                    "usage": state["usage"],
                    "persisted_turns": len(state["persisted"]),
                    "sleeps": state["sleeps"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


@pytest.mark.parametrize(
    "raw",
    [
        ndjson({"error": "private upstream error"}),
        ndjson(CALL),
        ndjson(CALL) + b"{bad\n",
        ndjson(CALL) + b"\xff\n",
        ndjson(CALL, {"done": 1}),
        ndjson({"message": {"content": '<tool_call>{"name":"read_file","arguments":{}}</tool_call>'}, "done": False}),
    ],
)
def test_incomplete_tool_stream_never_emits_or_retries(stream_case, raw):
    _, body, manager, state = stream_case
    state["responses"] = [raw, raw, raw]
    emitted = []
    with pytest.raises(RuntimeError):
        for piece in manager.stream_generate("read sentinel", body["model"], tools=TOOLS):
            emitted.append(piece)
    assert emitted == []
    assert len(state["wire"]) == 1 and state["sleeps"] == []
    assert [r["success"] for r in state["usage"]] == [False]


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize(
    "raw", [ndjson({"error": "private upstream"}), ndjson({"message": {"content": "partial"}, "done": False})]
)
def test_direct_sse_failure_has_no_success_terminal(stream_case, route, raw):
    client, body, _, state = stream_case
    state["responses"] = [raw]
    response = client.post(route, json=body)
    assert response.status_code == 200
    assert '"provider_protocol_error"' in response.text
    assert "[DONE]" not in response.text and '"type": "message_stop"' not in response.text
    assert "private upstream" not in response.text
    assert [r["success"] for r in state["usage"]] == [False]
    assert state["persisted"] == [] and len(state["wire"]) == 1


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("http://127.0.0.1/api/chat", 500, "private", Message(), io.BytesIO(b'{"error":"failure"}')),
        TimeoutError("private timeout"),
    ],
)
def test_tools_transport_failure_never_falls_back(stream_case, error):
    _, body, manager, state = stream_case
    state["responses"] = [error] * 4
    with pytest.raises(RuntimeError):
        list(manager.stream_generate("read sentinel", body["model"], tools=TOOLS))
    assert len(state["wire"]) == 1 and state["sleeps"] == []


def test_valid_terminal_releases_native_tools(stream_case):
    _, body, manager, state = stream_case
    state["responses"] = [ndjson(CALL, {"done": True})]
    output = "".join(manager.stream_generate("read sentinel", body["model"], tools=TOOLS))
    assert "<tool_call>" in output and "read_file" in output
    assert [r["success"] for r in state["usage"]] == [True]


@pytest.mark.parametrize("completed_first", [False, True])
@pytest.mark.parametrize("next_failure", [ndjson({"error": "private upstream"}), TimeoutError("private timeout")])
def test_real_tool_loop_never_dispatches_incomplete_or_replays_completed_tool(
    stream_case, monkeypatch, tmp_path, completed_first, next_failure
):
    from antigravity_k.engine.tool_loop import ToolLoopEngine
    from tests.test_tool_loop import mock_orch

    _, body, manager, state = stream_case
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("owned read-only sentinel")
    dispatch = []
    outcomes = []
    orch = mock_orch._get_wrapped_function()()
    orch.manager = manager
    orch.project_root = str(tmp_path)
    orch._prepare_agent_prompt.return_value = (
        body["model"],
        "",
        "",
        "",
        "Read sentinel",
        [{"role": "user", "content": "Read sentinel"}],
    )
    manager.get(body["model"])

    async def read_owned(*args, **kwargs):
        dispatch.append("read_file")
        return sentinel.read_text()

    orch.ctx.tool_executor.execute_async = read_owned
    engine = ToolLoopEngine(orch, outcome_recorder=lambda outcome: outcomes.append(outcome))
    monkeypatch.setattr(engine, "_native_tools_kwargs", lambda *args, **kwargs: {"tools": TOOLS})
    first = ndjson(CALL, {"done": True}) if completed_first else ndjson(CALL)
    state["responses"] = [first, next_failure, next_failure]
    list(engine.run_loop([{"role": "user", "content": "Read sentinel"}], "CODER", "code", 3, body["model"]))
    assert dispatch == (["read_file"] if completed_first else [])
    assert len(state["wire"]) == (2 if completed_first else 1)
    assert outcomes and outcomes[-1].success is False
    assert [r["success"] for r in state["usage"]] == ([True, False] if completed_first else [False])
    assert sentinel.read_text() == "owned read-only sentinel"


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
def test_valid_direct_stream_keeps_success_contract(stream_case, route):
    client, body, _, state = stream_case
    state["responses"] = [ndjson({"message": {"content": "valid reply"}, "done": True})]
    response = client.post(route, json=body)
    assert response.status_code == 200 and "valid reply" in response.text
    assert "provider_protocol_error" not in response.text
    assert "[DONE]" in response.text if route.endswith("completions") else "message_stop" in response.text
    assert [r["success"] for r in state["usage"]] == [True]


@pytest.mark.parametrize("content", [["partial"], None, 1, False, {}])
@pytest.mark.parametrize("route", ["/v1/messages", "/v1/chat/completions"])
def test_malformed_content_is_typed_failure_not_success(stream_case, route, content):
    client, body, _, state = stream_case
    state["responses"] = [ndjson({"message": {"content": content}, "done": True})]
    response = client.post(route, json=body)
    assert '"provider_protocol_error"' in response.text
    assert "[DONE]" not in response.text and "message_stop" not in response.text
    assert [r["success"] for r in state["usage"]] == [False]
    assert state["persisted"] == [] and len(state["wire"]) == 1


@pytest.mark.parametrize(
    "message",
    [
        None,
        [],
        {"tool_calls": None},
        {"tool_calls": [None]},
        {"tool_calls": [{"function": None}]},
        {"tool_calls": [{"function": {"name": 1, "arguments": {}}}]},
        {"tool_calls": [{"function": {"name": "read_file", "arguments": "{}"}}]},
    ],
)
def test_malformed_message_or_tool_fields_never_dispatch(stream_case, message):
    _, body, manager, state = stream_case
    state["responses"] = [ndjson({"message": message, "done": True})]
    emitted = []
    with pytest.raises(RuntimeError):
        for chunk in manager.stream_generate("read sentinel", body["model"], tools=TOOLS):
            emitted.append(chunk)
    assert emitted == []
    assert [r["success"] for r in state["usage"]] == [False]


@pytest.mark.parametrize("route", ["/v1/messages", "/v1/chat/completions"])
def test_empty_string_content_with_valid_done_remains_success(stream_case, route):
    client, body, _, state = stream_case
    state["responses"] = [ndjson({"message": {"content": ""}, "done": True})]
    response = client.post(route, json=body)
    assert response.status_code == 200 and "provider_protocol_error" not in response.text
    assert "[DONE]" in response.text if route.endswith("completions") else "message_stop" in response.text
    assert [r["success"] for r in state["usage"]] == [True]
