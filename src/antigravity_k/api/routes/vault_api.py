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


VaultDependency = Annotated[VaultEngine | None, Depends(get_vault_engine)]


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
