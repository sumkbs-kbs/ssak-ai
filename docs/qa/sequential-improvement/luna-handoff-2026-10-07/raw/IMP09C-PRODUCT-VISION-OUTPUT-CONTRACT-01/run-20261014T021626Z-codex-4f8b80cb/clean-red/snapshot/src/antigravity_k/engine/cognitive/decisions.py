"""Decision lifecycle (P06) — closure, reopen, reassessment를 append로만 남긴다.

원문 §17 Decision Closure / §18 Reopening의 실행 계약을 구현한다.

- Closure는 "현재 추가 Cognition보다 Action 또는 Reality Feedback의 Expected Value가 더 크다"는 뜻이다.
  COMMIT readiness(READY/READY_WITH_GUARDS)를 통과한 결정만 닫을 수 있다.
- Reopen은 **material trigger**만 가능하다. 실제 evidence reference와 smallest justified scope가
  없으면 거부한다. 단순 불안·표현 변경은 trigger가 아니다.
- Human reopen은 즉시 허용하되 원본 이력을 보존한다.
- 이미 발생한 외부 행동을 되돌린 것으로 가정하지 않는다(``claims_effects_reverted``는 거부된다).
- DecisionClosed/Reopened/Reassessment는 append-only event다. 옛 DecisionTrace는 수정하지 않고
  digest만 기록한다.

이 모듈은 provider/UI/저장소를 import하지 않는다. event → canonical payload 변환만 제공하고
실제 영속화는 P08/P11이 연결한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from antigravity_k.engine.cognitive.models import (
    ClosureState,
    DecisionPayload,
    ProducerKind,
    ReadinessVerdict,
    ReassessmentPayload,
    Record,
    ReopenTrigger,
    same_enum,
)
from antigravity_k.engine.cognitive.readiness import FreshnessBinding, ReadinessResult
from antigravity_k.engine.cognitive.references import REL_GROUND, EntityType

#: material trigger로 인정하는 원문 §18 목록. Human reopen은 evidence 없이도 허용한다.
MATERIAL_REOPEN_TRIGGERS: Final[frozenset[ReopenTrigger]] = frozenset(ReopenTrigger)

#: 사람이 직접 연 경우. 즉시 허용하되 원본 이력은 그대로 둔다.
HUMAN_TRIGGER: Final[ReopenTrigger] = ReopenTrigger.HUMAN_REOPEN


class DecisionLifecycleError(RuntimeError):
    """closure/reopen 계약 위반."""


class ReopenRefused(DecisionLifecycleError):
    """material하지 않거나 중복된 reopen 시도."""


def _digest(payload: Mapping[str, object]) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    """원문 §17이 요구하는 Decision Trace 최소 구성. 이 객체는 만들어진 뒤 변경하지 않는다."""

    decision_id: str
    project_id: str
    decision_revision: int
    selected_action: str
    why_selected: str
    expected_outcome: str
    action_digest: str
    grounds: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    why_not_selected: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    risks: Mapping[str, str] = field(default_factory=dict)
    authority_revision: int | None = None
    state_revision: int = 1
    policy_version: str | None = None
    closure: ClosureState = ClosureState.OPEN
    reopen_triggers: tuple[ReopenTrigger, ...] = ()
    context_digest: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "decision_revision": self.decision_revision,
            "selected_action": self.selected_action,
            "why_selected": self.why_selected,
            "expected_outcome": self.expected_outcome,
            "action_digest": self.action_digest,
            "grounds": list(self.grounds),
            "alternatives": list(self.alternatives),
            "why_not_selected": list(self.why_not_selected),
            "evidence_ids": list(self.evidence_ids),
            "unknowns": list(self.unknowns),
            "risks": dict(self.risks),
            "authority_revision": self.authority_revision,
            "state_revision": self.state_revision,
            "policy_version": self.policy_version,
            "closure": self.closure.value,
            "reopen_triggers": [trigger.value for trigger in self.reopen_triggers],
            "context_digest": self.context_digest,
        }

    def digest(self) -> str:
        """이 trace의 불변 digest. reopen 뒤에도 같은 값을 유지해야 한다."""

        return _digest(self.as_mapping())

    @property
    def open_for_action(self) -> bool:
        return same_enum(self.closure, ClosureState.OPEN)

    @classmethod
    def from_record(cls, record: Record) -> DecisionTrace:
        if not same_enum(record.entity_type, EntityType.DECISION):
            raise DecisionLifecycleError(f"record is not a Decision: {record.entity_type}")
        payload = record.payload
        if not isinstance(payload, DecisionPayload):
            raise DecisionLifecycleError("Decision record payload mismatch")
        grounds = tuple(reference.target_id for reference in record.references if reference.relation == REL_GROUND)
        evidence_ids = tuple(
            reference.target_id
            for reference in record.references
            if reference.relation == REL_GROUND and same_enum(reference.expected_type, EntityType.EVIDENCE)
        )
        return cls(
            decision_id=record.id,
            project_id=record.project_id,
            decision_revision=payload.readiness.decision_revision,
            selected_action=payload.selected_action,
            why_selected=payload.why_selected,
            expected_outcome=payload.expected_outcome,
            action_digest=payload.readiness.action_digest or "",
            grounds=grounds,
            alternatives=(),
            evidence_ids=evidence_ids,
            why_not_selected=payload.why_not_selected,
            risks={result.check.value: result.status.value for result in payload.readiness.check_results},
            authority_revision=payload.authority_revision,
            state_revision=payload.readiness.state_revision,
            policy_version=payload.readiness.policy_version,
            closure=payload.closure,
            reopen_triggers=payload.reopen_triggers,
        )


@dataclass(frozen=True, slots=True)
class ClosureEvent:
    """DecisionClosed는 append-only 사건이다."""

    event_id: str
    decision_id: str
    project_id: str
    sequence: int
    occurred_at: datetime
    trace_digest: str
    readiness_verdict: ReadinessVerdict
    freshness: FreshnessBinding
    guards: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    blocking_conditions: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "event_id": self.event_id,
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "trace_digest": self.trace_digest,
            "readiness_verdict": self.readiness_verdict.value,
            "freshness": self.freshness.as_mapping(),
            "guards": list(self.guards),
            "limits": list(self.limits),
            "blocking_conditions": list(self.blocking_conditions),
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


@dataclass(frozen=True, slots=True)
class ReopenRequest:
    trigger: ReopenTrigger
    trigger_evidence_ids: tuple[str, ...]
    smallest_scope: str
    rationale: str
    actor_kind: ProducerKind = ProducerKind.BODY
    actions_already_dispatched: tuple[str, ...] = ()
    claims_effects_reverted: bool = False


@dataclass(frozen=True, slots=True)
class ReopenEvent:
    """Reopened는 trigger evidence와 smallest scope를 기록한 새 사건이다."""

    event_id: str
    decision_id: str
    project_id: str
    sequence: int
    occurred_at: datetime
    trace_digest: str
    trigger: ReopenTrigger
    trigger_evidence_ids: tuple[str, ...]
    smallest_scope: str
    rationale: str
    actor_kind: ProducerKind
    supersedes_event_id: str
    state_revision: int
    actions_already_dispatched: tuple[str, ...] = ()
    #: 이미 발생한 외부 행동은 되돌린 것으로 가정하지 않는다.
    assumes_effects_reverted: bool = False

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "event_id": self.event_id,
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "trace_digest": self.trace_digest,
            "trigger": self.trigger.value,
            "trigger_evidence_ids": list(self.trigger_evidence_ids),
            "smallest_scope": self.smallest_scope,
            "rationale": self.rationale,
            "actor_kind": self.actor_kind.value,
            "supersedes_event_id": self.supersedes_event_id,
            "state_revision": self.state_revision,
            "actions_already_dispatched": list(self.actions_already_dispatched),
            "assumes_effects_reverted": self.assumes_effects_reverted,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())

    def as_reassessment_payload(
        self, *, changed_understanding: str, evidence_ids: Sequence[str] = ()
    ) -> ReassessmentPayload:
        """store가 Reassessment record로 남길 수 있는 payload로 옮긴다."""

        return ReassessmentPayload(
            target_record_id=self.decision_id,
            trigger=self.trigger,
            changed_understanding=changed_understanding,
            evidence_ids=tuple(dict.fromkeys((*self.trigger_evidence_ids, *evidence_ids))),
            smallest_scope=self.smallest_scope,
            resolution="",
        )


@dataclass(frozen=True, slots=True)
class ReassessmentEvent:
    """기존 결정을 덮어쓰지 않고 새 판단을 별도 ID로 연결한다."""

    event_id: str
    decision_id: str
    new_decision_id: str
    sequence: int
    occurred_at: datetime
    trigger: ReopenTrigger
    changed_understanding: str
    evidence_ids: tuple[str, ...]
    smallest_scope: str
    previous_trace_digest: str

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "event_id": self.event_id,
            "decision_id": self.decision_id,
            "new_decision_id": self.new_decision_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "trigger": self.trigger.value,
            "changed_understanding": self.changed_understanding,
            "evidence_ids": list(self.evidence_ids),
            "smallest_scope": self.smallest_scope,
            "previous_trace_digest": self.previous_trace_digest,
        }

    def digest(self) -> str:
        return _digest(self.as_mapping())


LifecycleEvent = ClosureEvent | ReopenEvent | ReassessmentEvent


class DecisionLedger:
    """append-only decision lifecycle ledger.

    저장소는 소유하지 않는다(P08/P11이 store에 연결한다). 이 ledger는 순서·중복·digest 보존을
    강제하는 계약 구현이며, semantic 재심사를 하지 않는다.
    """

    def __init__(self) -> None:
        self._events: list[LifecycleEvent] = []
        self._sequence = 0
        self._trace_digests: dict[str, list[str]] = {}
        self._reopens: set[tuple[str, str, tuple[str, ...]]] = set()
        self._closed: set[str] = set()

    # ── 조회 ────────────────────────────────────────────
    @property
    def events(self) -> tuple[LifecycleEvent, ...]:
        return tuple(self._events)

    def trace_digest_history(self, decision_id: str) -> tuple[str, ...]:
        """reopen 뒤에도 옛 trace digest가 그대로 남아 있는지 확인한다."""

        return tuple(self._trace_digests.get(decision_id, ()))

    # ── closure ─────────────────────────────────────────
    def close(
        self,
        trace: DecisionTrace,
        readiness: ReadinessResult,
        *,
        occurred_at: datetime,
        current_freshness: FreshnessBinding | None = None,
        event_id: str | None = None,
    ) -> ClosureEvent:
        """readiness를 통과한 결정만 닫는다. readiness 밖의 판단은 하지 않는다."""

        if same_enum(readiness.verdict, ReadinessVerdict.NOT_READY):
            raise DecisionLifecycleError(f"NOT_READY 결정은 닫을 수 없다: {list(readiness.blocking_conditions)}")
        freshness = current_freshness if current_freshness is not None else readiness.freshness
        changed = readiness.freshness.changed_fields(freshness)
        if changed:
            raise DecisionLifecycleError(f"COMMIT 이후 stale 상태다: {list(changed)}")
        if trace.action_digest and readiness.freshness.action_digest != trace.action_digest:
            raise DecisionLifecycleError("readiness와 decision trace의 action digest가 다르다")

        self._sequence += 1
        event = ClosureEvent(
            event_id=event_id or f"closure:{trace.decision_id}:{self._sequence}",
            decision_id=trace.decision_id,
            project_id=trace.project_id,
            sequence=self._sequence,
            occurred_at=occurred_at,
            trace_digest=trace.digest(),
            readiness_verdict=readiness.verdict,
            freshness=readiness.freshness,
            guards=tuple(receipt.guard.value for receipt in readiness.guards),
            limits=readiness.limits,
            blocking_conditions=readiness.blocking_conditions,
        )
        self._events.append(event)
        self._trace_digests.setdefault(trace.decision_id, []).append(event.trace_digest)
        self._closed.add(trace.decision_id)
        return event

    # ── reopen ──────────────────────────────────────────
    def reopen(
        self,
        trace: DecisionTrace,
        request: ReopenRequest,
        *,
        occurred_at: datetime,
        supersedes_event_id: str = "",
        event_id: str | None = None,
    ) -> ReopenEvent:
        """material trigger와 smallest scope가 있어야 다시 연다. 원본 trace는 그대로 둔다."""

        if not request.smallest_scope:
            raise ReopenRefused("smallest justified scope 없이 reopen할 수 없다")
        if not request.rationale:
            raise ReopenRefused("reopen에는 변경된 이해에 대한 설명이 필요하다")
        if request.trigger is not HUMAN_TRIGGER and not request.trigger_evidence_ids:
            raise ReopenRefused(f"{request.trigger.value} reopen에는 material evidence reference가 필요하다")
        if request.claims_effects_reverted:
            raise ReopenRefused("이미 발생한 외부 행동을 되돌린 것으로 가정할 수 없다")
        key = (trace.decision_id, request.trigger.value, tuple(sorted(request.trigger_evidence_ids)))
        if key in self._reopens:
            raise ReopenRefused("같은 trigger와 evidence로 반복 reopen할 수 없다")

        self._sequence += 1
        event = ReopenEvent(
            event_id=event_id or f"reopen:{trace.decision_id}:{self._sequence}",
            decision_id=trace.decision_id,
            project_id=trace.project_id,
            sequence=self._sequence,
            occurred_at=occurred_at,
            trace_digest=trace.digest(),
            trigger=request.trigger,
            trigger_evidence_ids=request.trigger_evidence_ids,
            smallest_scope=request.smallest_scope,
            rationale=request.rationale,
            actor_kind=request.actor_kind,
            supersedes_event_id=supersedes_event_id,
            state_revision=trace.state_revision,
            actions_already_dispatched=request.actions_already_dispatched,
            assumes_effects_reverted=False,
        )
        self._events.append(event)
        self._reopens.add(key)
        return event

    # ── reassessment ────────────────────────────────────
    def reassess(
        self,
        trace: DecisionTrace,
        reopen_event: ReopenEvent,
        *,
        new_decision_id: str,
        changed_understanding: str,
        evidence_ids: Sequence[str] = (),
        occurred_at: datetime,
        event_id: str | None = None,
    ) -> ReassessmentEvent:
        """재평가는 새 ID로 연결한다. 원래 trace digest는 그대로 남는다."""

        if not new_decision_id:
            raise DecisionLifecycleError("reassessment는 새 decision ID를 만들어야 한다")
        if new_decision_id == trace.decision_id:
            raise DecisionLifecycleError("원래 decision을 수정하는 방식의 재평가는 허용되지 않는다")
        if not changed_understanding:
            raise DecisionLifecycleError("reassessment에는 변경된 이해가 필요하다")

        self._sequence += 1
        event = ReassessmentEvent(
            event_id=event_id or f"reassess:{trace.decision_id}:{self._sequence}",
            decision_id=trace.decision_id,
            new_decision_id=new_decision_id,
            sequence=self._sequence,
            occurred_at=occurred_at,
            trigger=reopen_event.trigger,
            changed_understanding=changed_understanding,
            evidence_ids=tuple(dict.fromkeys((*reopen_event.trigger_evidence_ids, *evidence_ids))),
            smallest_scope=reopen_event.smallest_scope,
            previous_trace_digest=reopen_event.trace_digest,
        )
        self._events.append(event)
        return event


__all__ = [
    "HUMAN_TRIGGER",
    "MATERIAL_REOPEN_TRIGGERS",
    "ClosureEvent",
    "DecisionLedger",
    "DecisionLifecycleError",
    "DecisionTrace",
    "LifecycleEvent",
    "ReassessmentEvent",
    "ReopenEvent",
    "ReopenRefused",
    "ReopenRequest",
]
