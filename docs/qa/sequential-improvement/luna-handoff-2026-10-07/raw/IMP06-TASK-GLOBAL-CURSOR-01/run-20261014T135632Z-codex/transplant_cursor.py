from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
WT = Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
BASE = Path(__file__).resolve().parent
before = json.loads((BASE / "before.json").read_bytes())
owned = list(before["owned"]) + ["src/antigravity_k/api/routes/task_api.py", "tests/test_task_api.py"]
added = "tests/test_task_global_cursor_contract.py"
assert hashlib.sha256(subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=ROOT)).hexdigest() == before["staged_sha"]
for path in owned:
    if path in before["owned"]:
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == before["owned"][path], path
    else:
        prior = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=WT)
        assert (ROOT / path).read_bytes() == prior, path
        destination = BASE / "preimage" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(prior)
assert not (ROOT / added).exists()
for path in owned + [added]:
    shutil.copy2(WT / path, ROOT / path)
independent = {path: sha for path, sha in before["independent"].items() if path not in owned + [added]}
drift = [path for path, sha in independent.items() if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha]
assert not drift, drift
receipt = {"owned": owned + [added], "independent_checked": len(independent), "independent_drift": drift, "staged_unchanged": hashlib.sha256(subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=ROOT)).hexdigest() == before["staged_sha"]}
(BASE / "transplant.json").write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
