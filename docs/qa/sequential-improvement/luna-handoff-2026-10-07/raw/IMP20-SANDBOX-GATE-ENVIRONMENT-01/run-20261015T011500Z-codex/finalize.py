import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
FORMAL_REPO = Path("/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai")
REPORT = BASE.parents[1] / "IMP20-FRESH-FULL-GATES-02/run-20261015T001700Z-codex/gate-report.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


bound = json.loads((BASE / "source-binding.json").read_bytes())
assert all(sha(REPO / path) == digest for path, digest in bound["sources"].items())
sources_match_formal = {path: sha(FORMAL_REPO / path) == digest for path, digest in bound["sources"].items()}
report_bytes = REPORT.read_bytes()
report = json.loads(report_bytes)
gate = next(g for g in report["gates"] if g["id"] == "python-tests")
failure_lines = [line for line in gate["stdout"].splitlines() if "test_cr0" in line and "FAILED" in line]
snapshot = {
    "report_path": str(REPORT),
    "report_sha_at_read": hashlib.sha256(report_bytes).hexdigest(),
    "python_gate_status": gate["status"],
    "python_gate_exit": gate["exit_code"],
    "failure_lines": failure_lines,
    "cr03_failed_lines": sum("test_cr03" in line for line in failure_lines),
    "cr04_failed_lines": sum("test_cr04" in line for line in failure_lines),
    "limitations": "Interrupted formal report has progress failures, not individual failure tracebacks. CR04 attribution remains static rather than dynamically reproduced.",
}
(BASE / "formal-failure-extract.json").write_text(json.dumps(snapshot, indent=2) + "\n")
scenarios = []
for mode in ("with-artificial-outer-profile", "product-sandbox-only"):
    output = BASE / mode
    suite = ET.parse(output / "junit.xml").getroot().find("testsuite")
    assert suite is not None
    audit = json.loads((output / "audit.json").read_bytes())
    receipt = json.loads((output / "receipt.json").read_bytes())
    scenarios.append({
        "mode": mode,
        "tests": int(suite.attrib["tests"]),
        "failures": int(suite.attrib["failures"]),
        "errors": int(suite.attrib["errors"]),
        "skipped": int(suite.attrib["skipped"]),
        "exit_code": receipt["exit_code"],
        "socket_connect_or_bind_events": sum(item["event"] in {"socket.connect", "socket.bind"} for item in audit),
        "product_sandbox_exec_calls": sum(item.get("executable") == "sandbox-exec" for item in audit),
        "junit": str(output / "junit.xml"),
        "receipt": str(output / "receipt.json"),
        "audit": str(output / "audit.json"),
    })
assert scenarios[0]["failures"] == 1 and scenarios[0]["exit_code"] == 1
assert scenarios[1]["failures"] == 0 and scenarios[1]["exit_code"] == 0
assert all(row["tests"] == 1 and row["errors"] == 0 and row["skipped"] == 0 for row in scenarios)
assert all(row["socket_connect_or_bind_events"] == 0 and row["product_sandbox_exec_calls"] == 1 for row in scenarios)
result = {
    "verdict": "CONFIRMED_SCOPED_OUTER_SEATBELT_INTERFERENCE",
    "scenarios": scenarios,
    "source_binding_unchanged": True,
    "diagnostic_sources_match_formal_checkout": sources_match_formal,
    "mechanism": "Product mandatory sandbox-exec exits 71 with sandbox_apply Operation not permitted only under the artificial outer Seatbelt layer; the same reviewed print-only test passes with the product sandbox retained and no artificial outer profile.",
    "not_claimed": ["All CR03 or CR04 cases pass", "UV isolated interpreter is verified", "Formal Python gate passes", "Full 23 gate pass", "A replacement full-suite safety boundary was implemented"],
    "known_warning": "asyncio_mode unknown because diagnostic disables plugin autoload; one warning per run",
    "process_limit_observation": "Product ps-based process budget yielded 64 under the outer layer and 760 without it. Both use the same code; failure is sandbox_apply before Python payload, not a Python import or ulimit failure.",
}
(BASE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
manifest = []
for path in sorted(BASE.rglob("*")):
    relative = path.relative_to(BASE)
    if not path.is_file() or "private-runtime" in relative.parts or path.name == "artifact-manifest.json":
        continue
    manifest.append({"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
(BASE / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"verdict": result["verdict"], "scenarios": scenarios, "manifest_count": len(manifest), "sources_match_formal": sources_match_formal}, indent=2))
