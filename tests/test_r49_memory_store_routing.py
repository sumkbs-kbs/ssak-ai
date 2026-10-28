"""The actual chat/runtime graph stores a project fact after a negative tool mention."""

from __future__ import annotations

import json
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests import test_r43_b_agent_integration as recall
from tests import test_r47_memory_read_contract_integration as reads

integration_case = recall.integration_case
contract_case = reads.contract_case
FACT = "R49-ALPHA-POSTGRES-6518"


@pytest.mark.parametrize("ban_clause", ["read_file을 호출하지 마세요. 도구를 사용하지 마세요.", "파일을 읽지 마세요. read_file 도구를 쓸 필요는 없습니다."])
def test_negative_tool_mention_reaches_normal_prefetch_and_project_sync(integration_case: recall.IntegrationCase, monkeypatch: pytest.MonkeyPatch, ban_clause: str) -> None:
    # Given: a real request project/runtime with synthetic providers at its boundaries.
    from antigravity_k.api import dependencies
    from antigravity_k.engine import request_execution_context
    from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
    from antigravity_k.engine.project_memory import ProjectMemoryProvider

    case = integration_case
    current_request = "다음 합성 프로젝트 사실을 기억해줘. " + ban_clause + " 확인 한 문장만 답해줘.\n프로젝트 사실: database = " + FACT
    monkeypatch.setattr(request_execution_context, "get_project_registry", lambda: case.registry)
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", "false")
    project = case.registry.get_project(case.project_id)
    assert project is not None
    handle = dependencies.acquire_project_runtime(project_id=case.project_id, project_root=project.path)
    handle.memory_manager.add_provider(ProjectMemoryProvider(project.path))
    prefetch_calls: list[str] = []
    original_prefetch = handle.memory_manager.prefetch_all

    def observed_prefetch(query: str, session_id: str | None = None) -> str:
        prefetch_calls.append(query)
        return original_prefetch(query, session_id)

    def provider_stream(*, prompt: str, target: str, **kwargs: JsonValue) -> Iterator[str]:
        case.provider.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            case.provider.calls.append("ceo")
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": current_request})
            return
        case.provider.calls.append("store_confirmation")
        yield "요청한 프로젝트 사실을 기억했습니다."

    monkeypatch.setattr(handle.memory_manager, "prefetch_all", observed_prefetch)
    monkeypatch.setattr(case.provider, "stream_generate", provider_stream)
    original_mode = get_access_mode()
    set_access_mode(AccessMode.FULL_ACCESS)
    # When: ASGI drives the actual chat/runtime/store path once.
    try:
        response = case.client.post("/v1/chat/completions", json={"model": recall.MODEL, "project_id": case.project_id, "conversation_id": "r49-memory-store", "conversation_revision": 0, "messages": [{"role": "user", "content": current_request}], "stream": True, "agent_mode": True, "web_search": False, "code_mode": False, "mcp_servers": []})
    finally:
        set_access_mode(original_mode)
    facts_path = Path(project.path) / ".antigravity/memory/project_facts.json"
    payload = json.loads(facts_path.read_bytes()) if facts_path.is_file() else {}
    store = handle.agent_runtime.task_runner.state_store
    tasks = store.list_tasks(10)
    checkpoint = store.get_last_checkpoint(tasks[0]["task_id"]) if tasks else None
    checkpoint_context = json.loads(checkpoint["context_json"]) if checkpoint else {}
    case.evidence["r49_memory_storage"] = {"status": response.status_code, "sse": response.text, "prefetch_calls": prefetch_calls, "file_exists": facts_path.is_file(), "file_payload": payload, "checkpoint_expected_tools": checkpoint_context.get("expected_tools", []), "provider_calls": list(case.provider.calls)}
    capture = os.environ.get("R43_CAPTURE_ROOT")
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        suffix = hashlib.sha256(current_request.encode()).hexdigest()[:16]
        (target / f"memory-store-{suffix}.json").write_text(json.dumps(case.evidence["r49_memory_storage"], ensure_ascii=False, indent=2) + "\n")
    # Then: real prefetch and real durable project sync run; no forbidden tool runs.
    assert response.status_code == 200
    assert prefetch_calls
    assert payload.get("fact:database", {}).get("value") == FACT
    assert checkpoint_context.get("expected_tools", []) == []
    assert handle.orchestrator.ctx.tool_executor.tool_call_history == []
    assert "ceo" in case.provider.calls
    reloaded = ProjectMemoryProvider(project.path).authoritative_facts()
    assert [(fact.key, fact.value) for fact in reloaded] == [("project:fact:database", FACT)]
    assert case.forbidden == []


def test_inline_named_positive_read_preserves_authenticated_actual_file_path(contract_case: reads.ContractCase) -> None:
    # Given: the existing authenticated project/Vault fixture with a new unindexed tail.
    prompt = f"`read_file` 도구로 {reads.READ_PATH} 파일을 실제로 읽고, " + recall.QUESTION
    scenario = reads.Scenario("explicit-read-retains-real-io", prompt, 1)
    # When / Then: its real router/tool/file/task assertions also hold for the inline tool name.
    reads.test_current_user_read_contract_controls_real_recall_file_io(contract_case, scenario)
