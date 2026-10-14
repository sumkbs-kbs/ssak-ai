from __future__ import annotations

import json
import os
import urllib.request
from http.client import HTTPResponse
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request

from pydantic import JsonValue, ValidationError

from antigravity_k.engine.long_context_capabilities import derive_long_context_capability
from antigravity_k.engine.long_context_metadata import infer_long_context_capabilities
from antigravity_k.engine.provider_adapters.unsloth_provider import (
    UnslothEndpointError,
    resolve_unsloth_settings,
)
from antigravity_k.tools.egress_policy import EgressPolicyError
from antigravity_k.tools.egress_policy import safe_urlopen as _safe_urlopen

from .provider_capability_models import (
    RESPONSE_ADAPTER,
    NativeToolCalling,
    ProviderCapability,
    RuntimeStatus,
    UnslothModelList,
)

if TYPE_CHECKING:
    from .model_registry import ModelProfile


def _has_transformers_weights(model_path: Path) -> bool:
    return any(model_path.glob("*.safetensors"))


from .provider_capability_probe_utils import ProviderProbeUtilities


class UrlOpenCallable(Protocol):
    def __call__(self, target: str | Request, *, timeout: float) -> HTTPResponse: ...


_urlopen_provider: UrlOpenCallable | None = None


def configure_urlopen(provider: UrlOpenCallable) -> None:
    global _urlopen_provider
    _urlopen_provider = provider


class ProviderProbeRuntime(ProviderProbeUtilities):
    def _static_unknown(self, profile: ModelProfile) -> ProviderCapability:
        return self._capability(
            profile,
            "unknown",
            "not_required",
            "provider:static",
            "This provider does not expose a local native-tool capability probe.",
        )

    def _endpoint(self, profile: ModelProfile, default_base_url: str) -> tuple[str, str]:
        provider_config = self._registry.get_provider_config(profile.backend)
        configured_base_url = provider_config.get("base_url", "")
        if not isinstance(configured_base_url, str):
            configured_base_url = ""
        base_url = profile.api_base or configured_base_url or default_base_url
        configured_key_env = provider_config.get("api_key_env", "")
        if not isinstance(configured_key_env, str):
            configured_key_env = ""
        key_env = profile.api_key_env or configured_key_env
        api_key = os.environ.get(key_env, "") if key_env else ""
        if not api_key and profile.backend.casefold() == "ollama":
            api_key = os.environ.get("OLLAMA_API_KEY", "") or "ollama"
        return str(base_url).rstrip("/"), api_key

    @staticmethod
    def _request_json(request: urllib.request.Request) -> dict[str, JsonValue]:
        opener = _urlopen_provider or _safe_urlopen
        with opener(request, timeout=2) as response:
            payload = RESPONSE_ADAPTER.validate_json(response.read())
        return payload

    @staticmethod
    def _capability(
        profile: ModelProfile,
        native_tool_calling: NativeToolCalling,
        runtime_status: RuntimeStatus,
        source: str,
        detail: str,
        reported_capabilities: list[str] | None = None,
        reported_model_count: int = 0,
        reported_model_ids: list[str] | None = None,
    ) -> ProviderCapability:
        capabilities = reported_capabilities or []
        return {
            "model": profile.name,
            "provider": profile.backend,
            "is_local": profile.is_local,
            "native_tool_calling": native_tool_calling,
            "runtime_status": runtime_status,
            "source": source,
            "detail": detail,
            "reported_capabilities": capabilities,
            "reported_model_count": reported_model_count,
            "reported_model_ids": reported_model_ids or [],
            "active_turn_steering": "queued_replay",
            "long_context": derive_long_context_capability(profile.backend, runtime_status, capabilities),
        }

    def _unavailable(self, profile: ModelProfile, source: str, exc: BaseException) -> ProviderCapability:
        return self._capability(
            profile,
            "unknown",
            "unavailable",
            source,
            f"{type(exc).__name__}: {exc}",
        )

    def _probe_unsloth(self, profile: ModelProfile) -> ProviderCapability:
        model_path = Path(profile.repo)
        has_adapter = (model_path / "adapter_config.json").is_file()
        if has_adapter or ((model_path / "config.json").is_file() and _has_transformers_weights(model_path)):
            return self._probe_local_transformers(
                profile,
                required_packages=("transformers", "torch", "peft") if has_adapter else ("transformers", "torch"),
                source="unsloth:local-adapter" if has_adapter else "unsloth:local-transformers",
                missing_detail=(
                    "Unsloth adapter를 직접 로드하려면 transformers, torch, peft가 필요합니다."
                    if has_adapter
                    else "Unsloth 모델을 직접 로드하려면 transformers와 torch가 필요합니다."
                ),
            )

        provider_config = self._registry.get_provider_config(profile.backend)
        try:
            api_base, api_key = resolve_unsloth_settings(profile, provider_config, allow_default_endpoint=False)
        except UnslothEndpointError as exc:
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                "unsloth:/v1/models",
                str(exc),
            )

        request = urllib.request.Request(f"{api_base}/models", headers=self._headers(api_key))
        try:
            payload = self._request_json(request)
            model_list = UnslothModelList.model_validate(payload)
        except (
            EgressPolicyError,
            HTTPError,
            URLError,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                "unsloth:/v1/models",
                f"{type(exc).__name__}: {exc}",
            )

        models = model_list.data
        loaded_ids = [entry.id for entry in models]
        identifiers = {profile.name, profile.repo}
        matched = next((entry for entry in models if entry.id in identifiers), None)
        if matched is None:
            detail = (
                "Unsloth server has no loaded models."
                if not loaded_ids
                else "Unsloth server reachable; configured model identifiers are not loaded."
            )
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                "unsloth:/v1/models",
                detail,
                reported_model_count=len(models),
                reported_model_ids=loaded_ids[:5],
            )

        capabilities = [item.casefold() for item in matched.capabilities]
        metadata: dict[str, JsonValue] = {
            "capabilities": list(matched.capabilities),
            "attention_type": matched.attention_type,
            "attention_mechanism": matched.attention_mechanism,
            "sparse_attention": matched.sparse_attention,
            "linear_attention": matched.linear_attention,
            "kv_cache_compression": matched.kv_cache_compression,
            "kv_cache_quantization": matched.kv_cache_quantization,
        }
        for capability_name in infer_long_context_capabilities(metadata):
            if capability_name not in capabilities:
                capabilities.append(capability_name)
        if matched.supports_tools is True and "tools" not in capabilities:
            capabilities.append("tools")
        capability = self._capability(
            profile,
            "unsupported",
            "available",
            "unsloth:/v1/models",
            "Unsloth process reachable; server-side tools are disabled by Ssak-Ai policy.",
            capabilities,
            reported_model_count=len(models),
            reported_model_ids=loaded_ids[:5],
        )
        if matched.backend is not None:
            capability["reported_backend"] = matched.backend
        if matched.device is not None:
            capability["reported_device"] = matched.device
        if matched.quantization is not None:
            capability["reported_quantization"] = matched.quantization
        if matched.context_length is not None and matched.context_length > 0:
            capability["reported_context_length"] = matched.context_length
        return capability
