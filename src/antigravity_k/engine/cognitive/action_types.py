"""Action intent, receipt and executor boundary values."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.governance import (
    GovernanceOutcome,
    ReshapeGuard,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    AuthorityDimension,
    ExecutionReceiptPayload,
    ObservationStatus,
    Producer,
    ReceiptStatus,
    Record,
    RiskProfile,
)
from antigravity_k.engine.cognitive.readiness import (
    FreshnessBinding,
    GuardReceipt,
    ReadinessResult,
)
from antigravity_k.engine.cognitive.references import REL_ACTION, EntityType, Reference, new_id


class ActionRefusal(StrEnum):
    """dispatch를 거부한 이유. 거부는 receipt가 아니라 사유로 남는다."""

    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    POLICY_CLEARANCE_MISSING = "POLICY_CLEARANCE_MISSING"
    COST_EXCEEDS_CLEARANCE = "COST_EXCEEDS_CLEARANCE"
    STALE_READINESS = "STALE_READINESS"
    GUARD_RECEIPTS_MISSING = "GUARD_RECEIPTS_MISSING"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    UNRESOLVED_UNKNOWN = "UNRESOLVED_UNKNOWN"
    NON_IDEMPOTENT_REDISPATCH = "NON_IDEMPOTENT_REDISPATCH"
    NO_DISPATCH_PORT = "NO_DISPATCH_PORT"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    PROJECT_MISMATCH = "PROJECT_MISMATCH"
    STALE_RECEIPT_REVISION = "STALE_RECEIPT_REVISION"
    MALFORMED_OBSERVATION = "MALFORMED_OBSERVATION"
    PROJECTION_SETTLED = "PROJECTION_SETTLED"


class ActionDispatchError(RuntimeError):
    """계약상 호출할 수 없는 동작(예: 이미 dispatch된 action에 대한 cancel)."""


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """executor가 돌려주는 dispatch 결과. 이 시점의 effect는 아직 관측되지 않았다."""

    accepted: bool
    external_ref: str = ""
    detail: str = ""


@runtime_checkable
class ToolDispatchPort(Protocol):
    """기존 executor 표면 adapter가 만족해야 하는 최소 계약."""

    def dispatch(self, tool: str, arguments: Mapping[str, object], *, action_id: str) -> DispatchOutcome: ...


@dataclass(frozen=True, slots=True)
class CallablePort:
    """임의 callable을 port로 감싼다(시험·shadow 경로용)."""

    call: Callable[[str, Mapping[str, object], str], object]

    def dispatch(self, tool: str, arguments: Mapping[str, object], *, action_id: str) -> DispatchOutcome:
        result = self.call(tool, arguments, action_id)
        if isinstance(result, DispatchOutcome):
            return result
        return DispatchOutcome(accepted=True, detail=str(result))


@dataclass(frozen=True, slots=True)
class ToolExecutorPort:
    """기존 ``ToolExecutor`` 표면 adapter.

    ToolExecutor는 문자열 결과를 돌려주므로 실패 판정 predicate를 주입받는다
    (예: ``antigravity_k.engine.tool_executor.result_indicates_failure``).
    """

    executor: object
    failure_predicate: Callable[[object], bool]
    detail_limit: int = 200

    def dispatch(self, tool: str, arguments: Mapping[str, object], *, action_id: str) -> DispatchOutcome:
        _ = action_id
        execute = getattr(self.executor, "execute")
        result = execute(tool, dict(arguments))
        failed = bool(self.failure_predicate(result))
        return DispatchOutcome(
            accepted=not failed,
            external_ref=f"tool_executor:{tool}",
            detail=str(result)[: self.detail_limit],
        )


@dataclass(frozen=True, slots=True)
class PolicyClearance:
    """P05 governance/public authority 판정에서 ACTION으로 넘어오는 실행 허가."""

    authority: AuthorityDecision | None = None
    network_allowed: bool = False
    cost_ceiling_usd: float = 0.0
    private_data_allowed: bool = False
    revision: int | None = None
    source_request_id: str = ""

    @property
    def granted(self) -> bool:
        return self.authority is not None and self.authority.allowed

    @classmethod
    def from_governance(
        cls,
        outcome: GovernanceOutcome,
        *,
        network_allowed: bool = False,
        cost_ceiling_usd: float = 0.0,
        private_data_allowed: bool = False,
    ) -> PolicyClearance:
        """governance가 실행을 허용한 결과만 clearance로 인정한다."""

        authority = outcome.authority if outcome.admits_execution else None
        return cls(
            authority=authority,
            network_allowed=network_allowed and authority is not None and authority.allowed,
            cost_ceiling_usd=cost_ceiling_usd,
            private_data_allowed=private_data_allowed and authority is not None and authority.allowed,
            revision=authority.profile_revision if authority is not None else None,
            source_request_id=outcome.request_id,
        )


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """실행 의도. 의미적 정답 field는 없고 구조·권한·receipt 정보만 담는다."""

    action_id: str
    submission_id: str
    action_key: str
    tool: str
    operation: str = "execute_tool"
    arguments: Mapping[str, object] = field(default_factory=dict)
    scope: str = ""
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE
    risk: RiskProfile = field(default_factory=RiskProfile)
    reversible: bool = True
    idempotent: bool = True
    guards: tuple[ReshapeGuard, ...] = ()
    guard_receipts: tuple[GuardReceipt, ...] = ()
    readiness: ReadinessResult | None = None
    clearance: PolicyClearance | None = None
    decision_revision: int = 1
    state_revision: int = 1
    authority_revision: int | None = None
    policy_version: str | None = None
    network_access: bool = False
    cost_usd: float = 0.0
    private_data: bool = False

    def args_digest(self) -> str:
        payload = {
            "tool": self.tool,
            "operation": self.operation,
            "scope": self.scope,
            "arguments": dict(self.arguments),
        }
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
        )

    def freshness(self) -> FreshnessBinding:
        return FreshnessBinding(
            decision_revision=self.decision_revision,
            action_digest=self.args_digest(),
            state_revision=self.state_revision,
            authority_revision=self.authority_revision,
            policy_version=self.policy_version,
        )

    def required_guards(self) -> tuple[ReshapeGuard, ...]:
        guards = list(self.guards)
        if self.readiness is not None:
            guards.extend(receipt.guard for receipt in self.readiness.guards)
        return tuple(dict.fromkeys(guards))


@dataclass(frozen=True, slots=True)
class ActionObservation:
    """ACTION 이후의 관측. 관측 없이 성공을 선언하지 않는다."""

    observed: bool
    succeeded: bool | None = None
    external_ref: str = ""
    detail: str = ""
    status: ObservationStatus = ObservationStatus.COMPLETE

    def __post_init__(self) -> None:
        if not self.observed and self.succeeded is not None:
            raise ValueError("unobserved ActionObservation cannot declare succeeded")


def new_receipt_id() -> str:
    """Stable ExecutionReceipt ID used as both receipt_id and committed record id."""

    return new_id(EntityType.EXECUTION_RECEIPT)


@dataclass(frozen=True, slots=True)
class ActionReceipt:
    receipt_id: str
    action_id: str
    action_key: str
    submission_id: str
    dispatch_attempt: int
    status: ReceiptStatus
    started_at: datetime
    finished_at: datetime | None = None
    external_ref: str | None = None
    effects_observed: bool | None = None
    reconciliation: str = ""
    detail: str = ""

    @property
    def settled(self) -> bool:
        return self.status in (ReceiptStatus.COMPLETED, ReceiptStatus.FAILED, ReceiptStatus.CANCELLED)

    def to_record(
        self,
        *,
        project_id: str,
        producer: Producer,
        created_at: datetime,
        references: tuple[Reference, ...] = (),
    ) -> Record:
        """Canonical receipt ID equals ``receipt_id`` so evaluation refs resolve after restart."""
        action_ref = Reference(
            relation=REL_ACTION,
            target_id=self.action_id,
            expected_type=EntityType.ACTION,
        )
        extra = tuple(ref for ref in references if not (ref.relation == REL_ACTION and ref.target_id == self.action_id))
        merged = (action_ref, *extra)
        return Record.create(
            entity_type=EntityType.EXECUTION_RECEIPT,
            record_id=self.receipt_id,
            project_id=project_id,
            producer=producer,
            references=merged,
            payload=ExecutionReceiptPayload(
                action_id=self.action_id,
                idempotency_key=self.action_key,
                dispatch_attempt=self.dispatch_attempt,
                started_at=self.started_at,
                finished_at=self.finished_at,
                external_ref=self.external_ref,
                status=self.status,
                effects_observed=self.effects_observed,
                reconciliation=self.reconciliation,
            ),
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ActionRun:
    intent: ActionIntent
    status: ActionExecutionStatus
    receipt: ActionReceipt | None = None
    refusal: ActionRefusal | None = None
    reason: str = ""
    reconciliation_required: bool = False
    cancellation_requested: bool = False
    cancellation_note: str = ""
    records: tuple[Record, ...] = ()

    @property
    def refused(self) -> bool:
        return self.refusal is not None

    @property
    def effect_possible(self) -> bool:
        """effect가 발생했을 가능성이 있는가. UNKNOWN은 '없음'이 아니다."""

        return (self.receipt is not None and self.receipt.effects_observed is True) or self.status in (
            ActionExecutionStatus.DISPATCHED,
            ActionExecutionStatus.UNKNOWN,
        )


@dataclass(frozen=True, slots=True)
class ObservationSubmission:
    """Authenticated recovery observation. Never redispatches."""

    project_id: str
    action_key: str
    expected_receipt_id: str
    observation: ActionObservation
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Outcome of a recovery observation (append or idempotent replay)."""

    accepted: bool
    refusal: ActionRefusal | None = None
    reason: str = ""
    receipt_id: str | None = None
    observation_record_id: str | None = None
    projection_revision: int = 0
    records: tuple[Record, ...] = ()
    redispatched: bool = False
