from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import ClassVar, override

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from starlette.responses import Response

from antigravity_k.engine.decision_evaluation import evaluate_decisions
from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport, DecisionEvaluationRequest


class DecisionEvaluationInputError(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
    detail: str


class DecisionEvaluationRoute(APIRoute):
    @override
    def get_route_handler(self) -> Callable[[Request], Coroutine[None, None, Response]]:
        original_handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError:
                error = DecisionEvaluationInputError(detail="Invalid decision evaluation input")
                return JSONResponse(status_code=422, content=error.model_dump())

        return handle


router = APIRouter(prefix="/api/benchmarks/decisions", route_class=DecisionEvaluationRoute)


@router.post(
    "/evaluate",
    response_model=DecisionEvaluationReport,
    responses={422: {"model": DecisionEvaluationInputError}},
)
def evaluate_decision_probabilities(request: DecisionEvaluationRequest) -> DecisionEvaluationReport:
    """Measure supplied probabilities without attesting model calibration."""
    return evaluate_decisions(request)
