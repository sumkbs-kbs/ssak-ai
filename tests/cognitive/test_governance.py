"""T05 — Governance·다차원 Authority enforcement 시험 (P05).

검증 범위(T05-A~D):
- A: 5 disposition 모두 No Silent Governance feedback을 남기고, 변경된 args는 재권한 검사를 받는다.
- B: 위험 재구성은 grant 안에서 제한 행동을 만들고, human-only boundary는 reshape로 우회되지 않는다.
- C: ACCEPTABLE/MATERIAL Unknown은 일괄 차단하지 않고 BLOCKING은 관련 action만 차단한다.
- D: dimension별 grant·scope·만료·취소·delegation과 승인 재사용, 단일 score 판정 없음.

Body는 Brain 결론의 의미적 정답을 심사하지 않는다. 또한 tool_executor 실제 표면에서 adapter가
동작하는지 확인한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from antigravity_k.engine.cognitive.authority import (
    ApprovalReuseVerdict,
    ApprovalUse,
    AuthorityProfile,
    AuthorityQuery,
    AuthorityVerdict,
    AuthorityViolation,
    DelegationRequest,
    RevocationRequest,
)
from antigravity_k.engine.cognitive.governance import (
    ExecutionAuthorization,
    GovernanceError,
    GovernanceGate,
    GovernanceOutcome,
    GovernanceRequest,
    RequestedAction,
    ReshapeGuard,
    ToolGovernanceAdapter,
    UnknownAssessment,
    classify_tool_dimension,
    risk_profile_for,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    AuthorityGrant,
    GovernanceDisposition,
    GovernanceFeedback,
    ProducerKind,
    RiskLevel,
    RiskProfile,
    UnknownMateriality,
)
from antigravity_k.engine.tool_executor import ToolExecutor
from antigravity_k.tools.base_tool import BaseTool
from antigravity_k.tools.base_tool import RiskLevel as ToolRiskLevel
from antigravity_k.tools.tool_registry import ToolRegistry

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
SUBJECT = "body:runtime"


# ─── fixture helper ──────────────────────────────────────────────────


def grant(
    *,
    subject: str = SUBJECT,
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE,
    scope: str = "src",
    operations: tuple[str, ...] = ("execute_tool",),
    constraints: tuple[str, ...] = (),
    expires_at: datetime | None = None,
    revision: int = 1,
    granted_by: str = "human:mr.k",
    revoked_at: datetime | None = None,
) -> AuthorityGrant:
    return AuthorityGrant(
        subject=subject,
        dimension=dimension,
        resource_scope=scope,
        allowed_operations=operations,
        constraints=constraints,
        granted_by=granted_by,
        issued_at=NOW,
        expires_at=expires_at,
        revision=revision,
        revoked_at=revoked_at,
    )


def low_risk() -> RiskProfile:
    return RiskProfile(
        reversibility=RiskLevel.LOW,
        blast_radius=RiskLevel.LOW,
        data_state_loss=RiskLevel.LOW,
        external_impact=RiskLevel.LOW,
        security_privacy=RiskLevel.LOW,
        verification=RiskLevel.LOW,
        rollback=RiskLevel.LOW,
        cost=RiskLevel.LOW,
        goal_premise_impact=RiskLevel.LOW,
        authority_sensitivity=RiskLevel.LOW,
    )


def action(**overrides: object) -> RequestedAction:
    base: dict[str, object] = {
        "tool": "write_file",
        "operation": "execute_tool",
        "dimension": AuthorityDimension.TOOL_WRITE,
        "resource_scope": "src/a.py",
        "arguments": {"file_path": "src/a.py"},
        "risk": low_risk(),
    }
    base.update(overrides)
    return RequestedAction(**base)  # type: ignore[arg-type]


def request_for(
    target: RequestedAction,
    *,
    authority: AuthorityProfile | None = None,
    unknowns: tuple[UnknownAssessment, ...] = (),
    advisory: tuple[str, ...] = (),
    subject: str = SUBJECT,
    human_approval: ApprovalUse | None = None,
    parent_request_id: str = "",
) -> GovernanceRequest:
    return GovernanceRequest(
        request_id="req-1",
        project_id="project:ssak-ai",
        subject=subject,
        action=target,
        authority=authority,
        unknowns=unknowns,
        human_approval=human_approval,
        state_revision=1,
        parent_request_id=parent_request_id,
        advisory_notes=advisory,
    )


@pytest.fixture()
def gate() -> GovernanceGate:
    return GovernanceGate(clock=lambda: NOW)


# ─── A. disposition·feedback·재권한 ──────────────────────────────────


def test_approve_is_plain_acceptance(gate: GovernanceGate) -> None:
    target = action()
    outcome = gate.evaluate(request_for(target))

    assert outcome.disposition is GovernanceDisposition.APPROVE
    assert outcome.admits_execution
    assert outcome.changes == ()
    assert outcome.feedback.original_request_digest == target.digest()
    assert outcome.feedback.why_changed


def test_material_unknown_yields_approve_with_limits(gate: GovernanceGate) -> None:
    outcome = gate.evaluate(
        request_for(
            action(),
            unknowns=(
                UnknownAssessment(
                    question="L2 범위가 충분한가", materiality=UnknownMateriality.MATERIAL, affects_action=False
                ),
            ),
        )
    )

    assert outcome.disposition is GovernanceDisposition.APPROVE_WITH_LIMITS
    assert outcome.admits_execution
    assert any("L2 범위가 충분한가" in limit for limit in outcome.limits)
    assert outcome.remaining_unknowns == ("L2 범위가 충분한가",)


def test_missing_grant_defers_with_alternatives(gate: GovernanceGate) -> None:
    outcome = gate.evaluate(request_for(action(), authority=AuthorityProfile(revision=1)))

    assert outcome.disposition is GovernanceDisposition.DEFER
    assert not outcome.admits_execution
    assert outcome.alternatives
    assert "request_approval" in outcome.alternatives


def test_revoked_grant_is_denied(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=2, grants=(grant(revoked_at=NOW),))
    outcome = gate.evaluate(request_for(action(), authority=profile))

    assert outcome.disposition is GovernanceDisposition.DENY
    assert outcome.limits
    assert outcome.authority is not None
    assert outcome.authority.verdict is AuthorityVerdict.REVOKED


def test_high_risk_request_is_reshaped_not_escalated(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    risky = action(risk=RiskProfile(blast_radius=RiskLevel.HIGH, data_state_loss=RiskLevel.HIGH), reversible=False)
    outcome = gate.evaluate(request_for(risky, authority=profile))

    assert outcome.disposition is GovernanceDisposition.RESHAPE
    assert not outcome.human_decision_required
    assert ReshapeGuard.ISOLATED_SCOPE in outcome.guards
    assert ReshapeGuard.CHECKPOINT in outcome.guards
    assert outcome.reshaped_action is not None
    assert outcome.reshaped_action.guard_obligations == outcome.guards
    assert outcome.reauthorization_required


def test_all_dispositions_bind_feedback_to_original_request(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    cases = (
        request_for(action()),
        request_for(
            action(),
            unknowns=(
                UnknownAssessment(question="범위 확인", materiality=UnknownMateriality.MATERIAL, affects_action=False),
            ),
        ),
        request_for(action(risk=RiskProfile(blast_radius=RiskLevel.HIGH)), authority=profile),
        request_for(action(), authority=AuthorityProfile(revision=1)),
        request_for(action(), authority=AuthorityProfile(revision=2, grants=(grant(revoked_at=NOW),))),
    )

    dispositions = []
    for case in cases:
        outcome = gate.evaluate(case)
        dispositions.append(outcome.disposition)
        assert outcome.feedback.original_request_digest == case.action.digest()
        assert outcome.feedback.why_changed
    assert set(dispositions) == set(GovernanceDisposition)


def test_reshaped_action_is_reauthorized_before_execution(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    original = request_for(action(risk=RiskProfile(blast_radius=RiskLevel.HIGH)), authority=profile)
    outcome = gate.evaluate(original)
    assert outcome.disposition is GovernanceDisposition.RESHAPE

    blocked = gate.authorize_execution(outcome)
    assert not blocked.allowed
    assert "재권한" in blocked.reason

    reauthorized = gate.reauthorize(outcome, original)
    assert reauthorized.parent_request_id == original.request_id
    assert reauthorized.admits_execution
    assert any("re-authorized" in change for change in reauthorized.feedback.what_changed)

    incomplete = gate.authorize_execution(reauthorized, satisfied_guards=(ReshapeGuard.ISOLATED_SCOPE,))
    assert not incomplete.allowed
    assert incomplete.missing_guards

    allowed = gate.authorize_execution(
        reauthorized,
        satisfied_guards=reauthorized.guards,
        action_digest=reauthorized.action_digest,
    )
    assert allowed.allowed

    unbound = gate.authorize_execution(reauthorized, satisfied_guards=reauthorized.guards)
    assert not unbound.allowed
    assert "digest" in unbound.reason

    changed_args = gate.authorize_execution(
        reauthorized,
        satisfied_guards=reauthorized.guards,
        action_digest=action(risk=RiskProfile(blast_radius=RiskLevel.HIGH)).digest(),
    )
    assert not changed_args.allowed
    assert "digest" in changed_args.reason


def test_widened_reshaped_action_is_denied_by_authority(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(scope="src"),))
    original = request_for(action(risk=RiskProfile(blast_radius=RiskLevel.HIGH)), authority=profile)
    outcome = gate.evaluate(original)

    widened = gate.reauthorize(outcome, original, action=action(resource_scope="infra/deploy.py"))
    assert widened.disposition is GovernanceDisposition.DENY
    assert widened.authority is not None
    assert widened.authority.verdict is AuthorityVerdict.SCOPE_OUT_OF_RANGE

    allowed = gate.reauthorize(outcome, original, action=action(resource_scope="src/nested/a.py"))
    assert allowed.disposition is GovernanceDisposition.APPROVE
    assert allowed.admits_execution


# ─── B. Risk Shaping·human-only boundary ─────────────────────────────


def test_reshape_plan_reduces_risk_without_touching_human_boundary() -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    gate = GovernanceGate(clock=lambda: NOW)
    reshape_target = action(
        risk=RiskProfile(
            blast_radius=RiskLevel.HIGH,
            verification=RiskLevel.HIGH,
            cost=RiskLevel.HIGH,
            security_privacy=RiskLevel.HIGH,
        )
    )
    outcome = gate.evaluate(request_for(reshape_target, authority=profile))

    assert outcome.disposition is GovernanceDisposition.RESHAPE
    assert set(outcome.guards) >= {
        ReshapeGuard.ISOLATED_SCOPE,
        ReshapeGuard.NARROWED_SCOPE,
        ReshapeGuard.VERIFICATION,
        ReshapeGuard.DIFF_INSPECTION,
        ReshapeGuard.BUDGET_LIMIT,
    }
    assert outcome.human_decision_required is False


@pytest.mark.parametrize("target_operation", ["change_human_ceiling", "grant_authority", "constitution_change"])
def test_human_only_operation_cannot_be_reshaped(gate: GovernanceGate, target_operation: str) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(operations=(target_operation,)),))
    risky = action(operation=target_operation, risk=RiskProfile(blast_radius=RiskLevel.HIGH))
    outcome = gate.evaluate(request_for(risky, authority=profile))

    assert outcome.disposition is GovernanceDisposition.DENY
    assert outcome.human_decision_required
    assert outcome.reshaped_action is None
    assert outcome.guards == ()


def test_constitutional_dimension_is_human_only_even_with_high_risk(gate: GovernanceGate) -> None:
    risky = action(dimension=AuthorityDimension.CONSTITUTIONAL, risk=RiskProfile(blast_radius=RiskLevel.SEVERE))
    outcome = gate.evaluate(request_for(risky))

    assert outcome.disposition is GovernanceDisposition.DENY
    assert outcome.human_decision_required
    assert "human-only" in outcome.reason


def test_human_only_operation_is_allowed_only_with_reusable_human_approval(gate: GovernanceGate) -> None:
    operation = "change_human_ceiling"
    profile = AuthorityProfile(revision=1, grants=(grant(operations=(operation,)),))
    target = action(operation=operation)
    approval = ApprovalUse(
        approval_id="approval:1",
        principal=SUBJECT,
        resource_scope="src/a.py",
        operation=operation,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        action_digest=target.digest(),
    )
    outcome = gate.evaluate(request_for(target, authority=profile, human_approval=approval))

    assert outcome.disposition is GovernanceDisposition.APPROVE


# ─── C. Unknown 처리 ─────────────────────────────────────────────────


def test_acceptable_unknown_does_not_block(gate: GovernanceGate) -> None:
    outcome = gate.evaluate(
        request_for(
            action(),
            unknowns=(UnknownAssessment(question="표현 차이", materiality=UnknownMateriality.ACCEPTABLE),),
        )
    )

    assert outcome.disposition is GovernanceDisposition.APPROVE
    assert outcome.admits_execution
    assert outcome.remaining_unknowns == ("표현 차이",)


def test_blocking_unknown_blocks_only_its_action(gate: GovernanceGate) -> None:
    blocking = UnknownAssessment(question="되돌릴 수 있는가", materiality=UnknownMateriality.BLOCKING)
    blocked = gate.evaluate(request_for(action(), unknowns=(blocking,)))
    other = gate.evaluate(request_for(action(tool="read_file", dimension=AuthorityDimension.TOOL_READ)))

    assert blocked.disposition is GovernanceDisposition.DENY
    assert blocked.blocked_unknowns == ("되돌릴 수 있는가",)
    assert "다른 action은 계속 진행할 수 있다" in blocked.limits
    assert other.disposition is GovernanceDisposition.APPROVE


def test_irrelevant_material_unknown_does_not_block_its_own_action(gate: GovernanceGate) -> None:
    unrelated = UnknownAssessment(
        question="다른 repo의 정책", materiality=UnknownMateriality.MATERIAL, affects_action=False
    )
    outcome = gate.evaluate(request_for(action(), unknowns=(unrelated,)))

    assert outcome.disposition is GovernanceDisposition.APPROVE_WITH_LIMITS
    assert outcome.admits_execution


# ─── D. 다차원 권한 ──────────────────────────────────────────────────


def test_dimension_grants_are_evaluated_independently() -> None:
    profile = AuthorityProfile(
        revision=1,
        grants=(grant(dimension=AuthorityDimension.TOOL_READ, scope="src", operations=("execute_tool",)),),
    )
    read = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT, dimension=AuthorityDimension.TOOL_READ, resource_scope="src/a.py", operation="execute_tool"
        ),
        now=NOW,
    )
    write = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT,
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/a.py",
            operation="execute_tool",
        ),
        now=NOW,
    )

    assert read.allowed and read.verdict is AuthorityVerdict.ALLOWED
    assert not write.allowed and write.verdict is AuthorityVerdict.NOT_GRANTED


def test_scope_expiry_and_revocation_are_distinct_verdicts() -> None:
    subject = SUBJECT
    profile = AuthorityProfile(
        revision=3,
        grants=(
            grant(scope="src", dimension=AuthorityDimension.TOOL_WRITE),
            grant(scope="infra", dimension=AuthorityDimension.EXTERNAL_ACTION, expires_at=NOW - timedelta(minutes=1)),
            grant(scope="docs", dimension=AuthorityDimension.TOOL_READ, revoked_at=NOW),
        ),
    )
    out_of_scope = profile.evaluate(
        AuthorityQuery(
            subject=subject,
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="other/a.py",
            operation="execute_tool",
        ),
        now=NOW,
    )
    expired = profile.evaluate(
        AuthorityQuery(
            subject=subject,
            dimension=AuthorityDimension.EXTERNAL_ACTION,
            resource_scope="infra/x",
            operation="execute_tool",
        ),
        now=NOW,
    )
    revoked = profile.evaluate(
        AuthorityQuery(
            subject=subject,
            dimension=AuthorityDimension.TOOL_READ,
            resource_scope="docs/a.md",
            operation="execute_tool",
        ),
        now=NOW,
    )

    assert out_of_scope.verdict is AuthorityVerdict.SCOPE_OUT_OF_RANGE
    assert expired.verdict is AuthorityVerdict.EXPIRED
    assert revoked.verdict is AuthorityVerdict.REVOKED


def test_operation_and_constraint_limits_are_enforced() -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(operations=("read_only",), constraints=("no_network",)),))
    not_allowed = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT, dimension=AuthorityDimension.TOOL_WRITE, resource_scope="src/a.py", operation="delete"
        ),
        now=NOW,
    )
    constraint_missing = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT,
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/a.py",
            operation="read_only",
            constraints=("no_network", "cost_cap"),
        ),
        now=NOW,
    )
    allowed = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT,
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/a.py",
            operation="read_only",
            constraints=("no_network",),
        ),
        now=NOW,
    )

    assert not_allowed.verdict is AuthorityVerdict.OPERATION_NOT_ALLOWED
    assert constraint_missing.verdict is AuthorityVerdict.CONSTRAINT_VIOLATED
    assert allowed.allowed
    assert allowed.limits == ("no_network",)


def test_delegation_must_be_a_strict_subset() -> None:
    parent = grant(
        scope="src", operations=("read_only", "write"), constraints=("no_network",), expires_at=NOW + timedelta(days=1)
    )
    profile = AuthorityProfile(revision=1, grants=(parent,))

    wider_scope = profile.delegate(
        DelegationRequest(
            parent_subject=SUBJECT,
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="infra",
            allowed_operations=("read_only",),
        ),
        now=NOW,
    )
    extra_operation = profile.delegate(
        DelegationRequest(
            parent_subject=SUBJECT,
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only", "deploy"),
        ),
        now=NOW,
    )
    dropped_constraint = profile.delegate(
        DelegationRequest(
            parent_subject=SUBJECT,
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only",),
        ),
        now=NOW,
    )
    subset = profile.delegate(
        DelegationRequest(
            parent_subject=SUBJECT,
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only",),
            constraints=("no_network",),
            expires_at=NOW + timedelta(hours=1),
        ),
        now=NOW,
    )

    assert wider_scope.verdict is AuthorityVerdict.DELEGATION_NOT_SUBSET
    assert extra_operation.verdict is AuthorityVerdict.DELEGATION_NOT_SUBSET
    assert dropped_constraint.verdict is AuthorityVerdict.DELEGATION_NOT_SUBSET
    assert subset.ok and subset.grant is not None
    assert subset.grant.granted_by == SUBJECT


def test_revocation_propagates_to_delegated_child_and_keeps_original() -> None:
    child = grant(subject="agent:child", scope="src/sub", granted_by=SUBJECT)
    original = AuthorityProfile(revision=1, grants=(grant(scope="src"), child))
    revoked = original.revoke(
        RevocationRequest(subject=SUBJECT, revoked_at=NOW + timedelta(minutes=5), revision=2, reason="권한 회수")
    )

    assert original.grants[0].revoked_at is None
    assert revoked.grants[0].revoked_at is not None
    assert revoked.grants[1].revoked_at is not None
    assert revoked.revision == 2


def test_approval_reuse_requires_same_principal_scope_operation_and_validity() -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(scope="src/sub", operations=("execute_tool",)),))
    query = AuthorityQuery(
        subject=SUBJECT,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/sub/b.py",
        operation="execute_tool",
    )
    digest = "sha256:" + ("ab" * 32)
    reusable = ApprovalUse(
        approval_id="approval:1",
        principal=SUBJECT,
        resource_scope="src",
        operation="execute_tool",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        action_digest=digest,
    )
    mismatches = (
        replace(reusable, principal="agent:other"),
        replace(reusable, resource_scope="docs"),
        replace(reusable, operation="delete"),
        replace(reusable, expires_at=NOW - timedelta(minutes=1)),
    )

    assert profile.reuse_approval(reusable, query, now=NOW, action_digest=digest).verdict is ApprovalReuseVerdict.REUSED
    assert [profile.reuse_approval(item, query, now=NOW, action_digest=digest).reusable for item in mismatches] == [
        False
    ] * 4
    assert (
        profile.reuse_approval(reusable, query, now=NOW, action_digest="").verdict
        is ApprovalReuseVerdict.DIGEST_MISMATCH
    )
    assert (
        profile.reuse_approval(replace(reusable, action_digest=""), query, now=NOW, action_digest=digest).verdict
        is ApprovalReuseVerdict.DIGEST_MISMATCH
    )


def test_no_single_autonomy_score_exists() -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    view = profile.dimension_view(SUBJECT, resource_scope="src/a.py", operation="execute_tool", now=NOW)
    decision_fields = set(AuthorityProfile.__dataclass_fields__) | set(
        profile.evaluate(
            AuthorityQuery(
                subject=SUBJECT,
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src/a.py",
                operation="execute_tool",
            ),
            now=NOW,
        ).__dataclass_fields__
    )

    assert "score" not in decision_fields
    assert not any("score" in field for field in decision_fields)
    assert set(view) == set(AuthorityDimension)
    assert all(isinstance(verdict, AuthorityVerdict) for verdict in view.values())


def test_non_human_actor_cannot_issue_grants_or_raise_ceiling() -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))

    with pytest.raises(AuthorityViolation):
        profile.issue_grant(grant(subject="learned:policy"), actor_kind=ProducerKind.BRAIN)

    proposal = profile.propose_ceiling_change(
        subject="learned:policy",
        dimension=AuthorityDimension.TOOL_WRITE,
        requested_scope="infra",
        reason="성공률 개선",
    )
    assert proposal.human_decision_required
    assert not proposal.allowed


def test_body_does_not_deny_because_it_disagrees_with_brain_conclusion(gate: GovernanceGate) -> None:
    profile = AuthorityProfile(revision=1, grants=(grant(),))
    neutral = gate.evaluate(request_for(action(), authority=profile))
    dissenting = gate.evaluate(
        request_for(
            action(),
            authority=profile,
            advisory=("이 action은 틀렸다", "다른 결론이 더 옳다", "Body는 이 판단에 동의하지 않는다"),
        )
    )

    assert neutral.disposition is dissenting.disposition
    assert neutral.limits == dissenting.limits
    assert neutral.semantic_review_performed is False

    with pytest.raises(GovernanceError):
        replace(neutral, semantic_review_performed=True)


def test_feedback_missing_original_digest_is_rejected() -> None:
    digest = action().digest()
    with pytest.raises(GovernanceError):
        GovernanceOutcome(
            request_id="req-1",
            action_digest=digest,
            disposition=GovernanceDisposition.APPROVE,
            reason="ok",
            feedback=GovernanceFeedback(original_request_digest="sha256:" + "0" * 64),
        )


# ─── tool_executor 실제 표면 ─────────────────────────────────────────


class _WriteTool(BaseTool):
    """통합 시험용 실제 파일 쓰기 도구."""

    risk_level = ToolRiskLevel.LOW

    @property
    def name(self) -> str:
        return "fake_write"

    @property
    def description(self) -> str:
        return "test-only file writer"

    @property
    def parameters_schema(self) -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    def execute(self, **kwargs: object) -> object:
        path = Path(str(kwargs["file_path"]))
        path.write_text(str(kwargs.get("content", "")), encoding="utf-8")
        return f"wrote {path.name}"


class _RecordingAdapter:
    """ToolExecutor가 보는 표면을 그대로 노출하면서 판정을 기록한다."""

    def __init__(self, adapter: ToolGovernanceAdapter) -> None:
        self.adapter = adapter
        self.outcomes: list[GovernanceOutcome] = []

    def admit(
        self, tool_name: str, args: Mapping[str, object], *, execution_mode: str = "interactive"
    ) -> GovernanceOutcome:
        outcome = self.adapter.admit(tool_name, args, execution_mode=execution_mode)
        self.outcomes.append(outcome)
        return outcome


def _executor(tmp_path: Path, registry: ToolRegistry) -> ToolExecutor:
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        executor = ToolExecutor(
            tool_registry=registry,
            permission_gate=registry.permission_gate,
            project_root=str(tmp_path),
        )
    setattr(executor, "_immune_system", None)
    return executor


def _tool_registry(tmp_path: Path) -> ToolRegistry:
    registry = ToolRegistry(project_root=str(tmp_path))
    getattr(registry, "install")(_WriteTool())
    return registry


def test_tool_executor_runs_approved_tool_and_blocks_revoked_grant(tmp_path: Path) -> None:
    registry = _tool_registry(tmp_path)
    executor = _executor(tmp_path, registry)
    target = tmp_path / "out.txt"
    allowed_profile = AuthorityProfile(revision=1, grants=(grant(scope=str(tmp_path), operations=("execute_tool",)),))
    adapter = _RecordingAdapter(
        ToolGovernanceAdapter(
            gate=GovernanceGate(clock=lambda: NOW),
            subject=SUBJECT,
            project_id="project:ssak-ai",
            authority=allowed_profile,
        )
    )
    executor.set_governance_gate(adapter)

    result = executor.execute("fake_write", {"file_path": str(target), "content": "governed"})

    assert target.read_text(encoding="utf-8") == "governed"
    assert "wrote out.txt" in result
    assert adapter.outcomes[0].disposition is GovernanceDisposition.APPROVE

    revoked = AuthorityProfile(revision=2, grants=(grant(scope=str(tmp_path), revoked_at=NOW),))
    blocked_target = tmp_path / "blocked.txt"
    blocked_adapter = _RecordingAdapter(
        ToolGovernanceAdapter(
            gate=GovernanceGate(clock=lambda: NOW),
            subject=SUBJECT,
            project_id="project:ssak-ai",
            authority=revoked,
        )
    )
    executor.set_governance_gate(blocked_adapter)

    blocked_result = executor.execute("fake_write", {"file_path": str(blocked_target), "content": "no"})

    assert "[GOVERNANCE DENY]" in blocked_result
    assert not blocked_target.exists()


def _adapter_globals() -> dict[str, object]:
    """adapter의 `admit`이 실제로 읽는 module namespace.

    다른 시험 파일이 import 시점에 `sys.modules`에서 `antigravity_k.*`를 지우면 같은 이름의 module이
    두 번 만들어지고, 이 시험 module은 옛 객체를 참조하게 된다. 경로 문자열이나 `sys.modules` 조회로
    patch하면 새 객체가 바뀌고 옛 객체를 참조하는 adapter는 바뀌지 않는다. 함수의 `__globals__`는
    그 함수가 속한 module의 dict이므로 중복 여부와 무관하게 정확하다.
    """

    globals_map = ToolGovernanceAdapter.admit.__globals__
    assert "risk_profile_for" in globals_map
    return globals_map


def test_tool_executor_requires_guard_receipts_for_reshaped_call(tmp_path: Path) -> None:
    registry = _tool_registry(tmp_path)
    executor = _executor(tmp_path, registry)
    profile = AuthorityProfile(revision=1, grants=(grant(scope=str(tmp_path), operations=("execute_tool",)),))
    target = tmp_path / "wide.txt"

    without_guards = _RecordingAdapter(
        ToolGovernanceAdapter(
            gate=GovernanceGate(clock=lambda: NOW),
            subject=SUBJECT,
            project_id="project:ssak-ai",
            authority=profile,
        )
    )
    executor.set_governance_gate(without_guards)
    raised_risk = RiskProfile(blast_radius=RiskLevel.HIGH, data_state_loss=RiskLevel.HIGH)
    with patch.dict(_adapter_globals(), {"risk_profile_for": lambda _name: raised_risk}):
        blocked_result = executor.execute("fake_write", {"file_path": str(target), "content": "wide"})

    assert blocked_result.count("[GOVERNANCE") == 1
    assert not target.exists()
    assert without_guards.outcomes[0].disposition is GovernanceDisposition.RESHAPE

    satisfied: list[ReshapeGuard] = []
    with patch.dict(_adapter_globals(), {"risk_profile_for": lambda _name: raised_risk}):
        guarded = _RecordingAdapter(
            ToolGovernanceAdapter(
                gate=GovernanceGate(clock=lambda: NOW),
                subject=SUBJECT,
                project_id="project:ssak-ai",
                authority=profile,
                guard_runner=lambda outcome: satisfied.extend(outcome.guards) or outcome.guards,
            )
        )
        executor.set_governance_gate(guarded)
        allowed_result = executor.execute("fake_write", {"file_path": str(target), "content": "guarded"})

    assert "wrote wide.txt" in allowed_result
    assert target.read_text(encoding="utf-8") == "guarded"
    assert set(satisfied) >= {ReshapeGuard.CHECKPOINT, ReshapeGuard.ISOLATED_SCOPE}
    assert guarded.outcomes[0].parent_request_id == "tool:fake_write"
    assert guarded.outcomes[0].admits_execution


def test_dimension_equality_survives_a_duplicate_enum_class(tmp_path: Path) -> None:
    """같은 이름·같은 값의 enum이 프로세스 안에 두 번 로드돼도 grant가 매칭되어야 한다.

    실제로 전체 suite collection 문맥에서 `AuthorityDimension` class 객체가 두 개 생기고,
    identity(`is`) 비교 때 RESHAPE 대신 NOT_GRANTED→DEFER가 나왔다. 권한 판정은 identity가
    아니라 dimension 값으로 결정되어야 한다(재로드·중복 import는 권한 부족이 아니다).
    """

    import importlib.util

    import antigravity_k.engine.cognitive.models as models

    # 실제 상황과 같게 **같은 module 이름**으로 한 번 더 실행한다(sys.modules에 넣지 않는다).
    # 그래야 class의 __module__은 같고 객체만 다른 상태가 재현된다.
    spec = importlib.util.spec_from_file_location(models.__name__, Path(models.__file__))
    assert spec is not None and spec.loader is not None
    duplicate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(duplicate)
    assert duplicate.AuthorityDimension is not AuthorityDimension, "전제: 서로 다른 class 객체"
    assert duplicate.AuthorityDimension.__module__ == AuthorityDimension.__module__
    assert duplicate.AuthorityDimension.TOOL_WRITE == AuthorityDimension.TOOL_WRITE

    target = tmp_path / "wide.txt"
    profile = AuthorityProfile(
        revision=1,
        grants=(grant(scope=str(tmp_path)).model_copy(update={"dimension": duplicate.AuthorityDimension.TOOL_WRITE}),),
    )
    decision = profile.evaluate(
        AuthorityQuery(
            subject=SUBJECT,
            dimension=classify_tool_dimension("fake_write"),
            resource_scope=str(target),
            operation="execute_tool",
        ),
        now=NOW,
    )

    assert decision.allowed is True
    assert decision.verdict is AuthorityVerdict.ALLOWED


def test_tool_dimension_and_risk_classification() -> None:
    assert classify_tool_dimension("read_file") is AuthorityDimension.TOOL_READ
    assert classify_tool_dimension("write_file") is AuthorityDimension.TOOL_WRITE
    assert risk_profile_for("delete_file").data_state_loss is RiskLevel.HIGH
    assert risk_profile_for("read_file").blast_radius is RiskLevel.LOW


def test_execution_authorization_reports_missing_guards() -> None:
    digest = action().digest()
    outcome = GovernanceOutcome(
        request_id="req-1",
        action_digest=digest,
        disposition=GovernanceDisposition.RESHAPE,
        reason="guarded",
        feedback=GovernanceFeedback(original_request_digest=digest, why_changed="guarded"),
        guards=(ReshapeGuard.CHECKPOINT,),
        reshaped_action=action(guard_obligations=(ReshapeGuard.CHECKPOINT,)),
        reauthorization_required=True,
    )
    authorization = GovernanceGate(clock=lambda: NOW).authorize_execution(outcome)

    assert isinstance(authorization, ExecutionAuthorization)
    assert not authorization.allowed
