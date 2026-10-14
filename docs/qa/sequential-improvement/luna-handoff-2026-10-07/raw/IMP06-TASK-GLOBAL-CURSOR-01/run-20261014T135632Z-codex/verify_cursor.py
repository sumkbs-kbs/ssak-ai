from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
repo = Path(sys.argv[1]).resolve()
label = sys.argv[2]
out = BASE / label
out.mkdir(exist_ok=False)
files = [
    "src/antigravity_k/api/task_models.py",
    "src/antigravity_k/api/routes/task_api.py",
    "tests/test_task_api.py",
    "tests/test_task_global_cursor_contract.py",
    *[str(p.relative_to(repo)) for p in (repo / "dashboard/src/features/task-execution").glob("*.ts")],
]
sources = {p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in files}
environment = dict(os.environ, PYTHONPATH=str(repo / "src") + os.pathsep + str(repo), PYTHONDONTWRITEBYTECODE="1")
tools_root = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin")
python = str(tools_root / "python")
dashboard = repo / "dashboard"
configuration = out / "basedpyright.json"
configuration.write_text(json.dumps({"extends": str(repo / "pyproject.toml"), "extraPaths": [str(repo / "src")], "pythonVersion": "3.13"}))
checks = [
    ("dashboard-tests", ["pnpm", "exec", "vitest", "run", "src/features/task-execution", "--reporter=json", "--outputFile=" + str(out / "vitest.json")], dashboard),
    ("dashboard-types", ["pnpm", "exec", "tsc", "--noEmit", "--incremental", "false", "--project", "tsconfig.json"], dashboard),
    ("python-tests", [python, "-m", "pytest", "-q", "tests/test_task_api.py", "tests/test_task_global_cursor_contract.py", "--junitxml=" + str(out / "junit.xml")], repo),
    ("ruff", [str(tools_root / "ruff"), "check", *files[:4]], repo),
    ("format", [str(tools_root / "ruff"), "format", "--check", *files[:4]], repo),
    ("python-types", [str(tools_root / "basedpyright"), "--project", str(configuration), "--level", "error", *files[:2]], repo),
]
receipts = []
for name, command, cwd in checks:
    started = time.time()
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, timeout=180, check=False)
    (out / (name + ".stdout.txt")).write_bytes(result.stdout)
    (out / (name + ".stderr.txt")).write_bytes(result.stderr)
    receipt = {"name": name, "command": command, "cwd": str(cwd), "exit_code": result.returncode, "started": started, "elapsed": time.time() - started}
    receipts.append(receipt)
    (out / "checks.json").write_text(json.dumps({"source_sha256": sources, "checks": receipts}, indent=2))
    print(json.dumps(receipt), flush=True)
raise SystemExit(any(item["exit_code"] for item in receipts))
