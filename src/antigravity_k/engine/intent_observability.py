"""r32: structured, text-free intent-classification events.

Each event says what the classifier concluded, at which stage, whether that stage succeeded, and
which follow-up path the request took. It never stores the user's text, tokens, or prompt — only
its length. Events live in a bounded in-process ring exposed by the models diagnostics endpoint,
so they are observable without lowering the application log level.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Literal, TypedDict

Stage = Literal["keyword", "llm", "llm_error_keyword_fallback"]
FollowUp = Literal["fast_search", "tdd", "tdd_rejected_no_code_signal", "general", "memory"]


class IntentEvent(TypedDict, total=False):
    seq: int
    ts: float
    intent: str
    stage: str
    ok: bool
    follow_up: str
    text_len: int
    # r33: model selection, response parsing and the path actually taken (after mode overrides).
    model: str
    parse: str
    reply_len: int
    final_path: str


_PARSE = frozenset({"none", "matched_tdd", "matched_search", "matched_memory", "default_general", "provider_error"})
_PATHS = frozenset({"fast_search", "tdd", "general", "memory"})  # r41: memory recall is its own path


_lock = threading.Lock()
_ring: deque[IntentEvent] = deque(maxlen=50)
_seq = 0


def record(
    intent: str,
    stage: Stage,
    ok: bool,
    follow_up: FollowUp,
    text_len: int,
    *,
    model: str = "",
    parse: str = "none",
    reply_len: int = 0,
) -> IntentEvent:
    global _seq
    with _lock:
        _seq += 1
        event: IntentEvent = {
            "seq": _seq,
            "ts": round(time.time(), 3),
            "intent": str(intent)[:16],
            "stage": stage,
            "ok": bool(ok),
            "follow_up": follow_up,
            "text_len": int(text_len),
            "model": _model_label(model),
            "parse": parse if parse in _PARSE else "none",
            "reply_len": int(reply_len),
            "final_path": "",
        }
        _ring.append(event)
    return event


def _model_label(model: str) -> str:
    """Model name only (``name:tag``); anything path- or URL-like is dropped."""
    text = str(model or "")[:64]
    return "" if any(ch in text for ch in "/\\ @?=") else text


def finalize(event: IntentEvent | None, path: str) -> None:
    """Record the follow-up path actually taken after access-mode / request overrides."""
    if event is None:
        return
    with _lock:
        event["final_path"] = path if path in _PATHS else "general"


def snapshot() -> dict[str, object]:
    with _lock:
        return {"total": _seq, "recent": list(_ring)}
