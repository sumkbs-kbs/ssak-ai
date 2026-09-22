"""학습 policy version lifecycle (P09).

계약(EXPERIENCE_AND_LEARNING.md §35 실행 가능한 보완 명세, ACCEPTANCE_CHECKLIST T10-D/E):

- **검증 우회 금지:** ``register``는 통과한 ``ValidationReport``가 없으면 거부한다. policy를 직접
  편집하는 경로 자체가 없다.
- **CAS promotion:** ``promote``는 ``expected_active_version``이 현재 active와 같을 때만 성공한다.
  동시 promotion은 직렬화되고, 지는 쪽은 ``PolicyCasConflict``로 남는다.
- **실행 중 episode pin:** episode는 시작 policy version을 pin한다. 새 promotion은 그 episode의 선택을
  바꾸지 않는다. 권한 취소만 즉시 반영되며 그때 pin 선택은 거부된다.
- **rollback/retire는 append 사건:** 과거 version·activation을 지우지 않는다. retired version도 조회된다.
- **성장 통과 조건:** activation 기록만으로는 성장이 아니다. policy 없이 같은 입력에 대한 shadow 선택과
  실제 선택이 다르고 outcome이 연결된 ``BehaviorChangeTrace``가 있어야 한다.
- **권한 불변:** learned policy는 protected authority·human ceiling을 바꾸지 못한다. ``PolicyTarget``
  allowlist 밖 target, 권한 확대 파라미터, protected target 문자열 참조는 등록 단계에서 거부된다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Final

from antigravity_k.engine.cognitive.learning import (
    MIN_INDEPENDENT_EPISODES,
    CandidateKind,
    LearningCandidate,
    ValidationReport,
)
from antigravity_k.engine.cognitive.models import (
    BehaviorChangeTracePayload,
    EventPayload,
    KnowledgeLifecycle,
    LoopState,
    PolicyActivationPayload,
    PolicyPayload,
    PolicyTarget,
    Producer,
    Record,
    ScalarParameter,
    same_enum,
)
from antigravity_k.engine.cognitive.protected_targets import ActorKind, ProtectedWriteGuard
from antigravity_k.engine.cognitive.references import REL_POLICY, REL_VALIDATION, EntityType, Reference, new_id

#: policy가 만들 수 없는 것들. 권한 확대는 사람 결정 경로다.
AUTHORITY_WIDENING_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "grant",
        "new_grant",
        "issue_grant",
        "ceiling",
        "human_ceiling",
        "max_autonomy",
        "autonomy_score",
        "constitution",
        "constitutional_authority",
    }
)

#: AUTHORITY_DELEGATION target에서 허용하는 파라미터 = 기존 grant 안의 선택·위임 조정.
DELEGATION_SELECTION_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"preferred_subject", "preferred_dimension", "selection_order", "fallback", "max_parallel"}
)


class ActivationKind(StrEnum):
    PROMOTION = "PROMOTION"
    ROLLBACK = "ROLLBACK"


class PolicyContractError(ValueError):
    """policy 계약 위반의 공통 상위 타입."""


class PromotionRefused(PolicyContractError):
    """검증되지 않은 version을 activate하려는 시도."""


class PolicyCasConflict(PolicyContractError):
    """expected_active_version이 현재 active와 다르다(동시 promotion)."""


class PolicyNotFoundError(PolicyContractError):
    """알 수 없는 policy/version."""


class RetiredVersionRefused(PolicyContractError):
    """retired version을 다시 활성화하려는 시도."""


class AuthorityWideningRefused(PolicyContractError):
    """learned policy가 protected authority/human ceiling을 바꾸려는 시도."""


class AuthorityRevokedError(PolicyContractError):
    """권한이 취소된 뒤 pin으로 선택을 요청했다."""


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyVersion:
    """검증을 통과한 policy version 한 건. active 적용은 별도 ActivationEvent다."""

    policy_id: str
    version: str
    record_id: str
    target: PolicyTarget
    rule: str
    parameters: Mapping[str, ScalarParameter]
    candidate_id: str
    validation_report_id: str
    producer: Producer
    created_at: datetime
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE
    compatibility: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "target": self.target.value,
            "rule": self.rule,
            "parameters": dict(self.parameters),
            "candidate_id": self.candidate_id,
            "validation_report_id": self.validation_report_id,
            "lifecycle": self.lifecycle.value,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    def to_record(self, *, project_id: str) -> Record:
        references: tuple[Reference, ...] = (
            Reference(
                relation=REL_VALIDATION,
                target_id=self.validation_report_id,
                expected_type=EntityType.VALIDATION_REPORT,
            ),
        )
        return Record.create(
            entity_type=EntityType.POLICY,
            project_id=project_id,
            producer=self.producer,
            payload=PolicyPayload(
                target=self.target,
                rule=self.rule,
                parameters=dict(self.parameters),
                version=self.version,
                lifecycle=self.lifecycle,
                compatibility=self.compatibility,
            ),
            references=references,
            record_id=self.record_id,
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class ActivationEvent:
    """promotion/rollback은 교체가 아니라 append 사건이다."""

    activation_id: str
    policy_id: str
    version: str
    kind: ActivationKind
    expected_active_version: str | None
    previous_version: str | None
    validation_report_id: str
    reason: str
    sequence: int
    actor: Producer
    occurred_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "activation_id": self.activation_id,
            "policy_id": self.policy_id,
            "version": self.version,
            "kind": self.kind.value,
            "expected_active_version": self.expected_active_version,
            "previous_version": self.previous_version,
            "validation_report_id": self.validation_report_id,
            "reason": self.reason,
            "sequence": self.sequence,
            "actor": {"kind": self.actor.kind.value, "actor_id": self.actor.actor_id},
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    def to_record(self, *, project_id: str) -> Record:
        references: tuple[Reference, ...] = (
            Reference(
                relation=REL_VALIDATION,
                target_id=self.validation_report_id,
                expected_type=EntityType.VALIDATION_REPORT,
            ),
        )
        return Record.create(
            entity_type=EntityType.POLICY_ACTIVATION,
            project_id=project_id,
            producer=self.actor,
            payload=PolicyActivationPayload(
                policy_id=self.policy_id,
                version=self.version,
                expected_active_version=self.expected_active_version,
                validation_report_id=self.validation_report_id,
                reason=f"{self.kind.value}: {self.reason}",
            ),
            references=references,
            record_id=self.activation_id,
            created_at=self.occurred_at,
        )


@dataclass(frozen=True, slots=True)
class RetirementEvent:
    """retirement도 삭제가 아니라 LEARN 단계의 append 사건이다."""

    retirement_id: str
    policy_id: str
    version: str
    reason: str
    sequence: int
    actor: Producer
    occurred_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "retirement_id": self.retirement_id,
            "policy_id": self.policy_id,
            "version": self.version,
            "reason": self.reason,
            "sequence": self.sequence,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    def to_record(self, *, project_id: str) -> Record:
        return Record.create(
            entity_type=EntityType.EVENT,
            project_id=project_id,
            producer=self.actor,
            payload=EventPayload(
                sequence=self.sequence,
                episode_id=f"policy-retirement:{self.policy_id}:{self.version}",
                state=LoopState.LEARN,
                caused_by=self.reason,
                state_revision=self.sequence,
            ),
            record_id=self.retirement_id,
            created_at=self.occurred_at,
        )


@dataclass(frozen=True, slots=True)
class BehaviorChangeTrace:
    """policy 없이 같은 입력에 대한 shadow 선택과 실제 선택의 차이."""

    trace_id: str
    policy_id: str
    policy_version: str
    task_id: str
    shadow_selection: tuple[str, ...]
    actual_selection: tuple[str, ...]
    recorded_at: datetime
    producer: Producer
    outcome_ref: str | None = None
    difference: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "trace_id": self.trace_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "task_id": self.task_id,
            "shadow_selection": list(self.shadow_selection),
            "actual_selection": list(self.actual_selection),
            "difference": self.difference,
            "outcome_ref": self.outcome_ref,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    @property
    def changed(self) -> bool:
        return self.shadow_selection != self.actual_selection

    def to_record(self, *, project_id: str, policy_record_id: str) -> Record:
        return Record.create(
            entity_type=EntityType.BEHAVIOR_CHANGE_TRACE,
            project_id=project_id,
            producer=self.producer,
            payload=BehaviorChangeTracePayload(
                policy_version=self.policy_version,
                task_id=self.task_id,
                shadow_selection=self.shadow_selection,
                actual_selection=self.actual_selection,
                difference=self.difference,
                outcome_ref=self.outcome_ref,
            ),
            references=(Reference(relation=REL_POLICY, target_id=policy_record_id, expected_type=EntityType.POLICY),),
            record_id=self.trace_id,
            created_at=self.recorded_at,
        )


@dataclass(frozen=True, slots=True)
class GrowthEvidence:
    """성장 통과 근거. 선택 변화와 outcome 연결이 모두 있어야 만들어진다."""

    policy_id: str
    policy_version: str
    changed_tasks: tuple[str, ...]
    outcome_refs: tuple[str, ...]
    trace_ids: tuple[str, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "changed_tasks": list(self.changed_tasks),
            "outcome_refs": list(self.outcome_refs),
            "trace_ids": list(self.trace_ids),
        }


@dataclass(frozen=True, slots=True)
class PolicyPin:
    """실행 중 episode가 잡은 policy version. promotion은 이 pin을 바꾸지 않는다."""

    episode_id: str
    policy_id: str
    policy_version: str
    pinned_at: datetime
    authority_revision: int | None = None
    revoked_at: datetime | None = None
    revoked_reason: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "episode_id": self.episode_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "authority_revision": self.authority_revision,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


def _selection_difference(shadow: Sequence[str], actual: Sequence[str]) -> str:
    """shadow/실제 선택의 기계 diff. 의미 해석을 하지 않는다."""

    added = [item for item in actual if item not in shadow]
    removed = [item for item in shadow if item not in actual]
    parts = []
    if added:
        parts.append("only_with_policy: " + ", ".join(added))
    if removed:
        parts.append("dropped_by_policy: " + ", ".join(removed))
    return "; ".join(parts)


class PolicyStore:
    """policy version registry와 activation ledger. active 적용은 반드시 CAS를 통한다."""

    def __init__(self, *, guard: ProtectedWriteGuard | None = None) -> None:
        self._guard = guard
        self._project_id = ""
        self._versions: dict[tuple[str, str], PolicyVersion] = {}
        self._active: dict[str, str] = {}
        self._activations: dict[str, list[ActivationEvent]] = {}
        self._retirements: dict[str, list[RetirementEvent]] = {}
        self._traces: dict[str, list[BehaviorChangeTrace]] = {}
        self._pins: dict[str, PolicyPin] = {}
        self._sequence = 0
        self._records: list[Record] = []

    # ── 조회 ────────────────────────────────────────────
    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    def versions(self, policy_id: str) -> tuple[PolicyVersion, ...]:
        return tuple(version for (owner, _), version in self._versions.items() if owner == policy_id)

    def version(self, policy_id: str, version: str) -> PolicyVersion:
        found = self._versions.get((policy_id, version))
        if found is None:
            raise PolicyNotFoundError(f"unknown policy version: {policy_id}@{version}")
        return found

    def active_version(self, policy_id: str) -> str | None:
        return self._active.get(policy_id)

    def active_policy(self, target: PolicyTarget) -> PolicyVersion | None:
        """해당 운영 target에 대해 가장 마지막에 활성화된 version. 없으면 None."""

        candidates = [
            version
            for version in self._versions.values()
            if version.target is target and self._active.get(version.policy_id) == version.version
        ]
        return candidates[-1] if candidates else None

    def activations(self, policy_id: str) -> tuple[ActivationEvent, ...]:
        return tuple(self._activations.get(policy_id, ()))

    def retirements(self, policy_id: str) -> tuple[RetirementEvent, ...]:
        return tuple(self._retirements.get(policy_id, ()))

    def traces(self, policy_id: str) -> tuple[BehaviorChangeTrace, ...]:
        return tuple(self._traces.get(policy_id, ()))

    def pins(self) -> tuple[PolicyPin, ...]:
        return tuple(self._pins.values())

    def pin_of(self, episode_id: str) -> PolicyPin | None:
        return self._pins.get(episode_id)

    # ── 등록 ────────────────────────────────────────────
    def register(
        self,
        candidate: LearningCandidate,
        report: ValidationReport,
        *,
        version: str,
        producer: Producer,
        created_at: datetime,
        policy_id: str | None = None,
        compatibility: str = "",
    ) -> PolicyVersion:
        """검증 통과 + allowlist + 권한 불변 검사를 지난 version만 등록한다."""

        if not same_enum(candidate.kind, CandidateKind.POLICY):
            raise PolicyContractError("POLICY 후보만 policy version이 될 수 있다")
        if candidate.target is None:
            raise PolicyContractError("policy version에는 PolicyTarget이 필요하다")
        if report.candidate_id != candidate.candidate_id:
            raise PromotionRefused("validation report가 다른 candidate에 대한 것이다")
        if not report.passed:
            raise PromotionRefused("validation을 통과하지 않은 candidate는 등록되지 않는다")
        if report.independent_episode_count < MIN_INDEPENDENT_EPISODES:
            raise PromotionRefused("독립 episode 2건 미만의 report로는 등록되지 않는다")
        self._assert_authority_unchanged(candidate)

        resolved_policy_id = policy_id if policy_id is not None else candidate.candidate_id
        if policy_id is not None and not any(owner == policy_id for owner, _ in self._versions):
            raise PolicyNotFoundError(f"unknown policy: {policy_id}")
        if (resolved_policy_id, version) in self._versions:
            raise PolicyContractError(f"duplicate policy version: {resolved_policy_id}@{version}")

        if not self._project_id:
            self._project_id = candidate.project_id
        policy_version = PolicyVersion(
            policy_id=resolved_policy_id,
            version=version,
            record_id=new_id(EntityType.POLICY),
            target=candidate.target,
            rule=candidate.rule,
            parameters=dict(candidate.parameters),
            candidate_id=candidate.candidate_id,
            validation_report_id=report.report_id,
            producer=producer,
            created_at=created_at,
            lifecycle=KnowledgeLifecycle.CANDIDATE,
            compatibility=compatibility or candidate.scope,
        )
        self._versions[(resolved_policy_id, version)] = policy_version
        self._records.append(policy_version.to_record(project_id=self._project_id))
        return policy_version

    def _assert_authority_unchanged(self, candidate: LearningCandidate) -> None:
        """target allowlist·파라미터·protected 참조를 등록 단계에서 차단한다."""

        assert candidate.target is not None
        rejected = sorted(key for key in candidate.parameters if key.lower() in AUTHORITY_WIDENING_PARAMETERS)
        if rejected:
            raise AuthorityWideningRefused(f"learned policy는 authority/ceiling을 바꿀 수 없다: {rejected}")
        if same_enum(candidate.target, PolicyTarget.AUTHORITY_DELEGATION):
            outside = sorted(key for key in candidate.parameters if key not in DELEGATION_SELECTION_PARAMETERS)
            if outside:
                raise AuthorityWideningRefused(
                    f"AUTHORITY_DELEGATION policy는 기존 grant 안의 선택·위임 조정만 한다: {outside}"
                )
        if self._guard is None:
            return
        decision = self._guard.evaluate_policy_target(
            candidate.target.value,
            rule=candidate.rule,
            parameters=dict(candidate.parameters),
            actor_kind=ActorKind.LEARNED_POLICY,
        )
        if not decision.allowed:
            raise AuthorityWideningRefused(f"{decision.code.value}: {decision.detail}")

    # ── activation ──────────────────────────────────────
    def promote(
        self,
        policy_id: str,
        *,
        version: str,
        expected_active_version: str | None,
        actor: Producer,
        reason: str,
        occurred_at: datetime,
    ) -> ActivationEvent:
        """CAS로만 활성화한다. 동시 promotion은 한 건만 성공한다."""

        policy_version = self.version(policy_id, version)
        if same_enum(policy_version.lifecycle, KnowledgeLifecycle.RETIRED):
            raise RetiredVersionRefused(f"retired version은 다시 활성화하지 않는다: {policy_id}@{version}")
        return self._activate(
            policy_version,
            kind=ActivationKind.PROMOTION,
            expected_active_version=expected_active_version,
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
        )

    def rollback(
        self,
        policy_id: str,
        *,
        to_version: str,
        reason: str,
        expected_active_version: str | None,
        actor: Producer,
        occurred_at: datetime,
    ) -> ActivationEvent:
        """이전 activation을 새 event로 지정한다. 과거 기록은 남는다."""

        policy_version = self.version(policy_id, to_version)
        if same_enum(policy_version.lifecycle, KnowledgeLifecycle.RETIRED):
            raise RetiredVersionRefused(f"retired version으로 rollback하지 않는다: {policy_id}@{to_version}")
        return self._activate(
            policy_version,
            kind=ActivationKind.ROLLBACK,
            expected_active_version=expected_active_version,
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
        )

    def _activate(
        self,
        policy_version: PolicyVersion,
        *,
        kind: ActivationKind,
        expected_active_version: str | None,
        actor: Producer,
        reason: str,
        occurred_at: datetime,
    ) -> ActivationEvent:
        policy_id = policy_version.policy_id
        current = self._active.get(policy_id)
        if current != expected_active_version:
            raise PolicyCasConflict(
                f"active version이 다르다: current={current!r}, expected={expected_active_version!r}"
            )
        self._sequence += 1
        event = ActivationEvent(
            activation_id=new_id(EntityType.POLICY_ACTIVATION),
            policy_id=policy_id,
            version=policy_version.version,
            kind=kind,
            expected_active_version=expected_active_version,
            previous_version=current,
            validation_report_id=policy_version.validation_report_id,
            reason=reason,
            sequence=self._sequence,
            actor=actor,
            occurred_at=occurred_at,
        )
        self._activations.setdefault(policy_id, []).append(event)
        self._active[policy_id] = policy_version.version
        self._records.append(event.to_record(project_id=self._project_id))
        return event

    def retire(
        self,
        policy_id: str,
        *,
        version: str,
        reason: str,
        actor: Producer,
        occurred_at: datetime,
    ) -> RetirementEvent:
        """retire는 삭제가 아니다. active라면 이전 version으로 되돌리는 event를 함께 남긴다."""

        policy_version = self.version(policy_id, version)
        if same_enum(policy_version.lifecycle, KnowledgeLifecycle.RETIRED):
            raise PolicyContractError(f"이미 retired version이다: {policy_id}@{version}")
        self._versions[(policy_id, version)] = replace(policy_version, lifecycle=KnowledgeLifecycle.RETIRED)
        self._sequence += 1
        event = RetirementEvent(
            retirement_id=new_id(EntityType.EVENT),
            policy_id=policy_id,
            version=version,
            reason=reason,
            sequence=self._sequence,
            actor=actor,
            occurred_at=occurred_at,
        )
        self._retirements.setdefault(policy_id, []).append(event)
        self._records.append(event.to_record(project_id=self._project_id))
        if self._active.get(policy_id) == version:
            fallback = self._previous_activatable(policy_id, exclude=version)
            if fallback is None:
                self._active.pop(policy_id, None)
            else:
                self._activate(
                    self.version(policy_id, fallback),
                    kind=ActivationKind.ROLLBACK,
                    expected_active_version=version,
                    actor=actor,
                    reason=f"RETIRE {version}: {reason}",
                    occurred_at=occurred_at,
                )
        return event

    def _previous_activatable(self, policy_id: str, *, exclude: str) -> str | None:
        for candidate in reversed([event.version for event in self._activations.get(policy_id, ())]):
            if candidate == exclude:
                continue
            if (policy_id, candidate) in self._versions and (
                not same_enum(self._versions[(policy_id, candidate)].lifecycle, KnowledgeLifecycle.RETIRED)
            ):
                return candidate
        return None

    # ── 실행 중 pin ─────────────────────────────────────
    def pin(
        self,
        episode_id: str,
        policy_id: str,
        *,
        pinned_at: datetime,
        authority_revision: int | None = None,
    ) -> PolicyPin:
        """episode는 시작 시점의 active version을 잡는다."""

        active = self._active.get(policy_id)
        if active is None:
            raise PolicyNotFoundError(f"active version이 없는 policy는 pin하지 않는다: {policy_id}")
        found = PolicyPin(
            episode_id=episode_id,
            policy_id=policy_id,
            policy_version=active,
            pinned_at=pinned_at,
            authority_revision=authority_revision,
        )
        self._pins[episode_id] = found
        return found

    def resolve(self, pin: PolicyPin) -> PolicyVersion:
        """pin된 version으로 선택한다. 권한 취소는 즉시 반영된다."""

        if pin.revoked_at is not None:
            raise AuthorityRevokedError(f"권한이 취소된 episode다: {pin.episode_id} ({pin.revoked_reason})")
        return self.version(pin.policy_id, pin.policy_version)

    def revoke_authority(self, *, reason: str, revoked_at: datetime) -> tuple[PolicyPin, ...]:
        """권한 취소는 pin·promotion보다 우선한다. 새 결과를 지어내지 않고 거부만 한다."""

        revoked: list[PolicyPin] = []
        for episode_id, found in list(self._pins.items()):
            if found.revoked_at is not None:
                continue
            updated = replace(found, revoked_at=revoked_at, revoked_reason=reason)
            self._pins[episode_id] = updated
            revoked.append(updated)
        return tuple(revoked)

    # ── 실제 행동 변화 ─────────────────────────────────
    def record_behavior_change(
        self,
        *,
        policy_id: str,
        version: str,
        task_id: str,
        shadow_selection: Sequence[str],
        actual_selection: Sequence[str],
        producer: Producer,
        recorded_at: datetime,
        outcome_ref: str | None = None,
        difference: str = "",
    ) -> BehaviorChangeTrace:
        """다음 task에서 실제 선택이 어떻게 달라졌는지 남긴다."""

        policy_version = self.version(policy_id, version)
        trace = BehaviorChangeTrace(
            trace_id=new_id(EntityType.BEHAVIOR_CHANGE_TRACE),
            policy_id=policy_id,
            policy_version=version,
            task_id=task_id,
            shadow_selection=tuple(shadow_selection),
            actual_selection=tuple(actual_selection),
            recorded_at=recorded_at,
            producer=producer,
            outcome_ref=outcome_ref,
            difference=difference or _selection_difference(shadow_selection, actual_selection),
        )
        self._traces.setdefault(policy_id, []).append(trace)
        self._records.append(trace.to_record(project_id=self._project_id, policy_record_id=policy_version.record_id))
        return trace

    def growth_evidence(self, policy_id: str, *, minimum_changed_tasks: int = 1) -> GrowthEvidence | None:
        """기록 생성만으로는 성장이 아니다. 선택 변화 + outcome 연결이 있어야 한다."""

        eligible = [
            trace for trace in self._traces.get(policy_id, ()) if trace.changed and trace.outcome_ref is not None
        ]
        if len(eligible) < minimum_changed_tasks:
            return None
        return GrowthEvidence(
            policy_id=policy_id,
            policy_version=eligible[-1].policy_version,
            changed_tasks=tuple(trace.task_id for trace in eligible),
            outcome_refs=tuple(trace.outcome_ref for trace in eligible if trace.outcome_ref is not None),
            trace_ids=tuple(trace.trace_id for trace in eligible),
        )


__all__ = [
    "AUTHORITY_WIDENING_PARAMETERS",
    "DELEGATION_SELECTION_PARAMETERS",
    "ActivationEvent",
    "ActivationKind",
    "AuthorityRevokedError",
    "AuthorityWideningRefused",
    "BehaviorChangeTrace",
    "GrowthEvidence",
    "PolicyCasConflict",
    "PolicyContractError",
    "PolicyNotFoundError",
    "PolicyPin",
    "PolicyStore",
    "PolicyVersion",
    "PromotionRefused",
    "RetiredVersionRefused",
    "RetirementEvent",
]
