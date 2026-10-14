# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run with root .venv/bin/python; applies only inside owned evidence reconstruction.
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

evidence = Path(__file__).resolve().parent / "candidate-v2"
reconstructed = evidence / "patch-reconstruction"
shutil.copytree(evidence / "source-preimage", reconstructed)
command = ["git", "apply", "--unsafe-paths", "--directory=" + str(reconstructed), str(evidence / "candidate.patch")]
result = subprocess.run(command, capture_output=True, check=False)
checks = json.loads((evidence / "checks.json").read_text())
observed = {name: hashlib.sha256((reconstructed / name).read_bytes()).hexdigest() for name in checks["source_after"] if (reconstructed / name).exists()}
receipt = {"argv": command, "exit_code": result.returncode, "stdout": result.stdout.decode(), "stderr": result.stderr.decode(), "sha256": observed, "byte_identical": observed == checks["source_after"]}
(evidence / "patch-reconstruction.json").write_text(json.dumps(receipt, indent=2))
raise SystemExit(0 if result.returncode == 0 and receipt["byte_identical"] else 1)
