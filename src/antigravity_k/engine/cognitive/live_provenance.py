"""Canonical provenance for actual model choice, mechanical commit and file readback."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from antigravity_k.engine.cognitive.live_trial_types import ModelChoice
from antigravity_k.engine.cognitive.models import (
    BrainJudgmentPayload,
    DecisionAssurance,
    DecisionPayload,
    ObservationPayload,
    ObservationStatus,
    OutcomePayload,
    OutcomeStatus,
    Producer,
    ProducerKind,
    Record,
)
from antigravity_k.engine.cognitive.readiness import ReadinessResult
from antigravity_k.engine.cognitive.references import REL_GROUND, EntityType, Reference


@dataclass(frozen=True, slots=True)
class LiveProvenance:
    project_id: str
    model_id: str
    producer: Producer
    context_digest: str

    def decision_records(self, choice: ModelChoice, readiness: ReadinessResult) -> tuple[Record | None, Record]:
        """Preserve model bytes and mechanical readiness without inventing a semantic assessment."""
        now = datetime.now(UTC)
        raw = json.dumps(asdict(choice), sort_keys=True)
        judgment = (
            Record.create(
                entity_type=EntityType.BRAIN_JUDGMENT,
                project_id=self.project_id,
                producer=Producer(kind=ProducerKind.BRAIN, actor_id=self.model_id),
                payload=BrainJudgmentPayload(
                    current_judgment=raw,
                    grounds=choice.ground_refs,
                    confidence=0,
                    confidence_reason="Confidence was not requested or measured",
                    brain_version=self.model_id,
                    context_digest=self.context_digest,
                ),
                references=tuple(
                    Reference(relation=REL_GROUND, target_id=ref, expected_type=EntityType.EVIDENCE)
                    for ref in choice.ground_refs
                ),
                created_at=now,
            )
            if choice.ground_refs
            else None
        )
        fresh = readiness.freshness
        decision = Record.create(
            entity_type=EntityType.DECISION,
            project_id=self.project_id,
            producer=self.producer,
            payload=DecisionPayload(
                selected_action="fixture_write",
                why_selected="Dispatch the actual model-selected append bytes",
                expected_outcome=choice.append_content or "empty append",
                readiness=DecisionAssurance(
                    verdict=readiness.verdict,
                    check_results=readiness.checks,
                    decision_revision=fresh.decision_revision,
                    authority_revision=fresh.authority_revision,
                    action_digest=fresh.action_digest,
                    state_revision=fresh.state_revision,
                    policy_version=fresh.policy_version,
                ),
                unknowns_assessed=False,
                authority_revision=fresh.authority_revision,
            ),
            created_at=now,
        )
        return judgment, decision

    def readback_records(self, expected: str, written: str, *, available: bool) -> tuple[Record, Record]:
        now = datetime.now(UTC)
        observation = Record.create(
            entity_type=EntityType.OBSERVATION,
            project_id=self.project_id,
            producer=self.producer,
            payload=ObservationPayload(
                raw_measurement_or_handle=json.dumps(written) if available else "target does not exist",
                observed_at=now,
                method="file.read_text" if available else "Path.exists",
                source="isolated trial output",
                status=ObservationStatus.COMPLETE if available else ObservationStatus.UNAVAILABLE,
            ),
            created_at=now,
        )
        outcome = Record.create(
            entity_type=EntityType.OUTCOME,
            project_id=self.project_id,
            producer=self.producer,
            payload=OutcomePayload(
                expected=expected,
                observed=written,
                delta=None if written == expected else "readback differs",
                status=OutcomeStatus.MATCH if written == expected else OutcomeStatus.DEVIATION,
            ),
            created_at=now,
        )
        return observation, outcome
