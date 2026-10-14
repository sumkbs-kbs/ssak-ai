from __future__ import annotations
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parent / "checks-attempt-2-static"
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
ORIGINAL = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4")
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

BASE.mkdir()
runtime = BASE / "runtime"
runtime.mkdir()
for name in ("auth-private", "tmp", "cache", "project_root", "models_dir", "data_dir", "documents_dir", "vectors_dir", "logs_dir", "wiki_dir"):
    (runtime / name).mkdir()
(runtime / "empty.env").write_text("")
pin = str(secrets.randbelow(1000000)).zfill(6)
(runtime / "auth-private/pin.txt").write_text(pin)
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / "plan.json").read_bytes()), runtime, pin)
env["PATH"] = "/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin"
env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + str(REPO)
env["UV_CACHE_DIR"] = str(runtime / "cache/uv")
env.pop("AGK_TEST_PYTHON", None)
files = ["scripts/run_dashboard_e2e_ambient.py", "scripts/commercial_ga_gates.json", "tests/test_cr14_ambient_backend_gate_contract.py"]
(BASE / "source-binding.json").write_text(json.dumps([{"path": f, "sha256": hashlib.sha256((REPO / f).read_bytes()).hexdigest()} for f in files], indent=2) + "\n")
python = str(REPO / ".venv/bin/python")
uv = ["uv", "run", "--isolated", "--frozen", "--extra", "dev", "--extra", "rag", "--extra", "documents"]
manifest = json.loads((REPO / "scripts/commercial_ga_gates.json").read_bytes())
commands = [
    ("contract", [python, "-B", "-m", "pytest", "-q", "tests/test_cr14_ambient_backend_gate_contract.py", "tests/test_cr14_browser_witness_gate_contract.py", "tests/test_cr14_f47_leftover_inventory_contract.py", "--basetemp", str(runtime / "pytest"), "--junitxml", str(BASE / "junit.xml")], 300),
    ("ruff", [str(REPO / ".venv/bin/ruff"), "check", files[0], files[2]], 120),
    ("format", [str(REPO / ".venv/bin/ruff"), "format", "--check", files[0], files[2]], 120),
    ("type", [str(REPO / ".venv/bin/basedpyright"), "--level", "error", files[0]], 180),
]
for gate_id in ():
    gate = next(row for row in manifest["gates"] if row["id"] == gate_id)
    commands.append((gate_id, gate["command"], 1200))
receipts = []
with socket.socket() as reserved:
    reserved.bind(("127.0.0.1", 0))
    env["AGK_MODEL_API_BASE"] = f"http://127.0.0.1:{reserved.getsockname()[1]}/v1"
    env["AGK_MODEL_API_ENGINE"] = "ollama"
    config = yaml.safe_load((REPO / "src/antigravity_k/config.yaml").read_text())
    for group in config.get("models", {}).values():
        for model in group:
            model["api_base"] = env["AGK_MODEL_API_BASE"]
    (runtime / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True))
    for name, command, timeout in commands:
        cwd = REPO / next((row.get("cwd", ".") for row in manifest["gates"] if row["id"] == name), ".")
        started = time.time()
        timed_out = False
        with (BASE / f"{name}.stdout.txt").open("xb") as stdout, (BASE / f"{name}.stderr.txt").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait(timeout=10)
        receipt = {"name": name, "command": command, "cwd": str(cwd), "exit_code": code, "timed_out": timed_out, "process_reaped": process.poll() is not None, "elapsed_seconds": time.time() - started, "source_binding": "source-binding.json"}
        receipts.append(receipt)
        (BASE / "checks.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)
        for stream in ("stdout", "stderr"):
            assert pin not in (BASE / f"{name}.{stream}.txt").read_text()
print(json.dumps({"failed_checks": [r["name"] for r in receipts if r["exit_code"] or r["timed_out"]]}), flush=True)
