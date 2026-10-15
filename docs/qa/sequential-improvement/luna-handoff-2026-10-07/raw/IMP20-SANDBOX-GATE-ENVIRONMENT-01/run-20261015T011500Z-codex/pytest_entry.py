import json
import os
import sys
from pathlib import Path

OUTPUT = Path(sys.argv[1])
EVENTS = []


def audit(event, args):
    if event in {"socket.connect", "socket.bind"}:
        EVENTS.append({"event": event, "address": repr(args[1:]), "blocked": True})
        raise PermissionError("Diagnostic permits no network connect or bind")
    if event == "subprocess.Popen":
        EVENTS.append({"event": event, "executable": str(args[0]), "argv": args[1], "cwd": str(args[2])})


sys.addaudithook(audit)
import pytest

from antigravity_k.engine.sandbox import _python_runtime_read_paths

(OUTPUT / "runtime.json").write_text(json.dumps({
    "executable": sys.executable,
    "resolved_executable": os.path.realpath(sys.executable),
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "product_runtime_read_paths": _python_runtime_read_paths(),
}, indent=2) + "\n")
try:
    status = pytest.main([
        "-q", "-p", "no:cacheprovider",
        "tests/test_cr03_sandbox_read_boundary.py::TestWorkspaceStillRuns::test_python_runs_inside_workspace",
        "--basetemp", str(OUTPUT / "private-runtime" / "pytest"),
        "--junitxml", str(OUTPUT / "junit.xml"),
    ])
finally:
    (OUTPUT / "audit.json").write_text(json.dumps(EVENTS, indent=2) + "\n")
raise SystemExit(status)
