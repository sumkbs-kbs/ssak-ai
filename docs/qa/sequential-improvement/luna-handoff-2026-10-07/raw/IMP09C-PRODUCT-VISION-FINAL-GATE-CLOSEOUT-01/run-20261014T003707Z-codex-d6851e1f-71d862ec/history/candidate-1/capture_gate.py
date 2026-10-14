# /// script
# requires-python = ">=3.11"
# ///
# Usage: python -B capture_gate.py prepare|gate
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

RUN = Path(__file__).resolve().parent
ROOT = next(parent for parent in RUN.parents if parent.name == "Ssak-Ai")
SOURCES = (
    "run_harness.py",
    "runtime_adapter.py",
    "run_offline_prechecks.py",
    "test_runtime_final_gate_contract.py",
    "test_runtime_bridge_contract.py",
    "test_runtime_compatibility_contract.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> dict[str, str]:
    return {name: digest(RUN / name) for name in SOURCES}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "gate"))
    mode = parser.parse_args().mode
    invocation = RUN / "launches" / f"{mode}-{uuid.uuid4().hex}"
    invocation.mkdir(parents=True, exist_ok=False)
    argv = (
        [sys.executable, "-B", str(RUN / "run_harness.py"), "--owned-prepare"]
        if mode == "prepare"
        else [sys.executable, "-B", str(RUN / "run_offline_prechecks.py")]
    )
    before = snapshot()
    binding_path = RUN / "execution-binding.json"
    binding_before = digest(binding_path) if binding_path.is_file() else None
    started = datetime.now(UTC).isoformat()
    start_monotonic = time.monotonic()
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(
            token in key.upper()
            for token in (
                "API_KEY",
                "ACCESS_TOKEN",
                "BEARER",
                "SECRET",
                "OLLAMA_HOST",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
            )
        )
    }
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONPATH=str(ROOT / "src"),
    )
    with (invocation / "stdout.txt").open("xb") as stdout, (invocation / "stderr.txt").open("xb") as stderr:
        process = subprocess.run(
            argv,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            check=False,
            timeout=1800,
        )
    receipt = {
        "mode": mode,
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": started,
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.monotonic() - start_monotonic,
        "exit_code": process.returncode,
        "source_sha256_before": before,
        "source_sha256_after": snapshot(),
        "execution_binding_sha256_before": binding_before,
        "execution_binding_sha256_after": digest(binding_path) if binding_path.is_file() else None,
        "launcher_sha256": digest(Path(__file__)),
        "stdout": {"path": "stdout.txt", "sha256": digest(invocation / "stdout.txt")},
        "stderr": {"path": "stderr.txt", "sha256": digest(invocation / "stderr.txt")},
    }
    with (invocation / "launch-receipt.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"launch": str(invocation.relative_to(RUN)), "exit_code": process.returncode}))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
