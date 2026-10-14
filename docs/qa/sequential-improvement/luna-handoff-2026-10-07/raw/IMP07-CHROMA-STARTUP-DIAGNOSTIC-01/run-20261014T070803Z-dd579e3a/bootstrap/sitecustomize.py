# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# How to run: inherited through the supervisor's owned PYTHONPATH; no installation.
"""Deny physical networking before native Chroma initialization."""

import json
import os
from pathlib import Path
import socket
import sys
from typing import Final

RUN: Final = Path(os.environ["CHROMA_QA_RUN"])
LOG: Final = RUN / f"guard-{os.getpid()}.jsonl"
type AuditValue = socket.socket | str | int | bytes | None | tuple[AuditValue, ...]


class NetworkDenied(PermissionError):
    """No physical network or external executables are allowed by this probe."""


def record(event: str, operation: str = "", family: int = 0) -> None:
    with LOG.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"event": event, "operation": operation, "family": family, "pid": os.getpid(), "ppid": os.getppid()}) + "\n")


def audit(event: str, args: tuple[AuditValue, ...]) -> None:
    if event in {"socket.connect", "socket.bind", "socket.sendto"}:
        match args[0]:
            case socket.socket() as endpoint:
                physical = endpoint.family in {socket.AF_INET, socket.AF_INET6}
                record("physical_denied" if physical else "ipc_socket", event, int(endpoint.family))
                if physical:
                    raise NetworkDenied(event)
            case _:
                raise NetworkDenied("unrecognized socket audit argument")
    if event in {"socket.getaddrinfo", "subprocess.Popen"}:
        record("physical_denied" if event.startswith("socket.") else "external_process_denied", event)
        raise NetworkDenied(event)


ORIGINAL_LISTEN: Final = socket.socket.listen


def guarded_listen(endpoint: socket.socket, backlog: int = 0) -> None:
    physical = endpoint.family in {socket.AF_INET, socket.AF_INET6}
    record("physical_denied" if physical else "ipc_socket", "socket.listen", int(endpoint.family))
    if physical:
        raise NetworkDenied("socket.listen")
    ORIGINAL_LISTEN(endpoint, backlog)


sys.addaudithook(audit)
socket.socket.listen = guarded_listen
record("guard_installed")
