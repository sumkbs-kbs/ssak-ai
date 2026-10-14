"""Bounded canonical model input for the synthetic live experiment."""

from __future__ import annotations

import json
from dataclasses import asdict

from antigravity_k.engine.cognitive.brain_context_render import render_context_for_brain
from antigravity_k.engine.cognitive.growth import CONTEXT_DISCLOSURE, GrowthBenchmarkError
from antigravity_k.engine.cognitive.live_trial_types import ModelTask
from antigravity_k.engine.cognitive.models import (
    ContextItem,
    ContextPackagePayload,
    ExperiencePayload,
    IntegrityStatus,
    Record,
    same_enum,
    to_wire,
)
from antigravity_k.engine.cognitive.references import REL_OBSERVATION, REL_OUTCOME, EntityType
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest

LIVE_MODEL_INPUT_BYTES = 32768


def expanded_context(record: Record, refs: tuple[str, ...], store: CanonicalStore) -> Record:
    """Persist the actual extra evidence disclosed for the second model call."""
    package = record.payload
    assert isinstance(package, ContextPackagePayload)
    present = {item.record_id for item in package.l3_evidence}
    items = list(package.l3_evidence)
    for ref in refs:
        source = store.read(ref)
        if (
            source is None
            or source.project_id != record.project_id
            or not same_enum(source.entity_type, EntityType.EVIDENCE)
        ):
            raise GrowthBenchmarkError("Requested live evidence is unavailable")
        if ref not in present:
            items.append(
                ContextItem(
                    record_id=ref,
                    reason_selected="Model requested missing synthetic task evidence",
                    token_estimate=len(json.dumps(to_wire(source)).encode()),
                    disclosure_level=CONTEXT_DISCLOSURE,
                )
            )
            present.add(ref)
    used = sum(
        item.token_estimate for item in (*package.l0_constraints, *package.l1_state, *package.l2_history, *items)
    )
    if used > package.budget.token_budget:
        raise GrowthBenchmarkError("Expanded canonical context exceeds selection budget")
    payload = package.model_copy(
        update={"l3_evidence": tuple(items), "budget": package.budget.model_copy(update={"tokens_used": used})}
    )
    return Record.create(
        entity_type=EntityType.CONTEXT_PACKAGE, project_id=record.project_id, producer=record.producer, payload=payload
    )


def model_task(
    task_id: str, record: Record, store: CanonicalStore, *, limit: int = LIVE_MODEL_INPUT_BYTES
) -> ModelTask:
    package = record.payload
    assert isinstance(package, ContextPackagePayload)
    if not same_enum(package.integrity, IntegrityStatus.COMPLETE):
        raise GrowthBenchmarkError("Incomplete live model context")
    rendered = render_context_for_brain(
        package,
        project_id=record.project_id,
        context_digest=canonical_digest(to_wire(record)),
        load_record=store.read,
        context_limit=limit,
    )
    if not rendered.ready_for_provider:
        raise GrowthBenchmarkError(f"Live model context unavailable: {rendered.omitted_required}")
    related: dict[str, object] = {}
    for item in package.l2_history:
        selected = store.read(item.record_id)
        if selected is None or not isinstance(selected.payload, ExperiencePayload):
            continue
        core = selected.payload
        if not same_enum(core.integrity, IntegrityStatus.COMPLETE) or core.missing_references:
            raise GrowthBenchmarkError("Incomplete live Experience cannot be disclosed as validated")
        for reference in selected.references:
            if reference.relation not in {REL_OBSERVATION, REL_OUTCOME}:
                continue
            ref = reference.target_id
            source = store.read(ref)
            if (
                source is None
                or source.project_id != record.project_id
                or not same_enum(source.entity_type, reference.expected_type)
            ):
                raise GrowthBenchmarkError("Selected Experience has unavailable observed lineage")
            if same_enum(source.entity_type, EntityType.OBSERVATION) or same_enum(
                source.entity_type, EntityType.OUTCOME
            ):
                related[ref] = to_wire(source)
    wire = dict(rendered.wire)
    wire["selected_experience_observed_lineage"] = list(related.values())
    visible = ModelTask(
        task_id,
        tuple(item.record_id for item in package.l3_evidence),
        package.policy_version,
        json.dumps(wire, ensure_ascii=False, separators=(",", ":")),
    )
    if len(json.dumps(asdict(visible), ensure_ascii=False).encode()) > limit:
        raise GrowthBenchmarkError("Complete live model input exceeds byte budget")
    return visible
