"""Post-dispatch observation and cancellation semantics."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final

from antigravity_k.engine.cognitive.action_context import ActionContext
from antigravity_k.engine.cognitive.action_journal import PENDING, SETTLED
from antigravity_k.engine.cognitive.action_types import (
    ActionDispatchError,
    ActionObservation,
    ActionReceipt,
    ActionRun,
    new_receipt_id,
)
from antigravity_k.engine.cognitive.models import ActionExecutionStatus, Producer, ReceiptStatus, same_enum
from antigravity_k.engine.cognitive.references import REL_SUPERSEDES, EntityType, Reference


# ── 관측·조정 ───────────────────────────────────────
def reconcile(
    self: ActionContext,
    run: ActionRun,
    observation: ActionObservation,
    *,
    project_id: str,
    producer: Producer,
    now: datetime | None = None,
    persist: bool = True,
    receipt_id: str | None = None,
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

    previous_id = receipt.receipt_id
    updated = replace(updated, receipt_id=receipt_id or new_receipt_id())
    record = updated.to_record(
        project_id=project_id,
        producer=producer,
        created_at=moment,
        references=(
            Reference(
                relation=REL_SUPERSEDES,
                target_id=previous_id,
                expected_type=EntityType.EXECUTION_RECEIPT,
            ),
        ),
    )
    if persist:
        self._receipts[receipt.action_key] = updated
        self._persist((record,))
    if persist and self.journal is not None:
        journal_status = PENDING if same_enum(status, ActionExecutionStatus.UNKNOWN) else SETTLED
        self.journal.attach_receipt(project_id, receipt.action_key, updated.receipt_id, status=journal_status)
    return replace(
        run,
        status=status,
        receipt=updated,
        reconciliation_required=same_enum(status, ActionExecutionStatus.UNKNOWN),
        records=(*run.records, record),
    )


# ── 취소 ────────────────────────────────────────────
def cancel(
    self: ActionContext,
    run: ActionRun,
    *,
    reason: str,
    now: datetime | None = None,
) -> ActionRun:
    """dispatch 전에는 취소로 끝낼 수 있다. 이미 나간 action은 되돌린 것으로 주장하지 않는다."""

    moment = now if now is not None else self._now()
    if run.receipt is None or not run.effect_possible:
        cancelled = ActionReceipt(
            receipt_id=new_receipt_id(),
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

    note = f"취소 요청만 기록한다({reason}). 이미 발생한 행동의 되돌림은 주장하지 않으며 외부 관측으로 조정해야 한다."
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


#: 취소·조정 문구가 되돌림을 주장하는지 판정하는 표시. 문자열 약속으로 복구를 대신하지 않는다.
REVERSAL_CLAIM_MARKERS: Final[tuple[str, ...]] = ("되돌렸", "복구했다", "reverted", "rolled back")


def claims_reversal(note: str) -> bool:
    """이 문구가 이미 발생한 행동을 되돌렸다고 주장하는가."""

    lowered = note.lower()
    return any(marker in lowered for marker in REVERSAL_CLAIM_MARKERS)
