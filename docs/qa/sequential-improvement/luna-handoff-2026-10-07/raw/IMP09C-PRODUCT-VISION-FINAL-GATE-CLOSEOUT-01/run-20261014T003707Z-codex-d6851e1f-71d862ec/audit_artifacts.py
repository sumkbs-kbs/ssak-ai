# /// script
# requires-python = ">=3.11"
# ///
# Usage: python -B audit_artifacts.py
from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

RUN = Path(__file__).resolve().parent
ROOT = next(parent for parent in RUN.parents if parent.name == "Ssak-Ai")
FINAL_RECEIPT = "checks-956ad18301aa472b81ff2e9c74263531.json"
CHANGED = ("run_harness.py", "run_offline_prechecks.py", "test_runtime_final_gate_contract.py")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(base: Path) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for directory, directories, files in os.walk(base, followlinks=False):
        for name in sorted([*directories, *files]):
            path = Path(directory) / name
            rel = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                records.append({"path": rel, "type": "symlink", "target": os.readlink(path)})
            elif path.is_file():
                raw = path.read_bytes()
                records.append(
                    {"path": rel, "type": "file", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                )
    return sorted(records, key=lambda item: str(item["path"]))


def mismatch_hashes(base: Path, expected: dict[str, str]) -> list[str]:
    return sorted(name for name, expected_hash in expected.items() if digest(base / name) != expected_hash)


def main() -> int:
    binding = json.loads((RUN / "execution-binding.json").read_text())
    receipt = json.loads((RUN / FINAL_RECEIPT).read_text())
    saved = json.loads((RUN / "baseline/preserved-inputs-before.json").read_text())
    current = {str(item["path"]): item for rel in saved["roots"] for item in inventory(ROOT / rel)}
    before = {item["path"]: item for item in saved["items"]}
    for rel in set(before) - set(current):
        path = ROOT / rel
        if path.is_file() and not path.is_symlink():
            raw = path.read_bytes()
            current[rel] = {
                "path": rel,
                "type": "file",
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
    missing = sorted(set(before) - set(current))
    added = sorted(set(current) - set(before))
    changed = sorted(rel for rel in before.keys() & current.keys() if before[rel] != current[rel])
    protected_mismatches = mismatch_hashes(ROOT, receipt["protected_files_after"])
    source_mismatches = mismatch_hashes(RUN, binding["implementation_source_sha256"])
    patch_mismatches = [
        name for name in CHANGED if (RUN / name).read_bytes() != (RUN / "patch-reconstruction" / name).read_bytes()
    ]
    child = RUN / receipt["selector_child_output_path"]
    guard = json.loads((child / "state-guard.json").read_text())
    tests = list(ET.parse(child / "junit.xml").getroot().iter("testcase"))
    cases = {
        "tests": len(tests),
        "failures": sum(case.find("failure") is not None for case in tests),
        "errors": sum(case.find("error") is not None for case in tests),
        "skipped": sum(case.find("skipped") is not None for case in tests),
    }
    cases["passed"] = cases["tests"] - cases["failures"] - cases["errors"] - cases["skipped"]
    delivery = receipt["delivery_artifacts"]
    inventory_path = RUN / delivery["inventory_path"]
    delivery_snapshot = json.loads(inventory_path.read_text())
    delivery_phase_mismatches = [
        record["path"] for record in delivery_snapshot["files"] if digest(RUN / record["path"]) != record["sha256"]
    ]
    command_hash_mismatches: list[str] = []
    for check in receipt["checks"]:
        for name in ("stdout", "stderr"):
            record = check[name]
            if digest(RUN / record["path"]) != record["sha256"]:
                command_hash_mismatches.append(record["path"])
    launches = []
    for path in sorted((RUN / "launches").glob("*/launch-receipt.json")):
        launch = json.loads(path.read_text())
        launches.append(
            {
                "path": str(path.relative_to(RUN)),
                "mode": launch["mode"],
                "exit_code": launch["exit_code"],
                "source_sha256_before": launch["source_sha256_before"],
                "source_sha256_after": launch["source_sha256_after"],
            }
        )
    historical_checks = []
    for path in sorted(RUN.glob("checks-*.json")):
        observed = json.loads(path.read_text())
        historical_checks.append(
            {
                "path": path.name,
                "sha256": digest(path),
                "overall_valid": observed["overall_valid"],
                "reported_counts": observed["selector_counts"],
                "errors": observed["selector_evidence_errors"],
                "child_output": observed["selector_child_output_path"],
            }
        )
    allowed_phase_difference = ["launches/gate-37df3c4d565d499d89eb7ab34f61a274/stdout.txt"]
    valid = (
        not missing
        and not added
        and not changed
        and not protected_mismatches
        and not source_mismatches
        and not patch_mismatches
        and not command_hash_mismatches
        and cases == {"tests": 22, "failures": 0, "errors": 0, "skipped": 0, "passed": 22}
        and receipt["overall_valid"] is True
        and receipt["selector_evidence_errors"] == []
        and digest(RUN / delivery["counts_path"]) == delivery["counts_sha256"]
        and digest(inventory_path) == delivery["inventory_sha256"]
        and guard["violations"] == []
        and not any(guard["guard_counters"].values())
        and delivery_phase_mismatches == allowed_phase_difference
    )
    report = {
        "status": "PASS_SCOPED_STORED_ARTIFACTS" if valid else "FAIL",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "final_checks": {"path": FINAL_RECEIPT, "sha256": digest(RUN / FINAL_RECEIPT)},
        "binding_sha256": digest(RUN / "execution-binding.json"),
        "binding_source_mismatches": source_mismatches,
        "protected": {"count": len(receipt["protected_files_after"]), "mismatches": protected_mismatches},
        "preserved_inputs": {"count": len(before), "missing": missing, "added": added, "changed": changed},
        "patch": {
            "path": "task-only.patch",
            "sha256": digest(RUN / "task-only.patch"),
            "git_apply_exit_code_observed_by_root": 0,
            "reconstructed": list(CHANGED),
            "mismatches": patch_mismatches,
        },
        "junit": {"path": str((child / "junit.xml").relative_to(RUN)), **cases},
        "guard_counters": guard["guard_counters"],
        "static_checks": [
            {"kind": c["check_kind"], "exit_code": c["exit_code"], "attempt": c["attempt"]}
            for c in receipt["checks"]
            if c["check_kind"] != "cold-selector"
        ],
        "command_output_hash_mismatches": command_hash_mismatches,
        "delivery_receipt_hashes_match": digest(inventory_path) == delivery["inventory_sha256"]
        and digest(RUN / delivery["counts_path"]) == delivery["counts_sha256"],
        "delivery_snapshot_limitation": {
            "kind": "DURING_RUN_SNAPSHOT_WITH_ACTIVE_OUTER_STDOUT",
            "mismatches": delivery_phase_mismatches,
            "historical_bytes_preserved": True,
            "final_seal_requires_closed_outputs": True,
        },
        "historical_checks": historical_checks,
        "launches": launches,
        "live_observation": "NOT_RUN",
        "live_authorization": "NOT_ISSUED",
        "ledger": "NOT_RECOVERED",
        "overall_imp09": "PARTIAL",
    }
    with (RUN / "artifact-audit-final.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    event = (
        json.dumps(
            {
                "at_utc": datetime.now(UTC).isoformat(),
                "stage": "root-stored-artifact-audit",
                "status": report["status"],
                "receipt": "artifact-audit-final.json",
            }
        )
        + "\n"
    )
    fd = os.open(RUN / "worklog.jsonl", os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, event.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    print(
        json.dumps(
            {
                "status": report["status"],
                "preserved_items": len(before),
                "protected": len(receipt["protected_files_after"]),
                "junit": cases,
                "patch_mismatches": patch_mismatches,
            }
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
