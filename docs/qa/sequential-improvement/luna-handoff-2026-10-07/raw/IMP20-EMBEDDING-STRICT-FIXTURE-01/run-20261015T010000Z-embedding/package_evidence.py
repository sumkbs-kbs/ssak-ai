# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: candidate/.venv/bin/python -B package_evidence.py
"""Validate preserved results and publish a bounded evidence inventory."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


red = json.loads((BASE / "red-2/receipt.json").read_text())
green = json.loads((BASE / "green/receipt.json").read_text())
before = json.loads((BASE / "static/type-before.stdout.txt").read_text())
after = json.loads((BASE / "static/type-after.stdout.txt").read_text())
errors_before = [(d["range"], d["message"]) for d in before["generalDiagnostics"] if d["severity"] == "error"]
errors_after = [(d["range"], d["message"]) for d in after["generalDiagnostics"] if d["severity"] == "error"]
assert errors_before == errors_after and len(errors_after) == 4
binding = {path: {"expected": sha, "current": digest(REPO / path)} for path, sha in green["source_sha256"].items() if path != "owned_test"}
assert all(row["expected"] == row["current"] for row in binding.values())
assert digest(BASE / "preimage/test_api_server.py") == binding["tests/test_api_server.py"]["expected"]
assert digest(BASE / "postimage/test_api_server.py") == green["source_sha256"]["owned_test"]
junit = ET.parse(BASE / "green/junit.xml").getroot()
assert len(junit.findall(".//testcase")) == 5
assert not junit.findall(".//failure") and not junit.findall(".//error") and not junit.findall(".//skipped")
observations = json.loads((BASE / "green/observations.json").read_text())
assert observations["counts"] == {"network_attempts": 0, "listen_attempts": 0, "process_attempts": 0}
assert [r["status"] for r in observations["responses"]] == [503, 503, 503, 503, 200]
result = {
    "status": "PREPARED_OFFLINE_SCOPED",
    "integration": "PENDING_PARENT_FULL_GATE_COMPLETION",
    "candidate_head": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
    "red_exit": red["exit_code"], "green_exit": green["exit_code"], "green_tests": 5,
    "source_preservation": binding,
    "type_errors_before": len(errors_before), "type_errors_after": len(errors_after),
    "type_errors_unchanged": True,
    "warnings_before": before["summary"]["warningCount"], "warnings_after": after["summary"]["warningCount"],
    "network_guard": observations["counts"],
    "lifespan": "DISABLED_FOR_OFFLINE_SCOPE", "real_inference": "NOT_RUN",
    "changed_target": "tests/test_api_server.py",
    "patch": "task-only.patch", "handoff": "handoff-ko.md",
}
(BASE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
files = {}
for path in sorted(BASE.rglob("*")):
    relative = path.relative_to(BASE)
    if not path.is_file() or any(part in {"runtime", ".git", "__pycache__", ".pytest_cache"} for part in relative.parts):
        continue
    if path.name in {"artifact-manifest.json", "final-artifact-check.json"}:
        continue
    files[str(relative)] = {"bytes": path.stat().st_size, "sha256": digest(path)}
(BASE / "artifact-manifest.json").write_text(json.dumps({"files": files}, indent=2) + "\n")
assert all((BASE / p).stat().st_size == row["bytes"] and digest(BASE / p) == row["sha256"] for p, row in files.items())
(BASE / "final-artifact-check.json").write_text(json.dumps({"files_checked": len(files), "mismatches": [], "manifest_sha256": digest(BASE / "artifact-manifest.json")}, indent=2) + "\n")
print(json.dumps({"files": len(files), "tests": 5, "new_type_errors": 0, "candidate": result["candidate_head"]}))
