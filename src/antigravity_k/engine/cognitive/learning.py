"""Experience → Knowledge/Policy 후보 lifecycle (P09).

계약(EXPERIENCE_AND_LEARNING.md §26/§27/§35/§36, ACCEPTANCE_CHECKLIST T10):

- **A 승격 경계:** 한 실패·한 Brain 해석·grade/cooldown trigger만으로는 어떤 후보도 검증·승격되지 않는다.
  후보는 독립 episode 수(raw material 중복을 독립 replication으로 세지 않는다)와 별도 validation report를
  갖춘다. human-assisted 후보도 같은 검증을 지난다.
- **B 해석 주체:** 기계 집계(``summarize``/``aggregate``)와 의미 해석(``MeaningInterpreter``)을 분리한다.
  의미 해석의 author는 Primary Brain 또는 human-assisted 경로뿐이며, 의미 해석은 FACT나 검증된 Principle이
  되지 않는다.
- **C 적용과 수정:** knowledge confidence가 높아도 현재 applicability가 MISMATCH면 자동 적용하지 않는다.
  challenged/scoped/revised/retired는 append 사건이고 원본 record digest는 그대로 남는다.
- **E 성장 범위:** 운영 target은 ``PolicyTarget`` allowlist 전체로 확장 가능하고, 기존 grant 안의 위임·선택
  조정과 신규 grant/ceiling 발급은 서로 다른 경로다. learned policy는 protected authority를 바꾸지 못한다.

이 모듈은 provider/UI를 import하지 않는다. policy version·activation의 소유는 ``policy_store``가 맡는다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.experience import EpisodeEvaluations
from antigravity_k.engine.cognitive.models import (
    ApplicabilityLevel,
    ApplicabilityProfile,
    ConfidenceProfile,
    EvidenceKind,
    HypothesisPayload,
    KnowledgeLifecycle,
    MetricResult,
    OutcomeStatus,
    PolicyPayload,
    PolicyTarget,
    PrinciplePayload,
    Producer,
    ProducerKind,
    Record,
    ScalarParameter,
    StrategyPayload,
    ValidationReportPayload,
    same_enum,
)
from antigravity_k.engine.cognitive.protected_targets import ActorKind, ProtectedWriteGuard
from antigravity_k.engine.cognitive.references import REL_EVIDENCE, EntityType, Reference, new_id


class TriggerSource(StrEnum):
    """후보가 생긴 계기. 계기와 승격 근거는 다르다."""

    FAILURE = "FAILURE"
    GRADE = "GRADE"
    COOLDOWN = "COOLDOWN"
    BRAIN_INTERPRETATION = "BRAIN_INTERPRETATION"
    ENVIRONMENT_CHANGE = "ENVIRONMENT_CHANGE"
    HUMAN_REQUEST = "HUMAN_REQUEST"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"


class CandidateKind(StrEnum):
    PATTERN = "PATTERN"
    POLICY = "POLICY"


class KnowledgeTarget(StrEnum):
    HYPOTHESIS = "HYPOTHESIS"
    STRATEGY = "STRATEGY"
    PRINCIPLE = "PRINCIPLE"


class ValidationRole(StrEnum):
    LEARNING = "LEARNING"
    VALIDATION = "VALIDATION"
    BROADER = "BROADER"


class ApplicabilityDisposition(StrEnum):
    APPLY = "APPLY"
    APPLY_WITH_SCOPE = "APPLY_WITH_SCOPE"
    WITHHOLD = "WITHHOLD"


#: 중복 원자료에서 파생된 episode를 독립 replication으로 세지 않는다.
MIN_INDEPENDENT_EPISODES: Final[int] = 2

#: 의미 해석을 할 수 있는 주체. Body·도구는 의미를 확정하지 않는다.
MEANING_AUTHORS: Final[frozenset[ProducerKind]] = frozenset({ProducerKind.BRAIN, ProducerKind.HUMAN})

#: 후보 발생 계기일 뿐 승격 근거가 될 수 없는 trigger. 여기만 있으면 후보는 검증되지 않는다.
EVIDENCE_FREE_TRIGGERS: Final[frozenset[TriggerSource]] = frozenset(
    {TriggerSource.GRADE, TriggerSource.COOLDOWN, TriggerSource.BRAIN_INTERPRETATION}
)

KNOWLEDGE_ENTITY: Final[Mapping[KnowledgeTarget, EntityType]] = {
    KnowledgeTarget.HYPOTHESIS: EntityType.HYPOTHESIS,
    KnowledgeTarget.STRATEGY: EntityType.STRATEGY,
    KnowledgeTarget.PRINCIPLE: EntityType.PRINCIPLE,
}

#: 관리(하향·범위 조정) 전이만 revise로 표현한다. 지원 수준 상향은 validation report가 필요하다.
MANAGEMENT_LIFECYCLES: Final[frozenset[KnowledgeLifecycle]] = frozenset(
    {
        KnowledgeLifecycle.CHALLENGED,
        KnowledgeLifecycle.SCOPED,
        KnowledgeLifecycle.REVISED,
        KnowledgeLifecycle.RETIRED,
    }
)

FAILURE_OUTCOMES: Final[frozenset[OutcomeStatus]] = frozenset(
    {OutcomeStatus.FAILED, OutcomeStatus.DEVIATION, OutcomeStatus.PARTIAL}
)

_APPLICABILITY_FIELDS: Final[tuple[str, ...]] = (
    "goal_match",
    "context_match",
    "constraint_match",
    "environment_match",
    "action_match",
    "known_exception",
    "context_drift",
)


class LearningContractError(ValueError):
    """학습 계약 위반의 공통 상위 타입."""


class InsufficientEvidenceError(LearningContractError):
    """독립 근거·관측이 부족하다. trigger만으로는 후보가 승격되지 않는다."""


class ValidationBypassRefused(LearningContractError):
    """검증 분리(split/freeze)를 우회하려는 시도."""


class SemanticAuthorityError(LearningContractError):
    """의미 해석 주체가 Primary/human-assisted 경로가 아니다."""


class EvidenceMismatchError(LearningContractError):
    """후보가 주장한 근거 집계가 실제 episode 집계와 다르다."""


class NotPromotableError(LearningContractError):
    """승격 조건(검증·broader validation·근거 종류)을 만족하지 않는다."""


class PolicyTargetRefused(LearningContractError):
    """allowlist 밖 target이거나 protected authority를 건드리려는 policy다."""


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


# ─── 의미 해석 경계 ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MeaningRequest:
    """의미 해석 요청. 기계 집계 결과와 그 근거만 넘긴다."""

    question: str
    summary_digest: str
    evidence_ids: tuple[str, ...] = ()
    target_scope: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "question": self.question,
            "summary_digest": self.summary_digest,
            "evidence_ids": list(self.evidence_ids),
            "target_scope": self.target_scope,
        }


@dataclass(frozen=True, slots=True)
class SemanticReading:
    """의미 해석 결과. producer/provenance를 남기며 FACT가 아니다."""

    meaning: str
    author: Producer
    confidence_profile: ConfidenceProfile
    applicability: ApplicabilityProfile = field(default_factory=ApplicabilityProfile)
    evidence_ids: tuple[str, ...] = ()
    causal_claim: str = ""
    interpreter_version: str = ""
    recorded_at: datetime | None = None

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "meaning": self.meaning,
            "author": {"kind": self.author.kind.value, "actor_id": self.author.actor_id},
            "causal_claim": self.causal_claim,
            "interpreter_version": self.interpreter_version,
            "evidence_ids": list(self.evidence_ids),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    @property
    def evidence_kind(self) -> EvidenceKind:
        """의미 해석은 추론이다. FACT로 승격되지 않는다."""

        return EvidenceKind.INFERENCE


@runtime_checkable
class MeaningInterpreter(Protocol):
    """의미 해석 hook. Primary Brain 또는 human-assisted 구현이 담당한다.

    기계 집계 경로(``ExperienceEvaluator.aggregate``)는 이 hook을 호출하지 않는다. 시험은 호출 0을 고정한다.
    """

    def read(self, request: MeaningRequest) -> SemanticReading: ...


# ─── 기계 집계 ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EpisodeObservation:
    """학습 근거로 쓰는 episode 한 건. 기계 비교 결과만 담는다."""

    episode_id: str
    task_id: str
    raw_material_digest: str
    evaluations: EpisodeEvaluations
    experience_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    applicability: ApplicabilityProfile = field(default_factory=ApplicabilityProfile)
    producer: Producer | None = None

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "episode_id": self.episode_id,
            "task_id": self.task_id,
            "raw_material_digest": self.raw_material_digest,
            "experience_id": self.experience_id,
            "outcome": self.evaluations.outcome.status.value,
            "decision": self.evaluations.decision.status.value,
            "execution": self.evaluations.execution.status.value,
            "available_at_decision": self.evaluations.decision.available_at_decision,
            "evidence_ids": list(self.evidence_ids),
        }

    @property
    def outcome_failed(self) -> bool:
        return self.evaluations.outcome.status in FAILURE_OUTCOMES

    @property
    def decision_failed(self) -> bool:
        """당시 정보로 판단이 잘못됐을 때만 참이다. 결과 실패와 자동 치환하지 않는다."""

        evaluation = self.evaluations.decision
        if evaluation.status in FAILURE_OUTCOMES:
            return not evaluation.available_at_decision
        return False

    @property
    def unattributable_failure(self) -> bool:
        """결과는 실패했지만 당시 판단은 합리적이었다(환경·예상 불가 요인)."""

        evaluation = self.evaluations.decision
        return (
            self.outcome_failed
            and evaluation.available_at_decision
            and same_enum(evaluation.status, OutcomeStatus.MATCH)
        )


@dataclass(frozen=True, slots=True)
class EvidenceAnalysis:
    """candidate 근거를 기계적으로 센 결과. 결과 실패와 판단 실패를 합치지 않는다."""

    observation_count: int
    independent_episode_count: int
    outcome_failures: int
    decision_failures: int
    execution_failures: int
    unattributable_failures: int
    unknown_outcomes: int

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "observation_count": self.observation_count,
            "independent_episode_count": self.independent_episode_count,
            "outcome_failures": self.outcome_failures,
            "decision_failures": self.decision_failures,
            "execution_failures": self.execution_failures,
            "unattributable_failures": self.unattributable_failures,
            "unknown_outcomes": self.unknown_outcomes,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


def summarize(observations: Sequence[EpisodeObservation]) -> EvidenceAnalysis:
    """기계 집계. 의미 해석·causal 추론을 하지 않는다."""

    raw_materials: list[str] = []
    outcome_failures = 0
    decision_failures = 0
    execution_failures = 0
    unattributable = 0
    unknown = 0
    for observation in observations:
        if observation.raw_material_digest not in raw_materials:
            raw_materials.append(observation.raw_material_digest)
        if observation.outcome_failed:
            outcome_failures += 1
        if observation.decision_failed:
            decision_failures += 1
        if observation.evaluations.execution.status in FAILURE_OUTCOMES:
            execution_failures += 1
        if observation.unattributable_failure:
            unattributable += 1
        if observation.evaluations.outcome.status in {OutcomeStatus.UNKNOWN, OutcomeStatus.PENDING}:
            unknown += 1
    return EvidenceAnalysis(
        observation_count=len(observations),
        independent_episode_count=len(raw_materials),
        outcome_failures=outcome_failures,
        decision_failures=decision_failures,
        execution_failures=execution_failures,
        unattributable_failures=unattributable,
        unknown_outcomes=unknown,
    )


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    """Evaluator/PatternBuilder 사이의 계약. 기계 집계 결과만 담는다."""

    observations: tuple[EpisodeObservation, ...]
    analysis: EvidenceAnalysis

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "observations": [observation.as_mapping() for observation in self.observations],
            "analysis": self.analysis.as_mapping(),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    @property
    def independent_episode_count(self) -> int:
        return self.analysis.independent_episode_count

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref for observation in self.observations for ref in observation.evidence_ids))

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(observation.task_id for observation in self.observations))


class ExperienceEvaluator:
    """Evaluator 기본 구현. 기계 집계와 의미 해석 호출 경로를 분리한다."""

    def __init__(self, *, interpreter: MeaningInterpreter | None = None) -> None:
        self._interpreter = interpreter
        self._interpret_calls = 0
        self._readings: list[SemanticReading] = []

    @property
    def interpret_calls(self) -> int:
        return self._interpret_calls

    @property
    def readings(self) -> tuple[SemanticReading, ...]:
        return tuple(self._readings)

    def aggregate(self, observations: Sequence[EpisodeObservation]) -> EvaluationSummary:
        """세 평가를 기계적으로 집계한다. 모델·검색·의미 해석 호출이 없다."""

        return EvaluationSummary(observations=tuple(observations), analysis=summarize(observations))

    def interpret(
        self,
        summary: EvaluationSummary,
        *,
        question: str,
        target_scope: str = "",
        evidence_ids: Sequence[str] = (),
    ) -> SemanticReading:
        """명시적 의미 해석 경로. Primary Brain 또는 human-assisted 구현만 허용한다."""

        if self._interpreter is None:
            raise SemanticAuthorityError("의미 해석 구현이 연결되지 않았다 — Body가 대신 해석하지 않는다")
        self._interpret_calls += 1
        request = MeaningRequest(
            question=question,
            summary_digest=summary.digest(),
            evidence_ids=tuple(dict.fromkeys((*evidence_ids, *summary.evidence_ids))),
            target_scope=target_scope,
        )
        reading = self._interpreter.read(request)
        if reading.author.kind not in MEANING_AUTHORS:
            raise SemanticAuthorityError(
                f"{reading.author.kind}는 의미 해석 주체가 아니다 — Primary Brain 또는 human-assisted 경로만 가능하다"
            )
        self._readings.append(reading)
        return reading


# ─── typed candidate ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CandidateRequest:
    """candidate 작성 요청. rule/scope는 기계 규칙이며 자유 서술이 아니다."""

    kind: CandidateKind
    rule: str
    scope: str
    target: PolicyTarget | None = None
    version: str = "0.1.0"
    parameters: Mapping[str, ScalarParameter] = field(default_factory=dict)
    applicability: ApplicabilityProfile = field(default_factory=ApplicabilityProfile)
    semantic_reading: SemanticReading | None = None
    trigger_sources: tuple[TriggerSource, ...] = ()
    falsification_criteria: tuple[str, ...] = ()
    evaluation_plan: str = ""
    counterexamples: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    """typed candidate. 제안과 active 적용은 분리되며 여기에는 active 변경 경로가 없다."""

    candidate_id: str
    kind: CandidateKind
    project_id: str
    proposed_by: Producer
    trigger_sources: tuple[TriggerSource, ...]
    rule: str
    scope: str
    summary: EvaluationSummary
    evidence_analysis: EvidenceAnalysis
    applicability: ApplicabilityProfile
    created_at: datetime
    target: PolicyTarget | None = None
    version: str = "0.1.0"
    parameters: Mapping[str, ScalarParameter] = field(default_factory=dict)
    semantic_reading: SemanticReading | None = None
    falsification_criteria: tuple[str, ...] = ()
    evaluation_plan: str = ""
    counterexamples: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def independent_episode_count(self) -> int:
        return self.evidence_analysis.independent_episode_count

    @property
    def human_assisted(self) -> bool:
        return same_enum(self.proposed_by.kind, ProducerKind.HUMAN)

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return self.summary.evidence_ids

    @property
    def task_ids(self) -> tuple[str, ...]:
        return self.summary.task_ids

    @property
    def policy_target_value(self) -> str:
        return self.target.value if self.target is not None else ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "target": self.policy_target_value,
            "rule": self.rule,
            "scope": self.scope,
            "version": self.version,
            "trigger_sources": [trigger.value for trigger in self.trigger_sources],
            "evidence_analysis": self.evidence_analysis.as_mapping(),
            "semantic_reading": self.semantic_reading.digest() if self.semantic_reading else None,
            "human_assisted": self.human_assisted,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    def to_record(self) -> Record:
        """candidate를 canonical record로 남긴다. Policy 후보는 lifecycle=CANDIDATE다."""

        references = tuple(
            Reference(relation=REL_EVIDENCE, target_id=evidence_id, expected_type=EntityType.EVIDENCE)
            for evidence_id in self.evidence_ids
        )
        if same_enum(self.kind, CandidateKind.POLICY):
            if self.target is None:
                raise LearningContractError("POLICY 후보에는 target이 필요하다")
            return Record.create(
                entity_type=EntityType.POLICY,
                project_id=self.project_id,
                producer=self.proposed_by,
                payload=PolicyPayload(
                    target=self.target,
                    rule=self.rule,
                    parameters=dict(self.parameters),
                    version=self.version,
                    lifecycle=KnowledgeLifecycle.CANDIDATE,
                    compatibility=self.scope,
                ),
                references=references,
                record_id=self.candidate_id,
                created_at=self.created_at,
            )
        return Record.create(
            entity_type=EntityType.HYPOTHESIS,
            project_id=self.project_id,
            producer=self.proposed_by,
            payload=HypothesisPayload(
                claim=self.rule,
                falsification_criteria=self.falsification_criteria or ("반증 조건이 아직 정의되지 않았다",),
                evaluation_plan=self.evaluation_plan or self.scope,
            ),
            references=references,
            record_id=self.candidate_id,
            created_at=self.created_at,
        )


@runtime_checkable
class PatternBuilder(Protocol):
    """기계 집계(EvaluationSummary)에서 typed candidate를 만든다."""

    def propose(
        self,
        summary: EvaluationSummary,
        request: CandidateRequest,
        *,
        project_id: str,
        producer: Producer,
        created_at: datetime,
    ) -> LearningCandidate: ...


class CandidateProposer:
    """PatternBuilder 기본 구현. 의미 해석을 만들지 않고 주어진 reading만 인용한다."""

    def __init__(self, *, guard: ProtectedWriteGuard | None = None) -> None:
        self._guard = guard

    def propose(
        self,
        summary: EvaluationSummary,
        request: CandidateRequest,
        *,
        project_id: str,
        producer: Producer,
        created_at: datetime,
    ) -> LearningCandidate:
        if not summary.observations:
            raise InsufficientEvidenceError("관측 없는 후보는 만들지 않는다")
        if same_enum(request.kind, CandidateKind.POLICY) and request.target is None:
            raise LearningContractError("POLICY 후보에는 PolicyTarget이 필요하다")
        if same_enum(request.kind, CandidateKind.PATTERN) and request.target is not None:
            raise LearningContractError("PATTERN 후보는 운영 target을 바꾸지 않는다")
        if request.semantic_reading is not None:
            self._assert_meaning_author(request.semantic_reading)
        if same_enum(request.kind, CandidateKind.POLICY) and request.target is not None:
            self._assert_policy_target(request)

        entity_type = EntityType.POLICY if same_enum(request.kind, CandidateKind.POLICY) else EntityType.HYPOTHESIS
        return LearningCandidate(
            candidate_id=new_id(entity_type),
            kind=request.kind,
            project_id=project_id,
            proposed_by=producer,
            trigger_sources=request.trigger_sources,
            rule=request.rule,
            scope=request.scope,
            summary=summary,
            evidence_analysis=summary.analysis,
            applicability=request.applicability,
            created_at=created_at,
            target=request.target,
            version=request.version,
            parameters=dict(request.parameters),
            semantic_reading=request.semantic_reading,
            falsification_criteria=request.falsification_criteria,
            evaluation_plan=request.evaluation_plan,
            counterexamples=request.counterexamples,
            limitations=request.limitations,
        )

    @staticmethod
    def _assert_meaning_author(reading: SemanticReading) -> None:
        if reading.author.kind not in MEANING_AUTHORS:
            raise SemanticAuthorityError(
                f"{reading.author.kind}는 의미 해석 주체가 아니다 — 의미는 Primary/human-assisted 경로만 해석한다"
            )

    def _assert_policy_target(self, request: CandidateRequest) -> None:
        if self._guard is None or request.target is None:
            return
        decision = self._guard.evaluate_policy_target(
            request.target.value,
            rule=request.rule,
            parameters=dict(request.parameters),
            actor_kind=ActorKind.LEARNED_POLICY,
        )
        if not decision.allowed:
            raise PolicyTargetRefused(f"{decision.code.value}: {decision.detail}")


class CandidateStore:
    """candidate와 report를 append-only로 보관한다. active policy를 바꾸지 않는다."""

    def __init__(self) -> None:
        self._candidates: dict[str, LearningCandidate] = {}
        self._reports: dict[str, list[ValidationReport]] = {}
        self._records: list[Record] = []

    @property
    def candidates(self) -> tuple[LearningCandidate, ...]:
        return tuple(self._candidates.values())

    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    def append(self, candidate: LearningCandidate) -> LearningCandidate:
        if candidate.candidate_id in self._candidates:
            raise LearningContractError(f"duplicate candidate: {candidate.candidate_id}")
        self._candidates[candidate.candidate_id] = candidate
        self._records.append(candidate.to_record())
        return candidate

    def require(self, candidate_id: str) -> LearningCandidate:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise LearningContractError(f"unknown candidate: {candidate_id}")
        return candidate

    def add_report(self, report: ValidationReport) -> ValidationReport:
        """실패한 report도 보존한다. 기준 완화 대신 새 experiment ID를 만든다."""

        candidate = self.require(report.candidate_id)
        reports = self._reports.setdefault(report.candidate_id, [])
        if any(existing.report_id == report.report_id for existing in reports):
            raise LearningContractError(f"duplicate validation report: {report.report_id}")
        reports.append(report)
        self._records.append(report.to_record(candidate=candidate))
        return report

    def reports(self, candidate_id: str) -> tuple[ValidationReport, ...]:
        return tuple(self._reports.get(candidate_id, ()))

    def passed_report(self, candidate_id: str) -> ValidationReport | None:
        return next((report for report in self._reports.get(candidate_id, ()) if report.passed), None)


# ─── validation ─────────────────────────────────────────────────────


def new_split_id(role: ValidationRole) -> str:
    return f"split_{role.value.lower()}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class ValidationSplit:
    """사전 등록된 frozen split. 실행 뒤에 만들거나 바꾸지 않는다."""

    split_id: str
    role: ValidationRole
    task_ids: tuple[str, ...]
    source: str
    registered_at: datetime
    manifest_digest: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "split_id": self.split_id,
            "role": self.role.value,
            "task_ids": list(self.task_ids),
            "source": self.source,
            "registered_at": self.registered_at.isoformat(),
            "manifest_digest": self.manifest_digest,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


@dataclass(frozen=True, slots=True)
class ValidationCriterion:
    """실행 전에 고정한 합격 기준. 결과를 본 뒤 완화하면 새 experiment ID가 필요하다."""

    experiment_id: str
    metric_name: str
    minimum_value: float
    registered_at: datetime
    noninferiority_margin: float = 0.0
    required_independent_episodes: int = MIN_INDEPENDENT_EPISODES
    minimum_samples: int = MIN_INDEPENDENT_EPISODES

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "metric_name": self.metric_name,
            "minimum_value": self.minimum_value,
            "noninferiority_margin": self.noninferiority_margin,
            "required_independent_episodes": self.required_independent_episodes,
            "minimum_samples": self.minimum_samples,
            "registered_at": self.registered_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


@dataclass(frozen=True, slots=True)
class ValidationObservation:
    """frozen split의 task 하나에 대한 관측. success=None은 UNKNOWN이다."""

    task_id: str
    success: bool | None
    negative_transfer: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """validation 결과. 실패 report도 지우지 않는다."""

    report_id: str
    candidate_id: str
    validator_id: str
    split_ids: tuple[str, ...]
    split_roles: tuple[str, ...]
    method: str
    metrics: tuple[MetricResult, ...]
    passed: bool
    independent_episode_count: int
    criterion: ValidationCriterion
    negative_transfer_count: int
    limitations: tuple[str, ...]
    generated_at: datetime
    checks: Mapping[str, str] = field(default_factory=dict)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "report_id": self.report_id,
            "candidate_id": self.candidate_id,
            "validator_id": self.validator_id,
            "split_ids": list(self.split_ids),
            "split_roles": list(self.split_roles),
            "method": self.method,
            "metrics": [{"name": metric.name, "value": metric.value} for metric in self.metrics],
            "passed": self.passed,
            "independent_episode_count": self.independent_episode_count,
            "criterion": self.criterion.as_mapping(),
            "negative_transfer_count": self.negative_transfer_count,
            "checks": dict(self.checks),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    @property
    def broader_validated(self) -> bool:
        """broader split까지 마친 report인지. Principle 승격 조건이다."""

        return ValidationRole.BROADER.value in self.split_roles

    def to_record(self, *, candidate: LearningCandidate) -> Record:
        references = tuple(
            Reference(relation=REL_EVIDENCE, target_id=evidence_id, expected_type=EntityType.EVIDENCE)
            for evidence_id in candidate.evidence_ids
        )
        return Record.create(
            entity_type=EntityType.VALIDATION_REPORT,
            project_id=candidate.project_id,
            producer=Producer(kind=ProducerKind.BODY, actor_id=self.validator_id),
            payload=ValidationReportPayload(
                candidate_id=self.candidate_id,
                split_ids=self.split_ids,
                method=self.method,
                metrics=self.metrics,
                passed=self.passed,
                limitations=self.limitations,
                independent_episode_count=self.independent_episode_count,
            ),
            references=references,
            record_id=self.report_id,
            created_at=self.generated_at,
        )


@runtime_checkable
class Validator(Protocol):
    """후보를 frozen split에서 검증한다. 승격 판정은 하지 않는다."""

    def validate(
        self,
        candidate: LearningCandidate,
        *,
        split: ValidationSplit,
        criterion: ValidationCriterion,
        observations: Sequence[ValidationObservation],
        generated_at: datetime,
    ) -> ValidationReport: ...


class HeldOutValidator:
    """held-out / broader split 검증기. 계약 위반은 예외로, 측정 실패는 report로 남긴다."""

    def __init__(self, *, validator_id: str = "validator:held-out") -> None:
        self._validator_id = validator_id

    @property
    def validator_id(self) -> str:
        return self._validator_id

    def validate(
        self,
        candidate: LearningCandidate,
        *,
        split: ValidationSplit,
        criterion: ValidationCriterion,
        observations: Sequence[ValidationObservation],
        generated_at: datetime,
    ) -> ValidationReport:
        if same_enum(split.role, ValidationRole.LEARNING):
            raise ValidationBypassRefused("학습에 쓴 split으로 검증할 수 없다 — 별도 validation split이 필요하다")
        overlap = sorted(set(candidate.task_ids) & set(split.task_ids))
        if overlap:
            raise ValidationBypassRefused(f"학습 task와 검증 task가 분리되지 않았다: {overlap}")
        if set(candidate.trigger_sources) <= EVIDENCE_FREE_TRIGGERS:
            raise InsufficientEvidenceError(
                "grade/cooldown/Brain 해석 trigger는 후보 발생 계기일 뿐이다 — 별도 근거가 필요하다"
            )
        if summarize(candidate.summary.observations).digest() != candidate.evidence_analysis.digest():
            raise EvidenceMismatchError("candidate가 주장한 근거 집계와 episode 집계가 다르다")
        required = max(criterion.required_independent_episodes, MIN_INDEPENDENT_EPISODES)
        if candidate.independent_episode_count < required:
            raise InsufficientEvidenceError(
                f"독립 episode가 부족하다: {candidate.independent_episode_count} < {required}"
                " (중복 원자료는 독립 replication으로 세지 않는다)"
            )
        if TriggerSource.FAILURE in candidate.trigger_sources and candidate.evidence_analysis.decision_failures == 0:
            raise InsufficientEvidenceError(
                "결과 실패를 판단 실패로 자동 치환한 후보는 검증할 수 없다 — 당시 정보로 판단이 합리적이었다"
            )

        negative_transfer = sum(1 for observation in observations if observation.negative_transfer)
        unknown = sum(1 for observation in observations if observation.success is None)
        success_rate = (
            sum(1 for observation in observations if observation.success) / len(observations) if observations else 0.0
        )
        checks: dict[str, str] = {
            "sample_size": "PASS" if len(observations) >= criterion.minimum_samples else "FAIL",
            "metric_threshold": "PASS" if success_rate >= criterion.minimum_value else "FAIL",
            "unknown_outcomes": "PASS" if unknown == 0 else "FAIL",
            "negative_transfer": "PASS" if negative_transfer == 0 else "FAIL",
        }
        limitations = [
            f"{name}: {status} ({criterion.metric_name}={success_rate:.3f}, 기준 {criterion.minimum_value:.3f})"
            for name, status in checks.items()
            if status == "FAIL"
        ]
        if unknown:
            limitations.append(f"UNKNOWN 결과 {unknown}건은 성공으로 세지 않는다")
        passed = all(status == "PASS" for status in checks.values())
        metrics = (
            MetricResult(
                name=criterion.metric_name,
                value=success_rate,
                unit="ratio",
                denominator=f"{len(observations)} tasks",
                measured_window=criterion.experiment_id,
            ),
        )
        return ValidationReport(
            report_id=new_id(EntityType.VALIDATION_REPORT),
            candidate_id=candidate.candidate_id,
            validator_id=self._validator_id,
            split_ids=(split.split_id,),
            split_roles=(split.role.value,),
            method="frozen_held_out_split"
            if not same_enum(split.role, ValidationRole.BROADER)
            else "frozen_broader_split",
            metrics=metrics,
            passed=passed,
            independent_episode_count=candidate.independent_episode_count,
            criterion=criterion,
            negative_transfer_count=negative_transfer,
            limitations=tuple(limitations),
            generated_at=generated_at,
            checks=checks,
        )


# ─── knowledge lifecycle ────────────────────────────────────────────


def _knowledge_payload(
    target: KnowledgeTarget,
    candidate: LearningCandidate,
    report: ValidationReport | None,
    confidence_profile: ConfidenceProfile | None,
) -> HypothesisPayload | StrategyPayload | PrinciplePayload:
    lifecycle = KnowledgeLifecycle.SUPPORTED if report is not None and report.passed else KnowledgeLifecycle.CANDIDATE
    if same_enum(target, KnowledgeTarget.STRATEGY):
        return StrategyPayload(
            operational_rule=candidate.rule,
            applicability=candidate.applicability,
            exceptions=candidate.counterexamples,
            lifecycle=lifecycle,
        )
    if same_enum(target, KnowledgeTarget.PRINCIPLE):
        assert confidence_profile is not None  # KnowledgeLedger.add가 먼저 검사한다.
        return PrinciplePayload(
            statement=candidate.rule,
            scope=candidate.scope,
            confidence_profile=confidence_profile,
            applicability=candidate.applicability,
            lifecycle=lifecycle,
        )
    return HypothesisPayload(
        claim=candidate.rule,
        falsification_criteria=candidate.falsification_criteria or ("반증 조건이 아직 정의되지 않았다",),
        evaluation_plan=candidate.evaluation_plan or candidate.scope,
    )


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    """support 수준 knowledge 하나. lifecycle 상향은 report_id가 있어야 한다."""

    item_id: str
    target: KnowledgeTarget
    statement: str
    scope: str
    lifecycle: KnowledgeLifecycle
    candidate_id: str
    report_id: str | None
    record_digest: str
    created_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "item_id": self.item_id,
            "target": self.target.value,
            "statement": self.statement,
            "scope": self.scope,
            "lifecycle": self.lifecycle.value,
            "candidate_id": self.candidate_id,
            "report_id": self.report_id,
            "record_digest": self.record_digest,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeRevision:
    """challenged/scoped/revised/retired 전이. 원본 digest를 그대로 보존한다."""

    revision_id: str
    item_id: str
    lifecycle: KnowledgeLifecycle
    reason: str
    evidence_ids: tuple[str, ...]
    supersedes_revision: str | None
    original_record_digest: str
    recorded_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "revision_id": self.revision_id,
            "item_id": self.item_id,
            "lifecycle": self.lifecycle.value,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "supersedes_revision": self.supersedes_revision,
            "original_record_digest": self.original_record_digest,
            "recorded_at": self.recorded_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


@dataclass(frozen=True, slots=True)
class ApplicabilityReview:
    """적용 여부 판정. confidence는 판정 입력이지 적용 근거가 아니다."""

    disposition: ApplicabilityDisposition
    level: ApplicabilityLevel
    reason: str
    mismatched_fields: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "disposition": self.disposition.value,
            "level": self.level.value,
            "reason": self.reason,
            "mismatched_fields": list(self.mismatched_fields),
            "unknown_fields": list(self.unknown_fields),
        }


class KnowledgeLedger:
    """Hypothesis/Strategy/Principle 승격과 관리 전이를 append-only로 남긴다."""

    def __init__(self) -> None:
        self._items: dict[str, KnowledgeItem] = {}
        self._revisions: dict[str, list[KnowledgeRevision]] = {}
        self._records: list[Record] = []

    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    @property
    def items(self) -> tuple[KnowledgeItem, ...]:
        return tuple(self._items.values())

    def item(self, item_id: str) -> KnowledgeItem:
        item = self._items.get(item_id)
        if item is None:
            raise LearningContractError(f"unknown knowledge item: {item_id}")
        return item

    def revisions(self, item_id: str) -> tuple[KnowledgeRevision, ...]:
        return tuple(self._revisions.get(item_id, ()))

    def add(
        self,
        candidate: LearningCandidate,
        *,
        target: KnowledgeTarget,
        scope: str,
        created_at: datetime,
        report: ValidationReport | None = None,
        semantic_reading: SemanticReading | None = None,
        confidence_profile: ConfidenceProfile | None = None,
    ) -> KnowledgeItem:
        """candidate를 knowledge로 승격한다. 검증 없는 support 수준 승격은 거부한다."""

        if same_enum(candidate.kind, CandidateKind.POLICY):
            raise NotPromotableError("운영 policy 승격은 PolicyStore가 담당한다")
        if semantic_reading is not None and semantic_reading.author.kind not in MEANING_AUTHORS:
            raise SemanticAuthorityError("의미 해석 주제가 Primary/human-assisted 경로가 아니다")
        if not same_enum(target, KnowledgeTarget.HYPOTHESIS) and (report is None or not report.passed):
            raise NotPromotableError(f"{target.value} 승격에는 통과한 validation report가 필요하다")
        if same_enum(target, KnowledgeTarget.PRINCIPLE):
            assert report is not None
            if not report.broader_validated:
                raise ValidationBypassRefused("Principle 승격에는 broader validation이 필요하다")
            if candidate.independent_episode_count < MIN_INDEPENDENT_EPISODES:
                raise InsufficientEvidenceError("Principle 승격에는 독립 episode 2건 이상이 필요하다")
            if not candidate.evidence_ids:
                raise NotPromotableError("의미 해석만으로 Principle을 세우지 않는다 — Evidence reference가 필요하다")
            if confidence_profile is None:
                raise NotPromotableError("Principle 승격에는 Primary/human이 남긴 confidence profile이 필요하다")

        references = tuple(
            Reference(relation=REL_EVIDENCE, target_id=evidence_id, expected_type=EntityType.EVIDENCE)
            for evidence_id in candidate.evidence_ids
        )
        record = Record.create(
            entity_type=KNOWLEDGE_ENTITY[target],
            project_id=candidate.project_id,
            producer=candidate.proposed_by,
            payload=_knowledge_payload(target, candidate, report, confidence_profile),
            references=references,
            created_at=created_at,
        )
        item = KnowledgeItem(
            item_id=record.id,
            target=target,
            statement=candidate.rule,
            scope=scope,
            lifecycle=KnowledgeLifecycle.SUPPORTED
            if report is not None and report.passed
            else KnowledgeLifecycle.CANDIDATE,
            candidate_id=candidate.candidate_id,
            report_id=report.report_id if report is not None else None,
            record_digest=_digest(record.model_dump(mode="json")),
            created_at=created_at,
        )
        self._items[item.item_id] = item
        self._records.append(record)
        return item

    def revise(
        self,
        item_id: str,
        *,
        lifecycle: KnowledgeLifecycle,
        reason: str,
        recorded_at: datetime,
        evidence_ids: Sequence[str] = (),
    ) -> KnowledgeRevision:
        """관리 전이는 append 사건이다. 원본 item의 lifecycle·digest는 그대로다."""

        item = self.item(item_id)
        if lifecycle not in MANAGEMENT_LIFECYCLES:
            raise NotPromotableError(f"{lifecycle.value} 전이는 validation report가 필요한 승격 경로다")
        if not reason:
            raise LearningContractError("전이에는 이유가 필요하다")
        existing = self._revisions.setdefault(item_id, [])
        revision = KnowledgeRevision(
            revision_id=f"{item_id}:revision:{len(existing) + 1}",
            item_id=item_id,
            lifecycle=lifecycle,
            reason=reason,
            evidence_ids=tuple(evidence_ids),
            supersedes_revision=existing[-1].revision_id if existing else None,
            original_record_digest=item.record_digest,
            recorded_at=recorded_at,
        )
        existing.append(revision)
        return revision

    def reassess_applicability(
        self,
        profile: ApplicabilityProfile,
        *,
        knowledge_confidence: ConfidenceProfile,
    ) -> ApplicabilityReview:
        """confidence가 높아도 현재 applicability가 MISMATCH면 자동 적용하지 않는다."""

        mismatched = tuple(
            name for name in _APPLICABILITY_FIELDS if same_enum(getattr(profile, name), ApplicabilityLevel.MISMATCH)
        )
        unknown = tuple(
            name for name in _APPLICABILITY_FIELDS if same_enum(getattr(profile, name), ApplicabilityLevel.UNKNOWN)
        )
        if mismatched:
            return ApplicabilityReview(
                disposition=ApplicabilityDisposition.WITHHOLD,
                level=ApplicabilityLevel.MISMATCH,
                reason=(
                    "현재 applicability가 MISMATCH다 — confidence"
                    f"(evidence_strength={knowledge_confidence.evidence_strength})와 무관하게 자동 적용하지 않는다"
                ),
                mismatched_fields=mismatched,
                unknown_fields=unknown,
            )
        if unknown:
            return ApplicabilityReview(
                disposition=ApplicabilityDisposition.APPLY_WITH_SCOPE,
                level=ApplicabilityLevel.UNKNOWN,
                reason="일부 축이 UNKNOWN이다 — scope를 좁혀 적용하고 UNKNOWN을 기록한다",
                unknown_fields=unknown,
            )
        if any(same_enum(getattr(profile, name), ApplicabilityLevel.PARTIAL) for name in _APPLICABILITY_FIELDS):
            return ApplicabilityReview(
                disposition=ApplicabilityDisposition.APPLY_WITH_SCOPE,
                level=ApplicabilityLevel.PARTIAL,
                reason="부분 일치다 — 예외 범위를 함께 적용한다",
            )
        return ApplicabilityReview(
            disposition=ApplicabilityDisposition.APPLY,
            level=ApplicabilityLevel.MATCH,
            reason="모든 applicability 축이 일치한다",
        )


__all__ = [
    "EVIDENCE_FREE_TRIGGERS",
    "FAILURE_OUTCOMES",
    "KNOWLEDGE_ENTITY",
    "MANAGEMENT_LIFECYCLES",
    "MEANING_AUTHORS",
    "MIN_INDEPENDENT_EPISODES",
    "ApplicabilityDisposition",
    "ApplicabilityReview",
    "CandidateKind",
    "CandidateProposer",
    "CandidateRequest",
    "CandidateStore",
    "EpisodeObservation",
    "EvaluationSummary",
    "EvidenceAnalysis",
    "EvidenceMismatchError",
    "ExperienceEvaluator",
    "HeldOutValidator",
    "InsufficientEvidenceError",
    "KnowledgeItem",
    "KnowledgeLedger",
    "KnowledgeRevision",
    "KnowledgeTarget",
    "LearningCandidate",
    "LearningContractError",
    "MeaningInterpreter",
    "MeaningRequest",
    "NotPromotableError",
    "PatternBuilder",
    "PolicyTargetRefused",
    "SemanticAuthorityError",
    "SemanticReading",
    "TriggerSource",
    "ValidationBypassRefused",
    "ValidationCriterion",
    "ValidationObservation",
    "ValidationReport",
    "ValidationRole",
    "ValidationSplit",
    "Validator",
    "new_split_id",
    "summarize",
]
