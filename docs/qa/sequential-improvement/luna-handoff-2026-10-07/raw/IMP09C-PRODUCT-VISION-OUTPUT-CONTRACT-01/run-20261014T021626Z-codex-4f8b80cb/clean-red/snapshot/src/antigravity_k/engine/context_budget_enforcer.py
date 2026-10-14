from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

Message = dict[str, str]
TokenEstimator = Callable[[str], int]

_COMPACTION_MARKER: Final = "\n...[context compacted]...\n"
_MIN_CONTENT_TOKENS: Final = 12
# 도구 호출 블록 — 가운데 자르면 깨진 JSON이 히스토리로 재주입되어
# 파서를 오염시킨다. 압축 시 블록 단위로만 제거한다.
_TOOL_CALL_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<(tool_call|action_call)>.*?</\1>",
    re.DOTALL,
)


def enforce_context_budget(
    messages: list[Message],
    token_budget: int,
    estimate_tokens: TokenEstimator,
    *,
    preserve_user_and_system: bool = False,
) -> list[Message]:
    fitted = [dict(message) for message in messages]
    total = _total_tokens(fitted, estimate_tokens)
    if total <= token_budget:
        return messages

    while total > token_budget:
        index = _next_trim_index(fitted, estimate_tokens, preserve_user_and_system=preserve_user_and_system)
        if index is None:
            break
        content = fitted[index].get("content", "")
        current = estimate_tokens(content)
        target = max(_MIN_CONTENT_TOKENS, current - (total - token_budget))
        compacted = compact_text_to_budget(content, target, estimate_tokens)
        if estimate_tokens(compacted) >= current:
            compacted = compact_text_to_budget(content, current - 1, estimate_tokens)
        fitted[index]["content"] = compacted
        total = _total_tokens(fitted, estimate_tokens)

    while total > token_budget and len(fitted) > 1:
        drop_index = _next_drop_index(fitted, preserve_user_and_system=preserve_user_and_system)
        if drop_index is None:
            break
        pair = _paired_message_index(fitted, drop_index)
        del fitted[drop_index]
        # 페어링 인식 드롭 — assistant의 <tool_call>과 그 결과는 함께
        # 사라져야 한다. 한쪽만 남으면 고아 호출/고아 결과가 히스토리로
        # 재주입되어 모델과 파서를 오염시킨다.
        if pair is not None and pair > drop_index:
            pair -= 1
        if (
            pair is not None
            and len(fitted) > 1
            and not (
                preserve_user_and_system
                and (pair == _latest_user_index(fitted) or fitted[pair].get("role") == "system")
            )
        ):
            del fitted[pair]
        total = _total_tokens(fitted, estimate_tokens)

    if total > token_budget and fitted and not preserve_user_and_system:
        content = fitted[0].get("content", "")
        target = max(1, estimate_tokens(content) - (total - token_budget))
        fitted[0]["content"] = compact_text_to_budget(content, target, estimate_tokens)
    return fitted


def compact_text_to_budget(
    text: str,
    token_budget: int,
    estimate_tokens: TokenEstimator,
) -> str:
    if estimate_tokens(text) <= token_budget:
        return text

    # 도구 호출 블록을 먼저 통째로 제거한다 — 이진 탐색 head/tail 절단은
    # <tool_call> JSON 중간을 자를 수 있고, 깨진 호출 마크업은 다음
    # 스텝에서 모델/파서를 오염시킨다.
    while True:
        match = _TOOL_CALL_BLOCK_RE.search(text)
        if match is None:
            break
        text = text[: match.start()] + text[match.end() :]
        if estimate_tokens(text) <= token_budget:
            return text

    best = ""
    lower = 0
    upper = len(text)
    while lower <= upper:
        retained = (lower + upper) // 2
        candidate = _head_tail(text, retained)
        if estimate_tokens(candidate) <= token_budget:
            best = candidate
            lower = retained + 1
        else:
            upper = retained - 1
    return best


def _head_tail(text: str, retained: int) -> str:
    if retained <= 0:
        return ""
    if retained >= len(text):
        return text
    head_chars = (retained + 1) // 2
    tail_chars = retained // 2
    tail = text[-tail_chars:] if tail_chars else text[-1:]
    return f"{text[:head_chars]}{_COMPACTION_MARKER}{tail}"


def _next_trim_index(
    messages: list[Message], estimate_tokens: TokenEstimator, *, preserve_user_and_system: bool = False
) -> int | None:
    latest_user = _latest_user_index(messages)
    protected = _protected_message_indices(messages) if preserve_user_and_system else set()
    candidates = [
        index
        for index, message in enumerate(messages)
        if estimate_tokens(message.get("content", "")) > _MIN_CONTENT_TOKENS
        and index not in protected
        # 순수 도구 호출 래퍼는 trim 대상에서 제외한다 — 블록 제거가 유일한
        # 축소 경로라 호출이 빈 껍데기가 되어 고아 결과를 남긴다.
        # 페어 통째 드롭이 drop 단계에서 처리한다.
        and not _is_pure_tool_call_wrapper(message)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda index: (
            _protection_rank(messages[index], index, latest_user),
            -estimate_tokens(messages[index].get("content", "")),
            index,
        ),
    )


def _next_drop_index(messages: list[Message], *, preserve_user_and_system: bool = False) -> int | None:
    latest_user = _latest_user_index(messages)
    protected = _protected_message_indices(messages) if preserve_user_and_system else set()
    candidates = [index for index in range(len(messages)) if index != latest_user and index not in protected]
    if not candidates:
        return None if preserve_user_and_system else 0
    return min(
        candidates,
        key=lambda index: (_protection_rank(messages[index], index, latest_user), index),
    )


def _paired_message_index(messages: list[Message], index: int) -> int | None:
    if _is_tool_result_message(messages[index]):
        if index > 0 and _contains_tool_call(messages[index - 1]):
            return index - 1
    elif _contains_tool_call(messages[index]):
        if index + 1 < len(messages) and _is_tool_result_message(messages[index + 1]):
            return index + 1
    return None


def _protected_message_indices(messages: list[Message]) -> set[int]:
    latest_user = _latest_user_index(messages)
    latest_instruction = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "user" and not _is_tool_result_message(messages[index])
        ),
        latest_user,
    )
    protected = {
        index
        for index, message in enumerate(messages)
        if index in (latest_user, latest_instruction) or message.get("role") == "system"
    }
    for index in tuple(protected):
        pair = _paired_message_index(messages, index)
        if pair is not None:
            protected.add(pair)
    return protected


def _latest_user_index(messages: list[Message]) -> int:
    return next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        len(messages) - 1,
    )


def _protection_rank(message: Message, index: int, latest_user: int) -> int:
    content = message.get("content", "")
    # [TOOL_EVIDENCE]는 tool_loop가 실제로 생성하는 증거 봉투 마커다.
    # (이전 버전은 존재하지 않는 "VERIFIED_RESULT=" 마커를 검사해
    # 최상위 보호가 사실상 데드 코드였다.)
    if "[TOOL_EVIDENCE]" in content:
        return 5
    if index == latest_user:
        return 4
    role = message.get("role", "")
    return {"assistant": 0, "tool": 1, "user": 2, "system": 3}.get(role, 0)


def _total_tokens(messages: list[Message], estimate_tokens: TokenEstimator) -> int:
    return sum(estimate_tokens(message.get("content", "")) for message in messages)


_TOOL_CALL_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<(tool_call|action_call)>")
_TOOL_RESULT_RE: Final[re.Pattern[str]] = re.compile(r"<tool_response>|<tool_result>|\[TOOL_EVIDENCE\]")


def _contains_tool_call(message: Message) -> bool:
    """assistant 메시지가 도구 호출 마크업을 포함하는지."""
    return bool(_TOOL_CALL_TAG_RE.search(message.get("content", "")))


def _is_tool_result_message(message: Message) -> bool:
    """메시지가 도구 실행 결과(페어링된 호출의 응답)인지."""
    role = message.get("role", "")
    if role in ("tool", "function", "tool_result"):
        return True
    return bool(_TOOL_RESULT_RE.search(message.get("content", "")))


def _is_pure_tool_call_wrapper(message: Message) -> bool:
    """메시지가 (거의) 도구 호출 블록만으로 구성됐는지.

    호출 블록 제거 시 남는 텍스트가 절반 미만이면 순수 래퍼로 본다 —
    trim이 이런 메시지를 빈 껍데기로 만들지 못하게 한다.
    """
    content = message.get("content", "")
    if not _contains_tool_call(message):
        return False
    stripped = _TOOL_CALL_BLOCK_RE.sub("", content)
    return len(stripped.strip()) < len(content) * 0.5


# ─── CTX-02: deterministic final serialized prompt fitting ──────────────

from dataclasses import dataclass

from antigravity_k.engine.context_budget import (
    HardTokenLimit,
    PromptBudgetExceededError,
    PromptComponentLedger,
    build_prompt_component_ledger,
    prompt_selection_digest,
)
from antigravity_k.engine.tokenizer import TokenEstimator as DefaultTokenEstimator


@dataclass(frozen=True, slots=True)
class FinalPromptFit:
    """Result of the deterministic final-prompt compression pipeline."""

    system: str
    tools: str
    skills: str
    memory: str
    artifacts: str
    messages: list[Message]
    serialized: str
    ledger: PromptComponentLedger
    digest: str
    cache_prefix: str
    strategy: str
    compressed: bool


def serialize_final_prompt(
    *,
    system: str,
    tools: str,
    skills: str,
    messages: list[Message],
    memory: str = "",
    artifacts: str = "",
) -> tuple[str, str]:
    """Build the final serialized prompt and its immutable cache prefix.

    Cache prefix = System + skills + tools (stable bytes for provider caching).
    Memory/artifacts/messages sit in the mutable suffix (recency region).
    """
    prefix = f"System: {system}\n{skills}\n"
    if tools:
        prefix += f"\n{tools}\n"
    prefix += "\n"
    body_parts: list[str] = []
    for message in messages:
        body_parts.append(f"{message.get('role', 'user').capitalize()}: {message.get('content', '')}\n")
    if artifacts:
        body_parts.append(artifacts if artifacts.endswith("\n") else f"{artifacts}\n")
    if memory:
        body_parts.append(f"<working_context>\n{memory}</working_context>\n")
    suffix = "".join(body_parts) + "Assistant: "
    return prefix + suffix, prefix


def fit_final_prompt(
    *,
    system: str,
    tools: str,
    skills: str,
    messages: list[Message],
    hard_limit: HardTokenLimit,
    memory: str = "",
    artifacts: str = "",
    estimate_tokens: TokenEstimator | None = None,
    allow_typed_error: bool = True,
) -> FinalPromptFit:
    """Fit the final serialized prompt under ``hard_limit.input_budget``.

    Compression priority: artifacts → memory → skills → older messages.
    Prompt-cache prefix bytes stay identical when only the mutable suffix shrinks.
    System, selected tools, and the latest user request remain complete or raise a typed error.
    """
    estimate: TokenEstimator = estimate_tokens or DefaultTokenEstimator.estimate_text
    fitted = {
        "system": system,
        "tools": tools,
        "skills": skills,
        "memory": memory,
        "artifacts": artifacts,
    }
    fitted_messages = [dict(message) for message in messages]
    compressed = False
    strategy = "passthrough"

    def _message_blob(msgs: list[Message]) -> str:
        return "".join(
            f"{message.get('role', 'user').capitalize()}: {message.get('content', '')}\n" for message in msgs
        )

    def _ledger(msgs: list[Message]) -> PromptComponentLedger:
        return build_prompt_component_ledger(
            system=fitted["system"],
            tools=fitted["tools"],
            skills=fitted["skills"],
            memory=fitted["memory"],
            artifacts=fitted["artifacts"],
            serialized_messages=_message_blob(msgs),
            output_reserve=hard_limit.output_reserve,
            estimate_tokens=estimate,
        )

    def _serialize(msgs: list[Message]) -> tuple[str, str]:
        return serialize_final_prompt(
            system=fitted["system"],
            tools=fitted["tools"],
            skills=fitted["skills"],
            messages=msgs,
            memory=fitted["memory"],
            artifacts=fitted["artifacts"],
        )

    def _ok(msgs: list[Message]) -> bool:
        serialized, _prefix = _serialize(msgs)
        if estimate(serialized) > hard_limit.input_budget:
            return False
        ledger = _ledger(msgs)
        if ledger.input_total > hard_limit.input_budget:
            return False
        if ledger.total_with_reserve > hard_limit.effective:
            return False
        return True

    def _shrink_text(name: str, need: int) -> None:
        nonlocal compressed
        text = fitted[name]
        if not text or need <= 0:
            return
        current = estimate(text)
        target = max(0, current - need)
        fitted[name] = "" if target <= 0 else compact_text_to_budget(text, target, estimate)
        compressed = True

    def _shrink_messages(need: int) -> None:
        nonlocal compressed, fitted_messages
        if need <= 0 and _ok(fitted_messages):
            return
        mutable_room = max(0, _total_tokens(fitted_messages, estimate) - need)
        before = fitted_messages
        fitted_messages = enforce_context_budget(fitted_messages, mutable_room, estimate, preserve_user_and_system=True)
        compressed = compressed or fitted_messages != before

    def _excess(msgs: list[Message]) -> int:
        serialized, _ = _serialize(msgs)
        ledger = _ledger(msgs)
        return max(
            1,
            estimate(serialized) - hard_limit.input_budget,
            ledger.input_total - hard_limit.input_budget,
            ledger.total_with_reserve - hard_limit.effective,
        )

    if _ok(fitted_messages):
        serialized, cache_prefix = _serialize(fitted_messages)
        ledger = _ledger(fitted_messages)
        digest = prompt_selection_digest(
            system=fitted["system"],
            tools=fitted["tools"],
            skills=fitted["skills"],
            memory=fitted["memory"],
            artifacts=fitted["artifacts"],
            messages=fitted_messages,
        )
        return FinalPromptFit(
            system=fitted["system"],
            tools=fitted["tools"],
            skills=fitted["skills"],
            memory=fitted["memory"],
            artifacts=fitted["artifacts"],
            messages=messages if fitted_messages == messages else fitted_messages,
            serialized=serialized,
            ledger=ledger,
            digest=digest,
            cache_prefix=cache_prefix,
            strategy=strategy,
            compressed=False,
        )

    strategy = "deterministic_priority_v1"
    protected = _protected_message_indices(fitted_messages)
    essential_messages = [message for index, message in enumerate(fitted_messages) if index in protected]
    essential_serialized, _ = serialize_final_prompt(system=system, tools=tools, skills="", messages=essential_messages)
    essential_ledger = build_prompt_component_ledger(
        system=system,
        tools=tools,
        serialized_messages=_message_blob(essential_messages),
        output_reserve=hard_limit.output_reserve,
        estimate_tokens=estimate,
    )
    if (
        estimate(essential_serialized) > hard_limit.input_budget
        or essential_ledger.input_total > hard_limit.input_budget
        or essential_ledger.total_with_reserve > hard_limit.effective
    ):
        raise PromptBudgetExceededError(
            f"complete system, selected tools, and user request exceed budget {hard_limit.input_budget}",
            ledger=essential_ledger,
            hard_limit=hard_limit,
        )

    for component in ("artifacts", "memory", "skills"):
        while fitted[component] and not _ok(fitted_messages):
            before = fitted[component]
            _shrink_text(component, _excess(fitted_messages))
            if fitted[component] == before:
                break
    while not _ok(fitted_messages):
        before_msgs = fitted_messages
        _shrink_messages(_excess(fitted_messages))
        if fitted_messages == before_msgs:
            break

    serialized, cache_prefix = _serialize(fitted_messages)
    ledger = _ledger(fitted_messages)
    if not _ok(fitted_messages):
        raise PromptBudgetExceededError(
            f"final prompt input {estimate(serialized)} exceeds budget {hard_limit.input_budget}",
            ledger=ledger,
            hard_limit=hard_limit,
        )

    digest = prompt_selection_digest(
        system=fitted["system"],
        tools=fitted["tools"],
        skills=fitted["skills"],
        memory=fitted["memory"],
        artifacts=fitted["artifacts"],
        messages=fitted_messages,
    )
    return FinalPromptFit(
        system=fitted["system"],
        tools=fitted["tools"],
        skills=fitted["skills"],
        memory=fitted["memory"],
        artifacts=fitted["artifacts"],
        messages=fitted_messages,
        serialized=serialized,
        ledger=ledger,
        digest=digest,
        cache_prefix=cache_prefix,
        strategy=strategy,
        compressed=compressed,
    )
