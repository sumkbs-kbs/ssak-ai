"""B recall through the real chat/router/runtime/store/tool path, with synthetic providers.

No listener is started. TestClient drives ASGI in-process. Only the model manager and
embedding engine are scripted; project binding, Chroma, vault, agent graph, tool execution,
conversation persistence and task persistence run their production implementations.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import override

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

FACT = "HERON-CALDERA-7342"
OTHER = "OTHER-PROJECT-ANCHOR-9821"
QUESTION = "Quillmere 오프사이트 배지 색상으로 우리가 정했던 것은 무엇이었지? 코드만 답해줘."
NOTE_ID = "r42/synthetic-decision.md"
MODEL = "r43-scripted-model"
EMBED = "r43-scripted-embedding"


class ScriptedProvider:
    """Return a known provider transcript; never replace the runtime or its tools."""

    def __init__(self, registry: object, *, force_read: bool) -> None:
        self._registry = registry
        self.router = SimpleNamespace(get_combo=lambda name: None)
        self.force_read = force_read
        self.prompts: list[str] = []
        self.calls: list[str] = []
        self.answer_calls = 0

    def is_loaded(self, name: str) -> bool:
        return True

    def get_model_info(self) -> dict[str, object]:
        return {"name": MODEL, "loaded": True, "provider": "scripted-test-provider"}

    def generate(self, *, prompt: str, target: str, max_tokens: int = 1024, **kwargs: object) -> str:
        self.prompts.append(prompt)
        if max_tokens == 10:
            self.calls.append("intent")
            return "MEMORY"
        self.calls.append("unexpected_generate")
        raise AssertionError("Unexpected provider call, including a gratuitous quality revision")

    def stream_generate(self, *, prompt: str, target: str, **kwargs: object) -> Iterator[str]:
        self.prompts.append(prompt)
        if kwargs.get("response_format") == "json":
            self.calls.append("ceo")
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": QUESTION})
            return
        self.calls.append("answer")
        self.answer_calls += 1
        assert OTHER not in prompt, "Another project's stored memory reached the provider"
        assert FACT in prompt, "The answer must be grounded in the retrieved synthetic note"
        if self.answer_calls == 1:
            supplied = "already supplied" in prompt and "do not need another read_file" in prompt
            if self.force_read or not supplied:
                path = re.search(r"read_file path: ([^\n]+)", prompt)
                read_path = path.group(1).strip() if path else NOTE_ID
                yield FACT + "\n\n"
                yield (
                    "<tool_call>"
                    + json.dumps({"name": "read_file", "arguments": {"file_path": read_path}})
                    + "</tool_call>"
                )
                return
        yield FACT


@dataclass
class IntegrationCase:
    app: FastAPI
    client: TestClient
    registry: object
    runtimes: dict[str, object]
    provider: ScriptedProvider
    conversations: object
    project_id: str
    forbidden: list[str]
    embedding_calls: list[list[str]]
    evidence: dict[str, object] = field(default_factory=dict)


@pytest.fixture
def integration_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[IntegrationCase]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)
    forbidden: list[str] = []

    def deny_network(*args: object, **kwargs: object) -> object:
        forbidden.append("physical_network")
        raise AssertionError("Physical network is forbidden in the scripted-provider regression")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    original_popen = subprocess.Popen

    class GuardedPopen(original_popen):
        def __init__(self, args: object, *positional: object, **kwargs: object) -> None:
            command = list(args) if isinstance(args, (list, tuple)) else []
            allowed = command == ["file", "-b", sys.executable]
            allowed = allowed or (
                len(command) >= 2
                and Path(str(command[0])).name == "git"
                and command[1] in {"init", "status", "diff", "rev-parse", "log", "check-ignore"}
            )
            if not allowed:
                forbidden.append("subprocess:" + (str(command[1]) if len(command) > 1 else "shell"))
                raise AssertionError("Only synthetic vault initialization and read-only runtime queries are permitted")
            super().__init__(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)

    from antigravity_k.api import dependencies, project_binding
    from antigravity_k.api.contracts.errors import ExecutionContextError
    from antigravity_k.api.error_handler import global_exception_handler
    from antigravity_k.api.routes import chat, session_state
    from antigravity_k.config import config
    from antigravity_k.engine import conversation_store
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.audit_logger import AuditLogger
    from antigravity_k.engine.conversation_store import ConversationStore
    from antigravity_k.engine.embeddings import EmbeddingEngine
    from antigravity_k.engine.memory_provider import MemoryManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
    from antigravity_k.engine.project_embedding_binding import ProjectEmbeddingBinding
    from antigravity_k.engine.project_registry import ProjectRegistry
    from antigravity_k.engine.project_runtime import ProjectRuntime, ProjectRuntimeRegistry
    from antigravity_k.engine.protocol_translator import ProtocolTranslator
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.engine.task_runner import BackgroundTaskRunner
    from antigravity_k.engine.vault import VaultEngine
    from antigravity_k.engine.vector_store import VectorStore
    from antigravity_k.tools.system_tools import ReadFileTool
    from antigravity_k.tools.tool_registry import ToolRegistry

    def deny_model(*args: object, **kwargs: object) -> object:
        forbidden.append("physical_model_or_embedding_fallback")
        raise AssertionError("Physical model loading and fallback embeddings are forbidden")

    monkeypatch.setattr(EmbeddingEngine, "load_model", deny_model)
    monkeypatch.setattr(EmbeddingEngine, "_fallback_embedding", deny_model)
    embedding_calls: list[list[str]] = []

    class ScriptedEmbedding(EmbeddingEngine):
        @override
        def embed(self, text: str | list[str], model_name: str, *, allow_fallback: bool = True) -> list[list[float]]:
            assert model_name == EMBED and allow_fallback is False
            texts = [text] if isinstance(text, str) else list(text)
            embedding_calls.append(texts)
            return [[1.0, 0.25, 0.5, 0.75] for item in texts]

    monkeypatch.setattr(config.paths, "project_root", tmp_path.resolve())
    project_registry = ProjectRegistry(storage_path=tmp_path / "project-registry.json")
    model_config = tmp_path / "models.yaml"
    model_config.write_text(
        yaml.safe_dump(
            {
                "models": {
                    "embedding": [{"name": EMBED, "repo": EMBED, "provider": "ollama", "dimensions": 4}],
                    "reasoning": [{"name": MODEL, "repo": MODEL, "provider": "ollama", "context_length": 32768}],
                }
            }
        )
    )
    model_registry = ModelRegistry(config_path=str(model_config))
    provider = ScriptedProvider(model_registry, force_read=bool(request.param) if hasattr(request, "param") else True)
    embedder = ScriptedEmbedding(registry=model_registry)
    project_a = tmp_path / "projects" / "alpha"
    project_b = tmp_path / "projects" / "beta"
    project_ids: dict[str, str] = {}
    vaults: dict[str, VaultEngine] = {}
    for root, fact in ((project_a, FACT), (project_b, OTHER)):
        root.mkdir(parents=True)
        (root / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "agent_models": {"default": MODEL},
                    "amplification": {"cognitive": {"enabled": False}, "self_evolution": {"enabled": False}},
                    "self_evolution": {"auto_modify": False},
                    "ambient_partner": {"watchdog_enabled": False},
                    "model": {"complex_task_thinking": False},
                }
            )
        )
        project = project_registry.add_project(name=root.name, path=str(root))
        project_ids[root.name] = project.id
        vault = VaultEngine(str(root / ".antigravity" / "vault_data"), sync_rag=False)
        note = vault.vault_path / NOTE_ID
        note.parent.mkdir(parents=True)
        note.write_text(
            "---\ntitle: Synthetic decision\ntags: [synthetic]\n---\nQuillmere 오프사이트 배지 색상 코드는 "
            + fact
            + ".\n",
            encoding="utf-8",
        )
        vectors = VectorStore(
            str(vault.vault_path / ".chroma"), embedding_binding=ProjectEmbeddingBinding(embedder, EMBED)
        )
        vectors.upsert_chunks([{"id": "synthetic-decision", "text": note.read_text(), "metadata": {"source": NOTE_ID}}])
        vault.vector_store = vectors
        vault.sync_rag = True
        vaults[project.id] = vault

    runtimes: dict[str, ProjectRuntime] = {}
    runtime_registry = ProjectRuntimeRegistry()

    def build_runtime(project_id: str, project_root: str) -> ProjectRuntime:
        session = SessionManager(base_dir=str(Path(project_root) / ".antigravity" / "sessions"))
        memory = MemoryManager(project_root=project_root)
        tools = ToolRegistry(project_root=project_root)
        tools.install(ReadFileTool())
        orch = OrchestratorAgent(
            provider,
            vault_engine=vaults[project_id],
            project_root=project_root,
            project_id=project_id,
            session_manager=session,
            memory_manager=memory,
            tool_registry=tools,
        )
        runner = BackgroundTaskRunner(db_path=str(Path(project_root) / ".antigravity" / "tasks.db"))
        runtime = AgentRuntime(orch, task_runner=runner)
        handle = ProjectRuntime(
            project_id, project_root, memory, session, orch, agent_runtime=runtime, vault_engine=vaults[project_id]
        )
        runtimes[project_id] = handle
        return handle

    conversations = ConversationStore(storage_dir=tmp_path / "conversations")
    monkeypatch.setattr(project_binding, "get_project_registry", lambda: project_registry)
    monkeypatch.setattr(dependencies, "get_project_runtime_registry", lambda: runtime_registry)
    monkeypatch.setattr(dependencies, "_build_project_runtime", build_runtime)
    monkeypatch.setattr(conversation_store, "_store_singleton", conversations)
    monkeypatch.setattr(chat, "get_audit_logger", lambda: AuditLogger(log_dir=tmp_path / "audit"))
    monkeypatch.setattr(
        dependencies, "get_session_manager", lambda: dependencies.acquire_project_runtime().session_manager
    )
    monkeypatch.setattr(session_state, "_active_session", session_state.ActiveAgentSession())
    app = FastAPI()
    app.add_exception_handler(ExecutionContextError, global_exception_handler)
    app.include_router(chat.router)
    app.dependency_overrides[chat.get_model_manager] = lambda: provider
    app.dependency_overrides[chat.get_translator] = ProtocolTranslator
    with TestClient(app) as client:
        case = IntegrationCase(
            app,
            client,
            project_registry,
            runtimes,
            provider,
            conversations,
            project_ids["alpha"],
            forbidden,
            embedding_calls,
        )
        yield case
    for handle in runtimes.values():
        handle.shutdown()
    for vault in vaults.values():
        vault.vector_store.close()
    capture = os.environ.get("R43_CAPTURE_ROOT")
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        case.evidence.update(
            {
                "provider_calls": provider.calls,
                "provider_prompts": provider.prompts,
                "embedding_inputs": embedding_calls,
                "forbidden": forbidden,
            }
        )
        name = "forced-read" if provider.force_read else "supplied-evidence"
        (target / f"integration-{name}.json").write_text(
            json.dumps(case.evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    assert forbidden == []


@pytest.mark.parametrize("integration_case", [True, False], indirect=True, ids=["forced-read", "supplied-evidence"])
def test_b_agent_recall_keeps_one_answer_and_project_scoped_evidence(integration_case: IntegrationCase) -> None:
    case = integration_case
    response = case.client.post(
        "/v1/chat/completions",
        json={
            "model": MODEL,
            "project_id": case.project_id,
            "conversation_id": "r43-b-agent",
            "messages": [{"role": "user", "content": QUESTION}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
            "code_mode": False,
            "mcp_servers": [],
        },
    )
    case.evidence["status_code"] = response.status_code
    case.evidence["sse"] = response.text
    assert response.status_code == 200
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    deltas = "".join(event.get("choices", [{}])[0].get("delta", {}).get("content", "") for event in events)
    finals = [event["agk_final_content"] for event in events if "agk_final_content" in event]
    record = case.conversations.get(project_id=case.project_id, conversation_id="r43-b-agent")
    answers = (
        [message.content for message in record.messages if message.role == "assistant"] if record is not None else []
    )
    case.evidence["conversation_answers"] = answers
    handle = case.runtimes[case.project_id]
    tasks = handle.agent_runtime.task_runner.state_store.list_tasks(10)
    case.evidence["tasks"] = tasks
    history = handle.orchestrator.ctx.tool_executor.tool_call_history
    case.evidence["tool_history"] = history
    assert finals and finals[-1] == FACT
    assert deltas == FACT
    assert OTHER not in response.text
    assert record is not None and answers == [FACT]
    assert len(tasks) == 1 and tasks[0]["status"] == "done" and tasks[0]["output"] == FACT
    if case.provider.force_read:
        assert len(history) == 1 and history[0]["name"] == "read_file" and history[0]["success"] is True
        assert "Error: File" not in response.text and "파일이 존재하지" not in response.text
        assert case.provider.answer_calls == 2
    else:
        assert history == [] and case.provider.answer_calls == 1
    assert "unexpected_generate" not in case.provider.calls
    assert len(case.embedding_calls) == 3
    assert case.forbidden == []
