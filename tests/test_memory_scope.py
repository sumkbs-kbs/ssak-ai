from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Protocol, cast
from unittest.mock import MagicMock

import pytest
from fastapi import Request as FastAPIRequest
from starlette.datastructures import State

from antigravity_k.engine.memory_provider import (
    BuiltinMemoryProvider,
    EpisodicMemoryProvider,
    GlobalMemoryProvider,
    MemoryManager,
    WorkingMemoryBuffer,
)
from antigravity_k.engine.session_manager import SessionManager


class _MockCall(Protocol):
    def __call__(self, event_type: str, payload: Mapping[str, object]) -> object: ...
    def assert_called_once_with(self, *args: object, **kwargs: object) -> object: ...


class _AuditLogger(Protocol):
    log_event: _MockCall


def _memory_manager(tmp_path: Path) -> tuple[MemoryManager, SessionManager, GlobalMemoryProvider]:
    session_manager = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = session_manager.start_session(project_path=str(tmp_path / "project"), resume=False)
    session_manager.add_turn([{"role": "user", "content": "session secret"}])
    session_manager.set_memory("working-secret", "working value")

    global_provider = GlobalMemoryProvider(memory_dir=str(tmp_path / "global"))
    global_provider.add_preference("global preference")

    episodic = EpisodicMemoryProvider(persist_dir=str(tmp_path / "episodic"))
    episodic.sync_turn("episodic secret", "private answer")

    working = WorkingMemoryBuffer(max_turns=10)
    working.sync_turn("working turn", "working response")

    manager = MemoryManager()
    manager.add_provider(BuiltinMemoryProvider(session_manager))
    manager.add_provider(episodic)
    manager.add_provider(working)
    manager.add_provider(global_provider)
    return manager, session_manager, global_provider


def test_memory_manager_clears_only_requested_scope(tmp_path: Path):
    manager, session_manager, global_provider = _memory_manager(tmp_path)

    global_report = manager.clear("global")

    assert global_report["global"] == 1
    assert global_provider.get_all() == {"preferences": [], "patterns": [], "facts": []}
    assert session_manager.get_messages()
    assert session_manager.get_all_memory()

    session_report = manager.clear("session")

    assert session_report["builtin"] == 1
    assert session_manager.get_messages() == []
    assert session_manager.get_all_memory()

    working_report = manager.clear("working")

    assert working_report["builtin"] == 1
    assert session_manager.get_all_memory() == {}


def test_memory_manager_clear_all_persists_across_restart(tmp_path: Path):
    manager, session_manager, global_provider = _memory_manager(tmp_path)

    report = manager.clear("all")

    assert report["builtin"] == 2
    assert report["global"] == 1
    assert session_manager.get_messages() == []
    assert session_manager.get_all_memory() == {}
    assert global_provider.get_all() == {"preferences": [], "patterns": [], "facts": []}

    restored = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = restored.start_session(project_path=str(tmp_path / "project"), resume=True)
    assert restored.get_messages() == []
    assert restored.get_all_memory() == {}


def test_memory_manager_clear_all_removes_persisted_sessions(tmp_path: Path):
    session_manager = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = session_manager.start_session(project_path=str(tmp_path / "project-a"), resume=False)
    session_manager.add_turn([{"role": "user", "content": "old session"}])
    _ = session_manager.start_session(project_path=str(tmp_path / "project-b"), resume=False)
    _ = session_manager.set_memory("old-key", "old value")

    manager = MemoryManager()
    manager.add_provider(BuiltinMemoryProvider(session_manager))

    _ = manager.clear("all")

    assert list((tmp_path / "sessions").glob("*.json")) == []
    assert session_manager.get_messages() == []
    assert session_manager.get_all_memory() == {}


def test_session_manager_clear_all_without_active_session_removes_files(tmp_path: Path):
    base_dir = tmp_path / "sessions"
    writer = SessionManager(base_dir=str(base_dir))
    _ = writer.start_session(project_path=str(tmp_path / "project"), resume=False)
    writer.add_turn([{"role": "user", "content": "persisted secret"}])

    fresh_manager = SessionManager(base_dir=str(base_dir))

    _ = fresh_manager.clear_memory("all")

    assert list(base_dir.glob("*.json")) == []


def test_memory_manager_rejects_unknown_scope(tmp_path: Path):
    manager, _, _ = _memory_manager(tmp_path)

    with pytest.raises(ValueError, match="scope"):
        _ = manager.clear("user")


def test_session_manager_project_clear_is_a_no_op(tmp_path: Path) -> None:
    # Given: session data exists beside project-owned memory.
    manager = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = manager.start_session(project_path=str(tmp_path / "project"), resume=False)
    manager.add_turn([{"role": "user", "content": "keep this turn"}])
    original_messages = manager.get_messages()

    # When: the session store receives a project-only clear request.
    deleted = manager.clear_memory("project")

    # Then: this provider reports no deletion and preserves its own scope.
    assert deleted == 0
    assert manager.get_messages() == original_messages


def test_session_manager_project_export_is_empty(tmp_path: Path) -> None:
    # Given: session data exists beside project-owned memory.
    manager = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = manager.start_session(project_path=str(tmp_path / "project"), resume=False)
    manager.add_turn([{"role": "user", "content": "session-only turn"}])

    # When: the session store receives a project-only export request.
    exported = manager.export_memory("project")

    # Then: no session records are exposed under the project scope.
    assert exported == []


def test_session_manager_project_redaction_is_a_no_op(tmp_path: Path) -> None:
    # Given: working memory exists beside project-owned memory.
    manager = SessionManager(base_dir=str(tmp_path / "sessions"))
    _ = manager.start_session(project_path=str(tmp_path / "project"), resume=False)
    _ = manager.set_memory("credential", "TOKEN=session-only-123456")
    original_memory = manager.get_all_memory()

    # When: the session store receives a project-only redaction request.
    changed = manager.redact_memory("project")

    # Then: this provider reports no change and preserves its own scope.
    assert changed == 0
    assert manager.get_all_memory() == original_memory


def test_engine_context_reuses_injected_memory_manager(tmp_path: Path):
    from antigravity_k.engine.engine_context import EngineContext

    manager = MemoryManager()

    context = EngineContext(
        model_manager=MagicMock(),
        project_root=str(tmp_path),
        memory_manager=manager,
    )

    assert context.memory_manager is manager


def test_memory_routes_use_the_shared_dependency_manager(monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import system_api

    manager = MemoryManager()
    monkeypatch.setattr(system_api, "_get_shared_memory_manager", lambda: manager)

    get_memory_manager = cast(Callable[[], MemoryManager], getattr(system_api, "_get_memory_manager"))
    assert get_memory_manager() is manager


def test_dependency_orchestrator_receives_shared_memory_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """WS-03: orchestrator is built per project — the project runtime factory must
    receive the project's shared memory_manager (not a per-caller singleton)."""
    from antigravity_k.api import dependencies

    manager = MemoryManager()
    captured: dict[str, object] = {}

    class Orchestrator:
        def __init__(self, **kwargs: object):
            captured.update(kwargs)
            # Slash registry build touches these — stub minimal surface.
            self.tool_registry = None
            self.context_shaper = None
            self.ctx = SimpleNamespace(skill_loader=None, slash_commands=SimpleNamespace(bind_runtime=lambda _rt: None))

    monkeypatch.setattr(dependencies, "OrchestratorAgent", Orchestrator)
    monkeypatch.setattr(dependencies, "get_model_manager", lambda: MagicMock())
    monkeypatch.setattr(dependencies, "_build_project_vault", lambda _root: None)
    monkeypatch.setattr(
        dependencies,
        "build_project_memory_manager",
        lambda _root, _session, **_kw: manager,
    )
    monkeypatch.setattr(dependencies, "_attach_project_rag_indexer", lambda _o, _root, *, embedding_binding=None: None)
    monkeypatch.setattr(dependencies, "get_task_runner", lambda: MagicMock(), raising=False)
    monkeypatch.setattr(dependencies, "_build_project_job_service", lambda _rt, _root: None, raising=False)
    dependencies.reset_runtime_dependencies()

    try:
        result = dependencies.acquire_project_runtime(
            project_root=str(tmp_path),
        ).orchestrator
    finally:
        dependencies.reset_runtime_dependencies()

    assert isinstance(result, Orchestrator)
    assert captured["memory_manager"] is manager


@pytest.mark.asyncio
async def test_memory_purge_route_returns_audited_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manager, _, _ = _memory_manager(tmp_path)
    audit_logger = cast(_AuditLogger, MagicMock())

    from antigravity_k.api.routes import system_api

    monkeypatch.setattr(system_api, "_get_memory_manager", lambda: manager)
    monkeypatch.setattr(system_api, "get_audit_logger", lambda: audit_logger)

    class RequestStub:
        async def json(self) -> dict[str, str]:
            return {"scope": "global"}

    result = await system_api.purge_memory(cast(FastAPIRequest[State], cast(object, RequestStub())))

    assert result == {
        "ok": True,
        "scope": "global",
        "deleted": {"builtin": 0, "episodic": 0, "working_memory": 0, "global": 1},
    }
    _ = audit_logger.log_event.assert_called_once_with(
        "memory_purge",
        {"scope": "global", "deleted": result["deleted"]},
    )
