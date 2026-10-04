"""Learning accepts Experience claims only through resolved complete historical cores."""

from dataclasses import replace

import pytest

from antigravity_k.engine.cognitive.experience import ExperienceCore
from antigravity_k.engine.cognitive.learning import (
    CandidateKind,
    CandidateProposer,
    CandidateRequest,
    EvaluationSummary,
    ExperienceEvaluator,
    InsufficientEvidenceError,
    summarize,
)
from antigravity_k.engine.cognitive.models import IntegrityStatus
from antigravity_k.engine.cognitive.references import EntityType, new_id
from tests.cognitive.test_learning import BODY, NOW, PROJECT, observation


def linked_observation():
    observed = observation(1)
    core = ExperienceCore(
        experience_id=new_id(EntityType.EXPERIENCE),
        episode_reference=observed.episode_id,
        trigger="observed",
        evidence_refs=observed.evidence_ids,
    )
    return replace(observed, experience_id=core.experience_id), core


def test_claimed_experience_without_lookup_is_rejected() -> None:
    # Given an observation claiming a canonical Experience identity.
    observed, _ = linked_observation()
    # When aggregation has no authoritative core lookup.
    with pytest.raises(InsufficientEvidenceError):
        ExperienceEvaluator().aggregate((observed,))
    # Then no learning summary can silently assert that this historical core is complete.


@pytest.mark.parametrize("invalid", ["missing", "incomplete", "episode", "evidence", "identity"])
def test_unresolved_or_inconsistent_experience_is_rejected(invalid: str) -> None:
    # Given a resolver whose result fails one provenance requirement.
    observed, core = linked_observation()
    if invalid == "missing":
        resolved = None
    elif invalid == "incomplete":
        resolved = replace(core, integrity=IntegrityStatus.INCOMPLETE, missing_references=("outcome_ref",))
    elif invalid == "episode":
        resolved = replace(core, episode_reference="episode:other")
    elif invalid == "evidence":
        resolved = replace(core, evidence_refs=())
    else:
        resolved = replace(core, experience_id=new_id(EntityType.EXPERIENCE))
    # When the claimed Experience is used for learning aggregation.
    with pytest.raises(InsufficientEvidenceError):
        ExperienceEvaluator(experience_lookup=lambda identity: resolved).aggregate((observed,))
    # Then missing historical lineage cannot become successful learning input.


def test_complete_resolved_experience_remains_mechanically_aggregatable() -> None:
    # Given a complete historical core matching the claimed episode and evidence.
    observed, core = linked_observation()
    # When its authoritative lookup is supplied.
    summary = ExperienceEvaluator(experience_lookup=lambda identity: core).aggregate((observed,))
    # Then the existing mechanical outcome comparison is preserved.
    assert summary.observations == (observed,)
    assert summary.analysis.observation_count == 1


def test_raw_comparison_without_experience_claim_needs_no_lookup() -> None:
    # Given a mechanical comparison making no canonical Experience claim.
    observed = observation(1)
    # When it is aggregated in isolation.
    summary = ExperienceEvaluator().aggregate((observed,))
    # Then ordinary comparison remains available.
    assert summary.observations == (observed,)


def test_handbuilt_summary_cannot_bypass_candidate_provenance_check() -> None:
    # Given a handbuilt mechanical summary claiming an unresolved Experience.
    observed, _ = linked_observation()
    summary = EvaluationSummary(observations=(observed,), analysis=summarize((observed,)))
    # When candidate formation bypasses the evaluator.
    with pytest.raises(InsufficientEvidenceError):
        CandidateProposer().propose(
            summary,
            CandidateRequest(kind=CandidateKind.PATTERN, rule="hypothesis", scope="test"),
            project_id=PROJECT,
            producer=BODY,
            created_at=NOW,
        )
    # Then the second learning boundary refuses the unresolved historical claim.


@pytest.mark.parametrize("resolved", [False, True])
def test_validator_rechecks_core_provenance_before_issuing_report(resolved: bool) -> None:
    from antigravity_k.engine.cognitive.learning import HeldOutValidator, TriggerSource
    from tests.cognitive.test_learning import criterion, validation_observations, validation_split

    # Given a candidate originally built from a complete resolved core.
    observed, core = linked_observation()
    summary = ExperienceEvaluator(experience_lookup=lambda identity: core).aggregate((observed,))
    candidate = CandidateProposer(experience_lookup=lambda identity: core).propose(
        summary,
        CandidateRequest(
            kind=CandidateKind.PATTERN, rule="hypothesis", scope="test", trigger_sources=(TriggerSource.HUMAN_REQUEST,)
        ),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    incomplete = replace(core, integrity=IntegrityStatus.INCOMPLETE, missing_references=("outcome_ref",))
    validator = HeldOutValidator(experience_lookup=(lambda identity: incomplete) if resolved else None)
    # When validation has either an incomplete core or no lookup at all.
    with pytest.raises(InsufficientEvidenceError, match="Experience"):
        validator.validate(
            candidate,
            split=validation_split(),
            criterion=criterion(),
            observations=validation_observations(True, True),
            generated_at=NOW,
        )
    # Then it cannot issue a promotion-enabling validation report.


def test_complete_ledger_lookup_binds_aggregation_and_candidate() -> None:
    from antigravity_k.engine.cognitive.experience import ExperienceLedger

    # Given a canonical Experience record rehydrated into the actual ledger.
    observed, core = linked_observation()
    ledger = ExperienceLedger()
    ledger.ingest_core_record(core.to_record(project_id=PROJECT, producer=BODY, created_at=NOW))
    # When both learning boundaries resolve the real ledger core.
    summary = ExperienceEvaluator(experience_lookup=ledger.core).aggregate((observed,))
    candidate = CandidateProposer(experience_lookup=ledger.core).propose(
        summary,
        CandidateRequest(kind=CandidateKind.PATTERN, rule="hypothesis", scope="test"),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    # Then canonical historical provenance is retained in the candidate's input.
    assert candidate.summary.observations[0].experience_id == core.experience_id
