"""레시피 프리셋 API — 학습 레시피 카탈로그 + 감사된 하이퍼파라미터 노출.

Phase 24: 대시보드 학습 UI(StudioPage STEP 4)에서 레시피 프리셋을 선택해
편집 가능한 하이퍼파라미터 필드를 채울 수 있도록 카탈로그를 제공한다.
단일 진실원은 `engine/data_recipes.py`의 RECIPES (Phase 11 감사값 포함).
"""

from __future__ import annotations

from fastapi import APIRouter

from antigravity_k.engine.data_recipes import RECIPES
from antigravity_k.finetune.hyperparameters import backend_capabilities

router = APIRouter(prefix="/api/recipes")


@router.get("/capabilities")
async def list_capabilities() -> dict[str, object]:
    """백엔드 capability schema (TRN-01) — MLX/Unsloth 지원 차이를 UI에 노출."""
    return {"ok": True, "capabilities": [backend_capabilities("mlx"), backend_capabilities("unsloth")]}


@router.get("")
async def list_recipes() -> dict[str, object]:
    """학습 데이터 레시피 프리셋 목록 (하이퍼파라미터 오버라이드 포함)."""
    return {
        "ok": True,
        "recipes": [
            {
                "name": recipe.name,
                "title": recipe.title,
                "description": recipe.description,
                "source_hint": recipe.source_hint,
                "format": recipe.format,
                "min_records": recipe.min_records,
                "hyperparameters": dict(recipe.hyperparameter_overrides),
            }
            for recipe in RECIPES
        ],
    }
