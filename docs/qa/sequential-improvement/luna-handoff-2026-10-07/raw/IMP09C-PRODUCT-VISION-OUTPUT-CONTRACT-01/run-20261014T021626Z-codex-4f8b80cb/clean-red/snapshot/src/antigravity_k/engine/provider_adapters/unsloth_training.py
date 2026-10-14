from __future__ import annotations

from collections.abc import Mapping
from typing import assert_never, override

from pydantic import JsonValue

from antigravity_k.engine.approval_manager import ApprovalManager, ApprovalStatus
from antigravity_k.engine.provider_adapters.unsloth_resource_broker import UnslothResourceBroker
from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    ReservationId,
    UnslothAdmissionCode,
)
from antigravity_k.engine.provider_adapters.unsloth_studio_contracts import UnslothStudioSettings
from antigravity_k.engine.provider_adapters.unsloth_training_contracts import (
    UnslothTrainingLaunchState,
    UnslothTrainingStartOutcome,
    UnslothTrainingStartRequest,
)
from antigravity_k.engine.provider_adapters.unsloth_training_mcp import (
    RemoteTrainingRejected,
    RemoteTrainingStarted,
    RemoteTrainingUncertain,
    UnslothTrainingMCPClient,
)
from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from antigravity_k.tools.mcp_session_manager import MCPSessionManager
from antigravity_k.tools.tool_registry import ToolRegistry


class _StartTrainingDescriptor(BaseTool):
    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.BACKGROUND
    risk_level: RiskLevel = RiskLevel.CRITICAL
    tags: list[str] = ["unsloth", "studio", "mcp", "training", "mutating"]

    @property
    @override
    def name(self) -> str:
        return "start_training"

    @property
    @override
    def description(self) -> str:
        return "Start a resource-intensive local Unsloth training job."

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return {
            "type": "object",
            "properties": {"request_fingerprint": {"type": "string"}},
            "required": ["request_fingerprint"],
            "additionalProperties": False,
        }

    @override
    def execute(self, **kwargs: object) -> JsonValue:
        raise _DescriptorExecutionError(
            "Unsloth training descriptors cannot execute outside the guarded adapter.",
        )


class _DescriptorExecutionError(RuntimeError):
    pass


class UnslothTrainingService:
    def __init__(
        self,
        *,
        settings: UnslothStudioSettings,
        manager: MCPSessionManager,
        registry: ToolRegistry,
        broker: UnslothResourceBroker,
        approvals: ApprovalManager,
    ) -> None:
        self._settings: UnslothStudioSettings = settings
        self._manager: MCPSessionManager = manager
        self._registry: ToolRegistry = registry
        self._broker: UnslothResourceBroker = broker
        self._approvals: ApprovalManager = approvals
        self._remote: UnslothTrainingMCPClient = UnslothTrainingMCPClient(settings, manager)

    async def launch(self, request: UnslothTrainingStartRequest) -> UnslothTrainingStartOutcome:
        if not self._settings.write_tools_enabled:
            return self._outcome(UnslothTrainingLaunchState.WRITE_DISABLED)

        approval_arguments = {"request_fingerprint": request.request_fingerprint()}
        policy = self._registry.authorize_tool(
            _StartTrainingDescriptor(),
            approval_arguments,
            objective="Start an explicitly approved local Unsloth training job.",
        )
        if policy.is_denied:
            return self._outcome(UnslothTrainingLaunchState.POLICY_DENIED)

        approval_outcome = self._approval_outcome(request, approval_arguments)
        if approval_outcome is not None:
            return approval_outcome

        admission = self._broker.admit(request.admission)
        if not admission.allowed or admission.reservation_id is None:
            return self._outcome(
                UnslothTrainingLaunchState.RESOURCE_DENIED,
                resource_code=admission.code,
            )
        match admission.code:
            case UnslothAdmissionCode.ACCEPTED:
                launch_state = UnslothTrainingLaunchState.STARTED
            case UnslothAdmissionCode.REPLAYED:
                launch_state = UnslothTrainingLaunchState.IDEMPOTENT_REPLAY
                if admission.resource_job_id is not None:
                    return self._outcome(
                        launch_state,
                        reservation_id=admission.reservation_id,
                        resource_code=admission.code,
                        resource_job_id=admission.resource_job_id,
                        remote_status="queued",
                    )
            case (
                UnslothAdmissionCode.DEVICE_BUSY
                | UnslothAdmissionCode.INSUFFICIENT_MEMORY
                | UnslothAdmissionCode.IDEMPOTENCY_CONFLICT
                | UnslothAdmissionCode.RESERVATION_RELEASED
            ):
                raise _UnexpectedAdmissionError(admission.code.value)
            case _:
                assert_never(admission.code)

        remote = await self._remote.start(request.mcp_config())
        match remote:
            case RemoteTrainingStarted(job=job):
                reservation = self._broker.bind_job(ReservationId(admission.reservation_id), job.job_id)
                if reservation is None:
                    return self._outcome(
                        UnslothTrainingLaunchState.UNCERTAIN,
                        reservation_id=admission.reservation_id,
                        resource_code=admission.code,
                        resource_job_id=job.job_id,
                        remote_status=job.status,
                    )
                return self._outcome(
                    launch_state,
                    reservation_id=admission.reservation_id,
                    resource_code=admission.code,
                    resource_job_id=job.job_id,
                    remote_status=job.status,
                )
            case RemoteTrainingRejected():
                _ = self._broker.release(ReservationId(admission.reservation_id))
                return self._outcome(
                    UnslothTrainingLaunchState.REMOTE_REJECTED,
                    reservation_id=admission.reservation_id,
                    resource_code=admission.code,
                )
            case RemoteTrainingUncertain():
                return self._outcome(
                    UnslothTrainingLaunchState.UNCERTAIN,
                    reservation_id=admission.reservation_id,
                    resource_code=admission.code,
                )
            case _:
                assert_never(remote)

    def _approval_outcome(
        self,
        request: UnslothTrainingStartRequest,
        approval_arguments: Mapping[str, str],
    ) -> UnslothTrainingStartOutcome | None:
        if request.approval_id is None:
            approval_request = self._approvals.request_approval(
                tool_name="start_training",
                tool_args=dict(approval_arguments),
                risk_level=RiskLevel.CRITICAL.value,
                description="Start a local Unsloth LoRA/QLoRA training job.",
            )
            match approval_request.status:
                case ApprovalStatus.PENDING:
                    return self._outcome(
                        UnslothTrainingLaunchState.APPROVAL_REQUIRED,
                        approval_id=approval_request.request_id,
                    )
                case (
                    ApprovalStatus.APPROVED
                    | ApprovalStatus.DENIED
                    | ApprovalStatus.TIMEOUT
                    | ApprovalStatus.ALWAYS_ALLOW
                ):
                    return self._outcome(UnslothTrainingLaunchState.APPROVAL_DENIED)
                case _:
                    assert_never(approval_request.status)

        stored_approval = self._approvals.get_request(request.approval_id)
        if (
            stored_approval is None
            or stored_approval.tool_name != "start_training"
            or stored_approval.tool_args != approval_arguments
        ):
            return self._outcome(UnslothTrainingLaunchState.APPROVAL_DENIED)
        match stored_approval.status:
            case ApprovalStatus.PENDING:
                return self._outcome(
                    UnslothTrainingLaunchState.APPROVAL_REQUIRED,
                    approval_id=stored_approval.request_id,
                )
            case ApprovalStatus.APPROVED:
                return None
            case ApprovalStatus.DENIED | ApprovalStatus.TIMEOUT | ApprovalStatus.ALWAYS_ALLOW:
                return self._outcome(UnslothTrainingLaunchState.APPROVAL_DENIED)
            case _:
                assert_never(stored_approval.status)

    def _outcome(
        self,
        state: UnslothTrainingLaunchState,
        *,
        approval_id: str | None = None,
        reservation_id: str | None = None,
        resource_code: UnslothAdmissionCode | None = None,
        resource_job_id: str | None = None,
        remote_status: str | None = None,
    ) -> UnslothTrainingStartOutcome:
        return UnslothTrainingStartOutcome(
            state=state,
            write_tools_enabled=self._settings.write_tools_enabled,
            approval_id=approval_id,
            reservation_id=reservation_id,
            resource_code=resource_code,
            resource_job_id=resource_job_id,
            remote_status=remote_status,
        )


class _UnexpectedAdmissionError(RuntimeError):
    pass
