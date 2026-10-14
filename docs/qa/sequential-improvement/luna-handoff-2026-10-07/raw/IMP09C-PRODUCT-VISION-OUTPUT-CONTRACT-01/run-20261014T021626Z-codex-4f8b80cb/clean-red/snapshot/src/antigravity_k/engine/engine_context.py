"""Ssak-Ai: Engine Context (DI Container).

============================================
Provides a unified context holding initialized services (Singletons/Scoped)
to decouple Orchestrator from direct instantiations.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from importlib import import_module
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, cast, final

import yaml

import antigravity_k.engine.gate_pipeline as gate_pipeline_module
from antigravity_k.engine.autonomous_learner import AutonomousLearner
from antigravity_k.engine.cognitive_loop import CognitiveLoop
from antigravity_k.engine.context_shaper import ContextShaper
from antigravity_k.engine.cost_guard import CostGuard
from antigravity_k.engine.decision_anchor import DecisionAnchor
from antigravity_k.engine.failure_memory import FailureMemory
from antigravity_k.engine.gate_pipeline import GatePipeline
from antigravity_k.engine.ide_sync import IDEContextManager
from antigravity_k.engine.knowledge import KIEngine
from antigravity_k.engine.memory_contracts import JsonValue
from antigravity_k.engine.memory_provider import (
    BuiltinMemoryProvider,
    EpisodicMemoryProvider,
    MemoryManager,
    MemoryProvider,
    WorkingMemoryBuffer,
)
from antigravity_k.engine.mode_manager import ModeManager
from antigravity_k.engine.persistent_agency import (
    PersistentAgencyController,
    persistent_agency_config_from_raw,
)
from antigravity_k.engine.plan_guard import PlanGuard
from antigravity_k.engine.project_memory import ProjectMemoryProvider
from antigravity_k.engine.project_memory_paths import project_memory_dir
from antigravity_k.engine.prompt_builder import PromptBuilder
from antigravity_k.engine.quality_gate import QualityGate
from antigravity_k.engine.session_manager import SessionManager
from antigravity_k.engine.skill_loader import SkillLoader
from antigravity_k.engine.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
)
from antigravity_k.engine.uncertainty import UncertaintyEstimator
from antigravity_k.engine.user_model import UserIntentModeler
from antigravity_k.runtime_paths import default_config_path
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_registry import ToolRegistry

logger = logging.getLogger("antigravity_k.engine_context")


class _SlashCommandRegistryLike(Protocol):
    def __init__(self, **kwargs: object) -> None: ...


class _ToolExecutorLike(Protocol):
    def __init__(self, **kwargs: object) -> None: ...

    def register_default_tools(self) -> None: ...

    def reset_error_counter(self) -> None: ...

    def set_objective(self, objective: str) -> None: ...

    def execute(self, name: str, args: dict[str, object], execution_mode: str | None = None) -> str: ...


class CognitiveKwargs(TypedDict):
    enable_caveman: NotRequired[bool]
    max_retries: NotRequired[int | None]
    dialectic_enabled: NotRequired[bool | None]


CognitiveConfig = tuple[bool, CognitiveKwargs]


def _mapping(value: object) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, Mapping) else {}


def cognitive_config_from_raw(config: object) -> CognitiveConfig:
    """config dict의 amplification.cognitive 섹션을 (enabled, kwargs)로 정규화.

    amplification.cognitive.enabled가 false면 (False, {}). 그 외에는
    CognitiveLoop 생성자에 넘길 kwargs dict를 반환한다. None 값은
    CognitiveLoop 기본값으로 폴백된다.
    """
    root = _mapping(config)
    amp = _mapping(root.get("amplification", {}))
    cog = _mapping(amp.get("cognitive", {}))
    enabled = bool(cog.get("enabled", True))
    if not enabled:
        return False, CognitiveKwargs()
    max_retries = cog.get("max_retries")
    dialectic_enabled = cog.get("dialectic_enabled")
    kwargs: CognitiveKwargs = {
        "enable_caveman": bool(cog.get("enable_caveman", False)),
        "max_retries": max_retries if isinstance(max_retries, int) else None,
        "dialectic_enabled": dialectic_enabled if isinstance(dialectic_enabled, bool) else None,
    }
    return True, kwargs


def quality_gate_from_config(config: object) -> QualityGate:
    """config.yaml의 quality_gate 섹션에서 QualityGate를 생성한다."""
    values = _mapping(_mapping(config).get("quality_gate", {}))
    retries = values.get("max_retries", 1)
    return QualityGate(max_retries=retries if isinstance(retries, int) and retries >= 0 else 1)


@final
class EngineContext:
    """Central context object wiring together all engine subsystems for a session."""

    def __init__(
        self,
        model_manager: object,
        vault_engine: object | None = None,
        project_root: str | None = None,
        tool_registry: object | None = None,
        session_manager: SessionManager | None = None,
        memory_manager: MemoryManager | None = None,
    ):
        """Initialize the EngineContext.

        Args:
            model_manager: model manager.
            vault_engine: vault engine.
            project_root: project root.
            tool_registry: tool registry.
            session_manager: 외부에서 주입받은 SessionManager (작업 1: 인스턴스 통일).
                            None이면 내부에서 새로 생성. chat.py와 동일한 인스턴스를
                            공유해야 단기기억이 끊기지 않음.

        """
        self.model_manager: object = model_manager
        self.vault_engine: object | None = vault_engine
        self.project_root: str = project_root or os.getcwd()

        # Load Config
        self.config: dict[str, JsonValue] = {}
        config_path = default_config_path(Path(self.project_root))
        if os.path.exists(config_path):
            with open(config_path) as f:
                self.config = _mapping(yaml.safe_load(f) or {})

        self.persistent_agency: PersistentAgencyController = PersistentAgencyController(
            project_root=self.project_root,
            config=persistent_agency_config_from_raw(self.config),
        )

        # Core Tools & Gates
        self.shared_tool_registry: bool = tool_registry is not None
        capability_policy_config = _mapping(self.config.get("autonomous_capabilities", {}))
        self.tool_registry: ToolRegistry = (
            cast(ToolRegistry, tool_registry)
            if tool_registry is not None
            else ToolRegistry(
                project_root=self.project_root,
                capability_policy_config=capability_policy_config,
            )
        )
        self.permission_gate: PermissionGate = PermissionGate(project_root=self.project_root)

        # Knowledge & Memory
        self.ki_engine: KIEngine = KIEngine(project_root=self.project_root)
        self.failure_memory: FailureMemory = FailureMemory(project_root=self.project_root)

        # Learners & Cognition
        self.autonomous_learner: AutonomousLearner = AutonomousLearner(
            model_manager=model_manager,
            ki_engine=self.ki_engine,
            project_root=self.project_root,
        )
        # amplification.cognitive: 인지 순환 증폭 (qwen3.6 등 작은 모델 추론 깊이 보완)
        cog_enabled, cog_kwargs = cognitive_config_from_raw(self.config)
        self.cognitive_loop: CognitiveLoop | None = (
            CognitiveLoop(
                project_root=self.project_root,
                failure_memory=self.failure_memory,
                **cog_kwargs,
            )
            if cog_enabled
            else None
        )

        # Guardrails & Quality
        guardrail_cfg = self._load_guardrail_config()
        self.tool_guardrail: ToolCallGuardrailController = ToolCallGuardrailController(config=guardrail_cfg)
        self.quality_gate: QualityGate = quality_gate_from_config(self.config)
        self.uncertainty_estimator: UncertaintyEstimator = UncertaintyEstimator()

        # Context & Modeling
        self.user_model: UserIntentModeler = UserIntentModeler(project_root=self.project_root)
        self.context_shaper: ContextShaper = ContextShaper()
        # DecisionAnchor: 핵심 합의를 컨텍스트 상단에 고정 (tool_loop auto_extract/add,
        # agent._prepare_agent_prompt inject_into_messages, system_api anchors_count 연동)
        self.decision_anchor: DecisionAnchor = DecisionAnchor()
        # 작업 1: 외부 주입 SessionManager 우선 사용 — chat.py와 동일 인스턴스 공유
        self.session_manager: SessionManager = session_manager or SessionManager()

        # 4-Tier Cognitive Memory System + 글로벌 메모리 (P2-3)
        from antigravity_k.engine.memory_provider import GlobalMemoryProvider

        self.memory_manager: MemoryManager = memory_manager if memory_manager is not None else MemoryManager()
        self.memory_manager.bind_project_root(self.project_root)
        self.global_memory: MemoryProvider | None
        if memory_manager is None:
            self.memory_manager.add_provider(BuiltinMemoryProvider(self.session_manager))
            episodic_dir = project_memory_dir(self.project_root) / "episodic"
            self.memory_manager.add_provider(EpisodicMemoryProvider(max_episodes=200, persist_dir=str(episodic_dir)))
            self.memory_manager.add_provider(WorkingMemoryBuffer(max_turns=20))
            # Cross-Project 글로벌 메모리 — 사용자 선호/패턴 영속화
            self.global_memory = GlobalMemoryProvider()
            self.memory_manager.add_provider(self.global_memory)
        else:
            self.global_memory = next(
                (provider for provider in self.memory_manager.providers if provider.name == "global"),
                None,
            )
        if not any(provider.name == "project" for provider in self.memory_manager.providers):
            self.memory_manager.add_provider(ProjectMemoryProvider(self.project_root))

        self.skill_loader: SkillLoader = SkillLoader(
            project_root=self.project_root,
            capability_policy_config=capability_policy_config,
        )
        self.ide_manager: IDEContextManager = IDEContextManager()
        self.prompt_builder: PromptBuilder = PromptBuilder()

        # ─── Mode Manager (Plan/Build/Interactive) ───
        self.mode_manager: ModeManager = ModeManager()

        # ─── Phase 1 D3: PlanGuard + GatePipeline ───
        self.plan_guard: PlanGuard = PlanGuard()

        # CostGuard 인스턴스화 (작업 4: 비용 게이트 활성화)
        # config의 cost 섹션 → 환경변수(.env의 AGK_DAILY_BUDGET_USD 등) 순서로 초기화
        cost_cfg = _mapping(self.config.get("cost", {}))

        daily_budget_raw = cost_cfg.get("daily_budget_usd")
        daily_budget = float(daily_budget_raw) if isinstance(daily_budget_raw, (int, float, str)) else 50.0
        hourly_limit_raw = cost_cfg.get("hourly_action_limit")
        hourly_limit = int(hourly_limit_raw) if isinstance(hourly_limit_raw, (int, float, str)) else 100
        cost_enabled = bool(cost_cfg.get("enabled", True))
        self.cost_guard: CostGuard = CostGuard(
            daily_budget_usd=daily_budget,
            hourly_action_limit=hourly_limit,
            enabled=cost_enabled,
        )

        create_pipeline = cast(Callable[..., GatePipeline], gate_pipeline_module.create_default_pipeline)
        self.gate_pipeline: GatePipeline = create_pipeline(
            guardrails=self.tool_guardrail,
            cost_guard=self.cost_guard,
        )

        slash_commands_module = import_module("antigravity_k.engine.slash_commands")
        slash_registry = cast(
            Callable[..., _SlashCommandRegistryLike], slash_commands_module.__dict__["SlashCommandRegistry"]
        )

        self.slash_commands: _SlashCommandRegistryLike = slash_registry(
            tool_registry=self.tool_registry,
            session_manager=self.session_manager,
            context_shaper=self.context_shaper,
            model_manager=model_manager,
            skill_loader=self.skill_loader,
            mode_manager=self.mode_manager,
        )

        tool_executor_module = import_module("antigravity_k.engine.tool_executor")
        tool_executor = cast(Callable[..., _ToolExecutorLike], tool_executor_module.__dict__["ToolExecutor"])
        self.tool_executor: _ToolExecutorLike = tool_executor(
            tool_registry=self.tool_registry,
            permission_gate=self.permission_gate,
            model_manager=model_manager,
            vault_engine=vault_engine,
            project_root=self.project_root,
            capability_policy_config=capability_policy_config,
            plan_guard=self.plan_guard,
            gate_pipeline=self.gate_pipeline,
        )

        if not self.shared_tool_registry:
            self.tool_executor.register_default_tools()

    def _load_guardrail_config(self) -> ToolCallGuardrailConfig:
        try:
            section = _mapping(self.config.get("tool_loop_guardrails", {}))
            return ToolCallGuardrailConfig.from_config(section)
        except Exception:
            logger.exception("Failed to load guardrail config")
        return ToolCallGuardrailConfig()
