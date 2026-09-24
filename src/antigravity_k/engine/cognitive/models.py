"""Typed Cognitive Model (P01) — canonical record 30종과 envelope.

원문 데이터 계약(COGNITIVE_DATA_MODEL.md)을 실행 가능한 discriminated union으로 구현한다.

불변 규칙:
- 모든 record는 ``schema_version='1.0'``, canonical ID, timezone-aware UTC 시간을 가진다.
- Observation에는 해석을 섞지 않는다. 해석은 Interpretation record로 분리한다.
- BrainJudgment의 ground는 Evidence reference로만 인정한다. 자유문 justification은 거부한다.
- Policy는 allowlist된 운영 knob만 대상으로 한다. 헌법·authority grant를 대상으로 쓸 수 없다.
- 알 수 없는 필드(extra)는 거부한다. 미정의 payload는 실행되지 않는다.

이 모듈은 provider/UI/저장소를 import하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from antigravity_k.engine.cognitive.references import (
    ENTITY_NAMESPACES,
    ID_PATTERN,
    REL_CONSTITUTION_RULE,
    REL_GROUND,
    EntityType,
    Reference,
    namespace_for,
    new_id,
)

SCHEMA_VERSION: Final[str] = "1.0"
SUPPORTED_SCHEMA_MAJOR: Final[str] = "1"


class UnsupportedSchemaError(ValueError):
    """알 수 없는 schema major를 격리한다. 실행하지 않는다."""


class CanonicalInvariantError(ValueError):
    """entity/envelope 불변 조건 위반."""


def ensure_utc(value: datetime) -> datetime:
    """naive 시간을 거부하고 UTC로 정규화한다."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime rejected: canonical records store timezone-aware UTC time")
    return value.astimezone(UTC)


def same_enum(left: object, right: object) -> bool:
    """두 값이 **같은 enum 계열의 같은 값**인지 판정한다.

    왜 ``is``나 ``==``를 그대로 쓰지 않는가:

    - ``left is Enum.MEMBER``는 판정 주체와 값이 같은 이름의 class를 **다른 객체**로 들고 있으면
      (module이 두 번 로드되는 경우) False가 된다. 권한·readiness·receipt 판정이 "아직 충분하지 않다"나
      "미완료"처럼 **조용히 다른 답**으로 흘러가는 부류다.
    - ``left == Enum.MEMBER``만 쓰면 정의 module이 다른 **다른 enum**까지 같다고 본다
      (예: cognitive ``RiskLevel`` vs 도구 ``RiskLevel``은 같은 문자열 값을 가진다).

    그래서 정의 module 이름·class 이름·값을 함께 본다: module 중복 로드에는 관대하고, 다른 enum type에는
    엄격하다. enum이 아닌 값(문자열·None·임의 객체)은 ``is``와 동일하게 False다.
    """

    if left is right:
        return True
    left_type = type(left)
    right_type = type(right)
    if not (isinstance(left_type, type) and issubclass(left_type, Enum)):
        return False
    if not (isinstance(right_type, type) and issubclass(right_type, Enum)):
        return False
    if (left_type.__module__, left_type.__qualname__) != (right_type.__module__, right_type.__qualname__):
        return False
    return left.value == right.value  # type: ignore[attr-defined]


UtcDatetime = Annotated[AwareDatetime, AfterValidator(ensure_utc)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
ScalarParameter = str | int | float | bool


# ─── enum ────────────────────────────────────────────────────────────


class ProducerKind(StrEnum):
    HUMAN = "human"
    BRAIN = "brain"
    BODY = "body"
    TOOL = "tool"


class EvidenceKind(StrEnum):
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    EXPERIENCE = "EXPERIENCE"
    INFERENCE = "INFERENCE"
    PRINCIPLE = "PRINCIPLE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"
    HUMAN_INPUT = "HUMAN_INPUT"
    MODEL_JUDGMENT = "MODEL_JUDGMENT"


class ApplicabilityLevel(StrEnum):
    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class KnowledgeLifecycle(StrEnum):
    CANDIDATE = "CANDIDATE"
    PROVISIONAL = "PROVISIONAL"
    SUPPORTED = "SUPPORTED"
    ESTABLISHED = "ESTABLISHED"
    CHALLENGED = "CHALLENGED"
    SCOPED = "SCOPED"
    REVISED = "REVISED"
    RETIRED = "RETIRED"


class GoalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    BLOCKED = "BLOCKED"
    ABANDONED = "ABANDONED"


class AssumptionStatus(StrEnum):
    UNTESTED = "UNTESTED"
    HELD = "HELD"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


class UnknownCategory(StrEnum):
    DEFINITION = "DEFINITION"
    CONTEXT = "CONTEXT"
    VERSION_TIME = "VERSION_TIME"
    MEASUREMENT = "MEASUREMENT"
    SOURCE = "SOURCE"
    EXECUTION = "EXECUTION"
    SEMANTIC = "SEMANTIC"
    RESOURCE = "RESOURCE"
    AUTHORITY = "AUTHORITY"
    OTHER = "OTHER"


class UnknownMateriality(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    MATERIAL = "MATERIAL"
    BLOCKING = "BLOCKING"
    LATENT = "LATENT"


class InvestigationStatus(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    NOT_INVESTIGATED = "NOT_INVESTIGATED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    DEEMED_UNNECESSARY = "DEEMED_UNNECESSARY"


class CognitiveRequestType(StrEnum):
    MORE_CONTEXT = "MORE_CONTEXT"
    MEMORY = "MEMORY"
    TOOL = "TOOL"
    TEST_OR_SIMULATION = "TEST_OR_SIMULATION"
    SECONDARY_BRAIN = "SECONDARY_BRAIN"
    EXTERNAL_EVIDENCE = "EXTERNAL_EVIDENCE"


class GovernanceDisposition(StrEnum):
    APPROVE = "APPROVE"
    APPROVE_WITH_LIMITS = "APPROVE_WITH_LIMITS"
    RESHAPE = "RESHAPE"
    DEFER = "DEFER"
    DENY = "DENY"


class ClosureState(StrEnum):
    OPEN = "open"
    CLOSED_FOR_ACTION = "closed_for_action"
    REOPENED = "reopened"


class ReopenTrigger(StrEnum):
    NEW_MATERIAL_EVIDENCE = "NEW_MATERIAL_EVIDENCE"
    UNEXPECTED_OUTCOME = "UNEXPECTED_OUTCOME"
    MATERIAL_CONTRADICTION = "MATERIAL_CONTRADICTION"
    CONTEXT_DRIFT = "CONTEXT_DRIFT"
    ASSUMPTION_FAILURE = "ASSUMPTION_FAILURE"
    RISK_CHANGE = "RISK_CHANGE"
    AUTHORITY_CHANGE = "AUTHORITY_CHANGE"
    HUMAN_REOPEN = "HUMAN_REOPEN"


class ActionExecutionStatus(StrEnum):
    PLANNED = "PLANNED"
    AUTHORIZED = "AUTHORIZED"
    DISPATCHED = "DISPATCHED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class ObservationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    DELAYED = "DELAYED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class OutcomeStatus(StrEnum):
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    MATCH = "MATCH"
    DEVIATION = "DEVIATION"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class IntegrityStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ReadinessCheck(StrEnum):
    """원문 §16의 9개 readiness check. semantic correctness는 포함하지 않는다."""

    GROUND_EXISTS = "GROUND_EXISTS"
    EVIDENCE_PROVENANCE_LINKED = "EVIDENCE_PROVENANCE_LINKED"
    MATERIAL_UNKNOWN_EXPLICIT = "MATERIAL_UNKNOWN_EXPLICIT"
    HARD_CONSTRAINTS_SATISFIED = "HARD_CONSTRAINTS_SATISFIED"
    RESIDUAL_RISK_MANAGEABLE = "RESIDUAL_RISK_MANAGEABLE"
    AUTHORITY_SUFFICIENT = "AUTHORITY_SUFFICIENT"
    VERIFICATION_SUFFICIENT = "VERIFICATION_SUFFICIENT"
    ROLLBACK_SUFFICIENT = "ROLLBACK_SUFFICIENT"
    ACTION_SCOPE_CLEAR = "ACTION_SCOPE_CLEAR"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    N_A = "N_A"


class ReadinessVerdict(StrEnum):
    READY = "READY"
    READY_WITH_GUARDS = "READY_WITH_GUARDS"
    NOT_READY = "NOT_READY"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    UNKNOWN = "UNKNOWN"


class PolicyTarget(StrEnum):
    """§36 개선 영역의 운영 knob만 policy target이 될 수 있다(헌법·권한은 제외)."""

    CONTEXT_SELECTION = "CONTEXT_SELECTION"
    CONTEXT_DEPTH = "CONTEXT_DEPTH"
    EXPERIENCE_RETRIEVAL = "EXPERIENCE_RETRIEVAL"
    BRAIN_ENGAGEMENT_DEPTH = "BRAIN_ENGAGEMENT_DEPTH"
    COGNITIVE_EXPANSION = "COGNITIVE_EXPANSION"
    TOOL_SELECTION = "TOOL_SELECTION"
    SECONDARY_BRAIN_USAGE = "SECONDARY_BRAIN_USAGE"
    CONFLICT_INVESTIGATION = "CONFLICT_INVESTIGATION"
    UNKNOWN_INVESTIGATION = "UNKNOWN_INVESTIGATION"
    CLOSURE_TIMING = "CLOSURE_TIMING"
    RISK_SHAPING = "RISK_SHAPING"
    VERIFICATION_DEPTH = "VERIFICATION_DEPTH"
    ACTION_GOVERNANCE = "ACTION_GOVERNANCE"
    AUTHORITY_DELEGATION = "AUTHORITY_DELEGATION"


class AuthorityDimension(StrEnum):
    REASONING_FREEDOM = "REASONING_FREEDOM"
    MEMORY_READ = "MEMORY_READ"
    TOOL_READ = "TOOL_READ"
    TOOL_WRITE = "TOOL_WRITE"
    SECONDARY_BRAIN = "SECONDARY_BRAIN"
    CODE_MODIFICATION = "CODE_MODIFICATION"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    RESOURCE = "RESOURCE"
    FINANCIAL = "FINANCIAL"
    CONSTITUTIONAL = "CONSTITUTIONAL"


class LoopState(StrEnum):
    PREPARE = "PREPARE"
    THINK = "THINK"
    GOVERN = "GOVERN"
    EXECUTE = "EXECUTE"
    FEEDBACK = "FEEDBACK"
    TARGETED_RETHINK = "TARGETED_RETHINK"
    COMMIT = "COMMIT"
    ACTION = "ACTION"
    OBSERVE = "OBSERVE"
    EXPERIENCE = "EXPERIENCE"
    LEARN = "LEARN"
    BLOCKED_CONTEXT = "BLOCKED_CONTEXT"
    BLOCKED_READINESS = "BLOCKED_READINESS"
    BRAIN_FAILED = "BRAIN_FAILED"
    DEFERRED = "DEFERRED"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    ACTION_OUTCOME_UNKNOWN = "ACTION_OUTCOME_UNKNOWN"
    OBSERVATION_PENDING = "OBSERVATION_PENDING"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    CANCELLED = "CANCELLED"


class SelectionDisposition(StrEnum):
    """Experience 선별 disposition. 공통 의미 계약의 최소 표현이다(별도 entity를 만들지 않는다)."""

    OPERATIONAL_ONLY = "OPERATIONAL_ONLY"
    EXPERIENCE = "EXPERIENCE"
    DEFERRED = "DEFERRED"


class SelectionReason(StrEnum):
    """선별 사유. 원문 §21~23과 Roadmap 공통 의미 계약의 항목이다."""

    MATERIAL_DELTA = "MATERIAL_DELTA"
    ASSUMPTION_TESTED = "ASSUMPTION_TESTED"
    UNKNOWN_CHANGED = "UNKNOWN_CHANGED"
    FAILURE = "FAILURE"
    RECOVERY = "RECOVERY"
    RISK_SHAPING = "RISK_SHAPING"
    ROLLBACK = "ROLLBACK"
    ENVIRONMENT_DIFFERENCE = "ENVIRONMENT_DIFFERENCE"
    HUMAN_FEEDBACK = "HUMAN_FEEDBACK"
    AUTHORITY_CHANGE = "AUTHORITY_CHANGE"
    INDEPENDENT_REVALIDATION = "INDEPENDENT_REVALIDATION"
    ROUTINE = "ROUTINE"
    UNRESOLVED = "UNRESOLVED"


class ReceiptStatus(StrEnum):
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class DisclosureLevel(StrEnum):
    L0_SIGNAL = "L0_SIGNAL"
    L1_SUMMARY = "L1_SUMMARY"
    L2_DETAIL = "L2_DETAIL"
    L3_RAW = "L3_RAW"


class MemoryAccessibility(StrEnum):
    ACTIVE = "ACTIVE"
    WATCH = "WATCH"
    LATENT = "LATENT"
    DORMANT = "DORMANT"
    ARCHIVED = "ARCHIVED"


# ─── 공통 값 객체 ────────────────────────────────────────────────────


class EntityPayloadModel(BaseModel):
    """payload 공통 설정. 미정의 필드는 거부하고 생성 후 변경할 수 없다."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Producer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ProducerKind
    actor_id: str = Field(min_length=1)


class Provenance(BaseModel):
    """Evidence의 출처. 모델 판단과 관측을 같은 kind로 평탄화하지 않는다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_uri: str = Field(min_length=1)
    source_version: str = ""
    content_digest: str = Field(min_length=1)
    observed_at: UtcDatetime
    ingested_at: UtcDatetime
    access_scope: str = "project"


class ResourceBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tokens: int | None = Field(default=None, ge=0)
    seconds: float | None = Field(default=None, ge=0.0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    rounds: int | None = Field(default=None, ge=0)


class ConfidenceProfile(BaseModel):
    """단일 confidence scalar를 Core 표현으로 쓰지 않는다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_strength: Confidence
    independence: Confidence
    replication: Confidence
    contradiction: Confidence
    context_coverage: Confidence


class ApplicabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_match: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    context_match: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    constraint_match: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    environment_match: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    action_match: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    known_exception: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN
    context_drift: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN


class RiskProfile(BaseModel):
    """10개 차원을 따로 기록한다. 하나의 risk score로 합성하지 않는다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reversibility: RiskLevel = RiskLevel.UNKNOWN
    blast_radius: RiskLevel = RiskLevel.UNKNOWN
    data_state_loss: RiskLevel = RiskLevel.UNKNOWN
    external_impact: RiskLevel = RiskLevel.UNKNOWN
    security_privacy: RiskLevel = RiskLevel.UNKNOWN
    authority_sensitivity: RiskLevel = RiskLevel.UNKNOWN
    verification: RiskLevel = RiskLevel.UNKNOWN
    rollback: RiskLevel = RiskLevel.UNKNOWN
    cost: RiskLevel = RiskLevel.UNKNOWN
    goal_premise_impact: RiskLevel = RiskLevel.UNKNOWN


class ReadinessCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check: ReadinessCheck
    status: CheckStatus
    reason: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()


class DecisionAssurance(BaseModel):
    """readiness check 결과 집합. 단일 scalar로 축약하지 않는다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: ReadinessVerdict
    check_results: tuple[ReadinessCheckResult, ...]
    decision_revision: int = Field(ge=1)
    authority_revision: int | None = Field(default=None, ge=1)
    action_digest: str | None = None
    state_revision: int = Field(ge=1)
    policy_version: str | None = None

    @model_validator(mode="after")
    def _require_all_nine_checks(self) -> DecisionAssurance:
        seen = {result.check for result in self.check_results}
        missing = [check for check in ReadinessCheck if check not in seen]
        if missing:
            raise CanonicalInvariantError(f"DecisionAssurance missing readiness checks: {missing}")
        if same_enum(self.verdict, ReadinessVerdict.NOT_READY) and not any(
            not same_enum(result.status, CheckStatus.PASS) for result in self.check_results
        ):
            raise CanonicalInvariantError("NOT_READY verdict without failing check")
        return self


class GovernanceFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_request_digest: str = Field(min_length=1)
    what_changed: tuple[str, ...] = ()
    why_changed: str = ""
    remaining_constraints: tuple[str, ...] = ()
    available_alternatives: tuple[str, ...] = ()
    execution_receipt_id: str | None = Field(default=None, pattern=ID_PATTERN)


class AuthorityGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    dimension: AuthorityDimension
    resource_scope: str = Field(min_length=1)
    allowed_operations: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    granted_by: str = Field(min_length=1)
    issued_at: UtcDatetime
    expires_at: UtcDatetime | None = None
    revision: int = Field(ge=1)
    revoked_at: UtcDatetime | None = None


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(pattern=ID_PATTERN)
    reason_selected: str = Field(min_length=1)
    token_estimate: int = Field(ge=0)
    disclosure_level: DisclosureLevel
    applicability: ApplicabilityLevel = ApplicabilityLevel.UNKNOWN


class ContextExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(pattern=ID_PATTERN)
    reason_excluded: str = Field(min_length=1)
    token_estimate: int = Field(ge=0)


class ContextHandleRef(BaseModel):
    """handle은 capability token이 아니다. 조회 시 현재 권한을 다시 확인한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle_id: str = Field(min_length=1)
    project_id: str = Field(pattern=ID_PATTERN)
    owner_scope: str = Field(min_length=1)
    record_id: str = Field(pattern=ID_PATTERN)
    record_revision: int | None = Field(default=None, ge=1)
    content_digest: str = Field(min_length=1)
    disclosure_level: DisclosureLevel
    expires_at: UtcDatetime | None = None


class ContextBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token_budget: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    l0_reserved_tokens: int = Field(ge=0)


class ProjectionState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_version: str = Field(min_length=1)
    last_event_sequence: int = Field(ge=0)


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    value: float
    unit: str = ""
    denominator: str = ""
    measured_window: str = ""


# ─── payload 30종 ────────────────────────────────────────────────────


class ProjectPayload(EntityPayloadModel):
    entity_type: Literal["Project"] = "Project"
    name: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    human_partner_ref: str | None = Field(default=None, pattern=ID_PATTERN)
    protected_constraints: tuple[str, ...] = ()


class GoalPayload(EntityPayloadModel):
    entity_type: Literal["Goal"] = "Goal"
    statement: str = Field(min_length=1)
    success_criteria: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    status: GoalStatus = GoalStatus.PROPOSED


class EvidencePayload(EntityPayloadModel):
    entity_type: Literal["Evidence"] = "Evidence"
    kind: EvidenceKind
    claim: str = Field(min_length=1)
    provenance: Provenance
    time: UtcDatetime
    digest: str = Field(min_length=1)
    independence_group: str | None = None


class BrainJudgmentPayload(EntityPayloadModel):
    entity_type: Literal["BrainJudgment"] = "BrainJudgment"
    current_judgment: str = Field(min_length=1)
    grounds: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    requests: tuple[str, ...] = ()
    confidence: Confidence
    confidence_reason: str = ""
    brain_version: str = Field(min_length=1)
    context_digest: str = Field(min_length=1)


class AssumptionPayload(EntityPayloadModel):
    entity_type: Literal["Assumption"] = "Assumption"
    statement: str = Field(min_length=1)
    validity_scope: str = Field(min_length=1)
    status: AssumptionStatus = AssumptionStatus.UNTESTED


class UnknownPayload(EntityPayloadModel):
    entity_type: Literal["Unknown"] = "Unknown"
    question: str = Field(min_length=1)
    category: UnknownCategory
    materiality: UnknownMateriality
    materiality_reason: str = Field(min_length=1)
    potential_action_change: bool
    investigation_status: InvestigationStatus = InvestigationStatus.NOT_ASSESSED
    investigation_cost: str = ""
    disposition_reason: str = ""


class AlternativePayload(EntityPayloadModel):
    entity_type: Literal["Alternative"] = "Alternative"
    proposed_action: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)
    tradeoffs: tuple[str, ...] = ()
    selection_reason: str | None = None


class CognitiveRequestPayload(EntityPayloadModel):
    entity_type: Literal["CognitiveRequest"] = "CognitiveRequest"
    request_type: CognitiveRequestType
    purpose: str = Field(min_length=1)
    target: str = Field(min_length=1)
    expected_value: str = Field(min_length=1)
    expected_decision_impact: str = Field(min_length=1)
    args_digest: str = Field(min_length=1)
    budget: ResourceBudget | None = None


class GovernanceDecisionPayload(EntityPayloadModel):
    entity_type: Literal["GovernanceDecision"] = "GovernanceDecision"
    disposition: GovernanceDisposition
    changes: tuple[str, ...] = ()
    reason: str = Field(min_length=1)
    limits: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    feedback: GovernanceFeedback


class DecisionPayload(EntityPayloadModel):
    entity_type: Literal["Decision"] = "Decision"
    selected_action: str = Field(min_length=1)
    why_selected: str = Field(min_length=1)
    why_not_selected: tuple[str, ...] = ()
    closure: ClosureState = ClosureState.OPEN
    expected_outcome: str = Field(min_length=1)
    reopen_triggers: tuple[ReopenTrigger, ...] = ()
    readiness: DecisionAssurance
    unknowns_assessed: bool
    authority_revision: int | None = Field(default=None, ge=1)


class ActionPayload(EntityPayloadModel):
    entity_type: Literal["Action"] = "Action"
    tool: str = Field(min_length=1)
    args_digest: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    risk_profile: RiskProfile
    idempotency_key: str = Field(min_length=1)
    execution_status: ActionExecutionStatus = ActionExecutionStatus.PLANNED
    receipt: str | None = Field(default=None, pattern=ID_PATTERN)
    guards: tuple[str, ...] = ()


class ObservationPayload(EntityPayloadModel):
    """원시 관측만 담는다. meaning/interpretation 필드는 의도적으로 존재하지 않는다."""

    entity_type: Literal["Observation"] = "Observation"
    raw_measurement_or_handle: str = Field(min_length=1)
    observed_at: UtcDatetime
    method: str = Field(min_length=1)
    source: str = Field(min_length=1)
    status: ObservationStatus


class OutcomePayload(EntityPayloadModel):
    entity_type: Literal["Outcome"] = "Outcome"
    expected: str = Field(min_length=1)
    observed: str | None
    delta: str | None
    status: OutcomeStatus


class ExperiencePayload(EntityPayloadModel):
    entity_type: Literal["Experience"] = "Experience"
    trigger: str = Field(min_length=1)
    historical_refs: tuple[str, ...] = ()
    remaining_unknowns: tuple[str, ...] = ()
    future_attention: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_references: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _require_missing_references_when_incomplete(self) -> ExperiencePayload:
        if same_enum(self.integrity, IntegrityStatus.INCOMPLETE) and not self.missing_references:
            raise CanonicalInvariantError("INCOMPLETE Experience는 missing_references를 기록해야 한다")
        if same_enum(self.integrity, IntegrityStatus.COMPLETE) and self.missing_references:
            raise CanonicalInvariantError("COMPLETE Experience에 missing_references가 있으면 안 된다")
        return self


class PatternPayload(EntityPayloadModel):
    entity_type: Literal["Pattern"] = "Pattern"
    statement: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    counterexamples: tuple[str, ...] = ()
    independence_count: int = Field(ge=0)


class HypothesisPayload(EntityPayloadModel):
    entity_type: Literal["Hypothesis"] = "Hypothesis"
    claim: str = Field(min_length=1)
    falsification_criteria: tuple[str, ...]
    evaluation_plan: str = Field(min_length=1)


class StrategyPayload(EntityPayloadModel):
    entity_type: Literal["Strategy"] = "Strategy"
    operational_rule: str = Field(min_length=1)
    applicability: ApplicabilityProfile
    exceptions: tuple[str, ...] = ()
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE


class PrinciplePayload(EntityPayloadModel):
    entity_type: Literal["Principle"] = "Principle"
    statement: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    confidence_profile: ConfidenceProfile
    applicability: ApplicabilityProfile
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE


class PolicyPayload(EntityPayloadModel):
    """allowlist된 운영 설정만 담는다. 임의 Python/shell 문자열은 들어갈 수 없다."""

    entity_type: Literal["Policy"] = "Policy"
    target: PolicyTarget
    rule: str = Field(min_length=1)
    parameters: dict[str, ScalarParameter] = Field(default_factory=dict)
    version: str = Field(min_length=1)
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE
    compatibility: str = ""
    rollback_version: str | None = None

    @model_validator(mode="after")
    def _enforce_parameter_allowlist(self) -> PolicyPayload:
        for key in self.parameters:
            if not key.islower() or not key.replace("_", "").isalnum():
                raise CanonicalInvariantError(f"policy parameter key가 allowlist 형식이 아니다: {key}")
        return self


class AuthorityProfilePayload(EntityPayloadModel):
    entity_type: Literal["AuthorityProfile"] = "AuthorityProfile"
    grants: tuple[AuthorityGrant, ...] = ()
    human_ceiling_ref: str | None = Field(default=None, pattern=ID_PATTERN)
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def _grants_must_not_expire_before_issue(self) -> AuthorityProfilePayload:
        for grant in self.grants:
            if grant.expires_at is not None and grant.expires_at < grant.issued_at:
                raise CanonicalInvariantError(f"authority grant 만료가 발급보다 앞선다: {grant.subject}")
        return self


class ConstitutionRulePayload(EntityPayloadModel):
    entity_type: Literal["ConstitutionRule"] = "ConstitutionRule"
    principle_number: int = Field(ge=1, le=24)
    verbatim_text: str = Field(min_length=1)
    source_digest: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ArchitectureDecisionPayload(EntityPayloadModel):
    entity_type: Literal["ArchitectureDecision"] = "ArchitectureDecision"
    context: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    alternatives: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    compatibility: str = ""
    validation: str = ""
    rollback: str = ""


class ContextPackagePayload(EntityPayloadModel):
    entity_type: Literal["ContextPackage"] = "ContextPackage"
    goal_id: str = Field(pattern=ID_PATTERN)
    state_revision: int = Field(ge=1)
    policy_version: str | None = None
    l0_constraints: tuple[ContextItem, ...] = ()
    l1_state: tuple[ContextItem, ...] = ()
    l2_history: tuple[ContextItem, ...] = ()
    l3_evidence: tuple[ContextItem, ...] = ()
    handles: tuple[ContextHandleRef, ...] = ()
    budget: ContextBudget
    exclusions: tuple[ContextExclusion, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_ids: tuple[str, ...] = ()
    projection: ProjectionState | None = None

    @model_validator(mode="after")
    def _require_missing_ids_when_incomplete(self) -> ContextPackagePayload:
        if same_enum(self.integrity, IntegrityStatus.INCOMPLETE) and not self.missing_ids:
            raise CanonicalInvariantError("INCOMPLETE ContextPackage는 missing_ids를 기록해야 한다")
        if same_enum(self.integrity, IntegrityStatus.COMPLETE) and self.missing_ids:
            raise CanonicalInvariantError("COMPLETE ContextPackage에 missing_ids가 있으면 안 된다")
        if self.budget.l0_reserved_tokens > self.budget.token_budget:
            raise CanonicalInvariantError("L0 예약 token이 전체 예산을 초과한다")
        return self


class InterpretationPayload(EntityPayloadModel):
    entity_type: Literal["Interpretation"] = "Interpretation"
    experience_id: str = Field(pattern=ID_PATTERN)
    revision: int = Field(ge=1)
    supersedes: str | None = Field(default=None, pattern=ID_PATTERN)
    evidence_ids: tuple[str, ...] = ()
    author: Producer
    meaning: str = Field(min_length=1)
    confidence_profile: ConfidenceProfile
    applicability_profile: ApplicabilityProfile


class ReassessmentPayload(EntityPayloadModel):
    entity_type: Literal["Reassessment"] = "Reassessment"
    target_record_id: str = Field(pattern=ID_PATTERN)
    trigger: ReopenTrigger
    changed_understanding: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    smallest_scope: str = Field(min_length=1)
    resolution: str = ""


class ValidationReportPayload(EntityPayloadModel):
    entity_type: Literal["ValidationReport"] = "ValidationReport"
    candidate_id: str = Field(pattern=ID_PATTERN)
    split_ids: tuple[str, ...]
    method: str = Field(min_length=1)
    metrics: tuple[MetricResult, ...] = ()
    passed: bool
    limitations: tuple[str, ...] = ()
    independent_episode_count: int = Field(ge=0)


class PolicyActivationPayload(EntityPayloadModel):
    entity_type: Literal["PolicyActivation"] = "PolicyActivation"
    policy_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1)
    expected_active_version: str | None = None
    validation_report_id: str = Field(pattern=ID_PATTERN)
    reason: str = Field(min_length=1)


class BehaviorChangeTracePayload(EntityPayloadModel):
    entity_type: Literal["BehaviorChangeTrace"] = "BehaviorChangeTrace"
    policy_version: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    shadow_selection: tuple[str, ...] = ()
    actual_selection: tuple[str, ...] = ()
    difference: str = ""
    outcome_ref: str | None = Field(default=None, pattern=ID_PATTERN)


class SelectionInfo(BaseModel):
    """선별 기록의 canonical 표현 — 계약 최소 필드를 Event에 실어 roundtrip 가능하게 한다.

    disposition·reason·evidence references·policy version은 선별 판단의 본체다. producer와
    recorded_at은 envelope(producer·created_at)이 소유하므로 여기 담지 않는다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: SelectionDisposition
    reasons: tuple[SelectionReason, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    policy_version: str | None = None
    note: str = ""


class EventPayload(EntityPayloadModel):
    entity_type: Literal["Event"] = "Event"
    sequence: int = Field(ge=0)
    episode_id: str = Field(min_length=1)
    state: LoopState
    caused_by: str | None = None
    state_revision: int = Field(ge=1)
    #: 선별 기록(공통 의미 계약). 선별이 아닌 Event는 None이다.
    selection: SelectionInfo | None = None


class ExecutionReceiptPayload(EntityPayloadModel):
    entity_type: Literal["ExecutionReceipt"] = "ExecutionReceipt"
    action_id: str = Field(pattern=ID_PATTERN)
    idempotency_key: str = Field(min_length=1)
    dispatch_attempt: int = Field(ge=1)
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
    external_ref: str | None = None
    status: ReceiptStatus
    effects_observed: bool | None = None
    reconciliation: str = ""


EntityPayload = Annotated[
    ProjectPayload
    | GoalPayload
    | EvidencePayload
    | BrainJudgmentPayload
    | AssumptionPayload
    | UnknownPayload
    | AlternativePayload
    | CognitiveRequestPayload
    | GovernanceDecisionPayload
    | DecisionPayload
    | ActionPayload
    | ObservationPayload
    | OutcomePayload
    | ExperiencePayload
    | PatternPayload
    | HypothesisPayload
    | StrategyPayload
    | PrinciplePayload
    | PolicyPayload
    | AuthorityProfilePayload
    | ConstitutionRulePayload
    | ArchitectureDecisionPayload
    | ContextPackagePayload
    | InterpretationPayload
    | ReassessmentPayload
    | ValidationReportPayload
    | PolicyActivationPayload
    | BehaviorChangeTracePayload
    | EventPayload
    | ExecutionReceiptPayload,
    Field(discriminator="entity_type"),
]

PAYLOAD_TYPES: Final[dict[EntityType, type[EntityPayloadModel]]] = {
    EntityType.PROJECT: ProjectPayload,
    EntityType.GOAL: GoalPayload,
    EntityType.EVIDENCE: EvidencePayload,
    EntityType.BRAIN_JUDGMENT: BrainJudgmentPayload,
    EntityType.ASSUMPTION: AssumptionPayload,
    EntityType.UNKNOWN: UnknownPayload,
    EntityType.ALTERNATIVE: AlternativePayload,
    EntityType.COGNITIVE_REQUEST: CognitiveRequestPayload,
    EntityType.GOVERNANCE_DECISION: GovernanceDecisionPayload,
    EntityType.DECISION: DecisionPayload,
    EntityType.ACTION: ActionPayload,
    EntityType.OBSERVATION: ObservationPayload,
    EntityType.OUTCOME: OutcomePayload,
    EntityType.EXPERIENCE: ExperiencePayload,
    EntityType.PATTERN: PatternPayload,
    EntityType.HYPOTHESIS: HypothesisPayload,
    EntityType.STRATEGY: StrategyPayload,
    EntityType.PRINCIPLE: PrinciplePayload,
    EntityType.POLICY: PolicyPayload,
    EntityType.AUTHORITY_PROFILE: AuthorityProfilePayload,
    EntityType.CONSTITUTION_RULE: ConstitutionRulePayload,
    EntityType.ARCHITECTURE_DECISION: ArchitectureDecisionPayload,
    EntityType.CONTEXT_PACKAGE: ContextPackagePayload,
    EntityType.INTERPRETATION: InterpretationPayload,
    EntityType.REASSESSMENT: ReassessmentPayload,
    EntityType.VALIDATION_REPORT: ValidationReportPayload,
    EntityType.POLICY_ACTIVATION: PolicyActivationPayload,
    EntityType.BEHAVIOR_CHANGE_TRACE: BehaviorChangeTracePayload,
    EntityType.EVENT: EventPayload,
    EntityType.EXECUTION_RECEIPT: ExecutionReceiptPayload,
}


def payload_type_for(entity_type: EntityType) -> type[EntityPayloadModel]:
    return PAYLOAD_TYPES[EntityType(entity_type)]


# ─── envelope ────────────────────────────────────────────────────────


class Record(BaseModel):
    """canonical record envelope. 생성 후에는 변경하지 않는다(append-only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(pattern=ID_PATTERN)
    entity_type: EntityType
    project_id: str = Field(pattern=ID_PATTERN)
    created_at: UtcDatetime
    producer: Producer
    references: tuple[Reference, ...] = ()
    payload: EntityPayload

    @model_validator(mode="after")
    def _check_invariants(self) -> Record:
        expected_namespace = namespace_for(self.entity_type)
        actual_namespace, _ = self.id.split(":", 1)
        if actual_namespace != expected_namespace:
            raise CanonicalInvariantError(f"id namespace mismatch: {self.id} is not a {expected_namespace} id")
        if self.project_id.split(":", 1)[0] != ENTITY_NAMESPACES[EntityType.PROJECT]:
            raise CanonicalInvariantError(f"project_id must be a project id: {self.project_id}")
        if same_enum(self.entity_type, EntityType.PROJECT) and self.project_id != self.id:
            raise CanonicalInvariantError("Project record의 project_id는 자기 ID여야 한다")
        if self.payload.entity_type != self.entity_type:
            raise CanonicalInvariantError(f"payload/entity mismatch: {self.payload.entity_type} != {self.entity_type}")
        _check_entity_invariants(self)
        return self

    @classmethod
    def create(
        cls,
        *,
        entity_type: EntityType,
        project_id: str,
        producer: Producer,
        payload: EntityPayload,
        references: tuple[Reference, ...] = (),
        record_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Record:
        """canonical ID와 UTC 시각을 발급해 record를 만든다. Project는 project_id가 자기 ID다."""

        resolved_id = record_id if record_id is not None else new_id(entity_type)
        resolved_project_id = (
            resolved_id if same_enum(entity_type, EntityType.PROJECT) and not project_id else project_id
        )
        return cls(
            id=resolved_id,
            entity_type=entity_type,
            project_id=resolved_project_id,
            created_at=created_at if created_at is not None else datetime.now(UTC),
            producer=producer,
            references=references,
            payload=payload,
        )


def _check_entity_invariants(record: Record) -> None:
    """envelope만으로 판정 가능한 entity 불변 조건. 저장소·resolver가 필요한 검사는 P02가 담당한다."""

    payload = record.payload
    if isinstance(payload, BrainJudgmentPayload):
        if not payload.grounds:
            raise CanonicalInvariantError("BrainJudgment ground 없이 justification만 있는 판단은 거부한다")
        ground_refs = {
            reference.target_id
            for reference in record.references
            if reference.relation == REL_GROUND and same_enum(reference.expected_type, EntityType.EVIDENCE)
        }
        unbacked = [ground for ground in payload.grounds if ground not in ground_refs]
        if unbacked:
            raise CanonicalInvariantError(f"BrainJudgment ground without Evidence reference: {unbacked}")
    elif isinstance(payload, ProjectPayload):
        rule_refs = {
            reference.target_id
            for reference in record.references
            if reference.relation == REL_CONSTITUTION_RULE
            and same_enum(reference.expected_type, EntityType.CONSTITUTION_RULE)
        }
        unbacked_rules = [rule for rule in payload.protected_constraints if rule not in rule_refs]
        if unbacked_rules:
            raise CanonicalInvariantError(f"protected constraint without ConstitutionRule reference: {unbacked_rules}")


def major_of(schema_version: str) -> str:
    return schema_version.split(".", 1)[0]


def from_wire(data: Mapping[str, object]) -> Record:
    """wire(dict) 입력을 record로 해석한다. 미지원 schema major는 격리한다."""

    raw_version = data.get("schema_version")
    if not isinstance(raw_version, str):
        raise UnsupportedSchemaError(f"schema_version is required, got {raw_version!r}")
    if major_of(raw_version) != SUPPORTED_SCHEMA_MAJOR:
        raise UnsupportedSchemaError(f"UNSUPPORTED_SCHEMA: {raw_version}")
    return Record.model_validate(dict(data))


def to_wire(record: Record) -> dict[str, object]:
    """JSON 직렬화 가능한 dict로 변환한다. payload/enum은 손실 없이 왕복한다."""

    return record.model_dump(mode="json")
