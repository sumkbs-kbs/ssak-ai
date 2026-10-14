from __future__ import annotations

from typing import Literal, Protocol, TypedDict, runtime_checkable

from antigravity_k.engine.context_budget import ContextBudget
from antigravity_k.engine.long_context_capabilities import LongContextCapability, LongContextStrategy

LongContextRetrievalMode = Literal["native", "long_context"]
LongContextCacheMode = Literal["backend_managed", "bounded_context", "unavailable"]


class LongContextExecutionPlan(TypedDict):
    strategy: LongContextStrategy
    retrieval_mode: LongContextRetrievalMode
    native_attention_enabled: bool
    kv_cache_mode: LongContextCacheMode
    kv_cache_compression_enabled: bool
    context_token_limit: int
    candidate_pool: int
    rationale: str


@runtime_checkable
class LongContextPlanner(Protocol):
    def long_context_plan(
        self,
        name: str,
        *,
        refresh: bool = False,
    ) -> LongContextExecutionPlan | None: ...


def build_long_context_plan(
    capability: LongContextCapability | None,
    budget: ContextBudget,
) -> LongContextExecutionPlan:
    strategy: LongContextStrategy = "retrieval_fallback" if capability is None else capability["strategy"]
    match strategy:
        case "native":
            return {
                "strategy": strategy,
                "retrieval_mode": "native",
                "native_attention_enabled": True,
                "kv_cache_mode": "backend_managed",
                "kv_cache_compression_enabled": capability["kv_cache_compression"] == "supported"
                if capability is not None
                else False,
                "context_token_limit": budget.token_limit,
                "candidate_pool": 0,
                "rationale": "native_capability_verified",
            }
        case "retrieval_fallback":
            return {
                "strategy": strategy,
                "retrieval_mode": "long_context",
                "native_attention_enabled": False,
                "kv_cache_mode": "bounded_context",
                "kv_cache_compression_enabled": False,
                "context_token_limit": max(1_024, int(budget.token_limit * 0.8)),
                "candidate_pool": max(32, min(128, budget.token_limit // 128)),
                "rationale": "bounded_retrieval_fallback",
            }
        case "unavailable":
            return {
                "strategy": strategy,
                "retrieval_mode": "long_context",
                "native_attention_enabled": False,
                "kv_cache_mode": "unavailable",
                "kv_cache_compression_enabled": False,
                "context_token_limit": 0,
                "candidate_pool": 0,
                "rationale": "runtime_unavailable",
            }
