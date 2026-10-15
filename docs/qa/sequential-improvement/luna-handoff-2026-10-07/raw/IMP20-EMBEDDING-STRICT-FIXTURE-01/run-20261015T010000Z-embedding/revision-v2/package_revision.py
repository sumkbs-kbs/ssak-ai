# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: candidate/.venv/bin/python -B package_revision.py

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
PARENT = BASE.parent
REPO = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


original_manifest = json.loads((PARENT / "artifact-manifest.json").read_text())
for relative, row in original_manifest["files"].items():
    path = PARENT / relative
    assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
assert sha(PARENT / "artifact-manifest.json") == json.loads((PARENT / "final-artifact-check.json").read_text())["manifest_sha256"]
before = json.loads((PARENT / "static/type-before.stdout.txt").read_text())
after = json.loads((BASE / "static/type-after.stdout.txt").read_text())
old = Counter((d["severity"], d.get("rule"), d["message"]) for d in before["generalDiagnostics"])
new = Counter((d["severity"], d.get("rule"), d["message"]) for d in after["generalDiagnostics"])
assert old == new
receipt = json.loads((BASE / "green/receipt.json").read_text())
assert receipt["exit_code"] == 0
assert sha(REPO / "tests/test_api_server.py") == sha(BASE / "postimage/test_api_server.py") == receipt["source_sha256"]["owned_test"]
for relative, expected in receipt["source_sha256"].items():
    if relative != "owned_test":
        assert sha(REPO / relative) == expected
observations = json.loads((BASE / "green/observations.json").read_text())
assert observations["counts"] == {"network_attempts": 0, "listen_attempts": 0, "process_attempts": 0}
assert [r["status"] for r in observations["responses"]] == [503, 503, 503, 503, 200]
junit = ET.parse(BASE / "green/junit.xml").getroot()
assert len(junit.findall(".//testcase")) == 5
assert not any(junit.findall(f".//{tag}") for tag in ("failure", "error", "skipped"))
replay = json.loads((BASE / "static/patch-replay.json").read_text())
assert replay["exit_code"] == 0 and replay["byte_identical"]
result = {
    "status": "COMPLETE_OFFLINE_REVISION_V2",
    "integration_path": str(REPO / "tests/test_api_server.py"),
    "source_sha256": receipt["source_sha256"],
    "tests": {"passed": 5, "failed": 0, "errors": 0, "skipped": 0},
    "network_guard": observations["counts"],
    "asgi_posts": 5,
    "type_errors": 4,
    "type_warnings": 156,
    "type_diagnostic_multiset_matches_original_baseline": True,
    "new_type_errors": 0,
    "new_type_warnings": 0,
    "preserved_original_artifacts": len(original_manifest["files"]),
    "original_manifest_sha256": sha(PARENT / "artifact-manifest.json"),
    "patch_preimage_sha256": sha(BASE / "preimage/test_api_server.py"),
    "patch_postimage_sha256": sha(BASE / "postimage/test_api_server.py"),
    "patch_replay": "PASS_BYTE_IDENTICAL",
    "live_inference": "NOT_RUN",
    "lifespan": "DISABLED_OFFLINE_SCOPE",
    "commit": "NOT_PERFORMED",
}
(BASE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
files = {}
for path in sorted(BASE.rglob("*")):
    relative = path.relative_to(BASE)
    if not path.is_file() or any(part in {"runtime", ".git", "__pycache__", ".pytest_cache"} for part in relative.parts):
        continue
    if path.name in {"artifact-manifest.json", "final-artifact-check.json"}:
        continue
    files[str(relative)] = {"bytes": path.stat().st_size, "sha256": sha(path)}
(BASE / "artifact-manifest.json").write_text(json.dumps({"files": files}, indent=2) + "\n")
assert all((BASE / p).stat().st_size == row["bytes"] and sha(BASE / p) == row["sha256"] for p, row in files.items())
(BASE / "final-artifact-check.json").write_text(json.dumps({"files_checked": len(files), "mismatches": [], "manifest_sha256": sha(BASE / "artifact-manifest.json")}, indent=2) + "\n")
print(json.dumps({"files": len(files), "tests": 5, "source": result["patch_postimage_sha256"], "baseline_diagnostics_equal": True}))
