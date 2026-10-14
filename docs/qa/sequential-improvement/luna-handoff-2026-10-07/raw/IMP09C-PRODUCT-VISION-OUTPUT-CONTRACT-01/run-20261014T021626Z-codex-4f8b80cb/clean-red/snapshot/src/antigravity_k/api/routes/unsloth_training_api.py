from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError

from antigravity_k.api.dependencies import get_tool_registry
from antigravity_k.api.routes.unsloth_studio_api import get_unsloth_resource_broker
from antigravity_k.engine.approval_manager import get_approval_manager
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.provider_adapters.unsloth_resource_broker import UnslothResourceBroker
from antigravity_k.engine.provider_adapters.unsloth_studio_contracts import (
    UnslothStudioConfigurationError,
    UnslothStudioSettings,
)
from antigravity_k.engine.provider_adapters.unsloth_training import UnslothTrainingService
from antigravity_k.engine.provider_adapters.unsloth_training_contracts import (
    UnslothTrainingLaunchState,
    UnslothTrainingStartOutcome,
    UnslothTrainingStartRequest,
)
from antigravity_k.tools.mcp_session_manager import MCPSessionManager
from antigravity_k.tools.tool_registry import ToolRegistry

router = APIRouter()


def get_unsloth_training_service(
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
    broker: Annotated[UnslothResourceBroker, Depends(get_unsloth_resource_broker)],
) -> UnslothTrainingService:
    try:
        settings = UnslothStudioSettings.from_env()
    except (UnslothStudioConfigurationError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsloth Studio MCP configuration is invalid.",
        ) from exc
    return UnslothTrainingService(
        settings=settings,
        manager=MCPSessionManager(),
        registry=registry,
        broker=broker,
        approvals=get_approval_manager(),
    )


@router.post(
    "/v1/integrations/unsloth/training/start",
    response_model=UnslothTrainingStartOutcome,
)
async def start_unsloth_training(
    request: UnslothTrainingStartRequest,
    response: Response,
    service: Annotated[UnslothTrainingService, Depends(get_unsloth_training_service)],
) -> UnslothTrainingStartOutcome:
    outcome = await service.launch(request)
    get_audit_logger().log_event(
        "unsloth_training_start",
        {
            "state": outcome.state.value,
            "approval_id": outcome.approval_id,
            "reservation_id": outcome.reservation_id,
            "resource_code": outcome.resource_code.value if outcome.resource_code else None,
            "resource_job_id": outcome.resource_job_id,
            "remote_status": outcome.remote_status,
        },
    )
    response.status_code = _status_code_for(outcome.state)
    return outcome


def _status_code_for(state: UnslothTrainingLaunchState) -> int:
    match state:
        case UnslothTrainingLaunchState.WRITE_DISABLED | UnslothTrainingLaunchState.POLICY_DENIED:
            return status.HTTP_403_FORBIDDEN
        case UnslothTrainingLaunchState.APPROVAL_REQUIRED | UnslothTrainingLaunchState.STARTED:
            return status.HTTP_202_ACCEPTED
        case UnslothTrainingLaunchState.APPROVAL_DENIED:
            return status.HTTP_403_FORBIDDEN
        case UnslothTrainingLaunchState.RESOURCE_DENIED:
            return status.HTTP_409_CONFLICT
        case UnslothTrainingLaunchState.IDEMPOTENT_REPLAY:
            return status.HTTP_200_OK
        case UnslothTrainingLaunchState.REMOTE_REJECTED:
            return status.HTTP_502_BAD_GATEWAY
        case UnslothTrainingLaunchState.UNCERTAIN:
            return status.HTTP_503_SERVICE_UNAVAILABLE
