from __future__ import annotations

import importlib.util
import json
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from urllib.error import HTTPError, URLError

from pydantic import ValidationError
from typing_extensions import override

from antigravity_k.tools.egress_policy import EgressPolicyError

from .provider_capability_models import (
    MODEL_ENTRIES_ADAPTER,
    PROVIDER_BACKENDS,
    NativeToolCalling,
    ProviderCapability,
    ProviderConfigRegistry,
    RuntimeStatus,
)

if TYPE_CHECKING:
    from .model_registry import ModelProfile


def _has_transformers_weights(model_path: Path) -> bool:
    return any(model_path.glob("*.safetensors"))


from .provider_capability_probe_runtime import ProviderProbeRuntime


class LocalProviderCapabilityProbe(ProviderProbeRuntime):
    _CACHE_TTL_SECONDS: ClassVar[float] = 60.0

    def __init__(self, registry: ProviderConfigRegistry) -> None:
        super().__init__(registry)
        self._cache: dict[str, ProviderCapability] = {}
        self._observed_at: dict[str, float] = {}

    def observe(self, profile: ModelProfile, *, refresh: bool = False) -> ProviderCapability:
        now = time.monotonic()
        cached = self._cache.get(profile.name)
        observed_at = self._observed_at.get(profile.name, 0.0)
        if cached is not None and not refresh and now - observed_at < self._CACHE_TTL_SECONDS:
            return cached

        provider = PROVIDER_BACKENDS.get(profile.backend.casefold(), "unknown")
        capability = self._static_unknown(profile)
        match provider:  # noqa: E501  # noqa: MATCH_OK - provider is normalized from runtime configuration
            case "ollama":
                capability = self._probe_ollama(profile)
            case "lmstudio":
                capability = self._probe_lmstudio(profile)
            case "unsloth":
                capability = self._probe_unsloth(profile)
            case "mlx":
                capability = self._probe_mlx(profile)
            case "transformers":
                capability = self._probe_transformers(profile)
            case "unknown":
                capability = self._static_unknown(profile)

        self._cache[profile.name] = capability
        self._observed_at[profile.name] = now
        return capability

    def cached(self, model_name: str) -> ProviderCapability | None:
        """Return already-observed metadata without probing the provider."""
        return self._cache.get(model_name)

    def clear(self) -> None:
        self._cache.clear()
        self._observed_at.clear()

    def _probe_ollama(self, profile: ModelProfile) -> ProviderCapability:
        base_url, api_key = self._endpoint(profile, "http://localhost:11434")
        request = urllib.request.Request(
            f"{self._native_base(base_url)}/api/show",
            data=json.dumps({"name": profile.name}).encode("utf-8"),
            headers=self._headers(api_key),
        )
        try:
            payload = self._request_json(request)
        except (
            EgressPolicyError,
            HTTPError,
            URLError,
            OSError,
            TimeoutError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            return self._unavailable(profile, "ollama:/api/show", exc)

        raw_capabilities = payload.get("capabilities", [])
        capabilities = (
            [item.casefold() for item in raw_capabilities if isinstance(item, str)]
            if isinstance(raw_capabilities, list)
            else []
        )
        native_tools: NativeToolCalling = "unknown"
        if capabilities:
            native_tools = "supported" if "tools" in capabilities else "unsupported"
        return self._capability(
            profile,
            native_tools,
            "available",
            "ollama:/api/show",
            "Ollama model metadata reported its capability list.",
            capabilities,
        )

    def _probe_lmstudio(self, profile: ModelProfile) -> ProviderCapability:
        base_url, api_key = self._endpoint(profile, "http://127.0.0.1:1234/v1")
        api_base = base_url.rstrip("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"
        request = urllib.request.Request(f"{api_base}/models", headers=self._headers(api_key))
        try:
            payload = self._request_json(request)
        except (
            EgressPolicyError,
            HTTPError,
            URLError,
            OSError,
            TimeoutError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            return self._unavailable(profile, "lmstudio:/v1/models", exc)

        entries = payload.get("data", [])
        if isinstance(entries, list):
            try:
                models = MODEL_ENTRIES_ADAPTER.validate_python(entries)
            except ValidationError:
                models = []
        else:
            models = []
        loaded_ids: list[str] = []
        for entry in models:
            model_id = entry.get("id")
            if isinstance(model_id, str):
                loaded_ids.append(model_id)
        identifiers = {profile.name, profile.repo}
        matched = next(
            (entry for entry in models if isinstance(entry.get("id"), str) and entry["id"] in identifiers),
            None,
        )
        if matched is None:
            detail = (
                "LM Studio server has no loaded models."
                if not loaded_ids
                else "LM Studio server reachable; configured model identifiers are not loaded."
            )
            return self._capability(
                profile,
                "unknown",
                "unavailable",
                "lmstudio:/v1/models",
                detail,
                [],
                reported_model_count=len(models),
                reported_model_ids=loaded_ids[:5],
            )
        capabilities = self._reported_tool_capabilities(matched)
        native_tools: NativeToolCalling = "unknown"
        if capabilities:
            native_tools = "supported" if "tools" in capabilities else "unsupported"
        return self._capability(
            profile,
            native_tools,
            "available",
            "lmstudio:/v1/models",
            "LM Studio model discovery does not guarantee tool calling when it omits capability metadata.",
            capabilities,
            reported_model_count=len(models),
            reported_model_ids=loaded_ids[:5],
        )

    def _probe_mlx(self, profile: ModelProfile) -> ProviderCapability:
        installed = importlib.util.find_spec("mlx_lm") is not None
        runtime_status: RuntimeStatus = "available" if installed else "unavailable"
        detail = (
            "The direct MLX provider does not pass a native tool schema to mlx_lm."
            if installed
            else "mlx_lm is not installed for the direct MLX provider."
        )
        return self._capability(
            profile,
            "unsupported",
            runtime_status,
            "mlx_lm:direct",
            detail,
        )

    def _probe_transformers(self, profile: ModelProfile) -> ProviderCapability:
        return self._probe_local_transformers(
            profile,
            required_packages=("transformers", "torch"),
            source="transformers:direct",
            missing_detail="Transformers 모델을 직접 로드하려면 transformers와 torch가 필요합니다.",
        )

    @override
    def _probe_local_transformers(
        self,
        profile: ModelProfile,
        *,
        required_packages: tuple[str, ...],
        source: str,
        missing_detail: str,
    ) -> ProviderCapability:
        model_path = Path(profile.repo)
        if not model_path.is_dir():
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                source,
                f"로컬 모델 디렉터리가 없습니다: {profile.repo}",
            )

        missing = [package for package in required_packages if importlib.util.find_spec(package) is None]
        if missing:
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                source,
                f"{missing_detail} 누락: {', '.join(missing)}",
            )

        has_config = (model_path / "config.json").is_file()
        has_weights = _has_transformers_weights(model_path)
        if not has_config or not has_weights:
            return self._capability(
                profile,
                "unsupported",
                "unavailable",
                source,
                "로컬 모델에 config.json 또는 Transformers 가중치 파일이 없습니다.",
            )

        capabilities = self._local_reported_capabilities(model_path)
        return self._capability(
            profile,
            "unsupported",
            "available",
            source,
            "선택 시 별도 서버 없이 Transformers 런타임에서 직접 로드합니다.",
            capabilities,
        )
