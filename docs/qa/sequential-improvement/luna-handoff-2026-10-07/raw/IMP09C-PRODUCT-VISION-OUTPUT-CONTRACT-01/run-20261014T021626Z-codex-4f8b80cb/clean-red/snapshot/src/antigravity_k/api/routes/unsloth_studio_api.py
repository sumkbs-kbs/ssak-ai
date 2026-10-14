from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from antigravity_k.api.dependencies import get_tool_registry
from antigravity_k.config import config
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.provider_adapters.unsloth_capability_contracts import (
    UnslothCapabilitySnapshot,
)
from antigravity_k.engine.provider_adapters.unsloth_capability_preflight import (
    SystemCapabilityProbe,
    UnslothCapabilityPreflight,
)
from antigravity_k.engine.provider_adapters.unsloth_resource_broker import (
    SystemMemoryProbe,
    UnslothResourceBroker,
)
from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    ReservationId,
    UnslothAdmissionDecision,
    UnslothAdmissionRequest,
    UnslothReservation,
    UnslothResourceStatus,
)
from antigravity_k.engine.provider_adapters.unsloth_studio import UnslothStudioService
from antigravity_k.engine.provider_adapters.unsloth_studio_contracts import (
    UnslothStudioPermissionDenied,
    UnslothStudioSettings,
    UnslothStudioSnapshot,
)
from antigravity_k.tools.mcp_session_manager import MCPSessionManager
from antigravity_k.tools.tool_registry import ToolRegistry

router = APIRouter()


def get_unsloth_resource_broker() -> UnslothResourceBroker:
    return UnslothResourceBroker(
        database_path=config.paths.data_dir / "unsloth_resources.sqlite3",
        memory_probe=SystemMemoryProbe(),
    )


def get_unsloth_capability_preflight() -> UnslothCapabilityPreflight:
    return UnslothCapabilityPreflight(SystemCapabilityProbe(config.paths.data_dir))


@router.get(
    "/v1/integrations/unsloth/capabilities",
    response_model=UnslothCapabilitySnapshot,
)
def get_unsloth_capabilities(
    preflight: Annotated[UnslothCapabilityPreflight, Depends(get_unsloth_capability_preflight)],
) -> UnslothCapabilitySnapshot:
    return preflight.snapshot()


def get_unsloth_studio_service(
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> UnslothStudioService:
    try:
        settings = UnslothStudioSettings.from_env()
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsloth Studio MCP configuration is invalid.",
        ) from exc
    return UnslothStudioService(settings=settings, manager=MCPSessionManager(), registry=registry)


@router.get(
    "/v1/integrations/unsloth/studio",
    response_model=UnslothStudioSnapshot,
)
async def get_unsloth_studio_snapshot(
    service: Annotated[UnslothStudioService, Depends(get_unsloth_studio_service)],
) -> UnslothStudioSnapshot:
    try:
        snapshot = await service.snapshot()
    except UnslothStudioPermissionDenied as exc:
        get_audit_logger().log_event(
            "unsloth_studio_read_denied",
            {"tool": exc.tool.value, "source": exc.source},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsloth Studio read access was denied by policy.",
        ) from exc

    get_audit_logger().log_event(
        "unsloth_studio_read",
        {
            "configured": snapshot.configured,
            "available": snapshot.available,
            "tools": [result.tool.value for result in snapshot.results if result.ok],
        },
    )
    return snapshot


@router.post(
    "/v1/integrations/unsloth/resources/admissions",
    response_model=UnslothAdmissionDecision,
)
def admit_unsloth_resource(
    request: UnslothAdmissionRequest,
    broker: Annotated[UnslothResourceBroker, Depends(get_unsloth_resource_broker)],
) -> UnslothAdmissionDecision:
    decision = broker.admit(request)
    get_audit_logger().log_event(
        "unsloth_resource_admission",
        {
            "operation": decision.operation.value,
            "device_id": decision.device_id,
            "code": decision.code.value,
            "reservation_id": decision.reservation_id,
            "provenance_fingerprint": decision.provenance_fingerprint,
        },
    )
    return decision


@router.get(
    "/v1/integrations/unsloth/resources",
    response_model=UnslothResourceStatus,
)
def get_unsloth_resource_status(
    broker: Annotated[UnslothResourceBroker, Depends(get_unsloth_resource_broker)],
) -> UnslothResourceStatus:
    return broker.status()


@router.post(
    "/v1/integrations/unsloth/resources/reservations/{reservation_id}/release",
    response_model=UnslothReservation,
)
def release_unsloth_resource(
    reservation_id: str,
    broker: Annotated[UnslothResourceBroker, Depends(get_unsloth_resource_broker)],
) -> UnslothReservation:
    reservation = broker.release(ReservationId(reservation_id))
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsloth resource reservation was not found.",
        )
    get_audit_logger().log_event(
        "unsloth_resource_release",
        {
            "reservation_id": reservation.reservation_id,
            "operation": reservation.operation.value,
            "device_id": reservation.device_id,
            "state": reservation.state.value,
        },
    )
    return reservation
