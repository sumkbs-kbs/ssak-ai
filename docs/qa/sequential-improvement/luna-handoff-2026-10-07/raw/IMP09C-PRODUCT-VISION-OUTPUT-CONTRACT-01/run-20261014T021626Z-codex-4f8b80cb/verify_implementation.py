# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run with the repository .venv/bin/python from the repository root.
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
ROOT = Path.cwd()
FILES = ("src/antigravity_k/api/routes/chat.py", "src/antigravity_k/engine/protocol_translator.py", "src/antigravity_k/engine/structured_output.py", "tests/test_chat_structured_output_contract.py", "pyproject.toml", "uv.lock")
target = RUN / (sys.argv[1] if len(sys.argv) > 1 else "implementation-checks")
target.mkdir(exist_ok=False)
env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"), STRUCTURED_OUTPUT_CAPTURE_ROOT=str(target / "captures"))
receipts = []
for name, command in (
    ("focused", [sys.executable, "-m", "pytest", "tests/test_chat_structured_output_contract.py", "-q", "--junitxml=" + str(target / "junit.xml")]),
    ("lint", [str(ROOT / ".venv/bin/ruff"), "check", *FILES[:4]]),
    ("format", [str(ROOT / ".venv/bin/ruff"), "format", "--check", *FILES[:4]]),
    ("types", [str(ROOT / ".venv/bin/basedpyright"), "--level", "error", *FILES[:3]]),
    ("compile", [sys.executable, "-c", "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]", *FILES[:4]]),
):
    completed = subprocess.run(command, env=env, capture_output=True, check=False)
    (target / (name + ".stdout")).write_bytes(completed.stdout)
    (target / (name + ".stderr")).write_bytes(completed.stderr)
    receipts.append({"scenario": name, "argv": command, "exit_code": completed.returncode, "stdout": str(target / (name + ".stdout")), "stderr": str(target / (name + ".stderr"))})
patch = []
hashes = {}
for name in FILES:
    source = ROOT / name
    before = RUN / "source-preimage" / name
    after = target / "source-postimage" / name
    after.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, after)
    hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    patch.extend(difflib.unified_diff(before.read_text().splitlines(keepends=True) if before.exists() else [], source.read_text().splitlines(keepends=True), fromfile="a/" + name if before.exists() else "/dev/null", tofile="b/" + name))
(RUN / "task-only.patch").write_text("".join(patch))
(target / "checks.json").write_text(json.dumps({"checks": receipts, "source_sha256": hashes, "actual_network_or_inference": 0}, indent=2) + "\n")
raise SystemExit(0 if all(row["exit_code"] == 0 for row in receipts) else 1)
