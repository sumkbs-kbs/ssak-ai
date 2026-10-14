"""DAT-01 state/event projection order for task terminals.

Authoritative terminal outcome is ``task_history.status``. Execution events are
ordered by ``sequence`` and may describe progress, but they must not flip the
UI to a different terminal than the store after a CAS winner is committed.

Rules:
1. If store status is terminal (done|failed|cancelled), display that status.
2. Otherwise derive a non-terminal hint from the latest ``task.status`` event.
3. Ignore contradictory non-``task.status`` completion/cancel event types when
   the store already holds a different terminal (lost-race / buggy append).
"""

from __future__ import annotations

import json
from typing import Final, Iterable, Literal, cast

from antigravity_k.engine.task_events import ExecutionEventRecord
from antigravity_k.engine.task_state_types import TERMINAL_TASK_STATUSES

DisplayTerminalStatus = Literal["pending", "running", "resuming", "paused", "done", "failed", "cancelled", "unknown"]

_EVENT_TERMINAL_HINTS: Final[dict[str, DisplayTerminalStatus]] = {
    "done": "done",
    "completed": "done",
    "failed": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}

_DISPLAY_STATUSES: Final[dict[str, DisplayTerminalStatus]] = {
    status: cast(DisplayTerminalStatus, status)
    for status in ("pending", "running", "resuming", "paused", "done", "failed", "cancelled", "unknown")
}


def _status_from_task_status_payload(payload_json: str) -> DisplayTerminalStatus | None:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    to_status = payload.get("to_status")
    return _DISPLAY_STATUSES.get(to_status) if isinstance(to_status, str) else None


def resolve_display_terminal_status(
    store_status: str,
    events: Iterable[ExecutionEventRecord],
) -> DisplayTerminalStatus:
    if store_status in TERMINAL_TASK_STATUSES:
        return _DISPLAY_STATUSES.get(store_status, "unknown")
    if store_status in {"pending", "running", "resuming", "paused"}:
        # Prefer latest CAS-emitted task.status while still non-terminal.
        latest: DisplayTerminalStatus | None = None
        for event in events:
            if event["event_type"] != "task.status":
                continue
            hinted = _status_from_task_status_payload(event["payload_json"])
            if hinted is not None:
                latest = hinted
        return latest if latest is not None else _DISPLAY_STATUSES.get(store_status, "unknown")
    return "unknown"


def event_implies_terminal(event_type: str) -> DisplayTerminalStatus | None:
    normalized = event_type.lower()
    for needle, status in _EVENT_TERMINAL_HINTS.items():
        if needle in normalized:
            return status
    return None


__all__ = [
    "DisplayTerminalStatus",
    "event_implies_terminal",
    "resolve_display_terminal_status",
]
