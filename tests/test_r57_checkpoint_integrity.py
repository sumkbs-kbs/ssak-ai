"""Whole-checkpoint rejection through the runner and authenticated task HTTP API."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api import auth_policy, auth_routes, dependencies
from antigravity_k.api.routes import task_api
from antigravity_k.api.server import verify_access_token
from antigravity_k.config import config
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.task_events import ExecutionEventRecord
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskStateStore
from antigravity_k.engine.task_state_types import CheckpointRecord, TaskRecord

_TASK: Final = "r57-corrupt-checkpoint"
_CORRUPT_CONTEXTS: Final = (
    pytest.param("{", id="invalid-json"),
    pytest.param("[]", id="array"),
    pytest.param("null", id="null"),
    pytest.param("17", id="scalar"),
)


@dataclass(slots=True)  # MUTABLE_OK: the probe records calls and the runtime back-reference.
class _ProviderProbe:
    """Count stream entries and accept the real runtime's required back-reference."""

    calls: list[str] = field(default_factory=list)
    vault_engine: None = None
    max_engine: None = None
    agent_runtime: AgentRuntime | None = None

    def get_model_for_role(self, role: str) -> str:
        del role
        return "fixture-model"

    def run_stream(self, messages: Sequence[Mapping[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.calls.append("stream")
        return iter(("unexpected synthetic execution",))


@dataclass(frozen=True, slots=True)
class _Case:
    runner: BackgroundTaskRunner
    provider: _ProviderProbe
    acquisitions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Snapshot:
    task: TaskRecord
    events: tuple[ExecutionEventRecord, ...]
    checkpoint: CheckpointRecord | None
    checkpoint_count: int


def _snapshot(store: TaskStateStore) -> _Snapshot:
    task = store.get_task(_TASK)
    assert task is not None
    return _Snapshot(task, tuple(store.list_execution_events(_TASK)), store.get_last_checkpoint(_TASK),
                     store.checkpoint_counts([_TASK]).get(_TASK, 0))


@pytest.fixture(autouse=True)
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Case:
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    runner.state_store.create_task(_TASK, "synthetic checkpoint recovery", "paused", "2026-10-28T00:00:00Z",
                                   owner_subject="user")
    probe = _Case(runner, _ProviderProbe())

    def reject_acquisition(**_kwargs: str) -> None:
        probe.acquisitions.append("runtime")
        raise AssertionError("Corrupt authority must not acquire a project runtime")

    monkeypatch.setattr(dependencies, "acquire_project_runtime", reject_acquisition)
    return probe


@pytest.fixture
def authenticated_client(case: _Case, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    root = Path(case.runner.db_path).parent
    monkeypatch.setattr(config.security, "access_pin", "r57-synthetic-pin")
    monkeypatch.setattr(config.security, "pin_hash_file", str(root / "auth-hash"))
    monkeypatch.setattr(config.security, "token_secret_file", str(root / "token-secret"))
    monkeypatch.setattr(auth_routes, "_token_service", None)
    monkeypatch.setattr(auth_routes, "_pin_hash", None)
    monkeypatch.setattr(auth_policy, "_shared_auth_policy", None)
    auth_routes.init_auth_state()
    runtime = AgentRuntime(case.provider, case.runner)
    monkeypatch.setattr(task_api, "get_agent_runtime", lambda: runtime)
    app = FastAPI()
    app.middleware("http")(verify_access_token)
    app.include_router(auth_routes.router)
    app.include_router(task_api.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", json={"pin": "r57-synthetic-pin"})
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        assert client.get(f"/api/tasks/{_TASK}/status").status_code == 200
        yield client


@pytest.mark.parametrize("raw", _CORRUPT_CONTEXTS)
def test_direct_runner_rejects_whole_checkpoint_corruption_without_mutation(case: _Case, raw: str) -> None:
    # Given: an eligible task has corrupt whole context JSON in synthetic storage.
    store = case.runner.state_store
    store.save_checkpoint(_TASK, 4, raw, "previous synthetic output")
    before = _snapshot(store)
    rejection_error = ""
    accepted: bool | None = None

    # When: the direct runner receives an explicit resume request.
    try:
        accepted = case.runner.resume_task(_TASK, orchestrator=case.provider,
                                           target_model="fixture-model", owner_subject="user")
    except json.JSONDecodeError as error:
        rejection_error = str(error)
    finally:
        case.runner.wait_task(_TASK, timeout=2)

    # Then: refusal is explicit, with no stream, runtime, state, event or checkpoint effect.
    assert case.provider.calls == [] and case.acquisitions == []
    assert _snapshot(store) == before
    assert accepted is False, rejection_error


@pytest.mark.parametrize("raw", _CORRUPT_CONTEXTS)
def test_authenticated_http_rejects_the_same_corrupt_checkpoint_without_mutation(
    case: _Case, authenticated_client: TestClient, raw: str,
) -> None:
    # Given: the real authenticated task route sees the same corrupt owner checkpoint.
    store = case.runner.state_store
    store.save_checkpoint(_TASK, 4, raw, "previous synthetic output")
    before = _snapshot(store)

    # When: its verified owner requests resume through the production HTTP handler.
    response = authenticated_client.post(f"/api/tasks/{_TASK}/resume")
    case.runner.wait_task(_TASK, timeout=2)

    # Then: the authority guard rejects before acquisition or runner mutation; no 500 occurs.
    assert response.status_code == 404, response.text
    assert case.provider.calls == [] and case.acquisitions == []
    assert _snapshot(store) == before
