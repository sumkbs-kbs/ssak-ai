from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Final, Literal, NotRequired, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from antigravity_k.engine.long_context_capabilities import LongContextCapability
from antigravity_k.engine.long_context_policy import LongContextExecutionPlan
from antigravity_k.engine.provider_adapters.unsloth_provider import ProviderConfigValue

NativeToolCalling = Literal["supported", "unsupported", "unknown"]
ActiveTurnSteering = Literal["queued_replay"]
RuntimeStatus = Literal["available", "unavailable", "not_required"]
ProviderBackend = Literal[
    "ollama",
    "lmstudio",
    "unsloth",
    "mlx",
    "transformers",
    "unknown",
]

LOCAL_METADATA_ADAPTER = TypeAdapter(dict[str, JsonValue])
MODEL_ENTRIES_ADAPTER = TypeAdapter(list[dict[str, JsonValue]])
RESPONSE_ADAPTER: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
PROVIDER_BACKENDS: Final[dict[str, ProviderBackend]] = {
    "ollama": "ollama",
    "lmstudio": "lmstudio",
    "lm_studio": "lmstudio",
    "llama.cpp": "lmstudio",
    "llamacpp": "lmstudio",
    "openai-compatible-local": "lmstudio",
    "vllm": "lmstudio",
    "tgi": "lmstudio",
    "koboldcpp": "lmstudio",
    "text-generation-webui": "lmstudio",
    "unsloth": "unsloth",
    "mlx": "mlx",
    "transformers": "transformers",
}


class ProviderCapability(TypedDict):
    model: str
    provider: str
    is_local: bool
    native_tool_calling: NativeToolCalling
    runtime_status: RuntimeStatus
    source: str
    detail: str
    reported_capabilities: list[str]
    reported_model_count: int
    reported_model_ids: NotRequired[list[str]]
    reported_backend: NotRequired[str]
    reported_device: NotRequired[str]
    reported_quantization: NotRequired[str]
    reported_context_length: NotRequired[int]
    long_context: NotRequired[LongContextCapability]
    long_context_plan: NotRequired[LongContextExecutionPlan]
    active_turn_steering: NotRequired[ActiveTurnSteering]


class ProviderConfigRegistry(Protocol):
    def get_provider_config(self, provider: str) -> Mapping[str, ProviderConfigValue]: ...


class _UnslothModelMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    id: str
    backend: str | None = None
    device: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    capabilities: tuple[str, ...] = ()
    supports_tools: bool | None = None
    attention_type: str | None = None
    attention_mechanism: str | None = None
    sparse_attention: bool | None = None
    linear_attention: bool | None = None
    kv_cache_compression: bool | None = None
    kv_cache_quantization: bool | None = None


class UnslothModelList(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    data: tuple[_UnslothModelMetadata, ...] = ()
