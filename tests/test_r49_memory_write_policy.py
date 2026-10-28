"""Request policy and approval boundaries for memory writes; synthetic storage only."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import reset_bound_request_execution_context, set_bound_request_execution_context
from antigravity_k.api.routes import approval_api
from antigravity_k.engine import approval_manager, project_embedding_binding
from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
from antigravity_k.engine.approval_manager import ApprovalManager, ApprovalStatus
from antigravity_k.engine.approval_review import ApprovalReviewEngine
from antigravity_k.engine.gate_pipeline import create_default_pipeline
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.base_tool import RiskLevel
from antigravity_k.tools.memory_tools import SearchKnowledgeTool, StoreKnowledgeTool
from antigravity_k.tools.system_tools import ReplaceFileContentTool
from antigravity_k.tools.tool_registry import ToolRegistry

ARGS = {"knowledge_text": "synthetic launch label BLUE", "tags": ["synthetic"]}


@dataclass
class StorageProbe:
    constructors: list[dict[str, object]] = field(default_factory=list)
    bindings: int = 0
    document_embeddings: list[str] = field(default_factory=list)
    query_embeddings: list[str] = field(default_factory=list)
    writes: list[list[dict[str, object]]] = field(default_factory=list)
    queries: list[tuple[str, int]] = field(default_factory=list)

    def construct(self, **kwargs: object) -> RecordingStore:
        self.constructors.append(kwargs)
        return RecordingStore(self)

    def binding(self) -> None:
        self.bindings += 1


class RecordingStore:
    """Narrow fake VectorStore, including counted fake embedding work."""

    def __init__(self, probe: StorageProbe) -> None:
        self.probe = probe

    def upsert_chunks(self, chunks: Sequence[Mapping[str, object]]) -> None:
        self.probe.writes.append([dict(chunk) for chunk in chunks])
        self.probe.document_embeddings.extend(str(chunk["text"]) for chunk in chunks)

    def search(self, query: str, n_results: int = 5) -> list[dict[str, object]]:
        self.probe.queries.append((query, n_results))
        self.probe.query_embeddings.append(query)
        return [{"text": "synthetic recalled fact"}]


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Iterator[StorageProbe]:
    probe = StorageProbe()
    module = ModuleType("antigravity_k.engine.vector_store")
    module.VectorStore = probe.construct
    monkeypatch.setitem(sys.modules, "antigravity_k.engine.vector_store", module)
    monkeypatch.setattr(project_embedding_binding, "configured_embedding_binding_or_none", probe.binding)
    yield probe
    request.node.user_properties.append(("synthetic_storage_counts", json.dumps({
        "constructors": len(probe.constructors), "binding_requests": probe.bindings,
        "document_embeddings": len(probe.document_embeddings), "query_embeddings": len(probe.query_embeddings),
        "upserts": len(probe.writes), "searches": len(probe.queries),
    }, sort_keys=True)))


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "synthetic-project"
    root.mkdir()
    prior_mode = get_access_mode()
    token = set_bound_request_execution_context(RequestExecutionContext(
        request_id="synthetic-request", task_id="synthetic-task", project_id="synthetic-project",
        canonical_project_root=str(root), conversation_id="synthetic-conversation", conversation_revision=0,
        actor_subject="synthetic-user", session_id="synthetic-session", model_id="synthetic-model",
    ))
    # Real deterministic review and real approval evidence. No model reviewer or auto grant.
    manager = ApprovalManager(review_provider=ApprovalReviewEngine())
    monkeypatch.setattr(approval_manager, "_approval_manager", manager)
    # Unrelated optional recovery subsystem is not needed to dispatch this tool.
    monkeypatch.setattr("antigravity_k.engine.tool_executor.ImmuneSystem", lambda *_a, **_kw: None)
    try:
        yield root, manager
    finally:
        reset_bound_request_execution_context(token)
        set_access_mode(prior_mode)


def executor_for(root: Path, *, pipeline: bool = True) -> tuple[ToolExecutor, StoreKnowledgeTool]:
    registry = ToolRegistry(project_root=str(root))
    # Keep ordinary interactive approval. FULL_ACCESS does not mean auto-pilot.
    registry.permission_gate.mode = "balanced"
    store = StoreKnowledgeTool(project_root=str(root))
    registry.install(store)
    registry.install(SearchKnowledgeTool(project_root=str(root)))
    return ToolExecutor(
        tool_registry=registry, permission_gate=registry.permission_gate, project_root=str(root),
        gate_pipeline=create_default_pipeline() if pipeline else None,
    ), store


def run_request(executor: ToolExecutor, name: str, args: dict[str, object], *, read_only: bool) -> str:
    set_access_mode(AccessMode.READ_ONLY if read_only else AccessMode.FULL_ACCESS)
    token = set_tool_policy(ToolPolicy(safe_only=read_only))
    try:
        return executor.execute(name, args)
    finally:
        reset_tool_policy(token)


def assert_no_write_work(storage: StorageProbe) -> None:
    assert storage.constructors == []
    assert storage.bindings == 0
    assert storage.document_embeddings == []
    assert storage.query_embeddings == []
    assert storage.writes == []


def test_memory_write_has_same_side_effect_class_as_file_write() -> None:
    assert StoreKnowledgeTool.risk_level is ReplaceFileContentTool.risk_level is RiskLevel.LOW
    assert SearchKnowledgeTool.risk_level is RiskLevel.SAFE


@pytest.mark.parametrize("pipeline", [False, True])
@pytest.mark.parametrize("cached_store", [False, True])
def test_readonly_blocks_before_storage_embedding_or_approval(environment, storage: StorageProbe, pipeline, cached_store):
    root, manager = environment
    executor, store = executor_for(root, pipeline=pipeline)
    if cached_store:
        store._vector_store = RecordingStore(storage)
    result = run_request(executor, "store_knowledge", dict(ARGS), read_only=True)
    assert "[BLOCKED]" in result and "read-only" in result, result
    assert_no_write_work(storage)
    assert manager.get_pending() == []
    assert manager.always_allowed_grants() == []
    assert not (root / ".antigravity" / "vault_data").exists()


def test_full_access_requires_synthetic_human_approval_and_executes_once(environment, storage: StorageProbe):
    root, manager = environment
    executor, _ = executor_for(root)
    first = run_request(executor, "store_knowledge", dict(ARGS), read_only=False)
    assert "[APPROVAL REQUIRED]" in first
    assert_no_write_work(storage)
    pending = manager.get_pending()
    assert len(pending) == 1 and pending[0].tool_name == "store_knowledge"
    request_id = pending[0].request_id
    assert pending[0].status is ApprovalStatus.PENDING

    # Production route + real manager, in-process only. This is a synthetic human input,
    # not an automatic approval policy. Authentication of the full app is outside this test.
    app = FastAPI()
    app.include_router(approval_api.router)
    response = TestClient(app).post(f"/api/approval/{request_id}/resolve", json={"decision": "approve"})
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert manager.always_allowed_grants() == []

    # Even an existing human approval must not overrule the current read-only request.
    blocked = run_request(executor, "store_knowledge", dict(ARGS), read_only=True)
    assert "[BLOCKED]" in blocked and "read-only" in blocked
    assert_no_write_work(storage)
    assert request_id not in manager._consumed_approvals

    result = run_request(executor, "store_knowledge", dict(ARGS), read_only=False)
    assert result.startswith("Successfully stored knowledge. ID: "), result
    assert len(storage.constructors) == storage.bindings == len(storage.writes) == 1
    assert storage.document_embeddings == [ARGS["knowledge_text"]]
    assert storage.query_embeddings == []
    chunk = storage.writes[0][0]
    assert chunk["id"] == result.removeprefix("Successfully stored knowledge. ID: ")
    assert chunk["text"] == ARGS["knowledge_text"]
    assert chunk["metadata"] == {"type": "agent_knowledge", "tags": "synthetic"}
    assert storage.constructors[0]["persist_directory"] == str(root / ".antigravity" / "vault_data")
    assert request_id in manager._consumed_approvals

    repeated = run_request(executor, "store_knowledge", dict(ARGS), read_only=False)
    assert "[APPROVAL REQUIRED]" in repeated
    assert len(storage.writes) == len(storage.constructors) == 1
    assert manager.always_allowed_grants() == []


def test_readonly_search_still_uses_normal_lookup_without_upsert(environment, storage: StorageProbe):
    root, manager = environment
    executor, _ = executor_for(root)
    result = run_request(executor, "search_knowledge", {"query": "synthetic query", "max_results": 2}, read_only=True)
    assert result == "Found knowledge:\n- synthetic recalled fact"
    assert storage.queries == [("synthetic query", 2)]
    assert storage.query_embeddings == ["synthetic query"]
    assert storage.document_embeddings == storage.writes == []
    assert manager.get_pending() == []


def test_explicit_tool_toggle_denial_still_precedes_storage(environment, storage: StorageProbe):
    root, manager = environment
    executor, _ = executor_for(root)
    set_access_mode(AccessMode.FULL_ACCESS)
    token = set_tool_policy(ToolPolicy(denied_tools=frozenset({"store_knowledge"})))
    try:
        result = executor.execute("store_knowledge", dict(ARGS))
    finally:
        reset_tool_policy(token)
    assert "[BLOCKED]" in result and "disabled for this request" in result
    assert_no_write_work(storage)
    assert manager.get_pending() == []
