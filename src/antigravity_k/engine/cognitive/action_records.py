"""Canonical action envelope creation."""

from datetime import datetime

from antigravity_k.engine.cognitive.action_types import ActionIntent
from antigravity_k.engine.cognitive.models import ActionExecutionStatus, ActionPayload, Producer, Record
from antigravity_k.engine.cognitive.references import EntityType


def create_action_record(
    intent: ActionIntent,
    project_id: str,
    producer: Producer,
    created_at: datetime,
    *,
    status: ActionExecutionStatus = ActionExecutionStatus.AUTHORIZED,
) -> Record:
    """Bind the authorized record ID to the identity sent to the executor and receipt."""
    return Record.create(
        entity_type=EntityType.ACTION,
        record_id=intent.action_id if status == ActionExecutionStatus.AUTHORIZED else None,
        project_id=project_id,
        producer=producer,
        payload=ActionPayload(
            tool=intent.tool,
            args_digest=intent.args_digest(),
            scope=intent.scope or intent.tool,
            risk_profile=intent.risk,
            idempotency_key=intent.action_key,
            execution_status=status,
            guards=tuple(guard.value for guard in intent.required_guards()),
        ),
        created_at=created_at,
    )
