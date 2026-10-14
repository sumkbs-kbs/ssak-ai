# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
# Pytest plugin: -p offline_guard, only in the owned offline preparation run.
"""Prove preparation did not import the product or start sockets/processes."""

import json
import os
import sys
from pathlib import Path
from typing import TypeVar

import pytest

T = TypeVar("T")
attempts: list[str] = []


def audit(event: str, args: tuple[T, ...]) -> None:
    if event in ("socket.connect", "socket.bind", "subprocess.Popen"):
        attempts.append(event)
        raise RuntimeError("Preparation forbids external execution: " + event)


sys.addaudithook(audit)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    product = [name for name in sys.modules if name.startswith(("antigravity_k", "uvicorn", "chromadb"))]
    if attempts or product:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    Path(os.environ["OFFLINE_BOUNDARY_PATH"]).write_text(
        json.dumps({"attempts": attempts, "product_modules": product, "exitstatus": int(session.exitstatus)}, indent=2)
    )
