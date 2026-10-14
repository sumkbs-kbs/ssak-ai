# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run: .venv/bin/python verify.py <new attempt name>
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
target = base / sys.argv[1]
target.mkdir(exist_ok=False)
root = Path.cwd()
files = ["src/antigravity_k/engine/provider_adapters/inference_providers.py", "src/antigravity_k/engine/provider_adapters/transport_errors.py", "src/antigravity_k/api/routes/chat.py", "src/antigravity_k/api/routes/messages_api.py", "tests/test_native_stream_terminal_contract.py", "tests/test_inference_providers.py"]
env = dict(os.environ, PYTHONPATH=str(root / "src") + ":" + str(root), PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", TRANSPORT_CAPTURE_ROOT=str(target / "transport-captures"), STRUCTURED_OUTPUT_CAPTURE_ROOT=str(target / "route-captures"), AGK_AUTO_DISCOVER_LOCAL_MODELS="false", AGK_ALLOWED_ROOTS=str(target / "isolated"), AGK_DATA_DIR=str(target / "isolated/data"))
env["NATIVE_STREAM_CAPTURE_ROOT"] = str(target / "stream-captures")
before = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files}
for p in files:
    output = target / "source" / p
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / p, output)
receipts = []
for name, argv in [
    ("focused", [sys.executable, str(base / "cold_verify.py"), str(target)]),
    ("lint", [str(root / ".venv/bin/ruff"), "check", *files]),
    ("format", [str(root / ".venv/bin/ruff"), "format", "--check", *files]),
    ("types", [str(root / ".venv/bin/basedpyright"), "--pythonpath", sys.executable, "--level", "error", *files]),
    ("compile", [sys.executable, "-c", "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]", *files]),
]:
    result = subprocess.run(argv, env=env, capture_output=True, check=False)
    (target / (name + ".stdout")).write_bytes(result.stdout)
    (target / (name + ".stderr")).write_bytes(result.stderr)
    receipts.append({"name": name, "argv": argv, "exit_code": result.returncode, "cwd": str(root)})
after = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files}
(target / "checks.json").write_text(json.dumps({"checks": receipts, "source_before": before, "source_after": after, "stable": before == after}, indent=2))
print(json.dumps(receipts, indent=2))
raise SystemExit(0 if before == after and all(r["exit_code"] == 0 for r in receipts) else 1)
