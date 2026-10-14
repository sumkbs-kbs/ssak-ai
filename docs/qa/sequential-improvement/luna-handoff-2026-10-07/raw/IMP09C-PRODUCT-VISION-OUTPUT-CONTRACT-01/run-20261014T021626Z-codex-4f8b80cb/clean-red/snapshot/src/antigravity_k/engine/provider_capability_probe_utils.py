from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import JsonValue, ValidationError

from antigravity_k.engine.long_context_metadata import infer_long_context_capabilities

from .provider_capability_models import LOCAL_METADATA_ADAPTER, ProviderCapability, ProviderConfigRegistry

if TYPE_CHECKING:
    from .model_registry import ModelProfile


class ProviderProbeUtilities:
    def __init__(self, registry: ProviderConfigRegistry) -> None:
        self._registry: ProviderConfigRegistry = registry

    def _probe_local_transformers(
        self,
        profile: ModelProfile,
        *,
        required_packages: tuple[str, ...],
        source: str,
        missing_detail: str,
    ) -> ProviderCapability:
        _ = (profile, required_packages, source, missing_detail)
        raise NotImplementedError

    @staticmethod
    def _native_base(base_url: str) -> str:
        if base_url.endswith("/v1"):
            return base_url[:-3]
        return base_url

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _reported_tool_capabilities(entry: Mapping[str, JsonValue] | None) -> list[str]:
        if entry is None:
            return []
        raw_capabilities = entry.get("capabilities", [])
        capabilities = (
            [item.casefold() for item in raw_capabilities if isinstance(item, str)]
            if isinstance(raw_capabilities, list)
            else []
        )
        supports_tools = entry.get("supports_tools")
        if supports_tools is True:
            capabilities.append("tools")
        return capabilities

    @staticmethod
    def _local_reported_capabilities(model_path: Path) -> list[str]:
        capabilities: set[str] = set()
        for filename in ("config.json", "model_config.json", "adapter_config.json"):
            config_path = model_path / filename
            if not config_path.is_file():
                continue
            try:
                payload = LOCAL_METADATA_ADAPTER.validate_json(config_path.read_bytes())
            except (OSError, UnicodeError, ValidationError):
                continue
            capabilities.update(infer_long_context_capabilities(payload))
        return sorted(capabilities)
