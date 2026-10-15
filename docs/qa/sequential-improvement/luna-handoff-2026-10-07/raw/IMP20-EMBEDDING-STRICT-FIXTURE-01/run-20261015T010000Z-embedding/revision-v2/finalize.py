# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: candidate/.venv/bin/python -B finalize.py
"""Capture static checks and prove the test-only patch reconstructs exactly."""

from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
PYTHON = str(REPO / ".venv/bin/python")
OUT = BASE / "static"
OUT.mkdir()
before = BASE / "preimage/test_api_server.py"
after = BASE / "postimage/test_api_server.py"
commands = {
    "ruff": [PYTHON, "-B", "-m", "ruff", "check", "--config", str(REPO / "pyproject.toml"), str(after)],
    "format": [PYTHON, "-B", "-m", "ruff", "format", "--check", "--config", str(REPO / "pyproject.toml"), str(after)],
    "type-before": [str(REPO / ".venv/bin/basedpyright"), "--project", str(REPO / "pyproject.toml"), "--pythonpath", PYTHON, "--outputjson", str(before)],
    "type-after": [str(REPO / ".venv/bin/basedpyright"), "--project", str(REPO / "pyproject.toml"), "--pythonpath", PYTHON, "--outputjson", str(after)],
}
checks = []
for name, command in commands.items():
    started = time.time()
    with (OUT / f"{name}.stdout.txt").open("xb") as stdout, (OUT / f"{name}.stderr.txt").open("xb") as stderr:
        result = subprocess.run(command, cwd=REPO, stdout=stdout, stderr=stderr, timeout=120)
    checks.append({"name": name, "command": command, "exit_code": result.returncode, "seconds": time.time() - started})
    (OUT / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(name, result.returncode, flush=True)
compile(after.read_bytes(), str(after), "exec")
(OUT / "compile.json").write_text(json.dumps({"path": str(after), "sha256": hashlib.sha256(after.read_bytes()).hexdigest(), "memory_compile": "PASS"}, indent=2) + "\n")
patch = "".join(difflib.unified_diff(before.read_text().splitlines(keepends=True), after.read_text().splitlines(keepends=True), fromfile="a/tests/test_api_server.py", tofile="b/tests/test_api_server.py"))
(BASE / "task-only.patch").write_text(patch)
replay = OUT / "replay"
(replay / "tests").mkdir(parents=True)
(replay / "tests/test_api_server.py").write_bytes(before.read_bytes())
subprocess.run(["git", "init", "-q", str(replay)], check=True, capture_output=True)
applied = subprocess.run(["git", "-C", str(replay), "apply", str(BASE / "task-only.patch")], capture_output=True, check=False)
equal = (replay / "tests/test_api_server.py").read_bytes() == after.read_bytes()
(OUT / "patch-replay.json").write_text(json.dumps({"command": ["git", "-C", str(replay), "apply", str(BASE / "task-only.patch")], "exit_code": applied.returncode, "stderr": applied.stderr.decode(), "byte_identical": equal}, indent=2) + "\n")
assert applied.returncode == 0 and equal
