"""r41: per-task tool allowlist and completed-call reuse, enforced at the executor boundary.

The allowlist is server-side task state (checkpoint context ``allowed_tools``), never a
prompt instruction. A tool outside the list is refused before any gate runs, so it cannot
create an approval request. Naming a tool in the prompt grants nothing.

Completed-call reuse: an identical side-effecting call (same tool, same canonical args)
that already completed in this task returns its recorded result instead of executing or
asking for approval again. Records live in the task execution-event log, so they survive
a server restart and resume.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol, cast

COMPLETED_EVENT = "task_tool.completed"
MAX_QUOTA = 5
_RESULT_KEEP = 2000


class _Store(Protocol):
    def get_last_checkpoint(self, task_id: str) -> Mapping[str, object] | None: ...

    def append_execution_event(self, task_id: str, event_type: str, payload_json: str) -> int: ...

    def list_execution_events(self, task_id: str) -> list[Mapping[str, object]]: ...


def normalize_allowed_tools(raw: object) -> dict[str, int] | None:
    """Return {tool: max_calls} or None when no allowlist is configured.

    A list means one call each; a mapping gives explicit quotas (0..MAX_QUOTA).
    Invalid input raises ValueError so a malformed contract never silently widens access.
    """
    if raw is None:
        return None
    out: dict[str, int] = {}
    if isinstance(raw, (list, tuple)):
        for item in cast(list[object], list(raw)):
            if not isinstance(item, str) or not item.strip():
                raise ValueError("allowed_tools entries must be non-empty strings")
            out[item.strip()] = 1
        return out
    if isinstance(raw, Mapping):
        for key, value in cast(Mapping[object, object], raw).items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("allowed_tools keys must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_QUOTA:
                raise ValueError(f"allowed_tools quota must be an int 0..{MAX_QUOTA}")
            out[key.strip()] = value
        return out
    raise ValueError("allowed_tools must be a list or mapping")


def call_key(name: str, args: Mapping[str, object]) -> str:
    canonical = json.dumps({"tool": name, "args": dict(args)}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def task_allowed_tools(store: _Store, task_id: str) -> dict[str, int] | None:
    checkpoint = store.get_last_checkpoint(task_id)
    if checkpoint is None:
        return None
    try:
        payload = json.loads(str(checkpoint["context_json"]))
    except (json.JSONDecodeError, TypeError, KeyError):
        # Unreadable state must not widen access: treat as "no tools".
        return {}
    if not isinstance(payload, dict):
        return {}
    raw = cast(dict[str, object], payload).get("allowed_tools")
    try:
        return normalize_allowed_tools(raw)
    except ValueError:
        return {}


def _completed(store: _Store, task_id: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for event in store.list_execution_events(task_id):
        if event.get("event_type") != COMPLETED_EVENT:
            continue
        try:
            payload = json.loads(str(event.get("payload_json")))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            records.append(cast(dict[str, object], payload))
    return records


def completed_records(store: _Store, task_id: str) -> list[dict[str, object]]:
    """r42: completed side-effect tool records of this task (read-only view)."""
    return _completed(store, task_id)


def completed_result(store: _Store, task_id: str, key: str) -> str | None:
    for record in _completed(store, task_id):
        if record.get("key") == key:
            return str(record.get("result", ""))
    return None


def completed_count(store: _Store, task_id: str, tool: str) -> int:
    return sum(1 for record in _completed(store, task_id) if record.get("tool") == tool)


def record_completed(store: _Store, task_id: str, tool: str, key: str, result: str) -> None:
    payload = {"tool": tool, "key": key, "result": result[:_RESULT_KEEP]}
    store.append_execution_event(task_id, COMPLETED_EVENT, json.dumps(payload, ensure_ascii=False))
