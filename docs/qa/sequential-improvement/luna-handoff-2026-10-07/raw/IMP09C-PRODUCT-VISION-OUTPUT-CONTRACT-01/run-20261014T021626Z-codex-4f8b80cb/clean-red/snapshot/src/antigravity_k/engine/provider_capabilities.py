from __future__ import annotations

import importlib
from http.client import HTTPResponse
from typing import TYPE_CHECKING
from urllib.request import Request

from antigravity_k.tools.egress_policy import safe_urlopen as _safe_urlopen

from .provider_capability_models import (
    PROVIDER_BACKENDS,
    NativeToolCalling,
    ProviderBackend,
    ProviderCapability,
    ProviderConfigRegistry,
    RuntimeStatus,
)
from .provider_capability_probe import LocalProviderCapabilityProbe
from .provider_capability_probe_runtime import configure_urlopen

__all__ = [
    "LocalProviderCapabilityProbe",
    "importlib",
    "NativeToolCalling",
    "ProviderBackend",
    "ProviderCapability",
    "ProviderConfigRegistry",
    "RuntimeStatus",
    "remediation_hint",
]


safe_urlopen = _safe_urlopen


def _configured_urlopen(target: str | Request, *, timeout: float) -> HTTPResponse:
    return safe_urlopen(target, timeout=timeout)


configure_urlopen(_configured_urlopen)

if TYPE_CHECKING:
    from .model_registry import ModelProfile


def remediation_hint(profile: ModelProfile, capability: ProviderCapability) -> str:
    """Return the next operator action for an unavailable local provider."""
    if capability["runtime_status"] != "unavailable":
        return ""

    detail = capability["detail"]
    match PROVIDER_BACKENDS.get(profile.backend.casefold(), "unknown"):  # noqa: E501  # noqa: MATCH_OK - normalized runtime backend union
        case "ollama":
            if "404" in detail:
                return f"ollama pull {profile.repo}"
            return "ollama serve"
        case "lmstudio":
            if "401" in detail or "403" in detail:
                return "LM Studio 토큰을 .env의 LM_STUDIO_API_KEY에 추가"
            loaded_ids = capability.get("reported_model_ids", [])
            if loaded_ids:
                loaded_id = loaded_ids[0]
                return f"LM Studio에서 {loaded_id}를 로드하거나 config.yaml의 {profile.name} repo를 같은 식별자로 변경"
            if "not loaded" in detail or "no loaded models" in detail:
                return "LM Studio에서 모델을 로드한 뒤 다시 진단"
            return "LM Studio Local Server를 127.0.0.1:1234/v1에서 시작"
        case "unsloth":
            if "adapter" in detail or "transformers" in detail:
                return "uv sync --extra transformers"
            if "not configured" in detail:
                return "UNSLOTH_API_BASE를 loopback OpenAI API 주소로 설정"
            if "401" in detail or "403" in detail:
                return "Unsloth API 토큰을 UNSLOTH_API_KEY에 추가"
            if "loopback" in detail:
                return "Unsloth API를 localhost에 바인딩하고 UNSLOTH_API_BASE를 갱신"
            return "별도 Unsloth API 프로세스를 시작한 뒤 다시 진단"
        case "mlx":
            return "uv sync --extra mlx"
        case "transformers":
            return "uv sync --extra transformers"
        case "unknown":
            return ""
    return ""
