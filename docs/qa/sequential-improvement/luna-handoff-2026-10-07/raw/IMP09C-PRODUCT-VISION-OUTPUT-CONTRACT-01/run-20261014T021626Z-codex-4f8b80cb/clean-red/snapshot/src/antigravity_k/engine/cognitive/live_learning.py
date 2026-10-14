"""Observed trial experience and held-out validation for local live pilots."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from antigravity_k.engine.cognitive.experience import (
    DecisionEvaluation,
    EpisodeEvaluations,
    EpisodeSignals,
    ExecutionEvaluation,
    ExperienceCore,
    ExperienceLedger,
    OperationalRecord,
    compare_outcome,
    evaluate_outcome,
)
from antigravity_k.engine.cognitive.growth import MATURE_CONTEXT_STEP, GrowthTask
from antigravity_k.engine.cognitive.learning import (
    CandidateKind,
    CandidateProposer,
    CandidateRequest,
    CandidateStore,
    EpisodeObservation,
    ExperienceEvaluator,
    HeldOutValidator,
    LearningCandidate,
    TriggerSource,
    ValidationCriterion,
    ValidationObservation,
    ValidationRole,
    ValidationSplit,
)
from antigravity_k.engine.cognitive.models import IntegrityStatus, OutcomeStatus, PolicyTarget, Producer
from antigravity_k.engine.cognitive.policy_store import PolicyStore
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore


@dataclass
class LiveLearning:
    """Mutable experiment ledger; only TRAIN contributes to candidate evidence."""

    project_id: str
    producer: Producer
    ledger: ExperienceLedger = field(default_factory=ExperienceLedger)
    policies: PolicyStore = field(default_factory=PolicyStore)
    candidates: CandidateStore = field(default_factory=CandidateStore)
    observations: list[EpisodeObservation] = field(default_factory=list)
    advisory_refs: tuple[str, ...] = ()
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def observe(
        self,
        task: GrowthTask,
        written: str,
        *,
        store: CanonicalStore,
        context_ref: str,
        judgment_ref: str | None,
        decision_ref: str,
        action_ref: str | None,
        observation_ref: str,
        outcome_ref: str,
        execution: ExecutionEvaluation,
    ) -> None:
        now = datetime.now(UTC)
        comparison = compare_outcome(task.append_content + "\n", written)
        episode_id = f"live-observed:{task.split.value}:{task.task_id}"
        record = OperationalRecord(
            record_id=f"operational:{episode_id}",
            episode_reference=episode_id,
            kind="FILE_READBACK",
            detail=written,
            recorded_at=now,
        )
        self.ledger.record_operational(record, project_id=self.project_id, producer=self.producer, created_at=now)
        selection = self.ledger.select(
            record,
            comparison=comparison,
            signals=EpisodeSignals(assumption_tested=True),
            producer=self.producer,
            recorded_at=now,
            evidence_refs=task.required_refs,
        )
        core = self.ledger.form_experience(
            selection,
            ExperienceCore(
                experience_id=new_id(EntityType.EXPERIENCE),
                episode_reference=episode_id,
                trigger="FILE_READBACK",
                context_ref=context_ref,
                judgment_ref=judgment_ref,
                decision_ref=decision_ref,
                action_ref=action_ref,
                observation_refs=(observation_ref,),
                outcome_ref=outcome_ref,
                evidence_refs=task.required_refs,
                integrity=IntegrityStatus.COMPLETE if judgment_ref and action_ref else IntegrityStatus.INCOMPLETE,
                missing_references=tuple(
                    name for name, ref in (("judgment_ref", judgment_ref), ("action_ref", action_ref)) if ref is None
                ),
            ),
            project_id=self.project_id,
            producer=self.producer,
            created_at=now,
        )
        self.observations.append(
            EpisodeObservation(
                episode_id=episode_id,
                task_id=task.task_id,
                raw_material_digest="sha256:" + hashlib.sha256((task.task_id + written).encode()).hexdigest(),
                evaluations=EpisodeEvaluations(
                    outcome=evaluate_outcome(comparison),
                    decision=DecisionEvaluation(OutcomeStatus.UNKNOWN, False, "No semantic decision assessment"),
                    execution=execution,
                ),
                experience_id=core.experience_id,
                evidence_ids=task.required_refs,
                producer=self.producer,
            )
        )
        pending = self.ledger.pending_sink_records()
        store.commit_records(
            (selection.to_record(project_id=self.project_id, created_at=now), *pending),
            message="observed live TRAIN experience",
        )
        self.ledger.mark_sunk(len(pending))
        self.advisory_refs = tuple(dict.fromkeys((*self.advisory_refs, *task.required_refs)))

    def propose(self) -> LearningCandidate:
        """Evaluate the preregistered context-depth hypothesis using TRAIN experience."""
        candidate = CandidateProposer(experience_lookup=self.ledger.core).propose(
            ExperienceEvaluator(experience_lookup=self.ledger.core).aggregate(self.observations),
            CandidateRequest(
                kind=CandidateKind.POLICY,
                rule="Increase context selection depth",
                scope="registered local live corpus",
                target=PolicyTarget.CONTEXT_DEPTH,
                parameters={"extra_depth": MATURE_CONTEXT_STEP},
                trigger_sources=(TriggerSource.HUMAN_REQUEST,),
                limitations=("Operator-prespecified hypothesis; no claim of autonomous semantic discovery",),
            ),
            project_id=self.project_id,
            producer=self.producer,
            created_at=datetime.now(UTC),
        )
        self.candidates.append(candidate)
        return candidate

    def validate(
        self,
        candidate: LearningCandidate,
        observations: tuple[ValidationObservation, ...],
        *,
        minimum: float,
        store: CanonicalStore,
    ) -> str | None:
        now = datetime.now(UTC)
        report = HeldOutValidator(experience_lookup=self.ledger.core).validate(
            candidate,
            split=ValidationSplit(
                split_id="live-validation",
                role=ValidationRole.VALIDATION,
                task_ids=tuple(item.task_id for item in observations),
                source="disjoint live validation",
                registered_at=self.registered_at,
                manifest_digest="live-validation",
            ),
            criterion=ValidationCriterion(
                experiment_id="local-live",
                metric_name="task_success",
                minimum_value=minimum,
                registered_at=self.registered_at,
                required_independent_episodes=2,
                minimum_samples=len(observations),
            ),
            observations=observations,
            generated_at=now,
        )
        self.candidates.add_report(report)
        if report.passed:
            policy = self.policies.register(
                candidate, report, version="live-validated-v1", producer=self.producer, created_at=now
            )
            self.policies.promote(
                policy.policy_id,
                version=policy.version,
                expected_active_version=None,
                actor=self.producer,
                reason="Disjoint live validation passed",
                occurred_at=now,
            )
        store.commit_records((*self.candidates.records, *self.policies.records), message="live candidate validation")
        active = self.policies.active_policy(PolicyTarget.CONTEXT_DEPTH)
        return active.version if active else None
