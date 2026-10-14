import json
import os
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
OWNED = ("config.yaml", "tests/test_cli_smoke.py")
for name in ("result.json", "patch-reconstruction.json"):
    (BASE / ("initial-" + name)).write_bytes((BASE / name).read_bytes())
rebuilt = BASE / "reconstructed"
environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(BASE))
process = subprocess.run(["git", "apply", str(BASE / "task-only.patch")], cwd=rebuilt, env=environment, capture_output=True, check=False)
(BASE / "patch-apply.stdout.txt").write_bytes(process.stdout)
(BASE / "patch-apply.stderr.txt").write_bytes(process.stderr)
reconstruction = {path: (rebuilt / path).read_bytes() == (ROOT / path).read_bytes() for path in OWNED}
assert process.returncode == 0 and all(reconstruction.values()), reconstruction
(BASE / "patch-reconstruction.json").write_text(json.dumps(reconstruction, indent=2) + "\n")
result = json.loads((BASE / "result.json").read_text())
result["patch_reconstruction"] = reconstruction
result["limits"].append("Initial patch replay ran inside the parent Git checkout and applied no owned-path changes. Its false reconstruction results are retained in initial-result.json. Corrected replay stops Git parent discovery with GIT_CEILING_DIRECTORIES and verifies both bytes.")
(BASE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(reconstruction))
