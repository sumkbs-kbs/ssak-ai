"""Durable recovery observations; canonical append precedes journal publication."""

from __future__ import annotations

import hashlib
import json

from antigravity_k.engine.cognitive.action_types import (
    ActionIntent,
    ActionReceipt,
    ObservationSubmission,
)
from antigravity_k.engine.cognitive.models import (
    ActionPayload,
    ExecutionReceiptPayload,
    Record,
)


def observation_digest(submission: ObservationSubmission) -> str:
    observation = submission.observation
    payload = {
        "observed_at": submission.observed_at.isoformat() if submission.observed_at else None,
        "observed": observation.observed,
        "succeeded": observation.succeeded,
        "external_ref": observation.external_ref,
        "detail": observation.detail,
        "status": getattr(observation.status, "value", str(observation.status)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def receipt_from_record(record: Record) -> ActionReceipt:
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
        detail=payload.detail,
    )


def intent_from_action_record(record: Record) -> ActionIntent:
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
