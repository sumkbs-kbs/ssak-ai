# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run using the root repository .venv/bin/python, with the candidate checkout as cwd.
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

evidence = Path(__file__).resolve().parent
script_root = evidence
if len(sys.argv) > 1:
    evidence = evidence / sys.argv[1]
    evidence.mkdir(exist_ok=False)
candidate = Path.cwd().resolve()
root = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
files = ("src/antigravity_k/api/routes/chat.py", "src/antigravity_k/engine/protocol_translator.py", "src/antigravity_k/engine/structured_output.py", "tests/test_chat_structured_output_contract.py", "pyproject.toml", "uv.lock", "tests/fixtures/vision_shapes_384x256.png.b64")
env = dict(os.environ, PYTHONPATH=str(candidate / "src"), PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", STRUCTURED_OUTPUT_CAPTURE_ROOT=str(evidence / "captures"), AGK_AUTO_DISCOVER_LOCAL_MODELS="false", AGK_ALLOWED_ROOTS=str(evidence / "isolated"), AGK_DATA_DIR=str(evidence / "isolated/data"))
source_before = {name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in files}
receipts = []
for name, command in (
    ("focused", [sys.executable, str(script_root / "cold_candidate.py"), str(evidence)]),
    ("lint", [str(root / ".venv/bin/ruff"), "check", *files[:4]]),
    ("format", [str(root / ".venv/bin/ruff"), "format", "--check", *files[:4]]),
    ("types", [str(root / ".venv/bin/basedpyright"), "--pythonpath", sys.executable, "--level", "error", *files[:4]]),
    ("compile", [sys.executable, "-c", "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]", *files[:4]]),
):
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    (evidence / (name + ".stdout")).write_bytes(result.stdout)
    (evidence / (name + ".stderr")).write_bytes(result.stderr)
    receipts.append({"name": name, "argv": command, "cwd": str(candidate), "exit_code": result.returncode, "stdout": name + ".stdout", "stderr": name + ".stderr"})
patch = []
for name in files:
    result = subprocess.run(["git", "show", "HEAD:" + name], capture_output=True, check=False)
    source = candidate / name
    before = evidence / "source-preimage" / name
    after = evidence / "source-postimage" / name
    after.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, after)
    if result.returncode == 0:
        before.parent.mkdir(parents=True, exist_ok=True)
        before.write_bytes(result.stdout)
    patch.extend(difflib.unified_diff(result.stdout.decode().splitlines(keepends=True) if result.returncode == 0 else [], source.read_text().splitlines(keepends=True), fromfile="a/" + name if result.returncode == 0 else "/dev/null", tofile="b/" + name))
source_after = {name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in files}
(evidence / "candidate.patch").write_text("".join(patch))
(evidence / "checks.json").write_text(json.dumps({"checks": receipts, "source_before": source_before, "source_after": source_after, "source_unchanged": source_before == source_after, "base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}, indent=2))
raise SystemExit(0 if source_before == source_after and all(row["exit_code"] == 0 for row in receipts) else 1)
