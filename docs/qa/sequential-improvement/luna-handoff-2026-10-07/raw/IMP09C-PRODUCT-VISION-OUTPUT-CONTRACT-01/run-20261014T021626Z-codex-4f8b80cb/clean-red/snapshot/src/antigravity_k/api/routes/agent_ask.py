"""Unified agent ask API route."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    task: str = Field(min_length=1)
    model: str | None = None
    test_code: str | None = None
    adaptive: bool = True
    use_web: bool = False
    project_id: str | None = None


class AgentResponse(BaseModel):
    ok: bool = True
    task: str
    answer: str
    used_web: bool
    used_graphify: bool
    steps: int
    total_seconds: float
    passed: bool | None = None
    mode: str = "standard"
    error: str | None = None


@router.post("/ask", response_model=AgentResponse)
async def agent_ask(request: AgentRequest) -> AgentResponse:
    from antigravity_k.api.dependencies import get_model_manager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.unified_agent import UnifiedAgent

    registry = ModelRegistry()
    target = request.model or registry.defaults.reasoning or registry.defaults.coding
    if target is None:
        target = "qwen3.6:latest"
    mm = get_model_manager()
    agent = UnifiedAgent(mm.generate, target, project_root=Path.cwd())
    use_adaptive = bool(request.test_code) and request.adaptive
    outcome = agent.run(
        request.task,
        test_code=request.test_code,
        adaptive=use_adaptive,
        use_web=request.use_web,
    )
    return AgentResponse(
        ok=True,
        task=request.task,
        answer=outcome.answer,
        used_web=outcome.used_web,
        used_graphify=outcome.used_graphify,
        steps=len(outcome.steps),
        total_seconds=outcome.total_seconds,
        passed=outcome.passed,
        mode="adaptive" if use_adaptive else "standard",
    )
