"""T08/T09 — 최소 운영 루프와 Experience 형성 시험 (P08).

T08-A simple 경로에 불필요한 Secondary·재사고·verifier가 없다.
T08-B targeted rethink는 바뀐 grounds 범위만 다시 본다.
T08-C 같은 signature/새 ID만 있는 반복은 material delta 없이 종료한다.
T08-D stop은 READY가 아니다. readiness 부족이면 BLOCKED로 끝난다.
T09-A~E Operational Record 보존, 선별, 예상 일치 재검증, 세 평가 분리, 지연·불명, 해석 versioning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionIntent,
    ActionObservation,
    CallablePort,
    PolicyClearance,
    ToolExecutorPort,
)
from antigravity_k.engine.cognitive.authority import (
    AuthorityDecision,
    AuthorityGrant,
    AuthorityProfile,
    AuthorityVerdict,
)
from antigravity_k.engine.cognitive.experience import (
    DecisionAssessment,
    EpisodeEvaluations,
    EpisodeSignals,
    ExperienceContractError,
    ExperienceCore,
    ExperienceLedger,
    OperationalRecord,
    OutcomeComparison,
    SelectionDisposition,
    SelectionReason,
    compare_outcome,
    evaluate_decision,
    evaluate_execution,
    evaluate_outcome,
    observation_record,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    CognitiveRequestType,
    ConfidenceProfile,
    LoopState,
    ObservationStatus,
    OutcomeStatus,
    Producer,
    ProducerKind,
    Record,
    RiskLevel,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    HardConstraint,
    ReadinessGate,
    ReadinessInputs,
    check_readiness,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRequestEnvelope,
    CognitiveRuntime,
    EpisodeBudget,
    EpisodeDelta,
    EpisodePlan,
    EpisodeRequest,
    EpisodeTermination,
    ThinkOutcome,
    episode_records,
)
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.tools.base_tool import BaseTool
from antigravity_k.tools.tool_registry import ToolRegistry

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
PROJECT = "project:01234567-89ab-cdef-0123-456789abcdef"
EXPERIENCE_ID = new_id(EntityType.EXPERIENCE)
OTHER_EXPERIENCE_ID = new_id(EntityType.EXPERIENCE)
EPISODE = "episode:1"
BODY = Producer(kind=ProducerKind.BODY, actor_id="body:runtime")
PRIMARY = Producer(kind=ProducerKind.BRAIN, actor_id="brain:primary/v1")
HUMAN = Producer(kind=ProducerKind.HUMAN, actor_id="human:mr.k")
SUBJECT = "body:runtime"


def confidence() -> ConfidenceProfile:
    return ConfidenceProfile(
        evidence_strength=0.5, independence=0.5, replication=0.5, contradiction=0.1, context_coverage=0.5
    )


def low_risk() -> RiskProfile:
    return RiskProfile(
        reversibility=RiskLevel.LOW,
        blast_radius=RiskLevel.LOW,
        data_state_loss=RiskLevel.LOW,
        verification=RiskLevel.LOW,
        rollback=RiskLevel.LOW,
    )


def ready_readiness(action_digest: str, *, limits: tuple[str, ...] = ()) -> object:
    return check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool="write_file", scope="src/a.py", expected_outcome="T08", action_digest=action_digest
            ),
            authorized_action_digest=action_digest,
            decision_revision=1,
            state_revision=4,
            authority_revision=1,
            policy_version="policy/v1",
            grounds=("evidence:1",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:1",
                    provenance_uri="tests/cognitive/test_episode.py",
                    provenance_digest="sha256:" + "b" * 64,
                    observed_at=NOW,
                ),
            ),
            constraints=(HardConstraint(name="no_network", satisfied=True),),
            risk=low_risk(),
            limits=limits,
            authority_decision=AuthorityDecision(
                allowed=True,
                verdict=AuthorityVerdict.ALLOWED,
                reason="fixture",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src",
                profile_revision=1,
            ),
        )
    )


def blocked_readiness(action_digest: str) -> object:
    return check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool="write_file", scope="src/a.py", expected_outcome="T08", action_digest=action_digest
            ),
            authorized_action_digest=action_digest,
            grounds=("evidence:1",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:1",
                    provenance_uri="tests/cognitive/test_episode.py",
                    provenance_digest="sha256:" + "b" * 64,
                    observed_at=NOW,
                ),
            ),
            risk=low_risk(),
            authority_decision=None,
        )
    )


def make_action_intent(*, action_key: str = "key-1", target: str = "src/out.txt") -> ActionIntent:
    return ActionIntent(
        action_id=new_id(EntityType.ACTION),
        submission_id=f"submission:{action_key}",
        action_key=action_key,
        tool="fake_write",
        arguments={"file_path": target, "content": "run"},
        scope=target,
        dimension=AuthorityDimension.TOOL_WRITE,
        risk=low_risk(),
        clearance=PolicyClearance(
            authority=AuthorityDecision(
                allowed=True,
                verdict=AuthorityVerdict.ALLOWED,
                reason="fixture",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src",
                profile_revision=1,
            ),
            revision=1,
        ),
        authority_revision=1,
        state_revision=4,
        policy_version="policy/v1",
    )


class FakeThink:
    def __init__(self, outcome: ThinkOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        self.calls.append({"context_ref": context_ref, "signature": request_signature, "attempt": attempt})
        return self.outcome


class FakeRethink:
    def __init__(self, outcomes: Sequence[ThinkOutcome]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def rethink(
        self,
        *,
        previous_judgment_ref: str,
        feedback_refs: Sequence[str],
        affected_grounds: Sequence[str],
        round_index: int,
    ) -> ThinkOutcome:
        self.calls.append(
            {
                "previous": previous_judgment_ref,
                "feedback_refs": tuple(feedback_refs),
                "affected_grounds": tuple(affected_grounds),
                "round": round_index,
            }
        )
        if not self.outcomes:
            return ThinkOutcome(judgment_ref="judgment:exhausted", delta=EpisodeDelta(description="더 볼 것이 없다"))
        return self.outcomes.pop(0)


def plan_with_action(
    *, observation: ActionObservation | None = None, target: str = "src/out.txt"
) -> tuple[EpisodePlan, ActionIntent]:
    intent = make_action_intent(target=target)
    readiness = ready_readiness(intent.args_digest())
    intent = replace(intent, readiness=readiness)
    return EpisodePlan(readiness=readiness, action=intent, expected_outcome="T08 통과", observation=observation), intent


# ─── T08-A simple 경로 ──────────────────────────────────────────────


def test_simple_task_takes_prepare_think_commit_action() -> None:
    port_calls: list[str] = []
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1"))
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(
            port=CallablePort(lambda tool, args, action_id: (port_calls.append(action_id), "ok")[1]),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(
        EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", simple=True, plan=plan)
    )

    assert episode.termination is EpisodeTermination.COMPLETED
    assert episode.states() == (
        LoopState.PREPARE,
        LoopState.THINK,
        LoopState.COMMIT,
        LoopState.ACTION,
        LoopState.OBSERVE,
        LoopState.EXPERIENCE,
    )
    assert episode.counters.brain_calls == 1
    assert episode.counters.rethink_rounds == 0
    assert episode.counters.secondary_requests == 0
    assert episode.counters.verification_calls == 0
    assert episode.counters.tool_requests == 0
    assert len(port_calls) == 1
    assert episode.outcome is not None and episode.outcome.status is OutcomeStatus.MATCH


def test_simple_task_skips_expansion_even_when_requests_exist() -> None:
    envelope = CognitiveRequestEnvelope(
        request_id="request:1",
        request_type=CognitiveRequestType.SECONDARY_BRAIN,
        purpose="전문가 의견",
        target="design",
        expected_decision_impact="대안 확인",
        authority=AuthorityProfile(revision=1),
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(envelope,)))
    plan, _intent = plan_with_action()
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(
        EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", simple=True, plan=plan)
    )

    assert episode.counters.secondary_requests == 0
    assert episode.feedback == ()
    assert LoopState.GOVERN not in episode.states()


# ─── T08-B targeted rethink ─────────────────────────────────────────


def test_denied_request_triggers_targeted_rethink_with_affected_grounds() -> None:
    envelope = CognitiveRequestEnvelope(
        request_id="request:1",
        request_type=CognitiveRequestType.TOOL,
        purpose="추가 근거 확인",
        target="src/a.py",
        expected_decision_impact="ground 보강",
        authority=AuthorityProfile(revision=1),
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(envelope,)))
    rethink = FakeRethink(
        [ThinkOutcome(judgment_ref="judgment:2", delta=EpisodeDelta(judgment=True, description="판단이 좁혀졌다"))]
    )
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    runtime = CognitiveRuntime(
        think=think,
        rethink=rethink,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(
        EpisodeRequest(
            episode_id=EPISODE,
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=plan,
            affected_grounds=("ground:1",),
        )
    )

    assert episode.counters.rethink_rounds == 1
    assert episode.judgment_ref == "judgment:2"
    assert rethink.calls[0]["affected_grounds"] == ("ground:1",)
    assert rethink.calls[0]["feedback_refs"] == ("request:1",)
    assert rethink.calls[0]["previous"] == "judgment:1"
    assert LoopState.TARGETED_RETHINK in episode.states()
    assert episode.feedback[0].executed is False
    assert episode.termination is EpisodeTermination.COMPLETED


def test_authorized_request_executes_through_dispatcher() -> None:
    intent = make_action_intent(action_key="request-key")
    intent = replace(intent, readiness=ready_readiness(intent.args_digest()))
    envelope = CognitiveRequestEnvelope(
        request_id="request:1",
        request_type=CognitiveRequestType.TOOL,
        purpose="근거 수집",
        target="src/a.py",
        expected_decision_impact="ground 보강",
        dimension=AuthorityDimension.TOOL_WRITE,
        action=intent,
        authority=AuthorityProfile(
            revision=1,
            grants=(
                AuthorityGrant(
                    subject=SUBJECT,
                    dimension=AuthorityDimension.TOOL_WRITE,
                    resource_scope="src",
                    allowed_operations=("execute_tool",),
                    granted_by="human:mr.k",
                    issued_at=NOW,
                    revision=1,
                ),
            ),
        ),
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(envelope,)))
    plan, _intent = plan_with_action()
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(
        EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", simple=False, plan=plan)
    )

    assert episode.feedback[0].executed is True
    assert episode.feedback[0].disposition == "APPROVE"
    assert episode.feedback[0].receipt_ref is not None
    assert LoopState.EXECUTE in episode.states()


# ─── T08-C stop conditions ──────────────────────────────────────────


def test_repeated_signature_without_material_delta_stops() -> None:
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1"))
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        budget=EpisodeBudget(repeat_signature_limit=1),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    first = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))
    second = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert first.termination is EpisodeTermination.COMPLETED
    assert second.termination is EpisodeTermination.STOPPED_NO_DELTA
    assert "새 ID는 새 의미가 아니다" in second.note
    # R11: no-delta still leaves an operational trail; never auto-forms Experience.
    assert second.selection is not None
    assert second.selection.disposition is SelectionDisposition.OPERATIONAL_ONLY
    assert runtime.experience.cores_for_episode(EPISODE) == ()
    assert len(think.calls) == 1


def test_non_material_rethink_delta_stops_expansion() -> None:
    envelope = CognitiveRequestEnvelope(
        request_id="request:1",
        request_type=CognitiveRequestType.TOOL,
        purpose="추가 확인",
        target="src/a.py",
        expected_decision_impact="보강",
        authority=AuthorityProfile(revision=1),
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(envelope,)))
    rethink = FakeRethink([ThinkOutcome(judgment_ref="judgment:2", delta=EpisodeDelta(description="표현만 달라졌다"))])
    plan, _intent = plan_with_action()
    runtime = CognitiveRuntime(
        think=think,
        rethink=rethink,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(
        EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", simple=False, plan=plan)
    )

    assert episode.termination is EpisodeTermination.STOPPED_NO_DELTA
    assert episode.note == "No Material Cognitive Delta → stop"
    assert episode.action_run is None
    assert LoopState.ACTION not in episode.states()


# ─── T08-D stop ≠ READY ─────────────────────────────────────────────


def test_not_ready_blocks_before_action_and_does_not_dispatch() -> None:
    port_calls: list[str] = []
    intent = make_action_intent()
    readiness = blocked_readiness(intent.args_digest())
    intent = replace(intent, readiness=readiness)
    plan = EpisodePlan(readiness=readiness, action=intent, expected_outcome="T08 통과")
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(
            port=CallablePort(lambda tool, args, action_id: (port_calls.append(action_id), "ok")[1]),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert episode.termination is EpisodeTermination.BLOCKED_READINESS
    assert episode.note == "stop은 READY가 아니다"
    assert LoopState.BLOCKED_READINESS in episode.states()
    assert LoopState.ACTION not in episode.states()
    assert port_calls == []


def test_missing_readiness_and_missing_context_are_distinct() -> None:
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    no_readiness = runtime.run(
        EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=EpisodePlan())
    )
    no_context = runtime.run(EpisodeRequest(episode_id="episode:2", context_ref="", goal_ref="goal:1"))

    assert no_readiness.termination is EpisodeTermination.BLOCKED_READINESS
    assert no_context.termination is EpisodeTermination.BLOCKED_CONTEXT
    assert no_context.states() == (LoopState.PREPARE, LoopState.BLOCKED_CONTEXT)


def test_action_outcome_unknown_is_not_success() -> None:
    def crashing_port(tool: str, args: Mapping[str, object], action_id: str) -> str:
        _ = (tool, args, action_id)
        raise TimeoutError("no response")

    plan, _intent = plan_with_action()
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(crashing_port), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert episode.termination is EpisodeTermination.ACTION_OUTCOME_UNKNOWN
    assert episode.action_run is not None
    assert episode.action_run.reconciliation_required
    assert episode.outcome is None
    assert LoopState.ACTION_OUTCOME_UNKNOWN in episode.states()


def test_deferred_observation_ends_pending_and_is_selected_for_deferral() -> None:
    plan, _intent = plan_with_action()
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert episode.termination is EpisodeTermination.OBSERVATION_PENDING
    assert episode.state is LoopState.OBSERVE
    assert episode.selection is not None
    assert episode.selection.disposition is SelectionDisposition.DEFERRED
    assert SelectionReason.UNRESOLVED in episode.selection.reasons


# ─── T09-A~E Experience 선별·평가·해석 ───────────────────────────────


def operational(record_id: str = "operational:1") -> OperationalRecord:
    return OperationalRecord(
        record_id=record_id,
        episode_reference=EPISODE,
        kind="EPISODE",
        detail="정상 읽기",
        provenance_uri="episode://1",
        provenance_digest="sha256:" + "a" * 64,
        recorded_at=NOW,
    )


def test_routine_read_is_operational_only_and_still_preserved() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational())

    selection = ledger.select(
        record,
        comparison=compare_outcome("읽기 성공", "읽기 성공"),
        signals=EpisodeSignals(),
        producer=BODY,
        recorded_at=NOW,
        policy_version="policy/v1",
    )

    assert selection.disposition is SelectionDisposition.OPERATIONAL_ONLY
    assert SelectionReason.ROUTINE in selection.reasons
    assert ledger.operational_records == (record,)
    assert selection.policy_version == "policy/v1"
    with pytest.raises(ExperienceContractError):
        ledger.form_experience(
            selection,
            ExperienceCore(experience_id=new_id(EntityType.EXPERIENCE), episode_reference=EPISODE, trigger="정상 읽기"),
            project_id=PROJECT,
            producer=BODY,
            created_at=NOW,
        )


def test_failure_and_recovery_become_experience_with_reason() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:failure"))

    selection = ledger.select(
        record,
        comparison=compare_outcome("쓰기 성공", "권한 거부", delta="쓰기 미실행"),
        signals=EpisodeSignals(failure=True, recovery=True),
        producer=BODY,
        recorded_at=NOW,
        evidence_refs=("evidence:9",),
    )

    assert selection.disposition is SelectionDisposition.EXPERIENCE
    assert {SelectionReason.FAILURE, SelectionReason.RECOVERY, SelectionReason.MATERIAL_DELTA} <= set(selection.reasons)
    assert selection.evidence_refs == ("evidence:9",)


def test_unresolved_outcome_is_deferred_not_learned() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:pending"))
    pending = OutcomeComparison(expected="쓰기", observed=None, delta=None, status=OutcomeStatus.PENDING)

    selection = ledger.select(record, comparison=pending, signals=EpisodeSignals(), producer=BODY, recorded_at=NOW)

    assert selection.disposition is SelectionDisposition.DEFERRED
    assert SelectionReason.UNRESOLVED in selection.reasons
    assert not selection.reusable


def test_expected_equals_observed_can_still_be_experience() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:revalidation"))
    comparison = compare_outcome("환경 A에서 성공", "환경 A에서 성공")

    selection = ledger.select(
        record,
        comparison=comparison,
        signals=EpisodeSignals(environment_difference=True, independent_revalidation=True),
        producer=BODY,
        recorded_at=NOW,
    )

    assert comparison.matched_expected
    assert selection.disposition is SelectionDisposition.EXPERIENCE
    assert SelectionReason.INDEPENDENT_REVALIDATION in selection.reasons


def test_three_evaluations_are_separate_procedures() -> None:
    comparison = compare_outcome("배포 성공", "배포 실패", delta="실패")
    outcome = evaluate_outcome(comparison)
    decision = evaluate_decision(comparison, available_at_decision=True, reason="당시 근거로 합리적이었다")
    execution = evaluate_execution(succeeded=False, receipt_ref="receipt:1", reason="도구가 실패를 반환")
    evaluations = EpisodeEvaluations(outcome=outcome, decision=decision, execution=execution)

    assert outcome.status is OutcomeStatus.DEVIATION
    assert decision.status is OutcomeStatus.MATCH
    assert decision.available_at_decision
    assert execution.status is OutcomeStatus.FAILED
    assert not evaluations.agrees

    later_knowledge = evaluate_decision(
        comparison, available_at_decision=False, reason="나중에 얻은 지식으로 다시 본다"
    )
    unknown = evaluate_outcome(compare_outcome("배포 성공", None))
    assert later_knowledge.status is OutcomeStatus.DEVIATION
    assert unknown.status is OutcomeStatus.UNKNOWN
    assert (
        evaluate_decision(compare_outcome("배포 성공", None), available_at_decision=True, reason="결과 불명").status
        is OutcomeStatus.UNKNOWN
    )


def test_supplement_appends_delayed_observation_without_touching_core() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:delayed"))
    selection = ledger.select(
        record,
        comparison=compare_outcome("쓰기 성공", "권한 거부", delta="미실행"),
        signals=EpisodeSignals(failure=True),
        producer=BODY,
        recorded_at=NOW,
    )
    core = ledger.form_experience(
        selection,
        ExperienceCore(
            experience_id=EXPERIENCE_ID,
            episode_reference=EPISODE,
            trigger="권한 거부",
            remaining_unknowns=("권한 재요청 결과",),
        ),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    digest_before = ledger.core_digest_history(core.experience_id)

    observation = observation_record(
        project_id=PROJECT,
        producer=BODY,
        raw="재요청 후 성공",
        method="tool_receipt",
        source="tool_executor",
        observed_at=NOW,
        status=ObservationStatus.DELAYED,
    )
    supplement = ledger.supplement(core.experience_id, observation=observation, note="후속 관측", recorded_at=NOW)

    assert supplement.observation_ref == observation.id
    assert ledger.core_digest_history(core.experience_id) == digest_before
    assert ledger.core(core.experience_id) is not None


def test_interpretation_requires_primary_or_human_and_versions_history() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:meaning"))
    selection = ledger.select(
        record,
        comparison=compare_outcome("전제 검증", "전제 반증", delta="반증"),
        signals=EpisodeSignals(assumption_tested=True),
        producer=BODY,
        recorded_at=NOW,
    )
    core = ledger.form_experience(
        selection,
        ExperienceCore(experience_id=OTHER_EXPERIENCE_ID, episode_reference=EPISODE, trigger="전제 반증"),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    with pytest.raises(ExperienceContractError):
        ledger.interpret(
            core.experience_id,
            author=BODY,
            meaning="Body가 의미를 해석한다",
            confidence_profile=confidence(),
            recorded_at=NOW,
        )

    first = ledger.interpret(
        core.experience_id,
        author=PRIMARY,
        meaning="전제가 환경 A에서만 성립한다",
        confidence_profile=confidence(),
        recorded_at=NOW,
        project_id=PROJECT,
        created_at=NOW,
    )
    second = ledger.interpret(
        core.experience_id,
        author=HUMAN,
        meaning="환경 A의 범위를 좁힌다",
        confidence_profile=confidence(),
        recorded_at=NOW,
        project_id=PROJECT,
        created_at=NOW,
    )

    assert (first.revision, second.revision) == (1, 2)
    assert second.supersedes == first.interpretation_id
    assert ledger.core_digest_history(core.experience_id) == (core.digest(),)
    assert ledger.interpretations(core.experience_id) == (first, second)


def test_duplicate_operational_record_is_rejected() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational())

    with pytest.raises(ExperienceContractError):
        ledger.record_operational(record)


def test_selection_requires_operational_record_first() -> None:
    ledger = ExperienceLedger()

    with pytest.raises(ExperienceContractError):
        ledger.select(
            operational("operational:missing"),
            comparison=compare_outcome("a", "a"),
            signals=EpisodeSignals(),
            producer=BODY,
            recorded_at=NOW,
        )


# ─── 실제 표면 ──────────────────────────────────────────────────────


class _AppendTool(BaseTool):
    @property
    def name(self) -> str:
        return "fake_write"

    @property
    def description(self) -> str:
        return "test-only append writer"

    @property
    def parameters_schema(self) -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    def execute(self, **kwargs: object) -> object:
        path = Path(str(kwargs["file_path"]))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(str(kwargs.get("content", "")) + "\n")
        return f"appended {path.name}"


def _registry(tmp_path: Path) -> ToolRegistry:
    registry = ToolRegistry(project_root=str(tmp_path))
    getattr(registry, "install")(_AppendTool())
    return registry


def _executor(tmp_path: Path, registry: ToolRegistry) -> ToolExecutor:
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        executor = ToolExecutor(
            tool_registry=registry,
            permission_gate=registry.permission_gate,
            project_root=str(tmp_path),
        )
    setattr(executor, "_immune_system", None)
    return executor


def test_episode_runs_through_real_tool_executor_and_records_events(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    executor = _executor(tmp_path, registry)
    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    target = tmp_path / "episode.txt"
    intent = make_action_intent(target=str(target))
    readiness = ready_readiness(intent.args_digest())
    intent = replace(intent, readiness=readiness)
    plan = EpisodePlan(
        readiness=readiness,
        action=intent,
        expected_outcome="appended",
        observation=ActionObservation(observed=True, succeeded=True, detail="appended"),
    )
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(
            port=ToolExecutorPort(executor=executor, failure_predicate=result_indicates_failure),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )

    episode = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert episode.termination is EpisodeTermination.COMPLETED
    assert target.read_text(encoding="utf-8") == "run\n"
    assert episode.evaluations is not None
    assert episode.evaluations.execution.status is OutcomeStatus.MATCH
    assert episode.action_run is not None
    assert episode.action_run.receipt is not None
    assert episode.action_run.receipt.status.value == "COMPLETED"

    records: tuple[Record, ...] = episode_records(episode, project_id=PROJECT, producer=BODY, created_at=NOW)
    assert len(records) == len(episode.events)
    commit = store.commit_records(list(records))
    assert commit.committed_ids == tuple(record.id for record in records)
    assert store.verify_digests() == len(records)


def test_store_adapter_for_readiness_is_used_by_runtime() -> None:
    gate = ReadinessGate()
    intent = make_action_intent()
    readiness = ready_readiness(intent.args_digest())

    assert gate.assert_fresh(readiness, intent.freshness()).fresh

    stale = replace(intent, state_revision=99)
    check = gate.revalidate(readiness, stale.freshness())

    assert not check.fresh
    assert check.changed == ("state_revision",)


# ─── R07 feedback / rethink loop ─────────────────────────────────────


def test_r07_a1_successful_evidence_updates_plan_before_commit() -> None:
    intent = make_action_intent(action_key="collect-evidence")
    intent = replace(intent, readiness=ready_readiness(intent.args_digest()))
    envelope = CognitiveRequestEnvelope(
        request_id="request:evidence",
        request_type=CognitiveRequestType.TOOL,
        purpose="근거 수집",
        target="src/a.py",
        expected_decision_impact="ground 보강",
        evidence_revision="ev:1",
        dimension=AuthorityDimension.TOOL_WRITE,
        action=intent,
        authority=AuthorityProfile(
            revision=1,
            grants=(
                AuthorityGrant(
                    subject=SUBJECT,
                    dimension=AuthorityDimension.TOOL_WRITE,
                    resource_scope="src",
                    allowed_operations=("execute_tool",),
                    granted_by="human:mr.k",
                    issued_at=NOW,
                    revision=1,
                ),
            ),
        ),
    )
    initial_plan, _ = plan_with_action(target="src/old.txt")
    updated_plan, updated_intent = plan_with_action(
        observation=ActionObservation(observed=True, succeeded=True, detail="새 plan으로 완료"),
        target="src/new.txt",
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(envelope,)))
    rethink = FakeRethink(
        [
            ThinkOutcome(
                judgment_ref="judgment:2",
                delta=EpisodeDelta(judgment=True, ground=True, action=True, description="새 evidence로 plan 갱신"),
                plan=updated_plan,
            )
        ]
    )
    port_targets: list[str] = []
    runtime = CognitiveRuntime(
        think=think,
        rethink=rethink,
        actions=ActionDispatcher(
            port=CallablePort(
                lambda tool, args, action_id: (
                    port_targets.append(str(args.get("path") or args.get("target") or tool)),
                    "ok",
                )[1]
            ),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(
            episode_id="episode:r07-a1",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=initial_plan,
        )
    )
    assert episode.termination is EpisodeTermination.COMPLETED
    assert episode.judgment_ref == "judgment:2"
    assert rethink.calls and "request:evidence" in rethink.calls[0]["feedback_refs"]
    assert episode.feedback[0].executed is True
    assert episode.action_run is not None
    assert episode.action_run.intent.scope == "src/new.txt"
    assert episode.action_run.intent.arguments.get("file_path") == "src/new.txt"


def test_r07_a2_deny_then_safe_alternative_runs_next_round() -> None:
    denied = CognitiveRequestEnvelope(
        request_id="request:deny",
        request_type=CognitiveRequestType.TOOL,
        purpose="위험 도구",
        target="src/secret.py",
        expected_decision_impact="보강",
        authority=AuthorityProfile(revision=1),
    )
    alt_intent = make_action_intent(action_key="safe-alt", target="src/safe.py")
    alt_intent = replace(alt_intent, readiness=ready_readiness(alt_intent.args_digest()))
    alternative = CognitiveRequestEnvelope(
        request_id="request:alt",
        request_type=CognitiveRequestType.TOOL,
        purpose="안전한 대안",
        target="src/safe.py",
        expected_decision_impact="보강",
        evidence_revision="ev:2",
        dimension=AuthorityDimension.TOOL_WRITE,
        action=alt_intent,
        authority=AuthorityProfile(
            revision=1,
            grants=(
                AuthorityGrant(
                    subject=SUBJECT,
                    dimension=AuthorityDimension.TOOL_WRITE,
                    resource_scope="src",
                    allowed_operations=("execute_tool",),
                    granted_by="human:mr.k",
                    issued_at=NOW,
                    revision=1,
                ),
            ),
        ),
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(denied,)))
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="ok"))
    rethink = FakeRethink(
        [
            ThinkOutcome(
                judgment_ref="judgment:2",
                delta=EpisodeDelta(action=True, description="안전한 대안으로 교체"),
                requests=(alternative,),
            )
        ]
    )
    runtime = CognitiveRuntime(
        think=think,
        rethink=rethink,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(
            episode_id="episode:r07-a2",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=plan,
            affected_grounds=("ground:1",),
        )
    )
    assert episode.counters.rethink_rounds >= 1
    assert any(item.request_id == "request:alt" and item.executed for item in episode.feedback)
    assert any(item.request_id == "request:deny" and not item.executed for item in episode.feedback)
    assert LoopState.EXECUTE in episode.states()


def test_r07_a3_repeat_signature_stops_but_new_evidence_revision_retries() -> None:
    def envelope(request_id: str, evidence_revision: str, action_key: str) -> CognitiveRequestEnvelope:
        intent = make_action_intent(action_key=action_key)
        intent = replace(intent, readiness=ready_readiness(intent.args_digest()))
        return CognitiveRequestEnvelope(
            request_id=request_id,
            request_type=CognitiveRequestType.TOOL,
            purpose="동일 목적",
            target="src/a.py",
            expected_decision_impact="보강",
            evidence_revision=evidence_revision,
            dimension=AuthorityDimension.TOOL_WRITE,
            action=intent,
            authority=AuthorityProfile(
                revision=1,
                grants=(
                    AuthorityGrant(
                        subject=SUBJECT,
                        dimension=AuthorityDimension.TOOL_WRITE,
                        resource_scope="src",
                        allowed_operations=("execute_tool",),
                        granted_by="human:mr.k",
                        issued_at=NOW,
                        revision=1,
                    ),
                ),
            ),
        )

    first = envelope("request:1", "ev:1", "key-a")
    repeat = envelope("request:2", "ev:1", "key-b")
    changed = envelope("request:3", "ev:2", "key-c")
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(first,)))
    rethink = FakeRethink(
        [
            ThinkOutcome(
                judgment_ref="judgment:2",
                delta=EpisodeDelta(ground=True, description="재시도"),
                requests=(repeat, changed),
            )
        ]
    )
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="ok"))
    runtime = CognitiveRuntime(
        think=think,
        rethink=rethink,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        budget=EpisodeBudget(repeat_signature_limit=1, expansion_rounds=3),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(
            episode_id="episode:r07-a3",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=plan,
        )
    )
    by_id = {item.request_id: item for item in episode.feedback}
    assert by_id["request:1"].executed is True
    assert by_id["request:2"].disposition == "REPEAT_STOP"
    assert by_id["request:2"].executed is False
    assert by_id["request:3"].executed is True


def test_r07_a4_total_request_budget_caps_large_initial_batch() -> None:
    envelopes = tuple(
        CognitiveRequestEnvelope(
            request_id=f"request:{i}",
            request_type=CognitiveRequestType.TOOL,
            purpose=f"purpose-{i}",
            target=f"src/{i}.py",
            expected_decision_impact="x",
            authority=AuthorityProfile(revision=1),
        )
        for i in range(100)
    )
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=envelopes))
    plan, _ = plan_with_action()
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        budget=EpisodeBudget(max_total_requests=5, expansion_rounds=0),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(
            episode_id="episode:r07-a4",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=plan,
        )
    )
    assert episode.termination is EpisodeTermination.STOPPED_BUDGET
    assert len(episode.feedback) <= 5
    assert LoopState.ACTION not in episode.states()


def test_r07_a5_simple_and_no_delta_stop_without_extra_secondary() -> None:
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1"))
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="ok"))
    runtime = CognitiveRuntime(
        think=think,
        rethink=FakeRethink([]),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    simple = runtime.run(
        EpisodeRequest(episode_id="episode:r07-a5s", context_ref="context:1", goal_ref="goal:1", simple=True, plan=plan)
    )
    assert simple.termination is EpisodeTermination.COMPLETED
    assert simple.counters.rethink_rounds == 0
    assert simple.counters.secondary_requests == 0

    denied = CognitiveRequestEnvelope(
        request_id="request:1",
        request_type=CognitiveRequestType.TOOL,
        purpose="x",
        target="src/a.py",
        expected_decision_impact="y",
        authority=AuthorityProfile(revision=1),
    )
    think2 = FakeThink(ThinkOutcome(judgment_ref="judgment:1", requests=(denied,)))
    rethink = FakeRethink([ThinkOutcome(judgment_ref="judgment:2", delta=EpisodeDelta(description="표현만"))])
    runtime2 = CognitiveRuntime(
        think=think2,
        rethink=rethink,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    stopped = runtime2.run(
        EpisodeRequest(
            episode_id="episode:r07-a5n",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=False,
            plan=plan,
        )
    )
    assert stopped.termination is EpisodeTermination.STOPPED_NO_DELTA


# ─── R11 operational trail + selected Experience persistence ─────────


def test_r11_a1_stopped_no_delta_has_operational_trail_without_experience() -> None:
    think = FakeThink(ThinkOutcome(judgment_ref="judgment:1"))
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    sunk: list[Record] = []
    runtime = CognitiveRuntime(
        think=think,
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        budget=EpisodeBudget(repeat_signature_limit=1),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
        record_sink=lambda records: sunk.extend(records),
    )
    runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))
    stopped = runtime.run(EpisodeRequest(episode_id=EPISODE, context_ref="context:1", goal_ref="goal:1", plan=plan))

    assert stopped.termination is EpisodeTermination.STOPPED_NO_DELTA
    assert stopped.selection is not None
    assert stopped.selection.disposition is SelectionDisposition.OPERATIONAL_ONLY
    assert any(r.record_id.startswith("operational:") for r in runtime.experience.operational_records)
    assert runtime.experience.cores_for_episode(EPISODE) == ()
    assert len(sunk) >= 1


def test_r11_a2_deviation_core_survives_restart_via_canonical_records() -> None:
    sunk: list[Record] = []
    ledger = ExperienceLedger()
    context_ref = new_id(EntityType.CONTEXT_PACKAGE)
    judgment_ref = new_id(EntityType.BRAIN_JUDGMENT)
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref=judgment_ref)),
        actions=ActionDispatcher(
            port=CallablePort(lambda tool, args, action_id: "wrong"),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
        experience=ledger,
        record_sink=lambda records: sunk.extend(records),
    )
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="편차 결과"))
    plan = EpisodePlan(
        readiness=plan.readiness, action=plan.action, expected_outcome="기대 결과", observation=plan.observation
    )
    episode = runtime.run(
        EpisodeRequest(episode_id="episode:r11-a2", context_ref=context_ref, goal_ref="goal:1", plan=plan)
    )
    assert episode.selection is not None
    assert episode.selection.disposition is SelectionDisposition.EXPERIENCE
    cores = ledger.cores_for_episode("episode:r11-a2")
    assert len(cores) == 1
    core = cores[0]
    digest = core.digest()
    experience_records = [r for r in sunk if same_enum(r.entity_type, EntityType.EXPERIENCE)]
    assert len(experience_records) == 1

    restored = ExperienceLedger()
    restored.ingest_core_record(experience_records[0], episode_reference="episode:r11-a2")
    again = restored.cores_for_episode("episode:r11-a2")
    assert len(again) == 1
    assert again[0].experience_id == core.experience_id
    assert again[0].digest() == digest


def test_r11_a3_routine_match_stays_operational_only() -> None:
    plan, _intent = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(episode_id="episode:r11-a3", context_ref="context:1", goal_ref="goal:1", plan=plan)
    )
    assert episode.termination is EpisodeTermination.COMPLETED
    assert episode.selection is not None
    assert episode.selection.disposition is SelectionDisposition.OPERATIONAL_ONLY
    assert SelectionReason.ROUTINE in episode.selection.reasons
    assert runtime.experience.cores_for_episode("episode:r11-a3") == ()


def test_r11_a4_provider_neutral_core_reader() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:r11-a4"))
    selection = ledger.select(
        record,
        comparison=compare_outcome("쓰기 성공", "권한 거부", delta="쓰기 미실행"),
        signals=EpisodeSignals(failure=True),
        producer=BODY,
        recorded_at=NOW,
    )
    context_ref = new_id(EntityType.CONTEXT_PACKAGE)
    judgment_ref = new_id(EntityType.BRAIN_JUDGMENT)
    core = ledger.form_experience(
        selection,
        ExperienceCore(
            experience_id=new_id(EntityType.EXPERIENCE),
            episode_reference=EPISODE,
            trigger="실패",
            context_ref=context_ref,
            judgment_ref=judgment_ref,
        ),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    stored = ledger.records[-1]
    other = ExperienceLedger()
    rebuilt = other.ingest_core_record(stored, episode_reference=EPISODE)
    assert rebuilt.experience_id == core.experience_id
    assert rebuilt.context_ref == context_ref
    assert rebuilt.judgment_ref == judgment_ref
    assert rebuilt.digest() == core.digest()


def test_r11_a5_deferred_then_late_interpretation_leaves_core_bytes() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:r11-a5"))
    pending = OutcomeComparison(expected="쓰기", observed=None, delta=None, status=OutcomeStatus.PENDING)
    deferred = ledger.select(record, comparison=pending, signals=EpisodeSignals(), producer=BODY, recorded_at=NOW)
    assert deferred.disposition is SelectionDisposition.DEFERRED

    late = ledger.select(
        record,
        comparison=compare_outcome("쓰기", "실패", delta="미실행"),
        signals=EpisodeSignals(failure=True),
        producer=BODY,
        recorded_at=NOW,
    )
    assert late.disposition is SelectionDisposition.EXPERIENCE
    core = ledger.form_experience(
        late,
        ExperienceCore(
            experience_id=new_id(EntityType.EXPERIENCE),
            episode_reference=EPISODE,
            trigger="late-obs",
        ),
        project_id=PROJECT,
        producer=BODY,
        created_at=NOW,
    )
    before = core.digest()
    ledger.interpret(
        core.experience_id,
        author=PRIMARY,
        meaning="초기 해석",
        confidence_profile=confidence(),
        recorded_at=NOW,
        project_id=PROJECT,
        created_at=NOW,
    )
    ledger.interpret(
        core.experience_id,
        author=PRIMARY,
        meaning="후속 해석",
        confidence_profile=confidence(),
        recorded_at=NOW,
        project_id=PROJECT,
        created_at=NOW,
    )
    assert ledger.core(core.experience_id).digest() == before
    assert len(ledger.interpretations(core.experience_id)) == 2


def test_r11_a6_selected_core_idempotent_on_replay() -> None:
    ledger = ExperienceLedger()
    record = ledger.record_operational(operational("operational:r11-a6"))
    selection = ledger.select(
        record,
        comparison=compare_outcome("a", "b", delta="d"),
        signals=EpisodeSignals(failure=True),
        producer=BODY,
        recorded_at=NOW,
    )
    core_spec = ExperienceCore(
        experience_id=EXPERIENCE_ID,
        episode_reference=EPISODE,
        trigger="replay",
    )
    first = ledger.form_experience(selection, core_spec, project_id=PROJECT, producer=BODY, created_at=NOW)
    second = ledger.form_experience(selection, core_spec, project_id=PROJECT, producer=BODY, created_at=NOW)
    assert first.experience_id == second.experience_id == EXPERIENCE_ID
    assert len(ledger.cores_for_episode(EPISODE)) == 1


# ─── R12 decision quality vs outcome axes ────────────────────────────


def test_r12_a1_good_outcome_poor_decision_are_separate_axes() -> None:
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    plan = EpisodePlan(
        readiness=plan.readiness,
        action=plan.action,
        expected_outcome="T08 통과",
        observation=plan.observation,
        decision_assessment=DecisionAssessment(
            status=OutcomeStatus.FAILED,
            available_at_decision=False,
            reason="당시 근거가 부실했다",
            evidence_refs=("evidence:thin",),
        ),
    )
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(episode_id="episode:r12-a1", context_ref="context:1", goal_ref="goal:1", plan=plan)
    )
    assert episode.evaluations is not None
    assert episode.evaluations.outcome.status is OutcomeStatus.MATCH
    assert episode.evaluations.decision.status is OutcomeStatus.FAILED
    assert episode.evaluations.execution.status is OutcomeStatus.MATCH
    assert not episode.evaluations.agrees


def test_r12_a2_bad_outcome_sound_contemporaneous_decision() -> None:
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=False, detail="환경 장애"))
    plan = EpisodePlan(
        readiness=plan.readiness,
        action=plan.action,
        expected_outcome="T08 통과",
        observation=plan.observation,
        decision_assessment=DecisionAssessment(
            status=OutcomeStatus.MATCH,
            available_at_decision=True,
            reason="당시 정보로는 합리적 선택이었다",
            evidence_refs=("evidence:then",),
        ),
    )
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(episode_id="episode:r12-a2", context_ref="context:1", goal_ref="goal:1", plan=plan)
    )
    assert episode.evaluations is not None
    assert episode.evaluations.outcome.status is OutcomeStatus.DEVIATION
    assert episode.evaluations.decision.status is OutcomeStatus.MATCH
    assert episode.evaluations.decision.available_at_decision is True
    assert episode.evaluations.execution.status is OutcomeStatus.FAILED


def test_r12_a3_no_assessment_means_decision_unknown_despite_readiness() -> None:
    plan, _ = plan_with_action(observation=ActionObservation(observed=True, succeeded=True, detail="T08 통과"))
    assert plan.readiness is not None
    runtime = CognitiveRuntime(
        think=FakeThink(ThinkOutcome(judgment_ref="judgment:1")),
        actions=ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    episode = runtime.run(
        EpisodeRequest(episode_id="episode:r12-a3", context_ref="context:1", goal_ref="goal:1", plan=plan)
    )
    assert episode.evaluations is not None
    assert episode.evaluations.outcome.status is OutcomeStatus.MATCH
    assert episode.evaluations.decision.status is OutcomeStatus.UNKNOWN
    assert episode.evaluations.decision.available_at_decision is False
    assert (
        "readiness" in episode.evaluations.decision.reason.lower()
        or "unevaluated" in episode.evaluations.decision.reason.lower()
    )
