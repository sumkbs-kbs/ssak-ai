"""Store, fresh-conversation recall and read permissions through real ASGI/state.

Only the inherited fixture's model and embedding providers are scripted. Memory
delivery, durable storage, Graph, file reads and task/conversation APIs stay real.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import test_r43_b_agent_integration as recall
from tests import test_r47_memory_read_contract_integration as reads

integration_case = recall.integration_case
contract_case = reads.contract_case


def test_stored_fact_reaches_new_conversation_and_current_read_permissions(
    contract_case: reads.ContractCase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from antigravity_k.api import dependencies
    from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
    from antigravity_k.engine.project_memory import ProjectMemoryProvider
    from antigravity_k.engine.turn_tool_constraints import current_turn_tool_constraints

    case = contract_case
    core = case.core
    project = core.registry.get_project(core.project_id)
    assert project is not None
    handle = dependencies.acquire_project_runtime(project_id=core.project_id, project_root=project.path)
    store = handle.agent_runtime.task_runner.state_store
    executor = handle.orchestrator.ctx.tool_executor
    nonce = uuid.uuid4().hex[:12]
    sentinel = "R55-SYNTHETIC-BADGE-" + nonce
    saved = "요청한 프로젝트 배지 코드를 기억했습니다."
    store_request = (
        "다음 합성 프로젝트 사실을 기억해줘. read_file을 호출하지 마세요. "
        "확인 한 문장만 답해줘.\n프로젝트 사실: badge_code = " + sentinel
    )
    recall_request = "우리가 저장한 프로젝트 badge_code 기억은 무엇이었지? 코드만 답해줘."
    allowed_request = (
        f"read_file 도구로 {reads.READ_PATH} 파일을 실제로 읽고, "
        "마지막 줄 코드만 답해줘. 예전 색인이나 기억을 답으로 사용하지 마세요."
    )
    forbidden_request = recall_request + " read_file을 호출하지 마세요. 파일을 읽지 마세요."
    facts_path = Path(project.path) / ".antigravity/memory/project_facts.json"
    note_path = Path(project.path) / reads.READ_PATH
    seed_documents = [row["document"] for row in handle.vault_engine.vector_store.export_all()]
    before_facts = [(fact.key, fact.value) for fact in ProjectMemoryProvider(project.path).authoritative_facts()]
    assert all(sentinel not in text and reads.FRESH_TAIL not in text for text in seed_documents)
    assert sentinel not in note_path.read_text(encoding="utf-8")
    assert all(sentinel != value for _, value in before_facts)
    assert all(key != "project:fact:badge_code" for key, _ in before_facts)
    assert sentinel not in recall_request and sentinel not in forbidden_request
    assert handle.memory_manager.authoritative_project_fact_for_query(recall_request) is None
    assert sum(provider.name == "project" for provider in handle.memory_manager.providers) == 1
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", "false")

    phase = "not-started"
    answer_counts: dict[str, int] = {}
    provider_observations: list[dict[str, object]] = []
    turn_observations: list[dict[str, object]] = []
    expected_tasks: dict[str, str] = {}
    proof: dict[str, object] = {
        "sentinel": sentinel, "before_facts": before_facts,
        "old_seed_documents": seed_documents, "provider_observations": provider_observations,
        "turns": turn_observations,
        "scope": "real authenticated ASGI/Graph/memory/Vault/read/task/conversation; scripted model and embedding",
    }
    core.evidence["r55_memory_lifecycle"] = proof

    def remembered_value(prompt: str) -> str:
        match = re.search(
            r"\[(?:project:fact:badge_code|resolved:project:fact:badge_code[^\]]*)\]\s+(\S+)", prompt,
        )
        assert match is not None, "Stored project fact never reached the real answer-provider boundary"
        assert match.group(1) == sentinel
        assert "[Recalled Memory]" in prompt
        assert store_request not in prompt, "Recall passed by replaying the earlier store request"
        return match.group(1)

    def answer_from_current_evidence(prompt: str) -> str:
        assert "[QUALITY REVISION]" not in prompt and "[WEB CITATION CORRECTION]" not in prompt
        assert recall.OTHER not in prompt, "Another project's synthetic memory reached this turn"
        if phase == "store":
            assert reads.FRESH_TAIL not in prompt
            assert "[project:fact:badge_code]" not in prompt and "resolved:project:fact:badge_code" not in prompt
            return saved
        if phase == "allowed-read":
            assert len(case.physical_reads) == 1 and len(case.read_results) == 1
            result = case.read_results[0]
            assert reads.FRESH_TAIL in result and reads.FRESH_TAIL in prompt
            return result.strip().splitlines()[-1]
        assert reads.FRESH_TAIL not in prompt, "A previous read leaked fresh file bytes into a new recall turn"
        return remembered_value(prompt)

    def provider_generate(
        *, prompt: str, target: str, max_tokens: int = 1024, **kwargs: object,
    ) -> str:
        core.provider.prompts.append(prompt)
        if max_tokens == 10:
            core.provider.calls.append(phase + ":intent")
            return "MEMORY"
        answer_counts[phase] = answer_counts.get(phase, 0) + 1
        core.provider.calls.append(phase + ":complete")
        provider_observations.append({"phase": phase, "kind": "complete", "prompt": prompt})
        assert phase == "allowed-read", "Unexpected completion must not repair a missing stored memory"
        return answer_from_current_evidence(prompt)

    def provider_stream(*, prompt: str, target: str, **kwargs: object) -> Iterator[str]:
        core.provider.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            core.provider.calls.append(phase + ":ceo")
            provider_observations.append({"phase": phase, "kind": "ceo", "prompt": prompt})
            yield json.dumps({
                "task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": case.prompt,
            })
            return
        answer_counts[phase] = answer_counts.get(phase, 0) + 1
        core.provider.calls.append(phase + ":answer")
        provider_observations.append({"phase": phase, "kind": "answer", "prompt": prompt})
        assert recall.OTHER not in prompt
        if phase in {"recall", "forbidden-read"}:
            remembered_value(prompt)
            assert reads.FRESH_TAIL not in prompt
        if phase in {"allowed-read", "forbidden-read"} and answer_counts[phase] == 1:
            if phase == "allowed-read":
                assert reads.FRESH_TAIL not in prompt
                assert case.physical_reads == []
            yield "<tool_call>" + json.dumps(
                {"name": "read_file", "arguments": {"file_path": reads.READ_PATH}}
            ) + "</tool_call>"
            return
        if phase == "forbidden-read":
            assert answer_counts[phase] == 2
            assert "CURRENT USER TOOL CONSTRAINT" in prompt
        yield answer_from_current_evidence(prompt)

    monkeypatch.setattr(core.provider, "generate", provider_generate)
    monkeypatch.setattr(core.provider, "stream_generate", provider_stream)

    def assert_task_http(task_id: str, expected: str) -> dict[str, object]:
        own = case.client.get("/api/tasks", headers=case.headers["user"])
        assert own.status_code == 200
        assert {row["task_id"] for row in own.json()["data"]} == set(expected_tasks)
        status = case.client.get(f"/api/tasks/{task_id}/status", headers=case.headers["user"])
        assert status.status_code == 200 and status.json()["data"]["status"] == "done"
        output = case.client.get(f"/api/tasks/{task_id}/output", headers=case.headers["user"])
        assert output.status_code == 200 and output.json()["output"] == expected
        events = case.client.get(f"/api/tasks/{task_id}/events", headers=case.headers["user"])
        assert events.status_code == 200 and events.json()["events"]
        assert all(event["task_id"] == task_id for event in events.json()["events"])
        foreign = case.client.get("/api/tasks", headers=case.headers["foreign"])
        assert foreign.status_code == 200 and foreign.json()["data"] == []
        denied = {
            suffix: case.client.get(f"/api/tasks/{task_id}/{suffix}", headers=case.headers["foreign"]).status_code
            for suffix in ("status", "output", "events")
        }
        assert set(denied.values()) == {404}
        foreign_resume = case.client.post(f"/api/tasks/{task_id}/resume", headers=case.headers["foreign"])
        assert foreign_resume.status_code == 404
        assert store.get_task(task_id, owner_subject="r47-foreign") is None
        return {
            "owner_output": output.json()["output"], "event_count": len(events.json()["events"]), "foreign": denied,
        }

    def post_turn(name: str, request_text: str, expected: str, required_tools: list[str]) -> None:
        nonlocal phase
        phase = name
        case.prompt = request_text
        case.scenario_name = "r55-" + name
        conversation_id = "r55-" + name + "-" + nonce
        assert core.conversations.get(project_id=core.project_id, conversation_id=conversation_id) is None
        before_ids = {row["task_id"] for row in store.list_tasks(10, owner_subject="user")}
        response = case.client.post(
            "/v1/chat/completions", headers=case.headers["user"],
            json={
                "model": recall.MODEL, "project_id": core.project_id,
                "conversation_id": conversation_id, "conversation_revision": 0,
                "messages": [{"role": "user", "content": request_text}],
                "stream": True, "agent_mode": True, "web_search": False,
                "code_mode": False, "mcp_servers": [],
            },
        )
        events = [json.loads(line[6:]) for line in response.text.splitlines()
                  if line.startswith("data: ") and line != "data: [DONE]"]
        answer = "".join(event.get("choices", [{}])[0].get("delta", {}).get("content", "") for event in events)
        finals = [event["agk_final_content"] for event in events if "agk_final_content" in event]
        observation: dict[str, object] = {
            "phase": name, "request": request_text, "conversation_id": conversation_id,
            "http_status": response.status_code, "sse": response.text, "answer": answer, "finals": finals,
        }
        turn_observations.append(observation)
        assert response.status_code == 200, f"{name}: real chat request failed"
        assert answer == expected and finals == [expected], (
            f"{name}: canonical answer disagrees across SSE surfaces"
        )
        tasks = store.list_tasks(10, owner_subject="user")
        created = [row for row in tasks if row["task_id"] not in before_ids]
        assert len(created) == 1, f"{name}: request must create exactly one persisted owner task"
        task = created[0]
        observation["task_observed"] = task
        assert task["status"] == "done" and task["output"] == expected
        expected_tasks[task["task_id"]] = expected
        checkpoint = store.get_last_checkpoint(task["task_id"])
        assert checkpoint is not None
        checkpoint_context = json.loads(checkpoint["context_json"])
        assert checkpoint_context.get("expected_tools", []) == required_tools
        record = core.conversations.get(project_id=core.project_id, conversation_id=conversation_id)
        assert record is not None
        user_messages = [message.content for message in record.messages if message.role == "user"]
        assistant_messages = [message.content for message in record.messages if message.role == "assistant"]
        assert user_messages == [request_text], f"{name}: fresh conversation unexpectedly contains another turn"
        assert assistant_messages == [expected]
        if name == "recall":
            assert all(sentinel not in message for message in user_messages)
        observation.update({
            "task": task, "checkpoint_expected_tools": checkpoint_context.get("expected_tools", []),
            "conversation_users": user_messages, "conversation_assistants": assistant_messages,
            "task_http": assert_task_http(task["task_id"], expected),
            "tool_history": list(executor.tool_call_history),
        })

    original_mode = get_access_mode()
    try:
        set_access_mode(AccessMode.FULL_ACCESS)
        verified = case.client.post("/api/auth/verify", headers=case.headers["foreign"])
        assert verified.status_code == 200 and verified.json()["subject"] == "r47-foreign"
        post_turn("store", store_request, saved, [])
        payload = json.loads(facts_path.read_bytes()) if facts_path.is_file() else {}
        reloaded = [(fact.key, fact.value) for fact in ProjectMemoryProvider(project.path).authoritative_facts()]
        proof.update({"stored_payload": payload, "reloaded_facts": reloaded})
        assert payload.get("fact:badge_code", {}).get("value") == sentinel, (
            "Store confirmation lacked durable project data"
        )
        assert ("project:fact:badge_code", sentinel) in reloaded
        assert case.physical_reads == [] and executor.tool_call_history == []
        assert "store:ceo" in core.provider.calls and answer_counts["store"] == 1

        assert handle.memory_manager.authoritative_project_fact_for_query(recall_request) is None
        post_turn("recall", recall_request, sentinel, [])
        assert "recall:ceo" in core.provider.calls, "Custom-key recall must traverse the real Graph"
        assert answer_counts["recall"] == 1 and case.physical_reads == []
        assert executor.tool_call_history == []
        assert all(sentinel not in row["document"] for row in handle.vault_engine.vector_store.export_all())

        allowed_audit_start = len(case.tool_audit)
        post_turn("allowed-read", allowed_request, reads.FRESH_TAIL, ["read_file"])
        allowed_audit = case.tool_audit[allowed_audit_start:]
        assert len(case.physical_reads) == len(case.read_results) == 1
        assert reads.FRESH_TAIL in case.read_results[0]
        assert len(executor.tool_call_history) == 1
        read_history = executor.tool_call_history[0]
        assert read_history["name"] == "read_file" and read_history["success"] is True
        assert sum(item == {"name": "read_file", "stage": "execute_requested"} for item in allowed_audit) == 1
        assert all(item["stage"] != "blocked_by_user_constraint" for item in allowed_audit)
        assert answer_counts["allowed-read"] == 2

        forbidden_audit_start = len(case.tool_audit)
        history_before_ban = list(executor.tool_call_history)
        post_turn("forbidden-read", forbidden_request, sentinel, [])
        forbidden_audit = case.tool_audit[forbidden_audit_start:]
        assert {"name": "read_file", "stage": "blocked_by_user_constraint"} in forbidden_audit
        assert all(
            item["stage"] not in {"execute_requested", "approval_pending", "approval_granted"}
            for item in forbidden_audit
        )
        assert executor.tool_call_history == history_before_ban
        assert len(case.physical_reads) == len(case.read_results) == 1, "Forbidden proposal reached actual file I/O"
        assert answer_counts["forbidden-read"] == 2 and "forbidden-read:ceo" in core.provider.calls
        assert "APPROVAL REQUIRED" not in str(turn_observations[-1]["sse"])
        assert current_turn_tool_constraints().denial("read_file") is None
        assert len(expected_tasks) == 4
        assert case.client.get("/api/tasks").status_code == 401
        assert core.forbidden == []
    finally:
        set_access_mode(original_mode)
        proof.update({
            "answer_counts": answer_counts, "physical_reads": case.physical_reads,
            "physical_read_results": case.read_results, "tool_audit": case.tool_audit,
            "provider_calls": core.provider.calls, "expected_task_outputs": expected_tasks,
            "forbidden": core.forbidden,
        })
        capture = os.environ.get("R43_CAPTURE_ROOT")
        if capture:
            destination = Path(capture)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "r55-memory-lifecycle.json").write_text(
                json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
