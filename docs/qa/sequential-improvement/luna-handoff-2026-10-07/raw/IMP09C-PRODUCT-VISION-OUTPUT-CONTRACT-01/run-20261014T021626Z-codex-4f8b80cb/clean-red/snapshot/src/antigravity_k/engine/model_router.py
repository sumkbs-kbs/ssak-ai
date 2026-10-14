"""Ssak-Ai: 스마트 모델 라우터.

================================
9Router 패턴 이식 — 3-Tier 폴백, 라운드로빈, 로드밸런싱 전략 지원.

핵심 개념:
- ModelCombo: 여러 모델을 하나의 "콤보"로 묶어 관리
- ModelRouter: 콤보 내에서 최적의 모델을 자동 선택
- UnavailabilityTracker: 실패한 모델의 지수 백오프 쿨다운 관리
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, TypedDict, cast, final, overload, override

from pydantic import ValidationError

from .model_calibration import ModelQualityCalibrationConfig, ModelQualityCalibrationStore, TaskBenchmarkMetrics
from .model_policy import ModelRoutingPolicy
from .model_registry import ModelProfile, ModelRegistry

logger = logging.getLogger("antigravity_k.model_router")

_DEFAULT_CONFIDENCE_EVALUATOR = "qwen3.6:latest"


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


class _OperationalMetric(TypedDict):
    model: str
    outcome_count: int
    task_success_rate: float | None
    tool_accuracy: float | None
    retry_rate: float | None


class _QualityCalibrationStatus(TypedDict):
    enabled: bool
    eligible_models: list[str]
    ineligible_models: list[str]
    operational_metrics: list[_OperationalMetric]


class _RouterStatus(dict[str, object]):
    @overload
    def __getitem__(self, key: Literal["quality_calibration"]) -> _QualityCalibrationStatus: ...

    @overload
    def __getitem__(self, key: Literal["unavailable"]) -> list[dict[str, object]]: ...

    @overload
    def __getitem__(self, key: Literal["combos"]) -> list[dict[str, object]]: ...

    @overload
    def __getitem__(self, key: str) -> object: ...

    @override
    def __getitem__(self, key: str) -> object:
        return super().__getitem__(key)


# ─── 전략 열거형 ─────────────────────────────────────────────────────


class RouteStrategy(Enum):
    """모델 선택 전략."""

    FALLBACK = "fallback"  # 순서대로 시도, 실패 시 다음 모델
    ROUND_ROBIN = "round-robin"  # 순환 분배
    LOAD_BALANCE = "load-balance"  # 메모리 부하 기반 분배
    COLLECTIVE = "collective"  # 여러 모델 제안/비판/합성 집단지성 실행
    CASCADING = "cascading"  # 경량→중형→대형 점진적 에스컬레이션 (신뢰도 기반)


# ─── 데이터 클래스 ───────────────────────────────────────────────────


@dataclass
class ModelCombo:
    """모델 콤보: 여러 모델을 하나의 그룹으로 관리.

    예시 (config.yaml):
      combos:
        coding-stack:
          models: [qwen3-72b, qwen-coder-32b, llama4-scout]
          strategy: fallback
    """

    name: str
    models: list[str]  # 모델 이름 목록 (우선순위순)
    strategy: RouteStrategy = RouteStrategy.FALLBACK
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, data: Mapping[str, object]) -> ModelCombo:
        """From Dict.

        Args:
            name (str): str name.
            data (dict): dict data.

        Returns:
            'ModelCombo': The 'modelcombo' result.

        """
        strategy_str = _text(data.get("strategy", "fallback"), "fallback")
        try:
            strategy = RouteStrategy(strategy_str)
        except ValueError:
            logger.warning(
                "콤보 '%s': 알 수 없는 전략 '%s', fallback으로 대체합니다.",
                name,
                strategy_str,
            )
            strategy = RouteStrategy.FALLBACK

        raw_models = data.get("models", [])
        models = (
            [item for item in cast(list[object], raw_models) if isinstance(item, str)]
            if isinstance(raw_models, list)
            else []
        )
        return cls(
            name=name,
            models=models,
            strategy=strategy,
            description=_text(data.get("description", "")),
        )


@dataclass
class UnavailableEntry:
    """사용 불가 모델 추적 항목."""

    model_name: str
    marked_at: float  # 마킹 시각 (timestamp)
    cooldown_sec: float  # 현재 쿨다운 (지수 증가)
    retry_count: int = 0  # 재시도 횟수
    reason: str = ""  # 실패 사유

    @property
    def available_at(self) -> float:
        """다시 사용 가능해지는 시각."""
        return self.marked_at + self.cooldown_sec

    def is_expired(self) -> bool:
        """쿨다운이 만료되었는지 확인."""
        return time.time() >= self.available_at

    def remaining_sec(self) -> float:
        """남은 쿨다운 시간 (초)."""
        return max(0.0, self.available_at - time.time())


# ─── 비가용 추적기 ───────────────────────────────────────────────────


@final
class UnavailabilityTracker:
    """실패한 모델의 지수 백오프 쿨다운 관리.

    9Router 패턴: markAccountUnavailable() → 지수 백오프
    - 첫 실패: base_cooldown (60초)
    - 두 번째: base_cooldown × 2
    - 세 번째: base_cooldown × 4
    - 최대: max_cooldown (3600초)
    """

    def __init__(
        self,
        base_cooldown_sec: float = 60.0,
        max_cooldown_sec: float = 3600.0,
        backoff_multiplier: float = 2.0,
    ):
        """Initialize the UnavailabilityTracker.

        Args:
            base_cooldown_sec (float): float base cooldown sec.
            max_cooldown_sec (float): float max cooldown sec.
            backoff_multiplier (float): float backoff multiplier.

        """
        self._base: float = base_cooldown_sec
        self._max: float = max_cooldown_sec
        self._multiplier: float = backoff_multiplier
        self._entries: dict[str, UnavailableEntry] = {}

    def mark_unavailable(self, model_name: str, reason: str = "") -> None:
        """모델을 사용 불가로 마킹 (지수 백오프 적용)."""
        existing = self._entries.get(model_name)

        if existing and not existing.is_expired():
            # 이미 마킹됨 → 재시도 횟수 증가, 쿨다운 확장
            retry = existing.retry_count + 1
            cooldown = min(
                self._base * (self._multiplier**retry),
                self._max,
            )
        else:
            retry = 0
            cooldown = self._base

        entry = UnavailableEntry(
            model_name=model_name,
            marked_at=time.time(),
            cooldown_sec=cooldown,
            retry_count=retry,
            reason=reason,
        )
        self._entries[model_name] = entry
        logger.warning(
            "[%s] 사용 불가 마킹 — 쿨다운: %s초, 재시도: %s회, 사유: %s",
            model_name,
            cooldown,
            retry,
            reason or "없음",
        )

    def is_available(self, model_name: str) -> bool:
        """모델이 사용 가능한지 확인."""
        entry = self._entries.get(model_name)
        if entry is None:
            return True
        if entry.is_expired():
            # 쿨다운 만료 → 자동 복구
            logger.info("[%s] 쿨다운 만료, 재활성화", model_name)
            del self._entries[model_name]
            return True
        return False

    def mark_available(self, model_name: str) -> None:
        """모델을 수동으로 사용 가능 상태로 복원."""
        if model_name in self._entries:
            del self._entries[model_name]
            logger.info("[%s] 수동 재활성화", model_name)

    def get_entry(self, model_name: str) -> UnavailableEntry | None:
        """비가용 항목 조회."""
        return self._entries.get(model_name)

    def status(self) -> list[dict[str, object]]:
        """현재 비가용 모델 목록 반환."""
        result: list[dict[str, object]] = []
        for name, entry in self._entries.items():
            result.append(
                {
                    "model": name,
                    "reason": entry.reason,
                    "retry_count": entry.retry_count,
                    "remaining_sec": round(entry.remaining_sec(), 1),
                    "expired": entry.is_expired(),
                },
            )
        return result

    def clear_expired(self) -> int:
        """만료된 항목 정리, 정리된 수 반환."""
        expired = [name for name, entry in self._entries.items() if entry.is_expired()]
        for name in expired:
            del self._entries[name]
        return len(expired)

    def clear_all(self) -> None:
        """모든 비가용 마킹 초기화."""
        self._entries.clear()
        logger.info("모든 비가용 마킹 초기화")


# ─── 커스텀 예외 ─────────────────────────────────────────────────────


@final
class AllModelsUnavailableError(Exception):
    """콤보 내 모든 모델이 사용 불가."""

    def __init__(self, combo_name: str, tried: list[str]):
        """Initialize the AllModelsUnavailableError.

        Args:
            combo_name (str): str combo name.
            tried (list[str]): list[str] tried.

        """
        self.combo_name: str = combo_name
        self.tried: list[str] = tried
        super().__init__(f"콤보 '{combo_name}' 내 모든 모델이 사용 불가: {tried}")


@final
class ComboNotFoundError(Exception):
    """요청한 콤보가 등록되어 있지 않음."""

    def __init__(self, combo_name: str, available: list[str]):
        """Initialize the ComboNotFoundError.

        Args:
            combo_name (str): str combo name.
            available (list[str]): list[str] available.

        """
        self.combo_name: str = combo_name
        self.available: list[str] = available
        super().__init__(f"콤보 '{combo_name}'을 찾을 수 없습니다. 등록된 콤보: {available}")


# ─── 메인 라우터 ─────────────────────────────────────────────────────


@final
class ModelRouter:
    """스마트 모델 라우터 — 9Router 패턴 기반.

    핵심 기능:
    - route(combo_name): 콤보 내에서 최적의 모델 선택
    - mark_failure(model_name): 실패한 모델을 쿨다운 처리
    - status(): 라우터 상태 조회

    사용 예시:
        router = ModelRouter(registry)
        router.register_combo(ModelCombo(
            name="coding-stack",
            models=["qwen3-72b", "qwen-coder-32b", "llama4-scout"],
            strategy=RouteStrategy.FALLBACK,
        ))
        profile = router.route("coding-stack")
    """

    def __init__(
        self,
        registry: ModelRegistry,
        base_cooldown_sec: float = 60.0,
        max_cooldown_sec: float = 3600.0,
        max_retries: int = 3,
    ):
        """Initialize the ModelRouter.

        Args:
            registry (ModelRegistry): ModelRegistry registry.
            base_cooldown_sec (float): float base cooldown sec.
            max_cooldown_sec (float): float max cooldown sec.
            max_retries (int): int max retries.

        """
        self._registry: ModelRegistry = registry
        self._combos: dict[str, ModelCombo] = {}
        self._tracker: UnavailabilityTracker = UnavailabilityTracker(
            base_cooldown_sec=base_cooldown_sec,
            max_cooldown_sec=max_cooldown_sec,
        )
        self._max_retries: int = max_retries
        # 라운드로빈 인덱스 추적
        self._rr_index: dict[str, int] = {}
        self._provider_capabilities: dict[str, dict[str, object]] = {}
        self._policy_exclusion_logged: set[str] = set()

        # config.yaml에서 콤보 자동 로드
        self._load_combos_from_registry()

        self._load_router_settings()

    def _load_router_settings(self) -> None:
        router_raw = _mapping(getattr(self._registry, "_raw", {})).get("router", {})
        router = _mapping(router_raw)
        model_policy_raw = router.get("model_policy", {})
        self._model_policy = ModelRoutingPolicy.from_mapping(
            _mapping(model_policy_raw),
        )
        # router.max_retries / router.default_strategy — 기존에 읽히지 않아
        # config의 값이 조용히 무시되었다.
        config_max_retries = _int(router.get("max_retries"), 0)
        if config_max_retries > 0:
            self._max_retries = config_max_retries
        self.default_strategy: str = _text(router.get("default_strategy"), "fallback")
        self.cascade_on_low_confidence: bool = _bool(router.get("cascade_on_low_confidence"), False)
        self.cascade_confidence_threshold: float = _float(router.get("cascade_confidence_threshold"), 0.4)
        self.cascade_max_escalations: int = _int(router.get("cascade_max_escalations"), 2)
        self.confidence_evaluator_enabled: bool = _bool(router.get("confidence_evaluator_enabled"), False)
        self.confidence_evaluator_model: str = _text(
            router.get("confidence_evaluator_model"), _DEFAULT_CONFIDENCE_EVALUATOR
        )
        self.confidence_evaluator_min_params_b: float = _float(router.get("confidence_evaluator_min_params_b"), 20.0)
        self.confidence_evaluator_max_tokens: int = _int(router.get("confidence_evaluator_max_tokens"), 32)
        try:
            calibration_config = ModelQualityCalibrationConfig.model_validate(router.get("quality_calibration", {}))
        except ValidationError:
            logger.warning("모델 품질 calibration 설정이 올바르지 않아 비활성화합니다.")
            calibration_config = ModelQualityCalibrationConfig()
        registry_path = getattr(self._registry, "_config_path", None)
        match registry_path:
            case str() as config_path:
                config_directory = Path(config_path).resolve().parent
            case Path() as config_path:
                config_directory = config_path.resolve().parent
            case _:
                config_directory = Path.cwd()
        self._quality_calibration = ModelQualityCalibrationStore.from_config(
            calibration_config,
            config_directory,
        )

    def _load_combos_from_registry(self) -> None:
        """ModelRegistry의 raw config에서 combos 섹션 로드."""
        raw = _mapping(getattr(self._registry, "_raw", {}))
        combos_data = _mapping(raw.get("combos", {}))

        default_strategy = getattr(self, "default_strategy", "fallback")
        for combo_name, combo_config in combos_data.items():
            if isinstance(combo_config, dict):
                combo_map = _mapping(cast(object, combo_config))
                if not str(combo_map.get("strategy", "") or "").strip():
                    combo_map = {**combo_map, "strategy": default_strategy}
                combo = ModelCombo.from_dict(combo_name, combo_map)
                self._combos[combo_name] = combo
                logger.info(
                    "콤보 로드: %s (%s개 모델, %s)",
                    combo_name,
                    len(combo.models),
                    combo.strategy.value,
                )

    def reload(self) -> None:
        """레지스트리 변경 후 콤보를 핫 리로드합니다."""
        self._load_router_settings()
        self._combos.clear()
        self._load_combos_from_registry()
        logger.info("ModelRouter 콤보 핫 리로드 완료")

    # ─── 콤보 관리 ───────────────────────────────────────────────────

    def register_combo(self, combo: ModelCombo) -> None:
        """콤보 등록."""
        self._combos[combo.name] = combo
        logger.info("콤보 등록: %s", combo.name)

    def unregister_combo(self, name: str) -> bool:
        """콤보 등록 해제."""
        if name in self._combos:
            del self._combos[name]
            if name in self._rr_index:
                del self._rr_index[name]
            return True
        return False

    def get_combo(self, name: str) -> ModelCombo | None:
        """콤보 조회."""
        return self._combos.get(name)

    def list_combos(self) -> list[ModelCombo]:
        """등록된 모든 콤보 반환."""
        return list(self._combos.values())

    # ─── 핵심 라우팅 ─────────────────────────────────────────────────

    def route(self, combo_name: str) -> ModelProfile:
        """콤보 내에서 최적의 모델을 선택하여 반환.

        전략에 따라 동작이 다릅니다:
        - FALLBACK: 순서대로 시도, 사용 불가 시 다음 모델
        - ROUND_ROBIN: 순환 분배 (부하 분산)
        - LOAD_BALANCE: 메모리 사용량 기반 최적 선택
        - COLLECTIVE: ModelManager의 집단지성 실행기가 전체 후보를 호출.
          단일 라우팅이 필요한 레거시 경로에서는 fallback과 동일하게 동작.
        """
        combo = self._combos.get(combo_name)
        if combo is None:
            raise ComboNotFoundError(
                combo_name,
                list(self._combos.keys()),
            )

        # 만료된 비가용 항목 정리
        _ = self._tracker.clear_expired()

        if combo.strategy == RouteStrategy.FALLBACK:
            return self._route_fallback(combo)
        elif combo.strategy == RouteStrategy.ROUND_ROBIN:
            return self._route_round_robin(combo)
        elif combo.strategy == RouteStrategy.LOAD_BALANCE:
            return self._route_load_balance(combo)
        elif combo.strategy == RouteStrategy.CASCADING:
            return self._route_cascading(combo)
        elif combo.strategy == RouteStrategy.COLLECTIVE:
            return self._route_fallback(combo)
        else:
            return self._route_fallback(combo)

    def route_single(self, model_name: str) -> ModelProfile:
        """단일 모델 직접 라우팅 (콤보 없이)."""
        if not self._tracker.is_available(model_name):
            entry = self._tracker.get_entry(model_name)
            remaining = entry.remaining_sec() if entry else 0
            raise AllModelsUnavailableError(
                f"single:{model_name}",
                [f"{model_name} (쿨다운 {remaining:.0f}초 남음)"],
            )

        profile = self._registry.get_model(model_name)
        if profile is None:
            raise ValueError(f"모델 '{model_name}'이 레지스트리에 없습니다.")
        decision = self._model_policy.decide(profile, explicit=True)
        if not decision.allowed:
            raise ValueError(
                f"모델 '{model_name}'이 라우팅 정책에 의해 제외되었습니다: {decision.reason}",
            )
        return profile

    def available_model_names(self, combo_name: str) -> list[str]:
        """콤보 안에서 현재 라우팅 가능한 모델 이름 목록을 반환합니다."""
        combo = self._combos.get(combo_name)
        if combo is None:
            raise ComboNotFoundError(combo_name, list(self._combos.keys()))

        _ = self._tracker.clear_expired()
        return [profile.name for profile in self._candidate_profiles(combo.models)]

    def _available_profile(self, model_name: str) -> ModelProfile | None:
        if not self._tracker.is_available(model_name):
            return None
        profile = self._registry.get_model(model_name)
        if profile is None:
            return None
        decision = self._model_policy.decide(profile)
        if not decision.allowed:
            # 제외는 운영에 보여야 한다 — debug 레벨이면 구성된 폴백 체인이
            # 조용히 비어 있는지 알 수 없다. 모델당 1회만 경고한다.
            logged = getattr(self, "_policy_exclusion_logged", None)
            if logged is None:
                logged = set()
                self._policy_exclusion_logged = logged
            if model_name not in logged:
                logged.add(model_name)
                logger.warning(
                    "[%s] 라우팅 정책에 의해 제외(%s) — 콤보 폴백 체인에서 제거됨",
                    model_name,
                    decision.reason,
                )
            return None
        if not self._quality_calibration.is_eligible(model_name):
            logger.warning("[%s] 품질 calibration 기준 미달로 자동 라우팅에서 제외", model_name)
            return None
        return profile

    def _candidate_profiles(self, model_names: list[str]) -> list[ModelProfile]:
        profiles = [
            profile for model_name in model_names if (profile := self._available_profile(model_name)) is not None
        ]
        return self._model_policy.prioritize(profiles)

    # ─── 전략별 라우팅 구현 ──────────────────────────────────────────

    def _route_fallback(self, combo: ModelCombo) -> ModelProfile:
        """폴백 전략: 순서대로 시도, 사용 불가 모델은 건너뜀.

        9Router의 handleSingleModelChat → while(true) 폴백 루프 패턴.
        """
        for profile in self._candidate_profiles(combo.models):
            logger.info("[%s] 라우팅 → %s (fallback)", combo.name, profile.name)
            return profile

        raise AllModelsUnavailableError(combo.name, combo.models)

    def _route_round_robin(self, combo: ModelCombo) -> ModelProfile:
        """라운드로빈 전략: 사용 가능한 모델을 순환 선택."""
        available = self._candidate_profiles(combo.models)

        if not available:
            raise AllModelsUnavailableError(combo.name, combo.models)

        idx = self._rr_index.get(combo.name, 0) % len(available)
        selected = available[idx]
        self._rr_index[combo.name] = idx + 1

        logger.info("[%s] 라우팅 → %s (round-robin, idx=%s)", combo.name, selected.name, idx)
        return selected

    def _route_load_balance(self, combo: ModelCombo) -> ModelProfile:
        """로드밸런싱 전략: 메모리 사용량이 적은 모델 우선."""
        available = self._candidate_profiles(combo.models)

        if not available:
            raise AllModelsUnavailableError(combo.name, combo.models)

        # 메모리 적게 쓰는 모델 우선 (경량 모델 선호)
        selected = min(available, key=lambda p: p.estimated_memory_gb)
        logger.info(
            "[%s] 라우팅 → %s (load-balance, %sGB)",
            combo.name,
            selected.name,
            selected.estimated_memory_gb,
        )
        return selected

    def _route_cascading(self, combo: ModelCombo) -> ModelProfile:
        """Cascading 전략: 경량 모델부터 시도하고, 신뢰도가 낮으면 자동 에스컬레이션.

        모델 목록의 순서가 곧 에스컬레이션 티어입니다:
          - models[0]: Tier 1 (경량, 4B 급) — 빠른 응답
          - models[1]: Tier 2 (중형, 24B 급) — 품질 응답
          - models[2]: Tier 3 (대형, 72B 급 또는 MoA) — 최고 품질

        route()는 가장 가벼운 가용 모델을 반환하고,
        실제 에스컬레이션은 ModelManager에서 응답 품질을 평가한 후
        escalate()를 호출하여 다음 티어 모델을 받아옵니다.
        """
        for profile in self._candidate_profiles(combo.models):
            logger.info(
                "[%s] 라우팅 → %s (cascading, Tier %s/%s)",
                combo.name,
                profile.name,
                combo.models.index(profile.name) + 1,
                len(combo.models),
            )
            return profile

        raise AllModelsUnavailableError(combo.name, combo.models)

    def escalate(self, combo_name: str, current_model: str) -> ModelProfile | None:
        """현재 모델에서 다음 티어로 에스컬레이션합니다.

        Args:
            combo_name: 콤보 이름
            current_model: 현재 사용 중인 모델 이름

        Returns:
            다음 티어의 ModelProfile, 또는 없으면 None (최고 티어 도달)

        """
        combo = self._combos.get(combo_name)
        if combo is None:
            return None

        candidates = self._candidate_profiles(combo.models)
        candidate_names = [profile.name for profile in candidates]
        try:
            idx = candidate_names.index(current_model)
        except ValueError:
            return None

        # 다음 티어부터 가용 모델 탐색
        for profile in candidates[idx + 1 :]:
            logger.info(
                "[%s] 에스컬레이션: %s → %s (Tier %s)",
                combo_name,
                current_model,
                profile.name,
                combo.models.index(profile.name) + 1,
            )
            return profile

        logger.info("[%s] 에스컬레이션 불가: %s이 최고 티어", combo_name, current_model)
        return None

    def select_confidence_evaluator(self, preferred_name: str | None = None) -> ModelProfile | None:
        requested_name = preferred_name or self.confidence_evaluator_model
        requested_profile = self._registry.get_model(requested_name) if requested_name else None

        if requested_profile is not None:
            if self._is_large_enough_for_confidence(requested_profile):
                if self._available_profile(requested_profile.name) is not None:
                    return requested_profile
                return None
            if preferred_name or requested_name != _DEFAULT_CONFIDENCE_EVALUATOR:
                logger.warning(
                    "신뢰도 평가기 %s는 %.1fB 미만이라 사용할 수 없습니다.",
                    requested_profile.name,
                    self.confidence_evaluator_min_params_b,
                )
                return None

        candidates = [
            profile
            for profile in self._registry.list_models()
            if set(profile.supported_roles).intersection({"reasoning", "coding"})
            and self._is_large_enough_for_confidence(profile)
            and self._available_profile(profile.name) is not None
        ]
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda profile: (
                0 if profile.name == _DEFAULT_CONFIDENCE_EVALUATOR else 1,
                profile.parameter_count_b,
                profile.name,
            ),
        )

    def _is_large_enough_for_confidence(self, profile: ModelProfile) -> bool:
        return profile.effective_parameter_count_b >= self.confidence_evaluator_min_params_b

    @staticmethod
    def parse_confidence_score(raw: str) -> float | None:
        import re

        numeric = re.fullmatch(r"\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*", raw)
        if numeric:
            return float(numeric.group(1))

        try:
            payload = cast(object, json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            payload = None

        if isinstance(payload, dict):
            payload_mapping = _mapping(cast(object, payload))
            value = payload_mapping.get("score", payload_mapping.get("confidence"))
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    score = -1.0
                if 0.0 <= score <= 1.0:
                    return score

        line_pattern = re.compile(
            r"\s*(?:score|confidence)\s*(?:is|should be|[:=])\s*" + r"(0(?:\.\d+)?|1(?:\.0+)?)\s*[.!]?\s*$",
            re.IGNORECASE,
        )
        for line in reversed(raw.splitlines()):
            match = line_pattern.fullmatch(line)
            if match:
                return float(match.group(1))
        return None

    @staticmethod
    def estimate_confidence(response: str) -> float:
        """응답 텍스트에서 신뢰도 점수를 휴리스틱으로 추정합니다.

        신뢰도가 낮은 응답의 특징:
        - 매우 짧은 응답 (정보 부족)
        - "확실하지 않습니다", "모르겠습니다" 등 불확실성 표현
        - 반복적인 패턴
        - 도구 호출 실패/에러 포함

        Returns:
            0.0 ~ 1.0 사이의 신뢰도 점수

        """
        import re

        if not response or len(response.strip()) < 20:
            return 0.1

        score = 1.0

        # 너무 짧은 응답 감점
        if len(response) < 100:
            score *= 0.6
        elif len(response) < 200:
            score *= 0.8

        # 불확실성 표현 감점
        uncertainty_patterns = [
            r"확실하지 않",
            r"모르겠",
            r"잘 모르",
            r"정확하지 않",
            r"불확실",
            r"추측",
            r"I'm not sure",
            r"I don't know",
            r"uncertain",
        ]
        for pat in uncertainty_patterns:
            if re.search(pat, response, re.IGNORECASE):
                score *= 0.7
                break

        # 에러/실패 표현 감점
        error_patterns = [
            r"\[API Error",
            r"\[Error",
            r"실패",
            r"failed",
            r"error",
            r"exception",
        ]
        for pat in error_patterns:
            if re.search(pat, response, re.IGNORECASE):
                score *= 0.5
                break

        # 반복 패턴 감점
        sentences = response.split(".")
        if len(sentences) > 3:
            unique_ratio = len(set(sentences)) / len(sentences)
            if unique_ratio < 0.5:
                score *= 0.5

        return max(0.0, min(1.0, score))

    # ─── 실패/복구 관리 ──────────────────────────────────────────────

    def mark_failure(self, model_name: str, reason: str = "") -> None:
        """모델 사용 실패 시 호출 — 쿨다운 등록."""
        self._tracker.mark_unavailable(model_name, reason)

    def mark_recovered(self, model_name: str) -> None:
        """모델 복구 시 호출 — 쿨다운 해제."""
        self._tracker.mark_available(model_name)

    def get_temperature_boost(self, model_name: str) -> float:
        """Return a temperature boost for the given model (0.0 = no boost)."""
        _ = model_name
        return 0.0

    def set_provider_capability(self, model_name: str, capability: Mapping[str, object]) -> None:
        self._provider_capabilities[model_name] = dict(capability)

    def set_task_calibration(self, model_name: str, metrics: TaskBenchmarkMetrics | None) -> None:
        self._quality_calibration.set_task_metrics(model_name, metrics)

    # ─── 상태 조회 ───────────────────────────────────────────────────

    def status(self) -> _RouterStatus:
        """라우터 전체 상태 반환."""
        combos_info: list[dict[str, object]] = []
        for combo in self._combos.values():
            available_models = self.available_model_names(combo.name)
            combos_info.append(
                {
                    "name": combo.name,
                    "strategy": combo.strategy.value,
                    "total_models": len(combo.models),
                    "available_models": len(available_models),
                    "models": combo.models,
                    "description": combo.description,
                },
            )

        calibration_summaries = self._quality_calibration.summaries()
        operational_metrics: list[_OperationalMetric] = [
            {
                "model": summary.model_name,
                "outcome_count": summary.task_outcome_count,
                "task_success_rate": summary.task_success_rate,
                "tool_accuracy": summary.task_tool_accuracy,
                "retry_rate": summary.task_retry_rate,
            }
            for summary in calibration_summaries
            if summary.task_outcome_count > 0
        ]
        return _RouterStatus(
            {
                "combos": combos_info,
                "unavailable": self._tracker.status(),
                "max_retries": self._max_retries,
                "provider_capabilities": dict(self._provider_capabilities),
                "model_policy": self._model_policy.to_dict(),
                "quality_calibration": {
                    "enabled": self._quality_calibration.enabled,
                    "eligible_models": [
                        summary.model_name
                        for summary in calibration_summaries
                        if self._quality_calibration.is_eligible(summary.model_name)
                    ],
                    "ineligible_models": [
                        summary.model_name
                        for summary in calibration_summaries
                        if not self._quality_calibration.is_eligible(summary.model_name)
                    ],
                    "operational_metrics": operational_metrics,
                },
            },
        )

    def summary(self) -> str:
        """사람이 읽기 쉬운 요약."""
        lines = ["=== Model Router ==="]
        for combo in self._combos.values():
            available = self.available_model_names(combo.name)
            lines.append(f"\n[{combo.name}] ({combo.strategy.value})")
            for m in combo.models:
                marker = "✓" if m in available else "✗"
                lines.append(f"  {marker} {m}")
            lines.append(f"  → 사용 가능: {len(available)}/{len(combo.models)}")

        unavailable = self._tracker.status()
        if unavailable:
            lines.append("\n[비가용 모델]")
            for entry in unavailable:
                lines.append(
                    f"  ✗ {entry['model']} — 남은 시간: {entry['remaining_sec']}초, 재시도: {entry['retry_count']}회",
                )

        return "\n".join(lines)
