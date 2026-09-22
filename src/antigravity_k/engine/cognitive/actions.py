"""Action dispatch (P07) — intent → 권한 freshness → executor → receipt → 관찰.

COGNITIVE_OPERATING_LOOP.md와 IMPLEMENTATION_ROADMAP.md P07 계약을 구현한다.

- 순서는 ``persist intent → 권한 freshness → 기존 executor → receipt → 관찰``이다.
- **제출 idempotency(submission_id)와 action idempotency(action_key)를 분리한다.**
  같은 action key로 두 번 제출해도 중복 effect는 0이다.
- effect 발생 후 crash·취소·timeout은 ``UNKNOWN``이며 성공으로 승격하지 않는다. 관측으로만 확정한다.
- 비idempotent 도구의 재dispatch는 금지한다.
- 읽기 도구도 network/cost/privacy 측면에서는 행동이므로 권한 검사를 생략하지 않는다.
- 이미 발생한 action은 receipt로 복구하며 자동 삭제·취소 선언을 하지 않는다.
- opt-in이다. dispatch port가 없으면 아무 것도 실행하지 않는다(기본 off).

이 모듈은 provider/UI/저장소를 import하지 않는다. executor는 protocol로 주입되고, 기록은
``record_sink``가 받는다(P08/P11이 store에 연결).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.governance import (
    GovernanceOutcome,
    ReshapeGuard,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    ActionPayload,
    AuthorityDimension,
    ExecutionReceiptPayload,
    ObservationStatus,
    Producer,
    ReceiptStatus,
    Record,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.readiness import (
    FreshnessBinding,
    GuardReceipt,
    ReadinessGate,
    ReadinessResult,
    StaleReadinessError,
)
from antigravity_k.engine.cognitive.references import EntityType


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

    def to_record(self, *, project_id: str, producer: Producer, created_at: datetime) -> Record:
        return Record.create(
            entity_type=EntityType.EXECUTION_RECEIPT,
            project_id=project_id,
            producer=producer,
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

        return self.status in (ActionExecutionStatus.DISPATCHED, ActionExecutionStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ActionDispatcher:
    """intent→권한→executor→receipt 순서를 강제하는 dispatcher.

    ``port``가 없으면 아무 것도 실행하지 않는다(feature off). ``record_sink``는 canonical
    store adapter이며, 없으면 기록은 dispatcher 내부에만 남는다.
    """

    port: ToolDispatchPort | None = None
    record_sink: Callable[[Sequence[Record]], object] | None = None
    clock: Callable[[], datetime] | None = None
    _receipts: dict[str, ActionReceipt] = field(default_factory=dict, repr=False)
    _attempts: dict[str, int] = field(default_factory=dict, repr=False)
    _submissions: dict[str, str] = field(default_factory=dict, repr=False)
    _records: list[Record] = field(default_factory=list, repr=False)

    # ── 조회 ────────────────────────────────────────────
    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    def receipt_for(self, action_key: str) -> ActionReceipt | None:
        return self._receipts.get(action_key)

    def submission_target(self, submission_id: str) -> str | None:
        return self._submissions.get(submission_id)

    def pending_reconciliation(self) -> tuple[ActionReceipt, ...]:
        """crash·timeout 뒤 결과가 확정되지 않은 receipt. 재dispatch 전에 관측을 우선한다."""

        return tuple(
            receipt
            for receipt in self._receipts.values()
            if same_enum(receipt.status, ReceiptStatus.UNKNOWN)
            or (same_enum(receipt.status, ReceiptStatus.DISPATCHED) and receipt.effects_observed is None)
        )

    # ── 계획 ────────────────────────────────────────────
    def plan(self, intent: ActionIntent, *, project_id: str, producer: Producer) -> tuple[Record, ActionRun]:
        """dispatch 전에 intent를 canonical Action record로 남긴다."""

        record = Record.create(
            entity_type=EntityType.ACTION,
            project_id=project_id,
            producer=producer,
            payload=ActionPayload(
                tool=intent.tool,
                args_digest=intent.args_digest(),
                scope=intent.scope or intent.tool,
                risk_profile=intent.risk,
                idempotency_key=intent.action_key,
                execution_status=ActionExecutionStatus.PLANNED,
                guards=tuple(guard.value for guard in intent.required_guards()),
            ),
            created_at=self._now(),
        )
        run = ActionRun(
            intent=intent,
            status=ActionExecutionStatus.PLANNED,
            records=(record,),
        )
        self._persist(run.records)
        return record, run

    # ── 실행 ────────────────────────────────────────────
    def execute(
        self,
        intent: ActionIntent,
        *,
        project_id: str,
        producer: Producer,
        retry_authorized: bool = False,
        now: datetime | None = None,
    ) -> ActionRun:
        """정해진 순서로 dispatch한다. 거부는 receipt를 만들지 않는다."""

        refusal = self._preconditions(intent, retry_authorized=retry_authorized)
        if refusal is not None:
            return refusal

        started = now if now is not None else self._now()
        self._attempts[intent.action_key] = self._attempts.get(intent.action_key, 0) + 1
        attempt = self._attempts[intent.action_key]
        self._submissions[intent.submission_id] = intent.action_key

        action_record = self._action_record(intent, project_id, producer, started)
        port = self.port
        if port is None:  # _preconditions가 이미 막는다 — 여기서는 타입을 좁히는 재확인이다
            return self._refuse(intent, ActionRefusal.NO_DISPATCH_PORT, "dispatch 경로가 연결되지 않았다(feature off)")
        try:
            outcome = port.dispatch(intent.tool, intent.arguments, action_id=intent.action_id)
        except Exception as exc:  # executor가 결과를 돌려주지 못한 경우
            receipt = ActionReceipt(
                receipt_id=f"receipt:{intent.action_key}:{attempt}",
                action_id=intent.action_id,
                action_key=intent.action_key,
                submission_id=intent.submission_id,
                dispatch_attempt=attempt,
                status=ReceiptStatus.UNKNOWN,
                started_at=started,
                finished_at=started,
                effects_observed=None,
                reconciliation=f"결과 불명({type(exc).__name__}) — 외부 관측으로만 확정한다",
                detail=str(exc),
            )
            return self._finish(
                intent,
                ActionExecutionStatus.UNKNOWN,
                receipt,
                action_record,
                project_id,
                producer,
                reconciliation_required=True,
            )

        if outcome.accepted:
            receipt = ActionReceipt(
                receipt_id=f"receipt:{intent.action_key}:{attempt}",
                action_id=intent.action_id,
                action_key=intent.action_key,
                submission_id=intent.submission_id,
                dispatch_attempt=attempt,
                status=ReceiptStatus.DISPATCHED,
                started_at=started,
                external_ref=outcome.external_ref or None,
                effects_observed=None,
                reconciliation="dispatch 수락 — effect는 OBSERVE 단계에서 관측한다",
                detail=outcome.detail,
            )
            return self._finish(
                intent,
                ActionExecutionStatus.DISPATCHED,
                receipt,
                action_record,
                project_id,
                producer,
                reconciliation_required=True,
            )

        receipt = ActionReceipt(
            receipt_id=f"receipt:{intent.action_key}:{attempt}",
            action_id=intent.action_id,
            action_key=intent.action_key,
            submission_id=intent.submission_id,
            dispatch_attempt=attempt,
            status=ReceiptStatus.FAILED,
            started_at=started,
            finished_at=started,
            external_ref=outcome.external_ref or None,
            effects_observed=False,
            reconciliation="executor가 수락하지 않았다 — effect 없음으로 판정",
            detail=outcome.detail,
        )
        return self._finish(intent, ActionExecutionStatus.FAILED, receipt, action_record, project_id, producer)

    # ── 관측·조정 ───────────────────────────────────────
    def reconcile(
        self,
        run: ActionRun,
        observation: ActionObservation,
        *,
        project_id: str,
        producer: Producer,
        now: datetime | None = None,
    ) -> ActionRun:
        """UNKNOWN/DISPATCHED receipt를 관측으로 확정한다. 관측 없이는 성공이 없다."""

        if run.receipt is None:
            raise ActionDispatchError("receipt 없는 run은 조정할 수 없다")
        moment = now if now is not None else self._now()
        receipt = run.receipt
        if not observation.observed:
            updated = replace(
                receipt,
                status=ReceiptStatus.UNKNOWN,
                finished_at=moment,
                effects_observed=None,
                reconciliation="관측 실패 — 결과 불명을 유지한다(성공으로 승격하지 않는다)",
                detail=observation.detail or receipt.detail,
            )
            status = ActionExecutionStatus.UNKNOWN
        elif observation.succeeded is True:
            updated = replace(
                receipt,
                status=ReceiptStatus.COMPLETED,
                finished_at=moment,
                external_ref=observation.external_ref or receipt.external_ref,
                effects_observed=True,
                reconciliation="외부 관측으로 성공을 확인했다",
                detail=observation.detail or receipt.detail,
            )
            status = ActionExecutionStatus.SUCCEEDED
        elif observation.succeeded is False:
            updated = replace(
                receipt,
                status=ReceiptStatus.FAILED,
                finished_at=moment,
                external_ref=observation.external_ref or receipt.external_ref,
                effects_observed=True,
                reconciliation="effect는 관측됐지만 실패로 확인됐다",
                detail=observation.detail or receipt.detail,
            )
            status = ActionExecutionStatus.FAILED
        else:
            updated = replace(
                receipt,
                status=ReceiptStatus.UNKNOWN,
                finished_at=moment,
                effects_observed=None,
                reconciliation="관측했으나 성공/실패가 확정되지 않았다",
                detail=observation.detail or receipt.detail,
            )
            status = ActionExecutionStatus.UNKNOWN

        record = updated.to_record(project_id=project_id, producer=producer, created_at=moment)
        self._receipts[receipt.action_key] = updated
        self._persist((record,))
        return replace(
            run,
            status=status,
            receipt=updated,
            reconciliation_required=same_enum(status, ActionExecutionStatus.UNKNOWN),
            records=(*run.records, record),
        )

    # ── 취소 ────────────────────────────────────────────
    def cancel(
        self,
        run: ActionRun,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> ActionRun:
        """dispatch 전에는 취소로 끝낼 수 있다. 이미 나간 action은 되돌린 것으로 주장하지 않는다."""

        moment = now if now is not None else self._now()
        if run.receipt is None or not run.effect_possible:
            cancelled = ActionReceipt(
                receipt_id=f"receipt:cancel:{run.intent.action_key}",
                action_id=run.intent.action_id,
                action_key=run.intent.action_key,
                submission_id=run.intent.submission_id,
                dispatch_attempt=self._attempts.get(run.intent.action_key, 0),
                status=ReceiptStatus.CANCELLED,
                started_at=moment,
                finished_at=moment,
                effects_observed=False,
                reconciliation=f"dispatch 전 취소: {reason}",
            )
            self._receipts[run.intent.action_key] = cancelled
            return replace(
                run,
                status=ActionExecutionStatus.CANCELLED,
                receipt=cancelled,
                cancellation_requested=True,
                cancellation_note="dispatch 전 취소 — 외부 effect 없음",
                reconciliation_required=False,
            )

        note = (
            f"취소 요청만 기록한다({reason}). 이미 발생한 행동의 되돌림은 주장하지 않으며 외부 관측으로 조정해야 한다."
        )
        if claims_reversal(note):  # pragma: no cover — 방어적 검사
            raise ActionDispatchError("취소 문구가 되돌림을 주장한다")
        updated = replace(run.receipt, reconciliation=f"{run.receipt.reconciliation} / {note}")
        self._receipts[run.intent.action_key] = updated
        return replace(
            run,
            receipt=updated,
            cancellation_requested=True,
            cancellation_note=note,
            reconciliation_required=True,
        )

    # ── 내부 ────────────────────────────────────────────
    def _now(self) -> datetime:
        if self.clock is not None:
            return self.clock()
        return datetime.now(UTC)

    def _preconditions(self, intent: ActionIntent, *, retry_authorized: bool) -> ActionRun | None:
        clearance = intent.clearance
        if clearance is None or not clearance.granted:
            verdict = (
                clearance.authority.verdict.value if clearance is not None and clearance.authority else "NO_CLEARANCE"
            )
            return self._refuse(intent, ActionRefusal.NOT_AUTHORIZED, f"실행 허가가 없다: {verdict}")
        authority = clearance.authority
        if authority is not None and authority.dimension is not intent.dimension:
            return self._refuse(
                intent,
                ActionRefusal.DIMENSION_MISMATCH,
                f"허가 dimension {authority.dimension.value}과 요청 {intent.dimension.value}이 다르다",
            )
        if intent.network_access and not clearance.network_allowed:
            return self._refuse(intent, ActionRefusal.POLICY_CLEARANCE_MISSING, "network 접근 허가가 없다")
        if intent.private_data and not clearance.private_data_allowed:
            return self._refuse(intent, ActionRefusal.POLICY_CLEARANCE_MISSING, "private data 접근 허가가 없다")
        if intent.cost_usd > clearance.cost_ceiling_usd:
            return self._refuse(
                intent,
                ActionRefusal.COST_EXCEEDS_CLEARANCE,
                f"비용 {intent.cost_usd}이 clearance ceiling {clearance.cost_ceiling_usd}을 넘는다",
            )

        readiness = intent.readiness
        if readiness is None:
            return self._refuse(intent, ActionRefusal.STALE_READINESS, "readiness 없이 ACTION할 수 없다")
        if not readiness.ok:
            return self._refuse(
                intent,
                ActionRefusal.STALE_READINESS,
                f"readiness {readiness.verdict.value}: {list(readiness.blocking_conditions)}",
            )
        try:
            ReadinessGate().assert_fresh(readiness, intent.freshness())
        except StaleReadinessError as exc:
            return self._refuse(intent, ActionRefusal.STALE_READINESS, str(exc))
        if authority is not None and authority.profile_revision != (
            intent.authority_revision or authority.profile_revision
        ):
            return self._refuse(intent, ActionRefusal.STALE_READINESS, "authority revision이 판정 시점과 다르다")

        satisfied = {receipt.guard for receipt in intent.guard_receipts if receipt.accepted}
        missing = [guard.value for guard in intent.required_guards() if guard not in satisfied]
        if missing:
            return self._refuse(
                intent,
                ActionRefusal.GUARD_RECEIPTS_MISSING,
                f"guard receipt가 없는 의무: {missing}",
            )

        if self.port is None:
            return self._refuse(intent, ActionRefusal.NO_DISPATCH_PORT, "dispatch 경로가 연결되지 않았다(feature off)")

        existing = self._receipts.get(intent.action_key)
        if existing is not None:
            if existing.status in (ReceiptStatus.DISPATCHED, ReceiptStatus.COMPLETED, ReceiptStatus.CANCELLED):
                same_submission = existing.submission_id == intent.submission_id
                detail = (
                    "같은 submission이 이미 처리됐다"
                    if same_submission
                    else "같은 action key가 이미 실행됐다 — 중복 effect를 만들지 않는다"
                )
                return self._refuse(intent, ActionRefusal.DUPLICATE_ACTION, detail, receipt=existing)
            if same_enum(existing.status, ReceiptStatus.UNKNOWN):
                if not retry_authorized:
                    return self._refuse(
                        intent,
                        ActionRefusal.UNRESOLVED_UNKNOWN,
                        "이전 시도 결과가 UNKNOWN이다 — reconciliation을 먼저 수행한다",
                        receipt=existing,
                    )
                if not intent.idempotent:
                    return self._refuse(
                        intent,
                        ActionRefusal.NON_IDEMPOTENT_REDISPATCH,
                        "non-idempotent action을 재dispatch할 수 없다",
                        receipt=existing,
                    )
            if same_enum(existing.status, ReceiptStatus.FAILED) and existing.effects_observed is None:
                return self._refuse(
                    intent,
                    ActionRefusal.UNRESOLVED_UNKNOWN,
                    "이전 실패의 effect 발생 여부가 확인되지 않았다",
                    receipt=existing,
                )
        return None

    def _refuse(
        self, intent: ActionIntent, refusal: ActionRefusal, reason: str, *, receipt: ActionReceipt | None = None
    ) -> ActionRun:
        return ActionRun(
            intent=intent,
            status=ActionExecutionStatus.BLOCKED,
            receipt=receipt,
            refusal=refusal,
            reason=reason,
        )

    def _action_record(self, intent: ActionIntent, project_id: str, producer: Producer, created_at: datetime) -> Record:
        return Record.create(
            entity_type=EntityType.ACTION,
            project_id=project_id,
            producer=producer,
            payload=ActionPayload(
                tool=intent.tool,
                args_digest=intent.args_digest(),
                scope=intent.scope or intent.tool,
                risk_profile=intent.risk,
                idempotency_key=intent.action_key,
                execution_status=ActionExecutionStatus.AUTHORIZED,
                guards=tuple(guard.value for guard in intent.required_guards()),
            ),
            created_at=created_at,
        )

    def _finish(
        self,
        intent: ActionIntent,
        status: ActionExecutionStatus,
        receipt: ActionReceipt,
        action_record: Record | None,
        project_id: str,
        producer: Producer,
        *,
        reconciliation_required: bool = False,
    ) -> ActionRun:
        receipt_record = receipt.to_record(project_id=project_id, producer=producer, created_at=receipt.started_at)
        self._receipts[intent.action_key] = receipt
        records = (action_record, receipt_record) if action_record is not None else (receipt_record,)
        self._persist(records)
        return ActionRun(
            intent=intent,
            status=status,
            receipt=receipt,
            reconciliation_required=reconciliation_required,
            records=records,
        )

    def _persist(self, records: Sequence[Record]) -> None:
        if not records:
            return
        self._records.extend(records)
        if self.record_sink is not None:
            self.record_sink(records)


#: 취소·조정 문구가 되돌림을 주장하는지 판정하는 표시. 문자열 약속으로 복구를 대신하지 않는다.
REVERSAL_CLAIM_MARKERS: Final[tuple[str, ...]] = ("되돌렸", "복구했다", "reverted", "rolled back")


def claims_reversal(note: str) -> bool:
    """이 문구가 이미 발생한 행동을 되돌렸다고 주장하는가."""

    lowered = note.lower()
    return any(marker in lowered for marker in REVERSAL_CLAIM_MARKERS)


__all__ = [
    "ActionDispatchError",
    "ActionDispatcher",
    "ActionIntent",
    "ActionObservation",
    "ActionReceipt",
    "ActionRefusal",
    "ActionRun",
    "CallablePort",
    "DispatchOutcome",
    "PolicyClearance",
    "REVERSAL_CLAIM_MARKERS",
    "ToolDispatchPort",
    "ToolExecutorPort",
    "claims_reversal",
]
