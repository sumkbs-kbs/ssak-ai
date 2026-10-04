"""Admission checks shared by initial and immediate pre-effect validation."""

from __future__ import annotations

from datetime import datetime

from antigravity_k.engine.cognitive.action_context import ActionContext
from antigravity_k.engine.cognitive.action_types import ActionIntent, ActionRefusal, ActionRun
from antigravity_k.engine.cognitive.authority import scope_covers
from antigravity_k.engine.cognitive.models import ReceiptStatus, same_enum
from antigravity_k.engine.cognitive.readiness import FreshnessBinding, ReadinessGate, StaleReadinessError


def preconditions(
    self: ActionContext, intent: ActionIntent, *, retry_authorized: bool, now: datetime, subject: str
) -> ActionRun | None:
    clearance = intent.clearance
    if clearance is None or not clearance.granted:
        verdict = clearance.authority.verdict.value if clearance is not None and clearance.authority else "NO_CLEARANCE"
        return self._refuse(intent, ActionRefusal.NOT_AUTHORIZED, f"실행 허가가 없다: {verdict}")
    authority = clearance.authority
    if self.authority_resolver is not None:
        authority = self.authority_resolver(intent, now)
    if authority is None or not authority.allowed:
        return self._refuse(intent, ActionRefusal.NOT_AUTHORIZED, "current authority denies execution")
    scope = intent.scope or intent.tool
    grant = authority.grant
    if (
        (grant is not None or self.authority_resolver is not None)
        and authority.resource_scope
        and not scope_covers(authority.resource_scope, scope)
    ):
        return self._refuse(intent, ActionRefusal.NOT_AUTHORIZED, "decision scope does not cover action")
    if grant is not None and (
        grant.subject != subject
        or not scope_covers(grant.resource_scope, scope)
        or not same_enum(grant.dimension, intent.dimension)
        or ("*" not in grant.allowed_operations and intent.operation not in grant.allowed_operations)
        or grant.issued_at > now
        or (grant.expires_at is not None and grant.expires_at <= now)
        or grant.revoked_at is not None
    ):
        return self._refuse(intent, ActionRefusal.NOT_AUTHORIZED, "grant is no longer valid for this action")
    if authority is not None and not same_enum(authority.dimension, intent.dimension):
        return self._refuse(
            intent,
            ActionRefusal.DIMENSION_MISMATCH,
            f"허가 dimension {authority.dimension.value}과 요청 {intent.dimension.value}이 다르다",
        )
    if intent.network_access and not clearance.network_allowed:
        return self._refuse(intent, ActionRefusal.POLICY_CLEARANCE_MISSING, "network 접근 허가가 없다")
    if intent.private_data and not clearance.private_data_allowed:
        return self._refuse(intent, ActionRefusal.POLICY_CLEARANCE_MISSING, "private data 접근 허가가 없다")
    if intent.cost_usd > clearance.cost_ceiling_usd:
        return self._refuse(
            intent,
            ActionRefusal.COST_EXCEEDS_CLEARANCE,
            f"비용 {intent.cost_usd}이 clearance ceiling {clearance.cost_ceiling_usd}을 넘는다",
        )

    readiness = intent.readiness
    if readiness is None:
        return self._refuse(intent, ActionRefusal.STALE_READINESS, "readiness 없이 ACTION할 수 없다")
    if not readiness.ok:
        return self._refuse(
            intent,
            ActionRefusal.STALE_READINESS,
            f"readiness {readiness.verdict.value}: {list(readiness.blocking_conditions)}",
        )
    try:
        ReadinessGate().assert_fresh(readiness, _authoritative_freshness(self, intent, now))
    except StaleReadinessError as exc:
        return self._refuse(intent, ActionRefusal.STALE_READINESS, str(exc))
    if authority is not None and authority.profile_revision != (
        intent.authority_revision or authority.profile_revision
    ):
        return self._refuse(intent, ActionRefusal.STALE_READINESS, "authority revision이 판정 시점과 다르다")

    satisfied = {receipt.guard for receipt in intent.guard_receipts if receipt.accepted}
    missing = [guard.value for guard in intent.required_guards() if guard not in satisfied]
    if missing:
        return self._refuse(
            intent,
            ActionRefusal.GUARD_RECEIPTS_MISSING,
            f"guard receipt가 없는 의무: {missing}",
        )

    if self.port is None:
        return self._refuse(intent, ActionRefusal.NO_DISPATCH_PORT, "dispatch 경로가 연결되지 않았다(feature off)")

    existing = self._receipts.get(intent.action_key)
    if existing is not None:
        if existing.effects_observed is True:
            return self._refuse(
                intent, ActionRefusal.DUPLICATE_ACTION, "an effect was already observed", receipt=existing
            )
        if existing.status in (ReceiptStatus.DISPATCHED, ReceiptStatus.COMPLETED, ReceiptStatus.CANCELLED):
            same_submission = existing.submission_id == intent.submission_id
            detail = (
                "같은 submission이 이미 처리됐다"
                if same_submission
                else "같은 action key가 이미 실행됐다 — 중복 effect를 만들지 않는다"
            )
            return self._refuse(intent, ActionRefusal.DUPLICATE_ACTION, detail, receipt=existing)
        if same_enum(existing.status, ReceiptStatus.UNKNOWN):
            if not retry_authorized:
                return self._refuse(
                    intent,
                    ActionRefusal.UNRESOLVED_UNKNOWN,
                    "이전 시도 결과가 UNKNOWN이다 — reconciliation을 먼저 수행한다",
                    receipt=existing,
                )
            if not intent.idempotent:
                return self._refuse(
                    intent,
                    ActionRefusal.NON_IDEMPOTENT_REDISPATCH,
                    "non-idempotent action을 재dispatch할 수 없다",
                    receipt=existing,
                )
        if same_enum(existing.status, ReceiptStatus.FAILED) and existing.effects_observed is None:
            return self._refuse(
                intent,
                ActionRefusal.UNRESOLVED_UNKNOWN,
                "이전 실패의 effect 발생 여부가 확인되지 않았다",
                receipt=existing,
            )
    return None


def _authoritative_freshness(self: ActionContext, intent: ActionIntent, now: datetime) -> FreshnessBinding:
    """Compare readiness against live heads, never intent.freshness vs itself.

    ``freshness_resolver`` supplies the canonical authorized digest and live revisions.
    The executed arguments must match that authorization independently of readiness.
    """

    resolver = self.freshness_resolver
    if resolver is not None:
        live = resolver(intent, now)
        if live.action_digest != intent.args_digest():
            raise StaleReadinessError("Canonical decision does not authorize the current action digest")
        return live
    # Unit/legacy paths without a resolver: still recompute action_digest.
    # Decision/state/policy fall back to intent fields. ACTIVE must wire a resolver.
    base = intent.freshness()
    return FreshnessBinding(
        decision_revision=base.decision_revision,
        action_digest=intent.args_digest(),
        state_revision=base.state_revision,
        authority_revision=base.authority_revision,
        policy_version=base.policy_version,
    )
