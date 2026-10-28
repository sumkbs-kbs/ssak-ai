"""Authenticated direct-task ownership with synthetic principals and in-process ASGI.

Only the provider is scripted. Authentication, project binding, direct task creation,
the shared task database, task APIs and resume execution are production code.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

MODEL = "r45-scripted-model"
QUESTION = "합성 프로젝트의 배지 코드명이 무엇인지 코드만 답해줘."
ALPHA = "ALPHA-OWNERSHIP-7342"
BETA = "BETA-OWNERSHIP-5186"


class AccountProvider:
    def __init__(self, registry: object, marker: str) -> None:
        self._registry = registry
        self.router = SimpleNamespace(get_combo=lambda name: None)
        self.marker = marker
        self.interrupt_once = False
        self.observations: list[dict[str, object]] = []

    def is_loaded(self, name: str) -> bool:
        return True

    def get_model_info(self) -> dict[str, object]:
        return {"name": MODEL, "loaded": True, "provider": "scripted-test-provider"}

    def generate(self, *, prompt: str, target: str, max_tokens: int = 1024, **kwargs: object) -> str:
        self._observe()
        if max_tokens == 10:
            return "MEMORY"
        return self.marker

    def _observe(self) -> None:
        from antigravity_k.api.project_binding import get_bound_request_execution_context

        bound = get_bound_request_execution_context()
        self.observations.append(
            {"marker": self.marker, "context": bound.model_dump() if bound is not None else None}
        )

    def stream_generate(self, *, prompt: str, target: str, **kwargs: object) -> Iterator[str]:
        self._observe()
        if kwargs.get("response_format") == "json":
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": QUESTION})
            return
        if self.interrupt_once:
            from antigravity_k.engine.provider_adapters.transport_errors import NativeProtocolError

            self.interrupt_once = False
            yield ""
            # A scripted incomplete stream, not a physical network interruption.
            raise NativeProtocolError("incomplete_stream")
        yield self.marker


@dataclass
class OwnerCase:
    client: TestClient
    app: FastAPI
    state: dict[str, object]
    providers: dict[str, AccountProvider]
    project_ids: dict[str, str]
    headers: dict[str, dict[str, str]] = field(repr=False)
    restart: object = field(repr=False)

    def chat(self, subject: str = "user", project: str = "alpha", **extra: object):
        body = {
            "model": MODEL,
            "project_id": self.project_ids[project],
            "conversation_id": "r45-" + subject + "-" + str(time.monotonic_ns()),
            "messages": [{"role": "user", "content": QUESTION}],
            "stream": True,
            "agent_mode": True,
            "web_search": False,
            "code_mode": False,
            "mcp_servers": [],
        }
        body.update(extra)
        return self.client.post("/v1/chat/completions", json=body, headers=self.headers[subject])

    def rows(self):
        return self.state["runner"].state_store.list_tasks(100)


@pytest.fixture
def owner_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OwnerCase]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)

    from antigravity_k.api import auth_policy, auth_routes, dependencies, project_binding
    from antigravity_k.api.contracts.errors import ExecutionContextError
    from antigravity_k.api.error_handler import global_exception_handler
    from antigravity_k.api.routes import chat, filesystem, session_state, task_api
    from antigravity_k.api.server import verify_access_token
    from antigravity_k.config import config
    from antigravity_k.engine import conversation_store, request_execution_context
    from antigravity_k.engine import project_registry as project_registry_module
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.audit_logger import AuditLogger
    from antigravity_k.engine.conversation_store import ConversationStore
    from antigravity_k.engine.embeddings import EmbeddingEngine
    from antigravity_k.engine.memory_provider import MemoryManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
    from antigravity_k.engine.project_registry import ProjectRegistry
    from antigravity_k.engine.project_runtime import ProjectRuntime, ProjectRuntimeRegistry
    from antigravity_k.engine.protocol_translator import ProtocolTranslator
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.engine.task_runner import BackgroundTaskRunner
    from antigravity_k.tools.tool_registry import ToolRegistry

    def denied_model(*args: object, **kwargs: object) -> object:
        raise AssertionError("Real embedding/model loading is forbidden in the ownership regression")

    monkeypatch.setattr(EmbeddingEngine, "embed", denied_model)
    monkeypatch.setattr(EmbeddingEngine, "load_model", denied_model)
    monkeypatch.setattr(EmbeddingEngine, "_fallback_embedding", denied_model)
    monkeypatch.setattr(config.paths, "project_root", tmp_path.resolve())
    monkeypatch.setattr(config.security, "access_pin", "r45-synthetic-pin")
    monkeypatch.setattr(config.security, "pin_hash_file", str(tmp_path / "auth_hash"))
    monkeypatch.setattr(config.security, "token_secret_file", str(tmp_path / "token_secret"))
    monkeypatch.setattr(auth_routes, "_token_service", None)
    monkeypatch.setattr(auth_routes, "_pin_hash", None)
    monkeypatch.setattr(auth_policy, "_shared_auth_policy", None)
    monkeypatch.setattr(project_binding, "_session_bindings", project_binding.SessionProjectBindingStore())
    auth_routes.init_auth_state()

    registry_path = tmp_path / "projects.json"
    registry = ProjectRegistry(storage_path=registry_path)
    project_ids: dict[str, str] = {}
    for name in ("alpha", "beta"):
        root = tmp_path / "projects" / name
        root.mkdir(parents=True)
        (root / "config.yaml").write_text(
            yaml.safe_dump({"agent_models": {"default": MODEL}, "model": {"complex_task_thinking": False},
                            "amplification": {"cognitive": {"enabled": False}, "self_evolution": {"enabled": False}},
                            "self_evolution": {"auto_modify": False}, "ambient_partner": {"watchdog_enabled": False}})
        )
        project_ids[name] = registry.add_project(name=name, path=str(root)).id
    registry.switch_project(project_ids["alpha"])
    model_config = tmp_path / "models.yaml"
    model_config.write_text(yaml.safe_dump({"models": {"reasoning": [{"name": MODEL, "repo": MODEL,
                                                                         "provider": "ollama", "context_length": 32768}]}}))
    model_registry = ModelRegistry(config_path=str(model_config))
    database = tmp_path / "shared-tasks.db"
    state: dict[str, object] = {"runner": BackgroundTaskRunner(db_path=str(database)),
                                "registry": registry, "runtimes": ProjectRuntimeRegistry()}
    providers: dict[str, AccountProvider] = {}

    def build_runtime(project_id: str, project_root: str) -> ProjectRuntime:
        provider = AccountProvider(model_registry, ALPHA if project_id == project_ids["alpha"] else BETA)
        providers[project_id] = provider
        session = SessionManager(base_dir=str(Path(project_root) / ".antigravity" / "sessions"))
        memory = MemoryManager(project_root=project_root)
        tools = ToolRegistry(project_root=project_root)
        orch = OrchestratorAgent(provider, project_root=project_root, project_id=project_id,
                                 session_manager=session, memory_manager=memory, tool_registry=tools)
        runtime = AgentRuntime(orch, task_runner=state["runner"])
        return ProjectRuntime(project_id, project_root, memory, session, orch, agent_runtime=runtime)

    monkeypatch.setattr(project_binding, "get_project_registry", lambda: state["registry"])
    monkeypatch.setattr(project_registry_module, "get_project_registry", lambda: state["registry"])
    monkeypatch.setattr(request_execution_context, "get_project_registry", lambda: state["registry"])
    if hasattr(dependencies, "get_project_registry"):
        monkeypatch.setattr(dependencies, "get_project_registry", lambda: state["registry"])
    monkeypatch.setattr(dependencies, "get_project_runtime_registry", lambda: state["runtimes"])
    monkeypatch.setattr(dependencies, "_build_project_runtime", build_runtime)
    monkeypatch.setattr(conversation_store, "_store_singleton", ConversationStore(storage_dir=tmp_path / "conversations"))
    monkeypatch.setattr(chat, "get_audit_logger", lambda: AuditLogger(log_dir=tmp_path / "audit"))
    monkeypatch.setattr(dependencies, "get_session_manager", lambda: dependencies.acquire_project_runtime().session_manager)
    monkeypatch.setattr(session_state, "_active_session", session_state.ActiveAgentSession())
    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", str(tmp_path))
    app = FastAPI()
    app.middleware("http")(verify_access_token)
    app.add_exception_handler(ExecutionContextError, global_exception_handler)
    app.include_router(auth_routes.router)
    app.include_router(chat.router)
    app.include_router(task_api.router)
    app.include_router(filesystem.router)
    app.dependency_overrides[chat.get_model_manager] = lambda: AccountProvider(model_registry, ALPHA)
    app.dependency_overrides[chat.get_translator] = ProtocolTranslator

    def restart() -> None:
        state["runtimes"].shutdown_all()
        state["runtimes"] = ProjectRuntimeRegistry()
        state["runner"] = BackgroundTaskRunner(db_path=str(database))
        state["registry"] = ProjectRegistry(storage_path=registry_path)
        auth_routes._token_service = None
        auth_routes._pin_hash = None
        auth_routes.init_auth_state()

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"pin": "r45-synthetic-pin"})
        assert login.status_code == 200
        service = auth_routes.get_token_service()
        headers = {"user": {"Authorization": "Bearer " + login.json()["access_token"]},
                   "foreign": {"Authorization": "Bearer " + service.issue_token(subject="foreign")}}
        yield OwnerCase(client, app, state, providers, project_ids, headers, restart)
    state["runtimes"].shutdown_all()


def _assert_own_visible_and_foreign_hidden(case: OwnerCase, task_id: str, output: str) -> None:
    own = case.client.get("/api/tasks", headers=case.headers["user"])
    assert own.status_code == 200
    assert task_id in {row["task_id"] for row in own.json()["data"]}
    result = case.client.get(f"/api/tasks/{task_id}/output", headers=case.headers["user"])
    assert result.status_code == 200 and result.json()["output"] == output
    foreign = case.client.get("/api/tasks", headers=case.headers["foreign"])
    assert foreign.status_code == 200 and foreign.json()["data"] == []
    for suffix in ("status", "output", "events"):
        assert case.client.get(f"/api/tasks/{task_id}/{suffix}", headers=case.headers["foreign"]).status_code == 404
    assert case.client.post(f"/api/tasks/{task_id}/resume", headers=case.headers["foreign"]).status_code == 404


def test_login_chat_task_is_visible_to_its_authenticated_owner_only(owner_case: OwnerCase) -> None:
    case = owner_case
    response = case.chat()
    assert response.status_code == 200 and ALPHA in response.text
    (row,) = case.rows()
    assert case.state["runner"].state_store.get_task(row["task_id"], owner_subject="user") is not None
    assert row["status"] == "done"
    _assert_own_visible_and_foreign_hidden(case, row["task_id"], ALPHA)


@pytest.mark.parametrize("spoof", [{"actor_subject": "foreign"}, {"execution_context": {"actor_subject": "foreign"}},
                                   {"owner_subject": "foreign", "context": {"actor_subject": "foreign"}},
                                   {"execution_context": {"actor_subject": "foreign", "project_id": "replace-with-alpha"}}])
def test_client_identity_fields_cannot_override_verified_actor(owner_case: OwnerCase, spoof: dict[str, object]) -> None:
    nested = spoof.get("execution_context")
    if isinstance(nested, dict) and nested.get("project_id") == "replace-with-alpha":
        spoof = {"execution_context": {**nested, "project_id": owner_case.project_ids["alpha"]}}
    response = owner_case.chat(**spoof)
    assert response.status_code == 200
    (row,) = owner_case.rows()
    assert owner_case.state["runner"].state_store.get_task(row["task_id"], owner_subject="user") is not None
    observations = owner_case.providers[owner_case.project_ids["alpha"]].observations
    assert observations and all(item["context"]["actor_subject"] == "user" for item in observations)
    _assert_own_visible_and_foreign_hidden(owner_case, row["task_id"], ALPHA)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-synthetic-token"}])
def test_unauthenticated_requests_cannot_create_or_read_tasks(owner_case: OwnerCase, headers: dict[str, str]) -> None:
    case = owner_case
    for path in ("/api/tasks", "/api/tasks/unknown/status", "/api/tasks/unknown/output"):
        assert case.client.get(path, headers=headers).status_code == 401
    assert case.client.post("/api/tasks/unknown/resume", headers=headers).status_code == 401
    assert case.client.post("/api/tasks/submit", headers=headers, json={"prompt": QUESTION}).status_code == 401
    assert case.client.post("/v1/chat/completions", headers=headers, json={"messages": [{"role": "user", "content": QUESTION}]}).status_code == 401
    assert case.rows() == []


def test_authenticated_background_submission_retains_owner_and_ignores_nested_actor_spoof(owner_case: OwnerCase) -> None:
    case = owner_case
    response = case.client.post(
        "/api/tasks/submit",
        headers=case.headers["user"],
        json={"prompt": QUESTION, "model": MODEL, "project_id": case.project_ids["alpha"],
              "context": {"execution_context": {"project_id": case.project_ids["alpha"],
                                                  "actor_subject": "foreign"}}},
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = case.state["runner"].state_store.get_task(task_id, owner_subject="user")
        if row is not None and row["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert row is not None and row["status"] == "done"
    assert row["output"].count(ALPHA) == 1 and BETA not in row["output"]
    observations = case.providers[case.project_ids["alpha"]].observations
    assert observations and all(item["context"]["actor_subject"] == "user" for item in observations)
    _assert_own_visible_and_foreign_hidden(case, task_id, row["output"])


def test_owner_survives_auth_and_runtime_restart(owner_case: OwnerCase) -> None:
    case = owner_case
    assert case.chat().status_code == 200
    (before,) = case.rows()
    case.restart()
    _assert_own_visible_and_foreign_hidden(case, before["task_id"], ALPHA)
    assert case.rows() == [before]


def test_switching_verified_principals_preserves_each_tasks_owner(owner_case: OwnerCase) -> None:
    case = owner_case
    assert case.chat("user").status_code == 200
    (first,) = case.rows()
    assert case.chat("foreign").status_code == 200
    rows = case.rows()
    assert len(rows) == 2
    second = next(row for row in rows if row["task_id"] != first["task_id"])
    for subject, own, other in (("user", first, second), ("foreign", second, first)):
        listing = case.client.get("/api/tasks", headers=case.headers[subject])
        assert listing.status_code == 200
        assert {row["task_id"] for row in listing.json()["data"]} == {own["task_id"]}
        assert case.client.get(f"/api/tasks/{own['task_id']}/output", headers=case.headers[subject]).status_code == 200
        assert case.client.get(f"/api/tasks/{other['task_id']}/output", headers=case.headers[subject]).status_code == 404
    case.restart()
    for subject, own in (("user", first), ("foreign", second)):
        listing = case.client.get("/api/tasks", headers=case.headers[subject])
        assert {row["task_id"] for row in listing.json()["data"]} == {own["task_id"]}


def test_resume_after_project_switch_and_restart_uses_original_owner_and_project(owner_case: OwnerCase) -> None:
    case = owner_case
    # Build alpha before arming the synthetic provider interruption.
    from antigravity_k.api import dependencies
    from antigravity_k.api.project_binding import reset_bound_request_execution_context

    reset_bound_request_execution_context()
    dependencies.acquire_project_runtime(project_id=case.project_ids["alpha"])
    case.providers[case.project_ids["alpha"]].interrupt_once = True
    response = case.chat()
    assert response.status_code == 200
    (before,) = case.rows()
    assert before["status"] == "failed", "The real direct stream must leave a resumable failed checkpoint"
    task_id = before["task_id"]
    assert case.state["runner"].state_store.get_task(before["task_id"], owner_subject="user") is not None
    switch = case.client.post("/api/projects/switch", headers=case.headers["user"],
                              json={"project_id": case.project_ids["beta"]})
    assert switch.status_code == 200
    case.restart()
    assert case.state["registry"].get_active_project().id == case.project_ids["beta"]
    assert case.client.post(f"/api/tasks/{task_id}/resume", headers=case.headers["foreign"]).status_code == 404
    assert case.rows() == [before]
    resumed = case.client.post(f"/api/tasks/{task_id}/resume", headers=case.headers["user"])
    assert resumed.status_code == 200
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = case.state["runner"].state_store.get_task(task_id)
        if row["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert row["status"] == "done"
    assert row["output"].count(ALPHA) == 1 and BETA not in row["output"]
    assert case.state["runner"].state_store.get_task(task_id, owner_subject="user") is not None
    observations = case.providers[case.project_ids["alpha"]].observations
    assert observations and all(item["context"]["actor_subject"] == "user" for item in observations)
    assert all(item["context"]["project_id"] == case.project_ids["alpha"] for item in observations)
    assert all(Path(item["context"]["canonical_project_root"]).name == "alpha" for item in observations)
    beta_provider = case.providers.get(case.project_ids["beta"])
    assert beta_provider is None or beta_provider.observations == []
    _assert_own_visible_and_foreign_hidden(case, task_id, row["output"])


def test_fork_after_project_switch_preserves_source_boundary_and_is_resumable(owner_case: OwnerCase) -> None:
    case = owner_case
    assert case.chat().status_code == 200
    (source_before,) = case.rows()
    source_id = source_before["task_id"]
    store = case.state["runner"].state_store
    source_checkpoint = store.get_last_checkpoint(source_id)
    source_events = store.list_execution_events(source_id)
    alpha_provider = case.providers[case.project_ids["alpha"]]
    initial_observations = len(alpha_provider.observations)
    switch = case.client.post("/api/projects/switch", headers=case.headers["user"],
                              json={"project_id": case.project_ids["beta"]})
    assert switch.status_code == 200
    fork_payload = {"prompt": "합성 프로젝트의 배지 코드명을 알려줘.", "model": MODEL}
    denied = case.client.post(f"/api/tasks/{source_id}/fork", headers=case.headers["foreign"], json=fork_payload)
    assert denied.status_code == 404
    assert case.rows() == [source_before]
    alpha_provider.interrupt_once = True
    fork = case.client.post(f"/api/tasks/{source_id}/fork", headers=case.headers["user"], json=fork_payload)
    assert fork.status_code == 202
    fork_id = fork.json()["task_id"]
    assert fork_id != source_id and fork.json()["source_task_id"] == source_id
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = store.get_task(fork_id, owner_subject="user")
        if row is not None and row["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert row is not None and row["status"] == "failed"
    checkpoint = store.get_last_checkpoint(fork_id)
    assert checkpoint is not None
    context = json.loads(checkpoint["context_json"])
    assert context["execution_context"]["project_id"] == case.project_ids["alpha"]
    assert context["execution_context"]["actor_subject"] == "user"
    assert context["execution_context"].get("task_id") in {None, fork_id}
    assert Path(context["execution_context"]["canonical_project_root"]).name == "alpha"
    assert case.state["registry"].get_active_project().id == case.project_ids["beta"]
    assert case.client.post(f"/api/tasks/{fork_id}/resume", headers=case.headers["foreign"]).status_code == 404
    assert case.client.post(f"/api/tasks/{fork_id}/resume", headers=case.headers["user"]).status_code == 200
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = store.get_task(fork_id, owner_subject="user")
        if row is not None and row["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert row is not None and row["status"] == "done"
    assert row["output"].count(ALPHA) == 1 and BETA not in row["output"]
    observations = alpha_provider.observations[initial_observations:]
    assert observations and all(item["context"]["project_id"] == case.project_ids["alpha"] for item in observations)
    assert all(item["context"]["actor_subject"] == "user" for item in observations)
    assert all(item["context"].get("task_id") in {None, fork_id} for item in observations)
    beta_provider = case.providers.get(case.project_ids["beta"])
    assert beta_provider is None or beta_provider.observations == []
    assert case.state["registry"].get_active_project().id == case.project_ids["beta"]
    assert store.get_task(source_id) == source_before
    assert store.get_last_checkpoint(source_id) == source_checkpoint
    assert store.list_execution_events(source_id) == source_events
    _assert_own_visible_and_foreign_hidden(case, fork_id, row["output"])
