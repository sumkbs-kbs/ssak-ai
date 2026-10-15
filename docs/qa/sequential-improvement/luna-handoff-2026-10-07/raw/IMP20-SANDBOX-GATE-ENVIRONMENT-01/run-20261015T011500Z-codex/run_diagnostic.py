import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
RAW = BASE.parents[1]
ORIGINAL = RAW / "IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4"
PROFILE = RAW / "IMP20-FRESH-FULL-GATES-02/run-20261015T001700Z-codex/provider-boundary.sb"
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

PATHS = [
    "tests/test_cr03_sandbox_read_boundary.py",
    "tests/test_cr04_shell_api_boundary.py",
    "tests/conftest.py",
    "src/antigravity_k/engine/sandbox.py",
    "src/antigravity_k/api/routes/agent_tools.py",
]


def binding():
    return {path: hashlib.sha256((REPO / path).read_bytes()).hexdigest() for path in PATHS}


before = binding()
(BASE / "source-binding.json").write_text(json.dumps({
    "repo": str(REPO),
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
    "sources": before,
    "profile": str(PROFILE),
    "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
}, indent=2) + "\n")
rows = []
for mode in ("with-artificial-outer-profile", "product-sandbox-only"):
    output = BASE / mode
    output.mkdir()
    owned = output / "private-runtime"
    owned.mkdir()
    for name in ("auth-private", "tmp", "cache", "project_root", "models_dir", "data_dir", "documents_dir", "vectors_dir", "logs_dir", "wiki_dir"):
        (owned / name).mkdir()
    (owned / "empty.env").write_text("")
    plan = SourcePlan.model_validate_json((ORIGINAL / "plan.json").read_bytes()).model_copy(update={"candidate": REPO})
    env = child_environment(os.environ, plan, owned, "diagnostic-owned-pin")
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + str(REPO)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    command = [str(REPO / ".venv/bin/python"), "-B", str(BASE / "pytest_entry.py"), str(output)]
    if mode == "with-artificial-outer-profile":
        command = ["/usr/bin/sandbox-exec", "-f", str(PROFILE), *command]
    started = datetime.now(timezone.utc).isoformat()
    with (output / "stdout.txt").open("xb") as stdout, (output / "stderr.txt").open("xb") as stderr:
        completed = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=180)
    row = {"mode": mode, "command": command, "cwd": str(REPO), "started": started, "finished": datetime.now(timezone.utc).isoformat(), "exit_code": completed.returncode, "product_sandbox_enabled": True, "source_binding_unchanged": binding() == before}
    (output / "receipt.json").write_text(json.dumps(row, indent=2) + "\n")
    rows.append(row)
    print(json.dumps(row), flush=True)
(BASE / "comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
assert binding() == before
