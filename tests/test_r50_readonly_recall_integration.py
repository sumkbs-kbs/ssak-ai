"""Real authenticated recall routing exposes allowed tools to a scripted provider."""

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


def test_readonly_recall_cannot_offer_or_execute_write_tool(contract_case: reads.ContractCase, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the actual authenticated router/Vault/runtime with both real read and write tools.
    from antigravity_k.api import dependencies
    from antigravity_k.engine import llm_input_audit
    from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
    from antigravity_k.tools.file_tools import WriteFileTool

    case = contract_case
    core = case.core
    case.prompt = recall.QUESTION + " read_file을 호출하지 마세요. 파일을 읽지 마세요."
    case.scenario_name = "r50-readonly-recall"
    project = core.registry.get_project(core.project_id)
    assert project is not None
    handle = dependencies.acquire_project_runtime(project_id=core.project_id, project_root=project.path)
    handle.orchestrator.tool_registry.install(WriteFileTool())
    monkeypatch.setattr(core.provider, "provider_capability", lambda model: {"native_tool_calling": "supported"}, raising=False)
    attempted_tools: list[dict[str, str]] = []
    original_audit = llm_input_audit.audit_tool
    surfaces: list[dict[str, JsonValue]] = []

    def observe_audit(*, name: str, stage: str) -> None:
        attempted_tools.append({"name": name, "stage": stage})
        original_audit(name=name, stage=stage)

    def provider_stream(*, prompt: str, target: str, **kwargs: JsonValue) -> Iterator[str]:
        core.provider.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            core.provider.calls.append("ceo")
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": case.prompt})
            return
        assert recall.FACT in prompt and recall.OTHER not in prompt
        xml_names = re.findall(r"^- \*\*([a-z_]+)\*\*:", prompt, re.MULTILINE)
        native_names = [item.get("function", {}).get("name") for item in kwargs.get("tools", [])]
        surfaces.append({"xml_tool_names": xml_names, "native_tool_names": native_names, "memory_expected_present": True, "memory_other_absent": True})
        core.provider.answer_calls += 1
        core.provider.calls.append("policy_observing_answer")
        # The provider follows the offered capability surface. Runtime policy is tested separately.
        if core.provider.answer_calls == 1 and "write_file" in xml_names + native_names:
            yield '<tool_call>{"name":"write_file","arguments":{"file_path":"artifacts/answer.txt","content":"' + recall.FACT + '"}}</tool_call>'
            return
        yield recall.FACT

    monkeypatch.setattr(llm_input_audit, "audit_tool", observe_audit)
    monkeypatch.setattr(core.provider, "stream_generate", provider_stream)
    original_mode = get_access_mode()
    set_access_mode(AccessMode.READ_ONLY)
    # When: one actual in-process HTTP request reaches that provider boundary.
    try:
        response = case.client.post("/v1/chat/completions", headers=case.headers["user"], json={"model": recall.MODEL, "project_id": core.project_id, "conversation_id": "r50-readonly-recall", "conversation_revision": 0, "messages": [{"role": "user", "content": case.prompt}], "stream": True, "agent_mode": True, "web_search": False, "code_mode": False, "mcp_servers": []})
    finally:
        set_access_mode(original_mode)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    answer = "".join(event.get("choices", [{}])[0].get("delta", {}).get("content", "") for event in events)
    tasks = handle.agent_runtime.task_runner.state_store.list_tasks(10)
    isolation = reads._owner_http_observations(case, tasks[0]["task_id"])
    evidence = {"http_status": response.status_code, "surfaces": surfaces, "attempted_tools": attempted_tools, "canonical_answer": answer, "physical_file_reads": case.physical_reads, "task_output": tasks[0]["output"], "isolation": isolation, "artifact_exists": (Path(project.path) / "artifacts/answer.txt").exists(), "scope": "scripted provider boundary; real authenticated ASGI/project/Vault/runtime/tools/tasks; no native model"}
    capture = os.environ.get("R43_CAPTURE_ROOT")
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        (target / "r50-readonly-recall.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    # Then: memory answers once, no prohibited tool is offered/executed, and owner isolation remains.
    assert response.status_code == 200
    assert answer == tasks[0]["output"] == recall.FACT
    assert surfaces and all("write_file" not in item["xml_tool_names"] + item["native_tool_names"] for item in surfaces)
    assert attempted_tools == []
    assert case.physical_reads == []
    assert evidence["artifact_exists"] is False
    assert core.forbidden == []
