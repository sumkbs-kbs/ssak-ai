"""Run-wide LLM request budget (resource governance).

``AGK_LLM_CALL_BUDGET`` (positive int) caps the number of real LLM provider requests this
server process may *attempt*. Every attempt (intent routing, agent analysis, answer
generation, retries, combo fallbacks) is charged *before* the request is sent, from one
shared, lock-protected counter, so parallel agents cannot each get their own limit.
Unset / empty / 0 => unlimited (legacy behaviour). When exhausted, :class:`LLMCallBudgetExhausted`
is raised before sending; the budget is never raised and no other model is substituted.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

BUDGET_ENV = "AGK_LLM_CALL_BUDGET"


class LLMCallBudgetExhausted(RuntimeError):
    """Raised before a request would exceed the configured LLM call budget (non-retryable)."""

    status = "budget_exhausted"

    def __init__(self, limit: int, model: str) -> None:
        super().__init__(f"budget_exhausted: LLM call budget {limit} reached; request to '{model}' not sent")
        self.limit = limit
        self.model = model


class LLMLedgerUnavailable(LLMCallBudgetExhausted):
    """r34: the cross-restart ledger is missing/corrupt; distinct from a reached limit (not sent)."""

    status = "ledger_unavailable"

    def __init__(self, model: str, detail: str) -> None:
        RuntimeError.__init__(
            self, f"ledger_unavailable: {detail}; request to '{model}' not sent (counter is never reset to 0)"
        )
        self.limit = 0
        self.model = model


class LLMLedgerLimitReached(LLMCallBudgetExhausted):
    """r34: the cross-restart ledger total was actually reached (not sent)."""

    def __init__(self, model: str, detail: str) -> None:
        RuntimeError.__init__(self, f"budget_exhausted: {detail}; request to '{model}' not sent")
        self.limit = 0
        self.model = model


_lock = threading.Lock()
_used = 0
_blocked = 0
#: r30: model-resolution failures happen before any send; counted separately from attempts.
_resolution_failed = 0


def configured_limit() -> int | None:
    raw = os.environ.get(BUDGET_ENV, "").strip()
    if not raw:
        return None
    value = int(raw)  # invalid configuration must fail loudly, not silently become unlimited
    if value < 0:
        raise ValueError(f"{BUDGET_ENV} must be >= 0")
    return value or None


_tls = threading.local()


def last_ledger_reservation() -> int | None:
    """Ledger reservation number of the most recent charge() on this thread (None when off)."""
    return cast_int_or_none(getattr(_tls, "ledger_n", None))


def cast_int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def settle(ledger_n: int | None, state: str) -> None:
    """r32: record the terminal lifecycle of one dispatched LLM reservation."""
    import antigravity_k.engine.call_ledger as call_ledger

    # Terminal marks carry only n + ts; the identifiers live on the matching "dispatched" mark
    # (thread-local meta could belong to a later nested call by the time a stream settles).
    call_ledger.mark("llm", ledger_n, state)


def charge(model: str, purpose: str = "generate", model_input: str = "", provider: str = "", endpoint: str = "") -> int:
    """Reserve one attempt before sending. Returns the attempt number."""
    global _used, _blocked
    from antigravity_k.engine.model_allowlist import check_send

    # r34: approval is checked first, so a refused model consumes no budget and no ledger slot.
    check_send(model, provider, endpoint)
    limit = configured_limit()
    import antigravity_k.engine.call_ledger as call_ledger

    # r32: the per-start budget is checked BEFORE the cross-restart ledger reservation, under one
    # lock, so a per-start refusal never consumes a ledger reservation (r31: 23 reserved / 22 sent).
    with _lock:
        if limit is not None and _used >= limit:
            _blocked += 1
            logger.error("[LLMBudget] budget_exhausted %s/%s blocked model=%s purpose=%s", _used, limit, model, purpose)
            raise LLMCallBudgetExhausted(limit, model)
        try:
            ledger_n = call_ledger.reserve("llm")
        except call_ledger.CallLedgerUnavailable as exc:
            _blocked += 1
            logger.error("[LLMBudget] ledger_unavailable model=%s purpose=%s: %s", model, purpose, exc)
            raise LLMLedgerUnavailable(model, str(exc)) from exc
        except call_ledger.CallLedgerError as exc:
            _blocked += 1
            logger.error("[LLMBudget] budget_exhausted (test ledger) model=%s purpose=%s", model, purpose)
            raise LLMLedgerLimitReached(model, str(exc)) from exc
        _used += 1
        n = _used
    _tls.ledger_n = ledger_n
    if ledger_n is not None:
        import uuid

        from antigravity_k.engine.task_execution_context import current_task_execution_context

        ctx = current_task_execution_context()
        request_id = uuid.uuid4().hex[:12]
        meta: dict[str, object] = {"request_id": request_id, "purpose": purpose, "model": model, "attempt": n}
        if ctx is not None:
            meta["task_id"] = ctx.task_id
        logger.warning(
            "[LLMBudget] test-ledger llm cumulative=%s request_id=%s task=%s purpose=%s",
            ledger_n,
            request_id,
            meta.get("task_id", "-"),
            purpose,
        )
        call_ledger.mark("llm", ledger_n, "dispatched", meta)
    # Audit line (WARNING so it survives the default log level): no prompt text is logged,
    # only its size and whether retrieved project context is part of the model input.
    logger.warning(
        "[LLMBudget] attempt %s/%s model=%s purpose=%s input_chars=%s has_relevant_code=%s",
        n,
        limit if limit is not None else "unlimited",
        model,
        purpose,
        len(model_input),
        "<relevant_code>" in model_input,
    )
    import antigravity_k.engine.llm_input_audit as llm_input_audit

    llm_input_audit.audit_provider_input(
        attempt=n, model=model, provider=provider, purpose=purpose, final_input=model_input
    )
    return n


def record_resolution_failure(target: str, reason: str) -> None:
    """Record a pre-send model-resolution failure (nothing was sent, no attempt was charged)."""
    global _resolution_failed
    with _lock:
        _resolution_failed += 1
        n = _resolution_failed
    logger.warning("[LLMBudget] resolution_failed %s target=%s reason=%s (not sent)", n, target, reason)


def snapshot() -> dict[str, object]:
    try:
        limit = configured_limit()
    except ValueError:
        return {
            "limit": None,
            "used": _used,
            "blocked": _blocked,
            "resolution_failed": _resolution_failed,
            "state": "invalid_config",
        }
    with _lock:
        return {
            "limit": limit,
            "used": _used,
            "blocked": _blocked,
            "resolution_failed": _resolution_failed,
            "state": "budget_exhausted" if limit is not None and _used >= limit else "ok",
        }


def reset_for_tests() -> None:
    global _used, _blocked, _resolution_failed
    with _lock:
        _used = 0
        _blocked = 0
        _resolution_failed = 0


def model_input_text(prompt: object, raw_messages: object) -> str:
    parts = [prompt if isinstance(prompt, str) else ""]
    if isinstance(raw_messages, list):
        for msg in raw_messages:
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return "\n".join(parts)
