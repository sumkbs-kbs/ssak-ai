#!/usr/bin/env python3
"""Record the real collector exit once through the controller's NX10_JUDGE hook."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
SOAK = BASE.parent.parent / "IMP20-CURRENT-CANDIDATE-SOAK-01/run-20261015T020000Z-codex/soak"
PYTHON = REPO / ".venv/bin/python"
COLLECTOR = REPO / "scripts/collect_soak_result.py"
HEAD = "58d941b340a29a8717dcfbc87348b8542fe0bd77"


def record(name, value, exclusive=False):
    path = SOAK / name
    target = path if exclusive else path.with_suffix(".tmp")
    with target.open("x" if exclusive else "w") as stream:
        json.dump({"recorded_at": datetime.now(UTC).isoformat(), **value}, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        target.replace(path)


def main():
    if sys.argv[1:] or Path.cwd() != REPO or any(os.environ.get(key) != str(SOAK) for key in ("NX10_SOAK_OUT", "NX10_SOAK_OUT_DIR", "NX10_OUT")):
        raise RuntimeError("collector proxy requires exact owned output/cwd and no arguments")
    plan = json.loads((SOAK / "execution-plan.json").read_bytes())
    digest = hashlib.sha256(COLLECTOR.read_bytes()).hexdigest()
    committed = subprocess.check_output(["git", "-C", str(REPO), "show", HEAD + ":scripts/collect_soak_result.py"], timeout=60)
    if plan["head"] != HEAD or plan["measurement_sources"]["scripts/collect_soak_result.py"] != digest or hashlib.sha256(committed).hexdigest() != digest:
        raise RuntimeError("collector source binding changed")
    command = [str(PYTHON), str(COLLECTOR)]
    binding = {"command": command, "cwd": str(REPO), "source_sha256": digest, "proxy_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    record("collector-claim.json", binding, exclusive=True)
    process = subprocess.Popen(command, cwd=REPO, env=dict(os.environ))
    record("collector-pid.json", {**binding, "pid": process.pid}, exclusive=True)
    actual = process.wait()
    propagated = actual if actual >= 0 else 128 - actual
    record("collector-receipt.json", {**binding, "pid": process.pid, "actual_exit": actual, "propagated_exit": propagated, "reaped": True})
    return propagated


if __name__ == "__main__":
    raise SystemExit(main())
