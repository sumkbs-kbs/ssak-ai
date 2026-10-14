# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# How to run: inherited via PYTHONPATH by the owned capture.py invocation.
"""Observe process lifecycle and deny physical networking in every Python child."""

from __future__ import annotations

import json
import multiprocessing
import multiprocessing.process
import os
from pathlib import Path
import signal
import socket
import sys
import time
from types import FrameType
from typing import Final

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type AuditValue = socket.socket | str | int | bytes | None | tuple[AuditValue, ...]

RUN: Final = Path(os.environ["RESTART_QA_RUN"])
ROOT: Final = Path(os.environ["RESTART_QA_ROOT"])
LOG: Final = RUN / "process-ledger" / f"{os.getpid()}.jsonl"
LOG.parent.mkdir(parents=True, exist_ok=True)


def record(event: str, **details: JsonValue) -> None:
    """Append one complete observation to this process's own ledger."""
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": event, "pid": os.getpid(), "ppid": os.getppid(), "time": time.time(), **details}) + "\n")


class PhysicalNetworkDenied(PermissionError):
    """The owned QA run permits IPC but no physical network access."""


def audit(event: str, args: tuple[AuditValue, ...]) -> None:
    """Deny internet socket operations and distinguish local IPC."""
    if event in {"socket.connect", "socket.bind", "socket.sendto"}:
        match args[0]:
            case socket.socket() as endpoint:
                physical = endpoint.family in {socket.AF_INET, socket.AF_INET6}
                record("physical_network_denied" if physical else "ipc_socket", operation=event, family=int(endpoint.family))
                if physical:
                    raise PhysicalNetworkDenied(event)
            case _:
                raise PhysicalNetworkDenied("unrecognized socket audit argument")
    if event == "socket.getaddrinfo":
        record("physical_network_denied", operation=event)
        raise PhysicalNetworkDenied(event)
    if event == "subprocess.Popen":
        record("external_process_denied", executable=str(args[0]))
        raise PhysicalNetworkDenied("external executables are outside this fixture")


ORIGINAL_LISTEN: Final = socket.socket.listen


def guarded_listen(endpoint: socket.socket, backlog: int = 0) -> None:
    """Block internet listeners; preserve multiprocessing Unix IPC."""
    physical = endpoint.family in {socket.AF_INET, socket.AF_INET6}
    record("physical_network_denied" if physical else "ipc_socket", operation="socket.listen", family=int(endpoint.family))
    if physical:
        raise PhysicalNetworkDenied("socket.listen")
    ORIGINAL_LISTEN(endpoint, backlog)


sys.addaudithook(audit)
socket.socket.listen = guarded_listen
ORIGINAL_START: Final = multiprocessing.process.BaseProcess.start
ORIGINAL_JOIN: Final = multiprocessing.process.BaseProcess.join
ORIGINAL_KILL: Final = multiprocessing.process.BaseProcess.kill
ORIGINAL_RUN: Final = multiprocessing.process.BaseProcess.run


def observed_start(self: multiprocessing.process.BaseProcess) -> None:
    """Delegate unchanged and record the actual newly allocated PID."""
    ORIGINAL_START(self)
    record("process_started", child_pid=self.pid, name=self.name)


def observed_join(self: multiprocessing.process.BaseProcess, timeout: float | None = None) -> None:
    """Record the OS wait result after the original join."""
    ORIGINAL_JOIN(self, timeout)
    record("process_joined", child_pid=self.pid, exitcode=self.exitcode, alive=self.is_alive())


def observed_kill(self: multiprocessing.process.BaseProcess) -> None:
    """Record the target then delegate to the actual process kill."""
    record("process_kill_requested", child_pid=self.pid)
    ORIGINAL_KILL(self)


def observed_run(self: multiprocessing.process.BaseProcess) -> None:
    """Capture target identity and resolved project module paths."""
    record("worker_run_entered", name=self.name, target=getattr(self, "_target").__name__)
    try:
        ORIGINAL_RUN(self)
    finally:
        modules: dict[str, JsonValue] = {name: str(module.__file__) for name, module in tuple(sys.modules.items()) if getattr(module, "__file__", None) and str(module.__file__).startswith(str(ROOT)) and "site-packages" not in str(module.__file__)}
        record("worker_run_returned", modules=modules)


def deadline_cleanup(signum: int, _frame: FrameType | None) -> None:
    """Reap only children owned by this process on the outer deadline."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    children = multiprocessing.active_children()
    record("deadline_cleanup_started", signal=signum, owned_children=[child.pid for child in children])
    for child in children:
        if child.is_alive():
            child.kill()
        child.join(timeout=1)
    record("deadline_cleanup_finished", remaining=[child.pid for child in multiprocessing.active_children()])
    os._exit(124)


multiprocessing.process.BaseProcess.start = observed_start
multiprocessing.process.BaseProcess.join = observed_join
multiprocessing.process.BaseProcess.kill = observed_kill
multiprocessing.process.BaseProcess.run = observed_run
signal.signal(signal.SIGTERM, deadline_cleanup)
record("guard_installed", executable=sys.executable, cwd=os.getcwd(), pythonpath=os.environ.get("PYTHONPATH", ""))
