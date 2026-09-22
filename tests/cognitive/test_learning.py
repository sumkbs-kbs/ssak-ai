"""T10 — Experience가 미래 행동을 바꾸는 경로 시험 (P09).

검증 범위(T10-A~E):
- A: 한 실패·한 Brain 해석·grade/cooldown trigger만으로 active policy가 바뀌지 않는다. source independence와
  별도 validation을 강제하고 human-assisted 후보도 같은 검증을 지난다.
- B: Evaluator/PatternBuilder의 기계 집계와 의미 해석을 분리한다. 의미 해석은 Primary/human만 하고,
  근거 없는 causal claim은 FACT·검증된 Principle이 되지 않는다.
- C: confidence가 높아도 applicability가 MISMATCH면 자동 적용하지 않는다. challenged/scoped/revised/retired는
  append 사건이고 원본 digest는 불변이다.
- D: candidate → ValidationReport → PolicyActivation → 다음 task의 실제 선택 → outcome을
  BehaviorChangeTrace로 연결한다. CAS 충돌을 처리하고 rollback 후 선택이 복원된다.
- E: 다른 운영 target을 추가할 수 있고, 기존 grant 안의 위임 조정과 신규 grant/ceiling 발급을 구분한다.
  learned policy는 protected authority/human ceiling을 바꾸지 못한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.authority import (
    AuthorityGrant,
    AuthorityProfile,
    AuthorityViolation,
)
from antigravity_k.engine.cognitive.experience import (
    DecisionEvaluation,
    EpisodeEvaluations,
    ExecutionEvaluation,
    OutcomeEvaluation,
)
from antigravity_k.engine.cognitive.learning import (
    ApplicabilityDisposition,
    CandidateKind,
    CandidateProposer,
    CandidateRequest,
    CandidateStore,
    EpisodeObservation,
    EvaluationSummary,
    EvidenceMismatchError,
    ExperienceEvaluator,
    HeldOutValidator,
    InsufficientEvidenceError,
    KnowledgeLedger,
    KnowledgeTarget,
    LearningCandidate,
    LearningContractError,
    MeaningInterpreter,
    MeaningRequest,
    NotPromotableError,
    PolicyTargetRefused,
    SemanticAuthorityError,
    SemanticReading,
    TriggerSource,
    ValidationBypassRefused,
    ValidationCriterion,
    ValidationObservation,
    ValidationReport,
    ValidationRole,
    ValidationSplit,
    new_split_id,
)
from antigravity_k.engine.cognitive.models import (
    ApplicabilityLevel,
    ApplicabilityProfile,
    AuthorityDimension,
    ConfidenceProfile,
    EntityType,
    EvidenceKind,
    EvidencePayload,
    KnowledgeLifecycle,
    OutcomeStatus,
    PolicyTarget,
    Producer,
    ProducerKind,
    Provenance,
    Record,
    ScalarParameter,
)
from antigravity_k.engine.cognitive.policy_store import (
    ActivationKind,
    AuthorityRevokedError,
    AuthorityWideningRefused,
    PolicyCasConflict,
    PolicyContractError,
    PolicyStore,
    PromotionRefused,
    RetiredVersionRefused,
)
from antigravity_k.engine.cognitive.protected_targets import ProtectedWriteGuard
from antigravity_k.engine.cognitive.references import new_id
from antigravity_k.engine.cognitive.store import CanonicalStore

NOW = datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 22, 5, 0, 0, tzinfo=UTC)
LATEST = datetime(2026, 9, 22, 6, 0, 0, tzinfo=UTC)
BODY = Producer(kind=ProducerKind.BODY, actor_id="body:test")
PRIMARY = Producer(kind=ProducerKind.BRAIN, actor_id="brain:primary")
HUMAN = Producer(kind=ProducerKind.HUMAN, actor_id="human:operator")
PROJECT = new_id(EntityType.PROJECT)


# ─── fixture ────────────────────────────────────────────────────────


def confidence(strength: float = 0.9) -> ConfidenceProfile:
    return ConfidenceProfile(
        evidence_strength=strength,
        independence=strength,
        replication=strength,
        contradiction=0.1,
        context_coverage=strength,
    )


def evaluations(
    outcome: OutcomeStatus,
    *,
    decision: OutcomeStatus | None = None,
    available_at_decision: bool = False,
    execution: OutcomeStatus = OutcomeStatus.MATCH,
) -> EpisodeEvaluations:
    return EpisodeEvaluations(
        outcome=OutcomeEvaluation(
            status=outcome,
            expected="one appended line",
            observed="no appended line",
            delta="expected → observed",
        ),
        decision=DecisionEvaluation(
            status=decision if decision is not None else outcome,
            available_at_decision=available_at_decision,
            reason="fixture decision evaluation",
        ),
        execution=ExecutionEvaluation(status=execution, reason="fixture execution evaluation"),
    )


def observation(
    index: int,
    *,
    raw: str | None = None,
    outcome: OutcomeStatus = OutcomeStatus.DEVIATION,
    decision: OutcomeStatus | None = None,
    available_at_decision: bool = False,
    execution: OutcomeStatus = OutcomeStatus.MATCH,
    evidence: tuple[str, ...] | None = None,
) -> EpisodeObservation:
    return EpisodeObservation(
        episode_id=f"episode:{index}",
        task_id=f"task:learn-{index}",
        raw_material_digest=raw if raw is not None else f"sha256:raw-{index}",
        evaluations=evaluations(
            outcome,
            decision=decision,
            available_at_decision=available_at_decision,
            execution=execution,
        ),
        evidence_ids=evidence if evidence is not None else (new_id(EntityType.EVIDENCE),),
        producer=BODY,
    )


def learning_observations(
    count: int = 2,
    *,
    outcome: OutcomeStatus = OutcomeStatus.DEVIATION,
    decision: OutcomeStatus | None = None,
    available_at_decision: bool = False,
    evidence: tuple[str, ...] | None = None,
) -> tuple[EpisodeObservation, ...]:
    return tuple(
        observation(
            index,
            outcome=outcome,
            decision=decision,
            available_at_decision=available_at_decision,
            evidence=evidence,
        )
        for index in range(1, count + 1)
    )


def summary_of(observations: tuple[EpisodeObservation, ...]) -> EvaluationSummary:
    return ExperienceEvaluator().aggregate(observations)


def policy_candidate(
    summary: EvaluationSummary,
    *,
    target: PolicyTarget = PolicyTarget.CONTEXT_DEPTH,
    rule: str = "context_depth=2 when required config evidence is missing",
    scope: str = "goal:fixture + environment:local",
    parameters: dict[str, ScalarParameter] | None = None,
    triggers: tuple[TriggerSource, ...] = (TriggerSource.FAILURE,),
    producer: Producer = BODY,
    reading: SemanticReading | None = None,
    guard: ProtectedWriteGuard | None = None,
) -> LearningCandidate:
    request = CandidateRequest(
        kind=CandidateKind.POLICY,
        rule=rule,
        scope=scope,
        target=target,
        parameters=parameters if parameters is not None else {"extra_depth": 1},
        trigger_sources=triggers,
        semantic_reading=reading,
    )
    return CandidateProposer(guard=guard).propose(
        summary, request, project_id=PROJECT, producer=producer, created_at=NOW
    )


def pattern_candidate(
    summary: EvaluationSummary,
    *,
    rule: str = "config evidence handle이 얕은 context에서 누락된다",
    triggers: tuple[TriggerSource, ...] = (TriggerSource.FAILURE,),
    producer: Producer = BODY,
    reading: SemanticReading | None = None,
) -> LearningCandidate:
    request = CandidateRequest(
        kind=CandidateKind.PATTERN,
        rule=rule,
        scope="goal:fixture",
        trigger_sources=triggers,
        semantic_reading=reading,
        falsification_criteria=("config evidence가 있는데도 재시도가 나면 반증된다",),
        evaluation_plan="frozen split에서 재시도 횟수를 센다",
    )
    return CandidateProposer().propose(summary, request, project_id=PROJECT, producer=producer, created_at=NOW)


def criterion(**overrides: object) -> ValidationCriterion:
    values: dict[str, object] = {
        "experiment_id": "exp:fixture-1",
        "metric_name": "task_success_rate",
        "minimum_value": 0.8,
        "registered_at": NOW,
        "minimum_samples": 2,
    }
    values.update(overrides)
    return ValidationCriterion(**values)  # type: ignore[arg-type]


def validation_split(
    *,
    role: ValidationRole = ValidationRole.VALIDATION,
    task_ids: tuple[str, ...] = ("task:val-1", "task:val-2"),
) -> ValidationSplit:
    return ValidationSplit(
        split_id=new_split_id(role),
        role=role,
        task_ids=task_ids,
        source="fixtures/cognitive/frozen_split.json",
        registered_at=NOW,
        manifest_digest="sha256:" + "a" * 64,
    )


def validation_observations(
    *successes: bool | None, negative_transfer: bool = False
) -> tuple[ValidationObservation, ...]:
    return tuple(
        ValidationObservation(task_id=f"task:val-{index}", success=success, negative_transfer=negative_transfer)
        for index, success in enumerate(successes, start=1)
    )


def validate(
    candidate: LearningCandidate,
    *,
    role: ValidationRole = ValidationRole.VALIDATION,
    observations: tuple[ValidationObservation, ...] | None = None,
    criterion_overrides: dict[str, object] | None = None,
) -> ValidationReport:
    return HeldOutValidator().validate(
        candidate,
        split=validation_split(role=role),
        criterion=criterion(**(criterion_overrides or {})),
        observations=observations if observations is not None else validation_observations(True, True),
        generated_at=LATER,
    )


def reading(*, author: Producer = PRIMARY, causal: str = "") -> SemanticReading:
    return SemanticReading(
        meaning="config evidence 누락이 재시도를 만든다",
        author=author,
        confidence_profile=confidence(0.4),
        causal_claim=causal,
        interpreter_version="primary/fixture-1",
    )


@dataclass
class SpyInterpreter:
    """의미 해석 호출 횟수를 세는 Primary 대역."""

    reading: SemanticReading
    calls: list[MeaningRequest] = field(default_factory=list)

    def read(self, request: MeaningRequest) -> SemanticReading:
        self.calls.append(request)
        return self.reading


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "docs/ssak-ai-core").mkdir(parents=True)
    (root / "docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md").write_text("constitution\n", encoding="utf-8")
    return root


def activated_policy(
    *,
    target: PolicyTarget = PolicyTarget.CONTEXT_DEPTH,
    parameters: dict[str, ScalarParameter] | None = None,
    version: str = "1.0.0",
    guard: ProtectedWriteGuard | None = None,
    observations: tuple[EpisodeObservation, ...] | None = None,
) -> tuple[CandidateStore, PolicyStore, LearningCandidate, str]:
    """candidate → validation → registration을 거친 뒤 active version을 돌려준다."""

    candidates = CandidateStore()
    store = PolicyStore(guard=guard)
    candidate = policy_candidate(
        summary_of(observations if observations is not None else learning_observations(2)),
        target=target,
        parameters=parameters,
        guard=guard,
    )
    candidates.append(candidate)
    report = validate(candidate)
    candidates.add_report(report)
    store.register(candidate, report, version=version, producer=BODY, created_at=NOW)
    store.promote(
        candidate.candidate_id,
        version=version,
        expected_active_version=None,
        actor=BODY,
        reason="T10 fixture activation",
        occurred_at=LATER,
    )
    return candidates, store, candidate, version


# ─── T10-A: 승격 경계 ───────────────────────────────────────────────


def test_single_failure_is_not_enough_for_validation() -> None:
    candidate = policy_candidate(summary_of(learning_observations(1)))
    with pytest.raises(InsufficientEvidenceError):
        validate(candidate)


def test_duplicate_raw_material_is_not_independent_replication() -> None:
    observations = (observation(1, raw="sha256:same-source"), observation(2, raw="sha256:same-source"))
    summary = summary_of(observations)
    assert summary.analysis.observation_count == 2
    assert summary.independent_episode_count == 1
    with pytest.raises(InsufficientEvidenceError):
        validate(policy_candidate(summary))


def test_grade_or_cooldown_trigger_alone_is_refused() -> None:
    candidate = policy_candidate(
        summary_of(learning_observations(2)),
        triggers=(TriggerSource.GRADE, TriggerSource.COOLDOWN),
    )
    with pytest.raises(InsufficientEvidenceError, match="trigger"):
        validate(candidate)


def test_brain_interpretation_trigger_alone_is_refused() -> None:
    candidate = policy_candidate(
        summary_of(learning_observations(2)),
        triggers=(TriggerSource.BRAIN_INTERPRETATION,),
    )
    with pytest.raises(InsufficientEvidenceError):
        validate(candidate)


def test_outcome_failure_is_not_automatically_a_decision_failure() -> None:
    observations = learning_observations(
        2,
        outcome=OutcomeStatus.FAILED,
        decision=OutcomeStatus.MATCH,
        available_at_decision=True,
    )
    summary = summary_of(observations)
    assert summary.analysis.outcome_failures == 2
    assert summary.analysis.decision_failures == 0
    assert summary.analysis.unattributable_failures == 2
    with pytest.raises(InsufficientEvidenceError, match="판단 실패로 자동 치환"):
        validate(policy_candidate(summary))

    # 같은 관측을 환경 변화 계기로 다시 세우면(판단 실패를 주장하지 않으면) 검증은 진행된다.
    environment_candidate = policy_candidate(summary, triggers=(TriggerSource.ENVIRONMENT_CHANGE,))
    assert validate(environment_candidate).passed is True


def test_candidate_evidence_claim_must_match_episode_aggregation() -> None:
    candidate = policy_candidate(summary_of(learning_observations(2)))
    forged = replace(
        candidate,
        evidence_analysis=replace(candidate.evidence_analysis, decision_failures=99),
    )
    with pytest.raises(EvidenceMismatchError):
        validate(forged)


def test_validation_split_must_be_disjoint_from_learning_tasks() -> None:
    candidate = policy_candidate(summary_of(learning_observations(2)))
    overlapping = replace(
        validation_split(),
        task_ids=tuple(candidate.task_ids),
        split_id=new_split_id(ValidationRole.VALIDATION),
    )
    with pytest.raises(ValidationBypassRefused):
        HeldOutValidator().validate(
            candidate,
            split=overlapping,
            criterion=criterion(),
            observations=validation_observations(True, True),
            generated_at=LATER,
        )


def test_learning_split_cannot_be_used_for_validation() -> None:
    candidate = policy_candidate(summary_of(learning_observations(2)))
    with pytest.raises(ValidationBypassRefused):
        validate(candidate, role=ValidationRole.LEARNING)


def test_unvalidated_promotion_is_refused_and_active_stays_none() -> None:
    candidates = CandidateStore()
    store = PolicyStore()
    candidate = policy_candidate(summary_of(learning_observations(2)))
    candidates.append(candidate)
    failed = validate(candidate, observations=validation_observations(False, False))
    assert failed.passed is False
    assert failed.limitations
    candidates.add_report(failed)
    assert candidates.passed_report(candidate.candidate_id) is None
    with pytest.raises(PromotionRefused):
        store.register(candidate, failed, version="1.0.0", producer=BODY, created_at=NOW)
    assert store.active_version(candidate.candidate_id) is None

    other = policy_candidate(summary_of(learning_observations(2)))
    with pytest.raises(PromotionRefused):
        store.register(other, failed, version="1.0.0", producer=BODY, created_at=NOW)


def test_registration_alone_does_not_change_active_policy() -> None:
    candidates = CandidateStore()
    store = PolicyStore()
    candidate = policy_candidate(summary_of(learning_observations(2)))
    candidates.append(candidate)
    report = validate(candidate)
    candidates.add_report(report)
    store.register(candidate, report, version="1.0.0", producer=BODY, created_at=NOW)
    assert store.active_version(candidate.candidate_id) is None
    assert store.growth_evidence(candidate.candidate_id) is None
    with pytest.raises(PolicyCasConflict):
        store.promote(
            candidate.candidate_id,
            version="1.0.0",
            expected_active_version="9.9.9",
            actor=BODY,
            reason="stale expectation",
            occurred_at=LATER,
        )


def test_human_assisted_candidate_passes_the_same_validation_gate() -> None:
    human_candidate = policy_candidate(summary_of(learning_observations(1)), producer=HUMAN)
    assert human_candidate.human_assisted is True
    with pytest.raises(InsufficientEvidenceError):
        validate(human_candidate)

    verified = policy_candidate(summary_of(learning_observations(2)), producer=HUMAN)
    report = validate(verified)
    assert report.passed is True
    store = PolicyStore()
    store.register(verified, report, version="1.0.0", producer=HUMAN, created_at=NOW)
    assert store.active_version(verified.candidate_id) is None


# ─── T10-B: 해석 주체 ───────────────────────────────────────────────


def test_aggregation_never_calls_the_meaning_interpreter() -> None:
    spy = SpyInterpreter(reading=reading())
    assert isinstance(spy, MeaningInterpreter)
    evaluator = ExperienceEvaluator(interpreter=spy)

    summary = evaluator.aggregate(learning_observations(2))
    assert spy.calls == []
    assert evaluator.interpret_calls == 0
    assert summary.analysis.observation_count == 2

    result = evaluator.interpret(summary, question="재시도 원인은 무엇인가")
    assert len(spy.calls) == 1
    assert spy.calls[0].summary_digest == summary.digest()
    assert result.author.kind is ProducerKind.BRAIN
    assert result.evidence_kind is EvidenceKind.INFERENCE
    assert evaluator.readings == (result,)


def test_body_cannot_author_semantic_reading() -> None:
    spy = SpyInterpreter(reading=reading(author=BODY))
    with pytest.raises(SemanticAuthorityError):
        ExperienceEvaluator(interpreter=spy).interpret(summary_of(learning_observations(2)), question="원인은 무엇인가")
    with pytest.raises(SemanticAuthorityError):
        policy_candidate(summary_of(learning_observations(2)), reading=reading(author=BODY))
    with pytest.raises(SemanticAuthorityError):
        ExperienceEvaluator().interpret(summary_of(learning_observations(2)), question="원인은 무엇인가")


def test_meaning_without_evidence_never_becomes_principle() -> None:
    assert not hasattr(EntityType, "FACT")
    ledger = KnowledgeLedger()
    candidate = pattern_candidate(
        summary_of(learning_observations(2, evidence=())),
        reading=reading(causal="config evidence 누락 → read tool 재시도"),
    )
    assert candidate.evidence_ids == ()
    broader = validate(candidate, role=ValidationRole.BROADER)
    assert broader.broader_validated is True
    with pytest.raises(NotPromotableError):
        ledger.add(
            candidate,
            target=KnowledgeTarget.PRINCIPLE,
            scope="fixture",
            report=broader,
            created_at=LATER,
            confidence_profile=confidence(),
        )


def test_causal_claim_stays_a_hypothesis_until_validated() -> None:
    ledger = KnowledgeLedger()
    candidate = pattern_candidate(
        summary_of(learning_observations(2)),
        reading=reading(causal="config evidence 누락 → read tool 재시도"),
    )
    item = ledger.add(
        candidate,
        target=KnowledgeTarget.HYPOTHESIS,
        scope="fixture",
        created_at=LATER,
        semantic_reading=reading(),
    )
    assert item.lifecycle is KnowledgeLifecycle.CANDIDATE
    assert ledger.records[-1].entity_type is EntityType.HYPOTHESIS

    with pytest.raises(NotPromotableError):
        ledger.add(candidate, target=KnowledgeTarget.STRATEGY, scope="fixture", created_at=LATER)

    validated = ledger.add(
        candidate,
        target=KnowledgeTarget.STRATEGY,
        scope="fixture",
        report=validate(candidate),
        created_at=LATEST,
    )
    assert validated.lifecycle is KnowledgeLifecycle.SUPPORTED
    assert ledger.records[-1].entity_type is EntityType.STRATEGY


def test_principle_requires_broader_validation() -> None:
    ledger = KnowledgeLedger()
    candidate = pattern_candidate(summary_of(learning_observations(2)))
    with pytest.raises(ValidationBypassRefused):
        ledger.add(
            candidate,
            target=KnowledgeTarget.PRINCIPLE,
            scope="fixture",
            report=validate(candidate),
            created_at=LATER,
            confidence_profile=confidence(),
        )

    item = ledger.add(
        candidate,
        target=KnowledgeTarget.PRINCIPLE,
        scope="fixture",
        report=validate(candidate, role=ValidationRole.BROADER),
        created_at=LATER,
        confidence_profile=confidence(),
    )
    assert item.target is KnowledgeTarget.PRINCIPLE
    assert item.report_id is not None
    assert ledger.records[-1].entity_type is EntityType.PRINCIPLE


def test_policy_candidate_cannot_become_knowledge_support() -> None:
    ledger = KnowledgeLedger()
    candidate = policy_candidate(summary_of(learning_observations(2)))
    with pytest.raises(NotPromotableError):
        ledger.add(candidate, target=KnowledgeTarget.HYPOTHESIS, scope="fixture", created_at=LATER)
    with pytest.raises(LearningContractError):
        CandidateProposer().propose(
            summary_of(learning_observations(2)),
            CandidateRequest(kind=CandidateKind.POLICY, rule="context_depth=2", scope="fixture"),
            project_id=PROJECT,
            producer=BODY,
            created_at=NOW,
        )


# ─── T10-C: 적용과 수정 ─────────────────────────────────────────────


def _applicability(
    *, environment: ApplicabilityLevel = ApplicabilityLevel.MATCH, **overrides: object
) -> ApplicabilityProfile:
    values: dict[str, object] = {
        "goal_match": ApplicabilityLevel.MATCH,
        "context_match": ApplicabilityLevel.MATCH,
        "constraint_match": ApplicabilityLevel.MATCH,
        "environment_match": environment,
        "action_match": ApplicabilityLevel.MATCH,
        "known_exception": ApplicabilityLevel.MATCH,
        "context_drift": ApplicabilityLevel.MATCH,
    }
    values.update(overrides)
    return ApplicabilityProfile(**values)  # type: ignore[arg-type]


def test_high_confidence_with_mismatch_is_withheld() -> None:
    ledger = KnowledgeLedger()
    review = ledger.reassess_applicability(
        _applicability(environment=ApplicabilityLevel.MISMATCH),
        knowledge_confidence=confidence(0.99),
    )
    assert review.disposition is ApplicabilityDisposition.WITHHOLD
    assert review.mismatched_fields == ("environment_match",)
    assert "confidence" in review.reason

    assert (
        ledger.reassess_applicability(_applicability(), knowledge_confidence=confidence(0.2)).disposition
        is ApplicabilityDisposition.APPLY
    )
    unknown = ledger.reassess_applicability(
        _applicability(context_drift=ApplicabilityLevel.UNKNOWN),
        knowledge_confidence=confidence(0.9),
    )
    assert unknown.disposition is ApplicabilityDisposition.APPLY_WITH_SCOPE
    assert unknown.unknown_fields == ("context_drift",)
    partial = ledger.reassess_applicability(
        _applicability(action_match=ApplicabilityLevel.PARTIAL),
        knowledge_confidence=confidence(0.9),
    )
    assert partial.disposition is ApplicabilityDisposition.APPLY_WITH_SCOPE


def test_knowledge_revision_is_append_only() -> None:
    ledger = KnowledgeLedger()
    candidate = pattern_candidate(summary_of(learning_observations(2)))
    item = ledger.add(candidate, target=KnowledgeTarget.HYPOTHESIS, scope="fixture", created_at=LATER)
    original = item.record_digest

    first = ledger.revise(
        item.item_id,
        lifecycle=KnowledgeLifecycle.CHALLENGED,
        reason="환경 변화로 반증 관측이 생겼다",
        evidence_ids=(new_id(EntityType.EVIDENCE),),
        recorded_at=LATER,
    )
    second = ledger.revise(
        item.item_id,
        lifecycle=KnowledgeLifecycle.RETIRED,
        reason="대체 strategy가 별도 검증을 통과했다",
        recorded_at=LATEST,
    )
    assert second.supersedes_revision == first.revision_id
    assert [revision.lifecycle for revision in ledger.revisions(item.item_id)] == [
        KnowledgeLifecycle.CHALLENGED,
        KnowledgeLifecycle.RETIRED,
    ]
    assert ledger.item(item.item_id).lifecycle is KnowledgeLifecycle.CANDIDATE
    assert ledger.item(item.item_id).record_digest == original
    assert second.original_record_digest == original
    with pytest.raises(NotPromotableError):
        ledger.revise(
            item.item_id,
            lifecycle=KnowledgeLifecycle.SUPPORTED,
            reason="기준을 완화한다",
            recorded_at=LATEST,
        )
    with pytest.raises(LearningContractError):
        ledger.revise(item.item_id, lifecycle=KnowledgeLifecycle.SCOPED, reason="", recorded_at=LATEST)


# ─── T10-D: 실제 변화·복구 ─────────────────────────────────────────


def evidence_record(evidence_id: str) -> Record:
    """candidate가 참조하는 Evidence를 canonical store에 실제로 존재시키기 위한 fixture."""

    return Record.create(
        entity_type=EntityType.EVIDENCE,
        project_id=PROJECT,
        producer=BODY,
        payload=EvidencePayload(
            kind="OBSERVATION",
            claim="fixture observation for T10",
            provenance=Provenance(
                source_uri="tests/cognitive/test_learning.py",
                content_digest="sha256:" + "0" * 64,
                observed_at=NOW,
                ingested_at=NOW,
            ),
            time=NOW,
            digest="sha256:" + "1" * 64,
            independence_group="fixture",
        ),
        record_id=evidence_id,
        created_at=NOW,
    )


def two_version_policy() -> tuple[PolicyStore, LearningCandidate, str, str]:
    """v1.0.0/v2.0.0이 등록된 store. 활성화와 CAS는 시험이 직접 한다."""

    candidates = CandidateStore()
    store = PolicyStore()
    candidate = policy_candidate(summary_of(learning_observations(2)))
    candidates.append(candidate)
    report = validate(candidate)
    candidates.add_report(report)
    store.register(candidate, report, version="1.0.0", producer=BODY, created_at=NOW)
    store.register(
        candidate,
        report,
        version="2.0.0",
        producer=BODY,
        created_at=NOW,
        policy_id=candidate.candidate_id,
    )
    return store, candidate, "1.0.0", "2.0.0"


def test_growth_chain_links_candidate_validation_activation_and_behavior(tmp_path: Path) -> None:
    candidates = CandidateStore()
    store = PolicyStore()
    candidate = policy_candidate(summary_of(learning_observations(2)))
    candidates.append(candidate)
    report = validate(candidate)
    candidates.add_report(report)
    version = store.register(candidate, report, version="1.0.0", producer=BODY, created_at=NOW)
    activation = store.promote(
        candidate.candidate_id,
        version="1.0.0",
        expected_active_version=None,
        actor=BODY,
        reason="T10-D fixture activation",
        occurred_at=LATER,
    )
    assert activation.kind is ActivationKind.PROMOTION
    assert activation.validation_report_id == report.report_id
    assert version.lifecycle is KnowledgeLifecycle.CANDIDATE
    assert store.active_version(candidate.candidate_id) == "1.0.0"
    # activation 기록만으로는 성장이 아니다.
    assert store.growth_evidence(candidate.candidate_id) is None

    outcome_ref = new_id(EntityType.OUTCOME)
    trace = store.record_behavior_change(
        policy_id=candidate.candidate_id,
        version="1.0.0",
        task_id="task:next-1",
        shadow_selection=("context:l1#a",),
        actual_selection=("context:l1#a", "context:l2#b"),
        producer=BODY,
        recorded_at=LATEST,
        outcome_ref=outcome_ref,
    )
    assert trace.changed is True
    assert "context:l2#b" in trace.difference
    growth = store.growth_evidence(candidate.candidate_id)
    assert growth is not None
    assert growth.changed_tasks == ("task:next-1",)
    assert growth.outcome_refs == (outcome_ref,)

    # outcome 연결이 없는 기록은 성장 근거로 세지 않는다.
    store.record_behavior_change(
        policy_id=candidate.candidate_id,
        version="1.0.0",
        task_id="task:next-2",
        shadow_selection=(),
        actual_selection=("only:with-policy",),
        producer=BODY,
        recorded_at=LATEST,
    )
    assert store.growth_evidence(candidate.candidate_id, minimum_changed_tasks=2) is None

    canonical = CanonicalStore(tmp_path / "store", git_enabled=False)
    evidence_records = [evidence_record(evidence_id) for evidence_id in candidate.evidence_ids]
    records = [*evidence_records, *candidates.records, *store.records]
    canonical.commit_records(records, message="T10 fixture record set")
    assert canonical.verify_digests() == len(records)
    stored_activation = canonical.read(activation.activation_id)
    assert stored_activation is not None
    assert stored_activation.entity_type is EntityType.POLICY_ACTIVATION
    assert getattr(stored_activation.payload, "version", None) == "1.0.0"
    stored_trace = canonical.read(trace.trace_id)
    assert stored_trace is not None
    assert stored_trace.entity_type is EntityType.BEHAVIOR_CHANGE_TRACE
    assert getattr(stored_trace.payload, "actual_selection", None) == ("context:l1#a", "context:l2#b")


def test_cas_conflict_serializes_concurrent_promotion() -> None:
    store, candidate, v1, v2 = two_version_policy()
    policy_id = candidate.candidate_id
    store.promote(policy_id, version=v1, expected_active_version=None, actor=BODY, reason="winner", occurred_at=LATER)
    with pytest.raises(PolicyCasConflict):
        store.promote(
            policy_id, version=v2, expected_active_version=None, actor=BODY, reason="loser", occurred_at=LATER
        )
    assert store.active_version(policy_id) == v1
    store.promote(
        policy_id, version=v2, expected_active_version=v1, actor=BODY, reason="after conflict", occurred_at=LATEST
    )
    assert [event.kind for event in store.activations(policy_id)] == [
        ActivationKind.PROMOTION,
        ActivationKind.PROMOTION,
    ]
    assert store.active_version(policy_id) == v2


def test_rollback_restores_previous_selection() -> None:
    store, candidate, v1, v2 = two_version_policy()
    policy_id = candidate.candidate_id
    first = store.promote(
        policy_id, version=v1, expected_active_version=None, actor=BODY, reason="initial", occurred_at=LATER
    )
    store.promote(
        policy_id, version=v2, expected_active_version=v1, actor=BODY, reason="new evidence", occurred_at=LATER
    )
    rollback = store.rollback(
        policy_id,
        to_version=v1,
        reason="negative transfer 관측",
        expected_active_version=v2,
        actor=BODY,
        occurred_at=LATEST,
    )
    assert rollback.kind is ActivationKind.ROLLBACK
    assert store.active_version(policy_id) == v1
    history = store.activations(policy_id)
    assert len(history) == 3
    assert history[0].digest() == first.digest()
    pinned = store.pin("episode:after-rollback", policy_id, pinned_at=LATEST)
    assert store.resolve(pinned).version == v1


def test_inflight_episode_keeps_pinned_version_and_revocation_is_immediate() -> None:
    store, candidate, v1, v2 = two_version_policy()
    policy_id = candidate.candidate_id
    store.promote(policy_id, version=v1, expected_active_version=None, actor=BODY, reason="initial", occurred_at=LATER)
    pinned = store.pin("episode:1", policy_id, pinned_at=LATER, authority_revision=1)
    assert pinned.policy_version == v1
    store.promote(
        policy_id, version=v2, expected_active_version=v1, actor=BODY, reason="new evidence", occurred_at=LATEST
    )
    assert store.active_version(policy_id) == v2
    assert store.resolve(pinned).version == v1

    revoked = store.revoke_authority(reason="human revoked TOOL_WRITE", revoked_at=LATEST)
    assert [item.episode_id for item in revoked] == ["episode:1"]
    current = store.pin_of("episode:1")
    assert current is not None
    with pytest.raises(AuthorityRevokedError):
        store.resolve(current)
    assert store.revoke_authority(reason="again", revoked_at=LATEST) == ()


def test_retirement_keeps_history_and_blocks_reactivation() -> None:
    store, candidate, v1, v2 = two_version_policy()
    policy_id = candidate.candidate_id
    store.promote(policy_id, version=v1, expected_active_version=None, actor=BODY, reason="initial", occurred_at=LATER)
    store.promote(
        policy_id, version=v2, expected_active_version=v1, actor=BODY, reason="new evidence", occurred_at=LATER
    )
    retired = store.retire(policy_id, version=v2, reason="negative transfer", actor=BODY, occurred_at=LATEST)
    assert retired.version == v2
    assert store.active_version(policy_id) == v1
    assert store.version(policy_id, v2).lifecycle is KnowledgeLifecycle.RETIRED
    assert store.retirements(policy_id) == (retired,)
    assert store.activations(policy_id)[-1].kind is ActivationKind.ROLLBACK
    with pytest.raises(RetiredVersionRefused):
        store.promote(
            policy_id, version=v2, expected_active_version=v1, actor=BODY, reason="되돌리기", occurred_at=LATEST
        )


# ─── T10-E: 성장 범위·권한 ─────────────────────────────────────────


def test_multiple_operational_targets_activate_independently() -> None:
    candidates = CandidateStore()
    store = PolicyStore()
    targets = (
        (PolicyTarget.CONTEXT_SELECTION, "select required config evidence first", {"priority": 1}),
        (PolicyTarget.TOOL_SELECTION, "prefer read tool for config evidence", {"priority": 2}),
    )
    for target, rule, parameters in targets:
        candidate = policy_candidate(
            summary_of(learning_observations(2)), target=target, rule=rule, parameters=parameters
        )
        candidates.append(candidate)
        report = validate(candidate)
        candidates.add_report(report)
        store.register(candidate, report, version="1.0.0", producer=BODY, created_at=NOW)
        store.promote(
            candidate.candidate_id,
            version="1.0.0",
            expected_active_version=None,
            actor=BODY,
            reason="운영 target 확장 계약 확인",
            occurred_at=LATER,
        )
    selection = store.active_policy(PolicyTarget.CONTEXT_SELECTION)
    tooling = store.active_policy(PolicyTarget.TOOL_SELECTION)
    assert selection is not None and tooling is not None
    assert selection.target is PolicyTarget.CONTEXT_SELECTION
    assert tooling.target is PolicyTarget.TOOL_SELECTION
    assert selection.policy_id != tooling.policy_id
    assert {target.value for target in PolicyTarget} >= {"CONTEXT_SELECTION", "TOOL_SELECTION", "AUTHORITY_DELEGATION"}


def test_policy_cannot_widen_authority(project_root: Path) -> None:
    guard = ProtectedWriteGuard(project_root)
    summary = summary_of(learning_observations(2))

    widening = policy_candidate(
        summary,
        target=PolicyTarget.AUTHORITY_DELEGATION,
        rule="prefer existing grant holder",
        parameters={"new_grant": "TOOL_WRITE"},
        guard=guard,
    )
    with pytest.raises(AuthorityWideningRefused):
        PolicyStore(guard=guard).register(widening, validate(widening), version="1.0.0", producer=BODY, created_at=NOW)

    ceiling = policy_candidate(
        summary,
        target=PolicyTarget.AUTHORITY_DELEGATION,
        rule="raise autonomy",
        parameters={"max_autonomy": 0.9},
        guard=guard,
    )
    with pytest.raises(AuthorityWideningRefused):
        PolicyStore(guard=guard).register(ceiling, validate(ceiling), version="1.0.0", producer=BODY, created_at=NOW)

    outside = policy_candidate(
        summary,
        target=PolicyTarget.AUTHORITY_DELEGATION,
        rule="adjust delegation selection",
        parameters={"subject_override": "agent:child"},
        guard=guard,
    )
    with pytest.raises(AuthorityWideningRefused):
        PolicyStore(guard=guard).register(outside, validate(outside), version="1.0.0", producer=BODY, created_at=NOW)

    # 기존 grant 안의 선택·위임 조정은 등록된다.
    allowed = policy_candidate(
        summary,
        target=PolicyTarget.AUTHORITY_DELEGATION,
        rule="prefer existing grant holder",
        parameters={"selection_order": "preferred_first"},
        guard=guard,
    )
    version = PolicyStore(guard=guard).register(
        allowed, validate(allowed), version="1.0.0", producer=BODY, created_at=NOW
    )
    assert version.target is PolicyTarget.AUTHORITY_DELEGATION
    assert version.parameters == {"selection_order": "preferred_first"}


def test_policy_text_referencing_protected_target_is_refused(project_root: Path) -> None:
    guard = ProtectedWriteGuard(project_root)
    protected_rule = "raise context depth while writing docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md"
    with pytest.raises(PolicyTargetRefused):
        policy_candidate(summary_of(learning_observations(2)), rule=protected_rule, guard=guard)

    # guard 없이 만든 candidate도 등록 단계에서 거부된다.
    bypass = policy_candidate(summary_of(learning_observations(2)), rule=protected_rule)
    with pytest.raises(AuthorityWideningRefused):
        PolicyStore(guard=guard).register(bypass, validate(bypass), version="1.0.0", producer=BODY, created_at=NOW)


def test_policy_activation_does_not_change_authority_dimension_view() -> None:
    grant = AuthorityGrant(
        subject="body:test",
        dimension=AuthorityDimension.TOOL_READ,
        resource_scope="*",
        allowed_operations=("read_file",),
        granted_by="human:operator",
        issued_at=NOW,
        revision=1,
    )
    profile = AuthorityProfile.from_grants(
        (grant,),
        revision=3,
        human_ceiling={AuthorityDimension.TOOL_WRITE: "human:operator"},
    )
    before = {
        dimension: verdict.value
        for dimension, verdict in profile.dimension_view("body:test", resource_scope="*", operation="read_file").items()
    }

    _, store, candidate, _ = activated_policy()
    assert store.active_version(candidate.candidate_id) == "1.0.0"

    after = {
        dimension: verdict.value
        for dimension, verdict in profile.dimension_view("body:test", resource_scope="*", operation="read_file").items()
    }
    assert before == after
    assert profile.revision == 3

    with pytest.raises(AuthorityViolation):
        profile.issue_grant(grant, actor_kind=ProducerKind.BRAIN)
    ceiling_proposal = profile.propose_ceiling_change(
        subject="body:test",
        dimension=AuthorityDimension.TOOL_WRITE,
        requested_scope="*",
        reason="편의를 위해 확대한다",
    )
    assert ceiling_proposal.allowed is False
    assert ceiling_proposal.human_decision_required is True
    assert not hasattr(store, "issue_grant")
    assert not hasattr(store, "propose_ceiling_change")


def test_pattern_candidate_cannot_become_a_policy_version() -> None:
    pattern = pattern_candidate(summary_of(learning_observations(2)))
    with pytest.raises(PolicyContractError):
        PolicyStore().register(pattern, validate(pattern), version="1.0.0", producer=BODY, created_at=NOW)
