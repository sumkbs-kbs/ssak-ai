"""Canonical historical cores survive replay without republishing or identity drift."""

from dataclasses import replace

import pytest

from antigravity_k.engine.cognitive.experience import (
    ExperienceContractError,
    ExperienceCore,
    ExperienceLedger,
    ExperienceSelection,
)
from antigravity_k.engine.cognitive.models import (
    ExperiencePayload,
    IntegrityStatus,
    Record,
    SelectionDisposition,
    SelectionReason,
)
from antigravity_k.engine.cognitive.references import REL_EVIDENCE, EntityType, new_id
from tests.cognitive._fixtures import NOW, PRODUCER


def core_fixture() -> ExperienceCore:
    return ExperienceCore(
        experience_id=new_id(EntityType.EXPERIENCE),
        episode_reference="episode:real-run",
        trigger="material delta",
        context_ref=new_id(EntityType.CONTEXT_PACKAGE),
        judgment_ref=new_id(EntityType.BRAIN_JUDGMENT),
        governance_ref=new_id(EntityType.GOVERNANCE_DECISION),
        decision_ref=new_id(EntityType.DECISION),
        action_ref=new_id(EntityType.ACTION),
        observation_refs=(new_id(EntityType.OBSERVATION),),
        outcome_ref=new_id(EntityType.OUTCOME),
        evidence_refs=(new_id(EntityType.EVIDENCE),),
        remaining_unknowns=("follow-up",),
        future_attention=("verify recovery",),
    )


def form(ledger: ExperienceLedger, core: ExperienceCore) -> ExperienceCore:
    selection = ExperienceSelection(
        episode_reference=core.episode_reference,
        disposition=SelectionDisposition.EXPERIENCE,
        reasons=(SelectionReason.MATERIAL_DELTA,),
        evidence_refs=core.evidence_refs,
        producer=PRODUCER,
        recorded_at=NOW,
    )
    return ledger.form_experience(
        selection, core, project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW
    )


def test_roundtrip_preserves_full_core_and_typed_evidence() -> None:
    # Given a selected core with every historical reference.
    core = core_fixture()
    record = core.to_record(
        project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW
    )
    # When the serialized canonical record is parsed after restart.
    loaded = ExperienceLedger().ingest_core_record(Record.model_validate_json(record.model_dump_json()))
    # Then both historical content and identity remain exact.
    assert loaded == core
    assert loaded.digest() == core.digest()
    assert [(r.target_id, r.expected_type) for r in record.references if r.relation == REL_EVIDENCE] == [
        (core.evidence_refs[0], EntityType.EVIDENCE)
    ]


def test_regenerated_selection_returns_original_core_after_restart() -> None:
    # Given a committed core rehydrated into a fresh ledger.
    core = core_fixture()
    ledger = ExperienceLedger()
    ledger.ingest_core_record(
        core.to_record(project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW)
    )
    # When selection retries with a newly allocated candidate identity.
    selected = form(ledger, replace(core, experience_id=new_id(EntityType.EXPERIENCE)))
    # Then the committed core is reused and nothing is published again.
    assert selected == core
    assert ledger.cores_for_episode(core.episode_reference) == (core,)
    assert ledger.pending_sink_records() == ()


def test_ingestion_preserves_pending_new_records_without_republishing_history() -> None:
    # Given a newly formed unsunk core.
    ledger = ExperienceLedger()
    new_core = form(ledger, core_fixture())
    prior_core = replace(core_fixture(), episode_reference="episode:prior")
    prior_record = prior_core.to_record(
        project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW
    )
    # When older committed history arrives alongside it.
    ledger.ingest_core_record(prior_record)
    # Then only the new core is pending, and acknowledging it drains the queue.
    assert tuple(r.id for r in ledger.pending_sink_records()) == (new_core.experience_id,)
    assert prior_record in ledger.records
    ledger.mark_sunk(1)
    assert ledger.pending_sink_records() == ()


def test_legacy_record_marks_unknown_episode_instead_of_guessing_context() -> None:
    # Given an old record whose first historical reference is a context.
    record = Record.create(
        entity_type=EntityType.EXPERIENCE,
        project_id="project:00000000-0000-4000-8000-000000000001",
        producer=PRODUCER,
        payload=ExperiencePayload(trigger="legacy", historical_refs=(new_id(EntityType.CONTEXT_PACKAGE),)),
        created_at=NOW,
    )
    # When history is rehydrated without an independently known episode.
    core = ExperienceLedger().ingest_core_record(record)
    # Then the absent lineage is explicit.
    assert core.episode_reference == ""
    assert core.integrity == IntegrityStatus.INCOMPLETE
    assert "episode_reference" in core.missing_references


def test_conflicting_ingestion_cannot_replace_committed_core() -> None:
    # Given a committed core.
    ledger = ExperienceLedger()
    core = core_fixture()
    ledger.ingest_core_record(
        core.to_record(project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW)
    )
    changed = replace(core, trigger="revised history")
    # When the same identity claims changed historical content.
    with pytest.raises(ExperienceContractError):
        ledger.ingest_core_record(
            changed.to_record(
                project_id="project:00000000-0000-4000-8000-000000000001", producer=PRODUCER, created_at=NOW
            )
        )
    # Then the original history remains intact.
    assert ledger.core(core.experience_id) == core


def test_revised_history_is_appended_without_overwriting_original() -> None:
    # Given a formed historical core.
    ledger = ExperienceLedger()
    original = form(ledger, core_fixture())
    digest = original.digest()
    # When a distinct new historical revision is selected.
    revised = form(ledger, replace(original, experience_id=new_id(EntityType.EXPERIENCE), trigger="new observation"))
    # Then both versions survive and the original digest remains stable.
    assert ledger.cores_for_episode(original.episode_reference) == (original, revised)
    assert ledger.core_digest_history(original.experience_id) == (digest,)


def test_core_replay_from_real_store_is_idempotent(tmp_path) -> None:
    from antigravity_k.engine.cognitive.store import CanonicalStore
    from tests.cognitive._fixtures import build_evidence

    # Given one selected core committed with its evidence in the real store.
    project = new_id(EntityType.PROJECT)
    evidence = build_evidence(project)
    core = ExperienceCore(
        experience_id=new_id(EntityType.EXPERIENCE),
        episode_reference="episode:stored",
        trigger="material result",
        evidence_refs=(evidence.id,),
    )
    record = core.to_record(project_id=project, producer=PRODUCER, created_at=NOW)
    CanonicalStore(tmp_path, git_enabled=False).commit_records([evidence, record])
    # When another store and ledger reopen and replay the same selection.
    restarted = CanonicalStore(tmp_path, git_enabled=False)
    committed = restarted.read(core.experience_id)
    assert committed is not None
    ledger = ExperienceLedger()
    ledger.ingest_core_record(committed)
    selected = form(ledger, replace(core, experience_id=new_id(EntityType.EXPERIENCE)))
    # Then the selected identity is the original core and no extra publication is queued.
    assert selected == core
    assert ledger.pending_sink_records() == ()
    assert restarted.count_committed() == 2
