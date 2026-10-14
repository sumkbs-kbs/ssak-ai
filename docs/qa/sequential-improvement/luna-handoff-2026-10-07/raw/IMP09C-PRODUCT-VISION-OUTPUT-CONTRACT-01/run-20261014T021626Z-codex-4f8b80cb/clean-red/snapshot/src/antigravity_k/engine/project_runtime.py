"""Project-scoped runtime lifecycle (WS-03).

Orchestrator, memory, session, and derived caches are keyed by ``project_id``.
Switching projects must never field-patch an existing runtime: acquire a
distinct handle (create or reuse) for the target id. Eviction/shutdown stop
watchers and close DB/vector handles belonging to that project only.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from antigravity_k.engine.durable_memory import DurableMemoryProvider
from antigravity_k.engine.memory_provider import (
    BuiltinMemoryProvider,
    EpisodicMemoryProvider,
    GlobalMemoryProvider,
    MemoryManager,
    WorkingMemoryBuffer,
)
from antigravity_k.engine.project_memory import ProjectMemoryProvider
from antigravity_k.engine.project_memory_paths import project_memory_dir
from antigravity_k.engine.session_manager import SessionManager

logger = logging.getLogger("antigravity_k.engine.project_runtime")

DEFAULT_MAX_PROJECT_RUNTIMES = 8


class _OrchestratorShutdownPort(Protocol):
    def shutdown(self) -> None: ...


@dataclass
class ProjectRuntime:
    """Immutable identity + owned services for one project."""

    project_id: str
    project_root: str
    memory_manager: MemoryManager
    session_manager: SessionManager
    orchestrator: Any
    agent_runtime: Any | None = None
    slash_registry: Any | None = None
    scheduled_job_service: Any | None = None
    vault_engine: Any | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_used_at: float = field(default_factory=time.monotonic)
    _shutdown: bool = False

    def touch(self) -> None:
        self.last_used_at = time.monotonic()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        orch = self.orchestrator
        shutdown_fn = getattr(orch, "shutdown", None)
        if callable(shutdown_fn):
            try:
                shutdown_fn()
            except Exception:
                logger.exception(
                    "Orchestrator shutdown failed for project_id=%s",
                    self.project_id,
                )
        # Drop strong refs so GC can reclaim; callers must not reuse after shutdown.
        self.agent_runtime = None


def build_project_memory_manager(
    project_root: str | Path,
    session_manager: SessionManager,
    *,
    durable_hooks: dict[str, tuple[Callable[..., Any], ...]] | None = None,
) -> MemoryManager:
    """Create a MemoryManager bound exclusively to ``project_root``.

    Never rebind an existing manager to another root — callers that need
    another project must build a new manager (WS-03).
    """
    root = Path(project_root).resolve()
    manager = MemoryManager(project_root=str(root))
    manager.add_provider(BuiltinMemoryProvider(session_manager))
    episodic_dir = project_memory_dir(root) / "episodic"
    manager.add_provider(EpisodicMemoryProvider(max_episodes=200, persist_dir=str(episodic_dir)))
    manager.add_provider(WorkingMemoryBuffer(max_turns=20))
    manager.add_provider(GlobalMemoryProvider())
    manager.add_provider(ProjectMemoryProvider(root))
    if durable_hooks:
        for name, hooks in durable_hooks.items():
            clear_fn = hooks[0]
            export_fn = hooks[1]
            redact_fn = hooks[2]
            retain_fn = hooks[3] if len(hooks) > 3 else None
            if retain_fn is not None:
                manager.add_provider(
                    DurableMemoryProvider(name, clear_fn, export_fn, redact_fn, retain_fn),
                )
            else:
                manager.add_provider(DurableMemoryProvider(name, clear_fn, export_fn, redact_fn))
    return manager


class ProjectRuntimeRegistry:
    """Thread-safe LRU registry of project-scoped runtimes."""

    def __init__(self, *, max_entries: int = DEFAULT_MAX_PROJECT_RUNTIMES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._lock = threading.RLock()
        self._runtimes: dict[str, ProjectRuntime] = {}

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def active_project_ids(self) -> list[str]:
        with self._lock:
            return list(self._runtimes.keys())

    def get(self, project_id: str) -> ProjectRuntime | None:
        pid = (project_id or "").strip()
        if not pid:
            return None
        with self._lock:
            runtime = self._runtimes.get(pid)
            if runtime is not None and not runtime._shutdown:
                runtime.touch()
                return runtime
            return None

    def get_or_create(
        self,
        project_id: str,
        project_root: str,
        *,
        factory: Callable[[str, str], ProjectRuntime],
    ) -> ProjectRuntime:
        """Return existing runtime or create via ``factory(project_id, project_root)``.

        Factory failures do not mutate other project entries. On success the
        new runtime is inserted; LRU eviction may shut down a different
        project's runtime when over capacity.
        """
        pid = (project_id or "").strip()
        if not pid:
            raise ValueError("project_id is required")
        root = str(Path(project_root).resolve())

        with self._lock:
            existing = self._runtimes.get(pid)
            if existing is not None and not existing._shutdown:
                if os.path.realpath(existing.project_root) != os.path.realpath(root):
                    # Identity collision: never field-patch; replace with a fresh runtime.
                    logger.warning(
                        "ProjectRuntime root changed for project_id=%s (%s -> %s); replacing",
                        pid,
                        existing.project_root,
                        root,
                    )
                    existing.shutdown()
                    del self._runtimes[pid]
                else:
                    existing.touch()
                    return existing

        # Create outside the lock so a slow/failing init cannot block other projects.
        try:
            created = factory(pid, root)
        except Exception:
            logger.exception("Failed to create ProjectRuntime for project_id=%s", pid)
            raise

        if created.project_id != pid:
            raise RuntimeError("factory returned mismatched project_id")
        if os.path.realpath(created.project_root) != os.path.realpath(root):
            raise RuntimeError("factory returned mismatched project_root")

        with self._lock:
            # Another thread may have won the race — prefer the first inserted.
            raced = self._runtimes.get(pid)
            if raced is not None and not raced._shutdown:
                if os.path.realpath(raced.project_root) == os.path.realpath(root):
                    # Discard the duplicate we just built.
                    created.shutdown()
                    raced.touch()
                    return raced
                raced.shutdown()
                del self._runtimes[pid]

            self._runtimes[pid] = created
            created.touch()
            self._evict_overflow_locked(keep_project_id=pid)
            return created

    def evict(self, project_id: str) -> bool:
        pid = (project_id or "").strip()
        if not pid:
            return False
        with self._lock:
            runtime = self._runtimes.pop(pid, None)
        if runtime is None:
            return False
        runtime.shutdown()
        return True

    def shutdown_all(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.shutdown()

    def reset(self) -> None:
        """Test helper: shutdown everything and clear the map."""
        self.shutdown_all()

    def _evict_overflow_locked(self, *, keep_project_id: str) -> None:
        while len(self._runtimes) > self._max_entries:
            candidates = [(pid, rt) for pid, rt in self._runtimes.items() if pid != keep_project_id]
            if not candidates:
                break
            victim_id, victim = min(candidates, key=lambda item: item[1].last_used_at)
            del self._runtimes[victim_id]
            logger.info(
                "Evicting ProjectRuntime project_id=%s (LRU, max_entries=%s)",
                victim_id,
                self._max_entries,
            )
            # Shutdown outside holding structure; still under lock to serialize teardown.
            victim.shutdown()


_global_registry: ProjectRuntimeRegistry | None = None
_global_lock = threading.Lock()


def get_project_runtime_registry() -> ProjectRuntimeRegistry:
    global _global_registry
    with _global_lock:
        if _global_registry is None:
            raw = os.environ.get("AGK_MAX_PROJECT_RUNTIMES", "").strip()
            max_entries = DEFAULT_MAX_PROJECT_RUNTIMES
            if raw:
                try:
                    max_entries = max(1, int(raw))
                except ValueError:
                    logger.warning("Invalid AGK_MAX_PROJECT_RUNTIMES=%r; using default", raw)
            _global_registry = ProjectRuntimeRegistry(max_entries=max_entries)
        return _global_registry


def reset_project_runtime_registry() -> None:
    """Shutdown and drop the process-global registry (tests / process teardown)."""
    global _global_registry
    with _global_lock:
        if _global_registry is not None:
            _global_registry.shutdown_all()
            _global_registry = None


__all__ = [
    "DEFAULT_MAX_PROJECT_RUNTIMES",
    "ProjectRuntime",
    "ProjectRuntimeRegistry",
    "build_project_memory_manager",
    "get_project_runtime_registry",
    "reset_project_runtime_registry",
]
