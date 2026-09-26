"""R02: 위임 만료 상속, 후손 revoke 전파, 승인 action digest 결박."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from antigravity_k.engine.cognitive.authority import (
    ApprovalReuseVerdict,
    ApprovalUse,
    AuthorityDimension,
    AuthorityProfile,
    AuthorityQuery,
    AuthorityVerdict,
    DelegationRequest,
    RevocationRequest,
)
from antigravity_k.engine.cognitive.governance import (
    GovernanceDisposition,
    GovernanceGate,
    GovernanceRequest,
    RequestedAction,
    RiskLevel,
    RiskProfile,
)
from antigravity_k.engine.cognitive.models import AuthorityGrant

NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
PARENT_EXP = NOW + timedelta(hours=2)


def _grant(
    *,
    subject: str,
    scope: str,
    granted_by: str,
    expires_at: datetime | None = PARENT_EXP,
    operations: tuple[str, ...] = ("execute_tool", "read_only"),
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE,
    constraints: tuple[str, ...] = ("no_network",),
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
        revision=1,
    )


def test_r02_a1_omitted_child_expiry_inherits_parent_ceiling() -> None:
    parent = _grant(subject="agent:root", scope="src", granted_by="human:mr.k")
    profile = AuthorityProfile(revision=1, grants=(parent,))
    outcome = profile.delegate(
        DelegationRequest(
            parent_subject="agent:root",
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only",),
            constraints=("no_network",),
            expires_at=None,
            revision=2,
        ),
        now=NOW,
    )
    assert outcome.ok and outcome.grant is not None
    assert outcome.grant.expires_at == PARENT_EXP

    earlier = PARENT_EXP - timedelta(minutes=30)
    early = profile.delegate(
        DelegationRequest(
            parent_subject="agent:root",
            child_subject="agent:early",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only",),
            constraints=("no_network",),
            expires_at=earlier,
            revision=2,
        ),
        now=NOW,
    )
    assert early.ok and early.grant is not None
    assert early.grant.expires_at == earlier

    # 부모 만료 시각 이후: 상속된 자식도 거절
    with_child = AuthorityProfile(revision=2, grants=(parent, outcome.grant))
    after = (
        profile.evaluate(
            AuthorityQuery(
                subject="agent:child",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src/sub/a.py",
                operation="read_only",
            ),
            now=PARENT_EXP + timedelta(seconds=1),
        )
        if False
        else with_child.evaluate(
            AuthorityQuery(
                subject="agent:child",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src/sub/a.py",
                operation="read_only",
            ),
            now=PARENT_EXP + timedelta(seconds=1),
        )
    )
    assert after.allowed is False
    assert after.verdict is AuthorityVerdict.EXPIRED

    # 레거시: 자식 expires=None 이어도 부모 만료면 조상 검사로 거절
    legacy_child = _grant(
        subject="agent:legacy",
        scope="src/sub",
        granted_by="agent:root",
        expires_at=None,
    )
    legacy_profile = AuthorityProfile(revision=3, grants=(parent, legacy_child))
    legacy_after = legacy_profile.evaluate(
        AuthorityQuery(
            subject="agent:legacy",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub/a.py",
            operation="read_only",
        ),
        now=PARENT_EXP + timedelta(seconds=1),
    )
    assert legacy_after.allowed is False
    assert legacy_after.verdict in {AuthorityVerdict.EXPIRED, AuthorityVerdict.REVOKED}


def test_r02_a2_transitive_revoke_keeps_independent_grant() -> None:
    root = _grant(subject="agent:root", scope="src", granted_by="human:mr.k")
    mid = _grant(subject="agent:mid", scope="src/a", granted_by="agent:root")
    leaf = _grant(subject="agent:leaf", scope="src/a/b", granted_by="agent:mid")
    independent = _grant(subject="agent:other", scope="docs", granted_by="human:mr.k")
    profile = AuthorityProfile(revision=1, grants=(root, mid, leaf, independent))
    revoked = profile.revoke(
        RevocationRequest(subject="agent:root", revoked_at=NOW + timedelta(minutes=1), revision=2, reason="root cut")
    )
    by_subject = {g.subject: g for g in revoked.grants}
    assert by_subject["agent:root"].revoked_at is not None
    assert by_subject["agent:mid"].revoked_at is not None
    assert by_subject["agent:leaf"].revoked_at is not None
    assert by_subject["agent:other"].revoked_at is None

    leaf_decision = revoked.evaluate(
        AuthorityQuery(
            subject="agent:leaf",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/a/b/x.py",
            operation="read_only",
        ),
        now=NOW,
    )
    other_decision = revoked.evaluate(
        AuthorityQuery(
            subject="agent:other",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="docs/readme.md",
            operation="read_only",
        ),
        now=NOW,
    )
    assert leaf_decision.allowed is False
    assert leaf_decision.verdict is AuthorityVerdict.REVOKED
    assert other_decision.allowed is True


def test_r02_a3_governance_digest_mismatch_is_not_approve() -> None:
    gate = GovernanceGate(clock=lambda: NOW)
    human_action = RequestedAction(
        tool="authority",
        operation="grant_authority",
        dimension=AuthorityDimension.CONSTITUTIONAL,
        resource_scope="project:ssak",
        arguments={"subject": "agent:x", "scope": "src"},
        risk=RiskProfile(
            reversibility=RiskLevel.HIGH,
            blast_radius=RiskLevel.HIGH,
            data_state_loss=RiskLevel.HIGH,
            external_impact=RiskLevel.LOW,
            security_privacy=RiskLevel.HIGH,
            verification=RiskLevel.HIGH,
            rollback=RiskLevel.HIGH,
            cost=RiskLevel.LOW,
            goal_premise_impact=RiskLevel.HIGH,
            authority_sensitivity=RiskLevel.HIGH,
        ),
    )
    wrong = ApprovalUse(
        approval_id="approval:1",
        principal="human:mr.k",
        resource_scope="project:ssak",
        operation="grant_authority",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        action_digest="deadbeef" * 8,
    )
    outcome = gate.evaluate(
        GovernanceRequest(
            request_id="req-r02-a3",
            project_id="project:ssak",
            subject="human:mr.k",
            action=human_action,
            authority=AuthorityProfile(revision=1, grants=()),
            human_approval=wrong,
            state_revision=1,
        )
    )
    assert outcome.disposition is not GovernanceDisposition.APPROVE
    assert outcome.human_decision_required or outcome.disposition is GovernanceDisposition.DENY


def test_r02_a4_valid_subset_and_matching_digest_succeed() -> None:
    parent = _grant(subject="agent:root", scope="src", granted_by="human:mr.k")
    profile = AuthorityProfile(revision=1, grants=(parent,))
    subset = profile.delegate(
        DelegationRequest(
            parent_subject="agent:root",
            child_subject="agent:child",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub",
            allowed_operations=("read_only",),
            constraints=("no_network",),
            expires_at=PARENT_EXP - timedelta(minutes=5),
            revision=2,
        ),
        now=NOW,
    )
    assert subset.ok and subset.grant is not None

    action = RequestedAction(
        tool="write_file",
        operation="execute_tool",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/sub/a.py",
        arguments={"file_path": "src/sub/a.py"},
        risk=RiskProfile(
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
        ),
    )
    digest = action.digest()
    reuse = profile.reuse_approval(
        ApprovalUse(
            approval_id="approval:ok",
            principal="agent:root",
            resource_scope="src",
            operation="execute_tool",
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            action_digest=digest,
        ),
        AuthorityQuery(
            subject="agent:root",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub/a.py",
            operation="execute_tool",
        ),
        now=NOW,
        action_digest=digest,
    )
    assert reuse.verdict is ApprovalReuseVerdict.REUSED
    mismatch = profile.reuse_approval(
        ApprovalUse(
            approval_id="approval:bad",
            principal="agent:root",
            resource_scope="src",
            operation="execute_tool",
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            action_digest="00" * 32,
        ),
        AuthorityQuery(
            subject="agent:root",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="src/sub/a.py",
            operation="execute_tool",
        ),
        now=NOW,
        action_digest=digest,
    )
    assert mismatch.verdict is ApprovalReuseVerdict.DIGEST_MISMATCH
