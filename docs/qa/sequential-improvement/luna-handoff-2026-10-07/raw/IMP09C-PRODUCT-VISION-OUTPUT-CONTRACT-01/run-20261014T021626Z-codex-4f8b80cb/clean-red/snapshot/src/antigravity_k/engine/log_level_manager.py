"""Dynamic Log Level Manager.

서버 재시작 없이 Python logging 레벨을 동적으로 변경할 수 있는 모듈.
디버그 모드 토글, 개별 로거 레벨 변경, 전체 로거 탐색을 지원합니다.

사용법:
    from antigravity_k.engine.log_level_manager import LogLevelManager

    # 현재 모든 로거 레벨 조회
    levels = LogLevelManager.get_all_levels()

    # 특정 로거 레벨 변경
    LogLevelManager.set_level("antigravity_k.api", "DEBUG")

    # 디버그 모드 토글 (antigravity_k.* → DEBUG)
    LogLevelManager.enable_debug_mode()
    LogLevelManager.disable_debug_mode()
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import ClassVar, TypedDict, cast

# ─── Ssak-Ai 로거 네임스페이스 ───────────────────────────

ROOT_LOGGER_NAME = "antigravity_k"


class LogInfo(TypedDict):
    name: str
    level: int
    level_name: str
    effective_level: int
    effective_level_name: str
    handlers: int


class SetLevelResult(TypedDict):
    name: str
    previous_level: int
    current_level: int
    previous_level_name: str
    current_level_name: str


class SetAllLevelsResult(TypedDict):
    target_level: int
    target_level_name: str
    updated_count: int
    loggers: list[SetLevelResult]


class EnableDebugResult(TypedDict):
    success: bool
    message: str
    updated_count: int


class DisableDebugResult(TypedDict):
    success: bool
    message: str
    restored_count: int


# antigravity_k.* 네임스페이스 아래 주요 서브로거들
KNOWN_LOGGERS = frozenset(
    {
        "antigravity_k.api",
        "antigravity_k.api.server",
        "antigravity_k.api.errors",
        "antigravity_k.api.chat",
        "antigravity_k.api.auth_routes",
        "antigravity_k.api.system_api",
        "antigravity_k.api.git_api",
        "antigravity_k.api.filesystem",
        "antigravity_k.api.dependencies",
        "antigravity_k.api.approval",
        "antigravity_k.api.legacy",
        "antigravity_k.api.events",
        "antigravity_k.api.routes.agent_activity",
        "antigravity_k.api.code_api",
        "antigravity_k.engine",
        "antigravity_k.engine.auth",
        "antigravity_k.engine.cost_guard",
        "antigravity_k.engine.model_manager",
        "antigravity_k.engine.model_registry",
        "antigravity_k.engine.model_router",
        "antigravity_k.engine.embeddings",
        "antigravity_k.engine.provider_manager",
        "antigravity_k.engine.config",
        "antigravity_k.engine.api_cache",
        "antigravity_k.engine.orchestrator",
        "antigravity_k.engine.tool_executor",
        "antigravity_k.engine.session_manager",
        "antigravity_k.engine.memory_provider",
        "antigravity_k.engine.approval_manager",
        "antigravity_k.engine.audit_db",
        "antigravity_k.engine.event_bus",
        "antigravity_k.engine.metrics",
        "antigravity_k.engine.shields",
        "antigravity_k.engine.skill_loader",
        "antigravity_k.engine.evolution",
        "antigravity_k.engine.rag_indexer",
        "antigravity_k.engine.tracing",
        "antigravity_k.engine.rsi_engine",
        "antigravity_k.engine.meta_architect",
        "antigravity_k.engine.code_intel",
        "antigravity_k.engine.code_intel.pipeline",
        "antigravity_k.engine.quality_gate",
        "antigravity_k.engine.harness",
        "antigravity_k.engine.sandbox",
        "antigravity_k.engine.goal_runner",
        "antigravity_k.engine.autonomous_qa",
        "antigravity_k.engine.self_improvement",
        "antigravity_k.engine.self_evolution_coordinator",
        "antigravity_k.engine.context_shaper",
        "antigravity_k.engine.cognitive_loop",
        "antigravity_k.engine.healing_loop",
        "antigravity_k.engine.deterministic_worker",
        "antigravity_k.engine.multiplexer",
        "antigravity_k.engine.slash_commands",
        "antigravity_k.engine.diff_engine",
        "antigravity_k.engine.artifact_engine",
        "antigravity_k.engine.tool_guardrails",
        "antigravity_k.engine.secret_scanner",
        "antigravity_k.engine.ide_server",
        "antigravity_k.tools",
        "antigravity_k.tools.web_search",
        "antigravity_k.tools.browser_tools",
        "antigravity_k.tools.file_tools",
        "antigravity_k.tools.vision_tools",
        "antigravity_k.tools.terminal_tools",
        "antigravity_k.agents",
        "antigravity_k.knowledge",
        "antigravity_k.security",
        "antigravity_k.config",
        "antigravity_k.api_cache",
        "web_search",
        "data_extractor",
        "stock_code_validator",
        "pipeline_timer",
        "extraction_ab_test",
        "browser_agent",
        "meta_evolution",
        "antigravity_k.diff_engine",
        "antigravity_k.tdd_engine",
        "antigravity_k.approval_manager",
        "antigravity_k.max_engine",
        "antigravity_k.sandbox",
        "antigravity_k.external_brain",
        "antigravity_k.memory_policy",
        "antigravity_k.secure_key",
        "antigravity_k.lora_pipeline",
        "antigravity_k.prompt_evolver",
        "antigravity_k.curriculum_generator",
        "antigravity_k.chain_of_verification",
        "antigravity_k.self_repair",
        "antigravity_k.failure_memory",
        "antigravity_k.context_compressor",
        "antigravity_k.engine.gate_pipeline",
        "antigravity_k.engine.state_graph",
        "antigravity_k.engine.error_classifier",
        "antigravity_k.engine.plan_guard",
        "antigravity_k.engine.immune_system",
        "antigravity_k.rsi_sandbox",
        "antigravity_k.engine.worktree_manager",
        "antigravity_k.engine.code_intel.hybrid_search",
        "antigravity_k.engine.code_intel.knowledge_graph",
        "antigravity_k.engine.code_intel.staleness",
        "antigravity_k.engine.code_intel.impact_analyzer",
        "antigravity_k.engine.code_tree_indexer",
        "antigravity_k.engine.file_summarizer",
        "antigravity_k.engine.trajectory_compressor",
        "antigravity_k.engine.skill_installer",
        "antigravity_k.engine.skill_market_client",
        "antigravity_k.engine.skill_market_registry",
        "antigravity_k.engine.skill_generator",
        "antigravity_k.engine.skill_publisher",
        "antigravity_k.engine.skill_auto_learner",
        "antigravity_k.engine.subagent_spawner",
        "antigravity_k.engine.plan_to_build",
        "antigravity_k.engine.healing_loop",
        "antigravity_k.engine.output_quality_comparator",
        "antigravity_k.engine.extraction_ab_test",
    }
)


class LogLevelManager:
    """Python logging 레벨을 동적으로 관리합니다.

    Thread-safe 하며, 원래 로그 레벨을 보관하여 debug mode 해제 시 복원할 수 있습니다.
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _debug_mode_active: ClassVar[bool] = False
    _saved_levels: ClassVar[dict[str, int]] = {}

    # 공통 로그 레벨 이름 → 숫자 매핑 (사용자에게 표시용)
    LEVEL_NAMES: ClassVar[dict[str, int]] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    @classmethod
    def _normalize_level(cls, level: str | int) -> int:
        """레벨 이름 또는 숫자를 Python logging 레벨 숫자로 변환."""
        if isinstance(level, int):
            return level
        return cls.LEVEL_NAMES.get(level.upper(), logging.INFO)

    @classmethod
    def _get_level_name(cls, level: int) -> str:
        """Python logging 레벨 숫자를 이름으로 변환."""
        return str(logging.getLevelName(level))

    @classmethod
    def discover_loggers(cls) -> list[LogInfo]:
        """현재 등록된 모든 로거를 탐색하여 레벨 정보를 반환합니다.

        Returns:
            ``[{name, level, level_name, effective_level, effective_level_name, handlers}, ...]``
        """
        result: list[LogInfo] = []
        seen: set[str] = set()

        # root logger 포함
        root = logging.getLogger()
        seen.add("root")
        result.append(
            {
                "name": "root",
                "level": root.level,
                "level_name": cls._get_level_name(root.level),
                "effective_level": root.getEffectiveLevel(),
                "effective_level_name": cls._get_level_name(root.getEffectiveLevel()),
                "handlers": len(root.handlers),
            }
        )

        # manager 로거 dict에서 antigravity_k 관련 로거 수집
        manager = logging.root.manager
        logger_dict = cast(Mapping[str, object], getattr(manager, "loggerDict", {}))
        for name, logger_ref in logger_dict.items():
            if name not in seen and name.startswith(ROOT_LOGGER_NAME):
                seen.add(name)
                try:
                    if isinstance(logger_ref, logging.Logger):
                        logger_obj = logger_ref
                    elif isinstance(logger_ref, logging.PlaceHolder):
                        continue
                    else:
                        try:
                            logger_obj = logging.getLogger(name)
                        except Exception:
                            continue

                    result.append(
                        {
                            "name": logger_obj.name,
                            "level": logger_obj.level,
                            "level_name": cls._get_level_name(logger_obj.level),
                            "effective_level": logger_obj.getEffectiveLevel(),
                            "effective_level_name": cls._get_level_name(logger_obj.getEffectiveLevel()),
                            "handlers": len(logger_obj.handlers),
                        }
                    )
                except Exception:
                    continue

        # KNOWN_LOGGERS 중 빠진 것 추가 (런타임에 아직 생성되지 않은 로거 포함)
        for known_name in KNOWN_LOGGERS:
            if known_name not in seen:
                seen.add(known_name)
                logger_obj = logging.getLogger(known_name)
                result.append(
                    {
                        "name": logger_obj.name,
                        "level": logger_obj.level,
                        "level_name": cls._get_level_name(logger_obj.level),
                        "effective_level": logger_obj.getEffectiveLevel(),
                        "effective_level_name": cls._get_level_name(logger_obj.getEffectiveLevel()),
                        "handlers": len(logger_obj.handlers),
                    }
                )

        result.sort(key=lambda x: str(x["name"]))
        return result

    @classmethod
    def set_level(cls, logger_name: str, level: str | int) -> SetLevelResult:
        """특정 로거의 레벨을 변경합니다.

        Args:
            logger_name: 로거 이름 (e.g. ``"antigravity_k.api"``, ``"root"``)
            level: 로그 레벨 (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``)

        Returns:
            ``{name, previous_level, current_level, previous_level_name, current_level_name}``
        """
        effective_name = "" if logger_name == "root" else logger_name
        logger_obj = logging.getLogger(effective_name)
        previous = logger_obj.level
        new_level = cls._normalize_level(level)
        logger_obj.setLevel(new_level)

        # debug mode 저장에도 반영
        with cls._lock:
            if cls._debug_mode_active and logger_name not in cls._saved_levels:
                cls._saved_levels[logger_name] = previous

        return {
            "name": logger_name,
            "previous_level": previous,
            "current_level": new_level,
            "previous_level_name": cls._get_level_name(previous),
            "current_level_name": cls._get_level_name(new_level),
        }

    @classmethod
    def set_all_levels(cls, level: str | int) -> SetAllLevelsResult:
        """``antigravity_k.*`` 네임스페이스의 모든 로거 레벨을 한 번에 변경합니다.

        Args:
            level: 로그 레벨

        Returns:
            ``{target_level, target_level_name, updated_count, loggers: [...]}``
        """
        new_level = cls._normalize_level(level)
        loggers = cls.discover_loggers()
        updated: list[SetLevelResult] = []

        for info in loggers:
            if info["name"] == "root":
                continue
            result = cls.set_level(str(info["name"]), new_level)
            updated.append(result)

        return {
            "target_level": new_level,
            "target_level_name": cls._get_level_name(new_level),
            "updated_count": len(updated),
            "loggers": updated,
        }

    @classmethod
    def enable_debug_mode(cls) -> EnableDebugResult:
        """디버그 모드를 활성화합니다.

        ``antigravity_k.*`` 네임스페이스의 모든 로거를 DEBUG로 변경하고,
        원래 레벨을 저장합니다.

        Returns:
            ``{success, message, updated_count}``
        """
        with cls._lock:
            if cls._debug_mode_active:
                return {"success": True, "message": "Debug mode is already active.", "updated_count": 0}
            cls._debug_mode_active = True
            cls._saved_levels = {}

        # 모든 로거의 현재 레벨 저장 후 DEBUG로 변경
        loggers = cls.discover_loggers()
        for info in loggers:
            if info["name"] == "root":
                continue
            with cls._lock:
                cls._saved_levels[info["name"]] = info["level"]
            _ = cls.set_level(str(info["name"]), logging.DEBUG)

        # httpx, httpcore 등 외부 라이브러리도 DEBUG로
        for ext_logger in ["httpx", "httpcore", "urllib3", "asyncio"]:
            ext = logging.getLogger(ext_logger)
            with cls._lock:
                if ext_logger not in cls._saved_levels:
                    cls._saved_levels[ext_logger] = ext.level
            ext.setLevel(logging.DEBUG)

        return {
            "success": True,
            "message": "Debug mode enabled. All antigravity_k.* loggers set to DEBUG.",
            "updated_count": len(loggers),
        }

    @classmethod
    def disable_debug_mode(cls) -> DisableDebugResult:
        """디버그 모드를 비활성화하고 원래 로그 레벨로 복원합니다.

        Returns:
            ``{success, message, restored_count}``
        """
        with cls._lock:
            if not cls._debug_mode_active:
                return {"success": True, "message": "Debug mode is not active.", "restored_count": 0}
            saved = dict(cls._saved_levels)
            cls._debug_mode_active = False
            cls._saved_levels = {}

        restored = 0
        for logger_name, original_level in saved.items():
            try:
                logger_obj = logging.getLogger("" if logger_name == "root" else logger_name)
                logger_obj.setLevel(original_level)
                restored += 1
            except Exception:
                continue

        return {
            "success": True,
            "message": "Debug mode disabled. Original log levels restored.",
            "restored_count": restored,
        }

    @classmethod
    def is_debug_mode(cls) -> bool:
        """디버그 모드 활성화 여부를 반환합니다."""
        with cls._lock:
            return cls._debug_mode_active


__all__ = [
    "LogLevelManager",
    "KNOWN_LOGGERS",
    "ROOT_LOGGER_NAME",
]
