"""A stored checkpoint cannot move a resumed task to another actor or project.

All rows and projects are synthetic. Rejected attempts exercise the real store,
runner and runtime; acquisition and dispatch sentinels make side effects visible.
Routing-only positive cases intercept dispatch before creating any worker thread.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import (
    execution_context_to_task_context,
    get_bound_request_execution_context,
    reset_bound_request_execution_context,
    set_bound_request_execution_context,
)
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.project_registry import ProjectRegistry
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskStateStore

TASK_ID = "direct_synthetic_authority"
OWNER = "synthetic-owner"
OTHER = "synthetic-other"


class UnusedOrchestrator:
    max_engine = None

    def get_model_for_role(self, role: str) -> str:
        return "synthetic-model"

    def run_stream(self, *args: object, **kwargs: object) -> Iterator[str]:
        raise AssertionError("Authority checks must not invoke a provider")
        yield "unreachable"


@dataclass
class AuthorityCase:
    store: TaskStateStore
    runner: BackgroundTaskRunner
    runtime: AgentRuntime
    registry: ProjectRegistry
    context: RequestExecutionContext
    beta_root: Path

    def save(self, checkpoint: object) -> None:
        self.store.save_checkpoint(TASK_ID, 0, json.dumps(checkpoint), "synthetic prefix")


@pytest.fixture
def authority_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AuthorityCase:
    from antigravity_k.config import config
    from antigravity_k.engine import request_execution_context

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    registry = ProjectRegistry(storage_path=tmp_path / "registry.json")
    project = registry.add_project("alpha", str(alpha))
    registry.add_project("beta", str(beta))
    monkeypatch.setattr(request_execution_context, "get_project_registry", lambda: registry)
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "synthetic-tasks.db"))
    store = runner.state_store
    store.create_task(TASK_ID, "synthetic task", "pending", "2026-10-27T00:00:00+00:00", owner_subject=OWNER)
    assert store.transition(TASK_ID, "running") is True
    assert store.transition(TASK_ID, "paused", output="synthetic prefix") is True
    context = RequestExecutionContext(
        request_id="synthetic-request", task_id=TASK_ID, project_id=project.id,
        canonical_project_root=str(alpha.resolve()), conversation_id="conv_unspecified",
        conversation_revision=0, actor_subject=OWNER, session_id="synthetic-session",
        model_id="synthetic-model",
    )
    return AuthorityCase(store, runner, AgentRuntime(UnusedOrchestrator(), runner), registry, context, beta)


@pytest.mark.parametrize(
    "case_name",
    [
        "missing_context", "malformed_context", "wrong_task", "wrong_actor", "wrong_actor_internal",
        "project_mirror", "root_mirror", "actor_mirror", "unknown_project", "wrong_root",
        "deleted_root", "changed_registry_root", "unsafe_registry_root", "other_owner",
    ],
)
def test_resume_rejects_untrusted_authority_before_acquisition_or_state_change(
    authority_case: AuthorityCase, monkeypatch: pytest.MonkeyPatch, case_name: str,
) -> None:
    from antigravity_k.api import dependencies

    case = authority_case
    saved = execution_context_to_task_context(case.context)
    owner: str | None = OWNER
    if case_name == "missing_context":
        saved = {}
    elif case_name == "malformed_context":
        saved["execution_context"] = "not an execution context"
    elif case_name == "wrong_task":
        saved["execution_context"] = case.context.model_copy(update={"task_id": "another-task"}).model_dump()
    elif case_name in {"wrong_actor", "wrong_actor_internal"}:
        saved = execution_context_to_task_context(case.context.model_copy(update={"actor_subject": OTHER}))
        if case_name == "wrong_actor_internal":
            owner = None
    elif case_name == "project_mirror":
        saved["project_id"] = "another-project"
    elif case_name == "root_mirror":
        saved["canonical_project_root"] = str(case.beta_root)
    elif case_name == "actor_mirror":
        saved["actor_subject"] = OTHER
    elif case_name == "unknown_project":
        saved = execution_context_to_task_context(case.context.model_copy(update={"project_id": "missing-project"}))
    elif case_name == "wrong_root":
        saved = execution_context_to_task_context(
            case.context.model_copy(update={"canonical_project_root": str(case.beta_root)})
        )
    elif case_name == "deleted_root":
        Path(case.context.canonical_project_root).rmdir()
    elif case_name in {"changed_registry_root", "unsafe_registry_root"}:
        record = case.registry.get_project(case.context.project_id)
        assert record is not None
        record.path = str(case.beta_root) if case_name == "changed_registry_root" else "/etc"
    elif case_name == "other_owner":
        owner = OTHER
    else:
        raise AssertionError(case_name)
    case.save(saved)
    before = case.store.get_task(TASK_ID)
    events_before = case.store.list_execution_events(TASK_ID)
    side_effects: list[str] = []

    def deny_acquire(*args: object, **kwargs: object) -> object:
        side_effects.append("acquire")
        raise AssertionError("Rejected authority reached project runtime acquisition")

    def deny_dispatch(*args: object, **kwargs: object) -> bool:
        side_effects.append("dispatch")
        raise AssertionError("Rejected authority reached task dispatch")

    monkeypatch.setattr(dependencies, "acquire_project_runtime", deny_acquire)
    monkeypatch.setattr(case.runner, "resume_task", deny_dispatch)
    assert case.runtime.resume_task(TASK_ID, owner_subject=owner) is False
    assert side_effects == []
    assert case.store.get_task(TASK_ID) == before
    assert case.store.list_execution_events(TASK_ID) == events_before
    assert case.runner._tasks == {}


@pytest.mark.parametrize("owner", [OWNER, None])
def test_saved_authority_selects_original_runtime_and_preserves_owner_and_ambient_context(
    authority_case: AuthorityCase, monkeypatch: pytest.MonkeyPatch, owner: str | None,
) -> None:
    from antigravity_k.api import dependencies

    case = authority_case
    case.save(execution_context_to_task_context(case.context))
    original_runtime = AgentRuntime(UnusedOrchestrator(), case.runner)
    ambient = case.context.model_copy(update={"project_id": "ambient-beta", "canonical_project_root": str(case.beta_root)})
    token = set_bound_request_execution_context(ambient)
    acquisitions: list[dict[str, object]] = []
    dispatches: list[dict[str, object]] = []

    def acquire(**kwargs: object) -> object:
        assert get_bound_request_execution_context() == case.context
        acquisitions.append(kwargs)
        return SimpleNamespace(agent_runtime=original_runtime)

    def dispatch(**kwargs: object) -> bool:
        dispatches.append(kwargs)
        return True

    monkeypatch.setattr(dependencies, "acquire_project_runtime", acquire)
    monkeypatch.setattr(case.runner, "resume_task", dispatch)
    try:
        assert case.runtime.resume_task(TASK_ID, owner_subject=owner) is True
        assert get_bound_request_execution_context() == ambient
    finally:
        reset_bound_request_execution_context(token)
    assert acquisitions == [{"project_id": case.context.project_id, "project_root": case.context.canonical_project_root}]
    assert len(dispatches) == 1
    assert dispatches[0]["owner_subject"] == OWNER
    assert dispatches[0]["orchestrator"] is original_runtime.orchestrator
    assert dispatches[0]["target_model"] == "synthetic-model"
    assert case.store.get_task(TASK_ID)["status"] == "paused", "Routing-only test must not execute or mutate a task"


def test_runtime_acquisition_error_restores_callers_context_without_transition(
    authority_case: AuthorityCase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from antigravity_k.api import dependencies

    case = authority_case
    case.save(execution_context_to_task_context(case.context))
    ambient = case.context.model_copy(update={"project_id": "ambient-beta", "canonical_project_root": str(case.beta_root)})
    token = set_bound_request_execution_context(ambient)
    before = case.store.get_task(TASK_ID)

    def unavailable(**kwargs: object) -> object:
        assert get_bound_request_execution_context() == case.context
        raise RuntimeError("synthetic runtime unavailable")

    monkeypatch.setattr(dependencies, "acquire_project_runtime", unavailable)
    try:
        with pytest.raises(RuntimeError, match="synthetic runtime unavailable"):
            case.runtime.resume_task(TASK_ID, owner_subject=OWNER)
        assert get_bound_request_execution_context() == ambient
    finally:
        reset_bound_request_execution_context(token)
    assert case.store.get_task(TASK_ID) == before


def test_internal_legacy_without_context_retains_dispatch_contract(
    authority_case: AuthorityCase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = authority_case
    case.save({})
    calls: list[dict[str, object]] = []

    def dispatch(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(case.runner, "resume_task", dispatch)
    assert case.runtime.resume_task(TASK_ID) is True
    assert len(calls) == 1 and calls[0]["owner_subject"] is None
    assert calls[0]["orchestrator"] is case.runtime.orchestrator


@pytest.mark.parametrize("failure", ["wrong_runtime_type", "different_runner"])
def test_resume_refuses_runtime_without_same_task_store_runner(
    authority_case: AuthorityCase, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    from antigravity_k.api import dependencies

    case = authority_case
    case.save(execution_context_to_task_context(case.context))
    selected = (
        SimpleNamespace(task_runner=case.runner)
        if failure == "wrong_runtime_type"
        else AgentRuntime(UnusedOrchestrator(), BackgroundTaskRunner(db_path=str(case.beta_root / "other-tasks.db")))
    )
    monkeypatch.setattr(dependencies, "acquire_project_runtime", lambda **kwargs: SimpleNamespace(agent_runtime=selected))
    before = case.store.get_task(TASK_ID)
    assert case.runtime.resume_task(TASK_ID, owner_subject=OWNER) is False
    assert case.store.get_task(TASK_ID) == before
    assert case.runner._tasks == {}
