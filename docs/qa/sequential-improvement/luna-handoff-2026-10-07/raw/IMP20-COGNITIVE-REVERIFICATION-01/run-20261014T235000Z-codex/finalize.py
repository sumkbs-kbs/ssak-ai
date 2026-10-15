from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

RUN: Final = Path(__file__).resolve().parent
REPO: Final = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
PYTHON: Final = "/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python"
commands = [
    ("lint", [PYTHON, "-m", "ruff", "check", str(RUN / "verify.py"), str(RUN / "finalize.py")]),
    ("format", [PYTHON, "-m", "ruff", "format", "--check", str(RUN / "verify.py"), str(RUN / "finalize.py")]),
    (
        "diff",
        [
            "git",
            "diff",
            "--check",
            "--",
            "docs/ssak-ai-core/evidence/digest_reverification.json",
            "docs/ssak-ai-core/evidence/digest_drift.json",
        ],
    ),
]
checks = []
for name, argv in commands:
    result = subprocess.run(argv, cwd=REPO, capture_output=True, check=False)
    (RUN / ("final-" + name + ".stdout.txt")).write_bytes(result.stdout)
    (RUN / ("final-" + name + ".stderr.txt")).write_bytes(result.stderr)
    checks.append({"name": name, "command": argv, "exit_code": result.returncode})
    assert result.returncode == 0, name
for name in ["verify.py", "finalize.py"]:
    compile((RUN / name).read_bytes(), name, "exec")
checks.append({"name": "memory_compile", "files": ["verify.py", "finalize.py"], "exit_code": 0})
(RUN / "final-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
cases = ET.parse(RUN / "junit-attempt-2.xml").findall(".//testcase")
assert len(cases) == 145
assert not any(
    c.find("failure") is not None or c.find("error") is not None or c.find("skipped") is not None for c in cases
)
drift = json.loads((REPO / "docs/ssak-ai-core/evidence/digest_drift.json").read_text())
baseline = json.loads((RUN / "before-drift.stdout.txt").read_text())
result = {
    "status": "COMPLETE_SCOPED_REGISTRY_REVERIFICATION",
    "independent_review": "PENDING",
    "candidate": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
    "pytest": {"passed": len(cases), "failed": 0, "errors": 0, "skipped": 0},
    "before_counts": baseline["counts"],
    "after_counts": drift["counts"],
    "changed_registry_rows": 1,
    "changed_product_or_test_files": 0,
    "historical_T12_doc_test_row_and_pin": "PRESERVED",
    "prior_evidence": "prior-evidence-validation.json",
    "scope": "scope-verification.json",
    "initial_attempt": "145 setup errors from absent basetemp parent; source and logs preserved; fixed helper setup and reran full selector",
    "initial_static_check": "Ruff lint passed; format check failed, then helper formatted. Initial command output observed in session; not separately captured as raw file.",
    "limits": [
        "Prior migration test execution bytes not separately pinned by old receipt",
        "No historical live/model/56961-row migration renewal",
        "No full23 gates or GA approval; no commit/push by worker",
    ],
}
(RUN / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
rows = []
for path in sorted(RUN.rglob("*")):
    if path.is_file() and "private-runtime" not in path.parts and path.name != "artifact-manifest.json":
        data = path.read_bytes()
        rows.append(
            {"path": path.relative_to(RUN).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
(RUN / "artifact-manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
print(json.dumps({"status": result["status"], "tests": len(cases), "files": len(rows), "counts": drift["counts"]}))
