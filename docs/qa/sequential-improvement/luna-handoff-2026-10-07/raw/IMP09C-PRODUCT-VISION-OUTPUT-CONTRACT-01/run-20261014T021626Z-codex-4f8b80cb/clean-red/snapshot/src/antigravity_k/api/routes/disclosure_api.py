"""세션 한도 고지 API — 시작 전 사용자 고지 제공.

벤치마킹 출처: freebuff의 "session limits + data-use notice before you start" UX.
CostGuard의 라이브 상태를 사용자용 고지로 변환해 노출한다.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response

from antigravity_k.engine.cost_guard import CostGuard
from antigravity_k.engine.session_disclosure import build_session_disclosure

router = APIRouter(prefix="/api/session")


_seeded_guard: CostGuard | None = None


def set_seeded_cost_guard(guard: CostGuard | None) -> None:
    """테스트 또는 CLI 주입용 시딩된 CostGuard 설정."""
    global _seeded_guard
    _seeded_guard = guard


def get_cost_guard() -> CostGuard:
    """EngineContext의 CostGuard 재사용 우선, 실패 시 env 기반 fresh guard.

    AGK_SEED_BUDGET / AGK_SEED_LEVEL / AGK_SEED_ACTIONS 환경변수가 지정된 경우
    seed_cost_guard를 통해 결정론적인 시딩 가드를 반환한다.
    """
    global _seeded_guard
    if _seeded_guard is not None:
        return _seeded_guard

    guard: CostGuard | None = None
    try:
        from antigravity_k.api.dependencies import get_orchestrator

        candidate = get_orchestrator().ctx.cost_guard
        if isinstance(candidate, CostGuard):
            guard = candidate
    except Exception:  # noqa: BLE001 — 오케스트레이터 미기동 시 폴백
        pass

    if guard is None:
        daily_budget = float(os.getenv("AGK_DAILY_BUDGET_USD", "50.0") or 0.0)
        hourly_limit = int(os.getenv("AGK_HOURLY_ACTION_LIMIT", "100") or 0)
        guard = CostGuard(daily_budget_usd=daily_budget, hourly_action_limit=hourly_limit, enabled=True)

    seed_budget = os.getenv("AGK_SEED_BUDGET")
    seed_level = os.getenv("AGK_SEED_LEVEL")
    seed_actions_raw = os.getenv("AGK_SEED_ACTIONS")
    seed_actions = int(seed_actions_raw) if seed_actions_raw else None

    if seed_budget or seed_level or seed_actions is not None:
        from antigravity_k.engine.session_disclosure import seed_cost_guard

        seed_cost_guard(
            guard,
            seed_budget=seed_budget,
            seed_level=seed_level,
            seed_actions=seed_actions,
        )
        _seeded_guard = guard

    return guard


@router.get("/disclosure")
async def get_disclosure(
    guard: CostGuard = Depends(get_cost_guard),
) -> dict[str, object]:
    """구조화된 세션 고지를 반환한다."""
    return build_session_disclosure(guard.get_daily_stats()).to_dict()


@router.get("/disclosure.md")
async def get_disclosure_markdown(
    guard: CostGuard = Depends(get_cost_guard),
) -> Response:
    """마크다운 렌더링 세션 고지를 반환한다."""
    disclosure = build_session_disclosure(guard.get_daily_stats())
    return Response(content=disclosure.to_markdown(), media_type="text/markdown; charset=utf-8")
