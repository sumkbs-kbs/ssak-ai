"""Deterministic token-budget compaction with immutable prompt-cache prefixes."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from antigravity_k.engine.context_budget_enforcer import enforce_context_budget

Message = dict[str, str]
TokenEstimator = Callable[[str], int]
SummaryBuilder = Callable[[list[Message]], str]


class PromptCachePrefixError(ValueError):
    """Raised when an immutable cache prefix cannot fit the target budget."""


def leading_prompt_cache_prefix(messages: list[Message]) -> int:
    """Return the contiguous system prefix eligible for stable provider prompt caching."""
    prefix_count = 0
    for message in messages:
        if message.get("role") != "system":
            break
        prefix_count += 1
    return prefix_count


def adaptive_compact(
    messages: list[Message],
    *,
    token_budget: int,
    task_type: str,
    prompt_cache_prefix: int,
    estimate_tokens: TokenEstimator,
    summarize: SummaryBuilder,
    importance_weights: Mapping[str, float],
    task_strategies: Mapping[str, Mapping[str, int]],
) -> list[Message]:
    """Compact only the mutable suffix while preserving cached prefix bytes and order."""
    _validate_prefix(messages, prompt_cache_prefix)
    if _total_tokens(messages, estimate_tokens) <= token_budget:
        return messages

    prefix = messages[:prompt_cache_prefix]
    mutable = messages[prompt_cache_prefix:]
    prefix_tokens = _total_tokens(prefix, estimate_tokens)
    if prefix_tokens >= token_budget:
        raise PromptCachePrefixError(
            f"prompt-cache prefix requires {prefix_tokens} tokens but budget is {token_budget}",
        )

    compacted = _compact_mutable(
        mutable,
        token_budget=token_budget - prefix_tokens,
        task_type=task_type,
        estimate_tokens=estimate_tokens,
        summarize=summarize,
        importance_weights=importance_weights,
        task_strategies=task_strategies,
    )
    return [*prefix, *compacted]


def _compact_mutable(
    messages: list[Message],
    *,
    token_budget: int,
    task_type: str,
    estimate_tokens: TokenEstimator,
    summarize: SummaryBuilder,
    importance_weights: Mapping[str, float],
    task_strategies: Mapping[str, Mapping[str, int]],
) -> list[Message]:
    if _total_tokens(messages, estimate_tokens) <= token_budget:
        return messages

    strategy = task_strategies.get(task_type, task_strategies["GENERAL"])
    keep_last_n = strategy["keep_last_n"]
    max_tool_chars = strategy["max_tool_chars"]
    system_messages = [message for message in messages if message.get("role") == "system"]
    other_messages = [message for message in messages if message.get("role") != "system"]

    if len(other_messages) <= keep_last_n:
        return enforce_context_budget(messages, token_budget, estimate_tokens)

    recent = other_messages[-keep_last_n:]
    old = other_messages[:-keep_last_n]
    scored = [
        (
            importance_weights.get(message.get("role", "user"), 0.5) + ((index + 1) / len(old) * 0.3),
            index,
            message,
        )
        for index, message in enumerate(old)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))

    remaining = token_budget - _total_tokens([*system_messages, *recent], estimate_tokens)
    kept: list[tuple[int, Message]] = []
    for _importance, original_index, original in scored:
        candidate = _compact_tool_result(original, max_tool_chars)
        candidate_tokens = estimate_tokens(candidate.get("content", ""))
        if candidate_tokens <= remaining:
            kept.append((original_index, candidate))
            remaining -= candidate_tokens

    kept.sort(key=lambda item: item[0])
    kept_indices = {index for index, _message in kept}
    dropped = [message for index, message in enumerate(old) if index not in kept_indices]
    result = list(system_messages)
    if dropped and (summary := summarize(dropped)):
        result.append({"role": "system", "content": summary})
    result.extend(message for _index, message in kept)
    result.extend(recent)
    return enforce_context_budget(result, token_budget, estimate_tokens)


def _compact_tool_result(message: Message, max_chars: int) -> Message:
    content = message.get("content", "")
    if message.get("role") != "tool" or len(content) <= max_chars:
        return message
    truncated = content[:max_chars]
    # 잘린 봉투 태그를 재-닫는다 — 열린 채 남은 [UNTRUSTED_TOOL_RESULT]는
    # 프롬프트 주입 경계를 약화시키고, 하류 압축기(tool_evidence_compactor)의
    # 닫는 태그 매칭을 영구히 망친다. 봉투 순서: [/UNTRUSTED] → </tool_response>.
    closers = []
    if truncated.count("[UNTRUSTED_TOOL_RESULT]") > truncated.count("[/UNTRUSTED_TOOL_RESULT]"):
        closers.append("[/UNTRUSTED_TOOL_RESULT]")
    if truncated.count("<tool_response>") > truncated.count("</tool_response>"):
        closers.append("</tool_response>")
    return {
        **message,
        "content": truncated + "\n...(결과 일부 생략)" + "".join(closers),
    }


def _validate_prefix(messages: list[Message], prefix_count: int) -> None:
    if prefix_count < 0 or prefix_count > len(messages):
        raise ValueError(f"prompt_cache_prefix must be between 0 and {len(messages)}")


def _total_tokens(messages: list[Message], estimate_tokens: TokenEstimator) -> int:
    return sum(estimate_tokens(message.get("content", "")) for message in messages)
