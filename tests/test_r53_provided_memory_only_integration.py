"""Provided-memory-only requests stay on the real recall/auth/task path.

Only the existing fixture's model and embedding provider are scripted. No
listener, native app, real model, embedding download or external connection is
used. Real tool implementations stay installed so a missing dispatch guard
cannot pass by making a rogue tool unknown or replacing its execution result.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import test_r43_b_agent_integration as recall
from tests import test_r47_memory_read_contract_integration as reads

integration_case = recall.integration_case
contract_case = reads.contract_case

PROVIDED_MEMORY_REQUEST = (
    recall.QUESTION
    + " read_file을 호출하지 마세요. 파일을 읽지 마세요. 이미 전달된 기억으로 코드만 답해줘."
)
# In the actual r52 incident this was the preceding impact tool result's
# sha256_prefix, not a context_artifact_ref or a retrieved-memory chunk ID.
RESULT_DIGEST = "504890ff0fe556fd"
ROGUE_CALLS: tuple[tuple[str, dict[str, object]], ...] = (
    ("impact_analyzer", {"target_path": reads.READ_PATH, "symbol_name": recall.FACT}),
    ("read_context_artifact", {"ref_id": RESULT_DIGEST, "chunk_index": 0}),
    ("git_status", {}),
    ("list_directory", {"path": ".", "max_depth": 2}),
    ("glob_search", {"pattern": "**/*synthetic-decision*", "root": ".", "max_results": 10}),
)
ROGUE_NAMES = frozenset(name for name, _ in ROGUE_CALLS)
CASES = (("all-five-in-one-reply", ROGUE_CALLS),) + tuple(
    (name, ((name, arguments),)) for name, arguments in ROGUE_CALLS
)


def _native_names(raw_tools: object) -> list[str]:
    if not isinstance(raw_tools, list):
        return []
    names: list[str] = []
    for schema in raw_tools:
        assert isinstance(schema, dict)
        function = schema.get("function")
        name = function.get("name") if isinstance(function, dict) else schema.get("name")
        assert isinstance(name, str)
        names.append(name)
    return names


@pytest.mark.parametrize(("scenario_name", "rogue_calls"), CASES, ids=[case[0] for case in CASES])
def test_provided_memory_only_blocks_rogue_tools_before_executor_and_approval(
    contract_case: reads.ContractCase,
    monkeypatch: pytest.MonkeyPatch,
    scenario_name: str,
    rogue_calls: tuple[tuple[str, dict[str, object]], ...],
) -> None:
    # Given: real authenticated project recall, with all actual incident tools
    # registered and native schemas demonstrably enabled before this turn.
    from antigravity_k.api import dependencies
    from antigravity_k.engine import llm_input_audit
    from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
    from antigravity_k.engine.tool_loop import ToolLoopEngine
    from antigravity_k.engine.turn_tool_constraints import current_turn_tool_constraints
    from antigravity_k.tools.context_artifact_tools import ReadContextArtifactTool
    from antigravity_k.tools.file_tools import GlobSearchTool
    from antigravity_k.tools.git_tools import GitStatusTool
    from antigravity_k.tools.impact_analyzer import ImpactAnalyzerTool
    from antigravity_k.tools.system_tools import ListDirectoryTool

    case = contract_case
    core = case.core
    case.prompt = PROVIDED_MEMORY_REQUEST
    case.scenario_name = "r53-provided-memory-" + scenario_name
    project = core.registry.get_project(core.project_id)
    assert project is not None
    handle = dependencies.acquire_project_runtime(project_id=core.project_id, project_root=project.path)
    orchestrator = handle.orchestrator
    for tool in (
        ImpactAnalyzerTool(), ReadContextArtifactTool(project.path), GitStatusTool(),
        ListDirectoryTool(), GlobSearchTool(),
    ):
        orchestrator.tool_registry.install(tool)
    assert all(name in orchestrator.tool_registry for name in ROGUE_NAMES)
    loop_config = dict(orchestrator.config.get("tool_loop", {}))
    loop_config["native_function_calling"] = True
    monkeypatch.setitem(orchestrator.config, "tool_loop", loop_config)
    monkeypatch.setattr(
        core.provider, "provider_capability", lambda model: {"native_tool_calling": "supported"}, raising=False,
    )

    tool_audit: list[dict[str, str]] = []
    executor_calls: list[dict[str, object]] = []
    approval_calls: list[str] = []
    surfaces: list[dict[str, object]] = []
    executor = orchestrator.ctx.tool_executor
    original_audit = llm_input_audit.audit_tool
    original_execute = executor.execute
    original_register_approval = executor._register_approval_request

    def observe_audit(*, name: str, stage: str) -> None:
        tool_audit.append({"name": name, "stage": stage})
        original_audit(name=name, stage=stage)

    def observe_execute(
        name: str, args: dict[str, object], objective: str = "", execution_mode: str = "interactive",
        *, guardrail_prechecked: bool = False,
    ) -> str:
        executor_calls.append({"name": name, "arguments": dict(args)})
        return original_execute(
            name, args, objective, execution_mode, guardrail_prechecked=guardrail_prechecked,
        )

    def observe_register_approval(name: str, *args: object, **kwargs: object) -> object:
        approval_calls.append(name)
        return original_register_approval(name, *args, **kwargs)

    def provider_stream(*, prompt: str, target: str, **kwargs: object) -> Iterator[str]:
        core.provider.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            core.provider.calls.append("ceo")
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": case.prompt})
            return
        # The answer is observed at the actual provider boundary, inside the
        # retrieved-memory block rather than fabricated by the test's request.
        memory_blocks = re.findall(r"<past_memory>([\s\S]*?)</past_memory>", prompt)
        assert memory_blocks and any(recall.FACT in block for block in memory_blocks)
        assert recall.OTHER not in prompt
        assert reads.FRESH_TAIL not in prompt
        surfaces.append({
            "xml_tool_names": re.findall(r"^- \*\*([a-z_]+)\*\*:", prompt, re.MULTILINE),
            "native_tool_names": _native_names(kwargs.get("tools", [])),
            "past_memory_expected_present": True, "other_project_fact_absent": True,
        })
        core.provider.answer_calls += 1
        if core.provider.answer_calls == 1:
            core.provider.calls.append("provided_memory_rogue")
            # Deliberately ignore all advertised capabilities. Both the batch
            # and individual proposals must be rejected by the real parser /
            # dispatch boundary before executor or approval registration.
            for name, arguments in rogue_calls:
                yield "<tool_call>" + json.dumps({"name": name, "arguments": arguments}) + "</tool_call>\n"
            return
        assert core.provider.answer_calls == 2, "Only one corrective answer is allowed"
        core.provider.calls.append("provided_memory_answer")
        yield recall.FACT

    monkeypatch.setattr(llm_input_audit, "audit_tool", observe_audit)
    monkeypatch.setattr(executor, "execute", observe_execute)
    monkeypatch.setattr(executor, "_register_approval_request", observe_register_approval)
    monkeypatch.setattr(core.provider, "stream_generate", provider_stream)
    original_mode = get_access_mode()
    set_access_mode(AccessMode.READ_ONLY)
    try:
        baseline_native = _native_names(ToolLoopEngine(orchestrator)._native_tools_kwargs(recall.MODEL).get("tools", []))
        assert ROGUE_NAMES.issubset(baseline_native), "Native filtering must not be tested against an empty configuration"
        # When: actual in-process HTTP traverses auth, Graph, memory prefetch,
        # ToolLoop and persisted task output, including a hostile model reply.
        response = case.client.post(
            "/v1/chat/completions", headers=case.headers["user"],
            json={
                "model": recall.MODEL, "project_id": core.project_id,
                "conversation_id": "r53-provided-memory-" + scenario_name, "conversation_revision": 0,
                "messages": [{"role": "user", "content": case.prompt}],
                "stream": True, "agent_mode": True, "web_search": False, "code_mode": False, "mcp_servers": [],
            },
        )
    finally:
        set_access_mode(original_mode)
    events = [json.loads(line[6:]) for line in response.text.splitlines()
              if line.startswith("data: ") and line != "data: [DONE]"]
    answer = "".join(event.get("choices", [{}])[0].get("delta", {}).get("content", "") for event in events)
    finals = [event["agk_final_content"] for event in events if "agk_final_content" in event]
    tasks = handle.agent_runtime.task_runner.state_store.list_tasks(10, owner_subject="user")
    assert len(tasks) == 1
    isolation = reads._owner_http_observations(case, tasks[0]["task_id"])
    record = core.conversations.get(
        project_id=core.project_id, conversation_id="r53-provided-memory-" + scenario_name,
    )
    assistant_answers = [item.content for item in record.messages if item.role == "assistant"] if record else []
    proof = {
        "scenario": scenario_name, "original_request": case.prompt, "status_code": response.status_code,
        "answer": answer, "finals": finals, "assistant_answers": assistant_answers,
        "tasks": tasks, "isolation": isolation, "surfaces": surfaces,
        "tool_audit": tool_audit, "executor_calls": executor_calls, "approval_calls": approval_calls,
        "physical_reads": case.physical_reads, "baseline_native_names": baseline_native,
        "provider_calls": core.provider.calls,
        "scope": "real authenticated ASGI/Graph/ToolLoop/Vault/Chroma/task route; scripted provider only; no native app/model",
    }
    core.evidence.update(proof)
    capture = os.environ.get("R43_CAPTURE_ROOT")
    if capture:
        destination = Path(capture)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ("r53-provided-memory-" + scenario_name + ".json")).write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    # Then: one grounded answer survives; each forbidden proposal is visible in
    # audit evidence, but no tool/executor/approval/file-read path was reached.
    assert response.status_code == 200
    assert answer == recall.FACT and finals == [recall.FACT] and assistant_answers == [recall.FACT]
    assert tasks[0]["status"] == "done" and tasks[0]["output"] == recall.FACT
    assert executor_calls == [] and approval_calls == [] and case.physical_reads == []
    assert executor.tool_call_history == []
    for name, _ in rogue_calls:
        assert {"name": name, "stage": "blocked_by_user_constraint"} in tool_audit
    assert all(item["stage"] not in {"execute_requested", "approval_pending", "approval_granted"} for item in tool_audit)
    assert surfaces and all(item["xml_tool_names"] == [] and item["native_tool_names"] == [] for item in surfaces)
    assert "APPROVAL REQUIRED" not in response.text and "Artifact chunk not found" not in response.text
    assert core.provider.answer_calls == 2
    assert core.provider.calls.count("provided_memory_rogue") == core.provider.calls.count("provided_memory_answer") == 1
    assert len(core.provider.calls) <= 4 and "unexpected_generate" not in core.provider.calls
    assert all(current_turn_tool_constraints().denial(name) is None for name in ROGUE_NAMES)
    assert core.forbidden == []
