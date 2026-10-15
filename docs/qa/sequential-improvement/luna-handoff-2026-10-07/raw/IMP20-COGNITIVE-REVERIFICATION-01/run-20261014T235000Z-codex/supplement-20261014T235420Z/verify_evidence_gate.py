from __future__ import annotations

import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

RUN: Final = Path(__file__).resolve().parent
PARENT: Final = RUN.parent
REPO: Final = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
PYTHON: Final = "/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


expected = json.loads((PARENT / "final-binding.json").read_text())
assert expected == {name: digest(REPO / name) for name in expected}
prior_manifest = json.loads((PARENT / "artifact-manifest.json").read_text())
prior = {row["path"]: digest(PARENT / row["path"]) for row in prior_manifest}
assert prior == {row["path"]: row["sha256"] for row in prior_manifest}
prior["artifact-manifest.json"] = digest(PARENT / "artifact-manifest.json")
names = list(expected) + ["tests/cognitive/test_evidence_gate.py", "scripts/evidence_gate.py"]
binding = {name: digest(REPO / name) for name in names}
(RUN / "source-before.json").write_text(json.dumps(binding, indent=2) + "\n")
(RUN / "private-runtime").mkdir()
argv = [
    PYTHON,
    "-B",
    "-m",
    "pytest",
    "-q",
    "tests/cognitive/test_evidence_gate.py",
    "--basetemp",
    str(RUN / "private-runtime/pytest"),
    "--junitxml",
    str(RUN / "junit.xml"),
]
env = dict(os.environ, PYTHONPATH=str(REPO / "src") + ":" + str(REPO), PYTHONDONTWRITEBYTECODE="1")
with (RUN / "pytest.stdout.txt").open("xb") as stdout, (RUN / "pytest.stderr.txt").open("xb") as stderr:
    result = subprocess.run(argv, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=600, check=False)
(RUN / "checks.json").write_text(
    json.dumps(
        {"argv": argv, "cwd": str(REPO), "exit_code": result.returncode, "source_binding": "source-before.json"},
        indent=2,
    )
    + "\n"
)
current = {name: digest(REPO / name) for name in names}
(RUN / "source-after.json").write_text(json.dumps(current, indent=2) + "\n")
assert current == binding
assert prior == {name: digest(PARENT / name) for name in prior}
cases = ET.parse(RUN / "junit.xml").findall(".//testcase")
failed = sum(c.find("failure") is not None for c in cases)
errors = sum(c.find("error") is not None for c in cases)
skipped = sum(c.find("skipped") is not None for c in cases)
(RUN / "result.json").write_text(
    json.dumps(
        {
            "status": "PASS_SCOPED" if result.returncode == 0 else "FAIL",
            "total": len(cases),
            "passed": len(cases) - failed - errors - skipped,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "prior_145_tests_repeated": False,
            "original_artifacts_unchanged": len(prior),
            "source_bindings_unchanged": len(binding),
            "product_test_edits": 0,
            "scope": "Only tests/cognitive/test_evidence_gate.py; no historical or full23 claim",
        },
        indent=2,
    )
    + "\n"
)
rows = []
for path in sorted(RUN.rglob("*")):
    if path.is_file() and "private-runtime" not in path.parts and path.name != "artifact-manifest.json":
        rows.append({"path": path.relative_to(RUN).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
(RUN / "artifact-manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
print(
    json.dumps(
        {
            "exit_code": result.returncode,
            "tests": len(cases),
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "prior_artifacts_preserved": len(prior),
        }
    )
)
raise SystemExit(result.returncode)
