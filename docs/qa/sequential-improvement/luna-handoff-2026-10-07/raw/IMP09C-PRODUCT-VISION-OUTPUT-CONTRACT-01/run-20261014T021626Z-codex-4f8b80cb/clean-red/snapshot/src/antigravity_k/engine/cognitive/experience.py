"""Experience 형성과 보존 (P08).

EXPERIENCE_AND_LEARNING.md와 Roadmap의 "Experience 선별과 보존" 계약을 구현한다.

- 필요한 Operational Record와 Observation을 **먼저 보존**하고 provenance를 연결한다.
- Expected↔Observed 비교와 현재 근거로 미래 판단에 재사용 가치가 있는지 평가한다.
- 가치가 없으면 Operational Record로 유지한다. 있다고 판단하면 근거와 **해석 주체**를 남겨
  Experience를 형성한다. 불명확하면 선별을 보류(DEFERRED)하고 후속 관찰과 연결할 수 있다.
- 고정된 원시 delta 임계값만으로 의미적 가치를 단정하지 않는다. 선별 입력에는 threshold가 없다.
- OutcomeEvaluation / DecisionEvaluation / ExecutionEvaluation은 서로 다른 절차다. 나중에 얻은
  지식으로 과거 판단을 자동 오판 처리하지 않는다.
- Historical Core는 append-only다. 재해석은 새 Interpretation version이고 기존 core digest는 그대로다.
- Experience 선별과 Knowledge/Policy 승격은 서로 다른 절차다(P09).

의미 해석은 Primary Brain 또는 명시된 human-assisted 경로가 수행한다. Body는 기계 비교까지만 한다.

이 모듈은 provider/UI/저장소를 import하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from antigravity_k.engine.cognitive.models import (
    ApplicabilityProfile,
    ConfidenceProfile,
    EventPayload,
    ExperiencePayload,
    IntegrityStatus,
    InterpretationPayload,
    LoopState,
    ObservationPayload,
    ObservationStatus,
    OutcomeStatus,
    Producer,
    ProducerKind,
    Record,
    SelectionDisposition,
    SelectionInfo,
    SelectionReason,
    same_enum,
)
from antigravity_k.engine.cognitive.references import (
    REL_ACTION,
    REL_CONTEXT,
    REL_DECISION,
    REL_EVIDENCE,
    REL_EXPERIENCE,
    REL_GOVERNANCE,
    REL_JUDGMENT,
    REL_OBSERVATION,
    REL_OUTCOME,
    REL_SUPERSEDES,
    EntityType,
    Reference,
    new_id,
)


class ExperienceContractError(ValueError):
    """Experience 계약 위반(선별 없는 형성, Body의 의미 해석 등)."""


#: 재사용 가치가 있다고 판단하는 사유.
EXPERIENCE_REASONS: Final[frozenset[SelectionReason]] = frozenset(
    {
        SelectionReason.MATERIAL_DELTA,
        SelectionReason.ASSUMPTION_TESTED,
        SelectionReason.UNKNOWN_CHANGED,
        SelectionReason.FAILURE,
        SelectionReason.RECOVERY,
        SelectionReason.RISK_SHAPING,
        SelectionReason.ROLLBACK,
        SelectionReason.ENVIRONMENT_DIFFERENCE,
        SelectionReason.HUMAN_FEEDBACK,
        SelectionReason.AUTHORITY_CHANGE,
        SelectionReason.INDEPENDENT_REVALIDATION,
    }
)

#: 판단이 어려워 보류하는 상태.
DEFERRED_OUTCOMES: Final[frozenset[OutcomeStatus]] = frozenset({OutcomeStatus.PENDING, OutcomeStatus.UNKNOWN})

#: 의미 해석을 수행할 수 있는 주체. Body는 기계 비교만 한다.
INTERPRETATION_AUTHORS: Final[frozenset[ProducerKind]] = frozenset({ProducerKind.BRAIN, ProducerKind.HUMAN})

#: 선별 disposition → episode가 머무는 loop 상태 표식. 별도 entity를 만들지 않는다.
SELECTION_STATE: Final[Mapping[SelectionDisposition, LoopState]] = {
    SelectionDisposition.EXPERIENCE: LoopState.EXPERIENCE,
    SelectionDisposition.DEFERRED: LoopState.OBSERVATION_PENDING,
    SelectionDisposition.OPERATIONAL_ONLY: LoopState.OBSERVE,
}


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class OperationalRecord:
    """운영 기록. Experience 여부와 무관하게 먼저 보존된다."""

    record_id: str
    episode_reference: str
    kind: str
    detail: str
    state: LoopState = LoopState.OBSERVE
    provenance_uri: str = ""
    provenance_digest: str = ""
    recorded_at: datetime | None = None
    producer: Producer | None = None
    sequence: int = 0

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "record_id": self.record_id,
            "episode_reference": self.episode_reference,
            "kind": self.kind,
            "detail": self.detail,
            "state": self.state.value,
            "provenance_uri": self.provenance_uri,
            "provenance_digest": self.provenance_digest,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at is not None else None,
        }

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(_canonical(self.as_mapping()).encode("utf-8")).hexdigest()

    def to_record(
        self, *, project_id: str, producer: Producer, created_at: datetime, state_revision: int = 1
    ) -> Record:
        return Record.create(
            entity_type=EntityType.EVENT,
            project_id=project_id,
            producer=producer,
            payload=EventPayload(
                sequence=self.sequence,
                episode_id=self.episode_reference,
                state=self.state,
                caused_by=self.record_id,
                state_revision=max(1, state_revision),
            ),
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class OutcomeComparison:
    """Expected ↔ Observed ↔ Delta. 기계적 비교만 담는다."""

    expected: str
    observed: str | None
    delta: str | None
    status: OutcomeStatus

    @property
    def matched_expected(self) -> bool:
        return same_enum(self.status, OutcomeStatus.MATCH)


@dataclass(frozen=True, slots=True)
class EpisodeSignals:
    """선별 판단에 쓰는 구조적 신호. delta 크기 같은 수치 임계값은 없다."""

    assumption_tested: bool = False
    unknown_changed: bool = False
    failure: bool = False
    recovery: bool = False
    risk_shaping: bool = False
    rollback: bool = False
    environment_difference: bool = False
    human_feedback: bool = False
    authority_change: bool = False
    independent_revalidation: bool = False
    unresolved: bool = False

    def reasons(self) -> tuple[SelectionReason, ...]:
        mapping = (
            (self.assumption_tested, SelectionReason.ASSUMPTION_TESTED),
            (self.unknown_changed, SelectionReason.UNKNOWN_CHANGED),
            (self.failure, SelectionReason.FAILURE),
            (self.recovery, SelectionReason.RECOVERY),
            (self.risk_shaping, SelectionReason.RISK_SHAPING),
            (self.rollback, SelectionReason.ROLLBACK),
            (self.environment_difference, SelectionReason.ENVIRONMENT_DIFFERENCE),
            (self.human_feedback, SelectionReason.HUMAN_FEEDBACK),
            (self.authority_change, SelectionReason.AUTHORITY_CHANGE),
            (self.independent_revalidation, SelectionReason.INDEPENDENT_REVALIDATION),
            (self.unresolved, SelectionReason.UNRESOLVED),
        )
        return tuple(reason for flag, reason in mapping if flag)


@dataclass(frozen=True, slots=True)
class ExperienceSelection:
    """선별 기록. episode reference·disposition·reason·evidence·producer·시각·policy version을 가진다."""

    episode_reference: str
    disposition: SelectionDisposition
    reasons: tuple[SelectionReason, ...]
    evidence_refs: tuple[str, ...]
    producer: Producer
    recorded_at: datetime
    policy_version: str | None = None
    note: str = ""

    @property
    def reusable(self) -> bool:
        return same_enum(self.disposition, SelectionDisposition.EXPERIENCE)

    def to_record(self, *, project_id: str, created_at: datetime, sequence: int = 0) -> Record:
        """선별 계약 필드(disposition·reason·evidence·policy version)를 Event에 그대로 실어
        canonical roundtrip이 가능하게 한다. producer·시각은 envelope이 소유한다."""

        return Record.create(
            entity_type=EntityType.EVENT,
            project_id=project_id,
            producer=self.producer,
            payload=EventPayload(
                sequence=sequence,
                episode_id=self.episode_reference,
                state=SELECTION_STATE[self.disposition],
                caused_by=self.episode_reference,
                state_revision=1,
                selection=SelectionInfo(
                    disposition=self.disposition,
                    reasons=self.reasons,
                    evidence_refs=self.evidence_refs,
                    policy_version=self.policy_version,
                    note=self.note,
                ),
            ),
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class ExperienceCore:
    """Historical Core — context/judgment/governance/decision/action/observation/outcome ID 연결."""

    experience_id: str
    episode_reference: str
    trigger: str
    context_ref: str | None = None
    judgment_ref: str | None = None
    governance_ref: str | None = None
    decision_ref: str | None = None
    action_ref: str | None = None
    observation_refs: tuple[str, ...] = ()
    outcome_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    remaining_unknowns: tuple[str, ...] = ()
    future_attention: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_references: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "experience_id": self.experience_id,
            "episode_reference": self.episode_reference,
            "trigger": self.trigger,
            "context_ref": self.context_ref,
            "judgment_ref": self.judgment_ref,
            "governance_ref": self.governance_ref,
            "decision_ref": self.decision_ref,
            "action_ref": self.action_ref,
            "observation_refs": list(self.observation_refs),
            "outcome_ref": self.outcome_ref,
            "evidence_refs": list(self.evidence_refs),
            "remaining_unknowns": list(self.remaining_unknowns),
            "future_attention": list(self.future_attention),
            "integrity": self.integrity.value,
            "missing_references": list(self.missing_references),
        }

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(_canonical(self.as_mapping()).encode("utf-8")).hexdigest()

    def material_digest(self) -> str:
        """Identify the same historical content independently of candidate ID allocation."""
        material = dict(self.as_mapping())
        del material["experience_id"]
        return "sha256:" + hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()

    def to_record(self, *, project_id: str, producer: Producer, created_at: datetime) -> Record:
        references = [
            # 당시 Context 계보는 타입으로 가리킨다(문자열 historical_refs에만 두면 계보가 아니라 메모다).
            (REL_CONTEXT, self.context_ref, EntityType.CONTEXT_PACKAGE),
            (REL_JUDGMENT, self.judgment_ref, EntityType.BRAIN_JUDGMENT),
            (REL_GOVERNANCE, self.governance_ref, EntityType.GOVERNANCE_DECISION),
            (REL_DECISION, self.decision_ref, EntityType.DECISION),
            (REL_ACTION, self.action_ref, EntityType.ACTION),
            (REL_OUTCOME, self.outcome_ref, EntityType.OUTCOME),
        ]
        refs = (
            tuple(
                Reference(relation=relation, target_id=target, expected_type=expected)
                for relation, target, expected in references
                if target is not None
            )
            + tuple(
                Reference(relation=REL_OBSERVATION, target_id=target, expected_type=EntityType.OBSERVATION)
                for target in self.observation_refs
            )
            + tuple(
                Reference(relation=REL_EVIDENCE, target_id=target, expected_type=EntityType.EVIDENCE)
                for target in self.evidence_refs
            )
        )
        return Record.create(
            entity_type=EntityType.EXPERIENCE,
            project_id=project_id,
            producer=producer,
            payload=ExperiencePayload(
                episode_reference=self.episode_reference,
                evidence_refs=self.evidence_refs,
                trigger=self.trigger,
                historical_refs=tuple(
                    ref for ref in (self.context_ref, self.judgment_ref, self.decision_ref, self.action_ref) if ref
                ),
                remaining_unknowns=self.remaining_unknowns,
                future_attention=self.future_attention,
                integrity=self.integrity,
                missing_references=self.missing_references,
            ),
            references=refs,
            record_id=self.experience_id,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class Interpretation:
    """Interpretation Layer — versioning되는 현 의미. Historical Core를 바꾸지 않는다."""

    interpretation_id: str
    experience_id: str
    revision: int
    author: Producer
    meaning: str
    confidence_profile: ConfidenceProfile
    applicability_profile: ApplicabilityProfile = field(default_factory=ApplicabilityProfile)
    evidence_ids: tuple[str, ...] = ()
    supersedes: str | None = None
    recorded_at: datetime | None = None

    def to_record(self, *, project_id: str, created_at: datetime) -> Record:
        refs: tuple[Reference, ...] = (
            Reference(relation=REL_EXPERIENCE, target_id=self.experience_id, expected_type=EntityType.EXPERIENCE),
        )
        if self.supersedes is not None:
            refs = (
                *refs,
                Reference(relation=REL_SUPERSEDES, target_id=self.supersedes, expected_type=EntityType.INTERPRETATION),
            )
        return Record.create(
            entity_type=EntityType.INTERPRETATION,
            project_id=project_id,
            producer=self.author,
            payload=InterpretationPayload(
                experience_id=self.experience_id,
                revision=self.revision,
                supersedes=self.supersedes,
                evidence_ids=self.evidence_ids,
                author=self.author,
                meaning=self.meaning,
                confidence_profile=self.confidence_profile,
                applicability_profile=self.applicability_profile,
            ),
            references=refs,
            record_id=self.interpretation_id,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class OutcomeEvaluation:
    """결과 자체에 대한 평가."""

    status: OutcomeStatus
    expected: str
    observed: str | None
    delta: str | None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionAssessment:
    """Primary/Human의 명시적 판단 평가. Body는 이 기록이 없으면 decision quality를 주장하지 않는다."""

    status: OutcomeStatus
    available_at_decision: bool
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    """당시 이용 가능했던 정보에 비춘 판단 평가."""

    status: OutcomeStatus
    available_at_decision: bool
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionEvaluation:
    """실행 품질 평가."""

    status: OutcomeStatus
    receipt_ref: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExperienceSupplement:
    """후속 관찰을 원본을 바꾸지 않고 연결한다."""

    supplement_id: str
    experience_id: str
    observation_ref: str
    note: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class EpisodeEvaluations:
    outcome: OutcomeEvaluation
    decision: DecisionEvaluation
    execution: ExecutionEvaluation

    @property
    def agrees(self) -> bool:
        return self.outcome.status is self.decision.status is self.execution.status


def compare_outcome(expected: str, observed: str | None, *, delta: str | None = None) -> OutcomeComparison:
    """Expected/Observed를 기계적으로 비교한다. 의미 해석은 하지 않는다."""

    if observed is None:
        return OutcomeComparison(expected=expected, observed=None, delta=delta, status=OutcomeStatus.UNKNOWN)
    if observed == expected:
        return OutcomeComparison(expected=expected, observed=observed, delta=delta, status=OutcomeStatus.MATCH)
    return OutcomeComparison(
        expected=expected,
        observed=observed,
        delta=delta if delta is not None else f"{expected} → {observed}",
        status=OutcomeStatus.DEVIATION,
    )


def evaluate_outcome(comparison: OutcomeComparison) -> OutcomeEvaluation:
    return OutcomeEvaluation(
        status=comparison.status,
        expected=comparison.expected,
        observed=comparison.observed,
        delta=comparison.delta,
    )


def evaluate_decision(
    comparison: OutcomeComparison,
    *,
    available_at_decision: bool | None = None,
    reason: str = "",
    evidence_refs: Sequence[str] = (),
    assessed_status: OutcomeStatus | None = None,
    assessment: DecisionAssessment | None = None,
) -> DecisionEvaluation:
    """결정 품질은 outcome과 별축이다. 명시 assessment가 없으면 UNKNOWN이다(readiness≠판단)."""

    if assessment is not None:
        return DecisionEvaluation(
            status=assessment.status,
            available_at_decision=assessment.available_at_decision,
            reason=assessment.reason,
            evidence_refs=tuple(assessment.evidence_refs),
        )
    if available_at_decision is None and assessed_status is None:
        return DecisionEvaluation(
            status=OutcomeStatus.UNKNOWN,
            available_at_decision=False,
            reason=reason or "decision quality unevaluated — readiness PASS is not semantic decision assessment",
            evidence_refs=tuple(evidence_refs),
        )
    if assessed_status is not None:
        return DecisionEvaluation(
            status=assessed_status,
            available_at_decision=bool(available_at_decision) if available_at_decision is not None else False,
            reason=reason,
            evidence_refs=tuple(evidence_refs),
        )
    # Explicit contemporaneous flag without separate status (legacy unit-test path).
    assert available_at_decision is not None
    if same_enum(comparison.status, OutcomeStatus.UNKNOWN):
        status = OutcomeStatus.UNKNOWN
    elif available_at_decision:
        status = OutcomeStatus.MATCH
    else:
        status = comparison.status
    return DecisionEvaluation(
        status=status,
        available_at_decision=available_at_decision,
        reason=reason,
        evidence_refs=tuple(evidence_refs),
    )


def evaluate_execution(
    *, succeeded: bool | None, receipt_ref: str | None = None, reason: str = ""
) -> ExecutionEvaluation:
    if succeeded is None:
        status = OutcomeStatus.UNKNOWN
    elif succeeded:
        status = OutcomeStatus.MATCH
    else:
        status = OutcomeStatus.FAILED
    return ExecutionEvaluation(status=status, receipt_ref=receipt_ref, reason=reason)


class ExperienceLedger:
    """Operational Record → 선별 → Experience → 해석/보충을 append-only로 관리한다."""

    def __init__(self) -> None:
        self._operational: list[OperationalRecord] = []
        self._selections: list[ExperienceSelection] = []
        self._cores: dict[str, ExperienceCore] = {}
        self._core_digests: dict[str, list[str]] = {}
        self._interpretations: dict[str, list[Interpretation]] = {}
        self._supplements: dict[str, list[ExperienceSupplement]] = {}
        self._records: list[Record] = []
        self._sunk_record_ids: set[str] = set()

    # ── 조회 ────────────────────────────────────────────
    @property
    def operational_records(self) -> tuple[OperationalRecord, ...]:
        return tuple(self._operational)

    @property
    def selections(self) -> tuple[ExperienceSelection, ...]:
        return tuple(self._selections)

    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    def pending_sink_records(self) -> tuple[Record, ...]:
        return tuple(record for record in self._records if record.id not in self._sunk_record_ids)

    def mark_sunk(self, count: int) -> None:
        if count < 0:
            raise ExperienceContractError("sink count must be non-negative")
        self._sunk_record_ids.update(record.id for record in self.pending_sink_records()[:count])

    def core(self, experience_id: str) -> ExperienceCore | None:
        return self._cores.get(experience_id)

    def core_digest_history(self, experience_id: str) -> tuple[str, ...]:
        return tuple(self._core_digests.get(experience_id, ()))

    def interpretations(self, experience_id: str) -> tuple[Interpretation, ...]:
        return tuple(self._interpretations.get(experience_id, ()))

    def supplements(self, experience_id: str) -> tuple[ExperienceSupplement, ...]:
        return tuple(self._supplements.get(experience_id, ()))

    # ── 보존·선별 ───────────────────────────────────────
    def record_operational(
        self,
        record: OperationalRecord,
        *,
        project_id: str = "",
        producer: Producer | None = None,
        created_at: datetime | None = None,
    ) -> OperationalRecord:
        """무엇을 선별하든 운영 기록을 먼저 보존한다. 덮어쓰지 않는다."""

        if any(existing.record_id == record.record_id for existing in self._operational):
            raise ExperienceContractError(f"duplicate operational record: {record.record_id}")
        self._operational.append(record)
        if project_id and producer is not None and created_at is not None:
            self._records.append(
                record.to_record(project_id=project_id, producer=producer, created_at=created_at, state_revision=1)
            )
        return record

    def select(
        self,
        record: OperationalRecord,
        *,
        comparison: OutcomeComparison,
        signals: EpisodeSignals,
        producer: Producer,
        recorded_at: datetime,
        evidence_refs: Sequence[str] = (),
        policy_version: str | None = None,
        note: str = "",
    ) -> ExperienceSelection:
        """재사용 가치를 평가한다. 확신할 수 없으면 DEFERRED로 남기고 후속 관찰에 연결한다."""

        if not any(existing.record_id == record.record_id for existing in self._operational):
            raise ExperienceContractError("Operational Record를 먼저 보존해야 선별할 수 있다")

        reasons = list(signals.reasons())
        if same_enum(comparison.status, OutcomeStatus.DEVIATION) and SelectionReason.MATERIAL_DELTA not in reasons:
            reasons.append(SelectionReason.MATERIAL_DELTA)
        if comparison.status in DEFERRED_OUTCOMES and SelectionReason.UNRESOLVED not in reasons:
            reasons.append(SelectionReason.UNRESOLVED)

        if SelectionReason.UNRESOLVED in reasons:
            disposition = SelectionDisposition.DEFERRED
        elif any(reason in EXPERIENCE_REASONS for reason in reasons):
            disposition = SelectionDisposition.EXPERIENCE
        else:
            disposition = SelectionDisposition.OPERATIONAL_ONLY
            reasons.append(SelectionReason.ROUTINE)

        selection = ExperienceSelection(
            episode_reference=record.episode_reference,
            disposition=disposition,
            reasons=tuple(dict.fromkeys(reasons)),
            evidence_refs=tuple(evidence_refs),
            producer=producer,
            recorded_at=recorded_at,
            policy_version=policy_version,
            note=note,
        )
        self._selections.append(selection)
        return selection

    def form_experience(
        self,
        selection: ExperienceSelection,
        core: ExperienceCore,
        *,
        project_id: str,
        producer: Producer,
        created_at: datetime,
    ) -> ExperienceCore:
        """EXPERIENCE로 선별된 경우에만 Experience를 형성한다. 지식 승격은 여기서 하지 않는다."""

        if not same_enum(selection.disposition, SelectionDisposition.EXPERIENCE):
            raise ExperienceContractError(f"{selection.disposition} 선별로는 Experience를 형성하지 않는다")
        if core.episode_reference != selection.episode_reference:
            raise ExperienceContractError("Experience core가 선별된 episode와 다르다")
        digest = core.digest()
        for existing in self._cores.values():
            if existing.material_digest() == core.material_digest():
                return existing
        if core.experience_id in self._cores:
            raise ExperienceContractError(f"duplicate experience: {core.experience_id}")
        self._cores[core.experience_id] = core
        self._core_digests.setdefault(core.experience_id, []).append(digest)
        self._records.append(core.to_record(project_id=project_id, producer=producer, created_at=created_at))
        return core

    def cores_for_episode(self, episode_reference: str) -> tuple[ExperienceCore, ...]:
        return tuple(core for core in self._cores.values() if core.episode_reference == episode_reference)

    def ingest_core_record(self, record: Record, *, episode_reference: str = "") -> ExperienceCore:
        """Provider-neutral reader: rebuild an ExperienceCore from a committed Experience record."""
        if not same_enum(record.entity_type, EntityType.EXPERIENCE):
            raise ExperienceContractError("not an Experience record")
        payload = record.payload
        resolved_episode = getattr(payload, "episode_reference", None) or episode_reference
        if episode_reference and resolved_episode != episode_reference:
            raise ExperienceContractError("committed episode reference conflicts with supplied episode")
        missing = tuple(getattr(payload, "missing_references", ()))
        if not resolved_episode:
            missing = tuple(dict.fromkeys((*missing, "episode_reference")))
        by_rel = {ref.relation: ref.target_id for ref in record.references}
        obs = tuple(ref.target_id for ref in record.references if ref.relation == REL_OBSERVATION)
        core = ExperienceCore(
            experience_id=record.id,
            episode_reference=resolved_episode,
            trigger=str(getattr(payload, "trigger", "") or "ingested"),
            context_ref=by_rel.get(REL_CONTEXT),
            judgment_ref=by_rel.get(REL_JUDGMENT),
            governance_ref=by_rel.get(REL_GOVERNANCE),
            decision_ref=by_rel.get(REL_DECISION),
            action_ref=by_rel.get(REL_ACTION),
            observation_refs=obs,
            outcome_ref=by_rel.get(REL_OUTCOME),
            evidence_refs=tuple(getattr(payload, "evidence_refs", ())),
            remaining_unknowns=tuple(getattr(payload, "remaining_unknowns", ()) or ()),
            future_attention=tuple(getattr(payload, "future_attention", ()) or ()),
            integrity=IntegrityStatus.INCOMPLETE
            if missing
            else getattr(payload, "integrity", IntegrityStatus.COMPLETE),
            missing_references=missing,
        )
        if core.experience_id in self._cores:
            existing = self._cores[core.experience_id]
            if existing != core:
                raise ExperienceContractError(f"conflicting committed experience: {core.experience_id}")
            self._sunk_record_ids.add(record.id)
            return existing
        self._cores[core.experience_id] = core
        self._core_digests.setdefault(core.experience_id, []).append(core.digest())
        if record not in self._records:
            self._records.append(record)
        self._sunk_record_ids.add(record.id)
        return core

    # ── 해석·보충 ───────────────────────────────────────
    def interpret(
        self,
        experience_id: str,
        *,
        author: Producer,
        meaning: str,
        confidence_profile: ConfidenceProfile,
        applicability_profile: ApplicabilityProfile | None = None,
        evidence_ids: Sequence[str] = (),
        recorded_at: datetime,
        project_id: str = "",
        created_at: datetime | None = None,
    ) -> Interpretation:
        """재해석은 새 version이다. 기존 core digest는 변하지 않는다."""

        core = self._cores.get(experience_id)
        if core is None:
            raise ExperienceContractError(f"unknown experience: {experience_id}")
        if author.kind not in INTERPRETATION_AUTHORS:
            raise ExperienceContractError(
                f"{author.kind}는 의미 해석 주체가 아니다 — Primary Brain 또는 human-assisted 경로가 담당한다"
            )
        if not meaning:
            raise ExperienceContractError("interpretation에는 meaning이 필요하다")

        existing = self._interpretations.setdefault(experience_id, [])
        revision = (existing[-1].revision + 1) if existing else 1
        interpretation = Interpretation(
            interpretation_id=new_id(EntityType.INTERPRETATION),
            experience_id=experience_id,
            revision=revision,
            author=author,
            meaning=meaning,
            confidence_profile=confidence_profile,
            applicability_profile=applicability_profile or ApplicabilityProfile(),
            evidence_ids=tuple(evidence_ids),
            supersedes=existing[-1].interpretation_id if existing else None,
            recorded_at=recorded_at,
        )
        existing.append(interpretation)
        if project_id and created_at is not None:
            self._records.append(interpretation.to_record(project_id=project_id, created_at=created_at))
        return interpretation

    def supplement(
        self,
        experience_id: str,
        *,
        observation: Record,
        note: str,
        recorded_at: datetime,
    ) -> ExperienceSupplement:
        """지연·후속 관찰을 append한다. 원본 Experience bytes는 그대로다."""

        if experience_id not in self._cores:
            raise ExperienceContractError(f"unknown experience: {experience_id}")
        if not same_enum(observation.entity_type, EntityType.OBSERVATION):
            raise ExperienceContractError("supplement는 Observation record로만 연결한다")
        supplement = ExperienceSupplement(
            supplement_id=f"supplement:{experience_id}:{len(self._supplements.get(experience_id, [])) + 1}",
            experience_id=experience_id,
            observation_ref=observation.id,
            note=note,
            recorded_at=recorded_at,
        )
        self._supplements.setdefault(experience_id, []).append(supplement)
        self._records.append(observation)
        return supplement


def observation_record(
    *,
    project_id: str,
    producer: Producer,
    raw: str,
    method: str,
    source: str,
    observed_at: datetime,
    status: ObservationStatus = ObservationStatus.COMPLETE,
) -> Record:
    """관측은 원시값만 담는다. 해석은 Interpretation으로 분리한다."""

    return Record.create(
        entity_type=EntityType.OBSERVATION,
        project_id=project_id,
        producer=producer,
        payload=ObservationPayload(
            raw_measurement_or_handle=raw,
            observed_at=observed_at,
            method=method,
            source=source,
            status=status,
        ),
        created_at=observed_at,
    )


__all__ = [
    "DEFERRED_OUTCOMES",
    "EXPERIENCE_REASONS",
    "INTERPRETATION_AUTHORS",
    "SELECTION_STATE",
    "DecisionAssessment",
    "DecisionEvaluation",
    "EpisodeEvaluations",
    "EpisodeSignals",
    "ExecutionEvaluation",
    "ExperienceContractError",
    "ExperienceCore",
    "ExperienceLedger",
    "ExperienceSelection",
    "ExperienceSupplement",
    "Interpretation",
    "OperationalRecord",
    "OutcomeComparison",
    "OutcomeEvaluation",
    "SelectionDisposition",
    "SelectionReason",
    "compare_outcome",
    "evaluate_decision",
    "evaluate_execution",
    "evaluate_outcome",
    "observation_record",
]
