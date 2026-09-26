"""사용자 표면 opt-in 통합 (P11) — legacy 경로를 건드리지 않고 신규 core를 부착하는 adapter.

계약(ACCEPTANCE_CHECKLIST T11, IMPLEMENTATION_ROADMAP P11, ADR-0004):

- **기본 OFF:** 설정이 없거나 ``enabled=false``면 신규 core는 한 줄도 실행되지 않고 기존 경로(legacy
  ``engine.cognitive_loop``)가 그대로 동작한다. 알 수 없는 mode 문자열도 OFF로 fail-closed 한다.
- **SHADOW:** episode를 돌리되 **dispatch하지 않는다(action 0)**. shadow dispatcher는 port 없이 만들어지므로
  ``execute``는 ``NO_DISPATCH_PORT``로 거부되고 외부 effect·receipt가 생기지 않는다.
- **ACTIVE:** 인증된 승인 검증기, 실행 port, governance, 영구 claim journal, canonical sink,
  현재 권한 resolver를 모두 요구한다. 활성화 승인과 action 권한은 매 실행 재검증한다.
- **STATUS:** read-only 조회. mode·source·policy version·마지막 episode/판정·dispatch 수를 노출하며
  대시보드/CLI가 같은 값을 읽는다.
- **이중 write 금지(ADR-0004):** shadow는 canonical store에 아무 것도 commit하지 않는다. caller가 준
  dispatcher와 store만 쓴다.

이 모듈은 provider/UI를 import하지 않는다. 사용자 표면 결선은 CLI/API 계층에서 이 adapter를 호출한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from antigravity_k.engine.cognitive.action_journal import ActionJournal
from antigravity_k.engine.cognitive.action_types import ActionObservation, ToolDispatchPort
from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionExecutionStatus,
    ActionIntent,
    ObservationSubmission,
    ReconciliationResult,
)
from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.brain import (
    BrainAdapter,
    BrainFailure,
    BrainJudgment,
    StructuredBrainClient,
    render_context_for_brain,
)
from antigravity_k.engine.cognitive.experience import ExperienceLedger
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.models import (
    ContextPackagePayload,
    IntegrityStatus,
    Producer,
    ProducerKind,
    Record,
    same_enum,
    to_wire,
)
from antigravity_k.engine.cognitive.readiness import FreshnessBinding, ReadinessResult
from antigravity_k.engine.cognitive.references import is_canonical_id
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRuntime,
    Episode,
    EpisodePlan,
    EpisodeRequest,
    RethinkPort,
    ThinkOutcome,
)
from antigravity_k.engine.cognitive.store import CommitReceipt, canonical_digest

from .cognitive_surface_measurement import DurableSurfaceHistory as DurableSurfaceHistory
from .cognitive_surface_measurement import DurableSurfaceHistoryStore as DurableSurfaceHistoryStore

# Stable public imports for existing CLI/API consumers.
from .cognitive_surface_measurement import SurfaceMeasurement as SurfaceMeasurement
from .cognitive_surface_measurement import SurfaceReach as SurfaceReach
from .cognitive_surface_measurement import measure_surface_reach as measure_surface_reach
from .cognitive_surface_types import (
    CONFIG_SECTION,
    ActivationRecord,
    CognitiveCoreSettings,
    ShadowRun,
    SurfaceDisabledError,
    SurfaceEpisodeRequest,
    SurfaceIntentRequest,
    SurfaceMode,
    SurfaceNotReadyError,
    SurfaceSource,
    SurfaceStatus,
    ThinkLike,
)
from .cognitive_surface_types import CORE_MODULE as CORE_MODULE
from .cognitive_surface_types import DEFAULT_SURFACE_ENTRYPOINTS as DEFAULT_SURFACE_ENTRYPOINTS
from .cognitive_surface_types import LEGACY_HOOK_SITES as LEGACY_HOOK_SITES
from .cognitive_surface_types import LEGACY_MODULE as LEGACY_MODULE
from .cognitive_surface_types import CognitiveSurfaceError as CognitiveSurfaceError


class _CountingBrainAdapter:
    """Wraps a BrainAdapter to count respond() calls (R14 provider-call0 assertions)."""

    def __init__(self, inner: BrainAdapter) -> None:
        self._inner = inner
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self):
        return self._inner.capabilities

    def respond(self, context_wire, request_id: str, *, repair_of=None):
        self.call_count += 1
        return self._inner.respond(context_wire, request_id, repair_of=repair_of)


class StructuredSurfaceBrainPort:
    """Canonical ContextPackage → bounded wire → StructuredBrainClient.

    Opaque ``context_ref`` alone is never sent to the provider. INCOMPLETE packages and
    required omissions under a low context window fail closed with provider call count 0.
    When ``legacy_observation`` is set and the ref cannot be loaded as a ContextPackage,
    the legacy one-sentence observation path runs (still delta=None — not material THINK).
    """

    def __init__(
        self,
        adapter: BrainAdapter,
        *,
        project_id: str,
        load_context_package: Callable[[str], Record | None],
        load_record: Callable[[str], Record | None],
        legacy_observation: Callable[[str], str] | None = None,
    ) -> None:
        self._inner_adapter = adapter
        self._adapter = _CountingBrainAdapter(adapter)
        self._project_id = project_id
        self._load_package = load_context_package
        self._load_record = load_record
        self._legacy = legacy_observation
        self._client = StructuredBrainClient(self._adapter, project_id=project_id)
        self.provider_calls = 0

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        package_record = self._load_package(context_ref)
        if package_record is None:
            if self._legacy is not None:
                return SurfaceBrainPort(self._legacy).think(
                    context_ref=context_ref, request_signature=request_signature, attempt=attempt
                )
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"CONTEXT_UNRESOLVED: {context_ref} is not a loadable ContextPackage",
            )
        payload = package_record.payload
        if not isinstance(payload, ContextPackagePayload):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"CONTEXT_WRONG_TYPE: {context_ref} payload is not ContextPackage",
            )
        if same_enum(payload.integrity, IntegrityStatus.INCOMPLETE):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=("CONTEXT_INCOMPLETE: adapter blocked; missing_ids=" + ",".join(payload.missing_ids)),
            )
        digest = canonical_digest(to_wire(package_record))
        rendered = render_context_for_brain(
            payload,
            project_id=self._project_id,
            context_digest=digest,
            load_record=self._load_record,
            context_limit=int(self._adapter.capabilities.context_limit),
        )
        if not rendered.ready_for_provider:
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=(
                    "CONTEXT_OVERFLOW: required goal/state/evidence omitted under context_limit="
                    f"{self._adapter.capabilities.context_limit}; omitted={list(rendered.omitted_required)}"
                ),
            )
        # Count only actual adapter.respond invocations via wrapping — use a counter hook.
        before = self._adapter.call_count
        outcome = self._client.think(rendered.wire, request_signature or context_ref)
        self.provider_calls += self._adapter.call_count - before
        if isinstance(outcome, BrainFailure):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"brain failure {outcome.kind}: {outcome.detail}",
            )
        assert isinstance(outcome, BrainJudgment)
        return ThinkOutcome(
            judgment_ref=outcome.record.id,
            delta=None,
            detail=outcome.payload.current_judgment[:500],
        )


class SurfaceBrainPort:
    """실제 모델을 Primary Brain port(think)로 결선하는 최소 어댑터.

    shadow episode의 판단 주체다 — 모델 호출이 실패하면 failed think로 episode가
    BRAIN_FAILED로 종료된다(legacy 경로와 무관하다). 모델 응답의 의미 해석은 여기서
    하지 않고 detail로 실어 보낼 뿐이다(최종 통합은 Primary, Body는 전달).
    """

    def __init__(self, generate: Callable[[str], str]) -> None:
        self._generate = generate

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        prompt = (
            "SSAK-AI shadow observation. context_ref={context_ref} request={request_signature} attempt={attempt}. "
            "이 상호작용의 관찰 요약을 한 문장으로 제시하라."
        ).format(context_ref=context_ref, request_signature=request_signature, attempt=attempt)
        try:
            detail = str(self._generate(prompt))
        except Exception as exc:  # noqa: BLE001 — 모델 실패는 failed think로 끝난다
            return ThinkOutcome(judgment_ref="", failed=True, detail=f"surface brain port: {exc}")
        # 관찰 요약이 물질 판단을 주장하지 않는다 — delta를 비워 simple 경로로 끝나고,
        # material 여부는 Primary가 다른 경로에서 주장할 일이다(Body가 대신 정하지 않는다).
        return ThinkOutcome(
            judgment_ref=f"judgment:{uuid.uuid4()}",
            delta=None,
            detail=detail[:500],
        )


class CognitiveSurfaceAdapter:
    """legacy 경로 옆에 붙는 opt-in adapter. 설정이 OFF면 아무 것도 하지 않는다."""

    def __init__(
        self,
        settings: CognitiveCoreSettings | None = None,
        *,
        think: ThinkLike | None = None,
        rethink: RethinkPort | None = None,
        governance: GovernanceGate | None = None,
        dispatch_port: ToolDispatchPort | None = None,
        journal: ActionJournal | None = None,
        record_sink: Callable[[Sequence[Record]], CommitReceipt | None] | None = None,
        authority_resolver: Callable[[ActionIntent, datetime], AuthorityDecision] | None = None,
        freshness_resolver: Callable[[ActionIntent, datetime], FreshnessBinding] | None = None,
        activation_authorizer: Callable[[str, str, datetime], bool] | None = None,
        producer: Producer | None = None,
        clock: Callable[[], datetime] | None = None,
        history_store: DurableSurfaceHistoryStore | None = None,
    ) -> None:
        self.settings = settings if settings is not None else CognitiveCoreSettings()
        self.think = think
        self.rethink = rethink
        self.governance = governance
        self.dispatch_port = dispatch_port
        self.journal = journal
        self.record_sink = record_sink
        self.authority_resolver = authority_resolver
        self.freshness_resolver = freshness_resolver
        self.activation_authorizer = activation_authorizer
        self.producer = producer or Producer(kind=ProducerKind.BODY, actor_id="body:surface")
        self._clock = clock
        self.history_store = history_store
        self._activation: ActivationRecord | None = None
        self._last_episode_id: str | None = None
        self._last_termination: str | None = None
        self._last_readiness_verdict: str | None = None
        self._last_disposition: str | None = None
        self._dispatched = 0
        self._refused = 0
        self._experience = ExperienceLedger()

    # ── 조회 ────────────────────────────────────────────
    @property
    def source(self) -> SurfaceSource:
        mode = self.settings.effective_mode
        if same_enum(mode, SurfaceMode.OFF):
            return SurfaceSource.LEGACY
        if same_enum(mode, SurfaceMode.SHADOW) or self._activation is None:
            return SurfaceSource.CORE_SHADOW
        return SurfaceSource.CORE_ACTIVE

    def status(self) -> SurfaceStatus:
        last_episode = self._last_episode_id
        last_termination = self._last_termination
        dispatched = self._dispatched
        refused = self._refused
        notes = [note for note in (self.settings.note,) if note]
        history_source = "in_memory"
        if self.history_store is not None and is_canonical_id(self.settings.project_id):
            hist = self.history_store.latest(self.settings.project_id)
            if hist is not None and hist.source == "durable":
                last_episode = hist.last_episode_id
                last_termination = hist.last_termination
                dispatched, refused = self.history_store.totals(self.settings.project_id)
                history_source = "durable"
                if hist.observed_at:
                    notes.append(f"history_observed_at={hist.observed_at}")
                notes.append(f"history_projection_revision={hist.projection_revision}")
            elif hist is not None and hist.source == "empty" and last_episode is None:
                history_source = "durable_empty"
        notes.append(f"history_source={history_source}")
        notes.append("static_import_reach_is_not_runtime_evidence")
        # actual ACTIVE is activation-backed only — never inferred from reaches_core
        notes.append("actual_active=" + ("true" if self._activation is not None else "false"))
        return SurfaceStatus(
            enabled=self.settings.enabled,
            requested_mode=self.settings.requested_mode,
            mode=self.settings.effective_mode,
            source=self.source,
            policy_target=self.settings.policy_target,
            policy_version=None,
            activation=self._activation,
            last_episode_id=last_episode,
            last_termination=last_termination,
            last_readiness_verdict=self._last_readiness_verdict,
            last_disposition=self._last_disposition,
            dispatched_actions=dispatched,
            refused_actions=refused,
            notes=tuple(notes),
        )

    # ── 전환 ────────────────────────────────────────────
    def activate(self, *, approver: str, reason: str, now: datetime | None = None) -> ActivationRecord:
        """ACTIVE 전환. 사람 승인 식별자와 사유가 없으면 거부한다."""

        if not same_enum(self.settings.effective_mode, SurfaceMode.ACTIVE):
            raise SurfaceNotReadyError("mode가 ACTIVE가 아니다 — 설정을 바꾸지 않고 승인만으로 켤 수 없다")
        if not approver.strip() or not reason.strip():
            raise SurfaceNotReadyError("사람 승인(approver)과 사유(reason)가 필요하다")
        if self.dispatch_port is None or self.governance is None:
            raise SurfaceNotReadyError(
                "dispatch port와 governance gate가 연결되지 않았다 — ACTIVE는 실제 실행 경계가 있어야 한다"
            )
        if not is_canonical_id(self.settings.project_id):
            raise SurfaceNotReadyError(
                "ACTIVE는 canonical project id(`project:<uuid>`)가 필요하다 — 비어 있으면 canonical 기록을 만들 수 없다"
            )
        self._require_active_dependencies()
        activated_at = now or self._now()
        if activated_at.tzinfo is None:
            raise SurfaceNotReadyError("activation time must be timezone-aware")
        self._authorize_activation(approver.strip(), activated_at)
        self._activation = ActivationRecord(approver=approver.strip(), reason=reason.strip(), activated_at=activated_at)
        return self._activation

    def _now(self) -> datetime:
        return self._clock() if self._clock is not None else datetime.now(UTC)

    def _require_active_dependencies(self) -> None:
        if (
            self.journal is None
            or self.record_sink is None
            or self.authority_resolver is None
            or self.freshness_resolver is None
        ):
            raise SurfaceNotReadyError(
                "ACTIVE requires a durable journal, canonical record sink, "
                "live authority resolver and live freshness resolver"
            )
        if self.activation_authorizer is None:
            raise SurfaceNotReadyError("ACTIVE requires authenticated human activation authorization")

    def _authorize_activation(self, approver: str, now: datetime) -> None:
        authorizer = self.activation_authorizer
        if (
            not approver.startswith("human:")
            or authorizer is None
            or not authorizer(self.settings.project_id, approver, now)
        ):
            raise SurfaceNotReadyError("authenticated human activation authorization denied")

    # ── 실행 ────────────────────────────────────────────
    def run_shadow(self, request: SurfaceEpisodeRequest) -> ShadowRun:
        """episode를 돌리되 dispatch하지 않는다(action 0)."""

        if same_enum(self.settings.effective_mode, SurfaceMode.OFF):
            raise SurfaceDisabledError(
                f"{CONFIG_SECTION}가 OFF다 — legacy 경로를 그대로 쓴다(shadow를 조용히 실행하지 않는다)"
            )
        think = self.think
        if think is None:
            raise SurfaceNotReadyError("Primary Brain port(think)가 연결되지 않았다 — shadow는 판단 주체가 필요하다")
        dispatcher = ActionDispatcher(port=None, clock=self._clock)
        runtime = self._build_runtime(dispatcher, think=think, rethink=None)
        episode = runtime.run(self._episode_request(request))
        run = self._summarize(episode, dispatcher, request)
        self._remember(episode, run)
        return run

    def run_active(self, request: SurfaceEpisodeRequest) -> ShadowRun:
        """ACTIVE 실행. 승인·gate·port가 모두 있어야 하며 dispatch는 governance 경계를 지난다."""

        if not same_enum(self.settings.effective_mode, SurfaceMode.ACTIVE):
            raise SurfaceNotReadyError("mode가 ACTIVE가 아니다 — shadow나 legacy 경로를 쓴다")
        if self._activation is None:
            raise SurfaceNotReadyError("사람 승인 기록이 없다 — activate() 없이 실행하지 않는다")
        if self.dispatch_port is None or self.governance is None:
            raise SurfaceNotReadyError("dispatch port·governance gate가 연결되지 않았다")
        think = self.think
        if think is None:
            raise SurfaceNotReadyError("Primary Brain port(think)가 연결되지 않았다")
        self._require_active_dependencies()
        self._authorize_activation(self._activation.approver, self._now())
        dispatcher = ActionDispatcher(
            port=self.dispatch_port,
            clock=self._clock,
            journal=self.journal,
            record_sink=self.record_sink,
            authority_resolver=self._active_authority,
            freshness_resolver=self._active_freshness,
        )
        runtime = self._build_runtime(dispatcher, think=think, rethink=self.rethink)
        episode = runtime.run(self._episode_request(request))
        run = self._summarize(episode, dispatcher, request)
        self._remember(episode, run)
        return run

    def _active_authority(self, intent: ActionIntent, now: datetime) -> AuthorityDecision:
        activation = self._activation
        resolver = self.authority_resolver
        if activation is None or resolver is None:
            raise SurfaceNotReadyError("ACTIVE authorization context is missing")
        self._authorize_activation(activation.approver, now)
        return resolver(intent, now)

    def _active_freshness(self, intent: ActionIntent, now: datetime) -> FreshnessBinding:
        activation = self._activation
        resolver = self.freshness_resolver
        if activation is None or resolver is None:
            raise SurfaceNotReadyError("ACTIVE freshness context is missing")
        self._authorize_activation(activation.approver, now)
        return resolver(intent, now)

    # ── 내부 ────────────────────────────────────────────
    def _build_runtime(
        self, dispatcher: ActionDispatcher, *, think: ThinkLike, rethink: RethinkPort | None
    ) -> CognitiveRuntime:
        return CognitiveRuntime(
            think=think,
            rethink=rethink,
            actions=dispatcher,
            governance=self.governance,
            project_id=self.settings.project_id,
            producer=self.producer,
            clock=self._clock,
            experience=self._experience,
            record_sink=self.record_sink,
        )

    def _episode_request(self, request: SurfaceEpisodeRequest) -> EpisodeRequest:
        plan = EpisodePlan(
            readiness=self._bound_readiness(request.intent),
            action=request.intent.to_intent() if request.intent is not None else None,
            expected_outcome=request.expected_outcome,
        )
        return EpisodeRequest(
            episode_id=request.episode_id,
            context_ref=request.context_ref,
            goal_ref=request.goal_ref,
            expected_outcome=request.expected_outcome,
            simple=request.simple,
            policy_version=request.policy_version,
            plan=plan,
        )

    @staticmethod
    def _bound_readiness(intent: SurfaceIntentRequest | None) -> ReadinessResult | None:
        """readiness가 다른 action digest에 귀속된 것이면 실행하지 않는다(freshness 결박)."""

        if intent is None or intent.readiness is None:
            return None
        bound = intent.readiness.freshness.action_digest
        expected = intent.to_intent().args_digest()
        if bound != expected:
            raise SurfaceNotReadyError(
                "readiness가 이 action에 결박되지 않았다 — 다른 action의 판정을 재사용하지 않는다"
            )
        return intent.readiness

    def restore_experience_records(self, records: Sequence[Record], *, episode_reference: str = "") -> int:
        """Rebuild selected Experience cores from canonical records after restart (provider-neutral)."""
        count = 0
        for record in records:
            try:
                self._experience.ingest_core_record(record, episode_reference=episode_reference)
                count += 1
            except Exception:
                continue
        return count

    @property
    def experience(self) -> ExperienceLedger:
        return self._experience

    def list_pending_actions(self):
        """Pending durable claims for this project (timeout never clears them)."""
        self._require_active_dependencies()
        assert self.journal is not None
        dispatcher = ActionDispatcher(journal=self.journal, clock=self._clock)
        return dispatcher.pending_with_reasons(self.settings.project_id)

    def submit_observation(
        self,
        *,
        action_key: str,
        expected_receipt_id: str,
        observed: bool,
        succeeded: bool | None,
        detail: str = "",
        external_ref: str = "",
        load_record,
        now=None,
    ) -> ReconciliationResult:
        """Recover an UNKNOWN/DISPATCHED action by observation. Never redispatches."""
        self._require_active_dependencies()

        dispatcher = ActionDispatcher(
            port=None,
            clock=self._clock,
            journal=self.journal,
            record_sink=self.record_sink,
            authority_resolver=self.authority_resolver,
        )
        return dispatcher.submit_observation(
            ObservationSubmission(
                project_id=self.settings.project_id,
                action_key=action_key,
                expected_receipt_id=expected_receipt_id,
                observation=ActionObservation(
                    observed=observed,
                    succeeded=succeeded,
                    detail=detail,
                    external_ref=external_ref,
                ),
            ),
            producer=self.producer,
            load_record=load_record,
            now=now,
        )

    def _summarize(self, episode: Episode, dispatcher: ActionDispatcher, request: SurfaceEpisodeRequest) -> ShadowRun:
        action_run = episode.action_run
        refusal = action_run.refusal.value if action_run is not None and action_run.refusal is not None else None
        status = action_run.status.value if action_run is not None else None
        dispatched = (
            1
            if action_run is not None
            and action_run.status
            in (
                ActionExecutionStatus.DISPATCHED,
                ActionExecutionStatus.SUCCEEDED,
                ActionExecutionStatus.UNKNOWN,
                ActionExecutionStatus.FAILED,
            )
            else 0
        )
        planned = tuple(record.id for record in dispatcher.records)
        note = (
            "active — governance 및 영구 실행 기록 적용"
            if dispatcher.port is not None
            else "shadow — dispatch하지 않는다(action 0)"
        )
        return ShadowRun(
            episode_id=episode.episode_id,
            termination=episode.termination.value,
            states=tuple(state.value for state in episode.states()),
            judgment_ref=episode.judgment_ref,
            action_status=status,
            refusal=refusal,
            refused_actions=1 if refusal is not None else 0,
            dispatched_actions=dispatched,
            planned_records=planned,
            note=note if request.intent is not None else f"{note}; 계획된 action 없음",
        )

    def _remember(self, episode: Episode, run: ShadowRun) -> None:
        self._last_episode_id = episode.episode_id
        self._last_termination = episode.termination.value
        readiness = episode.readiness
        self._last_readiness_verdict = getattr(getattr(readiness, "verdict", None), "value", None)
        disposition = next((item.disposition for item in episode.feedback if item.disposition), None)
        self._last_disposition = disposition
        self._dispatched += run.dispatched_actions
        self._refused += run.refused_actions
        if self.history_store is not None and is_canonical_id(self.settings.project_id):
            self.history_store.record_run(
                project_id=self.settings.project_id,
                episode_id=episode.episode_id,
                termination=episode.termination.value,
                dispatched_actions=run.dispatched_actions,
                refused_actions=run.refused_actions,
            )
