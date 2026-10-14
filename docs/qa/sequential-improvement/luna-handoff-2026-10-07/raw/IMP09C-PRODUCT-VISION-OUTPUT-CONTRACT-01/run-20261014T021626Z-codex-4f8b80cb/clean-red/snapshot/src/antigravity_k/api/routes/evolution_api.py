"""Evolution API — 스킬/시스템 프롬프트 자율 진화 엔드포인트."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, JsonValue

from antigravity_k.api.dependencies import get_model_manager, get_vault_engine
from antigravity_k.config import config
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.vault import VaultEngine
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

router = APIRouter()
ModelManagerDependency = Annotated[ModelManager, Depends(get_model_manager)]
VaultDependency = Annotated[VaultEngine | None, Depends(get_vault_engine)]


def _permission_gate() -> PermissionGate:
    return PermissionGate(project_root=str(config.paths.project_root), mode="auto-pilot")


def _require_allowed(tool_name: str, args: dict[str, JsonValue], risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for {tool_name}: {decision.permission.value}",
        )


class EvolveRequest(BaseModel):
    """Evolverequest.

    Bases: BaseModel
    """

    skill_name: str = Field(..., description="Name of the skill to evolve")
    target_model: str = Field(default="qwen3.6:latest", description="Model to use for evolution")


class EvolveSystemPromptRequest(BaseModel):
    """Evolvesystempromptrequest.

    Bases: BaseModel
    """

    target_model: str = Field(default="qwen3.6:latest", description="Model to use for evolution")


@router.post("/api/agent/evolve")
async def evolve_skill_api(
    req: EvolveRequest,
    manager: ModelManagerDependency,
    vault: VaultDependency,
) -> dict[str, str]:
    """특정 스킬에 대해 과거 실패 이력을 바탕으로 한 자율 진화(Self-Evolution)를 시작합니다.

    진화된 결과는 SKILL_EVOLVED.md 로 저장되어 인간의 검토를 기다립니다.
    """
    _require_allowed("evolve_skill", {"skill_name": req.skill_name, "target_model": req.target_model}, "critical")
    from antigravity_k.engine.evolution import EvolutionManager

    if vault is None:
        raise HTTPException(
            status_code=422,
            detail="VaultEngine is not initialized. Set ANTIGRAVITY_VAULT_PATH environment variable.",
        )

    ev_manager = EvolutionManager(model_manager=manager, vault_engine=vault)
    draft_path = ev_manager.evolve_skill(skill_name=req.skill_name, target_model=req.target_model)

    if draft_path:
        return {
            "status": "success",
            "message": f"Skill '{req.skill_name}' has been successfully evolved.",
            "draft_path": draft_path,
        }
    raise HTTPException(
        status_code=500,
        detail="Failed to evolve skill. Check logs for details.",
    )


@router.post("/api/agent/evolve_system_prompt")
async def evolve_system_prompt_api(
    req: EvolveSystemPromptRequest,
    manager: ModelManagerDependency,
    vault: VaultDependency,
) -> dict[str, str]:
    """시스템 프롬프트의 자율 진화를 시작합니다."""
    _require_allowed("evolve_system_prompt", {"target_model": req.target_model}, "critical")
    from antigravity_k.engine.evolution import EvolutionManager

    if vault is None:
        raise HTTPException(
            status_code=422,
            detail="VaultEngine is not initialized. Set ANTIGRAVITY_VAULT_PATH environment variable.",
        )

    ev_manager = EvolutionManager(model_manager=manager, vault_engine=vault)
    draft_path = ev_manager.evolve_system_prompt(target_model=req.target_model)

    if draft_path:
        return {
            "status": "success",
            "message": "System prompt has been successfully evolved.",
            "draft_path": draft_path,
        }
    raise HTTPException(
        status_code=500,
        detail="Failed to evolve system prompt. Check logs for details.",
    )
