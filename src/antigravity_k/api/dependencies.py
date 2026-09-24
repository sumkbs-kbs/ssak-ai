"""FastAPI dependency injection providers (singletons and getters)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from pydantic import TypeAdapter, ValidationError

from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.benchmark_harness import BenchmarkHarness
from antigravity_k.engine.context_shaper import ContextShaper
from antigravity_k.engine.embeddings import EmbeddingEngine
from antigravity_k.engine.memory_provider import MemoryManager
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.orchestrator import OrchestratorAgent
from antigravity_k.engine.project_runtime import (
    ProjectRuntime,
    build_project_memory_manager,
    get_project_runtime_registry,
    reset_project_runtime_registry,
)
from antigravity_k.engine.protocol_translator import ProtocolTranslator
from antigravity_k.engine.scheduled_job_service import ScheduledJobService
from antigravity_k.engine.session_manager import SessionManager
from antigravity_k.engine.skill_loader import SkillLoader
from antigravity_k.engine.vault import VaultEngine
from antigravity_k.engine.voice_service import VoiceService
from antigravity_k.tools.tool_registry import ToolRegistry

logger = logging.getLogger("antigravity_k.api.dependencies")

if TYPE_CHECKING:
    from antigravity_k.engine.mode_manager import ModeManager


type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]


@runtime_checkable
class _SlashRegistryLike(Protocol):
    def bind_runtime(self, runtime: AgentRuntime) -> None: ...


@runtime_checkable
class _RuntimeContextLike(Protocol):
    slash_commands: _SlashRegistryLike


_JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)
_DURABLE_EXPORT_ADAPTER: Final[TypeAdapter[list[dict[str, JsonValue]]]] = TypeAdapter(list[dict[str, JsonValue]])


def _json_object(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _json_text(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""


def _widen_graph_record(record: Mapping[str, object]) -> dict[str, object]:
    widened: dict[str, object] = {}
    for key, value in record.items():
        widened[key] = value
    return widened


# Global instances (process-wide shared infrastructure)
model_manager: ModelManager | None = None
protocol_translator: ProtocolTranslator | None = None
vault_engine: VaultEngine | None = None

_tool_registry: ToolRegistry | None = None
_skill_loader: SkillLoader | None = None
_context_shaper: ContextShaper | None = None
# Legacy fallbacks when no project identity is available (CLI bootstrap).
_session_manager: SessionManager | None = None
_scheduled_job_service: ScheduledJobService | None = None
_voice_service: VoiceService | None = None
_benchmark_harness: BenchmarkHarness | None = None
_mode_manager: ModeManager | None = None
# WS-03: orchestrator / memory / agent_runtime are project-keyed via ProjectRuntimeRegistry.


def get_mode_manager() -> ModeManager:
    """ModeManager 싱글톤을 반환합니다.

    Phase 1 D7: Dashboard WebSocket이 실제 실행 모드를 조회하기 위해 사용.
    EngineContext.mode_manager와 동일한 인스턴스를 공유합니다.
    """
    global _mode_manager
    if _mode_manager is None:
        from antigravity_k.engine.mode_manager import ModeManager

        _mode_manager = ModeManager()
        logger.info("Lazy initializing ModeManager (singleton)...")
    return _mode_manager


def _legacy_session_manager() -> SessionManager:
    """CLI/bootstrap fallback when no project runtime identity is resolvable."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def _get_session_manager(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> SessionManager:
    """Return the SessionManager for the resolved project (WS-03 F1/F2).

    Always resolves through ``ProjectRuntimeRegistry`` when a project identity
    is available (bound request context, explicit id/root, or active registry
    project). Falls back to a process-local legacy manager only if acquisition
    fails during early bootstrap.
    """
    try:
        return acquire_project_runtime(project_id=project_id, project_root=project_root).session_manager
    except Exception:
        logger.debug("Falling back to legacy SessionManager", exc_info=True)
        return _legacy_session_manager()


get_session_manager = _get_session_manager


def _durable_memory_hooks(project_root: str) -> dict[str, tuple[Callable[..., object], ...]]:
    """Build clear/export/redact hooks scoped to ``project_root`` (WS-03 F5)."""
    root = str(Path(project_root).resolve())
    return {
        "memory_service": (
            lambda: _clear_memory_service(project_root=root),
            lambda: _export_memory_service(project_root=root),
            lambda: _redact_memory_service(project_root=root),
            lambda max_age_days: _retain_memory_service(max_age_days, project_root=root),
        ),
        "wiki": (
            lambda: _clear_wiki(project_root=root),
            lambda: _export_wiki(project_root=root),
            lambda: _redact_wiki(project_root=root),
            lambda max_age_days: _retain_wiki(max_age_days, project_root=root),
        ),
        "gbrain": (
            lambda: _clear_gbrain(project_root=root),
            lambda: _export_gbrain(project_root=root),
            lambda: _redact_gbrain(project_root=root),
        ),
        "project_vector": (
            lambda: _clear_project_vector(project_root=root),
            lambda: _export_project_vector(project_root=root),
            lambda: _redact_project_vector(project_root=root),
        ),
        "search_cache": (
            lambda: _clear_search_cache(project_root=root),
            lambda: _export_search_cache(project_root=root),
            lambda: _redact_search_cache(project_root=root),
            lambda max_age_days: _retain_search_cache(max_age_days, project_root=root),
        ),
    }


def _resolve_project_runtime_identity(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> tuple[str, str]:
    """Resolve ``(project_id, canonical_root)`` for runtime cache keys.

    Preference order:
    1. Bound request ``RequestExecutionContext`` (ARC-01 / WS-01)
    2. Explicit ``project_id`` via project registry
    3. Explicit ``project_root`` matched to a registered project path
    4. Process cwd / active registry project (CLI bootstrap only)
    """
    from antigravity_k.api.project_binding import get_bound_request_execution_context
    from antigravity_k.engine.project_registry import get_project_registry

    bound = get_bound_request_execution_context()
    if bound is not None:
        return bound.project_id, bound.canonical_project_root

    explicit_id = (project_id or "").strip()
    if explicit_id:
        from antigravity_k.engine.request_execution_context import resolve_canonical_project_root

        _record, root = resolve_canonical_project_root(explicit_id)
        return explicit_id, root

    registry = get_project_registry()
    if project_root:
        root = str(Path(project_root).resolve())
        root_real = os.path.realpath(root)
        for item in registry.list_projects():
            path = str(item.get("path") or "")
            if path and os.path.realpath(path) == root_real:
                return str(item["id"]), root
        return f"path:{root_real}", root

    active = registry.get_active_project()
    return active.id, os.path.abspath(active.path)


def _build_project_vault(project_root: str) -> VaultEngine | None:
    """Create a vault rooted under the project (WS-03 F6 isolation)."""
    from antigravity_k.engine.project_memory_paths import project_vault_dir

    vault_path = str(project_vault_dir(project_root))
    try:
        return VaultEngine(vault_path=vault_path, sync_rag=True)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Project VaultEngine init failed (sync_rag=True): %s", e)
        try:
            return VaultEngine(vault_path=vault_path, sync_rag=False)
        except OSError:
            logger.exception("Project VaultEngine completely failed for %s", project_root)
            return None


def _attach_project_rag_indexer(orchestrator: OrchestratorAgent, project_root: str) -> None:
    """Wire a real per-project RAGIndexer with vectors under the project root."""
    from antigravity_k.engine.project_memory_paths import project_rag_vector_dir
    from antigravity_k.engine.rag_indexer import RAGIndexer
    from antigravity_k.engine.vector_store import VectorStore

    rag_dir = project_rag_vector_dir(project_root)
    try:
        vector_store: object | None = VectorStore(str(rag_dir), collection_name="project_code")
    except Exception:
        logger.exception("Project RAG VectorStore init failed for %s", project_root)
        vector_store = None
    setattr(orchestrator, "_rag_indexer", RAGIndexer(project_root=project_root, vector_store=vector_store))


def _build_project_slash_registry(
    *,
    session_manager: SessionManager,
    agent_runtime: AgentRuntime,
    orchestrator: OrchestratorAgent,
) -> object:
    from antigravity_k.engine.slash_commands import SlashCommandRegistry

    registry = SlashCommandRegistry(
        tool_registry=orchestrator.tool_registry,
        session_manager=session_manager,
        context_shaper=orchestrator.context_shaper,
        model_manager=get_model_manager(),
        skill_loader=orchestrator.ctx.skill_loader,
        agent_runtime=agent_runtime,
    )
    context_value = vars(orchestrator).get("ctx")
    if isinstance(context_value, _RuntimeContextLike):
        context_value.slash_commands.bind_runtime(agent_runtime)
        # Prefer the project-scoped registry on the live context when present.
        try:
            setattr(context_value, "slash_commands", registry)
        except Exception:
            logger.debug("Could not replace orchestrator slash_commands", exc_info=True)
    return registry


def _build_project_job_service(agent_runtime: AgentRuntime, project_root: str) -> ScheduledJobService:
    from antigravity_k.engine.project_memory_paths import project_memory_dir
    from antigravity_k.engine.scheduled_job_store import ScheduledJobStore

    db_path = str(project_memory_dir(project_root) / "scheduled_jobs.db")
    return ScheduledJobService(
        ScheduledJobStore(db_path),
        agent_runtime.submit_task,
        agent_runtime.get_task_status,
    )


def _build_project_runtime(project_id: str, project_root: str) -> ProjectRuntime:
    """Factory: allocate a fresh orchestrator/memory/session for one project."""
    from antigravity_k.engine.project_memory_paths import project_sessions_dir
    from antigravity_k.engine.task_runner import get_task_runner

    session_manager = SessionManager(base_dir=str(project_sessions_dir(project_root)))
    memory_manager = build_project_memory_manager(
        project_root,
        session_manager,
        durable_hooks=_durable_memory_hooks(project_root),
    )
    vault_engine = _build_project_vault(project_root)
    orchestrator = OrchestratorAgent(
        model_manager=get_model_manager(),
        vault_engine=vault_engine,
        project_root=project_root,
        session_manager=session_manager,
        memory_manager=memory_manager,
        project_id=project_id,
    )
    _attach_project_rag_indexer(orchestrator, project_root)
    task_runner = get_task_runner()
    benchmark_harness = get_benchmark_harness()
    agent_runtime = AgentRuntime(
        orchestrator,
        task_runner,
        task_outcome_recorder=benchmark_harness.record_task_outcome,
    )
    _attach_cognitive_surface(agent_runtime, get_model_manager())
    _ = benchmark_harness.bind_task_runner(task_runner)
    slash_registry = _build_project_slash_registry(
        session_manager=session_manager,
        agent_runtime=agent_runtime,
        orchestrator=orchestrator,
    )
    job_service = _build_project_job_service(agent_runtime, project_root)

    return ProjectRuntime(
        project_id=project_id,
        project_root=project_root,
        memory_manager=memory_manager,
        session_manager=session_manager,
        orchestrator=orchestrator,
        agent_runtime=agent_runtime,
        slash_registry=slash_registry,
        scheduled_job_service=job_service,
        vault_engine=vault_engine,
    )


def acquire_project_runtime(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> ProjectRuntime:
    """Acquire (create or reuse) the project-scoped runtime handle."""
    pid, root = _resolve_project_runtime_identity(project_id=project_id, project_root=project_root)
    registry = get_project_runtime_registry()
    return registry.get_or_create(pid, root, factory=_build_project_runtime)


def evict_project_runtime(project_id: str) -> bool:
    """Shutdown and drop one project runtime (watchers/DB/process handles)."""
    return get_project_runtime_registry().evict(project_id)


def reset_runtime_dependencies() -> None:
    """Test/process helper: clear project runtime caches."""
    reset_project_runtime_registry()


def get_memory_manager(
    project_root: str | None = None,
    *,
    project_id: str | None = None,
) -> MemoryManager:
    """Return the MemoryManager for the resolved project (WS-03).

    Never rebinds a shared singleton across projects. Each project_id owns a
    distinct manager whose persistence directory is under that project's root.
    """
    return acquire_project_runtime(project_id=project_id, project_root=project_root).memory_manager


def _memory_service_db(project_root: str) -> str:
    from antigravity_k.engine.project_memory_paths import project_memory_dir

    return str(project_memory_dir(project_root) / "durable_memory.db")


def _wiki_for_project(project_root: str):
    from antigravity_k.engine.project_memory_paths import project_wiki_dir
    from antigravity_k.knowledge.wiki import LLMWiki

    wiki_dir = project_wiki_dir(project_root)
    return LLMWiki(db_path=wiki_dir / "wiki.db")


def _gbrain_for_project(project_root: str):
    from antigravity_k.engine.gbrain import GBrain
    from antigravity_k.engine.project_memory_paths import project_gbrain_dir

    return GBrain(storage_dir=str(project_gbrain_dir(project_root)))


def _project_vector_targets(project_root: str) -> list[tuple[Path, str]]:
    """Return (persist_dir, collection_name) pairs under the project root."""
    from antigravity_k.engine.project_memory_paths import project_rag_vector_dir, project_vault_dir

    root = Path(project_root).resolve()
    targets: list[tuple[Path, str]] = []
    vault_chroma = project_vault_dir(root) / ".chroma"
    targets.append((vault_chroma, "vault_notes"))
    targets.append((project_rag_vector_dir(root), "project_code"))
    return targets


def _search_cache_dir(project_root: str | None) -> Path:
    if project_root:
        from antigravity_k.engine.project_memory_paths import project_search_cache_dir

        return project_search_cache_dir(project_root)
    from antigravity_k.tools.web_search_cache import CACHE_DIR

    return CACHE_DIR


def _clear_memory_service(*, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.memory_service import MemoryService

    if not project_root:
        return MemoryService().clear_all()
    return MemoryService(db_path=_memory_service_db(project_root)).clear_all()


def _clear_wiki(*, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.wiki import LLMWiki

    if not project_root:
        return LLMWiki().clear_all()
    return _wiki_for_project(project_root).clear_all()


def _clear_gbrain(*, project_root: str | None = None) -> int:
    from antigravity_k.engine.gbrain import global_gbrain

    if not project_root:
        return global_gbrain.clear_all()
    return _gbrain_for_project(project_root).clear_all()


def _clear_project_vector(*, project_root: str | None = None) -> int:
    from antigravity_k.engine.vector_store import VectorStore

    if not project_root:
        vector_path = Path.cwd() / ".antigravity" / "vault_data"
        if not vector_path.exists():
            return 0
        vector_store = VectorStore(str(vector_path), collection_name="agent_knowledge")
        try:
            return vector_store.clear()
        finally:
            vector_store.close()

    deleted = 0
    for vector_path, collection_name in _project_vector_targets(project_root):
        if not vector_path.exists():
            continue
        vector_store = VectorStore(str(vector_path), collection_name=collection_name)
        try:
            deleted += vector_store.clear()
        finally:
            vector_store.close()
    return deleted


def _clear_search_cache(*, project_root: str | None = None) -> int:
    cache_dir = _search_cache_dir(project_root)
    if not cache_dir.exists():
        return 0

    deleted = 0
    for cache_file in cache_dir.glob("*.json"):
        cache_file.unlink()
        deleted += 1
    return deleted


def _export_memory_service(*, project_root: str | None = None) -> list[dict[str, JsonValue]]:
    from antigravity_k.knowledge.memory_service import MemoryService

    service = MemoryService(db_path=_memory_service_db(project_root)) if project_root else MemoryService()
    return _DURABLE_EXPORT_ADAPTER.validate_python(service.export_all())


def _redact_memory_service(*, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.memory_service import MemoryService

    service = MemoryService(db_path=_memory_service_db(project_root)) if project_root else MemoryService()
    return service.redact_all()


def _retain_memory_service(max_age_days: int, *, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.memory_service import MemoryService

    service = MemoryService(db_path=_memory_service_db(project_root)) if project_root else MemoryService()
    return service.apply_retention(max_age_days)


def _export_wiki(*, project_root: str | None = None) -> list[dict[str, JsonValue]]:
    from antigravity_k.knowledge.wiki import LLMWiki

    wiki = _wiki_for_project(project_root) if project_root else LLMWiki()
    return _DURABLE_EXPORT_ADAPTER.validate_python(wiki.export_all())


def _redact_wiki(*, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.wiki import LLMWiki

    wiki = _wiki_for_project(project_root) if project_root else LLMWiki()
    return wiki.redact_all()


def _retain_wiki(max_age_days: int, *, project_root: str | None = None) -> int:
    from antigravity_k.knowledge.wiki import LLMWiki

    wiki = _wiki_for_project(project_root) if project_root else LLMWiki()
    return wiki.apply_retention(max_age_days)


def _export_gbrain(*, project_root: str | None = None) -> list[dict[str, JsonValue]]:
    from antigravity_k.engine.gbrain import global_gbrain

    brain = _gbrain_for_project(project_root) if project_root else global_gbrain
    return _DURABLE_EXPORT_ADAPTER.validate_python(
        [_widen_graph_record(record) for record in brain.export_all()],
    )


def _redact_gbrain(*, project_root: str | None = None) -> int:
    from antigravity_k.engine.gbrain import global_gbrain

    brain = _gbrain_for_project(project_root) if project_root else global_gbrain
    return brain.redact_all()


def _export_project_vector(*, project_root: str | None = None) -> list[dict[str, JsonValue]]:
    from antigravity_k.engine.vector_store import VectorStore

    if not project_root:
        vector_path = Path.cwd() / ".antigravity" / "vault_data"
        if not vector_path.exists():
            return []
        vector_store = VectorStore(str(vector_path), collection_name="agent_knowledge")
        try:
            return _DURABLE_EXPORT_ADAPTER.validate_python(
                [_widen_graph_record(record) for record in vector_store.export_all()],
            )
        finally:
            vector_store.close()

    records: list[dict[str, JsonValue]] = []
    for vector_path, collection_name in _project_vector_targets(project_root):
        if not vector_path.exists():
            continue
        vector_store = VectorStore(str(vector_path), collection_name=collection_name)
        try:
            records.extend(
                _DURABLE_EXPORT_ADAPTER.validate_python(
                    [_widen_graph_record(record) for record in vector_store.export_all()],
                ),
            )
        finally:
            vector_store.close()
    return records


def _redact_project_vector(*, project_root: str | None = None) -> int:
    from antigravity_k.engine.vector_store import VectorStore

    if not project_root:
        vector_path = Path.cwd() / ".antigravity" / "vault_data"
        if not vector_path.exists():
            return 0
        vector_store = VectorStore(str(vector_path), collection_name="agent_knowledge")
        try:
            return vector_store.redact_all()
        finally:
            vector_store.close()

    changed = 0
    for vector_path, collection_name in _project_vector_targets(project_root):
        if not vector_path.exists():
            continue
        vector_store = VectorStore(str(vector_path), collection_name=collection_name)
        try:
            changed += vector_store.redact_all()
        finally:
            vector_store.close()
    return changed


def _export_search_cache(*, project_root: str | None = None) -> list[dict[str, JsonValue]]:
    cache_dir = _search_cache_dir(project_root)
    if not cache_dir.exists():
        return []
    records: list[dict[str, JsonValue]] = []
    for cache_file in cache_dir.glob("*.json"):
        try:
            data = _JSON_VALUE_ADAPTER.validate_json(cache_file.read_text(encoding="utf-8"))
            records.append({"file": cache_file.name, "data": data})
        except (OSError, ValidationError):
            continue
    return records


def _redact_search_cache(*, project_root: str | None = None) -> int:
    from antigravity_k.engine.secret_scanner import redact_full

    cache_dir = _search_cache_dir(project_root)
    changed = 0
    for record in _export_search_cache(project_root=project_root):
        data = json.dumps(record["data"], ensure_ascii=False)
        redacted = redact_full(data)
        if redacted != data:
            cache_file = _json_text(record.get("file"))
            if not cache_file:
                continue
            _ = (cache_dir / cache_file).write_text(redacted, encoding="utf-8")
            changed += 1
    return changed


def _retain_search_cache(max_age_days: int, *, project_root: str | None = None) -> int:
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    from datetime import UTC, datetime, timedelta

    cache_dir = _search_cache_dir(project_root)
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    deleted = 0
    for record in _export_search_cache(project_root=project_root):
        cached_at = _json_text(_json_object(record.get("data")).get("cached_at"))
        try:
            timestamp = datetime.fromisoformat(cached_at)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            continue
        if timestamp < cutoff:
            try:
                cache_file = _json_text(record.get("file"))
                if not cache_file:
                    continue
                (cache_dir / cache_file).unlink()
                deleted += 1
            except OSError:
                continue
    return deleted


def __get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry(project_root=os.getcwd())
        _ = _tool_registry.auto_discover("antigravity_k.tools")
    return _tool_registry


def get_tool_registry() -> ToolRegistry:
    """Prefer the request project's orchestrator registry when a context is bound."""
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    if get_bound_request_execution_context() is not None:
        return get_orchestrator().tool_registry
    return __get_tool_registry()


def __get_skill_loader() -> SkillLoader:
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader(project_root=os.getcwd())
    return _skill_loader


def get_skill_loader() -> SkillLoader:
    """Prefer the request project's skill loader when a context is bound."""
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    if get_bound_request_execution_context() is not None:
        return get_orchestrator().ctx.skill_loader
    return __get_skill_loader()


def _get_context_shaper() -> ContextShaper:
    global _context_shaper
    if _context_shaper is None:
        _context_shaper = ContextShaper()
    return _context_shaper


def get_model_manager() -> ModelManager:
    """Retrieve model manager.

    Returns:
        ModelManager: The modelmanager result.

    """
    global model_manager
    if model_manager is None:
        logger.info("Lazy initializing ModelManager...")
        from antigravity_k.engine.usage_tracker import UsageTracker, default_usage_db_path

        registry = ModelRegistry()
        # 경로를 하드코딩하지 않는다 — 기본 경로는 `default_usage_db_path()` 한 곳에서 정해진다.
        # `data/token_usage.json` 은 추적 파일이라, 테스트가 이 경로를 그대로 쓰면
        # 50건 자동 저장 임계값을 넘기는 순간 검증 실행이 후보 트리를 바꾼다(F-08).
        # `AGK_USAGE_DB` 로 배포·격리 실행에서 위치를 바꿀 수 있다.
        tracker = UsageTracker(db_path=str(default_usage_db_path()))
        model_manager = ModelManager(registry, tracker=tracker)
    return model_manager


def get_vault_engine(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> VaultEngine | None:
    """Retrieve vault engine.

    Returns the project-scoped VaultEngine when a RequestExecutionContext is active
    or explicit project parameters are given (WS-03 isolation); falls back to the
    ambient process-level vault engine otherwise.
    """
    global vault_engine

    # 1. Active RequestExecutionContext or explicit parameters (WS-03 project isolation)
    try:
        from antigravity_k.api.project_binding import get_bound_request_execution_context

        ctx = get_bound_request_execution_context()
        if ctx is not None:
            runtime = acquire_project_runtime(
                project_id=project_id or ctx.project_id,
                project_root=project_root or ctx.canonical_project_root,
            )
            if runtime.vault_engine is not None:
                return runtime.vault_engine
    except Exception:
        logger.debug("Project-scoped vault resolution via RequestExecutionContext skipped", exc_info=True)

    if project_id or project_root:
        try:
            runtime = acquire_project_runtime(project_id=project_id, project_root=project_root)
            if runtime.vault_engine is not None:
                return runtime.vault_engine
        except Exception:
            logger.debug("Project-scoped vault resolution via parameters skipped", exc_info=True)

    # 2. Ambient process fallback (backward compatibility)
    if vault_engine is None:
        vault_path = os.environ.get("ANTIGRAVITY_VAULT_PATH", "./vault_data")
        try:
            vault_engine = VaultEngine(vault_path=vault_path, sync_rag=True)
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("VaultEngine 초기화 실패 (RAG 비활성): %s", e)
            try:
                vault_engine = VaultEngine(vault_path=vault_path, sync_rag=False)
            except OSError:
                logger.exception("VaultEngine 완전 실패")
                return None
    return vault_engine


def get_orchestrator(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> OrchestratorAgent:
    """Return the OrchestratorAgent for the resolved project (WS-03).

    Cache key is ``project_id``. Project switches reuse or create handles —
    they never mutate another project's orchestrator fields in place.
    """
    return acquire_project_runtime(project_id=project_id, project_root=project_root).orchestrator


def get_benchmark_harness() -> BenchmarkHarness:
    global _benchmark_harness
    from antigravity_k.engine.task_runner import get_task_runner

    if _benchmark_harness is None:
        manager = get_model_manager()
        _benchmark_harness = BenchmarkHarness(
            manager,
            task_calibration_updater=manager.router.set_task_calibration,
        )
    _ = _benchmark_harness.bind_task_runner(get_task_runner())
    return _benchmark_harness


def get_agent_runtime(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> AgentRuntime:
    """Return the AgentRuntime bound to the resolved project's orchestrator."""
    runtime = acquire_project_runtime(project_id=project_id, project_root=project_root).agent_runtime
    if runtime is None:
        raise RuntimeError("ProjectRuntime missing agent_runtime")
    return runtime


def get_scheduled_job_service(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
) -> ScheduledJobService:
    """Return the ScheduledJobService bound to the resolved project's agent runtime."""
    runtime = acquire_project_runtime(project_id=project_id, project_root=project_root)
    if runtime.scheduled_job_service is None:
        if runtime.agent_runtime is None:
            raise RuntimeError("ProjectRuntime missing agent_runtime for job service")
        runtime.scheduled_job_service = _build_project_job_service(runtime.agent_runtime, runtime.project_root)
    return runtime.scheduled_job_service


def get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service


def get_translator() -> ProtocolTranslator:
    """Retrieve translator.

    Returns:
        ProtocolTranslator: The protocoltranslator result.

    """
    global protocol_translator
    if protocol_translator is None:
        logger.info("Lazy initializing ProtocolTranslator...")
        protocol_translator = ProtocolTranslator()
    return protocol_translator


def get_embedding_engine() -> EmbeddingEngine:
    """Retrieve embedding engine.

    Returns:
        EmbeddingEngine: The embeddingengine result.

    """
    engine = EmbeddingEngine()
    engine.initialize()
    return engine


_slash_registry = None  # legacy unused; project registries live on ProjectRuntime


def get_slash_registry(
    *,
    project_id: str | None = None,
    project_root: str | None = None,
):
    """Return the slash registry for the resolved project (WS-03 F3).

    Never freezes the first ``agent_runtime`` into a process singleton.
    """
    runtime = acquire_project_runtime(project_id=project_id, project_root=project_root)
    if runtime.slash_registry is None:
        if runtime.agent_runtime is None:
            raise RuntimeError("ProjectRuntime missing agent_runtime for slash registry")
        runtime.slash_registry = _build_project_slash_registry(
            session_manager=runtime.session_manager,
            agent_runtime=runtime.agent_runtime,
            orchestrator=runtime.orchestrator,
        )
    else:
        # Refresh runtime pointer in case of recreate edge cases.
        bind = getattr(runtime.slash_registry, "bind_runtime", None)
        if callable(bind) and runtime.agent_runtime is not None:
            bind(runtime.agent_runtime)
        setattr(runtime.slash_registry, "_session_manager", runtime.session_manager)
    return runtime.slash_registry


# ─── WS-01 request-scoped project binding (consume ARC-01) ─────────────────


def get_request_execution_context():
    """FastAPI-friendly accessor for the bound RequestExecutionContext."""
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    return get_bound_request_execution_context()


def require_request_execution_context():
    from antigravity_k.api.contracts.errors import MissingExecutionContextError
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    ctx = get_bound_request_execution_context()
    if ctx is None:
        raise MissingExecutionContextError(detail="RequestExecutionContext is not bound for this request")
    return ctx


def _attach_cognitive_surface(agent_runtime: AgentRuntime, model_manager: object) -> None:
    """P11 opt-in 배선: 설정(cognitive_core)이 SHADOW면 대화·과제 완료를 shadow로 관찰한다.

    설정이 없거나 OFF면 surface를 붙이지 않는다(legacy 그대로). think port는 실제 모델
    (SurfaceBrainPort)이고 모델 실패는 failed think로 episode가 BRAIN_FAILED 종료될 뿐
    legacy 경로에 영향이 없다. ACTIVE는 사람 승인·dispatch port가 필요해 여기서 붙지 않는다.
    """

    from antigravity_k.config import config
    from antigravity_k.engine.cognitive_surface import (
        CognitiveCoreSettings,
        CognitiveSurfaceAdapter,
        SurfaceBrainPort,
        SurfaceMode,
    )

    settings = CognitiveCoreSettings.from_config(config)
    if str(settings.effective_mode) != str(SurfaceMode.SHADOW):
        return

    def generate(prompt: str) -> str:
        target = model_manager.get_target_for_role("default", default_role="default")  # type: ignore[attr-defined]
        return str(model_manager.generate(prompt=prompt, target=target, temperature=0.2, max_tokens=512))  # type: ignore[attr-defined]

    agent_runtime.attach_cognitive_surface(CognitiveSurfaceAdapter(settings, think=SurfaceBrainPort(generate)))
