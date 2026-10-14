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
ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OLD = Path(
    "/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4"
)
sys.path.insert(0, str(OLD))
from startup_probe.contract import SourcePlan, child_environment, verify_sources

raw = json.loads((OLD / "plan.json").read_bytes())
raw["candidate"] = str(ROOT)
raw["candidate_head"] = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
raw["source_hashes"] = {
    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((ROOT / "src").rglob("*.py"))
    if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts
}
with (BASE / "plan.json").open("x") as f:
    f.write(json.dumps(raw, indent=2) + "\n")
plan = SourcePlan.model_validate(raw)
verify_sources(plan)
out = BASE / "runtime"
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
    (out / name).mkdir()
(out / "config.yaml").write_text("{}\n")
(out / "empty.env").write_text("")
pin = secrets.token_hex(24)
(out / "auth-private/pin.txt").write_text(pin)
env = child_environment(os.environ, plan, out, pin)
argv = [str(plan.python), "-B", str(BASE / "browser_entry.py"), str(out), str(OLD)]
(out / "launch.json").write_text(
    json.dumps(
        {
            "argv": argv,
            "source_hashes": plan.source_hashes,
            "entry_sha256": hashlib.sha256((BASE / "browser_entry.py").read_bytes()).hexdigest(),
            "owned_runtime": str(out),
            "prior_prod_or_native_success_replayed": False,
        },
        indent=2,
    )
    + "\n"
)
receipt: dict[str, object] = {"pid": None, "exit_code": None, "reaped": False, "forced": False, "group_empty": False}
with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
    start = time.monotonic()
    proc = subprocess.Popen(argv, cwd=out, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
    receipt["pid"] = proc.pid
    try:
        receipt["exit_code"] = proc.wait(timeout=450)
        receipt["reaped"] = True
    except subprocess.TimeoutExpired:
        receipt["forced"] = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            try:
                receipt["exit_code"] = proc.wait(timeout=5)
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
        (out / "supervisor-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
