from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_registry import ModelProfile


@dataclass(frozen=True, slots=True)
class ModelPolicyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ModelRoutingPolicy:
    enabled: bool = False
    prefer_local: bool = True
    max_parameter_count_b: float = 0.0
    min_local_parameter_count_b: float = 0.0
    allow_small_local_models: bool = False
    # 1k 토큰당 평균 비용 상한(USD). 0.0이면 비용 기준 미적용.
    max_cost_per_1k_tokens_usd: float = 0.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ModelRoutingPolicy:
        return cls(
            enabled=_as_bool(raw.get("enabled"), default=False),
            prefer_local=_as_bool(raw.get("prefer_local"), default=True),
            max_parameter_count_b=_as_non_negative_float(raw.get("max_parameter_count_b")),
            min_local_parameter_count_b=_as_non_negative_float(raw.get("min_local_parameter_count_b")),
            allow_small_local_models=_as_bool(raw.get("allow_small_local_models"), default=False),
            max_cost_per_1k_tokens_usd=_as_non_negative_float(raw.get("max_cost_per_1k_tokens_usd")),
        )

    def decide(self, profile: ModelProfile, *, explicit: bool = False) -> ModelPolicyDecision:
        if not self.enabled:
            return ModelPolicyDecision(allowed=True, reason="policy_disabled")

        parameter_count_b = profile.effective_parameter_count_b
        if not profile.is_local and self.max_parameter_count_b and parameter_count_b > self.max_parameter_count_b:
            return ModelPolicyDecision(allowed=False, reason="parameter_cap_exceeded")
        if (
            profile.is_local
            and parameter_count_b
            and parameter_count_b < self.min_local_parameter_count_b
            and not self.allow_small_local_models
            and not explicit
        ):
            return ModelPolicyDecision(allowed=False, reason="local_parameter_floor_not_met")
        if self.max_cost_per_1k_tokens_usd and profile.cost_per_1k_tokens_usd > self.max_cost_per_1k_tokens_usd:
            return ModelPolicyDecision(allowed=False, reason="cost_cap_exceeded")
        return ModelPolicyDecision(allowed=True, reason="eligible")

    def prioritize(self, profiles: Sequence[ModelProfile]) -> list[ModelProfile]:
        if not self.enabled or not self.prefer_local:
            return list(profiles)
        return sorted(profiles, key=lambda profile: not profile.is_local)

    def to_dict(self) -> dict[str, bool | float]:
        return {
            "enabled": self.enabled,
            "prefer_local": self.prefer_local,
            "max_parameter_count_b": self.max_parameter_count_b,
            "min_local_parameter_count_b": self.min_local_parameter_count_b,
            "allow_small_local_models": self.allow_small_local_models,
            "max_cost_per_1k_tokens_usd": self.max_cost_per_1k_tokens_usd,
        }


def _as_bool(value: object, *, default: bool) -> bool:
    match value:
        case bool() as parsed:
            return parsed
        case str() as parsed:
            return parsed.strip().lower() in {"1", "true", "yes", "on"}
        case int() | float() as parsed:
            return bool(parsed)
        case _:
            return default


def _as_non_negative_float(value: object) -> float:
    match value:
        case bool():
            return 0.0
        case int() | float() | str() as raw:
            try:
                parsed = float(raw)
            except ValueError:
                return 0.0
            return max(0.0, parsed)
        case _:
            return 0.0
