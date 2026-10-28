"""Real chat/runtime/auth paths enforce global read bans without phantom approval."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests import test_r43_b_agent_integration as recall
from tests import test_r47_memory_read_contract_integration as reads

integration_case = recall.integration_case
contract_case = reads.contract_case


def test_global_reader_ban_blocks_rogue_hex_before_approval_and_keeps_recall(contract_case: reads.ContractCase, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the actual authenticated project/Vault/runtime, with a real binary reader installed.
    from antigravity_k.api import dependencies
    from antigravity_k.engine import llm_input_audit
    from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
    from antigravity_k.engine.turn_tool_constraints import current_turn_tool_constraints
    from antigravity_k.tools.binary_tools import HexDumpTool

    case = contract_case
    core = case.core
    case.prompt = recall.QUESTION + " read_file을 호출하지 마세요. 파일을 읽지 마세요."
    case.scenario_name = "r51-global-reader-ban"
    project = core.registry.get_project(core.project_id)
    assert project is not None
    handle = dependencies.acquire_project_runtime(project_id=core.project_id, project_root=project.path)
    handle.orchestrator.tool_registry.install(HexDumpTool())
    observed_tools: list[dict[str, str]] = []
    surfaces: list[dict[str, JsonValue]] = []
    original_audit = llm_input_audit.audit_tool

    def observe_audit(*, name: str, stage: str) -> None:
        observed_tools.append({"name": name, "stage": stage})
        original_audit(name=name, stage=stage)

    def provider_stream(*, prompt: str, target: str, **kwargs: JsonValue) -> Iterator[str]:
        core.provider.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            core.provider.calls.append("ceo")
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": case.prompt})
            return
        assert recall.FACT in prompt and recall.OTHER not in prompt
        surfaces.append({"xml_tool_names": re.findall(r"^- \*\*([a-z_]+)\*\*:", prompt, re.MULTILINE), "native_schemas": kwargs.get("tools", [])})
        core.provider.answer_calls += 1
        core.provider.calls.append("rogue_hex_then_grounded_answer")
        if core.provider.answer_calls == 1:
            # Deliberately ignore the filtered advertisements to exercise the real dispatch guard.
            yield '<tool_call>{"name":"hex_dump","arguments":{"file_path":"' + reads.READ_PATH + '"}}</tool_call>'
            return
        yield recall.FACT

    monkeypatch.setattr(llm_input_audit, "audit_tool", observe_audit)
    monkeypatch.setattr(core.provider, "stream_generate", provider_stream)
    original_mode = get_access_mode()
    set_access_mode(AccessMode.READ_ONLY)
    # When: one real in-process chat request encounters the rogue alternative reader.
    try:
        response = case.client.post("/v1/chat/completions", headers=case.headers["user"], json={"model": recall.MODEL, "project_id": core.project_id, "conversation_id": "r51-global-read-ban", "conversation_revision": 0, "messages": [{"role": "user", "content": case.prompt}], "stream": True, "agent_mode": True, "web_search": False, "code_mode": False, "mcp_servers": []})
    finally:
        set_access_mode(original_mode)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    answer = "".join(event.get("choices", [{}])[0].get("delta", {}).get("content", "") for event in events)
    tasks = handle.agent_runtime.task_runner.state_store.list_tasks(10)
    isolation = reads._owner_http_observations(case, tasks[0]["task_id"])
    proof = {"http_status": response.status_code, "answer": answer, "tasks": tasks, "surfaces": surfaces, "tool_audit": observed_tools, "physical_read_calls": case.physical_reads, "isolation": isolation, "constraint_scope_reset": current_turn_tool_constraints().denial("hex_dump") is None, "scope": "real ASGI/auth/runtime/Vault/tool guards/tasks with scripted model/embedding; no native app or model"}
    capture = os.environ.get("R43_CAPTURE_ROOT")
    if capture:
        destination = Path(capture)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "r51-global-reader-proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    # Then: no execution or phantom approval occurs, while memory/task/auth behavior remains.
    assert response.status_code == 200 and answer == recall.FACT
    assert tasks[0]["status"] == "done" and tasks[0]["output"] == recall.FACT
    assert {"name": "hex_dump", "stage": "blocked_by_user_constraint"} in observed_tools
    assert all(event["stage"] != "execute_requested" for event in observed_tools)
    assert surfaces and all("hex_dump" not in item["xml_tool_names"] for item in surfaces)
    assert "APPROVAL REQUIRED" not in response.text
    assert case.physical_reads == []
    assert proof["constraint_scope_reset"] is True
    assert core.forbidden == []


def test_retrieved_document_prohibition_is_not_current_tool_authority(contract_case: reads.ContractCase) -> None:
    # Given / When: the existing real recall fixture inserts an untrusted read ban in its note.
    scenario = reads.Scenario("untrusted-recalled-ban-is-not-user-authority", recall.QUESTION, 1)
    reads.test_current_user_read_contract_controls_real_recall_file_io(contract_case, scenario)
    # Then: original-user neutral scope keeps the real read descriptor available.
    assert contract_case.first_answer_prompt
    descriptors = re.findall(r"^- \*\*([a-z_]+)\*\*:", contract_case.first_answer_prompt[0], re.MULTILINE)
    assert "read_file" in descriptors
