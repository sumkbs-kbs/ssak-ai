"""T07 — Action receipt·복구·idempotency 시험 (P07).

검증 범위:
- 제출 idempotency(submission_id)와 action idempotency(action_key) 분리, 같은 key 중복 effect 0.
- effect 후 crash·timeout → UNKNOWN. 관측 없이는 성공으로 승격하지 않는다.
- 비idempotent 재dispatch 금지, 이미 발생한 action의 자동 취소·되돌림 주장 금지.
- 읽기 도구도 network/cost/privacy 권한 검사를 생략하지 않는다.
- intent/receipt가 canonical record로 남고, 실제 ToolExecutor 표면까지 한 번 완주한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionIntent,
    ActionObservation,
    ActionRefusal,
    CallablePort,
    PolicyClearance,
    ToolExecutorPort,
    claims_reversal,
)
from antigravity_k.engine.cognitive.authority import (
    AuthorityDecision,
    AuthorityGrant,
    AuthorityProfile,
    AuthorityVerdict,
)
from antigravity_k.engine.cognitive.governance import (
    GovernanceGate,
    GovernanceRequest,
    RequestedAction,
    ReshapeGuard,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    AuthorityDimension,
    GovernanceDisposition,
    ObservationStatus,
    Producer,
    ProducerKind,
    ReceiptStatus,
    RiskLevel,
    RiskProfile,
)
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    GuardReceipt,
    HardConstraint,
    ReadinessInputs,
    ReadinessResult,
    check_readiness,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.tools.base_tool import BaseTool
from antigravity_k.tools.tool_registry import ToolRegistry

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
PROJECT = "project:01234567-89ab-cdef-0123-456789abcdef"
ACTION_ID = new_id(EntityType.ACTION)
OTHER_ACTION_ID = new_id(EntityType.ACTION)
BODY = Producer(kind=ProducerKind.BODY, actor_id="body:runtime")
SUBJECT = "body:runtime"


def low_risk() -> RiskProfile:
    return RiskProfile(
        reversibility=RiskLevel.LOW,
        blast_radius=RiskLevel.LOW,
        data_state_loss=RiskLevel.LOW,
        rollback=RiskLevel.LOW,
        verification=RiskLevel.LOW,
    )


def clearance_for(
    *,
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE,
    allowed: bool = True,
    network_allowed: bool = False,
    cost_ceiling_usd: float = 0.0,
    private_data_allowed: bool = False,
    revision: int = 1,
) -> PolicyClearance:
    decision = AuthorityDecision(
        allowed=allowed,
        verdict=AuthorityVerdict.ALLOWED if allowed else AuthorityVerdict.REVOKED,
        reason="fixture",
        dimension=dimension,
        resource_scope="src",
        profile_revision=revision,
    )
    return PolicyClearance(
        authority=decision,
        network_allowed=network_allowed,
        cost_ceiling_usd=cost_ceiling_usd,
        private_data_allowed=private_data_allowed,
        revision=revision,
    )


def ready_readiness(
    *,
    action_digest: str,
    guard_receipts: tuple[GuardReceipt, ...] = (),
    limits: tuple[str, ...] = (),
    authority_revision: int = 1,
) -> ReadinessResult:
    return check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool="write_file",
                scope="src/a.py",
                expected_outcome="T07 통과",
                action_digest=action_digest,
            ),
            authorized_action_digest=action_digest,
            decision_revision=1,
            state_revision=4,
            authority_revision=authority_revision,
            policy_version="policy/v1",
            grounds=("evidence:1",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:1",
                    provenance_uri="tests/cognitive/test_actions.py",
                    provenance_digest="sha256:" + "b" * 64,
                    observed_at=NOW,
                ),
            ),
            constraints=(HardConstraint(name="no_network", satisfied=True),),
            risk=low_risk(),
            guard_receipts=guard_receipts,
            limits=limits,
            authority_decision=clearance_for(revision=authority_revision).authority,
        )
    )


def make_intent(**overrides: object) -> ActionIntent:
    """readiness까지 붙은 정상 intent를 만든다. 인자 digest는 intent에서 계산한다."""

    arguments = overrides.pop("arguments", {"file_path": "src/a.py", "content": "x"})
    tool = str(overrides.pop("tool", "write_file"))
    scope = str(overrides.pop("scope", "src/a.py"))
    provisional = ActionIntent(
        action_id=str(overrides.pop("action_id", ACTION_ID)),
        submission_id=str(overrides.pop("submission_id", "submission:1")),
        action_key=str(overrides.pop("action_key", "key-1")),
        tool=tool,
        arguments=arguments,  # type: ignore[arg-type]
        scope=scope,
        dimension=overrides.pop("dimension", AuthorityDimension.TOOL_WRITE),  # type: ignore[arg-type]
        risk=overrides.pop("risk", low_risk()),  # type: ignore[arg-type]
        idempotent=bool(overrides.pop("idempotent", True)),
        guards=overrides.pop("guards", ()),  # type: ignore[arg-type]
        guard_receipts=overrides.pop("guard_receipts", ()),  # type: ignore[arg-type]
        decision_revision=int(overrides.pop("decision_revision", 1)),
        state_revision=int(overrides.pop("state_revision", 4)),
        authority_revision=overrides.pop("authority_revision", 1),  # type: ignore[arg-type]
        policy_version=overrides.pop("policy_version", "policy/v1"),  # type: ignore[arg-type]
        network_access=bool(overrides.pop("network_access", False)),
        cost_usd=float(overrides.pop("cost_usd", 0.0)),
        private_data=bool(overrides.pop("private_data", False)),
        clearance=overrides.pop("clearance", clearance_for()),  # type: ignore[arg-type]
    )
    readiness = overrides.pop("readiness", None)
    if readiness is None:
        readiness = ready_readiness(
            action_digest=provisional.args_digest(),
            guard_receipts=provisional.guard_receipts,
            authority_revision=provisional.authority_revision or 1,
        )
    return replace(provisional, readiness=readiness)  # type: ignore[arg-type]


def test_duplicate_action_key_has_no_second_effect() -> None:
    calls: list[str] = []
    port = CallablePort(lambda tool, args, action_id: (calls.append(action_id), "ok")[1])
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)
    intent = make_intent()

    first = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    second = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert first.status is ActionExecutionStatus.DISPATCHED
    assert first.receipt is not None and first.receipt.status is ReceiptStatus.DISPATCHED
    assert second.refused
    assert second.refusal is ActionRefusal.DUPLICATE_ACTION
    assert len(calls) == 1
    assert dispatcher.receipt_for(intent.action_key) == first.receipt


def test_submission_idempotency_and_action_idempotency_are_separate() -> None:
    calls: list[str] = []
    port = CallablePort(lambda tool, args, action_id: (calls.append(action_id), "ok")[1])
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)
    first = make_intent(action_key="key-1", submission_id="submission:1")
    same_submission = make_intent(action_key="key-1", submission_id="submission:1")
    other_submission = make_intent(action_key="key-1", submission_id="submission:2")
    same_submission_other_action = make_intent(action_key="key-2", submission_id="submission:1")

    dispatcher.execute(first, project_id=PROJECT, producer=BODY)
    replay = dispatcher.execute(same_submission, project_id=PROJECT, producer=BODY)
    duplicate_effect = dispatcher.execute(other_submission, project_id=PROJECT, producer=BODY)
    second_action = dispatcher.execute(same_submission_other_action, project_id=PROJECT, producer=BODY)

    assert replay.refusal is ActionRefusal.DUPLICATE_ACTION
    assert "같은 submission" in replay.reason
    assert duplicate_effect.refusal is ActionRefusal.DUPLICATE_ACTION
    assert "중복 effect" in duplicate_effect.reason
    assert second_action.status is ActionExecutionStatus.DISPATCHED
    assert len(calls) == 2


def test_crash_after_effect_yields_unknown_not_success(tmp_path: Path) -> None:
    target = tmp_path / "effect.txt"

    def crashing_port(tool: str, args: Mapping[str, object], action_id: str) -> str:
        _ = (tool, action_id)
        target.write_text(str(args["content"]), encoding="utf-8")
        raise TimeoutError("no response after effect")

    dispatcher = ActionDispatcher(port=CallablePort(crashing_port), clock=lambda: NOW)
    intent = make_intent(arguments={"file_path": str(target), "content": "side effect"})

    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert target.read_text(encoding="utf-8") == "side effect"
    assert run.status is ActionExecutionStatus.UNKNOWN
    assert run.receipt is not None
    assert run.receipt.status is ReceiptStatus.UNKNOWN
    assert run.receipt.effects_observed is None
    assert run.reconciliation_required

    unresolved = dispatcher.reconcile(
        run,
        ActionObservation(observed=False, status=ObservationStatus.UNAVAILABLE),
        project_id=PROJECT,
        producer=BODY,
    )
    assert unresolved.status is ActionExecutionStatus.UNKNOWN
    assert unresolved.receipt is not None and unresolved.receipt.effects_observed is None
    assert "성공으로 승격하지 않는다" in unresolved.receipt.reconciliation

    settled = dispatcher.reconcile(
        run,
        ActionObservation(observed=True, succeeded=True, external_ref="fs:effect.txt"),
        project_id=PROJECT,
        producer=BODY,
    )
    assert settled.status is ActionExecutionStatus.SUCCEEDED
    assert settled.receipt is not None
    assert settled.receipt.status is ReceiptStatus.COMPLETED
    assert settled.receipt.effects_observed is True
    assert not settled.reconciliation_required


def test_pending_reconciliation_lists_unsettled_receipts() -> None:
    def crashing_port(tool: str, args: Mapping[str, object], action_id: str) -> str:
        _ = (tool, args, action_id)
        raise TimeoutError("unknown outcome")

    dispatcher = ActionDispatcher(port=CallablePort(crashing_port), clock=lambda: NOW)
    intent = make_intent(action_key="pending")
    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert [receipt.action_key for receipt in dispatcher.pending_reconciliation()] == ["pending"]

    settled = dispatcher.reconcile(
        run,
        ActionObservation(observed=True, succeeded=True),
        project_id=PROJECT,
        producer=BODY,
    )

    assert settled.status is ActionExecutionStatus.SUCCEEDED
    assert dispatcher.pending_reconciliation() == ()


def test_non_idempotent_action_is_not_redispatched_after_unknown() -> None:
    calls: list[str] = []

    def crashing_port(tool: str, args: Mapping[str, object], action_id: str) -> str:
        calls.append(action_id)
        raise TimeoutError("unknown outcome")

    dispatcher = ActionDispatcher(port=CallablePort(crashing_port), clock=lambda: NOW)
    intent = make_intent(idempotent=False, action_key="non-idempotent")

    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.status is ActionExecutionStatus.UNKNOWN

    blocked = dispatcher.execute(intent, project_id=PROJECT, producer=BODY, retry_authorized=True)
    assert blocked.refusal is ActionRefusal.NON_IDEMPOTENT_REDISPATCH
    assert len(calls) == 1

    idempotent_intent = make_intent(idempotent=True, action_key="idempotent")
    dispatcher.execute(idempotent_intent, project_id=PROJECT, producer=BODY)
    retried = dispatcher.execute(idempotent_intent, project_id=PROJECT, producer=BODY, retry_authorized=True)
    assert retried.status is ActionExecutionStatus.UNKNOWN
    assert retried.receipt is not None and retried.receipt.dispatch_attempt == 2
    assert len(calls) == 3


def test_read_action_still_needs_clearance_and_matching_dimension() -> None:
    calls: list[str] = []
    port = CallablePort(lambda tool, args, action_id: (calls.append(action_id), "read ok")[1])
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)

    no_clearance = make_intent(tool="read_file", dimension=AuthorityDimension.TOOL_READ, clearance=None)
    wrong_dimension = make_intent(
        tool="read_file",
        dimension=AuthorityDimension.TOOL_READ,
        clearance=clearance_for(dimension=AuthorityDimension.TOOL_WRITE),
    )
    allowed = make_intent(
        tool="read_file",
        dimension=AuthorityDimension.TOOL_READ,
        clearance=clearance_for(dimension=AuthorityDimension.TOOL_READ),
    )

    assert dispatcher.execute(no_clearance, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.NOT_AUTHORIZED
    assert (
        dispatcher.execute(wrong_dimension, project_id=PROJECT, producer=BODY).refusal
        is ActionRefusal.DIMENSION_MISMATCH
    )
    assert dispatcher.execute(allowed, project_id=PROJECT, producer=BODY).status is ActionExecutionStatus.DISPATCHED
    assert len(calls) == 1


def test_network_cost_and_privacy_clearance_are_enforced() -> None:
    port = CallablePort(lambda tool, args, action_id: "ok")
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)

    network = make_intent(action_key="network", network_access=True, clearance=clearance_for())
    cost = make_intent(action_key="cost", cost_usd=5.0, clearance=clearance_for(cost_ceiling_usd=1.0))
    privacy = make_intent(action_key="privacy", private_data=True, clearance=clearance_for())
    granted = make_intent(
        action_key="granted",
        network_access=True,
        cost_usd=1.0,
        private_data=True,
        clearance=clearance_for(network_allowed=True, cost_ceiling_usd=2.0, private_data_allowed=True),
    )

    assert (
        dispatcher.execute(network, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.POLICY_CLEARANCE_MISSING
    )
    assert dispatcher.execute(cost, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.COST_EXCEEDS_CLEARANCE
    assert (
        dispatcher.execute(privacy, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.POLICY_CLEARANCE_MISSING
    )
    assert dispatcher.execute(granted, project_id=PROJECT, producer=BODY).status is ActionExecutionStatus.DISPATCHED


def test_stale_readiness_and_missing_guard_receipts_block_dispatch() -> None:
    calls: list[str] = []
    port = CallablePort(lambda tool, args, action_id: (calls.append(action_id), "ok")[1])
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)

    no_readiness = replace(make_intent(), readiness=None)
    stale = make_intent(readiness=ready_readiness(action_digest="sha256:" + "f" * 64))
    guard_required = make_intent(
        action_key="guarded",
        guards=(ReshapeGuard.CHECKPOINT,),
    )
    with_receipt = make_intent(
        action_key="guarded",
        guards=(ReshapeGuard.CHECKPOINT,),
        guard_receipts=(
            GuardReceipt(
                guard=ReshapeGuard.CHECKPOINT,
                enforced_by="tool_executor",
                receipt_digest="sha256:" + "c" * 64,
            ),
        ),
    )

    assert dispatcher.execute(no_readiness, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.STALE_READINESS
    assert dispatcher.execute(stale, project_id=PROJECT, producer=BODY).refusal is ActionRefusal.STALE_READINESS
    assert (
        dispatcher.execute(guard_required, project_id=PROJECT, producer=BODY).refusal
        is ActionRefusal.GUARD_RECEIPTS_MISSING
    )
    assert (
        dispatcher.execute(with_receipt, project_id=PROJECT, producer=BODY).status is ActionExecutionStatus.DISPATCHED
    )
    assert len(calls) == 1


def test_feature_off_without_port_executes_nothing() -> None:
    dispatcher = ActionDispatcher(clock=lambda: NOW)
    run = dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)

    assert run.refusal is ActionRefusal.NO_DISPATCH_PORT
    assert run.receipt is None
    assert dispatcher.records == ()


def test_cancel_before_dispatch_and_never_claims_reversal_after() -> None:
    port = CallablePort(lambda tool, args, action_id: "ok")
    dispatcher = ActionDispatcher(port=port, clock=lambda: NOW)
    planned = make_intent(action_key="cancel-before")
    _record, planned_run = dispatcher.plan(planned, project_id=PROJECT, producer=BODY)

    cancelled = dispatcher.cancel(planned_run, reason="Human 취소", now=NOW)

    assert cancelled.status is ActionExecutionStatus.CANCELLED
    assert cancelled.receipt is not None and cancelled.receipt.status is ReceiptStatus.CANCELLED
    assert cancelled.receipt.effects_observed is False
    assert not cancelled.reconciliation_required

    dispatched = dispatcher.execute(make_intent(action_key="cancel-after"), project_id=PROJECT, producer=BODY)
    after = dispatcher.cancel(dispatched, reason="Human 취소", now=NOW)

    assert after.status is ActionExecutionStatus.DISPATCHED
    assert after.cancellation_requested
    assert after.reconciliation_required
    assert not claims_reversal(after.cancellation_note)
    assert "되돌림은 주장하지 않으며" in after.cancellation_note
    assert after.receipt is not None and after.receipt.status is ReceiptStatus.DISPATCHED


def test_records_are_persisted_to_canonical_store(tmp_path: Path) -> None:
    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda tool, args, action_id: "ok"),
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="stored")

    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert run.receipt is not None
    assert len(dispatcher.records) == 2  # Action(intent) + ExecutionReceipt
    assert store.verify_digests() == 2
    action_record, receipt_record = dispatcher.records
    assert action_record.entity_type is EntityType.ACTION
    assert receipt_record.entity_type is EntityType.EXECUTION_RECEIPT
    assert store.read(receipt_record.id) == receipt_record
    assert store.read(action_record.id) == action_record
    assert all(record.project_id == PROJECT for record in dispatcher.records)

    republished = run.receipt.to_record(project_id=PROJECT, producer=BODY, created_at=NOW)
    assert republished.entity_type is EntityType.EXECUTION_RECEIPT
    assert republished.payload.action_id == run.intent.action_id  # type: ignore[union-attr]
    assert republished.payload.idempotency_key == run.intent.action_key  # type: ignore[union-attr]


# ─── 실제 ToolExecutor 표면 ─────────────────────────────────────────


class _AppendTool(BaseTool):
    """호출 횟수를 파일에 남기는 append 도구. 중복 effect 판정에 쓴다."""

    @property
    def name(self) -> str:
        return "append_line"

    @property
    def description(self) -> str:
        return "test-only append writer"

    @property
    def parameters_schema(self) -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    def execute(self, **kwargs: object) -> object:
        path = Path(str(kwargs["file_path"]))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(str(kwargs.get("content", "")) + "\n")
        return f"appended to {path.name}"


class _FailTool(_AppendTool):
    @property
    def name(self) -> str:
        return "append_line_fail"

    def execute(self, **kwargs: object) -> object:
        _ = kwargs
        return "Error: executor refused the write"


def _executor(tmp_path: Path, registry: ToolRegistry) -> ToolExecutor:
    with patch("antigravity_k.engine.tool_executor.ImmuneSystem"):
        executor = ToolExecutor(
            tool_registry=registry,
            permission_gate=registry.permission_gate,
            project_root=str(tmp_path),
        )
    setattr(executor, "_immune_system", None)
    return executor


def _registry(tmp_path: Path) -> ToolRegistry:
    registry = ToolRegistry(project_root=str(tmp_path))
    install = getattr(registry, "install")
    install(_AppendTool())
    install(_FailTool())
    return registry


def test_tool_executor_port_runs_governed_action_once(tmp_path: Path) -> None:
    """P05 governance → P06 readiness → P07 dispatch → 실제 ToolExecutor → 파일 관찰."""

    registry = _registry(tmp_path)
    executor = _executor(tmp_path, registry)
    target = tmp_path / "governed.txt"

    profile = AuthorityProfile(
        revision=1,
        grants=(
            AuthorityGrant(
                subject=SUBJECT,
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope=str(tmp_path),
                allowed_operations=("execute_tool",),
                constraints=(),
                granted_by="human:mr.k",
                issued_at=NOW,
                revision=1,
            ),
        ),
    )
    governance = GovernanceGate(clock=lambda: NOW).evaluate(
        GovernanceRequest(
            request_id="req-1",
            project_id=PROJECT,
            subject=SUBJECT,
            action=RequestedAction(
                tool="append_line",
                operation="execute_tool",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope=str(target),
                arguments={"file_path": str(target), "content": "run"},
                risk=low_risk(),
            ),
            authority=profile,
        )
    )
    assert governance.disposition is GovernanceDisposition.APPROVE

    arguments = {"file_path": str(target), "content": "run"}
    intent = ActionIntent(
        action_id=OTHER_ACTION_ID,
        submission_id="submission:1",
        action_key="governed-key",
        tool="append_line",
        arguments=arguments,
        scope=str(target),
        dimension=AuthorityDimension.TOOL_WRITE,
        risk=low_risk(),
        clearance=PolicyClearance.from_governance(governance),
        authority_revision=1,
        state_revision=4,
        policy_version="policy/v1",
    )
    readiness = ready_readiness(action_digest=intent.args_digest())
    intent = replace(intent, readiness=readiness)
    dispatcher = ActionDispatcher(
        port=ToolExecutorPort(executor=executor, failure_predicate=result_indicates_failure),
        clock=lambda: NOW,
    )

    first = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    replay = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert first.status is ActionExecutionStatus.DISPATCHED
    assert first.receipt is not None and first.receipt.status is ReceiptStatus.DISPATCHED
    assert first.reconciliation_required
    assert target.read_text(encoding="utf-8") == "run\n"
    assert replay.refusal is ActionRefusal.DUPLICATE_ACTION

    observed = dispatcher.reconcile(
        first,
        ActionObservation(observed=True, succeeded=True, external_ref=f"fs:{target.name}"),
        project_id=PROJECT,
        producer=BODY,
    )
    assert observed.status is ActionExecutionStatus.SUCCEEDED
    assert target.read_text(encoding="utf-8") == "run\n"


def test_tool_executor_port_reports_failure_without_effect_claim(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    executor = _executor(tmp_path, registry)
    target = tmp_path / "failed.txt"
    dispatcher = ActionDispatcher(
        port=ToolExecutorPort(executor=executor, failure_predicate=result_indicates_failure),
        clock=lambda: NOW,
    )
    intent = make_intent(
        tool="append_line_fail",
        scope=str(target),
        arguments={"file_path": str(target), "content": "no"},
    )

    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert run.status is ActionExecutionStatus.FAILED
    assert run.receipt is not None
    assert run.receipt.status is ReceiptStatus.FAILED
    assert run.receipt.effects_observed is False
    assert not target.exists()


def test_policy_clearance_from_governance_requires_admitted_execution() -> None:
    profile = AuthorityProfile(
        revision=2,
        grants=(
            AuthorityGrant(
                subject=SUBJECT,
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src",
                allowed_operations=("execute_tool",),
                constraints=(),
                granted_by="human:mr.k",
                issued_at=NOW,
                revision=1,
                revoked_at=NOW,
            ),
        ),
    )
    denied = GovernanceGate(clock=lambda: NOW).evaluate(
        GovernanceRequest(
            request_id="req-2",
            project_id=PROJECT,
            subject=SUBJECT,
            action=RequestedAction(
                tool="write_file",
                operation="execute_tool",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope="src/a.py",
                arguments={"file_path": "src/a.py"},
                risk=low_risk(),
            ),
            authority=profile,
        )
    )

    clearance = PolicyClearance.from_governance(denied, network_allowed=True)

    assert denied.disposition is GovernanceDisposition.DENY
    assert not clearance.granted
    assert not clearance.network_allowed
    assert clearance.revision is None


@pytest.mark.parametrize("reason", ["Human 취소", "timeout", "crash after effect"])
def test_cancel_note_never_claims_reversal(reason: str) -> None:
    dispatcher = ActionDispatcher(port=CallablePort(lambda tool, args, action_id: "ok"), clock=lambda: NOW)
    run = dispatcher.execute(make_intent(action_key=f"cancel-{reason}"), project_id=PROJECT, producer=BODY)
    cancelled = dispatcher.cancel(run, reason=reason, now=NOW)

    assert not claims_reversal(cancelled.cancellation_note)
    assert claims_reversal("이미 되돌렸다")


# ─── R09 durable episode/decision/receipt lineage ────────────────────


def test_r09_a1_reverse_trace_committed_receipt_ids(tmp_path: Path) -> None:
    """R09-A1: dispatch references reverse-trace from committed canonical records."""
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.references import REL_ACTION

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda tool, args, action_id: "ok"),
        record_sink=lambda records: store.commit_records(list(records)),
        journal=journal,
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r09-a1")

    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)

    assert run.receipt is not None
    receipt = run.receipt
    # durable receipt_id is the committed record id
    assert receipt.receipt_id.startswith("execution_receipt:")
    committed = store.read(receipt.receipt_id)
    assert committed is not None
    assert committed.id == receipt.receipt_id
    assert committed.payload.action_id == intent.action_id  # type: ignore[union-attr]
    action = store.read(intent.action_id)
    assert action is not None
    assert action.entity_type is EntityType.ACTION
    assert any(ref.relation == REL_ACTION and ref.target_id == intent.action_id for ref in committed.references)
    # republish keeps the same durable id (evaluation ref stable)
    again = receipt.to_record(project_id=PROJECT, producer=BODY, created_at=NOW)
    assert again.id == receipt.receipt_id == committed.id
    claim = journal.get(PROJECT, intent.action_key)
    assert claim is not None
    assert claim.action_record_id == intent.action_id
    assert claim.receipt_id == receipt.receipt_id


def test_r09_a2_persist_failure_zero_tool_calls(tmp_path: Path) -> None:
    """R09-A2: intent persistence failure means tool calls stay at 0."""
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal

    calls: list[int] = []

    def boom(records):
        raise OSError("canonical sink unavailable")

    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *args: calls.append(1)),
        journal=SqliteActionJournal(tmp_path / "claims.sqlite"),
        record_sink=boom,
        clock=lambda: NOW,
    )
    with pytest.raises(OSError):
        dispatcher.execute(make_intent(action_key="r09-a2"), project_id=PROJECT, producer=BODY)
    assert calls == []


def test_r09_a3_restart_pending_preserves_ids(tmp_path: Path) -> None:
    """R09-A3: after process restart, pending action and original decision/receipt IDs remain."""
    from antigravity_k.engine.cognitive.action_journal import PENDING, SqliteActionJournal

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal_path = tmp_path / "claims.sqlite"
    journal = SqliteActionJournal(journal_path)
    first = ActionDispatcher(
        port=CallablePort(lambda tool, args, action_id: "ok"),
        record_sink=lambda records: store.commit_records(list(records)),
        journal=journal,
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r09-a3")
    run = first.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    original_receipt_id = run.receipt.receipt_id
    original_action_id = intent.action_id

    # Simulate process restart: new dispatcher, same journal + store.
    restarted = ActionDispatcher(
        port=CallablePort(lambda *args: None),
        record_sink=lambda records: store.commit_records(list(records)),
        journal=SqliteActionJournal(journal_path),
        clock=lambda: NOW,
    )
    pending = restarted.pending_claims(PROJECT)
    assert len(pending) == 1
    claim = pending[0]
    assert claim.action_key == "r09-a3"
    assert claim.action_record_id == original_action_id
    assert claim.receipt_id == original_receipt_id
    assert claim.status == PENDING
    assert store.read(original_receipt_id) is not None
    assert store.read(original_action_id) is not None


def test_r09_a4_reconcile_append_supersedes_keeps_prior_bytes(tmp_path: Path) -> None:
    """R09-A4: new receipt revision appends; prior canonical bytes stay intact."""
    from antigravity_k.engine.cognitive.action_journal import SETTLED, SqliteActionJournal
    from antigravity_k.engine.cognitive.references import REL_SUPERSEDES

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda tool, args, action_id: "ok"),
        record_sink=lambda records: store.commit_records(list(records)),
        journal=journal,
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r09-a4")
    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    prior_id = run.receipt.receipt_id
    prior = store.read(prior_id)
    assert prior is not None
    prior_bytes = prior.model_dump_json().encode("utf-8")

    settled = dispatcher.reconcile(
        run,
        ActionObservation(observed=True, succeeded=True, detail="ok"),
        project_id=PROJECT,
        producer=BODY,
        now=NOW,
    )
    assert settled.receipt is not None
    assert settled.receipt.receipt_id != prior_id
    # prior row unchanged
    still = store.read(prior_id)
    assert still is not None
    assert still.model_dump_json().encode("utf-8") == prior_bytes
    newer = store.read(settled.receipt.receipt_id)
    assert newer is not None
    assert any(ref.relation == REL_SUPERSEDES and ref.target_id == prior_id for ref in newer.references)
    claim = journal.get(PROJECT, intent.action_key)
    assert claim is not None
    assert claim.receipt_id == settled.receipt.receipt_id
    assert claim.status == SETTLED
