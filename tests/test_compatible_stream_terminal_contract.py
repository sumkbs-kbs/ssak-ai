import json
import os
import uuid
from pathlib import Path

import pytest

from tests.test_chat_structured_output_contract import product as product
from tests.test_compatible_transport_error_contract import compat_case as compat_case

TOOLS = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]


def frame(delta, finish=None):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def wire(*chunks, done=True):
    return b"".join(b"data: " + json.dumps(chunk).encode() + b"\n\n" for chunk in chunks) + (
        b"data: [DONE]\n\n" if done else b""
    )


CALL = frame(
    {
        "tool_calls": [
            {
                "index": 0,
                "id": "call_owned",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"file_path":"sentinel"}'},
            }
        ]
    },
    "tool_calls",
)
ERROR = {"error": {"code": 500, "message": "private upstream detail"}}


@pytest.fixture
def terminal_case(compat_case, request):
    client, body, state, provider = compat_case
    captures = []
    yield client, body, state, captures
    export = os.environ.get("COMPAT_STREAM_CAPTURE_ROOT")
    if export:
        target = Path(export)
        target.mkdir(parents=True, exist_ok=True)
        (target / (uuid.uuid4().hex + ".json")).write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "provider": provider,
                    "captures": captures,
                    "wire": state["wire"],
                    "usage": state["usage"],
                    "persisted": len(state["persisted"]),
                    "sleeps": state["sleeps"],
                },
                indent=2,
            )
        )


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize(
    "payload,code",
    [
        (wire(ERROR), "upstream_stream_error"),
        (wire(frame({}, "error")), "upstream_stream_error"),
        (b"data: broken\n\ndata: [DONE]\n\n", "invalid_stream"),
        (b"data: \xff\n\n", "invalid_stream"),
        (wire(frame({"content": ["partial"]})), "invalid_stream"),
        (wire(frame({"content": 1})), "invalid_stream"),
        (wire(frame({"tool_calls": [{"index": 0, "function": {"name": 1}}]})), "invalid_stream"),
        (wire(frame({"tool_calls": [{"index": 0, "function": {"arguments": {}}}]})), "invalid_stream"),
        (wire(frame({"content": "partial"}), done=False), "incomplete_stream"),
    ],
)
def test_bad_sse_is_typed_failed_terminal(terminal_case, route, payload, code):
    client, body, state, captures = terminal_case
    state["outcome"] = [payload]
    response = client.post(route, json={**body, "stream": True})
    captures.append({"upstream_hex": payload.hex(), "response": response.text})
    assert "provider_protocol_error" in response.text and code in response.text
    assert "[DONE]" not in response.text and "message_stop" not in response.text
    assert "private upstream" not in response.text
    assert [row["success"] for row in state["usage"]] == [False]
    assert len(state["wire"]) == 1 and state["persisted"] == [] and state["sleeps"] == []


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
def test_normal_nullable_multiline_comments_and_usage_remain_success(terminal_case, route):
    client, body, state, captures = terminal_case
    payload = b': OPENROUTER PROCESSING\n\ndata: {\ndata: "choices":[{"delta":{"content":null}}]}\n\n' + wire(
        frame({"content": "[API Error] literal"}, "stop"),
        {**frame({"content": ""}, "stop"), "usage": {"completion_tokens": 1}},
        {"choices": [], "usage": {}},
    )
    state["outcome"] = [payload]
    response = client.post(route, json={**body, "stream": True})
    captures.append({"upstream_hex": payload.hex(), "response": response.text})
    assert "[API Error] literal" in response.text and "provider_protocol_error" not in response.text
    assert "[DONE]" in response.text if route.endswith("completions") else "message_stop" in response.text
    assert [row["success"] for row in state["usage"]] == [True]


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("completed_first", [False, True])
def test_real_tool_loop_holds_incomplete_tools_and_never_replays(terminal_case, monkeypatch, tmp_path, completed_first):
    from antigravity_k.engine.tool_loop import ToolLoopEngine
    from antigravity_k.tools import egress_policy
    from tests.test_tool_loop import mock_orch

    client, body, state, captures = terminal_case
    manager = client.contract_manager
    first = wire(CALL, done=completed_first)
    responses = [first, wire(ERROR)]
    terminal = egress_policy.urllib.request.OpenerDirector.open

    def next_response(opener, target, **kwargs):
        state["outcome"] = [responses[min(len(state["wire"]), 1)]]
        return terminal(opener, target, **kwargs)

    monkeypatch.setattr(egress_policy.urllib.request.OpenerDirector, "open", next_response)
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
    list(engine.run_loop([{"role": "user", "content": "Read sentinel"}], "CODER", "code", 3, body["model"]))
    captures.append(
        {
            "upstream_hex": [r.hex() for r in responses],
            "dispatch": dispatch,
            "outcome_success": [o.success for o in outcomes],
        }
    )
    assert dispatch == (["read_file"] if completed_first else [])
    assert len(state["wire"]) == (2 if completed_first else 1)
    assert outcomes and outcomes[-1].success is False
    assert [r["success"] for r in state["usage"]] == ([True, False] if completed_first else [False])
    assert sentinel.read_text() == "owned read-only sentinel"


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
def test_fragmented_tools_require_terminal_before_emission(terminal_case):
    client, body, state, captures = terminal_case
    payload = wire(
        frame({"content": None, "tool_calls": [{"index": 0, "function": {"name": "read_", "arguments": '{"file_'}}]}),
        frame(
            {"tool_calls": [{"index": 0, "function": {"name": "file", "arguments": 'path":"sentinel"}'}}]}, "tool_calls"
        ),
    )
    state["outcome"] = [payload]
    chunks = list(client.contract_manager.stream_generate("Read sentinel", body["model"], tools=TOOLS))
    captures.append({"upstream_hex": payload.hex(), "chunks": chunks})
    assert len(chunks) == 1 and '"name": "read_file"' in chunks[0] and '"file_path": "sentinel"' in chunks[0]
    assert [row["success"] for row in state["usage"]] == [True]


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize(
    "delta",
    [
        None,
        [],
        {"tool_calls": {}},
        {"tool_calls": [None]},
        {"tool_calls": [{"index": True}]},
        {"tool_calls": [{"index": -1}]},
        {"tool_calls": [{"index": 0, "function": None}]},
        {"tool_calls": [{"index": 0, "function": {"name": "read_file", "arguments": "[]"}}]},
    ],
)
def test_malformed_tool_shape_never_emits(terminal_case, delta):
    from antigravity_k.engine.provider_adapters.transport_errors import NativeProtocolError

    client, body, state, captures = terminal_case
    payload = wire(frame(delta, "tool_calls"))
    state["outcome"] = [payload]
    emitted = []
    with pytest.raises(NativeProtocolError) as failure:
        for chunk in client.contract_manager.stream_generate("Read sentinel", body["model"], tools=TOOLS):
            emitted.append(chunk)
    captures.append({"upstream_hex": payload.hex(), "emitted": emitted, "error": failure.value.detail()})
    assert failure.value.code == "invalid_stream" and emitted == []
    assert [row["success"] for row in state["usage"]] == [False]
    assert len(state["wire"]) == 1 and state["sleeps"] == []


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("explicit_error", [False, True])
def test_textual_tool_is_held_before_failed_terminal(terminal_case, explicit_error):
    from antigravity_k.engine.provider_adapters.transport_errors import NativeProtocolError

    client, body, state, captures = terminal_case
    xml = '<tool_call>{"name":"read_file","arguments":{"file_path":"sentinel"}}</tool_call>'
    payload = wire(frame({"content": xml}), *([ERROR] if explicit_error else []), done=False)
    state["outcome"] = [payload]
    emitted = []
    with pytest.raises(NativeProtocolError) as failure:
        for chunk in client.contract_manager.stream_generate("Read sentinel", body["model"], tools=TOOLS):
            emitted.append(chunk)
    captures.append({"upstream_hex": payload.hex(), "emitted": emitted, "error": failure.value.detail()})
    assert emitted == []
    assert failure.value.code == ("upstream_stream_error" if explicit_error else "incomplete_stream")
    assert [row["success"] for row in state["usage"]] == [False]


@pytest.mark.parametrize("compat_case", ["lmstudio", "openrouter"], indirect=True)
@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/messages"])
@pytest.mark.parametrize(
    "payload,code",
    [
        (wire(ERROR), "upstream_stream_error"),
        (wire(frame({"content": []})), "invalid_stream"),
        (wire(frame({"content": "partial"}), done=False), "incomplete_stream"),
    ],
)
def test_nonstream_protocol_failure_returns_typed_502(terminal_case, route, payload, code):
    client, body, state, captures = terminal_case
    state["outcome"] = [payload]
    response = client.post(route, json=body)
    captures.append({"upstream_hex": payload.hex(), "response": response.text, "status": response.status_code})
    assert response.status_code == 502
    error = response.json().get("detail", response.json().get("error"))
    assert error["type"] == "provider_protocol_error" and error["code"] == code
    assert "private upstream" not in response.text
    assert [row["success"] for row in state["usage"]] == [False]
    assert state["persisted"] == [] and len(state["wire"]) == 1
