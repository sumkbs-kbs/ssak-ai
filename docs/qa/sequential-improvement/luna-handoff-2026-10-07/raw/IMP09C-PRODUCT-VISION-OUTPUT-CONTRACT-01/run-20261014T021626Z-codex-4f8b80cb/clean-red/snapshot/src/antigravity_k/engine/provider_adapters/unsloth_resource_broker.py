from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol, assert_never

import psutil

from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    ReservationId,
    UnslothAdmissionCode,
    UnslothAdmissionDecision,
    UnslothAdmissionRequest,
    UnslothMemorySnapshot,
    UnslothReservation,
    UnslothReservationState,
    UnslothResourcePolicy,
    UnslothResourceStatus,
)
from antigravity_k.engine.provider_adapters.unsloth_resource_repository import (
    DeviceOccupancy,
    ExistingAdmission,
    PendingReservation,
    StoredAdmission,
    UnslothResourceRepository,
)


class UnslothMemoryProbe(Protocol):
    def snapshot(self) -> UnslothMemorySnapshot: ...


class SystemVirtualMemory(Protocol):
    @property
    def total(self) -> int: ...

    @property
    def available(self) -> int: ...


class SystemMemoryProvider(Protocol):
    def virtual_memory(self) -> SystemVirtualMemory: ...


SYSTEM_MEMORY_PROVIDER: Final[SystemMemoryProvider] = psutil


class SystemMemoryProbe:
    def snapshot(self) -> UnslothMemorySnapshot:
        memory = SYSTEM_MEMORY_PROVIDER.virtual_memory()
        return UnslothMemorySnapshot(total_bytes=memory.total, available_bytes=memory.available)


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    request: UnslothAdmissionRequest
    memory: UnslothMemorySnapshot
    required_headroom: int
    projected_available: int
    request_fingerprint: str
    provenance_fingerprint: str


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    code: UnslothAdmissionCode
    reservation_id: ReservationId | None = None
    reservation_state: UnslothReservationState | None = None
    resource_job_id: str | None = None
    replayed: bool = False


DEFAULT_RESOURCE_POLICY: Final = UnslothResourcePolicy()


class UnslothResourceBroker:
    def __init__(
        self,
        database_path: Path,
        memory_probe: UnslothMemoryProbe,
        policy: UnslothResourcePolicy = DEFAULT_RESOURCE_POLICY,
    ) -> None:
        self._repository: UnslothResourceRepository = UnslothResourceRepository(database_path)
        self._memory_probe: UnslothMemoryProbe = memory_probe
        self._policy: UnslothResourcePolicy = policy

    def admit(self, request: UnslothAdmissionRequest) -> UnslothAdmissionDecision:
        context = self._admission_context(request)
        with self._repository.admission() as transaction:
            inspection = transaction.inspect(request.idempotency_key, request.device_id)
            match inspection:
                case ExistingAdmission(stored=existing):
                    return self._existing_decision(existing, context)
                case DeviceOccupancy(active_count=active_count):
                    if active_count >= self._policy.max_active_per_device:
                        return self._decision(
                            context,
                            DecisionOutcome(code=UnslothAdmissionCode.DEVICE_BUSY),
                        )
                    if context.projected_available < context.required_headroom:
                        return self._decision(
                            context,
                            DecisionOutcome(code=UnslothAdmissionCode.INSUFFICIENT_MEMORY),
                        )

                    reservation_id = ReservationId(str(uuid.uuid4()))
                    transaction.insert(
                        PendingReservation(
                            reservation_id,
                            request.idempotency_key,
                            context.request_fingerprint,
                            request.operation,
                            request.device_id,
                            request.estimated_peak_bytes,
                            context.provenance_fingerprint,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                    return self._decision(
                        context,
                        DecisionOutcome(
                            code=UnslothAdmissionCode.ACCEPTED,
                            reservation_id=reservation_id,
                            reservation_state=UnslothReservationState.ACTIVE,
                        ),
                    )
            assert_never(inspection)

    def status(self) -> UnslothResourceStatus:
        return UnslothResourceStatus(
            memory=self._memory_probe.snapshot(),
            minimum_headroom_ratio=self._policy.minimum_headroom_ratio,
            max_active_per_device=self._policy.max_active_per_device,
            active_reservations=self._repository.list_active(),
        )

    def release(self, reservation_id: ReservationId) -> UnslothReservation | None:
        return self._repository.release(reservation_id, datetime.now(UTC).isoformat())

    def bind_job(self, reservation_id: ReservationId, resource_job_id: str) -> UnslothReservation | None:
        return self._repository.bind_job(reservation_id, resource_job_id)

    def _admission_context(self, request: UnslothAdmissionRequest) -> AdmissionContext:
        memory = self._memory_probe.snapshot()
        return AdmissionContext(
            request=request,
            memory=memory,
            required_headroom=math.ceil(
                memory.total_bytes * self._policy.minimum_headroom_ratio,
            ),
            projected_available=memory.available_bytes - request.estimated_peak_bytes,
            request_fingerprint=request.request_fingerprint(),
            provenance_fingerprint=request.artifact.fingerprint(),
        )

    def _existing_decision(
        self,
        existing: StoredAdmission,
        context: AdmissionContext,
    ) -> UnslothAdmissionDecision:
        if existing.request_fingerprint != context.request_fingerprint:
            return self._decision(
                context,
                DecisionOutcome(code=UnslothAdmissionCode.IDEMPOTENCY_CONFLICT),
            )
        match existing.state:
            case UnslothReservationState.ACTIVE:
                return self._decision(
                    context,
                    DecisionOutcome(
                        code=UnslothAdmissionCode.REPLAYED,
                        reservation_id=existing.reservation_id,
                        reservation_state=existing.state,
                        resource_job_id=existing.resource_job_id,
                        replayed=True,
                    ),
                )
            case UnslothReservationState.RELEASED:
                return self._decision(
                    context,
                    DecisionOutcome(
                        code=UnslothAdmissionCode.RESERVATION_RELEASED,
                        reservation_id=existing.reservation_id,
                        reservation_state=existing.state,
                        resource_job_id=existing.resource_job_id,
                        replayed=True,
                    ),
                )
        assert_never(existing.state)

    @staticmethod
    def _decision(
        context: AdmissionContext,
        outcome: DecisionOutcome,
    ) -> UnslothAdmissionDecision:
        match outcome.code:
            case UnslothAdmissionCode.ACCEPTED | UnslothAdmissionCode.REPLAYED:
                return UnslothResourceBroker._build_decision(context, outcome, allowed=True)
            case (
                UnslothAdmissionCode.DEVICE_BUSY
                | UnslothAdmissionCode.INSUFFICIENT_MEMORY
                | UnslothAdmissionCode.IDEMPOTENCY_CONFLICT
                | UnslothAdmissionCode.RESERVATION_RELEASED
            ):
                return UnslothResourceBroker._build_decision(context, outcome, allowed=False)
        assert_never(outcome.code)

    @staticmethod
    def _build_decision(
        context: AdmissionContext,
        outcome: DecisionOutcome,
        *,
        allowed: bool,
    ) -> UnslothAdmissionDecision:
        return UnslothAdmissionDecision(
            allowed=allowed,
            code=outcome.code,
            reservation_id=outcome.reservation_id,
            reservation_state=outcome.reservation_state,
            replayed=outcome.replayed,
            operation=context.request.operation,
            device_id=context.request.device_id,
            estimated_peak_bytes=context.request.estimated_peak_bytes,
            total_bytes=context.memory.total_bytes,
            available_bytes=context.memory.available_bytes,
            required_headroom_bytes=context.required_headroom,
            projected_available_bytes=context.projected_available,
            provenance_fingerprint=context.provenance_fingerprint,
            resource_job_id=outcome.resource_job_id,
        )
