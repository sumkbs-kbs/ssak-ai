"""Select late recovery observations into durable, explicitly partial Experience."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import NAMESPACE_URL, uuid5

from antigravity_k.engine.cognitive.actions import ReconciliationResult
from antigravity_k.engine.cognitive.experience import (
    EpisodeSignals,
    ExperienceCore,
    ExperienceLedger,
    OperationalRecord,
    compare_outcome,
)
from antigravity_k.engine.cognitive.models import IntegrityStatus, Producer, Record, SelectionDisposition
from antigravity_k.engine.cognitive.references import REL_ACTION, EntityType
from antigravity_k.engine.cognitive.store import CommitReceipt, DuplicateRecordError
from antigravity_k.engine.cognitive_surface_types import SurfaceNotReadyError


def record_recovery_experience(
    result: ReconciliationResult,
    *,
    project_id: str,
    producer: Producer,
    observed: bool,
    succeeded: bool | None,
    load_record: Callable[[str], Record | None],
    record_sink: Callable[[Sequence[Record]], CommitReceipt | None],
    ledger: ExperienceLedger,
) -> None:
    """Append once per canonical observation, including retries after a lost response."""
    if not result.accepted or not result.observation_record_id:
        return
    observation = load_record(result.observation_record_id)
    if observation is None or observation.project_id != project_id or observation.entity_type != EntityType.OBSERVATION:
        raise SurfaceNotReadyError("Recovery observation is not canonical in this project")
    marker_id = f"event:{uuid5(NAMESPACE_URL, 'selection/' + observation.id)}"
    core_id = f"experience:{uuid5(NAMESPACE_URL, 'experience/' + observation.id)}"
    marker_record = load_record(marker_id)
    if marker_record is not None:
        existing = load_record(core_id)
        selection_payload = getattr(marker_record.payload, "selection", None)
        if (
            selection_payload is not None
            and selection_payload.disposition == SelectionDisposition.EXPERIENCE
            and existing is None
        ):
            raise SurfaceNotReadyError("Selected recovery Experience is missing from canonical store")
        if existing is not None:
            ledger.ingest_core_record(existing)
        return
    action_ref = next((ref.target_id for ref in observation.references if ref.relation == REL_ACTION), None)
    episode = f"recovery:{observation.id}"
    continuation = ExperienceLedger()
    operational = OperationalRecord(
        record_id=observation.id,
        episode_reference=episode,
        kind="recovery_observation",
        detail=f"current_receipt={result.receipt_id}",
        recorded_at=observation.created_at,
        producer=producer,
    )
    continuation.record_operational(operational)
    outcome = None if not observed or succeeded is None else ("succeeded" if succeeded else "failed")
    selection = continuation.select(
        operational,
        comparison=compare_outcome("succeeded", outcome),
        signals=EpisodeSignals(recovery=True, unresolved=outcome is None),
        producer=producer,
        recorded_at=observation.created_at,
        note=f"canonical_observation={observation.id}; current_receipt={result.receipt_id}",
    )
    marker = selection.to_record(project_id=project_id, created_at=observation.created_at).model_copy(
        update={"id": marker_id}
    )
    records = [marker]
    if selection.disposition == SelectionDisposition.EXPERIENCE:
        core = ExperienceCore(
            experience_id=core_id,
            episode_reference=episode,
            trigger="late recovery observation",
            action_ref=action_ref,
            observation_refs=(observation.id,),
            integrity=IntegrityStatus.INCOMPLETE,
            missing_references=("context_ref", "judgment_ref", "governance_ref", "decision_ref", "outcome_ref")
            + (() if action_ref else ("action_ref",)),
        )
        continuation.form_experience(
            selection, core, project_id=project_id, producer=producer, created_at=observation.created_at
        )
        records.extend(continuation.pending_sink_records())
    try:
        record_sink(tuple(records))
    except DuplicateRecordError:
        # Concurrent exact replay may publish the same deterministic batch first.
        if not all(load_record(record.id) is not None for record in records):
            raise
    stored = load_record(core_id)
    if stored is not None:
        ledger.ingest_core_record(stored)
