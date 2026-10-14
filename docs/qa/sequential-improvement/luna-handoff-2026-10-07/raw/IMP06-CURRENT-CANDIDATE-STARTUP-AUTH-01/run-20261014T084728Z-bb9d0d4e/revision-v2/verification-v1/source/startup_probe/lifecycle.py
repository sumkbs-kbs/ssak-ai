# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Imported by the owned startup supervisor; pure fake operations in offline tests.
"""Post-spawn ownership, a single cleanup deadline, and fail-closed receipts."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from startup_probe.contract import Cleanup, SourcePlan


class Process(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def wait(self, timeout: float) -> int: ...


class Operations(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

    def signal(self, pid: int, signum: int) -> None: ...

    def group_empty(self, pid: int) -> bool: ...

    def write(self, path: Path, text: str) -> None: ...

    def emergency(self, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SystemOperations:
    outer_receipt: Path

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def signal(self, pid: int, signum: int) -> None:
        os.killpg(pid, signum)

    def group_empty(self, pid: int) -> bool:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return True
        return False

    def write(self, path: Path, text: str) -> None:
        path.write_text(text)

    def emergency(self, text: str) -> None:
        """Try an outer receipt and stderr independently; never turn failure into success."""
        try:
            self.outer_receipt.write_text(text)
        except OSError:
            text = text.rstrip() + "\nOUTER_RECEIPT_WRITE_FAILED\n"
        try:
            sys.stderr.write(text + "\n")
            sys.stderr.flush()
        except OSError:
            return


@dataclass(frozen=True, slots=True)
class CleanupResult:
    observed: Cleanup
    errors: tuple[str, ...]
    cleanup_deadline: float
    signal_races: int


@dataclass(frozen=True, slots=True)
class Terminal:
    outcome: str
    failures: tuple[str, ...]
    cleanup: CleanupResult
    elapsed_seconds: float
    terminal_file_written: bool


def cleanup_owned(
    child: Process, plan: SourcePlan, owned: Path, total_deadline: float, ops: Operations
) -> CleanupResult:
    """A failed stop-file write cannot bypass termination; every wait shares one deadline."""
    started = ops.now()
    deadline = min(total_deadline, started + plan.graceful_seconds + plan.kill_seconds)
    graceful_deadline = min(deadline, started + plan.graceful_seconds)
    errors: list[str] = []
    races = 0
    forced = False
    killed = False
    code: int | None = None
    reaped = False

    def send(signum: int) -> None:
        nonlocal races
        try:
            ops.signal(child.pid, signum)
        except ProcessLookupError:
            races += 1
        except OSError as exc:
            errors.append("signal:" + type(exc).__name__)

    def empty() -> bool:
        try:
            return ops.group_empty(child.pid)
        except ProcessLookupError:
            return True
        except OSError as exc:
            errors.append("group_probe:" + type(exc).__name__)
            return False

    def reap(until: float) -> bool:
        nonlocal code, reaped
        try:
            code = child.wait(timeout=max(0.0, min(until, deadline) - ops.now()))
            reaped = True
        except subprocess.TimeoutExpired:
            return False
        except OSError as exc:
            errors.append("wait:" + type(exc).__name__)
            return False
        return True

    try:
        ops.write(owned / "stop.requested", "graceful stop\n")
    except OSError as exc:
        errors.append("stop_write:" + type(exc).__name__)
        forced = True
        send(signal.SIGTERM)
    if not reap(graceful_deadline):
        forced = True
        killed = True
        send(signal.SIGKILL)
        _ = reap(deadline)
    if not empty():
        forced = True
        if not killed:
            send(signal.SIGKILL)
        while ops.now() < deadline and not empty():
            ops.sleep(min(0.05, max(0.0, deadline - ops.now())))
    if not reaped:
        _ = reap(deadline)
    return CleanupResult(Cleanup(code, reaped, empty(), forced), tuple(errors), deadline, races)


def own_spawned(
    child: Process,
    plan: SourcePlan,
    owned: Path,
    started_at: float,
    total_deadline: float,
    ops: Operations,
    observe: Callable[[Process], None],
    assess: Callable[[Cleanup], bool],
) -> Terminal:
    """Own every operation after Popen returns, including diagnostics and terminal writes."""
    failures: list[str] = []
    cleanup = CleanupResult(Cleanup(None, False, False, True), (), total_deadline, 0)
    accepted = False
    try:
        observe(child)
    except BaseException as exc:  # noqa: BLE001 — ownership boundary must also clean up interruption.
        failures.append("observation:" + type(exc).__name__)
    finally:
        try:
            cleanup = cleanup_owned(child, plan, owned, total_deadline, ops)
            failures.extend(cleanup.errors)
        except BaseException as exc:  # noqa: BLE001 — terminal receipt still required on cleanup defects.
            failures.append("cleanup:" + type(exc).__name__)
        finally:
            try:
                accepted = assess(cleanup.observed)
            except BaseException as exc:  # noqa: BLE001 — diagnostics must not skip the terminal result.
                failures.append("assessment:" + type(exc).__name__)
            finally:
                elapsed = ops.now() - started_at
                passed = accepted and not failures and cleanup.observed.passed() and ops.now() <= total_deadline
                terminal = Terminal(
                    "PASS_SCOPED_EXTERNAL_UVICORN_AUTH_LIFESPAN_ON" if passed else "NO_SUCCESS",
                    tuple(failures),
                    cleanup,
                    elapsed,
                    True,
                )
                try:
                    ops.write(owned / "result.json", json.dumps(asdict(terminal), indent=2))
                except OSError as exc:
                    terminal = Terminal(
                        "NO_SUCCESS",
                        (*terminal.failures, "terminal_write:" + type(exc).__name__),
                        cleanup,
                        elapsed,
                        False,
                    )
                    try:
                        ops.emergency(json.dumps(asdict(terminal), indent=2))
                    except OSError as fallback_error:
                        terminal = Terminal(
                            "NO_SUCCESS",
                            (*terminal.failures, "emergency_write:" + type(fallback_error).__name__),
                            cleanup,
                            elapsed,
                            False,
                        )
    return terminal
