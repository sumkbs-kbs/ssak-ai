"""Canonical ID와 typed reference 계약 (P01).

정본 cognitive record의 ID·namespace·reference 규칙만 소유한다.
이 모듈은 provider, UI, 저장소 구현을 import하지 않는다 — 계약만 정의한다.

규칙 요약:
- ID는 ``<namespace>:<uuid4>`` 형식이며 namespace는 entity type에 고정 매핑된다.
- reference는 target 존재, expected_type, project 범위, revision을 검증 대상으로 가진다.
- supersedes chain의 순환은 거부한다.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_ID_RE: Final[re.Pattern[str]] = re.compile(ID_PATTERN)


class EntityType(StrEnum):
    """canonical record의 entity 종류. envelope JSON Schema의 enum과 일치한다."""

    PROJECT = "Project"
    GOAL = "Goal"
    EVIDENCE = "Evidence"
    BRAIN_JUDGMENT = "BrainJudgment"
    ASSUMPTION = "Assumption"
    UNKNOWN = "Unknown"
    ALTERNATIVE = "Alternative"
    COGNITIVE_REQUEST = "CognitiveRequest"
    GOVERNANCE_DECISION = "GovernanceDecision"
    DECISION = "Decision"
    ACTION = "Action"
    OBSERVATION = "Observation"
    OUTCOME = "Outcome"
    EXPERIENCE = "Experience"
    PATTERN = "Pattern"
    HYPOTHESIS = "Hypothesis"
    STRATEGY = "Strategy"
    PRINCIPLE = "Principle"
    POLICY = "Policy"
    AUTHORITY_PROFILE = "AuthorityProfile"
    CONSTITUTION_RULE = "ConstitutionRule"
    ARCHITECTURE_DECISION = "ArchitectureDecision"
    CONTEXT_PACKAGE = "ContextPackage"
    INTERPRETATION = "Interpretation"
    REASSESSMENT = "Reassessment"
    VALIDATION_REPORT = "ValidationReport"
    POLICY_ACTIVATION = "PolicyActivation"
    BEHAVIOR_CHANGE_TRACE = "BehaviorChangeTrace"
    EVENT = "Event"
    EXECUTION_RECEIPT = "ExecutionReceipt"


#: 원문 entity 22종(P01 카드)과 보완 entity는 같은 union 안에서 관리한다.
CORE_ENTITY_TYPES: Final[tuple[EntityType, ...]] = (
    EntityType.PROJECT,
    EntityType.GOAL,
    EntityType.EVIDENCE,
    EntityType.BRAIN_JUDGMENT,
    EntityType.ASSUMPTION,
    EntityType.UNKNOWN,
    EntityType.ALTERNATIVE,
    EntityType.COGNITIVE_REQUEST,
    EntityType.GOVERNANCE_DECISION,
    EntityType.DECISION,
    EntityType.ACTION,
    EntityType.OBSERVATION,
    EntityType.OUTCOME,
    EntityType.EXPERIENCE,
    EntityType.PATTERN,
    EntityType.HYPOTHESIS,
    EntityType.STRATEGY,
    EntityType.PRINCIPLE,
    EntityType.POLICY,
    EntityType.AUTHORITY_PROFILE,
    EntityType.CONSTITUTION_RULE,
    EntityType.ARCHITECTURE_DECISION,
)

SUPPLEMENTAL_ENTITY_TYPES: Final[tuple[EntityType, ...]] = (
    EntityType.CONTEXT_PACKAGE,
    EntityType.INTERPRETATION,
    EntityType.REASSESSMENT,
    EntityType.VALIDATION_REPORT,
    EntityType.POLICY_ACTIVATION,
    EntityType.BEHAVIOR_CHANGE_TRACE,
    EntityType.EVENT,
    EntityType.EXECUTION_RECEIPT,
)

#: namespace는 ID의 안정적인 접두사다. entity type마다 하나만 허용한다.
ENTITY_NAMESPACES: Final[Mapping[EntityType, str]] = {
    EntityType.PROJECT: "project",
    EntityType.GOAL: "goal",
    EntityType.EVIDENCE: "evidence",
    EntityType.BRAIN_JUDGMENT: "brain_judgment",
    EntityType.ASSUMPTION: "assumption",
    EntityType.UNKNOWN: "unknown",
    EntityType.ALTERNATIVE: "alternative",
    EntityType.COGNITIVE_REQUEST: "cognitive_request",
    EntityType.GOVERNANCE_DECISION: "governance_decision",
    EntityType.DECISION: "decision",
    EntityType.ACTION: "action",
    EntityType.OBSERVATION: "observation",
    EntityType.OUTCOME: "outcome",
    EntityType.EXPERIENCE: "experience",
    EntityType.PATTERN: "pattern",
    EntityType.HYPOTHESIS: "hypothesis",
    EntityType.STRATEGY: "strategy",
    EntityType.PRINCIPLE: "principle",
    EntityType.POLICY: "policy",
    EntityType.AUTHORITY_PROFILE: "authority_profile",
    EntityType.CONSTITUTION_RULE: "constitution_rule",
    EntityType.ARCHITECTURE_DECISION: "architecture_decision",
    EntityType.CONTEXT_PACKAGE: "context_package",
    EntityType.INTERPRETATION: "interpretation",
    EntityType.REASSESSMENT: "reassessment",
    EntityType.VALIDATION_REPORT: "validation_report",
    EntityType.POLICY_ACTIVATION: "policy_activation",
    EntityType.BEHAVIOR_CHANGE_TRACE: "behavior_change_trace",
    EntityType.EVENT: "event",
    EntityType.EXECUTION_RECEIPT: "execution_receipt",
}

#: 널리 쓰는 relation 이름. reference.relation은 문자열이지만 이 상수를 우선 사용한다.
REL_GOAL: Final[str] = "goal"
REL_PARENT: Final[str] = "parent"
REL_GROUND: Final[str] = "ground"
REL_EVIDENCE: Final[str] = "evidence"
REL_HUMAN_INPUT: Final[str] = "human_input"
REL_CONSTITUTION_RULE: Final[str] = "constitution_rule"
REL_JUDGMENT: Final[str] = "judgment"
REL_REQUEST: Final[str] = "request"
REL_GOVERNANCE: Final[str] = "governance"
REL_DECISION: Final[str] = "decision"
REL_ACTION: Final[str] = "action"
REL_OBSERVATION: Final[str] = "observation"
REL_OUTCOME: Final[str] = "outcome"
REL_EXPERIENCE: Final[str] = "experience"
REL_INTERPRETATION: Final[str] = "interpretation"
REL_REASSESSMENT: Final[str] = "reassessment"
REL_PATTERN: Final[str] = "pattern"
REL_HYPOTHESIS: Final[str] = "hypothesis"
REL_CANDIDATE: Final[str] = "candidate"
REL_VALIDATION: Final[str] = "validation"
REL_POLICY: Final[str] = "policy"
REL_RECEIPT: Final[str] = "receipt"
REL_SUPERSEDES: Final[str] = "supersedes"
REL_SHARED_SCOPE: Final[str] = "shared_scope"
REL_ORIGIN: Final[str] = "origin"
REL_PROJECT: Final[str] = "project"

#: 다른 project의 record를 참조할 수 있는 명시적 shared scope relation만 허용한다.
SHARED_SCOPE_RELATIONS: Final[frozenset[str]] = frozenset({REL_SHARED_SCOPE})


class CanonicalIdError(ValueError):
    """canonical ID 형식 또는 namespace가 계약과 다를 때 발생한다."""


class ReferenceValidationError(ValueError):
    """typed reference 정합성이 깨졌을 때 발생한다. reason은 기계 판독 가능한 분류다."""

    def __init__(self, reason: str, target_id: str, detail: str = "") -> None:
        self.reason = reason
        self.target_id = target_id
        self.detail = detail
        message = f"{reason}: {target_id}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


def namespace_for(entity_type: EntityType | str) -> str:
    """entity type에 고정된 ID namespace를 반환한다."""

    try:
        resolved = EntityType(entity_type)
    except ValueError as exc:
        raise CanonicalIdError(f"unknown entity_type: {entity_type}") from exc
    return ENTITY_NAMESPACES[resolved]


def new_id(entity_type: EntityType | str) -> str:
    """해당 entity type의 canonical ID를 새로 발급한다."""

    return f"{namespace_for(entity_type)}:{uuid.uuid4()}"


def is_canonical_id(value: str) -> bool:
    """형식만 검사한다. namespace가 entity type과 맞는지는 record 생성 시 확인한다."""

    return bool(_ID_RE.match(value))


def split_id(target_id: str) -> tuple[str, str]:
    """canonical ID를 (namespace, uuid)로 분해한다. 형식 오류는 거부한다."""

    match = _ID_RE.match(target_id)
    if match is None:
        raise CanonicalIdError(f"not a canonical id: {target_id!r}")
    namespace, _, raw_uuid = match.group(0).partition(":")
    return namespace, raw_uuid


def entity_type_for_id(target_id: str) -> EntityType:
    """ID namespace로 entity type을 역추적한다. 미정의 namespace는 거부한다."""

    namespace, _ = split_id(target_id)
    for entity_type, candidate in ENTITY_NAMESPACES.items():
        if candidate == namespace:
            return entity_type
    raise CanonicalIdError(f"unknown id namespace: {namespace!r}")


class Reference(BaseModel):
    """typed reference. target 존재·타입·project 범위는 resolver가 확인한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation: str = Field(min_length=1)
    target_id: str = Field(pattern=ID_PATTERN)
    expected_type: EntityType
    target_revision: int | None = Field(default=None, ge=1)


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """resolver가 돌려주는 최소 정보. 존재하지 않으면 None을 반환한다."""

    entity_type: EntityType
    project_id: str
    revision: int | None = None


@runtime_checkable
class ReferenceResolver(Protocol):
    """record ID를 실제 존재 여부로 해석한다. store(P02)가 구현한다."""

    def resolve(self, target_id: str) -> ResolvedTarget | None: ...


@runtime_checkable
class ReferenceHolder(Protocol):
    """envelope 중 참조 검증에 필요한 필드만 요구한다."""

    @property
    def id(self) -> str: ...

    @property
    def project_id(self) -> str: ...

    @property
    def references(self) -> Sequence[Reference]: ...


def validate_references(
    record: ReferenceHolder,
    resolver: ReferenceResolver,
    *,
    shared_scope_relations: frozenset[str] = SHARED_SCOPE_RELATIONS,
) -> None:
    """쓰기 시점 참조 정합성 검사.

    거부 사유: SELF_REFERENCE, UNRESOLVED, TYPE_MISMATCH, CROSS_PROJECT, REVISION_MISMATCH.
    """

    for reference in record.references:
        if reference.target_id == record.id:
            raise ReferenceValidationError("SELF_REFERENCE", reference.target_id, reference.relation)
        resolved = resolver.resolve(reference.target_id)
        if resolved is None:
            raise ReferenceValidationError("UNRESOLVED", reference.target_id, reference.relation)
        if resolved.entity_type != reference.expected_type:
            raise ReferenceValidationError(
                "TYPE_MISMATCH",
                reference.target_id,
                f"expected {reference.expected_type}, resolved {resolved.entity_type}",
            )
        if resolved.project_id != record.project_id and reference.relation not in shared_scope_relations:
            raise ReferenceValidationError(
                "CROSS_PROJECT",
                reference.target_id,
                f"project {resolved.project_id} referenced from {record.project_id}",
            )
        if (
            reference.target_revision is not None
            and resolved.revision is not None
            and reference.target_revision != resolved.revision
        ):
            raise ReferenceValidationError(
                "REVISION_MISMATCH",
                reference.target_id,
                f"expected revision {reference.target_revision}, resolved {resolved.revision}",
            )


def assert_no_supersedes_cycle(
    record_id: str,
    load_references: Callable[[str], Sequence[Reference]],
) -> None:
    """supersedes chain을 따라가며 순환을 거부한다. 사슬 자체는 DAG일 필요가 없다."""

    seen: set[str] = {record_id}
    frontier: list[str] = [record_id]
    while frontier:
        current = frontier.pop()
        for reference in load_references(current):
            if reference.relation != REL_SUPERSEDES:
                continue
            if reference.target_id in seen:
                raise ReferenceValidationError(
                    "SUPERSEDES_CYCLE",
                    reference.target_id,
                    f"cycle reached from {record_id}",
                )
            seen.add(reference.target_id)
            frontier.append(reference.target_id)
