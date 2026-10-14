"""Typed configuration readers shared by orchestrator handlers."""

from collections.abc import Mapping
from typing import Protocol, cast

from antigravity_k.engine.memory_contracts import JsonValue

__all__ = ["_amplification_section", "_cov_settings", "_dict_value", "_raw_config", "cov_settings"]


class OrchestratorConfigLike(Protocol):
    config: Mapping[str, JsonValue] | None


def _raw_config(orch: OrchestratorConfigLike) -> Mapping[str, JsonValue]:
    config = getattr(orch, "config", None)
    return cast(Mapping[str, JsonValue], config) if isinstance(config, Mapping) else {}


def _dict_value(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _amplification_section(orch: OrchestratorConfigLike, name: str) -> dict[str, JsonValue]:
    amplification = _dict_value(_raw_config(orch).get("amplification"))
    return _dict_value(amplification.get(name))


def cov_settings(orch: OrchestratorConfigLike) -> tuple[bool, str, int, float, int]:
    cov = _amplification_section(orch, "cov")
    raw = _raw_config(orch)
    enabled = bool(cov.get("enabled", True))
    configured_model = cov.get("model")
    main_model = _dict_value(raw.get("model")).get("main_model")
    model = (
        configured_model
        if isinstance(configured_model, str) and configured_model
        else (main_model if isinstance(main_model, str) and main_model else "qwen3.6:latest")
    )
    min_len_value = cov.get("min_response_length", 50)
    threshold_value = cov.get("complexity_threshold", 0.4)
    max_iter_value = cov.get("max_revise_iterations", 2)
    min_len = int(min_len_value) if isinstance(min_len_value, (int, float)) else 50
    threshold = float(threshold_value) if isinstance(threshold_value, (int, float)) else 0.4
    max_iter = int(max_iter_value) if isinstance(max_iter_value, (int, float)) else 2
    return enabled, model, min_len, threshold, max_iter


_cov_settings = cov_settings
