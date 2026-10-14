from collections.abc import Sequence
from typing import Literal, TypedDict

LongContextSupport = Literal["supported", "unsupported", "unknown"]
LongContextStrategy = Literal["native", "retrieval_fallback", "unavailable"]


class LongContextCapability(TypedDict):
    strategy: LongContextStrategy
    native_sparse_attention: LongContextSupport
    native_linear_attention: LongContextSupport
    kv_cache_compression: LongContextSupport


def derive_long_context_capability(
    provider: str,
    runtime_status: str,
    reported_capabilities: Sequence[str],
) -> LongContextCapability:
    if runtime_status == "unavailable":
        return {
            "strategy": "unavailable",
            "native_sparse_attention": "unsupported",
            "native_linear_attention": "unsupported",
            "kv_cache_compression": "unsupported",
        }

    capabilities = {item.casefold() for item in reported_capabilities}
    sparse = _support_for(capabilities, ("sparse_attention", "dynamic_sparse_attention", "flashinfer_sparse"))
    linear = _support_for(capabilities, ("linear_attention", "gated_linear_attention", "recurrent_attention"))
    kv_cache = _support_for(capabilities, ("kv_cache_compression", "kv_cache_quantization", "paged_attention"))
    native = sparse == "supported" or linear == "supported"
    strategy: LongContextStrategy = "native" if native else "retrieval_fallback"
    if provider.casefold() in {"ollama", "mlx", "transformers", "unsloth"} and not native:
        strategy = "retrieval_fallback"
    return {
        "strategy": strategy,
        "native_sparse_attention": sparse,
        "native_linear_attention": linear,
        "kv_cache_compression": kv_cache,
    }


def _support_for(capabilities: set[str], names: Sequence[str]) -> LongContextSupport:
    return "supported" if capabilities.intersection(names) else "unknown"
