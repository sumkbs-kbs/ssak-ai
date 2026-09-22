"""Readiness gate (P06) — COMMIT은 readiness만 검사한다.

원문 §16 계약과 DECISION_AND_COMMIT.md의 실행 가능한 보완 명세를 구현한다.

- 검사 항목은 9개뿐이다: ground, evidence provenance, material unknown, hard constraints,
  residual risk, authority, verification, rollback, action scope.
- 결과는 ``READY / READY_WITH_GUARDS / NOT_READY``이며 **semantic rejection이 아니다**.
  NOT_READY는 blocking condition을 반환한다.
- 각 check는 ``PASS/FAIL/UNKNOWN/N_A``와 근거 reference를 가진다. N_A에도 이유가 필요하다.
- **모델 호출·지식 검색 확장·의미 재판정·외부 쓰기를 하지 않는다.** 의미적 불확실성은
  ``UNKNOWN``으로 표시해 Primary로 돌려보낸다(``needs_primary_judgment``).
- guard는 executor가 실제 강제한 receipt여야 한다. 문자열로만 존재하는 rollback은 충족이 아니다.
- ReadinessResult는 ``(decision_revision, action_digest, authority_revision, state_revision,
  policy_version)``에 귀속되며 ACTION 직전에 freshness를 다시 확인한다.

이 모듈은 provider/UI/저장소를 import하지 않는다. governance.RiskProfile·authority.AuthorityDecision
처럼 이미 판정이 끝난 값만 입력으로 받는다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.governance import ReshapeGuard
from antigravity_k.engine.cognitive.models import (
    CheckStatus,
    DecisionAssurance,
    ReadinessCheck,
    ReadinessCheckResult,
    ReadinessVerdict,
    RiskLevel,
    RiskProfile,
    UnknownMateriality,
    same_enum,
)

#: 높은 위험으로 취급하는 level. 단일 점수로 합성하지 않는다.
ELEVATED_RISKS: Final[frozenset[RiskLevel]] = frozenset({RiskLevel.HIGH, RiskLevel.SEVERE})

#: 실제로 집행 가능한 rollback mechanism. 문자열 약속은 여기에 없다.
EXECUTABLE_ROLLBACK_MECHANISMS: Final[frozenset[str]] = frozenset(
    {"CHECKPOINT", "SNAPSHOT", "GIT", "STORE_TRANSACTION"}
)

#: guard가 낮춰 주는 risk dimension.
GUARD_RISK_COVERAGE: Final[Mapping[ReshapeGuard, frozenset[str]]] = {
    ReshapeGuard.ISOLATED_SCOPE: frozenset({"blast_radius", "security_privacy"}),
    ReshapeGuard.NARROWED_SCOPE: frozenset({"blast_radius", "security_privacy", "external_impact"}),
    ReshapeGuard.CHECKPOINT: frozenset({"data_state_loss", "reversibility", "rollback"}),
    ReshapeGuard.DRY_RUN: frozenset({"data_state_loss"}),
    ReshapeGuard.DIFF_INSPECTION: frozenset({"verification", "goal_premise_impact"}),
    ReshapeGuard.VERIFICATION: frozenset({"verification"}),
    ReshapeGuard.BUDGET_LIMIT: frozenset({"cost"}),
    ReshapeGuard.READ_ONLY: frozenset({"authority_sensitivity"}),
}


class ReadinessError(ValueError):
    """readiness 계약 위반."""


class StaleReadinessError(ReadinessError):
    """ACTION 직전 freshness 확인에서 귀속 정보가 달라졌다."""


@runtime_checkable
class SemanticJudge(Protocol):
    """의미 판단 hook.

    **readiness gate는 이 hook을 호출하지 않는다.** 호출이 필요한 상황(의미적 불확실성)은
    ``UNKNOWN``으로 표시하고 Primary로 돌려보낸다. 시험은 호출 횟수 0을 고정한다.
    """

    def review(self, question: str, payload: Mapping[str, object]) -> object: ...


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class FreshnessBinding:
    """readiness가 귀속되는 revision 묶음. 하나라도 달라지면 재평가 대상이다."""

    decision_revision: int
    action_digest: str
    state_revision: int
    authority_revision: int | None = None
    policy_version: str | None = None

    def changed_fields(self, current: FreshnessBinding) -> tuple[str, ...]:
        changed: list[str] = []
        for name in ("decision_revision", "action_digest", "state_revision", "authority_revision", "policy_version"):
            if getattr(self, name) != getattr(current, name):
                changed.append(name)
        return tuple(changed)

    def is_fresh(self, current: FreshnessBinding) -> bool:
        return not self.changed_fields(current)

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(_canonical(self.as_mapping()).encode("utf-8")).hexdigest()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "decision_revision": self.decision_revision,
            "action_digest": self.action_digest,
            "state_revision": self.state_revision,
            "authority_revision": self.authority_revision,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class FreshnessCheck:
    fresh: bool
    changed: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ActionScope:
    """실행 대상의 구조적 범위. 의미적 정답은 담지 않는다."""

    tool: str
    scope: str
    expected_outcome: str
    action_digest: str
    human_only_operation: bool = False

    @property
    def clear(self) -> bool:
        return bool(self.tool and self.scope and self.expected_outcome and self.action_digest)


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    provenance_uri: str = ""
    provenance_digest: str = ""
    observed_at: datetime | None = None

    @property
    def provenance_linked(self) -> bool:
        return bool(self.provenance_uri and self.provenance_digest and self.observed_at is not None)


@dataclass(frozen=True, slots=True)
class UnknownDisposition:
    """unknown의 명시적 처리. ACCEPTABLE까지 명시되어야 explicit로 인정한다."""

    question: str
    materiality: UnknownMateriality = UnknownMateriality.ACCEPTABLE
    affects_action: bool = True
    disposition: str = ""
    reason: str = ""

    @property
    def explicit(self) -> bool:
        return bool(self.disposition and self.reason)

    @property
    def blocking(self) -> bool:
        return same_enum(self.materiality, UnknownMateriality.BLOCKING) and self.affects_action


@dataclass(frozen=True, slots=True)
class HardConstraint:
    name: str
    satisfied: bool
    machine_checkable: bool = True
    human_attestation: str = ""


@dataclass(frozen=True, slots=True)
class GuardReceipt:
    """executor가 실제 강제한 guard의 receipt. 문자열 선언만 있는 guard는 receipt가 아니다."""

    guard: ReshapeGuard
    enforced_by: str
    receipt_digest: str
    enforced: bool = True
    external_ref: str = ""

    @property
    def accepted(self) -> bool:
        return bool(self.enforced and self.enforced_by and self.receipt_digest)


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """rollback은 실행 가능한 mechanism과 checkpoint reference가 있어야 한다."""

    required: bool
    mechanism: str = ""
    checkpoint_ref: str = ""
    scope: str = ""
    note: str = ""

    @property
    def executable(self) -> bool:
        return self.mechanism in EXECUTABLE_ROLLBACK_MECHANISMS and bool(self.checkpoint_ref)


@dataclass(frozen=True, slots=True)
class VerificationRequirement:
    name: str
    required: bool = True
    satisfied: bool = False
    receipt_ref: str = ""

    @property
    def met(self) -> bool:
        return self.satisfied and bool(self.receipt_ref)


@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    """readiness 판정 입력. 의미적 결론 문구는 의도적으로 field가 없다."""

    action: ActionScope
    authorized_action_digest: str = ""
    decision_revision: int = 1
    state_revision: int = 1
    authority_revision: int | None = None
    policy_version: str | None = None
    grounds: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    unknowns: tuple[UnknownDisposition, ...] = ()
    constraints: tuple[HardConstraint, ...] = ()
    risk: RiskProfile = field(default_factory=RiskProfile)
    guard_receipts: tuple[GuardReceipt, ...] = ()
    risk_acceptances: Mapping[str, str] = field(default_factory=dict)
    rollback: RollbackPlan | None = None
    verification: tuple[VerificationRequirement, ...] = ()
    authority_decision: AuthorityDecision | None = None
    limits: tuple[str, ...] = ()
    advisory_notes: tuple[str, ...] = ()

    def freshness(self) -> FreshnessBinding:
        return FreshnessBinding(
            decision_revision=self.decision_revision,
            action_digest=self.authorized_action_digest or self.action.action_digest,
            state_revision=self.state_revision,
            authority_revision=self.authority_revision,
            policy_version=self.policy_version,
        )


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    verdict: ReadinessVerdict
    checks: tuple[ReadinessCheckResult, ...]
    freshness: FreshnessBinding
    blocking_conditions: tuple[str, ...] = ()
    guards: tuple[GuardReceipt, ...] = ()
    limits: tuple[str, ...] = ()
    needs_primary_judgment: bool = False
    semantic_review_performed: bool = False

    def __post_init__(self) -> None:
        if self.semantic_review_performed:
            raise ReadinessError("COMMIT gate는 결론의 의미적 정답을 재심사하지 않는다")
        seen = {result.check for result in self.checks}
        missing = [check for check in ReadinessCheck if check not in seen]
        if missing:
            raise ReadinessError(f"readiness check 누락: {missing}")
        if same_enum(self.verdict, ReadinessVerdict.NOT_READY) and not self.blocking_conditions:
            raise ReadinessError("NOT_READY에는 blocking condition이 필요하다")

    def check_result(self, check: ReadinessCheck) -> ReadinessCheckResult:
        for result in self.checks:
            if result.check is check:
                return result
        raise ReadinessError(f"check not found: {check}")

    @property
    def ok(self) -> bool:
        return not same_enum(self.verdict, ReadinessVerdict.NOT_READY)

    def as_assurance(self) -> DecisionAssurance:
        """canonical DecisionAssurance로 옮긴다. 같은 9개 check와 revision을 유지한다."""

        return DecisionAssurance(
            verdict=self.verdict,
            check_results=self.checks,
            decision_revision=max(1, self.freshness.decision_revision),
            authority_revision=self.freshness.authority_revision,
            action_digest=self.freshness.action_digest,
            state_revision=max(1, self.freshness.state_revision),
            policy_version=self.freshness.policy_version,
        )


def _result(
    check: ReadinessCheck,
    status: CheckStatus,
    reason: str,
    *,
    evidence_refs: Sequence[str] = (),
) -> ReadinessCheckResult:
    return ReadinessCheckResult(check=check, status=status, reason=reason, evidence_refs=tuple(evidence_refs))


class ReadinessGate:
    """9개 readiness check를 수행하는 순수 gate.

    ``semantic_judge``는 계약상 **호출되지 않는다**. 의미적 불확실성은 UNKNOWN으로 표시해
    Primary로 돌려보낸다. 이 파라미터는 그 경계를 시험으로 고정하기 위해 존재한다.
    """

    def __init__(self, *, semantic_judge: SemanticJudge | None = None) -> None:
        self.semantic_judge = semantic_judge

    def check(self, inputs: ReadinessInputs) -> ReadinessResult:
        checks = (
            self._ground(inputs),
            self._provenance(inputs),
            self._material_unknown(inputs),
            self._hard_constraints(inputs),
            self._residual_risk(inputs),
            self._authority(inputs),
            self._verification(inputs),
            self._rollback(inputs),
            self._action_scope(inputs),
        )
        failures = [result for result in checks if same_enum(result.status, CheckStatus.FAIL)]
        unknowns = [result for result in checks if same_enum(result.status, CheckStatus.UNKNOWN)]
        if failures or unknowns:
            verdict = ReadinessVerdict.NOT_READY
        elif inputs.guard_receipts or inputs.limits or inputs.risk_acceptances:
            verdict = ReadinessVerdict.READY_WITH_GUARDS
        else:
            verdict = ReadinessVerdict.READY
        blocking = tuple(f"{result.check.value}: {result.reason}" for result in (*failures, *unknowns))
        return ReadinessResult(
            verdict=verdict,
            checks=checks,
            freshness=inputs.freshness(),
            blocking_conditions=blocking,
            guards=inputs.guard_receipts,
            limits=inputs.limits,
            needs_primary_judgment=bool(unknowns),
        )

    # ── 개별 check ──────────────────────────────────────
    def _ground(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        if inputs.grounds:
            return _result(
                ReadinessCheck.GROUND_EXISTS,
                CheckStatus.PASS,
                f"decision ground {len(inputs.grounds)}건이 기록됐다",
                evidence_refs=inputs.grounds,
            )
        return _result(
            ReadinessCheck.GROUND_EXISTS,
            CheckStatus.FAIL,
            "ground 없는 판단은 COMMIT할 수 없다",
        )

    def _provenance(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        if not inputs.evidence_refs:
            if inputs.grounds:
                return _result(
                    ReadinessCheck.EVIDENCE_PROVENANCE_LINKED,
                    CheckStatus.FAIL,
                    "ground가 있지만 provenance가 연결된 evidence reference가 없다",
                )
            return _result(
                ReadinessCheck.EVIDENCE_PROVENANCE_LINKED,
                CheckStatus.N_A,
                "ground evidence reference가 없어 provenance 검사 대상이 없다",
            )
        unlinked = [ref.evidence_id for ref in inputs.evidence_refs if not ref.provenance_linked]
        if unlinked:
            return _result(
                ReadinessCheck.EVIDENCE_PROVENANCE_LINKED,
                CheckStatus.FAIL,
                f"provenance가 연결되지 않은 evidence: {unlinked}",
            )
        return _result(
            ReadinessCheck.EVIDENCE_PROVENANCE_LINKED,
            CheckStatus.PASS,
            "모든 evidence reference에 source·digest·관측 시각이 연결됐다",
            evidence_refs=tuple(ref.evidence_id for ref in inputs.evidence_refs),
        )

    def _material_unknown(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        if not inputs.unknowns:
            return _result(
                ReadinessCheck.MATERIAL_UNKNOWN_EXPLICIT,
                CheckStatus.N_A,
                "unknown이 기록되지 않았다",
            )
        blocking = [unknown for unknown in inputs.unknowns if unknown.blocking]
        if blocking:
            return _result(
                ReadinessCheck.MATERIAL_UNKNOWN_EXPLICIT,
                CheckStatus.FAIL,
                f"BLOCKING unknown이 이 action에 걸려 있다: {[unknown.question for unknown in blocking]}",
            )
        undeclared = [
            unknown.question
            for unknown in inputs.unknowns
            if (unknown.affects_action or unknown.materiality == "MATERIAL") and not unknown.explicit
        ]
        if undeclared:
            return _result(
                ReadinessCheck.MATERIAL_UNKNOWN_EXPLICIT,
                CheckStatus.FAIL,
                f"명시적 disposition이 없는 unknown: {undeclared}",
            )
        return _result(
            ReadinessCheck.MATERIAL_UNKNOWN_EXPLICIT,
            CheckStatus.PASS,
            f"unknown {len(inputs.unknowns)}건이 materiality와 disposition으로 명시됐다",
        )

    def _hard_constraints(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        if not inputs.constraints:
            return _result(
                ReadinessCheck.HARD_CONSTRAINTS_SATISFIED,
                CheckStatus.N_A,
                "hard constraint가 선언되지 않았다",
            )
        violated = [constraint.name for constraint in inputs.constraints if not constraint.satisfied]
        if violated:
            return _result(
                ReadinessCheck.HARD_CONSTRAINTS_SATISFIED,
                CheckStatus.FAIL,
                f"충족되지 않은 hard constraint: {violated}",
            )
        unattested = [
            constraint.name
            for constraint in inputs.constraints
            if not constraint.machine_checkable and not constraint.human_attestation
        ]
        if unattested:
            return _result(
                ReadinessCheck.HARD_CONSTRAINTS_SATISFIED,
                CheckStatus.UNKNOWN,
                f"기계 검증도 human attestation도 없는 constraint: {unattested} — Primary 판단이 필요하다",
            )
        return _result(
            ReadinessCheck.HARD_CONSTRAINTS_SATISFIED,
            CheckStatus.PASS,
            "모든 hard constraint가 기계 검증 또는 human attestation으로 확인됐다",
        )

    def _residual_risk(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        elevated = self._elevated_dimensions(inputs.risk)
        if not elevated:
            return _result(
                ReadinessCheck.RESIDUAL_RISK_MANAGEABLE,
                CheckStatus.PASS,
                "elevated risk dimension이 없다",
            )
        accepted = {
            guard
            for receipt in inputs.guard_receipts
            if receipt.accepted
            for guard in GUARD_RISK_COVERAGE[receipt.guard]
        }
        unmanaged = [
            dimension
            for dimension in elevated
            if dimension not in accepted and dimension not in inputs.risk_acceptances
        ]
        if unmanaged:
            return _result(
                ReadinessCheck.RESIDUAL_RISK_MANAGEABLE,
                CheckStatus.FAIL,
                f"guard receipt도 acceptance도 없는 elevated risk: {unmanaged}",
            )
        return _result(
            ReadinessCheck.RESIDUAL_RISK_MANAGEABLE,
            CheckStatus.PASS,
            "elevated risk가 강제된 guard receipt 또는 명시적 acceptance로 관리된다",
        )

    def _authority(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        decision = inputs.authority_decision
        if decision is None:
            return _result(
                ReadinessCheck.AUTHORITY_SUFFICIENT,
                CheckStatus.UNKNOWN,
                "authority 판정이 없어 충분성을 확인할 수 없다",
            )
        if not decision.allowed:
            return _result(
                ReadinessCheck.AUTHORITY_SUFFICIENT,
                CheckStatus.FAIL,
                f"authority 부족: {decision.verdict.value} — {decision.reason}",
            )
        if decision.profile_revision != (inputs.authority_revision or decision.profile_revision):
            return _result(
                ReadinessCheck.AUTHORITY_SUFFICIENT,
                CheckStatus.FAIL,
                "authority revision이 판정 시점과 다르다",
            )
        return _result(
            ReadinessCheck.AUTHORITY_SUFFICIENT,
            CheckStatus.PASS,
            f"{decision.dimension.value} 권한이 revision {decision.profile_revision}에서 확인됐다",
        )

    def _verification(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        required = [requirement for requirement in inputs.verification if requirement.required]
        if not required:
            return _result(
                ReadinessCheck.VERIFICATION_SUFFICIENT,
                CheckStatus.N_A,
                "action profile에 필요한 verification이 선언되지 않았다",
            )
        missing = [requirement.name for requirement in required if not requirement.met]
        if missing:
            return _result(
                ReadinessCheck.VERIFICATION_SUFFICIENT,
                CheckStatus.FAIL,
                f"필수 verification이 충족되지 않았다: {missing}",
            )
        return _result(
            ReadinessCheck.VERIFICATION_SUFFICIENT,
            CheckStatus.PASS,
            f"필수 verification {len(required)}건이 receipt로 확인됐다",
            evidence_refs=tuple(requirement.receipt_ref for requirement in required),
        )

    def _rollback(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        plan = inputs.rollback
        needed = bool(plan and plan.required) or inputs.risk.rollback in ELEVATED_RISKS
        if not needed:
            return _result(
                ReadinessCheck.ROLLBACK_SUFFICIENT,
                CheckStatus.N_A,
                "되돌릴 필요가 없는 action으로 선언됐다",
            )
        if plan is None:
            return _result(
                ReadinessCheck.ROLLBACK_SUFFICIENT,
                CheckStatus.FAIL,
                "rollback이 필요하지만 plan이 없다",
            )
        if not plan.executable:
            return _result(
                ReadinessCheck.ROLLBACK_SUFFICIENT,
                CheckStatus.FAIL,
                "문자열 rollback 약속은 충족이 아니다: 실행 가능한 mechanism과 checkpoint reference가 필요하다",
            )
        return _result(
            ReadinessCheck.ROLLBACK_SUFFICIENT,
            CheckStatus.PASS,
            f"{plan.mechanism} checkpoint로 되돌릴 수 있다",
            evidence_refs=(plan.checkpoint_ref,),
        )

    def _action_scope(self, inputs: ReadinessInputs) -> ReadinessCheckResult:
        if not inputs.action.clear:
            return _result(
                ReadinessCheck.ACTION_SCOPE_CLEAR,
                CheckStatus.FAIL,
                "action의 tool·scope·expected outcome·digest가 모두 선언되지 않았다",
            )
        if inputs.authorized_action_digest and inputs.action.action_digest != inputs.authorized_action_digest:
            return _result(
                ReadinessCheck.ACTION_SCOPE_CLEAR,
                CheckStatus.FAIL,
                "action args가 승인된 digest 이후에 바뀌었다: 재승인이 필요하다",
            )
        return _result(
            ReadinessCheck.ACTION_SCOPE_CLEAR,
            CheckStatus.PASS,
            f"action scope {inputs.action.scope}가 digest에 결박됐다",
        )

    @staticmethod
    def _elevated_dimensions(risk: RiskProfile) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                "reversibility",
                "blast_radius",
                "data_state_loss",
                "external_impact",
                "security_privacy",
                "authority_sensitivity",
                "verification",
                "rollback",
                "cost",
                "goal_premise_impact",
            )
            if getattr(risk, name) in ELEVATED_RISKS
        )

    # ── freshness ────────────────────────────────────────
    def revalidate(self, result: ReadinessResult, current: FreshnessBinding) -> FreshnessCheck:
        """ACTION 직전 재평가. COMMIT을 한 번 통과했다고 영구 허가하지 않는다."""

        changed = result.freshness.changed_fields(current)
        if not changed:
            return FreshnessCheck(fresh=True, reason="귀속 revision이 그대로다")
        return FreshnessCheck(
            fresh=False,
            changed=changed,
            reason=f"ACTION 전 재평가가 필요하다: {list(changed)}",
        )

    def assert_fresh(self, result: ReadinessResult, current: FreshnessBinding) -> FreshnessCheck:
        check = self.revalidate(result, current)
        if not check.fresh:
            raise StaleReadinessError(check.reason)
        return check


def check_readiness(inputs: ReadinessInputs) -> ReadinessResult:
    """provider를 받지 않는 순수 진입점. registry/저장소 없이도 같은 결과를 낸다."""

    return ReadinessGate().check(inputs)


__all__ = [
    "ELEVATED_RISKS",
    "EXECUTABLE_ROLLBACK_MECHANISMS",
    "GUARD_RISK_COVERAGE",
    "ActionScope",
    "EvidenceRef",
    "FreshnessBinding",
    "FreshnessCheck",
    "GuardReceipt",
    "HardConstraint",
    "ReadinessError",
    "ReadinessGate",
    "ReadinessInputs",
    "ReadinessResult",
    "RollbackPlan",
    "SemanticJudge",
    "StaleReadinessError",
    "UnknownDisposition",
    "VerificationRequirement",
    "check_readiness",
]
