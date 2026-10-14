# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest"]
# ///
# How to run: loaded by capture.py through pytest -p qa_receipts.
"""Write actual pytest report events without installing another plugin."""

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Final

import pytest

RUN: Final = Path(os.environ["RESTART_QA_RUN"])
ROOT: Final = Path(os.environ["RESTART_QA_ROOT"])


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Preserve pytest's real phase outcome and duration."""
    with (RUN / "pytest-reports.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome, "duration": report.duration, "longrepr": str(report.longrepr)}) + "\n")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Bind loaded project modules and the terminal pytest exit status."""
    modules = []
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and str(filename).startswith(str(ROOT)) and "site-packages" not in str(filename):
            file = Path(filename)
            if file.is_file():
                modules.append({"module": name, "path": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    (RUN / "pytest-session.json").write_text(json.dumps({"exitstatus": int(exitstatus), "testscollected": session.testscollected, "modules": modules}, indent=2))
