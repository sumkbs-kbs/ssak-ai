"""Cognitive surface configuration and request contracts."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol

from antigravity_k.engine.cognitive.actions import (
    ActionIntent,
    PolicyClearance,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    RiskProfile,
)
from antigravity_k.engine.cognitive.readiness import ReadinessResult
from antigravity_k.engine.cognitive.runtime import (
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
    operation: str = "execute_tool"
    arguments: Mapping[str, object] = field(default_factory=dict)
    scope: str = ""
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE
    risk: RiskProfile = field(default_factory=RiskProfile)
    reversible: bool = True
    idempotent: bool = True
    readiness: ReadinessResult | None = None
    clearance: PolicyClearance | None = None
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
            operation=self.operation,
            arguments=dict(self.arguments),
            scope=self.scope or self.tool,
            dimension=self.dimension,
            risk=self.risk,
            reversible=self.reversible,
            idempotent=self.idempotent,
            readiness=self.readiness,
            clearance=self.clearance,
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
    decision_ref: str | None = None
    governance_ref: str | None = None
    outcome_ref: str | None = None
    observation_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class ThinkLike(Protocol):
    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome: ...
