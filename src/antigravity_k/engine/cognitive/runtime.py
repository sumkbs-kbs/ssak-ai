"""Cognitive runtime (P08) — 최소 운영 루프와 episode 형성.

COGNITIVE_OPERATING_LOOP.md의 상태 전이표를 구현한다.

```text
PREPARE → THINK → (GOVERN → EXECUTE → FEEDBACK → TARGETED_RETHINK)* → COMMIT → ACTION → OBSERVE → EXPERIENCE
```

- 모든 단계를 강제하지 않는다. Simple Task는 ``PREPARE → THINK → COMMIT → ACTION``으로 끝난다.
- Expansion budget(rounds·동일 signature 반복·repair)과 request signature로 반복 사고를 제한한다.
  새 ID만 생기고 material cognitive delta가 없으면 stop이다.
- **Stop은 READY가 아니다.** readiness 부족이면 ``BLOCKED_READINESS``/``DEFERRED`` 또는 안전한 축소
  action으로 끝난다. 자동 READY도 무한 재평가도 없다.
- deferred observation은 ``OBSERVATION_PENDING``으로 남기고 Experience 선별로 넘긴다.
- 취소·BLOCKED·실패·대기는 서로 다른 종료 사유다.

opt-in이다. 실행 port가 주입되지 않으면 아무 것도 dispatch하지 않고, legacy ``CognitiveLoop``/orchestrator를
수정하지 않는다(ADR-0004). 이 모듈은 provider/UI/저장소를 import하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionIntent,
    ActionObservation,
    ActionRun,
)
from antigravity_k.engine.cognitive.authority import AuthorityProfile
from antigravity_k.engine.cognitive.experience import (
    DecisionAssessment,
    EpisodeEvaluations,
    EpisodeSignals,
    ExperienceCore,
    ExperienceLedger,
    ExperienceSelection,
    OperationalRecord,
    OutcomeComparison,
    compare_outcome,
    evaluate_decision,
    evaluate_execution,
    evaluate_outcome,
)
from antigravity_k.engine.cognitive.governance import (
    GovernanceGate,
    GovernanceRequest,
    RequestedAction,
    UnknownAssessment,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    AuthorityDimension,
    CognitiveRequestType,
    EventPayload,
    GovernanceDisposition,
    LoopState,
    Producer,
    ProducerKind,
    Record,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.readiness import ReadinessGate, ReadinessResult
from antigravity_k.engine.cognitive.references import EntityType, is_canonical_id, new_id

#: v1 기본 예산. 헌법이 아니라 task별로 조정 가능한 값이다.
DEFAULT_EXPANSION_ROUNDS: Final[int] = 3
DEFAULT_REPEAT_SIGNATURE_LIMIT: Final[int] = 1


class EpisodeTermination(StrEnum):
    """episode의 종료 사유. BLOCKED/FAILED/CANCELLED/WAITING을 섞지 않는다."""

    COMPLETED = "COMPLETED"
    STOPPED_NO_DELTA = "STOPPED_NO_DELTA"
    STOPPED_BUDGET = "STOPPED_BUDGET"
    BLOCKED_CONTEXT = "BLOCKED_CONTEXT"
    BLOCKED_READINESS = "BLOCKED_READINESS"
    BRAIN_FAILED = "BRAIN_FAILED"
    DEFERRED = "DEFERRED"
    REFUSED_ACTION = "REFUSED_ACTION"
    ACTION_OUTCOME_UNKNOWN = "ACTION_OUTCOME_UNKNOWN"
    OBSERVATION_PENDING = "OBSERVATION_PENDING"


@dataclass(frozen=True, slots=True)
class EpisodeBudget:
    expansion_rounds: int = DEFAULT_EXPANSION_ROUNDS
    repeat_signature_limit: int = DEFAULT_REPEAT_SIGNATURE_LIMIT
    max_total_requests: int = 32


@dataclass(frozen=True, slots=True)
class EpisodeDelta:
    """Material Cognitive Delta 여부. Body는 항목 유무만 보고 의미 크기는 Primary 설명을 따른다."""

    judgment: bool = False
    ground: bool = False
    alternative: bool = False
    unknown: bool = False
    risk: bool = False
    action: bool = False
    description: str = ""

    @property
    def material(self) -> bool:
        return any((self.judgment, self.ground, self.alternative, self.unknown, self.risk, self.action))


@dataclass(frozen=True, slots=True)
class ThinkOutcome:
    judgment_ref: str
    requests: tuple[CognitiveRequestEnvelope, ...] = ()
    delta: EpisodeDelta | None = None
    detail: str = ""
    failed: bool = False
    plan: EpisodePlan | None = None


@runtime_checkable
class ThinkPort(Protocol):
    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome: ...


@runtime_checkable
class RethinkPort(Protocol):
    def rethink(
        self,
        *,
        previous_judgment_ref: str,
        feedback_refs: Sequence[str],
        affected_grounds: Sequence[str],
        round_index: int,
    ) -> ThinkOutcome: ...


@dataclass(frozen=True, slots=True)
class CognitiveRequestEnvelope:
    """Brain의 Cognitive Request. 요청 단위 EXECUTE도 같은 권한·receipt 경계를 지난다."""

    request_id: str
    request_type: CognitiveRequestType
    purpose: str
    target: str
    expected_decision_impact: str
    dimension: AuthorityDimension = AuthorityDimension.TOOL_READ
    resource_scope: str = ""
    evidence_revision: str = ""
    action: ActionIntent | None = None
    authority: AuthorityProfile | None = None
    unknowns: tuple[UnknownAssessment, ...] = ()
    advisory_notes: tuple[str, ...] = ()
    risk: RiskProfile = field(default_factory=RiskProfile)

    def signature(self) -> str:
        """request type + target + normalized args + purpose + evidence revision."""

        arguments: dict[str, object] = {}
        if self.action is not None:
            arguments = {str(key): self.action.arguments[key] for key in sorted(self.action.arguments)}
        payload = {
            "request_type": self.request_type.value,
            "target": self.target.strip(),
            "purpose": self.purpose.strip(),
            "evidence_revision": self.evidence_revision,
            "arguments": arguments,
        }
        return (
            "sha256:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        )

    def to_requested_action(self) -> RequestedAction:
        return RequestedAction(
            tool=self.action.tool if self.action is not None else self.request_type.value,
            operation="execute_tool",
            dimension=self.dimension,
            resource_scope=self.action.scope
            if self.action is not None and self.action.scope
            else (self.resource_scope or self.target),
            arguments=dict(self.action.arguments) if self.action is not None else {},
            risk=self.risk,
            reversible=self.action.reversible if self.action is not None else True,
        )


@dataclass(frozen=True, slots=True)
class RequestFeedback:
    """요청별 처리 결과. GOVERN/EXECUTE/FEEDBACK 단계가 남기는 최소 기록."""

    request_id: str
    request_signature: str
    disposition: str
    executed: bool
    detail: str = ""
    receipt_ref: str | None = None
    effects_observed: bool | None = None


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    """전이는 episode_id·event_id·sequence·caused_by·state_revision을 가진다."""

    event_id: str
    episode_id: str
    sequence: int
    state: LoopState
    caused_by: str
    state_revision: int
    detail: str = ""
    occurred_at: datetime | None = None

    def to_record(self, *, project_id: str, producer: Producer, created_at: datetime) -> Record:
        return Record.create(
            entity_type=EntityType.EVENT,
            project_id=project_id,
            producer=producer,
            payload=EventPayload(
                sequence=self.sequence,
                episode_id=self.episode_id,
                state=self.state,
                caused_by=self.caused_by,
                state_revision=max(1, self.state_revision),
            ),
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class EpisodeCounters:
    """sparse activation 확인용 계측. 목표가 아니라 관찰값이다."""

    brain_calls: int = 0
    rethink_rounds: int = 0
    secondary_requests: int = 0
    tool_requests: int = 0
    verification_calls: int = 0
    expansion_rounds: int = 0


@dataclass(frozen=True, slots=True)
class EpisodePlan:
    """COMMIT/ACTION 입력. Body adapter(P06/P07)가 준비한다."""

    readiness: ReadinessResult | None = None
    action: ActionIntent | None = None
    expected_outcome: str = ""
    observation: ActionObservation | None = None
    decision_assessment: DecisionAssessment | None = None


@dataclass(frozen=True, slots=True)
class EpisodeRequest:
    episode_id: str
    context_ref: str
    goal_ref: str
    expected_outcome: str = ""
    simple: bool = True
    decision_revision: int = 1
    state_revision: int = 1
    authority_revision: int | None = None
    policy_version: str | None = None
    plan: EpisodePlan = field(default_factory=EpisodePlan)
    unresolved: bool = False
    affected_grounds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Episode:
    episode_id: str
    state: LoopState
    termination: EpisodeTermination
    events: tuple[EpisodeEvent, ...] = ()
    judgment_ref: str | None = None
    feedback: tuple[RequestFeedback, ...] = ()
    readiness: ReadinessResult | None = None
    action_run: ActionRun | None = None
    outcome: OutcomeComparison | None = None
    evaluations: EpisodeEvaluations | None = None
    selection: ExperienceSelection | None = None
    counters: EpisodeCounters = field(default_factory=EpisodeCounters)
    note: str = ""

    def states(self) -> tuple[LoopState, ...]:
        return tuple(event.state for event in self.events)


class CognitiveRuntime:
    """최소 운영 루프 실행기. opt-in이며 port가 없으면 실행하지 않는다."""

    def __init__(
        self,
        *,
        think: ThinkPort,
        rethink: RethinkPort | None = None,
        actions: ActionDispatcher | None = None,
        governance: GovernanceGate | None = None,
        readiness: ReadinessGate | None = None,
        experience: ExperienceLedger | None = None,
        budget: EpisodeBudget | None = None,
        project_id: str = "",
        producer: Producer | None = None,
        clock: Callable[[], datetime] | None = None,
        record_sink: Callable[[Sequence[Record]], object] | None = None,
    ) -> None:
        self.think = think
        self.rethink = rethink
        self.actions = actions
        self.governance = governance
        self.readiness = readiness or ReadinessGate()
        self.experience = experience or ExperienceLedger()
        self.budget = budget or EpisodeBudget()
        self.project_id = project_id
        self.producer = producer or Producer(kind=ProducerKind.BODY, actor_id="body:runtime")
        self._clock = clock
        self.record_sink = record_sink
        self._signature_counts: dict[str, int] = {}

    # ── 실행 ────────────────────────────────────────────
    def run(self, request: EpisodeRequest) -> Episode:
        events: list[EpisodeEvent] = []
        counters = EpisodeCounters()
        feedback: list[RequestFeedback] = []

        def transition(state: LoopState, caused_by: str, detail: str = "") -> EpisodeEvent:
            event = EpisodeEvent(
                event_id=f"event:{request.episode_id}:{len(events) + 1}",
                episode_id=request.episode_id,
                sequence=len(events) + 1,
                state=state,
                caused_by=caused_by,
                state_revision=request.state_revision,
                detail=detail,
                occurred_at=self._now(),
            )
            events.append(event)
            return event

        # 1) PREPARE
        transition(LoopState.PREPARE, "runtime", f"goal={request.goal_ref}")
        if not request.goal_ref or not request.context_ref:
            transition(LoopState.BLOCKED_CONTEXT, "prepare", "goal/context가 없다")
            return self._episode(request, events, counters, EpisodeTermination.BLOCKED_CONTEXT)

        # 2) THINK
        signal = self._observe_signature(request.episode_id)
        if signal is not None:
            transition(LoopState.COMMIT, "repeat-detector", signal)
            return self._episode(request, events, counters, EpisodeTermination.STOPPED_NO_DELTA, note=signal)
        transition(LoopState.THINK, "prepare")
        thought = self.think.think(context_ref=request.context_ref, request_signature=request.episode_id, attempt=1)
        counters = _bump(counters, brain_calls=1)
        if thought.failed:
            transition(LoopState.BRAIN_FAILED, "think", thought.detail)
            return self._episode(request, events, counters, EpisodeTermination.BRAIN_FAILED, note=thought.detail)
        judgment_ref = thought.judgment_ref

        # 3–4) GOVERN → EXECUTE → FEEDBACK → TARGETED_RETHINK* (simple이면 생략)
        # 성공 feedback도 Primary에 전달하고, rethink의 새 request는 같은 gate로 다음 round 실행한다.
        active_plan = thought.plan if thought.plan is not None else request.plan
        if not request.simple and thought.requests:
            governance = self.governance or GovernanceGate()
            pending: list[CognitiveRequestEnvelope] = list(thought.requests)
            rounds = 0
            total_requests = 0
            while pending:
                if total_requests >= self.budget.max_total_requests:
                    transition(
                        LoopState.COMMIT,
                        "stop-conditions",
                        f"total request budget={self.budget.max_total_requests}",
                    )
                    return self._episode(
                        request,
                        events,
                        counters,
                        EpisodeTermination.STOPPED_BUDGET,
                        note="request budget exhausted",
                        feedback=tuple(feedback),
                        judgment_ref=judgment_ref,
                    )
                round_feedback: list[RequestFeedback] = []
                truncated_by_budget = False
                for envelope in pending:
                    if total_requests >= self.budget.max_total_requests:
                        truncated_by_budget = True
                        break
                    sig_stop = self._observe_signature(envelope.signature())
                    if sig_stop is not None:
                        transition(LoopState.FEEDBACK, envelope.request_id, "REPEAT_STOP")
                        item = RequestFeedback(
                            request_id=envelope.request_id,
                            request_signature=envelope.signature(),
                            disposition="REPEAT_STOP",
                            executed=False,
                            detail=sig_stop,
                        )
                        feedback.append(item)
                        round_feedback.append(item)
                        continue
                    total_requests += 1
                    counters = _bump(
                        counters,
                        tool_requests=1 if same_enum(envelope.request_type, CognitiveRequestType.TOOL) else 0,
                        secondary_requests=1
                        if same_enum(envelope.request_type, CognitiveRequestType.SECONDARY_BRAIN)
                        else 0,
                    )
                    transition(LoopState.GOVERN, judgment_ref, envelope.request_id)
                    outcome = governance.evaluate(
                        GovernanceRequest(
                            request_id=envelope.request_id,
                            project_id=self.project_id,
                            subject=self.producer.actor_id,
                            action=envelope.to_requested_action(),
                            authority=envelope.authority,
                            unknowns=envelope.unknowns,
                            advisory_notes=envelope.advisory_notes,
                            state_revision=request.state_revision,
                        )
                    )
                    executed = False
                    detail = outcome.reason
                    receipt_ref: str | None = None
                    effects_observed: bool | None = None
                    if outcome.admits_execution and envelope.action is not None and self.actions is not None:
                        transition(LoopState.EXECUTE, envelope.request_id, outcome.disposition.value)
                        run = self.actions.execute(envelope.action, project_id=self.project_id, producer=self.producer)
                        executed = same_enum(run.status, ActionExecutionStatus.DISPATCHED)
                        detail = run.reason or detail
                        if run.receipt is not None:
                            receipt_ref = run.receipt.receipt_id
                            effects_observed = run.receipt.effects_observed
                    elif same_enum(outcome.disposition, GovernanceDisposition.DENY):
                        transition(LoopState.BLOCKED_CONTEXT, envelope.request_id, outcome.reason)
                    transition(LoopState.FEEDBACK, envelope.request_id, outcome.disposition.value)
                    item = RequestFeedback(
                        request_id=envelope.request_id,
                        request_signature=envelope.signature(),
                        disposition=outcome.disposition.value,
                        executed=executed,
                        detail=detail,
                        receipt_ref=receipt_ref,
                        effects_observed=effects_observed,
                    )
                    feedback.append(item)
                    round_feedback.append(item)

                pending = []
                if truncated_by_budget:
                    transition(
                        LoopState.COMMIT,
                        "stop-conditions",
                        f"total request budget={self.budget.max_total_requests}",
                    )
                    return self._episode(
                        request,
                        events,
                        counters,
                        EpisodeTermination.STOPPED_BUDGET,
                        note="request budget exhausted",
                        feedback=tuple(feedback),
                        judgment_ref=judgment_ref,
                    )
                # 성공·실패 feedback 모두 Primary 재통합 대상이다(실패만 rethink 금지).
                should_rethink = (
                    self.rethink is not None and bool(round_feedback) and rounds < self.budget.expansion_rounds
                )
                if not should_rethink:
                    break
                rounds += 1
                counters = _bump(counters, rethink_rounds=1, expansion_rounds=1)
                transition(LoopState.TARGETED_RETHINK, judgment_ref, f"round={rounds}")
                rethought = self.rethink.rethink(
                    previous_judgment_ref=judgment_ref,
                    feedback_refs=tuple(item.request_id for item in round_feedback),
                    affected_grounds=request.affected_grounds,
                    round_index=rounds,
                )
                counters = _bump(counters, brain_calls=1)
                if rethought.failed:
                    transition(LoopState.BRAIN_FAILED, "rethink", rethought.detail)
                    return self._episode(
                        request, events, counters, EpisodeTermination.BRAIN_FAILED, note=rethought.detail
                    )
                judgment_ref = rethought.judgment_ref
                if rethought.plan is not None:
                    active_plan = rethought.plan
                if rethought.delta is None or not rethought.delta.material:
                    transition(
                        LoopState.COMMIT,
                        "stop-conditions",
                        rethought.delta.description if rethought.delta else "material delta 없음",
                    )
                    return self._episode(
                        request,
                        events,
                        counters,
                        EpisodeTermination.STOPPED_NO_DELTA,
                        note="No Material Cognitive Delta → stop",
                        feedback=tuple(feedback),
                        judgment_ref=judgment_ref,
                    )
                if rethought.requests:
                    pending = list(rethought.requests)
                else:
                    break

        # 5) COMMIT — readiness만 검사한다 (최신 plan/judgment)
        transition(LoopState.COMMIT, judgment_ref, "readiness")
        readiness = active_plan.readiness
        if readiness is None:
            transition(LoopState.BLOCKED_READINESS, "commit", "readiness 없음")
            return self._episode(request, events, counters, EpisodeTermination.BLOCKED_READINESS, note="readiness 없음")
        if not readiness.ok:
            transition(LoopState.BLOCKED_READINESS, "commit", "; ".join(readiness.blocking_conditions))
            return self._episode(
                request,
                events,
                counters,
                EpisodeTermination.BLOCKED_READINESS,
                readiness=readiness,
                feedback=tuple(feedback),
                judgment_ref=judgment_ref,
                note="stop은 READY가 아니다",
            )

        # 6) ACTION
        action = active_plan.action
        if action is None:
            return self._episode(
                request,
                events,
                counters,
                EpisodeTermination.COMPLETED,
                readiness=readiness,
                feedback=tuple(feedback),
                judgment_ref=judgment_ref,
                note="ACTION 없이 COMMIT에서 종료",
            )
        if self.actions is None:
            transition(LoopState.BLOCKED_READINESS, "action", "dispatch 경로가 없다(feature off)")
            return self._episode(
                request,
                events,
                counters,
                EpisodeTermination.BLOCKED_READINESS,
                readiness=readiness,
                note="dispatch 경로 없음",
            )
        transition(LoopState.ACTION, judgment_ref, action.tool)
        action_run = self.actions.execute(action, project_id=self.project_id, producer=self.producer)
        if action_run.refused:
            transition(LoopState.BLOCKED_READINESS, "action", action_run.reason)
            return self._episode(
                request,
                events,
                counters,
                EpisodeTermination.REFUSED_ACTION,
                readiness=readiness,
                action_run=action_run,
                feedback=tuple(feedback),
                judgment_ref=judgment_ref,
                note=action_run.reason,
            )
        if same_enum(action_run.status, ActionExecutionStatus.UNKNOWN):
            transition(LoopState.ACTION_OUTCOME_UNKNOWN, "action", action_run.reason or "결과 불명")
            return self._episode(
                request,
                events,
                counters,
                EpisodeTermination.ACTION_OUTCOME_UNKNOWN,
                readiness=readiness,
                action_run=action_run,
                feedback=tuple(feedback),
                judgment_ref=judgment_ref,
                note="결과 불명은 성공이 아니다",
            )

        # 7) OBSERVE
        observed = active_plan.observation
        if observed is None:
            transition(LoopState.OBSERVE, "action", "관측 대기")
            episode = self._episode(
                request,
                events,
                counters,
                EpisodeTermination.OBSERVATION_PENDING,
                readiness=readiness,
                action_run=action_run,
                feedback=tuple(feedback),
                judgment_ref=judgment_ref,
                note="deferred observation",
            )
            return episode
        transition(LoopState.OBSERVE, "action", observed.detail or "observed")
        action_run = self.actions.reconcile(action_run, observed, project_id=self.project_id, producer=self.producer)
        comparison = _outcome_comparison(active_plan.expected_outcome, observed)
        evaluations = EpisodeEvaluations(
            outcome=evaluate_outcome(comparison),
            decision=evaluate_decision(
                comparison,
                assessment=active_plan.decision_assessment,
            ),
            execution=evaluate_execution(
                succeeded=observed.succeeded,
                receipt_ref=action_run.receipt.receipt_id if action_run.receipt else None,
                reason=observed.detail,
            ),
        )
        transition(LoopState.EXPERIENCE, "observe", comparison.status.value)
        episode = self._episode(
            request,
            events,
            counters,
            EpisodeTermination.COMPLETED,
            readiness=readiness,
            action_run=action_run,
            outcome=comparison,
            evaluations=evaluations,
            feedback=tuple(feedback),
            judgment_ref=judgment_ref,
        )
        return episode

    # ── Experience 선별 ─────────────────────────────────
    def _record_experience(
        self,
        request: EpisodeRequest,
        episode: Episode,
        *,
        action_run: ActionRun | None,
        force_operational_only: bool = False,
    ) -> ExperienceSelection:
        record = OperationalRecord(
            record_id=f"operational:{request.episode_id}:{len(self.experience.operational_records) + 1}",
            episode_reference=request.episode_id,
            kind="EPISODE",
            detail=episode.note or episode.termination.value,
            state=episode.state,
            provenance_uri=f"episode://{request.episode_id}",
            provenance_digest=episode.termination.value,
            recorded_at=self._now(),
            producer=self.producer,
        )
        created = self._now()
        self.experience.record_operational(
            record,
            project_id=self.project_id,
            producer=self.producer,
            created_at=created,
        )
        if force_operational_only:
            comparison = compare_outcome(request.plan.expected_outcome, request.plan.expected_outcome)
            signals = EpisodeSignals()
        else:
            comparison = episode.outcome or compare_outcome(request.plan.expected_outcome, None)
            signals = EpisodeSignals(
                failure=episode.termination in (EpisodeTermination.REFUSED_ACTION, EpisodeTermination.BRAIN_FAILED),
                unresolved=request.unresolved or same_enum(episode.termination, EpisodeTermination.OBSERVATION_PENDING),
                risk_shaping=bool(action_run and action_run.intent.guards),
                recovery=False,
            )
        selection = self.experience.select(
            record,
            comparison=comparison,
            signals=signals,
            producer=self.producer,
            recorded_at=self._now(),
            policy_version=request.policy_version,
            note=episode.termination.value,
        )
        if self.project_id:
            self.experience._records.append(selection.to_record(project_id=self.project_id, created_at=self._now()))
        return selection

    def form_experience_core(
        self,
        selection: ExperienceSelection,
        *,
        trigger: str,
        experience_id: str | None = None,
        context_ref: str | None = None,
        judgment_ref: str | None = None,
        decision_ref: str | None = None,
        action_ref: str | None = None,
        observation_refs: Sequence[str] = (),
        evidence_refs: Sequence[str] = (),
        remaining_unknowns: Sequence[str] = (),
        future_attention: Sequence[str] = (),
    ) -> ExperienceCore:
        """선별을 통과한 episode만 Experience core가 된다. 지식 승격은 P09다."""

        core = ExperienceCore(
            experience_id=experience_id or new_id(EntityType.EXPERIENCE),
            episode_reference=selection.episode_reference,
            trigger=trigger,
            context_ref=context_ref,
            judgment_ref=judgment_ref,
            decision_ref=decision_ref,
            action_ref=action_ref,
            observation_refs=tuple(observation_refs),
            evidence_refs=tuple(evidence_refs),
            remaining_unknowns=tuple(remaining_unknowns),
            future_attention=tuple(future_attention),
        )
        return self.experience.form_experience(
            selection,
            core,
            project_id=self.project_id,
            producer=self.producer,
            created_at=self._now(),
        )

    # ── 내부 ────────────────────────────────────────────

    def _flush_experience_records(self) -> None:
        """Push newly formed experience/operational/selection records through record_sink."""
        if self.record_sink is None:
            return
        batch = self.experience.pending_sink_records()
        if not batch:
            return
        self.record_sink(batch)
        self.experience.mark_sunk(len(batch))

    def _observe_signature(self, signature: str) -> str | None:
        seen = self._signature_counts.get(signature, 0)
        self._signature_counts[signature] = seen + 1
        if seen >= self.budget.repeat_signature_limit:
            return f"같은 request signature 반복({seen + 1}회) — 새 ID는 새 의미가 아니다"
        return None

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock()
        return datetime.now(UTC)

    def _episode(
        self,
        request: EpisodeRequest,
        events: list[EpisodeEvent],
        counters: EpisodeCounters,
        termination: EpisodeTermination,
        *,
        readiness: ReadinessResult | None = None,
        action_run: ActionRun | None = None,
        outcome: OutcomeComparison | None = None,
        evaluations: EpisodeEvaluations | None = None,
        feedback: tuple[RequestFeedback, ...] = (),
        judgment_ref: str | None = None,
        note: str = "",
    ) -> Episode:
        state = events[-1].state if events else LoopState.PREPARE
        episode = Episode(
            episode_id=request.episode_id,
            state=state,
            termination=termination,
            events=tuple(events),
            judgment_ref=judgment_ref,
            feedback=feedback,
            readiness=readiness,
            action_run=action_run,
            outcome=outcome,
            evaluations=evaluations,
            counters=counters,
            note=note,
        )
        # R11: every terminal/pending path leaves an operational trail; STOPPED_NO_DELTA is
        # operational-only and never auto-forms Experience.
        if same_enum(termination, EpisodeTermination.STOPPED_NO_DELTA):
            selection = self._record_experience(
                request,
                episode,
                action_run=action_run,
                force_operational_only=True,
            )
            episode = _with_selection(episode, selection)
        else:
            selection = self._record_experience(request, episode, action_run=action_run)
            episode = _with_selection(episode, selection)
            if selection.reusable:
                action_ref = None
                if action_run is not None and is_canonical_id(action_run.intent.action_id):
                    action_ref = action_run.intent.action_id
                ctx = request.context_ref if is_canonical_id(request.context_ref) else None
                jref = judgment_ref or episode.judgment_ref
                if jref is not None and not is_canonical_id(jref):
                    jref = None
                # Historical core still forms when selection says EXPERIENCE; non-canonical
                # shorthand refs stay out of Reference edges (remain in trigger/note only).
                self.form_experience_core(
                    selection,
                    trigger=episode.termination.value,
                    context_ref=ctx,
                    judgment_ref=jref,
                    action_ref=action_ref,
                )
        self._flush_experience_records()
        return episode


def _outcome_comparison(expected: str, observed: ActionObservation) -> OutcomeComparison:
    """관측을 Expected↔Observed 비교로 옮긴다. 관측이 없으면 UNKNOWN이다."""

    if not observed.observed:
        return compare_outcome(expected, None)
    if observed.succeeded is True:
        return compare_outcome(expected, observed.detail or expected)
    if observed.succeeded is False:
        return compare_outcome(expected, observed.detail or "(실패로 관측됨)")
    return compare_outcome(expected, None)


def _with_selection(episode: Episode, selection: ExperienceSelection) -> Episode:
    return Episode(
        episode_id=episode.episode_id,
        state=episode.state,
        termination=episode.termination,
        events=episode.events,
        judgment_ref=episode.judgment_ref,
        feedback=episode.feedback,
        readiness=episode.readiness,
        action_run=episode.action_run,
        outcome=episode.outcome,
        evaluations=episode.evaluations,
        selection=selection,
        counters=episode.counters,
        note=episode.note,
    )


def _bump(
    counters: EpisodeCounters,
    *,
    brain_calls: int = 0,
    rethink_rounds: int = 0,
    secondary_requests: int = 0,
    tool_requests: int = 0,
    verification_calls: int = 0,
    expansion_rounds: int = 0,
) -> EpisodeCounters:
    return EpisodeCounters(
        brain_calls=counters.brain_calls + brain_calls,
        rethink_rounds=counters.rethink_rounds + rethink_rounds,
        secondary_requests=counters.secondary_requests + secondary_requests,
        tool_requests=counters.tool_requests + tool_requests,
        verification_calls=counters.verification_calls + verification_calls,
        expansion_rounds=counters.expansion_rounds + expansion_rounds,
    )


def episode_records(
    episode: Episode, *, project_id: str, producer: Producer, created_at: datetime
) -> tuple[Record, ...]:
    """episode 전이를 canonical Event record로 옮긴다(P08 → P02 표면)."""

    return tuple(
        event.to_record(project_id=project_id, producer=producer, created_at=created_at) for event in episode.events
    )


__all__ = [
    "DEFAULT_EXPANSION_ROUNDS",
    "DEFAULT_REPEAT_SIGNATURE_LIMIT",
    "CognitiveRequestEnvelope",
    "CognitiveRuntime",
    "Episode",
    "EpisodeBudget",
    "EpisodeCounters",
    "EpisodeDelta",
    "EpisodeEvent",
    "EpisodePlan",
    "EpisodeRequest",
    "EpisodeTermination",
    "RequestFeedback",
    "RethinkPort",
    "ThinkOutcome",
    "ThinkPort",
    "episode_records",
]
