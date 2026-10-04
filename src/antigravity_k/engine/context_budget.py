from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from antigravity_k.engine.model_memory_calibration import ModelMemoryBudget, load_model_memory_budget

DEFAULT_CONTEXT_TOKEN_LIMIT: Final = 8_000
MAX_CONTEXT_TOKEN_LIMIT: Final = 32_768
MAX_TRAJECTORY_MESSAGES: Final = 128
LEGACY_TRAJECTORY_MAX_CHARS: Final = 80_000
RESPONSE_RESERVE_TOKENS: Final = 4_096


@dataclass(frozen=True, slots=True)
class ContextBudget:
    token_limit: int
    trajectory_max_messages: int
    trajectory_max_chars: int
    kv_cache_byte_limit: int | None = None


def context_budget_for_model(config: Mapping[str, JsonValue], model_name: str) -> ContextBudget:
    context_length = _model_context_length(config, model_name)
    memory_budget = _model_memory_budget(config, model_name)
    configured_limit = _configured_token_limit(config)
    if context_length is None and memory_budget is None:
        return _budget_from_token_limit(DEFAULT_CONTEXT_TOKEN_LIMIT)

    limits = [MAX_CONTEXT_TOKEN_LIMIT]
    if context_length is not None:
        limits.append(_input_limit_for_context(context_length))
    if configured_limit is not None:
        limits.append(configured_limit)
    if memory_budget is not None:
        limits.append(memory_budget.context_token_limit)
    return _budget_from_token_limit(
        min(limits),
        None if memory_budget is None else memory_budget.kv_cache_byte_limit,
    )


def context_budget_for_context_length(
    context_length: JsonValue,
    configured_token_limit: JsonValue = None,
) -> ContextBudget:
    resolved_context_length = _positive_int(context_length)
    if resolved_context_length is None:
        return _budget_from_token_limit(DEFAULT_CONTEXT_TOKEN_LIMIT)

    model_limit = _input_limit_for_context(resolved_context_length)
    configured_limit = _positive_int(configured_token_limit)
    token_limit = min(model_limit, configured_limit) if configured_limit is not None else model_limit
    return _budget_from_token_limit(token_limit)


def _model_profile(config: Mapping[str, JsonValue], model_name: str) -> Mapping[str, JsonValue] | None:
    models = config.get("models")
    if not isinstance(models, dict):
        return None
    alias: Mapping[str, JsonValue] | None = None
    for profiles in models.values():
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            if profile.get("name") == model_name:
                return profile
            if alias is None and profile.get("repo") == model_name:
                alias = profile
    return alias


def _model_context_length(config: Mapping[str, JsonValue], model_name: str) -> int | None:
    profile = _model_profile(config, model_name)
    return None if profile is None else _positive_int(profile.get("context_length"))


def _configured_token_limit(config: Mapping[str, JsonValue]) -> int | None:
    router = config.get("router")
    if not isinstance(router, dict):
        return None
    return _positive_int(router.get("context_token_limit"))


def _model_memory_budget(config: Mapping[str, JsonValue], model_name: str) -> ModelMemoryBudget | None:
    router = config.get("router")
    if not isinstance(router, dict):
        return None
    raw_paths = router.get("memory_calibration_artifact_paths")
    if not isinstance(raw_paths, list):
        return None
    paths = tuple(Path(raw_path) for raw_path in raw_paths if isinstance(raw_path, str))
    profile = _model_profile(config, model_name)
    identifiers = {model_name}
    if profile is not None:
        identifiers.update(value for key in ("name", "repo") if isinstance(value := profile.get(key), str))
    budgets = tuple(
        budget
        for identifier in sorted(identifiers)
        if (budget := load_model_memory_budget(paths, identifier)) is not None
    )
    if not budgets:
        return None
    return ModelMemoryBudget(
        model=model_name,
        context_token_limit=min(budget.context_token_limit for budget in budgets),
        kv_cache_byte_limit=min(budget.kv_cache_byte_limit for budget in budgets),
        source_sha256=min(budget.source_sha256 for budget in budgets),
    )


def _input_limit_for_context(context_length: int) -> int:
    response_reserve = min(RESPONSE_RESERVE_TOKENS, max(1_024, context_length // 4))
    return min(MAX_CONTEXT_TOKEN_LIMIT, max(1_024, context_length - response_reserve))


def _budget_from_token_limit(token_limit: int, kv_cache_byte_limit: int | None = None) -> ContextBudget:
    return ContextBudget(
        token_limit=token_limit,
        trajectory_max_messages=max(40, min(MAX_TRAJECTORY_MESSAGES, token_limit // 256)),
        trajectory_max_chars=max(LEGACY_TRAJECTORY_MAX_CHARS, token_limit * 4),
        kv_cache_byte_limit=kv_cache_byte_limit,
    )


def _positive_int(value: JsonValue) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


# ─── CTX-02: final serialized prompt ledger ─────────────────────────────


@dataclass(frozen=True, slots=True)
class HardTokenLimit:
    """Declared / empirical / operator limits and their effective minimum.

    ``effective`` is the hard ceiling for (final_input + output_reserve).
    ``input_budget`` is ``effective - output_reserve`` (tokens available for
    the serialized prompt body before the model call).
    """

    declared: int | None
    empirical: int | None
    operator: int | None
    output_reserve: int
    effective: int
    input_budget: int


@dataclass(frozen=True, slots=True)
class PromptComponentLedger:
    """Token counts for every component of the final serialized prompt."""

    system: int
    tools: int
    skills: int
    memory: int
    artifacts: int
    messages: int
    output_reserve: int

    @property
    def input_total(self) -> int:
        return self.system + self.tools + self.skills + self.memory + self.artifacts + self.messages

    @property
    def total_with_reserve(self) -> int:
        return self.input_total + self.output_reserve

    def as_dict(self) -> dict[str, int]:
        return {
            "system": self.system,
            "tools": self.tools,
            "skills": self.skills,
            "memory": self.memory,
            "artifacts": self.artifacts,
            "messages": self.messages,
            "output_reserve": self.output_reserve,
            "input_total": self.input_total,
            "total_with_reserve": self.total_with_reserve,
        }


class PromptBudgetExceededError(ValueError):
    """Final serialized prompt still exceeds the hard input budget."""

    def __init__(self, message: str, *, ledger: PromptComponentLedger, hard_limit: HardTokenLimit) -> None:
        super().__init__(message)
        self.ledger = ledger
        self.hard_limit = hard_limit


class OversizedPromptComponentError(ValueError):
    """A single prompt component cannot fit even after bounded compaction."""

    def __init__(self, component: str, tokens: int, budget: int) -> None:
        super().__init__(
            f"oversized prompt component {component!r}: {tokens} tokens > remaining budget {budget}",
        )
        self.component = component
        self.tokens = tokens
        self.budget = budget


class PromptBudgetEnforcementError(RuntimeError):
    """Final prompt budget gate could not be enforced; provider invoke must halt.

    Fail-closed: import/config/resolve/estimate failures must not fall through to
    the provider with an unchecked (possibly over-limit) serialized prompt.
    """

    def __init__(self, message: str, *, prompt_tokens: int | None = None) -> None:
        super().__init__(message)
        self.prompt_tokens = prompt_tokens


def output_reserve_tokens(context_length: int | None = None) -> int:
    """Conservative completion reserve used in the final hard-limit check."""
    if context_length is None or context_length <= 0:
        return RESPONSE_RESERVE_TOKENS
    return min(RESPONSE_RESERVE_TOKENS, max(1_024, context_length // 4))


def resolve_hard_token_limit(
    config: Mapping[str, JsonValue],
    model_name: str,
) -> HardTokenLimit:
    """Resolve the hard ceiling as min(declared, empirical, operator).

    ``input_budget`` is the maximum tokens allowed in the final serialized
    prompt body (system/tools/skills/memory/artifacts/messages). Callers must
    also keep ``output_reserve`` outside that body so
    ``final_input + output_reserve`` never exceeds the raw window when a full
    ``context_length`` is known.
    """
    declared = _model_context_length(config, model_name)
    memory = _model_memory_budget(config, model_name)
    empirical = None if memory is None else memory.context_token_limit
    operator = _configured_token_limit(config)
    reserve = output_reserve_tokens(declared)

    # MAX_CONTEXT_TOKEN_LIMIT also caps the provider window. Completion reserve
    # must fit inside that cap; empirical/operator ceilings still bind input.
    candidates: list[int] = [MAX_CONTEXT_TOKEN_LIMIT - reserve]
    if declared is not None:
        candidates.append(_input_limit_for_context(declared))
    if empirical is not None:
        candidates.append(empirical)
    if operator is not None:
        candidates.append(operator)
    if declared is None and empirical is None and operator is None:
        candidates.append(DEFAULT_CONTEXT_TOKEN_LIMIT)

    input_budget = min(candidates)
    # Effective hard check for (input + reserve): prefer raw declared window,
    # else input_budget + reserve.
    if declared is not None:
        effective = min(declared, input_budget + reserve)
    else:
        effective = input_budget + reserve
    if operator is not None:
        # Operator limit binds the input body; (input + reserve) must still
        # stay within declared when known.
        effective = min(effective, operator + reserve if declared is None else declared)
        effective = min(effective, input_budget + reserve)

    return HardTokenLimit(
        declared=declared,
        empirical=empirical,
        operator=operator,
        output_reserve=reserve,
        effective=effective,
        input_budget=input_budget,
    )


def build_prompt_component_ledger(
    *,
    system: str = "",
    tools: str = "",
    skills: str = "",
    memory: str = "",
    artifacts: str = "",
    messages: list[dict[str, str]] | None = None,
    serialized_messages: str = "",
    output_reserve: int = RESPONSE_RESERVE_TOKENS,
    estimate_tokens: Callable[[str], int] | None = None,
) -> PromptComponentLedger:
    """Count every final-prompt component before the provider invoke."""
    from antigravity_k.engine.tokenizer import TokenEstimator

    estimate = estimate_tokens or TokenEstimator.estimate_text
    if serialized_messages:
        message_tokens = estimate(serialized_messages)
    else:
        message_tokens = sum(estimate(message.get("content", "")) for message in (messages or []))
    return PromptComponentLedger(
        system=estimate(system),
        tools=estimate(tools),
        skills=estimate(skills),
        memory=estimate(memory),
        artifacts=estimate(artifacts),
        messages=message_tokens,
        output_reserve=max(0, int(output_reserve)),
    )


def prompt_selection_digest(
    *,
    system: str = "",
    tools: str = "",
    skills: str = "",
    memory: str = "",
    artifacts: str = "",
    messages: list[dict[str, str]] | None = None,
    strategy: str = "final_prompt_v1",
) -> str:
    """Deterministic digest of the selected/summarized prompt components."""
    import hashlib
    import json

    payload = {
        "strategy": strategy,
        "system": system,
        "tools": tools,
        "skills": skills,
        "memory": memory,
        "artifacts": artifacts,
        "messages": [
            {"role": message.get("role", ""), "content": message.get("content", "")} for message in (messages or [])
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def message_budget_for_aux(
    hard_limit: HardTokenLimit,
    *,
    system: str = "",
    tools: str = "",
    skills: str = "",
    memory: str = "",
    artifacts: str = "",
    estimate_tokens: Callable[[str], int] | None = None,
) -> int:
    """Tokens left for conversation messages after aux components + reserve."""
    from antigravity_k.engine.tokenizer import TokenEstimator

    estimate = estimate_tokens or TokenEstimator.estimate_text
    aux = estimate(system) + estimate(tools) + estimate(skills) + estimate(memory) + estimate(artifacts)
    return max(1, hard_limit.input_budget - aux)
