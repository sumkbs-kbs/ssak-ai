"""사용자 표면 opt-in 통합 (P11) — legacy 경로를 건드리지 않고 신규 core를 부착하는 adapter.

계약(ACCEPTANCE_CHECKLIST T11, IMPLEMENTATION_ROADMAP P11, ADR-0004):

- **기본 OFF:** 설정이 없거나 ``enabled=false``면 신규 core는 한 줄도 실행되지 않고 기존 경로(legacy
  ``engine.cognitive_loop``)가 그대로 동작한다. 알 수 없는 mode 문자열도 OFF로 fail-closed 한다.
- **SHADOW:** episode를 돌리되 **dispatch하지 않는다(action 0)**. shadow dispatcher는 port 없이 만들어지므로
  ``execute``는 ``NO_DISPATCH_PORT``로 거부되고 외부 effect·receipt가 생기지 않는다.
- **ACTIVE:** 사람 승인 기록(``activate``)과 dispatch port·governance gate가 모두 있을 때만 허용된다.
  셋 중 하나라도 없으면 실행하지 않는다(거부 사유를 남긴다).
- **STATUS:** read-only 조회. mode·source·policy version·마지막 episode/판정·dispatch 수를 노출하며
  대시보드/CLI가 같은 값을 읽는다.
- **이중 write 금지(ADR-0004):** shadow는 canonical store에 아무 것도 commit하지 않는다. caller가 준
  dispatcher와 store만 쓴다.

이 모듈은 provider/UI를 import하지 않는다. 사용자 표면 결선은 CLI/API 계층에서 이 adapter를 호출한다.
"""

from __future__ import annotations

import ast
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionExecutionStatus,
    ActionIntent,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    Producer,
    ProducerKind,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.readiness import ReadinessResult
from antigravity_k.engine.cognitive.references import is_canonical_id
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRuntime,
    Episode,
    EpisodePlan,
    EpisodeRequest,
    ThinkOutcome,
)

#: 설정 섹션 이름. config.yaml에 없으면 OFF다(기본값을 파일에 심지 않는다).
CONFIG_SECTION: Final[str] = "cognitive_core"
#: 신규 core 모듈(판정·실행 계약). 이 경로가 사용자 표면에 도달했는지가 P11의 실측 대상이다.
CORE_MODULE: Final[str] = "antigravity_k.engine.cognitive.runtime"
#: legacy 인지 순환. P11 이전까지 사용자 대화 경로가 실제로 쓰는 모듈이다.
LEGACY_MODULE: Final[str] = "antigravity_k.engine.cognitive_loop"
LEGACY_HOOK_SITES: Final[tuple[str, ...]] = (
    "antigravity_k.engine.engine_context (ctx.cognitive_loop 생성)",
    "antigravity_k.engine.tool_loop (reflect / verify_tool_result / adapt_strategy)",
)

#: P11 실측 대상 표면. (표시 이름, 모듈 경로)
DEFAULT_SURFACE_ENTRYPOINTS: Final[tuple[tuple[str, str], ...]] = (
    ("CLI", "antigravity_k.cli"),
    ("API server", "antigravity_k.api.server"),
    ("API chat", "antigravity_k.api.routes.chat"),
    ("API agent SSE", "antigravity_k.api.routes.agent_stream_api"),
    ("대화 경로(EngineContext)", "antigravity_k.engine.orchestrator.agent"),
    ("legacy loop 소유", "antigravity_k.engine.engine_context"),
    ("legacy hook(tool_loop)", "antigravity_k.engine.tool_loop"),
    ("background/durable task", "antigravity_k.engine.task_runner"),
    ("agent runtime", "antigravity_k.engine.agent_runtime"),
)


class SurfaceMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


class SurfaceSource(StrEnum):
    """이 표면이 지금 어느 engine을 쓰는가."""

    LEGACY = "legacy"
    CORE_SHADOW = "core_shadow"
    CORE_ACTIVE = "core_active"


class CognitiveSurfaceError(RuntimeError):
    """표면 adapter 계약 위반."""


class SurfaceDisabledError(CognitiveSurfaceError):
    """설정이 OFF다 — 호출하면 조용히 무시하지 않고 거부한다."""


class SurfaceNotReadyError(CognitiveSurfaceError):
    """mode는 켜져 있지만 필수 port·승인이 없다."""


@dataclass(frozen=True, slots=True)
class CognitiveCoreSettings:
    """설정에서 읽은 표면 계약. 알 수 없는 값은 OFF로 fail-closed 한다."""

    enabled: bool = False
    mode: SurfaceMode = SurfaceMode.OFF
    requested_mode: str = ""
    project_id: str = ""
    policy_target: str = ""
    note: str = ""

    @property
    def effective_mode(self) -> SurfaceMode:
        """enabled가 아니면 mode 값과 무관하게 OFF다."""

        return self.mode if self.enabled else SurfaceMode.OFF

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "enabled": self.enabled,
            "mode": self.mode.value,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode.value,
            "project_id": self.project_id,
            "policy_target": self.policy_target,
            "note": self.note,
        }

    @classmethod
    def from_config(cls, config: object) -> CognitiveCoreSettings:
        """config.yaml의 ``cognitive_core`` 섹션을 읽는다. 없거나 이상하면 OFF."""

        root = _as_mapping(getattr(config, "_raw", config))
        section = _as_mapping(root.get(CONFIG_SECTION))
        if not section:
            return cls(note=f"{CONFIG_SECTION} 설정이 없다 — legacy 경로 유지(기본 OFF)")
        requested = str(section.get("mode", "") or "")
        enabled = bool(section.get("enabled", False))
        mode = _parse_mode(requested) if enabled else SurfaceMode.OFF
        note = ""
        if enabled and mode is None:
            note = f"알 수 없는 mode '{requested}' — OFF로 fail-closed 한다"
            mode = SurfaceMode.OFF
            enabled = False
        elif not enabled:
            note = "enabled=false — legacy 경로 유지"
        return cls(
            enabled=enabled,
            mode=mode if mode is not None else SurfaceMode.OFF,
            requested_mode=requested,
            project_id=str(section.get("project_id", "") or ""),
            policy_target=str(section.get("policy_target", "") or ""),
            note=note,
        )


def _parse_mode(value: str) -> SurfaceMode | None:
    try:
        return SurfaceMode(value.strip().lower())
    except ValueError:
        return None


def _as_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True, slots=True)
class ActivationRecord:
    """ACTIVE 전환은 사람 승인 기록이 있어야 한다."""

    approver: str
    reason: str
    activated_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {"approver": self.approver, "reason": self.reason, "activated_at": self.activated_at.isoformat()}


@dataclass(frozen=True, slots=True)
class SurfaceStatus:
    """read-only 표면 상태. CLI/대시보드가 공유하는 값."""

    enabled: bool
    requested_mode: str
    mode: SurfaceMode
    source: SurfaceSource
    legacy_module: str = LEGACY_MODULE
    core_module: str = CORE_MODULE
    legacy_hook_sites: tuple[str, ...] = LEGACY_HOOK_SITES
    policy_target: str = ""
    policy_version: str | None = None
    activation: ActivationRecord | None = None
    last_episode_id: str | None = None
    last_termination: str | None = None
    last_readiness_verdict: str | None = None
    last_disposition: str | None = None
    dispatched_actions: int = 0
    refused_actions: int = 0
    notes: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "enabled": self.enabled,
            "requested_mode": self.requested_mode,
            "mode": self.mode.value,
            "source": self.source.value,
            "legacy_module": self.legacy_module,
            "core_module": self.core_module,
            "legacy_hook_sites": list(self.legacy_hook_sites),
            "policy_target": self.policy_target,
            "policy_version": self.policy_version,
            "activation": self.activation.as_mapping() if self.activation else None,
            "last_episode_id": self.last_episode_id,
            "last_termination": self.last_termination,
            "last_readiness_verdict": self.last_readiness_verdict,
            "last_disposition": self.last_disposition,
            "dispatched_actions": self.dispatched_actions,
            "refused_actions": self.refused_actions,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ShadowRun:
    """shadow 실행 결과. dispatch는 0이며 외부 effect가 없다."""

    episode_id: str
    termination: str
    states: tuple[str, ...]
    judgment_ref: str | None
    action_status: str | None
    refusal: str | None
    refused_actions: int
    dispatched_actions: int
    planned_records: tuple[str, ...]
    note: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "episode_id": self.episode_id,
            "termination": self.termination,
            "states": list(self.states),
            "judgment_ref": self.judgment_ref,
            "action_status": self.action_status,
            "refusal": self.refusal,
            "refused_actions": self.refused_actions,
            "dispatched_actions": self.dispatched_actions,
            "planned_records": list(self.planned_records),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class SurfaceIntentRequest:
    """표면에서 올라온 실행 의도. 의미적 결론 문구는 담지 않는다."""

    action_key: str
    tool: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    scope: str = ""
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE
    risk: RiskProfile = field(default_factory=RiskProfile)
    reversible: bool = True
    idempotent: bool = True
    readiness: ReadinessResult | None = None
    clearance: object | None = None
    policy_version: str | None = None
    decision_revision: int = 1
    state_revision: int = 1
    authority_revision: int | None = None

    def to_intent(self) -> ActionIntent:
        token = uuid.uuid5(uuid.NAMESPACE_URL, f"surface:{self.action_key}")
        return ActionIntent(
            action_id=f"action:{token}",
            submission_id=f"submission:{token}",
            action_key=self.action_key,
            tool=self.tool,
            arguments=dict(self.arguments),
            scope=self.scope or self.tool,
            dimension=self.dimension,
            risk=self.risk,
            reversible=self.reversible,
            idempotent=self.idempotent,
            readiness=self.readiness,
            clearance=self.clearance,  # type: ignore[arg-type]
            decision_revision=self.decision_revision,
            state_revision=self.state_revision,
            authority_revision=self.authority_revision,
            policy_version=self.policy_version,
        )


@dataclass(frozen=True, slots=True)
class SurfaceEpisodeRequest:
    """표면 episode 입력. shadow/active가 같은 입력을 쓴다."""

    episode_id: str
    context_ref: str
    goal_ref: str
    intent: SurfaceIntentRequest | None = None
    expected_outcome: str = ""
    simple: bool = True
    policy_version: str | None = None
    advisory_experience_ids: tuple[str, ...] = ()


class ThinkLike(Protocol):
    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome: ...


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
        rethink: object | None = None,
        governance: object | None = None,
        dispatch_port: object | None = None,
        producer: Producer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings if settings is not None else CognitiveCoreSettings()
        self.think = think
        self.rethink = rethink
        self.governance = governance
        self.dispatch_port = dispatch_port
        self.producer = producer or Producer(kind=ProducerKind.BODY, actor_id="body:surface")
        self._clock = clock
        self._activation: ActivationRecord | None = None
        self._last_episode_id: str | None = None
        self._last_termination: str | None = None
        self._last_readiness_verdict: str | None = None
        self._last_disposition: str | None = None
        self._dispatched = 0
        self._refused = 0

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
        return SurfaceStatus(
            enabled=self.settings.enabled,
            requested_mode=self.settings.requested_mode,
            mode=self.settings.effective_mode,
            source=self.source,
            policy_target=self.settings.policy_target,
            policy_version=None,
            activation=self._activation,
            last_episode_id=self._last_episode_id,
            last_termination=self._last_termination,
            last_readiness_verdict=self._last_readiness_verdict,
            last_disposition=self._last_disposition,
            dispatched_actions=self._dispatched,
            refused_actions=self._refused,
            notes=tuple(note for note in (self.settings.note,) if note),
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
        self._activation = ActivationRecord(
            approver=approver.strip(), reason=reason.strip(), activated_at=now or datetime.now(tz=UTC)
        )
        return self._activation

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
        dispatcher = ActionDispatcher(port=self.dispatch_port, clock=self._clock)  # type: ignore[arg-type]
        runtime = self._build_runtime(dispatcher, think=think, rethink=self.rethink)
        episode = runtime.run(self._episode_request(request))
        run = self._summarize(episode, dispatcher, request)
        self._remember(episode, run)
        return run

    # ── 내부 ────────────────────────────────────────────
    def _build_runtime(
        self, dispatcher: ActionDispatcher, *, think: ThinkLike, rethink: object | None
    ) -> CognitiveRuntime:
        return CognitiveRuntime(
            think=think,
            rethink=rethink,  # type: ignore[arg-type]
            actions=dispatcher,
            governance=self.governance,  # type: ignore[arg-type]
            project_id=self.settings.project_id,
            producer=self.producer,
            clock=self._clock,
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
            )
            else 0
        )
        planned = tuple(record.id for record in dispatcher.records)
        note = "shadow — dispatch하지 않는다(action 0)"
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


# ─── 표면 도달 실측(P11 진입 지표) ────────────────────────────────


@dataclass(frozen=True, slots=True)
class SurfaceReach:
    """정적 도달성. 실행 trace가 아니라 import 그래프 기준이다."""

    label: str
    module: str
    module_path: str
    exists: bool
    reaches_legacy: bool
    reaches_core: bool
    legacy_via: tuple[str, ...] = ()
    core_via: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "label": self.label,
            "module": self.module,
            "module_path": self.module_path,
            "exists": self.exists,
            "reaches_legacy": self.reaches_legacy,
            "reaches_core": self.reaches_core,
            "legacy_via": list(self.legacy_via),
            "core_via": list(self.core_via),
        }


@dataclass(frozen=True, slots=True)
class SurfaceMeasurement:
    source_root: str
    legacy_module: str
    core_module: str
    reached_at: str
    entrypoints: tuple[SurfaceReach, ...]

    @property
    def legacy_count(self) -> int:
        return sum(1 for item in self.entrypoints if item.reaches_legacy)

    @property
    def core_count(self) -> int:
        return sum(1 for item in self.entrypoints if item.reaches_core)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "source_root": self.source_root,
            "legacy_module": self.legacy_module,
            "core_module": self.core_module,
            "reached_at": self.reached_at,
            "legacy_count": self.legacy_count,
            "core_count": self.core_count,
            "entrypoints": [item.as_mapping() for item in self.entrypoints],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True)


def _module_file(module: str, source_root: Path) -> Path | None:
    parts = module.split(".")
    base = source_root.joinpath(*parts)
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _package_of(module: str, path: Path) -> tuple[str, ...]:
    """파일 경로에서 package 구성요소를 구한다(상대 import 해석용)."""

    if path.name == "__init__.py":
        return tuple(module.split("."))
    return tuple(module.split(".")[:-1])


def _first_party_imports(module: str, path: Path) -> tuple[str, ...]:
    """모듈의 first-party import를 절대 모듈명으로 돌려준다(상대 import 포함)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _package_of(module, path)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names if alias.name.startswith("antigravity_k"))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            base: tuple[str, ...] = ()
        else:
            # level 1은 현재 package, level 2는 한 단계 위를 가리킨다.
            base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
        candidates: list[str] = []
        if node.module:
            candidates.append(".".join((*base, node.module)))
        else:
            candidates.append(".".join(base))
        # `from . import sub` 처럼 이름으로 하위 모듈을 가져오는 형태도 도달로 센다.
        for alias in node.names:
            if alias.name == "*":
                continue
            candidates.append(".".join((*base, node.module, alias.name) if node.module else (*base, alias.name)))
        modules.extend(item for item in candidates if item.startswith("antigravity_k"))
    return tuple(dict.fromkeys(modules))


def _reach_path(entry_module: str, target: str, source_root: Path, *, limit: int = 4000) -> tuple[str, ...]:
    """entry에서 target까지 import 그래프 최단 경로. 도달하지 않으면 빈 tuple."""

    entry_file = _module_file(entry_module, source_root)
    if entry_file is None:
        return ()
    if entry_module == target:
        return (entry_module,)
    seen = {entry_module}
    queue: list[tuple[str, tuple[str, ...]]] = [(entry_module, (entry_module,))]
    while queue and len(seen) < limit:
        module, trail = queue.pop(0)
        path = _module_file(module, source_root)
        if path is None:
            continue
        for imported in _first_party_imports(module, path):
            if imported == target:
                return (*trail, imported)
            if imported in seen:
                continue
            seen.add(imported)
            queue.append((imported, (*trail, imported)))
    return ()


def measure_surface_reach(
    *,
    source_root: str | Path | None = None,
    entrypoints: Sequence[tuple[str, str]] = DEFAULT_SURFACE_ENTRYPOINTS,
    now: datetime | None = None,
) -> SurfaceMeasurement:
    """entrypoint별로 legacy loop와 신규 core에 도달하는지 측정한다(정적 import 그래프)."""

    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[2]
    reaches: list[SurfaceReach] = []
    for label, module in entrypoints:
        path = _module_file(module, root)
        legacy_via = _reach_path(module, LEGACY_MODULE, root)
        core_via = _reach_path(module, CORE_MODULE, root)
        reaches.append(
            SurfaceReach(
                label=label,
                module=module,
                module_path=str(path) if path is not None else "",
                exists=path is not None,
                reaches_legacy=bool(legacy_via),
                reaches_core=bool(core_via),
                legacy_via=legacy_via,
                core_via=core_via,
            )
        )
    return SurfaceMeasurement(
        source_root=str(root),
        legacy_module=LEGACY_MODULE,
        core_module=CORE_MODULE,
        reached_at=(now or datetime.now(tz=UTC)).isoformat(),
        entrypoints=tuple(reaches),
    )
