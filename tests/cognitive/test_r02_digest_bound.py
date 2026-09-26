"""R02 residual: digest binding required on reuse_approval and authorize_execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from antigravity_k.engine.cognitive.authority import (
    ApprovalReuseVerdict,
    ApprovalUse,
    AuthorityDimension,
    AuthorityProfile,
    AuthorityQuery,
)
from antigravity_k.engine.cognitive.governance import (
    GovernanceGate,
    GovernanceRequest,
    RequestedAction,
    RiskLevel,
    RiskProfile,
)
from antigravity_k.engine.cognitive.models import AuthorityGrant

NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
SUBJECT = "agent:root"
DIGEST = "sha256:" + ("cd" * 32)


def _low_risk() -> RiskProfile:
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


def _grant(*, scope: str = "src") -> AuthorityGrant:
    return AuthorityGrant(
        subject=SUBJECT,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope=scope,
        allowed_operations=("execute_tool",),
        constraints=("no_network",),
        granted_by="human:owner",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=2),
        revision=1,
    )


def test_r02_reuse_approval_rejects_missing_digest() -> None:
    profile = AuthorityProfile(revision=1, grants=(_grant(),))
    query = AuthorityQuery(
        subject=SUBJECT,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/a.py",
        operation="execute_tool",
    )
    approval = ApprovalUse(
        approval_id="a1",
        principal=SUBJECT,
        resource_scope="src",
        operation="execute_tool",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        action_digest=DIGEST,
    )
    assert profile.reuse_approval(approval, query, now=NOW).verdict is ApprovalReuseVerdict.DIGEST_MISMATCH
    assert (
        profile.reuse_approval(approval, query, now=NOW, action_digest="").verdict
        is ApprovalReuseVerdict.DIGEST_MISMATCH
    )
    ok = profile.reuse_approval(approval, query, now=NOW, action_digest=DIGEST)
    assert ok.verdict is ApprovalReuseVerdict.REUSED


def test_r02_authorize_execution_requires_digest() -> None:
    profile = AuthorityProfile(revision=1, grants=(_grant(),))
    gate = GovernanceGate(clock=lambda: NOW)
    action = RequestedAction(
        tool="write_file",
        operation="execute_tool",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/a.py",
        arguments={"file_path": "src/a.py", "content": "x"},
        risk=_low_risk(),
        reversible=True,
    )
    outcome = gate.evaluate(
        GovernanceRequest(
            request_id="req:1",
            project_id="p",
            subject=SUBJECT,
            action=action,
            authority=profile,
        )
    )
    assert outcome.admits_execution
    unbound = gate.authorize_execution(outcome, satisfied_guards=outcome.guards)
    assert not unbound.allowed
    assert "digest" in unbound.reason
    bound = gate.authorize_execution(
        outcome,
        satisfied_guards=outcome.guards,
        action_digest=outcome.action_digest,
    )
    assert bound.allowed
    mismatched = gate.authorize_execution(
        outcome,
        satisfied_guards=outcome.guards,
        action_digest=DIGEST,
    )
    assert not mismatched.allowed
