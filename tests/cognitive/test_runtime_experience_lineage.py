"""Experience lineage follows the active plan and marks missing performed-phase records."""

from dataclasses import replace

import pytest

from antigravity_k.engine.cognitive.actions import ActionDispatcher, ActionObservation, CallablePort
from antigravity_k.engine.cognitive.models import CognitiveRequestType, IntegrityStatus
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRequestEnvelope,
    CognitiveRuntime,
    EpisodeDelta,
    EpisodePlan,
    EpisodeRequest,
    ThinkOutcome,
)
from tests.cognitive.test_episode import BODY, NOW, PROJECT, FakeRethink, FakeThink, plan_with_action


def linked_plan() -> EpisodePlan:
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=False, detail="observed failure"))
    return replace(
        plan,
        decision_ref=new_id(EntityType.DECISION),
        governance_ref=new_id(EntityType.GOVERNANCE_DECISION),
        outcome_ref=new_id(EntityType.OUTCOME),
        observation_refs=(new_id(EntityType.OBSERVATION),),
        evidence_refs=(new_id(EntityType.EVIDENCE),),
    )


def runtime_for(plan: EpisodePlan) -> CognitiveRuntime:
    return CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref=new_id(EntityType.BRAIN_JUDGMENT), plan=plan)),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )


def request_for(plan: EpisodePlan) -> EpisodeRequest:
    return EpisodeRequest(
        episode_id="episode:lineage",
        context_ref=new_id(EntityType.CONTEXT_PACKAGE),
        goal_ref=new_id(EntityType.GOAL),
        plan=plan,
    )


def test_rethought_plan_supplies_selected_core_lineage() -> None:
    # Given original and revised plans with deliberately different canonical IDs.
    original, revised = linked_plan(), linked_plan()
    final_judgment = new_id(EntityType.BRAIN_JUDGMENT)
    runtime = runtime_for(original)
    runtime.think = FakeThink(
        ThinkOutcome(
            judgment_ref=new_id(EntityType.BRAIN_JUDGMENT),
            plan=original,
            requests=(
                CognitiveRequestEnvelope(
                    request_id=new_id(EntityType.COGNITIVE_REQUEST),
                    request_type=CognitiveRequestType.TOOL,
                    purpose="check",
                    target="src/a.py",
                    expected_decision_impact="change grounds",
                ),
            ),
        )
    )
    runtime.rethink = FakeRethink(
        [ThinkOutcome(judgment_ref=final_judgment, plan=revised, delta=EpisodeDelta(judgment=True))]
    )
    request = replace(request_for(original), simple=False)
    # When Primary rethinks and the revised action is observed.
    episode = runtime.run(request)
    # Then the selected historical core refers to the revised plan and judgment.
    assert episode.selection is not None and episode.selection.reusable
    (core,) = runtime.experience.cores_for_episode(request.episode_id)
    assert core.judgment_ref == final_judgment
    assert (core.decision_ref, core.governance_ref, core.outcome_ref, core.observation_refs, core.evidence_refs) == (
        revised.decision_ref,
        revised.governance_ref,
        revised.outcome_ref,
        revised.observation_refs,
        revised.evidence_refs,
    )
    assert core.action_ref == revised.action.action_id


@pytest.mark.parametrize("missing", ["context_ref", "decision_ref", "outcome_ref"])
def test_performed_phase_missing_reference_is_incomplete(missing: str) -> None:
    # Given a selected outcome whose historical lineage omits one performed phase.
    plan = linked_plan()
    if missing != "context_ref":
        plan = replace(plan, **{missing: None})
    runtime = runtime_for(plan)
    request = request_for(plan)
    if missing == "context_ref":
        request = replace(request, context_ref="context:legacy-shorthand")
    # When the action and observed outcome form an Experience.
    runtime.run(request)
    # Then incomplete provenance is explicit, never silently marked complete.
    (core,) = runtime.experience.cores_for_episode(request.episode_id)
    assert core.integrity == IntegrityStatus.INCOMPLETE
    assert missing in core.missing_references


def test_simple_episode_does_not_require_expansion_governance_reference() -> None:
    # Given a simple episode without a GOVERN expansion phase.
    plan = replace(linked_plan(), governance_ref=None)
    runtime = runtime_for(plan)
    request = request_for(plan)
    # When its action and outcome complete with all applicable canonical lineage.
    runtime.run(request)
    # Then the inapplicable expansion reference does not imply data loss.
    (core,) = runtime.experience.cores_for_episode(request.episode_id)
    assert "governance_ref" not in core.missing_references


def test_observed_result_without_supplied_record_gets_canonical_lineage() -> None:
    # Given an actual synchronous observation without a prebuilt record reference.
    plan = replace(linked_plan(), observation_refs=())
    runtime = runtime_for(plan)
    published = []
    runtime.record_sink = lambda records: published.extend(records)
    request = request_for(plan)
    # When runtime records the observation before forming Experience.
    runtime.run(request)
    # Then its historical core points to the published observation rather than losing it.
    (core,) = runtime.experience.cores_for_episode(request.episode_id)
    observations = [record for record in published if record.entity_type == EntityType.OBSERVATION]
    assert core.observation_refs == tuple(record.id for record in observations)
    assert len(core.observation_refs) == 1
    assert "observation_refs" not in core.missing_references


def test_governed_episode_without_governance_record_is_incomplete() -> None:
    # Given an expansion request that enters GOVERN without a canonical decision reference.
    plan = replace(linked_plan(), governance_ref=None)
    runtime = runtime_for(plan)
    runtime.think = FakeThink(
        ThinkOutcome(
            judgment_ref=new_id(EntityType.BRAIN_JUDGMENT),
            plan=plan,
            requests=(
                CognitiveRequestEnvelope(
                    request_id=new_id(EntityType.COGNITIVE_REQUEST),
                    request_type=CognitiveRequestType.TOOL,
                    purpose="check",
                    target="src/a.py",
                    expected_decision_impact="change grounds",
                ),
            ),
        )
    )
    runtime.rethink = FakeRethink(
        [ThinkOutcome(judgment_ref=new_id(EntityType.BRAIN_JUDGMENT), delta=EpisodeDelta(judgment=True))]
    )
    request = replace(request_for(plan), simple=False)
    # When that governed episode completes and is selected.
    runtime.run(request)
    # Then the performed governance phase cannot claim complete historical lineage.
    (core,) = runtime.experience.cores_for_episode(request.episode_id)
    assert core.integrity == IntegrityStatus.INCOMPLETE
    assert "governance_ref" in core.missing_references
