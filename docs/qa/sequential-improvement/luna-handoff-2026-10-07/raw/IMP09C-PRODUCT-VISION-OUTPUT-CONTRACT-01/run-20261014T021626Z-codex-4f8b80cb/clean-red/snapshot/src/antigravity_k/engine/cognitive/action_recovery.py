"""Durable recovery observations; canonical append precedes journal publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from antigravity_k.engine.cognitive.action_context import ActionContext
from antigravity_k.engine.cognitive.action_journal import PENDING, SETTLED, ObservationPublication
from antigravity_k.engine.cognitive.action_lifecycle import reconcile
from antigravity_k.engine.cognitive.action_recovery_records import (
    intent_from_action_record,
    observation_digest,
    receipt_from_record,
)
from antigravity_k.engine.cognitive.action_types import (
    ActionReceipt,
    ActionRefusal,
    ActionRun,
    ObservationSubmission,
    ReconciliationResult,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    ObservationPayload,
    ObservationStatus,
    Producer,
    ReceiptStatus,
    Record,
    same_enum,
)
from antigravity_k.engine.cognitive.references import REL_ACTION, REL_RECEIPT, EntityType, Reference


def submit_observation(
    self: ActionContext,
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
    digest = observation_digest(submission)
    identity = f"{submission.project_id}/{submission.action_key}/{submission.expected_receipt_id}/{digest}"
    observation_id = f"observation:{uuid5(NAMESPACE_URL, identity)}"
    receipt_id = f"execution_receipt:{uuid5(NAMESPACE_URL, 'receipt/' + identity)}"
    if (
        claim.observation_digest == digest
        and claim.observation_record_id
        and (claim.receipt_id == submission.expected_receipt_id or claim.observation_record_id == observation_id)
    ):
        return ReconciliationResult(
            accepted=True,
            receipt_id=claim.receipt_id,
            observation_record_id=claim.observation_record_id,
            projection_revision=claim.projection_revision,
            reason="idempotent observation replay",
        )
    if (claim.receipt_id or "") != submission.expected_receipt_id:
        return ReconciliationResult(
            accepted=False,
            refusal=ActionRefusal.STALE_RECEIPT_REVISION,
            reason="expected receipt id does not match current projection",
        )
    # Settled projection must not be overwritten by a conflicting observation
    # (late/alternate success↔fail cannot mutate projection; history row may append).
    if claim.status == SETTLED and claim.receipt_id is not None:
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
        intent = intent_from_action_record(action_record)
        observed_at = submission.observed_at or moment
        history_record = Record.create(
            entity_type=EntityType.OBSERVATION,
            project_id=submission.project_id,
            producer=producer,
            references=(
                Reference(relation=REL_ACTION, target_id=intent.action_id, expected_type=EntityType.ACTION),
                Reference(
                    relation=REL_RECEIPT,
                    target_id=claim.receipt_id,
                    expected_type=EntityType.EXECUTION_RECEIPT,
                ),
            ),
            payload=ObservationPayload(
                raw_measurement_or_handle=digest,
                observed_at=observed_at,
                method="late_observation_history",
                source=f"received_at:{moment.isoformat()}",
                status=submission.observation.status
                if hasattr(submission.observation, "status")
                else ObservationStatus.COMPLETE,
            ),
            created_at=moment,
        )
        self._persist((history_record,))
        return ReconciliationResult(
            accepted=False,
            refusal=ActionRefusal.PROJECTION_SETTLED,
            reason=(
                "settled projection refuses conflicting observation (late history appended without projection mutate)"
            ),
            receipt_id=claim.receipt_id,
            observation_record_id=history_record.id,
            projection_revision=claim.projection_revision,
            records=(history_record,),
            redispatched=False,
        )

    action_record = load_record(claim.action_record_id) if claim.action_record_id else None
    if action_record is None and claim.receipt_id is None:
        action_record = Record.model_validate_json(claim.intent_json)
    if action_record is None:
        return ReconciliationResult(
            accepted=False, refusal=ActionRefusal.UNKNOWN_ACTION, reason="canonical action missing"
        )
    if action_record.project_id != submission.project_id:
        return ReconciliationResult(
            accepted=False, refusal=ActionRefusal.PROJECT_MISMATCH, reason="action record project mismatch"
        )
    receipt_record = load_record(claim.receipt_id) if claim.receipt_id else None
    if claim.receipt_id and receipt_record is None:
        return ReconciliationResult(
            accepted=False, refusal=ActionRefusal.UNKNOWN_ACTION, reason="canonical receipt missing"
        )
    if receipt_record is None:
        receipt_record = ActionReceipt(
            receipt_id=f"execution_receipt:{uuid5(NAMESPACE_URL, 'unknown/' + action_record.id)}",
            action_id=action_record.id,
            action_key=claim.action_key,
            submission_id=f"recover:{claim.action_key}",
            dispatch_attempt=1,
            status=ReceiptStatus.UNKNOWN,
            started_at=action_record.created_at,
            reconciliation="durable claim recovered without a dispatch receipt",
        ).to_record(project_id=submission.project_id, producer=producer, created_at=moment)
    if not same_enum(receipt_record.entity_type, EntityType.EXECUTION_RECEIPT):
        return ReconciliationResult(
            accepted=False, refusal=ActionRefusal.MALFORMED_OBSERVATION, reason="receipt record type mismatch"
        )
    receipt = receipt_from_record(receipt_record)
    intent = intent_from_action_record(action_record)
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
    settled = reconcile(
        self,
        run,
        submission.observation,
        project_id=submission.project_id,
        producer=producer,
        now=moment,
        persist=False,
        receipt_id=receipt_id,
    )
    assert settled.receipt is not None
    obs_record = Record.create(
        record_id=observation_id,
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
            status=submission.observation.status,
        ),
        created_at=moment,
    )
    revision = claim.projection_revision + 1
    journal_status = PENDING if settled.reconciliation_required else SETTLED
    records = (*settled.records, obs_record)

    def append_records() -> None:
        nonlocal records
        # Canonical records are create-only. A prior crash may have committed the
        # batch already, so retain its original timestamps and append only gaps.
        existing = {record.id: load_record(record.id) for record in records}
        missing = tuple(record for record in records if existing[record.id] is None)
        records = tuple(existing[record.id] or record for record in records)
        self._persist(missing)

    published = self.journal.attach_observation(
        claim,
        ObservationPublication(digest, obs_record.id, receipt_id, journal_status),
        append_records,
    )
    if not published:
        # Re-read only after a lost compare-and-set; exact concurrent replay is
        # accepted, while an alternate observation cannot overwrite the winner.
        return submit_observation(self, submission, producer=producer, load_record=load_record, now=moment)
    self._receipts[claim.action_key] = receipt_from_record(
        next(record for record in records if record.id == receipt_id)
    )
    return ReconciliationResult(
        accepted=True,
        receipt_id=settled.receipt.receipt_id,
        observation_record_id=obs_record.id,
        projection_revision=revision,
        records=records,
        redispatched=False,
    )
