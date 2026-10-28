"""Vault API — Wiki 노트 CRUD·검색·동기화 엔드포인트."""

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, ClassVar, Literal, TypedDict, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictStr, ValidationError

from antigravity_k.api.dependencies import get_vault_engine
from antigravity_k.api.path_security import PathSecurityError, resolve_allowed_path
from antigravity_k.config import config
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.vault import VaultEngine
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.vault")
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class _VaultConfigRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    vault_path: StrictStr = ""


class _VaultWriteRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = ""
    content: StrictStr = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class VaultTreeNode(TypedDict, total=False):
    name: str
    path: str
    type: Literal["folder", "file"]
    children: list["VaultTreeNode"]
    size: int


def _resolve_vault_project_id(request: Request) -> str | None:
    """r36: the project whose vault the Wiki/vault routes operate on.

    The chat orchestrator reads past_memory from the *project-scoped* vault, while the
    dashboard Wiki posts /api/vault/* with no project identity; resolving those requests
    to the process-cwd ambient vault meant a saved memo could never reach past_memory
    (r36 trace: write -> $HOME/.antigravity-k/vault_data, read -> <project>/.antigravity/vault_data).
    Order: explicit X-AGK-Project-Id header / ``project_id`` query -> session active-project
    binding -> the registry's active project (the project the UI shows as current).
    The implicit cwd default project keeps the ambient vault (unchanged behaviour)."""
    from antigravity_k.api.project_binding import SESSION_ID_HEADER, get_session_active_project

    explicit = (request.headers.get("X-AGK-Project-Id") or request.query_params.get("project_id") or "").strip()
    binding = get_session_active_project(request.headers.get(SESSION_ID_HEADER))
    if explicit:
        # r37: an explicit id is validated (registered, root under the allowed bases) and must
        # agree with the current request/session project context. A wrong id is an error, never a
        # silent fallback to the default/ambient vault.
        _validate_explicit_vault_project(explicit, binding.project_id if binding is not None else None)
        return explicit
    if binding is not None:
        return binding.project_id
    try:
        from antigravity_k.engine.project_embedding_binding import IMPLICIT_DEFAULT_PROJECT_ID
        from antigravity_k.engine.project_registry import get_project_registry

        active = get_project_registry().get_active_project()
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - registry unavailable -> ambient vault
        logger.warning("vault project resolution: registry unavailable; using ambient vault")
        return None
    return None if active.id == IMPLICIT_DEFAULT_PROJECT_ID else active.id


def _validate_explicit_vault_project(project_id: str, session_project_id: str | None) -> str:
    """r37: existence + allowed-root + request-context check for an explicit vault project id.

    Returns the canonical project root. Raises 404 (unknown id), 403 (root outside the allowed
    bases) or 409 (disagrees with the session binding / bound request context)."""
    from antigravity_k.api.contracts.errors import ExecutionContextError, ProjectNotFoundError
    from antigravity_k.api.project_binding import get_request_project_id
    from antigravity_k.engine.request_execution_context import resolve_canonical_project_root

    try:
        _record, canonical = resolve_canonical_project_root(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="vault project not found") from exc
    except ExecutionContextError as exc:
        raise HTTPException(status_code=403, detail="vault project root not allowed") from exc
    bound = get_request_project_id()
    for current in (bound, session_project_id):
        if current and current != project_id:
            raise HTTPException(status_code=409, detail="vault project_id does not match the current project context")
    return canonical


def _project_vault_engine(
    request: Request,
    ambient: Annotated[VaultEngine | None, Depends(get_vault_engine)],
) -> VaultEngine | None:
    from antigravity_k.engine.project_embedding_binding import IMPLICIT_DEFAULT_PROJECT_ID

    project_id = _resolve_vault_project_id(request)
    if not project_id or project_id == IMPLICIT_DEFAULT_PROJECT_ID:
        # implicit default project -> ambient vault, resolved through DI (dependency overrides apply)
        return ambient
    # r37: a resolved project must reach *its* store; no silent ambient fallback on failure.
    from antigravity_k.api.dependencies import acquire_project_runtime
    from antigravity_k.engine.request_execution_context import resolve_canonical_project_root

    try:
        _record, canonical = resolve_canonical_project_root(project_id)
        runtime = acquire_project_runtime(project_id=project_id, project_root=canonical)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - fail closed, no fallback
        logger.warning("vault project runtime unavailable for resolved project; refusing fallback")
        raise HTTPException(status_code=503, detail="project vault unavailable") from exc
    if runtime.vault_engine is None:
        raise HTTPException(status_code=503, detail="project vault unavailable")
    return runtime.vault_engine


VaultDependency = Annotated[VaultEngine | None, Depends(_project_vault_engine)]


async def _parse_json_body(request: Request, model: type[_ModelT]) -> _ModelT:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


def _permission_gate() -> PermissionGate:
    return PermissionGate(project_root=str(config.paths.project_root), mode="auto-pilot")


def _require_allowed(tool_name: str, args: Mapping[str, JsonValue], risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for {tool_name}: {decision.permission.value}",
        )


@router.get("/api/vault/config")
def vault_config(engine: VaultDependency):
    """현재 Vault 설정 조회."""
    if not engine:
        return {"ok": False, "vault_path": None, "message": "VaultEngine not available"}
    return {"ok": True, "vault_path": str(engine.vault_path)}


@router.post("/api/vault/config")
async def set_vault_config(request: Request):
    """Vault 경로를 동적으로 변경 (Wiki + Chat 공유용).

    새 VaultEngine을 생성하고 dependencies.py의 싱글톤을 업데이트합니다.
    이후 /api/vault/tree 등의 모든 Vault API가 새 경로를 사용합니다.
    """
    payload = await _parse_json_body(request, _VaultConfigRequest)
    new_path = payload.vault_path
    if not new_path:
        raise HTTPException(status_code=400, detail="'vault_path' is required")
    try:
        target_path = resolve_allowed_path(new_path)
    except PathSecurityError as exc:
        raise HTTPException(status_code=403, detail="Vault path is outside the configured workspace roots.") from exc
    target = str(target_path)
    _require_allowed("set_vault_config", {"vault_path": target}, "critical")
    if not os.path.isdir(target):
        # 디렉토리가 없으면 생성 시도
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Cannot create directory: {e}")
    new_engine: VaultEngine
    try:
        new_engine = VaultEngine(vault_path=target, sync_rag=True)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Vault 재초기화 실패 (RAG 비활성): %s", e)
        try:
            new_engine = VaultEngine(vault_path=target, sync_rag=False)
        except (OSError, RuntimeError, ValueError) as e2:
            raise HTTPException(status_code=500, detail=f"Vault init failed: {e2}")

    # 싱글톤 업데이트 — 이후 모든 Vault API가 새 경로를 사용
    import antigravity_k.api.dependencies as deps

    deps.vault_engine = new_engine

    logger.info("Vault 경로 변경됨: %s", target)
    return {"ok": True, "vault_path": str(new_engine.vault_path)}


@router.get("/api/vault/tree")
def vault_tree(engine: VaultDependency):
    """Return the vault directory tree as a nested JSON structure."""
    if not engine:
        raise HTTPException(status_code=503, detail="VaultEngine not available")

    def build_tree(base_path: Path, rel_prefix: str = "") -> list[VaultTreeNode]:
        items: list[VaultTreeNode] = []
        try:
            entries = sorted(base_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return items
        for entry in entries:
            if entry.name.startswith("."):
                continue
            rel = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
            if entry.is_dir():
                children = build_tree(entry, rel)
                items.append(
                    {
                        "name": entry.name,
                        "path": rel,
                        "type": "folder",
                        "children": children,
                    },
                )
            elif entry.suffix.lower() in (".md", ".txt", ".yaml", ".yml"):
                items.append(
                    {
                        "name": entry.name,
                        "path": rel,
                        "type": "file",
                        "size": entry.stat().st_size,
                    },
                )
        return items

    tree = build_tree(engine.vault_path)
    return {"tree": tree, "vault_path": str(engine.vault_path)}


@router.get("/api/vault/read")
def vault_read(path: str, engine: VaultDependency):
    """Read a note from the vault. Returns metadata + content."""
    if not engine:
        raise HTTPException(status_code=503, detail="VaultEngine not available")
    # Security: prevent path traversal
    clean = Path(path)
    if ".." in clean.parts:
        raise HTTPException(status_code=400, detail="Invalid path")
    try:
        metadata, content = engine.read_note(path)
        return {"path": path, "metadata": metadata, "content": content}
    except ValueError as e:
        # Absolute / traversal / symlink escape from VaultEngine._safe_resolve
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/vault/write")
async def vault_write(request: Request, engine: VaultDependency):
    """Create or update a note in the vault."""
    if not engine:
        raise HTTPException(status_code=503, detail="VaultEngine not available")
    payload = await _parse_json_body(request, _VaultWriteRequest)
    path = payload.path
    content = payload.content
    metadata = payload.metadata
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")
    clean = Path(path)
    if ".." in clean.parts:
        raise HTTPException(status_code=400, detail="Invalid path")
    _require_allowed("vault_write", {"path": path}, "medium")
    try:
        engine.write_note(path, metadata, content, commit_message=f"Wiki edit: {path}")
        return {"ok": True, "path": path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (OSError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/vault/sync")
async def vault_sync(engine: VaultDependency):
    """현재 Vault 상태를 Git 스냅샷으로 저장."""
    if not engine:
        raise HTTPException(status_code=503, detail="VaultEngine not available")
    _require_allowed("vault_sync", {}, "high")
    try:
        commit_hash = engine.create_snapshot("Manual sync via Command Palette")
        return {"ok": True, "commit": commit_hash}
    except (OSError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/notes/search")
def search_notes(q: str, engine: VaultDependency):
    """Search for notes.

    Args:
        q (str): str q.
        engine (VaultEngine): VaultEngine engine.

    """
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    if not engine:
        raise HTTPException(status_code=503, detail="VaultEngine not available")

    audit = get_audit_logger()
    audit.log_event("search_notes", {"query": q})

    try:
        # 1. Semantic search via RAG (ChromaDB)
        semantic_results = engine.vector_store.search(q, n_results=5) if engine.sync_rag else []

        # 2. Keyword search via Vault text match
        keyword_results = engine.search_notes(q)

        return {
            "query": q,
            "semantic_results": semantic_results,
            "keyword_results": keyword_results,
        }
    except (ValueError, KeyError) as e:
        logger.error("Search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/vault/embedding-status")
def vault_embedding_status(probe: bool = False):
    """로컬 Ollama 임베딩 상태. 기본은 읽기 전용(/api/tags)이며 probe=true일 때만 임베딩 1회."""
    from antigravity_k.engine.embedding_readiness import check_embedding_readiness
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.project_embedding_binding import RAG_EMBEDDING_ENV

    binding_enabled = os.environ.get(RAG_EMBEDDING_ENV, "").strip().casefold() == "ollama"
    registry = ModelRegistry()
    profile = registry.get_default("embedding")
    if profile is None:
        return {
            "state": "model_missing",
            "rag_ready": False,
            "model": "",
            "message": "임베딩 모델이 설정되지 않았습니다.",
            "model_present": False,
            "embedding_verified": False,
            "app_rag_binding": binding_enabled,
            "app_rag_ready": False,
        }
    from antigravity_k.api.dependencies import project_rag_state

    result = dict(check_embedding_readiness(profile, registry, probe=probe))
    present = result["state"] not in {"ollama_unreachable", "model_missing"}
    verified = result["state"] == "ready"
    project_state = project_rag_state()
    result.update(
        model_present=present,
        embedding_verified=verified,
        app_rag_binding=binding_enabled,
        project_rag_state=project_state,
        # RAG-ready requires the active project's bound indexer; setup-pending is never ready.
        app_rag_ready=verified and binding_enabled and project_state == "attached",
    )
    return result
