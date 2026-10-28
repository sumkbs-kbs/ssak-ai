"""Request identity is authoritative and survives direct-task checkpoints."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import (
    reset_bound_request_execution_context,
    resolve_project_execution_context,
    set_bound_request_execution_context,
)
from antigravity_k.engine.direct_task_execution import DirectTaskExecution
from antigravity_k.engine.project_registry import ProjectRegistry
from antigravity_k.engine.task_state_store import TaskStateStore


class TextOrchestrator:
    def run_stream(self, *args: object, **kwargs: object) -> Iterator[str]:
        yield "synthetic answer"


def context(root: Path, actor: str) -> RequestExecutionContext:
    return RequestExecutionContext(
        request_id="request-synthetic", project_id="project-alpha",
        canonical_project_root=str(root), conversation_id="conv_unspecified",
        conversation_revision=0, actor_subject=actor, session_id="session-synthetic",
        model_id="synthetic-model",
    )


@pytest.mark.parametrize("actor", ["synthetic-alpha", "synthetic-beta", "loopback", "anonymous"])
def test_direct_task_stores_bound_actor_and_project_checkpoint(tmp_path: Path, actor: str) -> None:
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    store.initialize()
    execution = DirectTaskExecution(TextOrchestrator(), SimpleNamespace(state_store=store))
    token = set_bound_request_execution_context(context(tmp_path, actor))
    try:
        tracked = execution.start_stream([{"role": "user", "content": "synthetic prompt"}], "synthetic-model", 1, None)
    finally:
        reset_bound_request_execution_context(token)
    assert tracked.task_id is not None
    task = store.get_task(tracked.task_id, owner_subject=actor)
    assert task is not None, "New task must belong to the bound request actor"
    assert store.get_task(tracked.task_id, owner_subject="synthetic-outsider") is None
    checkpoint = store.get_last_checkpoint(tracked.task_id)
    assert checkpoint is not None
    saved = json.loads(checkpoint["context_json"])
    assert saved["project_id"] == "project-alpha"
    assert saved["execution_context"]["canonical_project_root"] == str(tmp_path)
    assert saved["execution_context"]["actor_subject"] == actor
    assert saved["execution_context"]["task_id"] == tracked.task_id
    assert "".join(tracked.chunks) == "synthetic answer"


def test_internal_direct_task_without_request_remains_loopback(tmp_path: Path) -> None:
    store = TaskStateStore(str(tmp_path / "tasks.db"))
    store.initialize()
    execution = DirectTaskExecution(TextOrchestrator(), SimpleNamespace(state_store=store))
    tracked = execution.start_stream([{"role": "user", "content": "synthetic prompt"}], "synthetic-model", 1, None)
    assert store.get_task(tracked.task_id, owner_subject="loopback") is not None
    assert "".join(tracked.chunks) == "synthetic answer"


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("actor", ["synthetic-alpha", "anonymous"])
def test_client_cannot_replace_server_actor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nested: bool, actor: str) -> None:
    from antigravity_k.config import config

    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)
    registry = ProjectRegistry(storage_path=tmp_path / "projects.json")
    root = tmp_path / "alpha"
    root.mkdir()
    project = registry.add_project("alpha", str(root))
    payload = {"project_id": project.id, "actor_subject": "synthetic-victim"}
    if nested:
        payload["execution_context"] = {"project_id": project.id, "actor_subject": "synthetic-victim"}
    resolved = resolve_project_execution_context(payload=payload, actor_subject=actor, registry=registry, bind=False)
    assert resolved.actor_subject == actor, "Client identity must not override verified request identity"
