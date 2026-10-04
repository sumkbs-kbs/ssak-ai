"""Trusted canonical CognitiveRequest bindings and per-action authorization heads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from antigravity_k.engine.cognitive.actions import ActionIntent
from antigravity_k.engine.cognitive.authority import AuthorityDecision, AuthorityProfile
from antigravity_k.engine.cognitive.models import AuthorityProfilePayload, CognitiveRequestPayload, Record
from antigravity_k.engine.cognitive.readiness import FreshnessBinding
from antigravity_k.engine.cognitive.references import EntityType
from antigravity_k.engine.cognitive.runtime import CognitiveRequestEnvelope
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.cognitive_active_heads import CanonicalCurrentHeads, CanonicalHeadAnchors
from antigravity_k.engine.cognitive_surface_types import SurfaceNotReadyError


@dataclass(frozen=True, slots=True)
class TrustedCognitiveRequestBinding:
    action: ActionIntent
    anchors: CanonicalHeadAnchors


class ActiveRequestBindings:
    """Server-owned mapping; unknown action identities never inherit final-action authority."""

    def __init__(
        self,
        store: CanonicalStore,
        project_id: str,
        principal: str,
        primary: CanonicalCurrentHeads,
        primary_action_ids: tuple[str, ...],
        bindings: Mapping[str, TrustedCognitiveRequestBinding],
    ) -> None:
        self.store = store
        self.project_id = project_id
        self.principal = principal
        self.primary = primary
        self.primary_action_ids = frozenset(primary_action_ids)
        self.bindings = dict(bindings)
        ids = [binding.action.action_id for binding in self.bindings.values()]
        if len(ids) != len(set(ids)) or self.primary_action_ids.intersection(ids):
            raise SurfaceNotReadyError("Trusted action identities must be unique")

    def _heads(self, action: ActionIntent) -> CanonicalCurrentHeads:
        for binding in self.bindings.values():
            if binding.action.action_id == action.action_id:
                return CanonicalCurrentHeads(self.store, self.project_id, self.principal, binding.anchors)
        if action.action_id in self.primary_action_ids:
            return self.primary
        raise SurfaceNotReadyError("Action has no trusted canonical head binding")

    def authority(self, action: ActionIntent, now: datetime) -> AuthorityDecision:
        return self._heads(action).authority(action, now)

    def freshness(self, action: ActionIntent, now: datetime) -> FreshnessBinding:
        return self._heads(action).freshness(action, now)

    def resolve(self, record: Record) -> CognitiveRequestEnvelope | None:
        binding = self.bindings.get(record.id)
        if binding is None:
            return None
        payload = record.payload
        if record.project_id != self.project_id or not isinstance(payload, CognitiveRequestPayload):
            raise SurfaceNotReadyError("Cognitive request binding project/type mismatch")
        if payload.args_digest != binding.action.args_digest():
            raise SurfaceNotReadyError("Cognitive request arguments differ from trusted binding")
        heads = self._heads(binding.action)
        profile = heads._head(binding.anchors.authority_id, EntityType.AUTHORITY_PROFILE, heads._records())
        if not isinstance(profile.payload, AuthorityProfilePayload) or profile.payload.human_ceiling_ref is not None:
            raise SurfaceNotReadyError("Cognitive request authority ceiling unresolved")
        return CognitiveRequestEnvelope(
            request_id=record.id,
            request_type=payload.request_type,
            purpose=payload.purpose,
            target=payload.target,
            expected_decision_impact=payload.expected_decision_impact,
            dimension=binding.action.dimension,
            resource_scope=binding.action.scope,
            action=binding.action,
            authority=AuthorityProfile.from_record(profile),
            risk=binding.action.risk,
        )
