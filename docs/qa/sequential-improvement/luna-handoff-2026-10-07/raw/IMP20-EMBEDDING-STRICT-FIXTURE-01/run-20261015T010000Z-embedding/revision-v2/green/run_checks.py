# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "pydantic"]
# ///
# Run: candidate/.venv/bin/python -B run_checks.py red|green
"""Launch an owned isolated test phase and preserve its execution receipt."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
ORIGINAL = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4")
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

phase = sys.argv[1]
out = BASE / phase
out.mkdir()
runtime = out / "runtime"
runtime.mkdir()
for name in ("auth-private", "tmp", "cache", "project_root", "models_dir", "data_dir", "documents_dir", "vectors_dir", "logs_dir", "wiki_dir"):
    (runtime / name).mkdir()
(runtime / "empty.env").write_text("")
(runtime / "config.yaml").write_text("{}\n")
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / "plan.json").read_bytes()), runtime, "123456")
env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + str(REPO)
env["TMPDIR"] = str(runtime / "tmp")
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
env["HF_HUB_OFFLINE"] = "1"
env["TRANSFORMERS_OFFLINE"] = "1"
env.pop("AGK_TEST_PYTHON", None)
command = [str(REPO / ".venv/bin/python"), "-B", str(BASE / "guarded_pytest.py"), phase]
files = ["tests/test_api_server.py", "tests/test_embeddings_model_contract.py", "src/antigravity_k/engine/embeddings.py", "src/antigravity_k/api/routes/models_api.py"]
binding = {path: hashlib.sha256((REPO / path).read_bytes()).hexdigest() for path in files}
binding["owned_test"] = hashlib.sha256((BASE / ("preimage" if phase.startswith("red") else "postimage") / "test_api_server.py").read_bytes()).hexdigest()
for name in ("guarded_pytest.py", "run_checks.py"):
    (out / name).write_bytes((BASE / name).read_bytes())
started = time.time()
with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
    result = subprocess.run(command, cwd=runtime, env=env, stdout=stdout, stderr=stderr, timeout=180)
receipt = {"command": command, "cwd": str(runtime), "exit_code": result.returncode, "elapsed_seconds": time.time() - started, "source_sha256": binding}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
