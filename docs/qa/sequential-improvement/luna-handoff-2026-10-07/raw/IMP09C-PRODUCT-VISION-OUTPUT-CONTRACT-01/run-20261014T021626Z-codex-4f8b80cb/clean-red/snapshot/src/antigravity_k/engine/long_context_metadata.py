from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import JsonValue

_CAPABILITY_ALIASES: Final[dict[str, str]] = {
    "sparse_attention": "sparse_attention",
    "dynamic_sparse_attention": "sparse_attention",
    "flashinfer_sparse": "sparse_attention",
    "linear_attention": "linear_attention",
    "gated_linear_attention": "linear_attention",
    "recurrent_attention": "linear_attention",
    "kv_cache_compression": "kv_cache_compression",
    "kv_cache_quantization": "kv_cache_compression",
}
_BOOLEAN_KEYS: Final[dict[str, str]] = {
    "sparse_attention": "sparse_attention",
    "use_sparse_attention": "sparse_attention",
    "supports_sparse_attention": "sparse_attention",
    "linear_attention": "linear_attention",
    "use_linear_attention": "linear_attention",
    "supports_linear_attention": "linear_attention",
    "kv_cache_compression": "kv_cache_compression",
    "use_kv_cache_compression": "kv_cache_compression",
    "supports_kv_cache_compression": "kv_cache_compression",
    "kv_cache_quantization": "kv_cache_compression",
}


def infer_long_context_capabilities(metadata: Mapping[str, JsonValue]) -> tuple[str, ...]:
    found: set[str] = set()
    _collect(metadata, found)
    return tuple(sorted(found))


def _collect(metadata: Mapping[str, JsonValue], found: set[str]) -> None:
    raw_capabilities = metadata.get("capabilities")
    if isinstance(raw_capabilities, list):
        for item in raw_capabilities:
            if isinstance(item, str):
                capability = _CAPABILITY_ALIASES.get(_normalize(item))
                if capability is not None:
                    found.add(capability)

    for raw_key, value in metadata.items():
        key = _normalize(raw_key)
        if value is True:
            capability = _BOOLEAN_KEYS.get(key)
            if capability is not None:
                found.add(capability)
        if isinstance(value, str):
            _collect_attention_type(key, value, found)

    nested = metadata.get("attention")
    if isinstance(nested, Mapping):
        _collect(nested, found)


def _collect_attention_type(key: str, value: str, found: set[str]) -> None:
    if key not in {"attention_type", "attention_mechanism"}:
        return
    match _normalize(value):
        case "linear" | "gated_linear" | "recurrent" | "recurrent_attention":
            found.add("linear_attention")
        case "sparse" | "dynamic_sparse":
            found.add("sparse_attention")
        case _:
            return


def _normalize(value: str) -> str:
    return value.casefold().replace("-", "_").replace(" ", "_")
