"""Opt-in cross-restart call ledger for scoped test bundles (LLM / embedding send boundary).

OFF unless ``AGK_TEST_CALL_LEDGER_DIR`` is set. Each kind keeps one integer file guarded by an
exclusive ``fcntl`` lock, so restarts and parallel workers share one cumulative count.
An unreadable or corrupt counter fails closed: it is never silently reset to 0.
"""

from __future__ import annotations

import atexit
import fcntl
import os
import threading
from pathlib import Path

LEDGER_DIR_ENV = "AGK_TEST_CALL_LEDGER_DIR"
LIMIT_ENVS = {"llm": "AGK_TEST_LLM_TOTAL_LIMIT", "embed": "AGK_TEST_EMBED_TOTAL_LIMIT"}


class CallLedgerError(RuntimeError):
    """Ledger total reached or counter unreadable; nothing was sent."""

    status = "budget_exhausted"


class CallLedgerUnavailable(CallLedgerError):
    """r34: counter missing/unreadable or limit unset — a ledger fault, NOT a reached limit."""

    status = "ledger_unavailable"


class CallLedgerLimitReached(CallLedgerError):
    """r34: the configured cumulative total was actually reached."""

    status = "budget_exhausted"


def enabled() -> bool:
    return bool(os.environ.get(LEDGER_DIR_ENV, "").strip())


def reserve(kind: str) -> int | None:
    """Reserve one send for ``kind`` before sending; returns the cumulative number or None if off."""
    root = os.environ.get(LEDGER_DIR_ENV, "").strip()
    if not root:
        return None
    raw_limit = os.environ.get(LIMIT_ENVS[kind], "").strip()
    if not raw_limit:
        raise CallLedgerUnavailable(f"call ledger enabled but {LIMIT_ENVS[kind]} is not set")
    limit = int(raw_limit)
    path = Path(root) / f"{kind}.count"
    if not path.exists():
        raise CallLedgerUnavailable(f"call ledger counter missing for {kind}; refusing to assume 0")
    with open(path, "r+", encoding="ascii") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        text = fh.read().strip()
        if not text.isdigit():
            raise CallLedgerUnavailable(f"call ledger counter unreadable for {kind}")
        used = int(text)
        if used >= limit:
            raise CallLedgerLimitReached(f"test bundle {kind} total {used}/{limit} reached; not sent")
        used += 1
        fh.seek(0)
        fh.write(str(used))
        fh.truncate()
        fh.flush()
        os.fsync(fh.fileno())
    return used


# --- r32: per-reservation lifecycle journal -------------------------------------------------------
# The integer counter stays the *reservation* count (it caps concurrency/total and is never
# decremented after a send). Each reservation additionally gets an append-only lifecycle journal:
#   reserved -> blocked                       (pre-send refusal; nothing left the process)
#   reserved -> dispatched -> succeeded|failed
#   reserved -> dispatched -> aborted_unknown (stream closed/cancelled; the provider may have run it)
# A reservation that never reaches a terminal mark (process died) is reported as ``unknown`` and is
# counted as *possibly sent* (upper bound), so neither undercount nor double deduction can happen:
# a retry is a new reservation, and marks are idempotent per (reservation, state).

STATES = ("blocked", "dispatched", "succeeded", "failed", "aborted_unknown")
_TERMINAL = {"blocked", "succeeded", "failed", "aborted_unknown"}
_META_KEYS = frozenset({"request_id", "task_id", "purpose", "model", "attempt", "step"})


_open_lock = threading.Lock()
_open: dict[tuple[str, int], bool] = {}


def open_reservations() -> list[tuple[str, int]]:
    """r42: reservations dispatched by THIS process without a terminal mark yet."""
    with _open_lock:
        return sorted(_open)


def abort_open(reason: str = "shutdown") -> int:
    """r42: on task end / server stop, mark this process's still-open dispatched reservations
    ``aborted_unknown`` (the provider may have run them). Never re-sent, never turned into success."""
    pending = open_reservations()
    for kind, number in pending:
        mark(kind, number, "aborted_unknown", {"purpose": reason})
    return len(pending)


def mark(kind: str, number: int | None, state: str, meta: dict[str, object] | None = None) -> None:
    """Append one lifecycle mark for reservation ``number``. No-op when the ledger is off.

    r33: ``meta`` links the reservation to request_id / task_id / purpose / model / attempt
    (identifiers only — never prompt text). Every mark carries a UTC timestamp.
    """
    if number is None or state not in STATES:
        return
    root = os.environ.get(LEDGER_DIR_ENV, "").strip()
    if not root:
        return
    import json

    with _open_lock:
        if state == "dispatched":
            _open[(kind, int(number))] = True
        elif state in _TERMINAL:
            _open.pop((kind, int(number)), None)
    path = Path(root) / f"{kind}.journal"
    with open(path, "a", encoding="ascii") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        from datetime import UTC, datetime

        rec: dict[str, object] = {"n": int(number), "state": state, "ts": datetime.now(UTC).isoformat()}
        for key, value in (meta or {}).items():
            if key in _META_KEYS and isinstance(value, (str, int)) and not isinstance(value, bool):
                rec[key] = value
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def summary(kind: str, root: str | None = None) -> dict[str, int]:
    """Classify every reservation by its last lifecycle mark (no raw payloads involved)."""
    import json

    base = Path(root or os.environ.get(LEDGER_DIR_ENV, "").strip())
    count_path = base / f"{kind}.count"
    reserved = int(count_path.read_text(encoding="ascii").strip() or 0) if count_path.exists() else 0
    marks: dict[int, set[str]] = {}
    journal = base / f"{kind}.journal"
    if journal.exists():
        for line in journal.read_text(encoding="ascii").splitlines():
            if line.strip():
                rec = json.loads(line)
                marks.setdefault(int(rec["n"]), set()).add(str(rec["state"]))
    out = {
        "reserved": reserved,
        "blocked": 0,
        "dispatched": 0,
        "succeeded": 0,
        "failed": 0,
        "aborted_unknown": 0,
        "unknown": 0,
        "unmarked": 0,
    }
    for n in range(1, reserved + 1):
        states = marks.get(n, set())
        if not states:
            out["unmarked"] += 1  # reserved before journaling existed, or died before dispatch
            continue
        if "dispatched" in states:
            out["dispatched"] += 1
        terminal = states & _TERMINAL
        for t in terminal:
            out[t] += 1
        if "dispatched" in states and not (terminal - {"blocked"}):
            out["unknown"] += 1
    out["possibly_sent_upper_bound"] = out["dispatched"] + out["unmarked"]
    return out


atexit.register(abort_open, "process_exit")
