"""Request governance (P05) — 요청의 구조적·권한적 수용 판정.

GOVERNANCE_AND_AUTHORITY.md 구현:

- disposition 5종: ``APPROVE / APPROVE_WITH_LIMITS / RESHAPE / DEFER / DENY``.
- **Body는 Brain 결론의 의미적 정답을 심사하지 않는다.** 판정 입력은 요청 type·args·권한·risk·
  unknown뿐이다. ``GovernanceRequest.advisory_notes``는 Body의 의미적 선호를 담는 자리이며
  판정에 사용하지 않는다(시험으로 고정한다).
- 권한이 없거나 불충분하다고 무조건 Human escalation하지 않는다. 설명 있는 ``DEFER``/``DENY``를
  반환하고 가능한 대안을 남긴다.
- 위험 재구성(RESHAPE)은 grant·human-only boundary를 우회하지 못한다. 재구성된 요청은 다시
  권한 검사를 받고, guard 의무를 만족하지 않은 채 실행될 수 없다.
- **No Silent Governance**: 모든 disposition은 원 요청 digest·변경·이유·남은 제약·대안을
  담은 feedback을 남긴다.
- Unknown: ACCEPTABLE/MATERIAL은 일괄 차단하지 않는다. BLOCKING은 관련 action만 차단한다.

이 모듈은 provider/UI/저장소를 import하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.authority import (
    HUMAN_ONLY_DIMENSIONS,
    HUMAN_ONLY_OPERATIONS,
    ApprovalUse,
    AuthorityDecision,
    AuthorityProfile,
    AuthorityQuery,
    AuthorityVerdict,
    scope_covers,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    GovernanceDisposition,
    GovernanceFeedback,
    InvestigationStatus,
    RiskLevel,
    RiskProfile,
    UnknownMateriality,
    same_enum,
)

#: 높은 위험으로 취급하는 level. 하나의 risk score로 합성하지 않는다.
ELEVATED_RISKS: Final[frozenset[RiskLevel]] = frozenset({RiskLevel.HIGH, RiskLevel.SEVERE})

#: shell 도구 이름. 같은 governance 경로를 지난다.
SHELL_TOOL_NAMES: Final[tuple[str, ...]] = ("run_bash_command", "bash", "run_persistent_command", "shell", "terminal")
#: 읽기 전용으로 분류하는 도구 이름 조각.
READ_TOOL_HINTS: Final[tuple[str, ...]] = (
    "read",
    "list",
    "grep",
    "glob",
    "search",
    "fetch",
    "status",
    "check",
    "diff",
    "describe",
)
#: 되돌리기 어려운 도구 이름 조각.
DESTRUCTIVE_TOOL_HINTS: Final[tuple[str, ...]] = ("delete", "remove", "drop", "truncate", "reset", "rollback", "rm_")
#: 쓰기로 분류하는 도구 이름 조각.
WRITE_TOOL_HINTS: Final[tuple[str, ...]] = (
    "write",
    "edit",
    "replace",
    "patch",
    "create",
    "move",
    "rename",
    "append",
    "install",
    "commit",
)


class GovernanceError(ValueError):
    """governance 계약 위반(누락된 feedback, 의미 심사 시도 등)."""


class ReshapeGuard(StrEnum):
    """재구성된 요청이 실행 전에 만족해야 하는 guard 의무."""

    ISOLATED_SCOPE = "ISOLATED_SCOPE"
    NARROWED_SCOPE = "NARROWED_SCOPE"
    CHECKPOINT = "CHECKPOINT"
    DRY_RUN = "DRY_RUN"
    DIFF_INSPECTION = "DIFF_INSPECTION"
    VERIFICATION = "VERIFICATION"
    BUDGET_LIMIT = "BUDGET_LIMIT"
    READ_ONLY = "READ_ONLY"


def reshape_plan(risk: RiskProfile, *, reversible: bool) -> tuple[ReshapeGuard, ...]:
    """risk dimension별로 필요한 guard를 나열한다. 위험을 낮추는 실행 형태를 guard로 구체화한다."""

    guards: list[ReshapeGuard] = []
    if not reversible:
        guards.extend((ReshapeGuard.CHECKPOINT, ReshapeGuard.NARROWED_SCOPE))
    if risk.blast_radius in ELEVATED_RISKS:
        guards.extend((ReshapeGuard.ISOLATED_SCOPE, ReshapeGuard.NARROWED_SCOPE))
    if risk.data_state_loss in ELEVATED_RISKS:
        guards.extend((ReshapeGuard.CHECKPOINT, ReshapeGuard.DRY_RUN))
    if risk.reversibility in ELEVATED_RISKS or risk.rollback in ELEVATED_RISKS:
        guards.append(ReshapeGuard.CHECKPOINT)
    if risk.verification in ELEVATED_RISKS:
        guards.extend((ReshapeGuard.VERIFICATION, ReshapeGuard.DIFF_INSPECTION))
    if risk.external_impact in ELEVATED_RISKS or risk.security_privacy in ELEVATED_RISKS:
        guards.append(ReshapeGuard.NARROWED_SCOPE)
    if risk.cost in ELEVATED_RISKS:
        guards.append(ReshapeGuard.BUDGET_LIMIT)
    if risk.authority_sensitivity in ELEVATED_RISKS:
        guards.append(ReshapeGuard.READ_ONLY)
    if risk.goal_premise_impact in ELEVATED_RISKS:
        guards.append(ReshapeGuard.DIFF_INSPECTION)
    return tuple(dict.fromkeys(guards))


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class RequestedAction:
    """governance가 판정하는 요청. 의미적 정답 field는 의도적으로 존재하지 않는다."""

    tool: str
    operation: str
    dimension: AuthorityDimension
    resource_scope: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    risk: RiskProfile = field(default_factory=RiskProfile)
    reversible: bool = True
    idempotency_key: str = ""
    guard_obligations: tuple[ReshapeGuard, ...] = ()

    def digest(self) -> str:
        payload = {
            "tool": self.tool,
            "operation": self.operation,
            "dimension": self.dimension.value,
            "resource_scope": self.resource_scope,
            "arguments": dict(self.arguments),
            "reversible": self.reversible,
            "idempotency_key": self.idempotency_key,
            "guards": [guard.value for guard in self.guard_obligations],
        }
        return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UnknownAssessment:
    """요청과 함께 전달되는 unknown 평가. 차단은 관련 action에만 적용한다."""

    question: str
    materiality: UnknownMateriality
    affects_action: bool = True
    investigation_status: InvestigationStatus = InvestigationStatus.NOT_ASSESSED


@dataclass(frozen=True, slots=True)
class GovernanceRequest:
    request_id: str
    project_id: str
    action: RequestedAction
    subject: str = "body:runtime"
    authority: AuthorityProfile | None = None
    unknowns: tuple[UnknownAssessment, ...] = ()
    human_approval: ApprovalUse | None = None
    policy_version: str | None = None
    state_revision: int = 1
    parent_request_id: str = ""
    advisory_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernanceOutcome:
    """판정 결과. scalar score field는 없고, feedback이 항상 동반된다."""

    request_id: str
    action_digest: str
    disposition: GovernanceDisposition
    reason: str
    feedback: GovernanceFeedback
    authority: AuthorityDecision | None = None
    changes: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    guards: tuple[ReshapeGuard, ...] = ()
    reshaped_action: RequestedAction | None = None
    reauthorization_required: bool = False
    blocked_unknowns: tuple[str, ...] = ()
    remaining_unknowns: tuple[str, ...] = ()
    semantic_review_performed: bool = False
    human_decision_required: bool = False
    parent_request_id: str = ""

    def __post_init__(self) -> None:
        if self.semantic_review_performed:
            raise GovernanceError("Body governance는 요청의 의미적 정답을 심사할 수 없다")
        if self.feedback.original_request_digest != self.action_digest:
            raise GovernanceError("feedback이 원 요청 digest에 결박되지 않았다")
        if self.disposition in (GovernanceDisposition.DENY, GovernanceDisposition.DEFER):
            if not self.reason:
                raise GovernanceError("DENY/DEFER에는 설명이 필요하다")
            if not self.alternatives and not self.limits:
                raise GovernanceError("DENY/DEFER에는 남은 제약 또는 대안이 필요하다")
        if self.disposition in (GovernanceDisposition.APPROVE, GovernanceDisposition.APPROVE_WITH_LIMITS):
            if self.changes:
                raise GovernanceError("APPROVE 계열은 요청을 변경하지 않는다")
        if same_enum(self.disposition, GovernanceDisposition.RESHAPE):
            if not self.guards or self.reshaped_action is None:
                raise GovernanceError("RESHAPE에는 guard와 재구성된 action이 필요하다")
            if not self.reauthorization_required and not self.parent_request_id:
                raise GovernanceError("RESHAPE 결과는 재권한 검사를 요구해야 한다")

    @property
    def admits_execution(self) -> bool:
        """실행을 허용하는 결과인지. RESHAPE는 재권한을 마친 경우에만 실행으로 넘어간다."""

        if self.disposition in (GovernanceDisposition.APPROVE, GovernanceDisposition.APPROVE_WITH_LIMITS):
            return True
        return same_enum(self.disposition, GovernanceDisposition.RESHAPE) and bool(self.parent_request_id)


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    allowed: bool
    reason: str
    disposition: GovernanceDisposition
    action_digest: str
    missing_guards: tuple[ReshapeGuard, ...] = ()
    limits: tuple[str, ...] = ()


class GovernanceGate:
    """Cognitive Request governance 판정기. 판정만 담당하고 부작용이 없다.

    Body는 이 gate에서 Brain 결론의 의미적 정답을 판단하지 않는다. ``advisory_notes``는
    판정 입력이 아니며, 결과를 바꾸지 못한다.
    """

    def __init__(
        self,
        *,
        human_only_operations: frozenset[str] = HUMAN_ONLY_OPERATIONS,
        human_only_dimensions: frozenset[AuthorityDimension] = HUMAN_ONLY_DIMENSIONS,
        clock: object | None = None,
    ) -> None:
        self.human_only_operations = human_only_operations
        self.human_only_dimensions = human_only_dimensions
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None and callable(self._clock):
            value = self._clock()
            if isinstance(value, datetime):
                return value
        return datetime.now(UTC)

    # ── 판정 ────────────────────────────────────────────
    def evaluate(self, request: GovernanceRequest) -> GovernanceOutcome:
        action = request.action
        action_digest = action.digest()
        changes: list[str] = []
        limits: list[str] = []
        blocked_unknowns: list[str] = []
        remaining_unknowns: list[str] = []
        authority_decision: AuthorityDecision | None = None
        human_decision_id = self._reusable_human_decision(request)

        # 1) protected/human-only boundary
        if action.operation in self.human_only_operations or action.dimension in self.human_only_dimensions:
            if not human_decision_id:
                return self._outcome(
                    request,
                    action_digest,
                    disposition=GovernanceDisposition.DENY,
                    reason=(
                        f"{action.dimension}/{action.operation}는 human-only boundary다. "
                        "Body·Brain·learned policy가 reshape로 우회할 수 없다."
                    ),
                    authority=authority_decision,
                    alternatives=("request_human_decision",),
                    limits=("human-only boundary는 reshape 대상이 아니다",),
                    human_decision_required=True,
                )

        # 2) 다차원 권한
        if request.authority is not None:
            authority_decision = request.authority.evaluate(
                AuthorityQuery(
                    subject=request.subject,
                    dimension=action.dimension,
                    resource_scope=action.resource_scope,
                    operation=action.operation,
                    human_decision_id=human_decision_id,
                ),
                now=self._now(),
            )
            if not authority_decision.allowed:
                verdict = authority_decision.verdict
                if verdict in (
                    AuthorityVerdict.REVOKED,
                    AuthorityVerdict.OPERATION_NOT_ALLOWED,
                    AuthorityVerdict.CEILING_EXCEEDED,
                    AuthorityVerdict.HUMAN_ONLY_BOUNDARY,
                    AuthorityVerdict.CONSTRAINT_VIOLATED,
                ):
                    return self._outcome(
                        request,
                        action_digest,
                        disposition=GovernanceDisposition.DENY,
                        reason=authority_decision.reason,
                        authority=authority_decision,
                        alternatives=("request_human_decision", "narrow_scope"),
                        limits=("grant가 허용하지 않는 요청이다",),
                        human_decision_required=authority_decision.human_decision_required,
                    )
                if request.parent_request_id:
                    return self._outcome(
                        request,
                        action_digest,
                        disposition=GovernanceDisposition.DENY,
                        reason=(f"재구성된 요청이 원 요청의 grant 밖이다: {authority_decision.reason}"),
                        authority=authority_decision,
                        alternatives=("narrow_scope", "request_human_decision"),
                        limits=("reshape는 grant를 넓힐 수 없다",),
                    )
                return self._outcome(
                    request,
                    action_digest,
                    disposition=GovernanceDisposition.DEFER,
                    reason=f"권한이 아직 충분하지 않다: {authority_decision.reason}",
                    authority=authority_decision,
                    alternatives=("request_approval", "narrow_scope", "split_action"),
                    limits=("유효한 grant 확보 전에는 실행하지 않는다",),
                )
            limits.extend(authority_decision.limits)

        # 3) unknown — BLOCKING만 관련 action을 차단한다
        for unknown in request.unknowns:
            if same_enum(unknown.materiality, UnknownMateriality.BLOCKING) and unknown.affects_action:
                blocked_unknowns.append(unknown.question)
                continue
            remaining_unknowns.append(unknown.question)
            if same_enum(unknown.materiality, UnknownMateriality.MATERIAL):
                limits.append(f"action 전에 확인할 unknown: {unknown.question}")
        if blocked_unknowns:
            return self._outcome(
                request,
                action_digest,
                disposition=GovernanceDisposition.DENY,
                reason="BLOCKING unknown이 이 action에 직접 걸려 있다",
                authority=authority_decision,
                alternatives=("resolve_unknown", "narrow_action"),
                limits=("다른 action은 계속 진행할 수 있다",),
                blocked_unknowns=tuple(blocked_unknowns),
                remaining_unknowns=tuple(remaining_unknowns),
            )

        # 4) 위험 재구성
        guards = reshape_plan(action.risk, reversible=action.reversible)
        reshaped_action: RequestedAction | None = None
        if guards:
            reshaped_action = replace(action, guard_obligations=guards)
            changes.append("risk를 낮추는 guard 의무를 요청에 추가했다")
            for guard in guards:
                changes.append(f"guard: {guard.value}")
            # 재구성은 권한을 넓히지 않는다 — 넓히면 거부한다.
            if request.authority is not None:
                reshaped_decision = request.authority.evaluate(
                    AuthorityQuery(
                        subject=request.subject,
                        dimension=reshaped_action.dimension,
                        resource_scope=reshaped_action.resource_scope,
                        operation=reshaped_action.operation,
                        human_decision_id=human_decision_id,
                    ),
                    now=self._now(),
                )
                if not reshaped_decision.allowed:
                    return self._outcome(
                        request,
                        action_digest,
                        disposition=GovernanceDisposition.DENY,
                        reason=f"재구성된 요청이 grant 밖이다: {reshaped_decision.reason}",
                        authority=reshaped_decision,
                        alternatives=("narrow_scope", "request_human_decision"),
                        limits=("reshape는 grant를 넓힐 수 없다",),
                        human_decision_required=reshaped_decision.human_decision_required,
                    )
            return self._outcome(
                request,
                action_digest,
                disposition=GovernanceDisposition.RESHAPE,
                reason="요청은 수용 가능하지만 위험을 낮춘 실행 형태가 필요하다",
                authority=authority_decision,
                changes=tuple(changes),
                limits=tuple(limits),
                alternatives=("accept_guards", "narrow_scope", "defer"),
                guards=guards,
                reshaped_action=reshaped_action,
                reauthorization_required=True,
                remaining_unknowns=tuple(remaining_unknowns),
            )

        # 5) 승인
        if limits:
            return self._outcome(
                request,
                action_digest,
                disposition=GovernanceDisposition.APPROVE_WITH_LIMITS,
                reason="요청을 수용하되 grant 제약과 남은 확인 사항을 limit으로 유지한다",
                authority=authority_decision,
                limits=tuple(limits),
                alternatives=("accept_limits",),
                remaining_unknowns=tuple(remaining_unknowns),
            )
        return self._outcome(
            request,
            action_digest,
            disposition=GovernanceDisposition.APPROVE,
            reason="요청을 그대로 수용한다",
            authority=authority_decision,
            remaining_unknowns=tuple(remaining_unknowns),
        )

    def _reusable_human_decision(self, request: GovernanceRequest) -> str:
        """같은 principal·scope·operation·유효기간의 사람 승인만 재사용한다."""

        if request.authority is None or request.human_approval is None:
            return ""
        reuse = request.authority.reuse_approval(
            request.human_approval,
            AuthorityQuery(
                subject=request.subject,
                dimension=request.action.dimension,
                resource_scope=request.action.resource_scope,
                operation=request.action.operation,
            ),
            now=self._now(),
            action_digest=request.action.digest(),
        )
        return request.human_approval.approval_id if reuse.reusable else ""

    def _outcome(
        self,
        request: GovernanceRequest,
        action_digest: str,
        *,
        disposition: GovernanceDisposition,
        reason: str,
        authority: AuthorityDecision | None,
        changes: tuple[str, ...] = (),
        limits: tuple[str, ...] = (),
        alternatives: tuple[str, ...] = (),
        guards: tuple[ReshapeGuard, ...] = (),
        reshaped_action: RequestedAction | None = None,
        reauthorization_required: bool = False,
        blocked_unknowns: tuple[str, ...] = (),
        remaining_unknowns: tuple[str, ...] = (),
        human_decision_required: bool = False,
    ) -> GovernanceOutcome:
        feedback_changes = changes
        if request.parent_request_id:
            feedback_changes = (*changes, f"re-authorized from request {request.parent_request_id}")
        feedback = GovernanceFeedback(
            original_request_digest=action_digest,
            what_changed=feedback_changes,
            why_changed=reason,
            remaining_constraints=limits if limits else (authority.limits if authority is not None else ()),
            available_alternatives=alternatives,
        )
        return GovernanceOutcome(
            request_id=request.request_id,
            action_digest=action_digest,
            disposition=disposition,
            reason=reason,
            feedback=feedback,
            authority=authority,
            changes=changes,
            limits=limits,
            alternatives=alternatives,
            guards=guards,
            reshaped_action=reshaped_action,
            reauthorization_required=reauthorization_required,
            blocked_unknowns=blocked_unknowns,
            remaining_unknowns=remaining_unknowns,
            human_decision_required=human_decision_required,
            parent_request_id=request.parent_request_id,
        )

    # ── 재구성된 요청의 재권한 ──────────────────────────
    def reauthorize(
        self,
        outcome: GovernanceOutcome,
        request: GovernanceRequest,
        *,
        action: RequestedAction | None = None,
        request_id: str | None = None,
    ) -> GovernanceOutcome:
        """변경된 args/action을 원 요청 계보에 붙여 다시 판정한다.

        ``action``을 주면 재구성 결과를 대체한다(넓히면 권한 검사에서 거부된다).
        """

        if not same_enum(outcome.disposition, GovernanceDisposition.RESHAPE) and action is None:
            raise GovernanceError("reauthorize는 RESHAPE 결과나 명시적 action 변경에만 사용한다")
        target = action if action is not None else outcome.reshaped_action
        if target is None:
            raise GovernanceError("재권한 대상 action이 없다")
        return self.evaluate(
            replace(
                request,
                request_id=request_id if request_id is not None else request.request_id,
                action=target,
                parent_request_id=outcome.request_id,
            )
        )

    # ── 실행 직전 확인 ──────────────────────────────────
    def authorize_execution(
        self,
        outcome: GovernanceOutcome,
        *,
        satisfied_guards: Sequence[ReshapeGuard] = (),
        action_digest: str | None = None,
    ) -> ExecutionAuthorization:
        """guard 의무·digest가 유지됐는지 확인한다. 문자열 약속은 guard를 대신하지 못한다."""

        if outcome.reauthorization_required and not outcome.parent_request_id:
            return ExecutionAuthorization(
                allowed=False,
                reason="재구성된 요청은 재권한 검사 전에 실행할 수 없다",
                disposition=outcome.disposition,
                action_digest=outcome.action_digest,
                missing_guards=outcome.guards,
            )
        if not outcome.admits_execution:
            return ExecutionAuthorization(
                allowed=False,
                reason=f"{outcome.disposition}: {outcome.reason}",
                disposition=outcome.disposition,
                action_digest=outcome.action_digest,
                limits=outcome.limits,
            )
        satisfied = set(satisfied_guards)
        missing = tuple(guard for guard in outcome.guards if guard not in satisfied)
        if missing:
            return ExecutionAuthorization(
                allowed=False,
                reason="guard 의무가 아직 만족되지 않았다",
                disposition=outcome.disposition,
                action_digest=outcome.action_digest,
                missing_guards=missing,
                limits=outcome.limits,
            )
        if action_digest is not None and action_digest != outcome.action_digest:
            return ExecutionAuthorization(
                allowed=False,
                reason="승인된 action digest와 실행 대상이 다르다",
                disposition=outcome.disposition,
                action_digest=outcome.action_digest,
                limits=outcome.limits,
            )
        return ExecutionAuthorization(
            allowed=True,
            reason=outcome.reason,
            disposition=outcome.disposition,
            action_digest=outcome.action_digest,
            limits=outcome.limits,
        )


def classify_tool_dimension(tool_name: str) -> AuthorityDimension:
    """도구 이름으로 authority dimension을 정한다. 읽기는 TOOL_READ, 그 외는 TOOL_WRITE."""

    lowered = tool_name.lower()
    if tool_name in SHELL_TOOL_NAMES:
        return AuthorityDimension.TOOL_WRITE
    if any(hint in lowered for hint in WRITE_TOOL_HINTS) or any(hint in lowered for hint in DESTRUCTIVE_TOOL_HINTS):
        return AuthorityDimension.TOOL_WRITE
    if any(hint in lowered for hint in READ_TOOL_HINTS):
        return AuthorityDimension.TOOL_READ
    return AuthorityDimension.TOOL_WRITE


def risk_profile_for(tool_name: str) -> RiskProfile:
    """도구 이름 기준의 구조적 risk profile. 의미 판단이 아니라 분류다."""

    lowered = tool_name.lower()
    if tool_name in SHELL_TOOL_NAMES:
        return RiskProfile(
            reversibility=RiskLevel.MODERATE,
            blast_radius=RiskLevel.MODERATE,
            external_impact=RiskLevel.MODERATE,
            security_privacy=RiskLevel.MODERATE,
            verification=RiskLevel.MODERATE,
            cost=RiskLevel.LOW,
        )
    if any(hint in lowered for hint in DESTRUCTIVE_TOOL_HINTS):
        return RiskProfile(
            reversibility=RiskLevel.HIGH,
            blast_radius=RiskLevel.HIGH,
            data_state_loss=RiskLevel.HIGH,
            rollback=RiskLevel.HIGH,
            verification=RiskLevel.MODERATE,
        )
    if any(hint in lowered for hint in WRITE_TOOL_HINTS):
        return RiskProfile(
            reversibility=RiskLevel.MODERATE,
            blast_radius=RiskLevel.MODERATE,
            data_state_loss=RiskLevel.MODERATE,
            verification=RiskLevel.MODERATE,
        )
    return RiskProfile(
        reversibility=RiskLevel.LOW,
        blast_radius=RiskLevel.LOW,
        data_state_loss=RiskLevel.LOW,
        external_impact=RiskLevel.LOW,
        security_privacy=RiskLevel.LOW,
        verification=RiskLevel.LOW,
        cost=RiskLevel.LOW,
    )


def is_reversible_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return not any(hint in lowered for hint in DESTRUCTIVE_TOOL_HINTS)


@runtime_checkable
class ToolGovernanceOutcome(Protocol):
    """ToolExecutor가 기대하는 최소 결과 표면."""

    @property
    def disposition(self) -> object: ...

    @property
    def reason(self) -> str: ...

    @property
    def admits_execution(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ToolGovernanceAdapter:
    """기존 tool_executor 표면 adapter. 도구 호출을 GovernanceRequest로 옮긴다.

    판정 자체는 ``GovernanceGate``가 한다. 이 adapter는 도구 이름·args를 구조적 입력으로
    변환할 뿐 의미 해석을 하지 않는다.
    """

    gate: GovernanceGate
    subject: str = "body:tool-executor"
    project_id: str = ""
    authority: AuthorityProfile | None = None
    authority_provider: Callable[[str, Mapping[str, object]], AuthorityProfile | None] | None = None
    unknowns_provider: Callable[[str, Mapping[str, object]], tuple[UnknownAssessment, ...]] | None = None
    guard_runner: Callable[[GovernanceOutcome], Sequence[ReshapeGuard]] | None = None
    human_approval: ApprovalUse | None = None

    def admit(
        self,
        tool_name: str,
        args: Mapping[str, object],
        *,
        execution_mode: str = "interactive",
        request_id: str = "",
        dry_run: bool = False,
    ) -> GovernanceOutcome:
        profile = self.authority
        if self.authority_provider is not None:
            profile = self.authority_provider(tool_name, args)
        action = RequestedAction(
            tool=tool_name,
            operation="execute_tool",
            dimension=classify_tool_dimension(tool_name),
            resource_scope=self._scope_for(tool_name, args),
            arguments=dict(args),
            risk=risk_profile_for(tool_name),
            reversible=is_reversible_tool(tool_name),
            idempotency_key=str(args.get("idempotency_key", "")),
        )
        unknowns = self.unknowns_provider(tool_name, args) if self.unknowns_provider is not None else ()
        request = GovernanceRequest(
            request_id=request_id or f"tool:{tool_name}",
            project_id=self.project_id,
            subject=self.subject,
            action=action,
            authority=profile,
            unknowns=unknowns,
            human_approval=self.human_approval,
        )
        outcome = self.gate.evaluate(request)
        if not same_enum(outcome.disposition, GovernanceDisposition.RESHAPE) or self.guard_runner is None:
            return outcome

        satisfied = tuple(self.guard_runner(outcome))
        reauthorized = self.gate.reauthorize(outcome, request)
        authorization = self.gate.authorize_execution(reauthorized, satisfied_guards=satisfied)
        if authorization.allowed:
            return reauthorized
        missing = tuple(guard.value for guard in authorization.missing_guards)
        return replace(
            reauthorized,
            disposition=GovernanceDisposition.DENY,
            reason=f"guard 의무를 만족하지 못했다: {list(missing) or authorization.reason}",
            guards=authorization.missing_guards,
            reshaped_action=None,
        )

    @staticmethod
    def _scope_for(tool_name: str, args: Mapping[str, object]) -> str:
        for key in ("file_path", "path", "target", "dir_path", "target_path"):
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
        if tool_name in SHELL_TOOL_NAMES:
            return "shell"
        return f"tool:{tool_name}"


__all__ = [
    "DESTRUCTIVE_TOOL_HINTS",
    "ELEVATED_RISKS",
    "READ_TOOL_HINTS",
    "SHELL_TOOL_NAMES",
    "WRITE_TOOL_HINTS",
    "ExecutionAuthorization",
    "GovernanceError",
    "GovernanceGate",
    "GovernanceOutcome",
    "GovernanceRequest",
    "RequestedAction",
    "ReshapeGuard",
    "ToolGovernanceAdapter",
    "ToolGovernanceOutcome",
    "UnknownAssessment",
    "classify_tool_dimension",
    "is_reversible_tool",
    "reshape_plan",
    "risk_profile_for",
    "scope_covers",
]
