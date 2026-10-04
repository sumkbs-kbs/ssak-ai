"""Resolve authoritative committed canonical heads for trusted ACTIVE execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from antigravity_k.engine.cognitive.actions import ActionIntent
from antigravity_k.engine.cognitive.authority import AuthorityDecision, AuthorityProfile, AuthorityQuery
from antigravity_k.engine.cognitive.models import (
    AuthorityProfilePayload,
    CheckStatus,
    DecisionPayload,
    EventPayload,
    PolicyPayload,
    ReadinessVerdict,
    Record,
)
from antigravity_k.engine.cognitive.readiness import FreshnessBinding
from antigravity_k.engine.cognitive.references import REL_SUPERSEDES, EntityType
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.cognitive_surface_types import SurfaceNotReadyError


@dataclass(frozen=True, slots=True)
class CanonicalHeadAnchors:
    """Stable lineage roots selected by trusted project preparation."""

    decision_id: str
    state_event_id: str
    authority_id: str
    policy_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalCurrentHeads:
    store: CanonicalStore
    project_id: str
    principal: str
    anchors: CanonicalHeadAnchors

    def _head(self, anchor: str, kind: EntityType, records: Mapping[str, Record]) -> Record:
        current = records.get(anchor)
        if current is None or current.entity_type != kind:
            raise SurfaceNotReadyError(f"Canonical {kind} head is missing")
        seen: set[str] = set()
        while True:
            if current.id in seen:
                raise SurfaceNotReadyError("Canonical head lineage contains a cycle")
            seen.add(current.id)
            children = [
                record
                for record in records.values()
                if any(ref.relation == REL_SUPERSEDES and ref.target_id == current.id for ref in record.references)
            ]
            if not children:
                return current
            if len(children) != 1 or children[0].entity_type != kind:
                raise SurfaceNotReadyError(f"Canonical {kind} head is ambiguous")
            successor = children[0]
            old_revision = self._revision(current)
            new_revision = self._revision(successor)
            if old_revision == new_revision:
                raise SurfaceNotReadyError("Canonical successor did not advance its revision")
            if isinstance(old_revision, int) and isinstance(new_revision, int) and new_revision < old_revision:
                raise SurfaceNotReadyError("Canonical successor regressed its revision")
            current = successor

    @staticmethod
    def _revision(record: Record) -> int | str:
        payload = record.payload
        if isinstance(payload, DecisionPayload):
            return payload.readiness.decision_revision
        if isinstance(payload, EventPayload):
            return payload.state_revision
        if isinstance(payload, AuthorityProfilePayload):
            return payload.revision
        if isinstance(payload, PolicyPayload):
            return payload.version
        raise SurfaceNotReadyError("Unsupported canonical head payload")

    def _records(self) -> Mapping[str, Record]:
        return {record.id: record for record in self.store.list_committed(self.project_id)}

    def authority(self, intent: ActionIntent, now: datetime) -> AuthorityDecision:
        record = self._head(self.anchors.authority_id, EntityType.AUTHORITY_PROFILE, self._records())
        payload = record.payload
        if not isinstance(payload, AuthorityProfilePayload) or payload.human_ceiling_ref is not None:
            raise SurfaceNotReadyError("Canonical authority ceiling cannot be resolved")
        return AuthorityProfile.from_record(record).evaluate(
            AuthorityQuery(
                subject=self.principal,
                dimension=intent.dimension,
                resource_scope=intent.scope,
                operation=intent.operation,
            ),
            now=now,
        )

    def freshness(self, intent: ActionIntent, now: datetime) -> FreshnessBinding:
        """Read committed heads again; never echo readiness/intent revisions."""
        records = self._records()
        decision = self._head(self.anchors.decision_id, EntityType.DECISION, records).payload
        state = self._head(self.anchors.state_event_id, EntityType.EVENT, records).payload
        authority = self._head(self.anchors.authority_id, EntityType.AUTHORITY_PROFILE, records).payload
        if (
            not isinstance(decision, DecisionPayload)
            or not isinstance(state, EventPayload)
            or not isinstance(authority, AuthorityProfilePayload)
        ):
            raise SurfaceNotReadyError("Canonical freshness payload mismatch")
        assurance = decision.readiness
        if assurance.verdict == ReadinessVerdict.NOT_READY or any(
            check.status in (CheckStatus.FAIL, CheckStatus.UNKNOWN) for check in assurance.check_results
        ):
            raise SurfaceNotReadyError("Current canonical Decision is not ready for execution")
        if assurance.verdict == ReadinessVerdict.READY_WITH_GUARDS and (
            intent.readiness is None or intent.readiness.verdict != ReadinessVerdict.READY_WITH_GUARDS
        ):
            raise SurfaceNotReadyError("Canonical guarded Decision requires guarded readiness")
        if not decision.readiness.action_digest:
            raise SurfaceNotReadyError("Canonical decision has no authorized action digest")
        policy_version = None
        if self.anchors.policy_id is not None:
            policy = self._head(self.anchors.policy_id, EntityType.POLICY, records).payload
            if not isinstance(policy, PolicyPayload):
                raise SurfaceNotReadyError("Canonical policy payload mismatch")
            policy_version = policy.version
        return FreshnessBinding(
            decision_revision=decision.readiness.decision_revision,
            action_digest=decision.readiness.action_digest,
            state_revision=state.state_revision,
            authority_revision=authority.revision,
            policy_version=policy_version,
        )
