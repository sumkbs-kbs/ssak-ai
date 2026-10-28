"""r34: durable execution journal for side-effecting file tools (write_artifact).

Scope (deliberately narrow — NOT an exactly-once guarantee for every tool):
  * write_artifact only. Other tools are unchanged.
  * Each logical write is keyed by an execution id = sha256(task_id | target). Records:
      intent   {exec_id, target, content_sha, pre_sha}   fsync'd BEFORE the file is touched
      executed {exec_id, result_sha}                     fsync'd right after the atomic replace
  * The file write is atomic (tmp + fsync + os.replace), so a torn artifact is impossible.
  * On a later call for the same exec_id we classify against the real artifact:
      completed      file sha == recorded/intended content sha -> do not write again
      not_executed   intent only and file sha == pre_sha (or absent when pre_sha empty) -> safe to write
      unknown        anything else -> HOLD (no write, explicit error)
  * Without a task context (ad-hoc chat call) journaling is per-call only and a resume skip is
    impossible; that path behaves exactly as before.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

CURRENT_TASK: contextvars.ContextVar[tuple[str, bool] | None] = contextvars.ContextVar(
    "agk_tool_journal_task", default=None
)


@contextlib.contextmanager
def task_scope(task_id: str, resuming: bool) -> Iterator[None]:
    """r35 restore contract: set the task context and ALWAYS restore the previous value
    (normal end, exception, early return, pause/cancel/approval-wait returns, generator close)."""
    token = CURRENT_TASK.set((task_id, resuming))
    try:
        yield
    finally:
        CURRENT_TASK.reset(token)


# Test-only fault injection: called with a point name; may raise to simulate a crash.
FAULT_HOOK: Callable[[str], None] | None = None


def _fault(point: str) -> None:
    if FAULT_HOOK is not None:
        FAULT_HOOK(point)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return sha256_bytes(fh.read())
    except FileNotFoundError:
        return ""


def execution_id(task_id: str, target: str) -> str:
    return sha256_bytes(f"{task_id}|{os.path.basename(target)}".encode())[:32]


class Journal:
    def __init__(self, directory: str) -> None:
        self.path = Path(directory) / ".tool_journal.jsonl"

    def append(self, rec: dict[str, object]) -> None:
        rec = {**rec, "ts": datetime.now(UTC).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # r35: never follow a symlink planted at the journal name.
        jfd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(jfd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def records(self, exec_id: str) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        out: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn trailing line from a crash mid-append: ignored, never trusted
            if isinstance(rec, dict) and rec.get("exec_id") == exec_id:
                out.append(rec)
        return out


def classify(journal: Journal, exec_id: str, filepath: str) -> tuple[str, dict[str, object] | None]:
    """Return (completed|not_executed|unknown|none, last_intent)."""
    recs = journal.records(exec_id)
    intents = [r for r in recs if r.get("state") == "intent"]
    if not intents:
        return "none", None
    last = intents[-1]
    executed = [r for r in recs if r.get("state") == "executed" and r.get("intent_seq") == last.get("seq")]
    current = file_sha(filepath)
    if executed:
        return ("completed" if current == executed[-1].get("result_sha") else "unknown"), last
    if current and current == last.get("content_sha"):
        return "completed", last  # written, crash before the result record
    if current == last.get("pre_sha"):
        return "not_executed", last
    return "unknown", last


def atomic_write(filepath: str, content: str) -> None:
    """r35: tmp create + fsync + rename all relative to ONE directory fd opened with O_NOFOLLOW,
    so a directory swapped for a symlink after the check cannot redirect the write; an existing
    symlink at the target name is replaced (never followed)."""
    directory = os.path.dirname(filepath) or "."
    name = os.path.basename(filepath)
    dflags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    dfd = os.open(directory, dflags)
    tmp = f".tmp-{os.getpid()}-{os.urandom(6).hex()}"
    created = False
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644, dir_fd=dfd)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        created = False
        os.fsync(dfd)
    finally:
        if created:
            try:
                os.unlink(tmp, dir_fd=dfd)
            except OSError:
                pass
        os.close(dfd)


def journaled_write(directory: str, filepath: str, content: str) -> tuple[str, str]:
    """Write ``content`` once per (task, target). Returns (outcome, exec_id).

    outcome: written | skipped_completed | held_unknown
    """
    ctx = CURRENT_TASK.get()
    data_sha = sha256_bytes(content.encode("utf-8"))
    journal = Journal(directory)
    if ctx is None:
        _fault("before_exec")
        atomic_write(filepath, content)
        _fault("after_exec")
        return "written", ""
    task_id, resuming = ctx
    exec_id = execution_id(task_id, filepath)
    state, last = classify(journal, exec_id, filepath)
    if state == "unknown":
        journal.append({"exec_id": exec_id, "state": "held", "reason": "unknown_side_effect"})
        return "held_unknown", exec_id
    if state == "completed" and (resuming or (last is not None and last.get("content_sha") == data_sha)):
        if last is not None and not [r for r in journal.records(exec_id) if r.get("state") == "executed"]:
            journal.append(
                {
                    "exec_id": exec_id,
                    "state": "executed",
                    "intent_seq": last.get("seq"),
                    "result_sha": file_sha(filepath),
                    "recovered": True,
                }
            )
        return "skipped_completed", exec_id
    seq = len(journal.records(exec_id)) + 1
    journal.append(
        {
            "exec_id": exec_id,
            "state": "intent",
            "seq": seq,
            "target": os.path.basename(filepath),
            "content_sha": data_sha,
            "pre_sha": file_sha(filepath),
        }
    )
    _fault("before_exec")
    atomic_write(filepath, content)
    _fault("after_exec")
    journal.append({"exec_id": exec_id, "state": "executed", "intent_seq": seq, "result_sha": data_sha})
    _fault("after_result")
    return "written", exec_id
