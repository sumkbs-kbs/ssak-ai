"""Deterministic conversation summaries with structured tool-evidence retention.

NX-01: compaction generations must not lose explicit user constraints.  The
previous store-generated summary is carried forward instead of being treated as
just another old message, and structured constraints (stable id / status /
source) are rendered ahead of free prose so they survive budget truncation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from antigravity_k.engine.summary_memory import (
    SUMMARY_TEXT_BUDGET_CHARS,
    SummaryMemory,
    compose_summary,
    render_marker,
)
from antigravity_k.engine.tool_evidence_compactor import compact_structured_tool_response

Message = dict[str, str]
Summarizer = Callable[[str], str]

logger = logging.getLogger("antigravity_k.context_summary")


def summarize_messages(
    old_messages: list[Message],
    summarize_fn: Summarizer | None,
    *,
    memory: SummaryMemory | None = None,
    carryover: str = "",
    budget: int = SUMMARY_TEXT_BUDGET_CHARS,
) -> str:
    """Summarize old messages without replacing verifiable tool evidence with prose.

    ``memory`` carries the durable structured constraints (when the caller owns
    one, i.e. :class:`ConversationStore`); ``carryover`` is the previous
    store-generated summary text, which is preserved explicitly so a later
    compaction generation cannot drop the earliest user requirements.
    """
    if not old_messages:
        return ""

    header = f"[대화 요약 — {len(old_messages)}개 메시지 압축]"
    evidence_blocks: list[str] = []
    for message in old_messages:
        compacted = compact_structured_tool_response(message.get("content", ""))
        # Identical evidence (e.g. the same tool_response twice) is kept once:
        # repetition only spends prompt budget without adding provenance.
        if compacted is not None and compacted not in evidence_blocks:
            evidence_blocks.append(compacted)
    preserved_evidence = evidence_blocks[-5:]
    # NX-01: a message whose text is already retained as a structured
    # constraint is rendered in the constraint block, not repeated as prose.
    constraint_source_ids = {c.source_message_id for c in memory.constraints} if memory is not None else set()

    body: str | None = None
    if summarize_fn is not None:
        prompt = _summary_prompt(old_messages, memory=memory, carryover=carryover)
        try:
            summary = summarize_fn(prompt)
            if summary and len(summary.strip()) > 20:
                sections = [summary.strip()]
                sections.extend(preserved_evidence)
                body = "\n".join(sections)
        except Exception:
            logger.exception("[Compressor] LLM summarization failed")

    if body is None:
        key_messages = [
            f"[{message.get('role', '')}]: {message.get('content', '')[:100]}"
            for message in old_messages
            if message.get("role") in ("user", "tool")
            and message.get("content", "")
            and compact_structured_tool_response(message.get("content", "")) is None
            and (message.get("id") or "") not in constraint_source_ids
        ]
        if preserved_evidence:
            # FR-09/RP-09: 초기 사용자 결정(제약·요구)도 evidence와 함께 보존한다.
            # evidence만 남기면 대화의 핵심 결정사항이 요약에서 사라진다.
            body = (
                "\n".join([*key_messages[:5], *preserved_evidence]) if key_messages else "\n".join(preserved_evidence)
            )
        elif key_messages:
            body = "\n".join(key_messages[:5])
        else:
            body = ""

    if memory is None:
        # Legacy caller without a structured owner: keep the pre-NX-01 shape
        # (no store marker, no invented constraints).
        if not body.strip() and not carryover.strip():
            return f"[System Note: {len(old_messages)} older messages were pruned for context efficiency. The agent has already explored previous steps.]"
        sections = [header]
        if carryover.strip():
            sections.append(carryover.strip())
        if body.strip():
            sections.append(body)
        return "\n".join(sections)[:budget]
    # The schema marker costs prompt budget on every generation, so it is only
    # emitted when this summary actually carries structured state (constraints
    # or a carried-over previous summary).  Records always persist
    # ``memory.schema`` and message provenance regardless of the marker.
    marker = render_marker(memory) if (memory.constraints or memory.carried_summary) else ""
    return compose_summary(
        header=header,
        memory=memory,
        carryover=carryover,
        body=body,
        budget=budget,
        marker=marker,
    )


def _summary_prompt(
    messages: list[Message],
    *,
    memory: SummaryMemory | None = None,
    carryover: str = "",
) -> str:
    instruction = "아래 대화 기록을 3줄 이내로 핵심만 요약해주세요. "
    instruction += "특히 사용자의 결정사항, 아키텍처 선택, 변경된 파일을 포함하세요.\n\n"
    context: list[str] = []
    if memory is not None:
        from antigravity_k.engine.summary_memory import render_constraint_block

        block = render_constraint_block(memory)
        if block:
            context.append("이미 보존된 사용자 제약(변경 금지, 그대로 유지):\n" + block)
    if carryover.strip():
        context.append("이전 압축 요약:\n" + carryover.strip())
    combined = "\n".join(f"[{message.get('role', '?')}]: {message.get('content', '')[:200]}" for message in messages)
    return instruction + "\n\n".join([*context, combined])[:2000]
