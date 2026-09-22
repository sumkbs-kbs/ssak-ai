"""T06 — COMMIT readiness와 Decision lifecycle 시험 (P06).

검증 범위(T06-A~D):
- A: provider/의미 판단을 호출하지 않고, readiness 입력이 같고 의미 결론만 다른 fixture에서 결과가 바뀌지 않는다.
- B: READY/READY_WITH_GUARDS/NOT_READY, check별 PASS/FAIL/UNKNOWN/N_A와 이유, ACCEPTABLE Unknown 단독으로 NOT_READY 아님.
- C: guard는 executor receipt가 있어야 하고, 문자열 rollback 약속은 통과하지 못한다. freshness 재확인.
- D: material trigger·smallest scope로만 reopen하고, 원래 DecisionTrace digest는 불변이다.

주의: COMMIT은 cognitive gate이며 ``git commit``과 무관하다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from antigravity_k.engine.cognitive.authority import (
    AuthorityDecision,
    AuthorityGrant,
    AuthorityProfile,
    AuthorityVerdict,
)
from antigravity_k.engine.cognitive.decisions import (
    DecisionLedger,
    DecisionLifecycleError,
    DecisionTrace,
    ReopenRefused,
    ReopenRequest,
)
from antigravity_k.engine.cognitive.governance import (
    GovernanceGate,
    GovernanceRequest,
    RequestedAction,
    ReshapeGuard,
    UnknownAssessment,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    CheckStatus,
    ClosureState,
    DecisionPayload,
    EntityType,
    GovernanceDisposition,
    Producer,
    ProducerKind,
    ReadinessCheck,
    ReadinessVerdict,
    Record,
    ReopenTrigger,
    RiskLevel,
    RiskProfile,
    UnknownMateriality,
)
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    FreshnessBinding,
    GuardReceipt,
    HardConstraint,
    ReadinessError,
    ReadinessGate,
    ReadinessInputs,
    RollbackPlan,
    StaleReadinessError,
    UnknownDisposition,
    VerificationRequirement,
    check_readiness,
)
from antigravity_k.engine.cognitive.references import new_id
from antigravity_k.engine.cognitive.store import CanonicalStore

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
DECISION_ID = new_id(EntityType.DECISION)
NEW_DECISION_ID = new_id(EntityType.DECISION)
THIRD_DECISION_ID = new_id(EntityType.DECISION)
EVIDENCE_ID = new_id(EntityType.EVIDENCE)
SECOND_EVIDENCE_ID = new_id(EntityType.EVIDENCE)
THIRD_EVIDENCE_ID = new_id(EntityType.EVIDENCE)


class _ForbiddenJudge:
    """호출되면 실패하는 semantic judge — readiness가 절대 부르지 않아야 한다."""

    def __init__(self) -> None:
        self.calls = 0

    def review(self, question: str, payload: object) -> object:
        self.calls += 1
        raise AssertionError("readiness gate는 semantic judge를 호출할 수 없다")


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


SUBJECT = "body:runtime"


def authority_grant(*, revoked_at: datetime | None = None) -> AuthorityGrant:
    return AuthorityGrant(
        subject=SUBJECT,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src",
        allowed_operations=("execute_tool",),
        constraints=(),
        granted_by="human:mr.k",
        issued_at=NOW,
        expires_at=None,
        revision=1,
        revoked_at=revoked_at,
    )


def governance_unknown() -> UnknownAssessment:
    return UnknownAssessment(
        question="L2 범위가 충분한가",
        materiality=UnknownMateriality.MATERIAL,
        affects_action=False,
    )


def governance_action() -> RequestedAction:
    return RequestedAction(
        tool="write_file",
        operation="execute_tool",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/a.py",
        arguments={"file_path": "src/a.py"},
        risk=low_risk(),
    )


def allowed_authority(*, revision: int = 1) -> AuthorityDecision:
    return AuthorityDecision(
        allowed=True,
        verdict=AuthorityVerdict.ALLOWED,
        reason="grant가 요청을 포함한다",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/a.py",
        profile_revision=revision,
        limits=("no_network",),
    )


def action(*, digest: str = DIGEST, scope: str = "src/a.py") -> ActionScope:
    return ActionScope(
        tool="write_file",
        scope=scope,
        expected_outcome="T06 통과",
        action_digest=digest,
    )


def ready_inputs(**overrides: object) -> ReadinessInputs:
    base: dict[str, object] = {
        "action": action(),
        "authorized_action_digest": DIGEST,
        "decision_revision": 1,
        "state_revision": 4,
        "authority_revision": 1,
        "policy_version": "policy/v1",
        "grounds": (EVIDENCE_ID,),
        "evidence_refs": (
            EvidenceRef(
                evidence_id=EVIDENCE_ID,
                provenance_uri="tests/cognitive/test_readiness.py",
                provenance_digest="sha256:" + "b" * 64,
                observed_at=NOW,
            ),
        ),
        "constraints": (HardConstraint(name="no_network", satisfied=True),),
        "risk": low_risk(),
        "authority_decision": allowed_authority(),
    }
    base.update(overrides)
    return ReadinessInputs(**base)  # type: ignore[arg-type]


def trace(*, digest: str = DIGEST) -> DecisionTrace:
    return DecisionTrace(
        decision_id=DECISION_ID,
        project_id="project:ssak-ai",
        decision_revision=1,
        selected_action="write_file(src/a.py)",
        why_selected="ground가 있고 risk가 낮다",
        expected_outcome="T06 통과",
        action_digest=digest,
        grounds=(EVIDENCE_ID,),
        evidence_ids=(EVIDENCE_ID,),
        alternatives=("read_only 검토",),
        why_not_selected=("추가 cognition 가치가 낮다",),
        risks={"blast_radius": "LOW"},
        authority_revision=1,
        state_revision=4,
        policy_version="policy/v1",
        reopen_triggers=(ReopenTrigger.NEW_MATERIAL_EVIDENCE,),
    )


# ─── A. 의미 재심사 금지 ─────────────────────────────────────────────


def test_semantic_judge_is_never_called_and_gate_still_succeeds() -> None:
    judge = _ForbiddenJudge()
    gate = ReadinessGate(semantic_judge=judge)

    result = gate.check(ready_inputs())

    assert judge.calls == 0
    assert result.verdict is ReadinessVerdict.READY
    assert result.semantic_review_performed is False


def test_same_structural_inputs_ignore_semantic_conclusion_text() -> None:
    neutral = check_readiness(ready_inputs())
    dissenting = check_readiness(
        ready_inputs(
            advisory_notes=(
                "이 결론은 틀렸다",
                "다른 대안이 더 옳다",
                "Body는 이 판단을 승인하지 않는다",
            )
        )
    )

    assert neutral.verdict is dissenting.verdict
    assert [check.status for check in neutral.checks] == [check.status for check in dissenting.checks]
    assert neutral.freshness.digest() == dissenting.freshness.digest()


def test_structural_changes_do_change_readiness() -> None:
    baseline = check_readiness(ready_inputs())
    changed_action = check_readiness(ready_inputs(action=action(scope=""), authorized_action_digest=DIGEST))
    changed_constraints = check_readiness(
        ready_inputs(constraints=(HardConstraint(name="no_network", satisfied=False),))
    )
    changed_evidence = check_readiness(ready_inputs(evidence_refs=()))
    changed_authority = check_readiness(ready_inputs(authority_decision=None))

    assert baseline.verdict is ReadinessVerdict.READY
    assert changed_action.verdict is ReadinessVerdict.NOT_READY
    assert changed_constraints.verdict is ReadinessVerdict.NOT_READY
    assert changed_evidence.verdict is ReadinessVerdict.NOT_READY
    assert changed_authority.verdict is ReadinessVerdict.NOT_READY


def test_modified_args_after_authorization_fail_the_scope_check() -> None:
    changed = check_readiness(ready_inputs(action=action(digest="sha256:" + "f" * 64), authorized_action_digest=DIGEST))
    scope_check = changed.check_result(ReadinessCheck.ACTION_SCOPE_CLEAR)

    assert scope_check.status is CheckStatus.FAIL
    assert "재승인" in scope_check.reason


def test_semantic_review_flag_is_rejected() -> None:
    with pytest.raises(ReadinessError):
        replace(check_readiness(ready_inputs()), semantic_review_performed=True)


# ─── B. verdict·check 상태 ───────────────────────────────────────────


def test_all_nine_checks_are_reported_with_reasons() -> None:
    result = check_readiness(ready_inputs())

    assert len(result.checks) == 9
    assert {check.check for check in result.checks} == set(ReadinessCheck)
    assert all(check.reason for check in result.checks)
    assert result.check_result(ReadinessCheck.VERIFICATION_SUFFICIENT).status is CheckStatus.N_A
    assert "선언되지 않았다" in result.check_result(ReadinessCheck.VERIFICATION_SUFFICIENT).reason


def test_ready_with_guards_when_receipts_or_limits_exist() -> None:
    result = check_readiness(
        ready_inputs(
            guard_receipts=(
                GuardReceipt(
                    guard=ReshapeGuard.CHECKPOINT, enforced_by="tool_executor", receipt_digest="sha256:" + "c" * 64
                ),
            ),
        )
    )

    assert result.verdict is ReadinessVerdict.READY_WITH_GUARDS
    assert result.ok


def test_acceptable_unknown_alone_does_not_block() -> None:
    result = check_readiness(
        ready_inputs(
            unknowns=(
                UnknownDisposition(
                    question="표현 차이",
                    materiality=UnknownMateriality.ACCEPTABLE,
                    disposition="ACCEPT",
                    reason="action을 바꾸지 않는다",
                ),
            )
        )
    )

    assert result.verdict is ReadinessVerdict.READY
    assert result.check_result(ReadinessCheck.MATERIAL_UNKNOWN_EXPLICIT).status is CheckStatus.PASS


def test_blocking_unknown_returns_not_ready_with_conditions() -> None:
    result = check_readiness(
        ready_inputs(
            unknowns=(
                UnknownDisposition(
                    question="되돌릴 수 있는가",
                    materiality=UnknownMateriality.BLOCKING,
                    disposition="OPEN",
                    reason="아직 모른다",
                ),
            )
        )
    )

    assert result.verdict is ReadinessVerdict.NOT_READY
    assert result.blocking_conditions
    assert result.needs_primary_judgment is False
    assert "BLOCKING unknown" in result.blocking_conditions[0]


def test_semantic_uncertainty_returns_to_primary_as_unknown() -> None:
    result = check_readiness(
        ready_inputs(
            constraints=(
                HardConstraint(name="no_network", satisfied=True),
                HardConstraint(name="tone_matches_project", satisfied=True, machine_checkable=False),
            )
        )
    )

    assert result.verdict is ReadinessVerdict.NOT_READY
    assert result.needs_primary_judgment
    assert result.check_result(ReadinessCheck.HARD_CONSTRAINTS_SATISFIED).status is CheckStatus.UNKNOWN

    attested = check_readiness(
        ready_inputs(
            constraints=(
                HardConstraint(
                    name="tone_matches_project",
                    satisfied=True,
                    machine_checkable=False,
                    human_attestation="human:mr.k",
                ),
            )
        )
    )
    assert attested.verdict is ReadinessVerdict.READY


def test_not_ready_requires_blocking_conditions() -> None:
    result = check_readiness(ready_inputs(authority_decision=None))
    with pytest.raises(ReadinessError):
        replace(result, blocking_conditions=())


# ─── C. guard·rollback·freshness ────────────────────────────────────


def test_string_only_guard_is_not_a_receipt() -> None:
    result = check_readiness(
        ready_inputs(
            risk=RiskProfile(blast_radius=RiskLevel.HIGH),
            guard_receipts=(
                GuardReceipt(
                    guard=ReshapeGuard.ISOLATED_SCOPE,
                    enforced_by="",
                    receipt_digest="",
                    enforced=False,
                ),
            ),
        )
    )
    risk_check = result.check_result(ReadinessCheck.RESIDUAL_RISK_MANAGEABLE)

    assert risk_check.status is CheckStatus.FAIL
    assert result.verdict is ReadinessVerdict.NOT_READY


def test_elevated_risk_is_manageable_with_receipt_or_acceptance() -> None:
    with_receipt = check_readiness(
        ready_inputs(
            risk=RiskProfile(blast_radius=RiskLevel.HIGH),
            guard_receipts=(
                GuardReceipt(
                    guard=ReshapeGuard.NARROWED_SCOPE,
                    enforced_by="tool_executor",
                    receipt_digest="sha256:" + "d" * 64,
                ),
            ),
        )
    )
    with_acceptance = check_readiness(
        ready_inputs(
            risk=RiskProfile(blast_radius=RiskLevel.HIGH),
            risk_acceptances={"blast_radius": "human 승인 limit 안에서 좁은 범위만 실행"},
        )
    )

    assert with_receipt.verdict is ReadinessVerdict.READY_WITH_GUARDS
    assert with_acceptance.verdict is ReadinessVerdict.READY_WITH_GUARDS


def test_rollback_needs_an_executable_mechanism() -> None:
    irreversible = RiskProfile(rollback=RiskLevel.HIGH)
    promise_only = check_readiness(
        ready_inputs(risk=irreversible, rollback=RollbackPlan(required=True, mechanism="", checkpoint_ref=""))
    )
    snapshot = check_readiness(
        ready_inputs(
            risk=irreversible,
            rollback=RollbackPlan(
                required=True, mechanism="SNAPSHOT", checkpoint_ref="vault:snapshot/42", scope="src/a.py"
            ),
        )
    )

    assert promise_only.check_result(ReadinessCheck.ROLLBACK_SUFFICIENT).status is CheckStatus.FAIL
    assert "문자열 rollback 약속" in promise_only.check_result(ReadinessCheck.ROLLBACK_SUFFICIENT).reason
    assert snapshot.check_result(ReadinessCheck.ROLLBACK_SUFFICIENT).status is CheckStatus.PASS


def test_required_verification_must_have_receipts() -> None:
    result = check_readiness(
        ready_inputs(
            verification=(
                VerificationRequirement(
                    name="pytest tests/cognitive", required=True, satisfied=True, receipt_ref="run:1"
                ),
                VerificationRequirement(name="manual QA", required=True, satisfied=False),
                VerificationRequirement(name="benchmark", required=False),
            )
        )
    )
    verification = result.check_result(ReadinessCheck.VERIFICATION_SUFFICIENT)

    assert verification.status is CheckStatus.FAIL
    assert "manual QA" in verification.reason


def test_freshness_revalidation_before_action() -> None:
    gate = ReadinessGate()
    result = gate.check(ready_inputs())
    current = FreshnessBinding(
        decision_revision=1,
        action_digest=DIGEST,
        state_revision=5,
        authority_revision=2,
        policy_version="policy/v2",
    )

    check = gate.revalidate(result, current)

    assert not check.fresh
    assert set(check.changed) == {"state_revision", "authority_revision", "policy_version"}
    with pytest.raises(StaleReadinessError):
        gate.assert_fresh(result, current)


def test_authority_revision_mismatch_fails_authority_check() -> None:
    result = check_readiness(ready_inputs(authority_decision=allowed_authority(revision=3), authority_revision=1))

    assert result.check_result(ReadinessCheck.AUTHORITY_SUFFICIENT).status is CheckStatus.FAIL


def test_assurance_round_trip_keeps_nine_checks() -> None:
    result = check_readiness(ready_inputs())
    assurance = result.as_assurance()

    assert assurance.verdict is ReadinessVerdict.READY
    assert len(assurance.check_results) == 9
    assert assurance.action_digest == DIGEST
    assert assurance.state_revision == 4


# ─── D. closure·reopen ──────────────────────────────────────────────


def test_close_requires_ready_and_keeps_trace_digest() -> None:
    ledger = DecisionLedger()
    decision = trace()
    result = check_readiness(ready_inputs())
    event = ledger.close(decision, result, occurred_at=NOW)

    assert event.readiness_verdict is ReadinessVerdict.READY
    assert event.trace_digest == decision.digest()
    assert ledger.trace_digest_history(decision.decision_id) == (decision.digest(),)

    with pytest.raises(DecisionLifecycleError):
        ledger.close(decision, check_readiness(ready_inputs(authority_decision=None)), occurred_at=NOW)


def test_close_rejects_stale_readiness() -> None:
    ledger = DecisionLedger()
    result = check_readiness(ready_inputs())
    stale = FreshnessBinding(
        decision_revision=1, action_digest=DIGEST, state_revision=9, authority_revision=1, policy_version="policy/v1"
    )

    with pytest.raises(DecisionLifecycleError):
        ledger.close(trace(), result, occurred_at=NOW, current_freshness=stale)


def test_reopen_requires_material_trigger_and_smallest_scope() -> None:
    ledger = DecisionLedger()
    decision = trace()
    ledger.close(decision, check_readiness(ready_inputs()), occurred_at=NOW)

    with pytest.raises(ReopenRefused):
        ledger.reopen(
            decision,
            ReopenRequest(
                trigger=ReopenTrigger.NEW_MATERIAL_EVIDENCE,
                trigger_evidence_ids=(),
                smallest_scope=f"{DECISION_ID}/ground:1",
                rationale="새 근거",
            ),
            occurred_at=NOW,
        )
    with pytest.raises(ReopenRefused):
        ledger.reopen(
            decision,
            ReopenRequest(
                trigger=ReopenTrigger.UNEXPECTED_OUTCOME,
                trigger_evidence_ids=(SECOND_EVIDENCE_ID,),
                smallest_scope="",
                rationale="결과가 달랐다",
            ),
            occurred_at=NOW,
        )

    event = ledger.reopen(
        decision,
        ReopenRequest(
            trigger=ReopenTrigger.UNEXPECTED_OUTCOME,
            trigger_evidence_ids=(SECOND_EVIDENCE_ID,),
            smallest_scope=f"{DECISION_ID}/action:write_file",
            rationale="예상과 다른 결과가 관측됐다",
            actor_kind=ProducerKind.HUMAN,
        ),
        occurred_at=NOW,
    )

    assert event.trigger is ReopenTrigger.UNEXPECTED_OUTCOME
    assert event.smallest_scope == f"{DECISION_ID}/action:write_file"
    assert event.assumes_effects_reverted is False
    assert event.trace_digest == decision.digest()
    assert decision.closure is ClosureState.OPEN


def test_duplicate_reopen_is_refused_and_old_trace_digest_is_unchanged() -> None:
    ledger = DecisionLedger()
    decision = trace()
    ledger.close(decision, check_readiness(ready_inputs()), occurred_at=NOW)
    request = ReopenRequest(
        trigger=ReopenTrigger.NEW_MATERIAL_EVIDENCE,
        trigger_evidence_ids=(SECOND_EVIDENCE_ID,),
        smallest_scope=DECISION_ID,
        rationale="새 근거가 생겼다",
    )
    first = ledger.reopen(decision, request, occurred_at=NOW)

    with pytest.raises(ReopenRefused):
        ledger.reopen(decision, request, occurred_at=NOW)

    digests = ledger.trace_digest_history(decision.decision_id)
    assert digests[0] == first.trace_digest == decision.digest()


def test_human_reopen_needs_no_evidence_and_cannot_claim_reversal() -> None:
    ledger = DecisionLedger()
    decision = trace()
    ledger.close(decision, check_readiness(ready_inputs()), occurred_at=NOW)

    human = ledger.reopen(
        decision,
        ReopenRequest(
            trigger=ReopenTrigger.HUMAN_REOPEN,
            trigger_evidence_ids=(),
            smallest_scope=DECISION_ID,
            rationale="Human이 직접 다시 열었다",
            actor_kind=ProducerKind.HUMAN,
            actions_already_dispatched=("action:1",),
        ),
        occurred_at=NOW,
    )
    assert human.actor_kind is ProducerKind.HUMAN
    assert human.actions_already_dispatched == ("action:1",)

    with pytest.raises(ReopenRefused):
        ledger.reopen(
            decision,
            ReopenRequest(
                trigger=ReopenTrigger.HUMAN_REOPEN,
                trigger_evidence_ids=(),
                smallest_scope=DECISION_ID,
                rationale="되돌렸다고 가정",
                claims_effects_reverted=True,
            ),
            occurred_at=NOW,
        )


def test_reassessment_appends_new_decision_link_without_touching_original() -> None:
    ledger = DecisionLedger()
    decision = trace()
    ledger.close(decision, check_readiness(ready_inputs()), occurred_at=NOW)
    reopen_event = ledger.reopen(
        decision,
        ReopenRequest(
            trigger=ReopenTrigger.MATERIAL_CONTRADICTION,
            trigger_evidence_ids=(THIRD_EVIDENCE_ID,),
            smallest_scope=f"{DECISION_ID}/ground:1",
            rationale="기존 ground와 모순되는 근거",
        ),
        occurred_at=NOW,
    )

    reassessment = ledger.reassess(
        decision,
        reopen_event,
        new_decision_id=NEW_DECISION_ID,
        changed_understanding="ground:1의 전제가 반증됐다",
        occurred_at=NOW,
    )

    assert reassessment.new_decision_id == NEW_DECISION_ID
    assert reassessment.previous_trace_digest == decision.digest()
    assert ledger.trace_digest_history(decision.decision_id) == (decision.digest(),)
    payload = reopen_event.as_reassessment_payload(changed_understanding="전제 반증")
    assert payload.target_record_id == decision.decision_id
    assert payload.smallest_scope == f"{DECISION_ID}/ground:1"

    with pytest.raises(DecisionLifecycleError):
        ledger.reassess(
            decision,
            reopen_event,
            new_decision_id=decision.decision_id,
            changed_understanding="원래 결정을 덮어쓰기",
            occurred_at=NOW,
        )


def test_governance_limits_flow_into_readiness_as_ready_with_guards() -> None:
    """P05 판정이 P06 입력으로 이어진다: APPROVE_WITH_LIMITS의 limit이 guard 의무로 유지된다."""

    profile = AuthorityProfile(revision=1, grants=(authority_grant(),))
    governance = GovernanceGate(clock=lambda: NOW).evaluate(
        GovernanceRequest(
            request_id="req-1",
            project_id="project:ssak-ai",
            subject=SUBJECT,
            action=governance_action(),
            authority=profile,
            unknowns=(governance_unknown(),),
        )
    )
    assert governance.disposition is GovernanceDisposition.APPROVE_WITH_LIMITS

    result = check_readiness(
        ready_inputs(
            authority_decision=governance.authority,
            limits=governance.limits,
        )
    )

    assert result.verdict is ReadinessVerdict.READY_WITH_GUARDS
    assert result.limits == governance.limits


def test_governance_denied_request_cannot_become_ready() -> None:
    """회수된 grant로 DENY된 요청은 readiness에서도 authority FAIL로 남는다."""

    profile = AuthorityProfile(revision=2, grants=(authority_grant(revoked_at=NOW),))
    governance = GovernanceGate(clock=lambda: NOW).evaluate(
        GovernanceRequest(
            request_id="req-1",
            project_id="project:ssak-ai",
            subject=SUBJECT,
            action=governance_action(),
            authority=profile,
        )
    )
    assert governance.disposition is GovernanceDisposition.DENY

    result = check_readiness(ready_inputs(authority_decision=governance.authority))

    assert result.verdict is ReadinessVerdict.NOT_READY
    assert result.check_result(ReadinessCheck.AUTHORITY_SUFFICIENT).status is CheckStatus.FAIL
    assert "REVOKED" in result.check_result(ReadinessCheck.AUTHORITY_SUFFICIENT).reason


def test_decision_record_persists_to_canonical_store(tmp_path) -> None:
    """P06 결과가 canonical record로 남는다: readiness assurance → Decision → store (P02 표면)."""

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    decision = trace()
    result = check_readiness(ready_inputs())
    ledger = DecisionLedger()
    closure = ledger.close(decision, result, occurred_at=NOW)

    record = Record.create(
        entity_type=EntityType.DECISION,
        project_id=new_id(EntityType.PROJECT),
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:runtime"),
        payload=DecisionPayload(
            selected_action=decision.selected_action,
            why_selected=decision.why_selected,
            closure=ClosureState.CLOSED_FOR_ACTION,
            expected_outcome=decision.expected_outcome,
            reopen_triggers=decision.reopen_triggers,
            readiness=result.as_assurance(),
            unknowns_assessed=True,
            authority_revision=result.freshness.authority_revision,
        ),
        created_at=NOW,
    )
    receipt = store.commit_records([record], message="cognitive: decision closure")

    assert receipt.committed_ids == (record.id,)
    assert store.read(record.id) == record
    assert store.verify_digests() == 1
    assert closure.trace_digest == decision.digest()
    assert len(store.list_committed()) == 1


def test_lifecycle_events_are_ordered_and_append_only() -> None:
    ledger = DecisionLedger()
    decision = trace()
    ledger.close(decision, check_readiness(ready_inputs()), occurred_at=NOW)
    reopen_event = ledger.reopen(
        decision,
        ReopenRequest(
            trigger=ReopenTrigger.RISK_CHANGE,
            trigger_evidence_ids=(SECOND_EVIDENCE_ID,),
            smallest_scope=f"{DECISION_ID}/risk",
            rationale="risk profile이 바뀌었다",
        ),
        occurred_at=NOW,
    )
    ledger.reassess(
        decision,
        reopen_event,
        new_decision_id=THIRD_DECISION_ID,
        changed_understanding="risk가 높아져 guard가 필요하다",
        occurred_at=NOW,
    )

    sequences = [event.sequence for event in ledger.events]
    assert sequences == sorted(sequences) == [1, 2, 3]
    assert [type(event).__name__ for event in ledger.events] == ["ClosureEvent", "ReopenEvent", "ReassessmentEvent"]
