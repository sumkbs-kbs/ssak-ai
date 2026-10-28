"""Saved-note / past-decision recall detector shared by chat routing and the orchestrator gate.

r34 root cause: "what did we agree/save earlier" went to web search. r38 root cause: the same
intent reached the agent graph, the CEO classified it simple_chat and the gate skipped
CONTEXT_ENRICH, so the past_memory vault search never ran.
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token

_MEMORY_RECALL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(did|have)\s+(we|i)\s+(agree|decide|settle|choose|pick|note|save|write down|record)",
        r"\bwe\s+(agreed|decided|settled on|chose|picked)\b",
        r"\b(i|we)\s+(noted|saved|wrote down|recorded|memo'?d)\b",
        r"\b(remember|recall)\b.*\b(we|i|our|my)\b",
        r"\b(my|our)\s+(memo|note|notes|decision record)\b",
        r"(우리가|내가|제가)\s*.{0,12}(정한|합의한|결정한|메모한|저장한|기록한)",
        r"(지난번|예전에|전에)\s*.{0,12}(정한|합의|결정|메모|저장|기록)",
        r"(메모|기억).{0,8}(뭐|무엇|알려|찾아)",
    )
]


def is_memory_recall(text: str) -> bool:
    return any(p.search(text or "") for p in _MEMORY_RECALL_PATTERNS)


# r41 root cause (r40 rB): chat.py's classifier (keyword *or* LLM) concluded MEMORY, but that decision
# was never handed on — the non-agent attach step and the agent CEO gate each re-ran the regex above,
# which misses e.g. a Korean "...정했던 ..." question, so no vault search ran (0 embeddings) and the
# request was recorded as final_path=general. The classifier's decision is now carried per request.
_request_recall: ContextVar[bool | None] = ContextVar("agk_request_memory_recall", default=None)


def set_request_recall(decided: bool) -> Token[bool | None]:
    """Record this request's classifier decision (True = MEMORY). Request-scoped (contextvar)."""
    return _request_recall.set(bool(decided))


def reset_request_recall(token: Token[bool | None]) -> None:
    _request_recall.reset(token)


def request_recall_decision() -> bool | None:
    return _request_recall.get()


def wants_memory_recall(text: str) -> bool:
    """True when this request's classifier decided MEMORY, or the shared detector matches the text."""
    return bool(_request_recall.get()) or is_memory_recall(text)


__all__ = [
    "is_memory_recall",
    "request_recall_decision",
    "reset_request_recall",
    "set_request_recall",
    "wants_memory_recall",
]
