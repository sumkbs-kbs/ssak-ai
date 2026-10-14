from typing import Annotated, ClassVar, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.api.dependencies import get_vault_engine
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.vault_privacy_contracts import (
    VaultPrivacyAction,
    VaultPrivacyError,
    VaultPrivacyFailure,
    VaultPrivacyMutation,
)

router = APIRouter()

VaultPaths = Annotated[tuple[str, ...], Field(min_length=1, max_length=100)]
RedactionValue = Annotated[str, Field(min_length=1)]
RedactionValues = Annotated[tuple[RedactionValue, ...], Field(min_length=1, max_length=100)]
SnapshotCommit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class VaultRedactRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    paths: VaultPaths
    values: RedactionValues
    confirmation: Literal["REDACT_VAULT_ACTIVE_CORPUS"]


class VaultPurgeRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    paths: VaultPaths
    confirmation: Literal["PURGE_VAULT_ACTIVE_CORPUS"]


class VaultRestoreRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    snapshot_commit: SnapshotCommit
    paths: VaultPaths
    confirmation: Literal["RESTORE_VAULT_SNAPSHOT"]


@router.post("/api/memory/vault/redact")
async def redact_vault_assets(request: VaultRedactRequest) -> dict[str, str | int | bool | tuple[str, ...]]:
    vault = get_vault_engine()
    if vault is None:
        raise HTTPException(status_code=503, detail="Vault is unavailable")
    try:
        result = vault.apply_privacy_mutation(
            VaultPrivacyMutation(
                action=VaultPrivacyAction.REDACT,
                paths=request.paths,
                values=request.values,
            ),
        )
    except VaultPrivacyError as exc:
        status_code = 404 if exc.failure is VaultPrivacyFailure.MISSING_NOTE else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    get_audit_logger().log_event(
        "vault_redact",
        {"paths": result.paths, "changed_files": result.changed_files},
    )
    return {
        "action": result.action.value,
        "paths": result.paths,
        "changed_files": result.changed_files,
        "replacement_count": result.replacement_count,
        "snapshot_commit": result.snapshot_commit,
        "mutation_commit": result.mutation_commit,
        "history_retained_for_rollback": result.history_retained_for_rollback,
    }


@router.post("/api/memory/vault/purge")
async def purge_vault_assets(request: VaultPurgeRequest) -> dict[str, str | int | bool | tuple[str, ...]]:
    vault = get_vault_engine()
    if vault is None:
        raise HTTPException(status_code=503, detail="Vault is unavailable")
    try:
        result = vault.apply_privacy_mutation(
            VaultPrivacyMutation(
                action=VaultPrivacyAction.PURGE,
                paths=request.paths,
            ),
        )
    except VaultPrivacyError as exc:
        status_code = 404 if exc.failure is VaultPrivacyFailure.MISSING_NOTE else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    get_audit_logger().log_event(
        "vault_purge",
        {"paths": result.paths, "changed_files": result.changed_files},
    )
    return {
        "action": result.action.value,
        "paths": result.paths,
        "changed_files": result.changed_files,
        "replacement_count": result.replacement_count,
        "snapshot_commit": result.snapshot_commit,
        "mutation_commit": result.mutation_commit,
        "history_retained_for_rollback": result.history_retained_for_rollback,
    }


@router.post("/api/memory/vault/restore")
async def restore_vault_snapshot(request: VaultRestoreRequest) -> dict[str, str | bool | tuple[str, ...]]:
    vault = get_vault_engine()
    if vault is None:
        raise HTTPException(status_code=503, detail="Vault is unavailable")
    try:
        restored = vault.restore_privacy_snapshot(request.snapshot_commit, request.paths)
    except VaultPrivacyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not restored:
        raise HTTPException(status_code=409, detail="Vault snapshot could not be restored")
    get_audit_logger().log_event(
        "vault_restore",
        {"snapshot_commit": request.snapshot_commit, "paths": request.paths},
    )
    return {"restored": True, "snapshot_commit": request.snapshot_commit, "paths": request.paths}
