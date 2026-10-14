from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
ROOT = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
CONTRACT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4")
sys.path.insert(0, str(CONTRACT))
from startup_probe.contract import SourcePlan, child_environment

SELECTORS = {
    "runtime": ["tests/test_cli_smoke.py", "tests/test_project_registry_atomic.py", "tests/test_secure_key.py::TestCliKeyRotateE2E::test_kdf_migration_v1_to_v2_via_cli", "tests/test_model_registry.py::test_bundled_default_config_matches_repository_default", "tests/test_model_manager_lifecycle.py::TestTargetResolution", "tests/test_local_model_discovery.py"],
    "api": ["tests/test_e2e_smoke.py"],
}


def main() -> None:
    phase = sys.argv[1]
    owned = BASE / phase
    owned.mkdir()
    runtime = owned / "private-runtime"
    runtime.mkdir(mode=0o700)
    for name in ("auth-private", "tmp", "cache", "project_root", "models_dir", "data_dir", "documents_dir", "vectors_dir", "logs_dir", "wiki_dir"):
        (runtime / name).mkdir()
    trace = owned / "trace"
    trace.mkdir()
    (runtime / "empty.env").write_text("")
    pin = str(secrets.randbelow(1000000)).zfill(6)
    env = child_environment(os.environ, SourcePlan.model_validate_json((CONTRACT / "plan.json").read_bytes()), runtime, pin)
    env["PATH"] = "/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin"
    env["PYTHONPATH"] = os.pathsep.join((str(BASE), str(ROOT / "src"), str(ROOT)))
    env["RECHECK_TRACE_DIR"] = str(trace)
    env["RECHECK_ALLOW_SERVER"] = "1" if phase == "api" else "0"
    env["AGK_AUTO_DISCOVER_LOCAL_MODELS"] = "true"
    env["AGK_VAULT_DIR"] = str(runtime / "vault-private")
    env["AGK_LOCAL_MODEL_DIRS"] = str(runtime / "models_dir")
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        endpoint = f"http://127.0.0.1:{reserved.getsockname()[1]}"
        for key in ("AGK_MODEL_API_BASE", "AGK_OLLAMA_API_BASE", "AGK_LMSTUDIO_API_BASE", "AGK_LLAMA_CPP_API_BASE"):
            env[key] = endpoint + ("" if key == "AGK_OLLAMA_API_BASE" else "/v1")
        config = yaml.safe_load((ROOT / "src/antigravity_k/config.yaml").read_text())
        for group in config.get("models", {}).values():
            for model in group:
                model["api_base"] = endpoint + "/v1"
        (runtime / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True))
        paths = {value.split("::")[0] for value in SELECTORS[phase]}
        paths.update(("tests/conftest.py", "tests/_cli_subprocess.py", "src/antigravity_k/engine/model_registry.py", "src/antigravity_k/engine/model_manager.py", "src/antigravity_k/engine/local_model_discovery.py", "src/antigravity_k/config.yaml", "config.yaml", "pyproject.toml", "uv.lock"))
        binding = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(paths)}
        (owned / "source-binding.json").write_text(json.dumps(binding, indent=2) + "\n")
        command = [str(ROOT / ".venv/bin/python"), "-B", "-m", "pytest", "-q", *SELECTORS[phase], "--basetemp", str(runtime / "pytest"), "--junitxml", str(owned / "junit.xml")]
        (owned / "launch.json").write_text(json.dumps({"command": command, "cwd": str(ROOT), "discovery_enabled": True, "provider_endpoint_non_listening": endpoint, "private_runtime_excluded_from_publication": True}, indent=2) + "\n")
        started = time.monotonic()
        with (owned / "stdout.txt").open("xb") as out, (owned / "stderr.txt").open("xb") as err:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=err, timeout=240, check=False)
        (owned / "receipt.json").write_text(json.dumps({"exit_code": result.returncode, "duration_seconds": time.monotonic() - started, "source_unchanged": all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest for path, digest in binding.items())}, indent=2) + "\n")
        print(f"{phase}: {result.returncode}")


if __name__ == "__main__":
    main()
