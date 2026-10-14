"""Orchestrator setup/initialization logic.

오케스트레이터의 각 컴포넌트를 초기화하는 함수들을 제공합니다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import JsonValue

from antigravity_k.engine.fact_appender import FactAppender
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.vault import VaultEngine

if TYPE_CHECKING:
    from antigravity_k.engine.ambient_watchdog import AmbientWatchdog
    from antigravity_k.engine.self_evolution_coordinator import SelfEvolutionCoordinator

logger = logging.getLogger("antigravity_k.orchestrator.setup")


class _ManagerInput(Protocol): ...


def _json_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


# ─── Planning Mode fallback prompt (ArtifactEngine 미사용 시) ──────────

PLANNING_MODE_BLOCK = (
    "\n\n[CRITICAL ALGORITHM OVERRIDE: PLANNING MODE]\n"
    "You are executing a COMPLEX task or requested to plan. You MUST enter PLANNING MODE.\n"
    "1. DO NOT write functional code yet. Research and plan first.\n"
    "2. Create `implementation_plan.md` outlining your technical plan.\n"
    "3. After approval, create a `task.md` with a checkbox list.\n"
    "4. After completion, create a `walkthrough.md` summarizing the changes.\n"
)


def load_agent_models(config: Mapping[str, JsonValue]) -> dict[str, str]:
    """Config dict에서 역할별 모델 매핑을 추출합니다."""
    raw_models = _json_mapping(config.get("agent_models", {}))
    return {role: model for role, model in raw_models.items() if isinstance(model, str)}


def create_state_graph():
    """State Graph 엔진을 초기화합니다."""
    try:
        from antigravity_k.engine.orchestrator_handlers import build_orchestrator_graph

        graph = build_orchestrator_graph()
        logger.info("[Orchestrator] State Graph 엔진 활성화 완료")
        return graph
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("[Orchestrator] State Graph 초기화 실패")
        return None


def create_artifact_engine(project_root: str):
    """Artifact Engine을 초기화합니다."""
    try:
        from antigravity_k.engine.artifact_engine import ArtifactEngine

        engine = ArtifactEngine(project_root)
        logger.info("[Orchestrator] Artifact Engine 활성화 완료")
        return engine
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("Failed to initialize ArtifactEngine")
        return None


def create_watchdog(
    config: Mapping[str, JsonValue],
    project_root: str,
    manager: _ManagerInput | None,
    vault_engine: VaultEngine | None,
) -> AmbientWatchdog | None:
    """AmbientWatchdog을 조건부로 초기화합니다."""
    ambient_config = _json_mapping(config.get("ambient_partner", {}))
    watchdog_enabled = ambient_config.get("watchdog_enabled", False)
    if not isinstance(watchdog_enabled, bool) or not watchdog_enabled or manager is None:
        return None
    try:
        from antigravity_k.engine.ambient_watchdog import AmbientWatchdog

        watchdog = AmbientWatchdog(project_root, cast(ModelManager, manager), vault_engine)
        watchdog.start()
        return watchdog
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("Failed to start AmbientWatchdog")
        return None


def create_fact_appender(manager: _ManagerInput | None, project_root: str) -> FactAppender | None:
    """FactAppender를 초기화합니다."""
    try:
        from antigravity_k.engine.fact_appender import initialize_fact_appender

        initializer = cast(
            Callable[[_ManagerInput | None, str], FactAppender],
            initialize_fact_appender,
        )
        appender = initializer(manager, project_root)
        logger.info("[Orchestrator] FactAppender 활성화 완료")
        return appender
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("Failed to initialize FactAppender")
        return None


def create_mode_manager():
    """ModeManager를 초기화합니다."""
    try:
        from antigravity_k.engine.mode_manager import ModeManager

        mgr = ModeManager()
        logger.info("[Orchestrator] ModeManager 활성화 완료 (mode=%s)", mgr.current_mode.value)
        return mgr
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("Failed to initialize ModeManager")
        return None


def create_evolution_coordinator(
    project_root: str,
    model_manager: _ManagerInput | None,
    verify_fn: Callable[[str], str] | None,
) -> SelfEvolutionCoordinator | None:
    """Self-Evolution Coordinator를 초기화합니다."""
    try:
        from antigravity_k.engine.self_evolution_coordinator import (
            SelfEvolutionCoordinator,
        )

        coordinator = SelfEvolutionCoordinator(
            project_root=project_root,
            model_manager=cast(ModelManager, model_manager) if model_manager is not None else None,
            verify_fn=verify_fn,
        )
        logger.info("[Orchestrator] Self-Evolution Coordinator 활성화 완료")
        return coordinator
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional component initialization must preserve fallback behavior
        logger.exception("[Orchestrator] Self-Evolution Coordinator 초기화 실패")
        return None
