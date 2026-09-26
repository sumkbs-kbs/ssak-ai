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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from antigravity_k.engine.cognitive.action_admission import preconditions
from antigravity_k.engine.cognitive.action_journal import PENDING, SETTLED, ActionJournal
from antigravity_k.engine.cognitive.action_lifecycle import (
    REVERSAL_CLAIM_MARKERS,
    cancel,
    claims_reversal,
    reconcile,
)
from antigravity_k.engine.cognitive.action_records import create_action_record
from antigravity_k.engine.cognitive.action_types import (
    ActionDispatchError,
    ActionIntent,
    ActionObservation,
    ActionReceipt,
    ActionRefusal,
    ActionRun,
    CallablePort,
    DispatchOutcome,
    ObservationSubmission,
    PolicyClearance,
    ReconciliationResult,
    ToolDispatchPort,
    ToolExecutorPort,
    new_receipt_id,
)
from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    ActionPayload,
    ExecutionReceiptPayload,
    ObservationPayload,
    ObservationStatus,
    Producer,
    ReceiptStatus,
    Record,
    same_enum,
)
from antigravity_k.engine.cognitive.references import REL_ACTION, REL_RECEIPT, EntityType, Reference


@dataclass(frozen=True, slots=True)
class ActionDispatcher:
    """intent→권한→executor→receipt 순서를 강제하는 dispatcher.

    ``port``가 없으면 아무 것도 실행하지 않는다(feature off). ``record_sink``는 canonical
    store adapter이며, 없으면 기록은 dispatcher 내부에만 남는다.
    """

    port: ToolDispatchPort | None = None
    record_sink: Callable[[Sequence[Record]], object] | None = None
    clock: Callable[[], datetime] | None = None
    journal: ActionJournal | None = None
    authority_resolver: Callable[[ActionIntent, datetime], AuthorityDecision] | None = None
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

        record = create_action_record(intent, project_id, producer, self._now(), status=ActionExecutionStatus.PLANNED)
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

        started = now if now is not None else self._now()
        refusal = preconditions(self, intent, retry_authorized=retry_authorized, now=started, subject=producer.actor_id)
        if refusal is not None:
            return refusal

        self._attempts[intent.action_key] = self._attempts.get(intent.action_key, 0) + 1
        attempt = self._attempts[intent.action_key]
        self._submissions[intent.submission_id] = intent.action_key

        action_record = create_action_record(intent, project_id, producer, started)
        if self.journal is not None and not self.journal.claim(project_id, intent.action_key, action_record):
            return self._refuse(intent, ActionRefusal.DUPLICATE_ACTION, "durable action claim already exists")
        self._persist((action_record,))
        refusal = preconditions(
            self,
            intent,
            retry_authorized=retry_authorized,
            now=now if now is not None else self._now(),
            subject=producer.actor_id,
        )
        if refusal is not None:
            return replace(refusal, records=(action_record,))
        port = self.port
        if port is None:  # _preconditions가 이미 막는다 — 여기서는 타입을 좁히는 재확인이다
            return self._refuse(intent, ActionRefusal.NO_DISPATCH_PORT, "dispatch 경로가 연결되지 않았다(feature off)")
        try:
            outcome = port.dispatch(intent.tool, intent.arguments, action_id=intent.action_id)
        except Exception as exc:  # executor가 결과를 돌려주지 못한 경우
            receipt = ActionReceipt(
                receipt_id=new_receipt_id(),
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
                receipt_id=new_receipt_id(),
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
            receipt_id=new_receipt_id(),
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

    def reconcile(
        self,
        run: ActionRun,
        observation: ActionObservation,
        *,
        project_id: str,
        producer: Producer,
        now: datetime | None = None,
    ) -> ActionRun:
        return reconcile(self, run, observation, project_id=project_id, producer=producer, now=now)

    def cancel(self, run: ActionRun, *, reason: str, now: datetime | None = None) -> ActionRun:
        return cancel(self, run, reason=reason, now=now)

    def submit_observation(
        self,
        submission: ObservationSubmission,
        *,
        producer: Producer,
        load_record: Callable[[str], Record | None],
        now: datetime | None = None,
    ) -> ReconciliationResult:
        """Append observation onto a durable pending claim. Never redispatches."""

        moment = now if now is not None else self._now()
        if self.journal is None:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.UNKNOWN_ACTION,
                reason="durable journal is required for recovery observation",
            )
        claim = self.journal.get(submission.project_id, submission.action_key)
        if claim is None:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.UNKNOWN_ACTION,
                reason="action claim not found for project",
            )
        if claim.project_id != submission.project_id:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.PROJECT_MISMATCH,
                reason="project mismatch",
            )
        if not claim.receipt_id:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.STALE_RECEIPT_REVISION,
                reason="claim has no durable receipt yet",
            )
        if claim.receipt_id != submission.expected_receipt_id:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.STALE_RECEIPT_REVISION,
                reason="expected receipt id does not match current projection",
            )
        digest = _observation_digest(submission.observation)
        if claim.observation_digest == digest and claim.observation_record_id and claim.receipt_id:
            return ReconciliationResult(
                accepted=True,
                receipt_id=claim.receipt_id,
                observation_record_id=claim.observation_record_id,
                projection_revision=claim.projection_revision,
                records=(),
                redispatched=False,
                reason="idempotent observation replay",
            )

        receipt_record = load_record(claim.receipt_id)
        action_record = load_record(claim.action_record_id) if claim.action_record_id else None
        if receipt_record is None or action_record is None:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.UNKNOWN_ACTION,
                reason="canonical action/receipt records missing",
            )
        if not same_enum(receipt_record.entity_type, EntityType.EXECUTION_RECEIPT):
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.MALFORMED_OBSERVATION,
                reason="receipt record type mismatch",
            )
        if action_record.project_id != submission.project_id:
            return ReconciliationResult(
                accepted=False,
                refusal=ActionRefusal.PROJECT_MISMATCH,
                reason="action record project mismatch",
            )

        receipt = _receipt_from_record(receipt_record)
        intent = _intent_from_action_record(action_record)
        run = ActionRun(
            intent=intent,
            status=ActionExecutionStatus.DISPATCHED
            if same_enum(receipt.status, ReceiptStatus.DISPATCHED)
            else ActionExecutionStatus.UNKNOWN,
            receipt=receipt,
            reconciliation_required=True,
            records=(action_record, receipt_record),
        )
        observed_at = submission.observed_at or moment
        # received_at is wall clock at recovery; recorded on observation payload method field
        settled = self.reconcile(
            run,
            submission.observation,
            project_id=submission.project_id,
            producer=producer,
            now=moment,
        )
        assert settled.receipt is not None
        obs_record = Record.create(
            entity_type=EntityType.OBSERVATION,
            project_id=submission.project_id,
            producer=producer,
            references=(
                Reference(relation=REL_ACTION, target_id=intent.action_id, expected_type=EntityType.ACTION),
                Reference(
                    relation=REL_RECEIPT,
                    target_id=settled.receipt.receipt_id,
                    expected_type=EntityType.EXECUTION_RECEIPT,
                ),
            ),
            payload=ObservationPayload(
                raw_measurement_or_handle=digest,
                observed_at=observed_at,
                method="recovery_observation",
                source=f"received_at:{moment.isoformat()}",
                status=submission.observation.status
                if hasattr(submission.observation, "status")
                else ObservationStatus.COMPLETE,
            ),
            created_at=moment,
        )
        self._persist((obs_record,))
        revision = claim.projection_revision + 1
        journal_status = PENDING if settled.reconciliation_required else SETTLED
        # re-attach receipt (reconcile already did) then observation projection
        self.journal.attach_observation(
            submission.project_id,
            submission.action_key,
            observation_digest=digest,
            observation_record_id=obs_record.id,
            receipt_id=settled.receipt.receipt_id,
            projection_revision=revision,
            status=journal_status,
        )
        return ReconciliationResult(
            accepted=True,
            receipt_id=settled.receipt.receipt_id,
            observation_record_id=obs_record.id,
            projection_revision=revision,
            records=(*settled.records, obs_record),
            redispatched=False,
        )

    def pending_with_reasons(self, project_id: str) -> tuple:
        """Operator-visible pending claims; timeout never clears these rows."""
        return self.pending_claims(project_id)

    # ── 내부 ────────────────────────────────────────────
    def _now(self) -> datetime:
        if self.clock is not None:
            return self.clock()
        return datetime.now(UTC)

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
        self._persist((receipt_record,))
        if self.journal is not None:
            journal_status = PENDING if reconciliation_required else SETTLED
            self.journal.attach_receipt(project_id, intent.action_key, receipt.receipt_id, status=journal_status)
        return ActionRun(
            intent=intent,
            status=status,
            receipt=receipt,
            reconciliation_required=reconciliation_required,
            records=records,
        )

    def pending_claims(self, project_id: str):
        """Restart-safe pending claim projection from the durable journal."""
        if self.journal is None:
            return ()
        return self.journal.list_pending(project_id)

    def _persist(self, records: Sequence[Record]) -> None:
        if not records:
            return
        if self.record_sink is not None:
            self.record_sink(records)
        self._records.extend(records)


def _observation_digest(observation: ActionObservation) -> str:
    payload = {
        "observed": observation.observed,
        "succeeded": observation.succeeded,
        "external_ref": observation.external_ref,
        "detail": observation.detail,
        "status": getattr(observation.status, "value", str(observation.status)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _receipt_from_record(record: Record) -> ActionReceipt:
    payload = record.payload
    if not isinstance(payload, ExecutionReceiptPayload):
        raise TypeError(f"expected ExecutionReceiptPayload, got {type(payload).__name__}")
    return ActionReceipt(
        receipt_id=record.id,
        action_id=payload.action_id,
        action_key=payload.idempotency_key,
        submission_id=f"recover:{payload.idempotency_key}",
        dispatch_attempt=int(payload.dispatch_attempt),
        status=payload.status,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        external_ref=payload.external_ref,
        effects_observed=payload.effects_observed,
        reconciliation=payload.reconciliation or "",
    )


def _intent_from_action_record(record: Record) -> ActionIntent:
    payload = record.payload
    assert isinstance(payload, ActionPayload)
    return ActionIntent(
        action_id=record.id,
        submission_id=f"recover:{payload.idempotency_key}",
        action_key=payload.idempotency_key,
        tool=payload.tool,
        scope=payload.scope,
        risk=payload.risk_profile,
    )


__all__ = [
    "ActionDispatchError",
    "ActionDispatcher",
    "ActionIntent",
    "ActionObservation",
    "ActionReceipt",
    "ActionRefusal",
    "ActionRun",
    "ReconciliationResult",
    "ObservationSubmission",
    "CallablePort",
    "DispatchOutcome",
    "PolicyClearance",
    "REVERSAL_CLAIM_MARKERS",
    "ToolDispatchPort",
    "ToolExecutorPort",
    "claims_reversal",
]
