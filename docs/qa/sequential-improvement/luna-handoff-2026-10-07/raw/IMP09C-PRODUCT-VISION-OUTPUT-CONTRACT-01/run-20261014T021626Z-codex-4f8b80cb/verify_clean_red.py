# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run with the repository .venv/bin/python from the repository root.
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

run = Path(__file__).resolve().parent
root = Path.cwd()
destination = run / "clean-red"
destination.mkdir(exist_ok=False)
snapshot = destination / "snapshot"
shutil.copytree(root / "src", snapshot / "src", ignore=shutil.ignore_patterns("__pycache__"))
for name in ("src/antigravity_k/api/routes/chat.py", "src/antigravity_k/engine/protocol_translator.py"):
    shutil.copyfile(run / "source-preimage" / name, snapshot / name)
shutil.copyfile(root / "config.yaml", snapshot / "config.yaml")
if (root / "config").exists():
    shutil.copytree(root / "config", snapshot / "config")
command = [sys.executable, "-m", "pytest", "-c", "/dev/null", "--noconftest", str(root / "tests/test_chat_structured_output_contract.py"), "-k", "test_structured_image_reaches_native_wire_once", "-q", "--junitxml=" + str(destination / "junit.xml")]
env = dict(os.environ, PYTHONPATH=str(snapshot / "src"), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1", STRUCTURED_OUTPUT_CAPTURE_ROOT=str(destination / "captures"))
result = subprocess.run(command, env=env, capture_output=True, check=False)
(destination / "stdout.txt").write_bytes(result.stdout)
(destination / "stderr.txt").write_bytes(result.stderr)
(destination / "receipt.json").write_text(json.dumps({"argv": command, "exit_code": result.returncode, "pythonpath": env["PYTHONPATH"], "source_preimage": str(run / "source-preimage"), "scope": "two native wire formatting regressions only"}, indent=2))
raise SystemExit(result.returncode)
