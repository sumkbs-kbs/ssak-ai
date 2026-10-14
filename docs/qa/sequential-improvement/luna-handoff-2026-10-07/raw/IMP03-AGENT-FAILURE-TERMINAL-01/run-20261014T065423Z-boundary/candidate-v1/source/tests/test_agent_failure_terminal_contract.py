"""Offline product path: real runtime, direct execution and tool loop fail closed."""

import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.test_chat_structured_output_contract import product as product
from tests.test_native_stream_terminal_contract import CALL, TOOLS, ndjson
from tests.test_native_stream_terminal_contract import stream_case as stream_case


@pytest.mark.parametrize("mode", ["terminal", "late", "transport", "escaping", "generic"])
def test_agent_failure_is_terminal_without_assistant_persistence(stream_case, monkeypatch, tmp_path, mode):
    from antigravity_k.api.routes import chat
    from antigravity_k.api.routes.session_state import get_active_session
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.provider_adapters.transport_errors import NativeProtocolError
    from antigravity_k.engine.task_runner import BackgroundTaskRunner
    from antigravity_k.engine.task_state_store import TaskExecutionContext
    from antigravity_k.engine.tool_loop import ToolLoopEngine
    from tests.test_tool_loop import mock_orch

    client, body, manager, state = stream_case
    body["agent_mode"] = True
    orch = mock_orch._get_wrapped_function()()
    orch.manager = manager
    orch.project_root = str(tmp_path)
    orch.task_execution_context = None
    orch._prepare_agent_prompt.return_value = (body["model"], "", "", "", "Read sentinel", body["messages"])
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    dispatch = []
    provider_attempts = []
    original_stream = manager.stream_generate

    def stream_generate(*args, **kwargs):
        provider_attempts.append("stream_generate")
        return original_stream(*args, **kwargs)

    monkeypatch.setattr(manager, "stream_generate", stream_generate)
    persistence = []
    engine = ToolLoopEngine(orch)
    monkeypatch.setattr(engine, "_native_tools_kwargs", lambda *a, **kw: {} if mode == "late" else {"tools": TOOLS})
    manager.get(body["model"])

    @contextmanager
    def bind(task_id, store):
        orch.task_execution_context = TaskExecutionContext(task_id=task_id, state_store=store)
        try:
            yield
        finally:
            orch.task_execution_context = None

    def run(messages, target_model, **kwargs):
        if mode in {"escaping", "generic"}:
            yield "partial-answer"
            if mode == "escaping":
                raise NativeProtocolError("incomplete_stream")
            raise RuntimeError("PRIVATE_AGENT_SECRET")
        yield from engine.run_loop(messages, "CODER", "code", 3, target_model)

    async def execute(*args, **kwargs):
        dispatch.append("unexpected")
        return "unexpected"

    orch.bind_task_execution = bind
    orch.run_stream = run
    orch.ctx.tool_executor.execute_async = execute
    runtime = AgentRuntime(orch, task_runner=runner)
    monkeypatch.setattr(chat, "get_agent_runtime", lambda: runtime)
    monkeypatch.setattr(chat, "_persist_assistant_to_conversation_store", lambda *a: persistence.append(a))
    state["responses"] = [
        TimeoutError("PRIVATE_AGENT_SECRET")
        if mode == "transport"
        else ndjson({"message": {"content": "partial-answer " + "x" * 40}, "done": False})
        if mode == "late"
        else ndjson(CALL, {"error": "PRIVATE_AGENT_SECRET"})
    ]
    response = client.post("/v1/chat/completions", json=body)
    rows = runner.state_store.list_tasks(10)
    active_session = get_active_session()
    receipt = {
        "mode": mode,
        "request": body,
        "sse": response.text,
        "tasks": [dict(r) for r in rows],
        "provider_calls": len(state["wire"]),
        "provider_attempts": provider_attempts,
        "wire_requests": state["wire"],
        "upstream_raw_hex_or_error_type": state["raw"],
        "active_session": {
            "done": active_session.done,
            "error": active_session.error,
            "is_active": active_session.is_active,
        },
        "retries": state["sleeps"],
        "tool_dispatch": dispatch,
        "session_persistence": len(state["persisted"]),
        "conversation_persistence": len(persistence),
    }
    export = os.environ.get("AGENT_FAILURE_CAPTURE_ROOT")
    if export:
        target = Path(export)
        target.mkdir(parents=True, exist_ok=True)
        (target / (mode + ".json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert response.text.count("event: error\n") == 1
    assert "[DONE]" not in response.text and "agk_final_content" not in response.text
    assert "PRIVATE_AGENT_SECRET" not in response.text
    assert not state["persisted"] and not persistence
    assert not active_session.done and not active_session.is_active and active_session.error
    assert not dispatch and not state["sleeps"]
    assert "재시도합니다" not in response.text
    assert len(state["wire"]) == len(provider_attempts) == (0 if mode in {"escaping", "generic"} else 1)
    if mode in {"late", "escaping", "generic"}:
        assert "partial-answer" in response.text
