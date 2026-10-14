from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CANDIDATE = Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
OLD_PROBE = Path(
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4"
)
sys.path.insert(0, str(OLD_PROBE))
from startup_probe.contract import SourcePlan, child_environment, verify_sources

plan = SourcePlan.model_validate_json((OLD_PROBE / "plan.json").read_bytes())
verify_sources(plan)
out = BASE / sys.argv[1]
out.mkdir(mode=0o700)
for name in (
    "auth-private",
    "tmp",
    "cache",
    "project_root",
    "models_dir",
    "data_dir",
    "documents_dir",
    "vectors_dir",
    "logs_dir",
    "wiki_dir",
):
    (out / name).mkdir(mode=0o700)
(out / "config.yaml").write_text("{}\n")
(out / "empty.env").write_text("")
env = child_environment(os.environ, plan, out, secrets.token_hex(24))
env["PYTHONPATH"] = str(CANDIDATE / "src")
argv = [str(plan.python), "-B", str(BASE / "probe.py"), str(out), str(OLD_PROBE)]
binding = {
    "head": subprocess.check_output(["git", "-C", str(CANDIDATE), "rev-parse", "HEAD"], text=True).strip(),
    "source_hashes": plan.source_hashes,
    "harness_sha": {
        name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
        for name in ("probe.py", "supervise.py", "acceptance.md")
    },
    "guard_sha": hashlib.sha256((OLD_PROBE / "startup_probe/guard.py").read_bytes()).hexdigest(),
    "argv": argv,
    "socket_budget": 0,
    "authorized_purge_budget": 1,
}
(out / "source-freeze.json").write_text(json.dumps(binding, indent=2) + "\n")
receipt: dict[str, object] = {
    "classification": "NOT_OBSERVED",
    "pid": None,
    "exit_code": None,
    "reaped": False,
    "forced": False,
    "cleanup_errors": [],
}
start = time.monotonic()
with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
    proc = subprocess.Popen(argv, cwd=out, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
    receipt["pid"] = proc.pid
    try:
        receipt["exit_code"] = proc.wait(timeout=60)
        receipt["reaped"] = True
    except subprocess.TimeoutExpired:
        receipt["forced"] = True
        deadline = time.monotonic() + 10
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            try:
                receipt["exit_code"] = proc.wait(timeout=min(3, max(0.01, deadline - time.monotonic())))
                receipt["reaped"] = True
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        try:
            os.killpg(proc.pid, 0)
            receipt["group_empty"] = False
        except ProcessLookupError:
            receipt["group_empty"] = True
        receipt["elapsed_sec"] = time.monotonic() - start
        receipt["classification"] = "EXIT_OBSERVED"
        (out / "supervisor-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
