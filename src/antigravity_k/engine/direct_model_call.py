"""r30: one pre-send boundary for model requests that do not go through ModelManager.

Some learning/evaluation/QA modules talk to the local Ollama HTTP API directly. Every such request
must still be charged against the run's single LLM budget (process cap + cross-restart test ledger)
and audited *before* it is sent, and must respect the per-request time cap. This module does not
route, retry or substitute models — it only applies the shared boundary and returns the capped
timeout. A budget block raises :class:`LLMCallBudgetExhausted` and nothing is sent.
"""

from __future__ import annotations

from antigravity_k.engine.llm_call_budget import charge

#: Existing per-request cap for real LLM sends (seconds).
LLM_REQUEST_TIMEOUT_CAP_S = 120.0


def guard_direct_model_call(model: str, purpose: str, model_input: str, *, timeout: float) -> float:
    """Charge one attempt for a direct (non-ModelManager) send and return the capped timeout."""
    _ = charge(model or "unknown", f"direct:{purpose}", model_input, provider="ollama-direct")
    return min(float(timeout), LLM_REQUEST_TIMEOUT_CAP_S)
