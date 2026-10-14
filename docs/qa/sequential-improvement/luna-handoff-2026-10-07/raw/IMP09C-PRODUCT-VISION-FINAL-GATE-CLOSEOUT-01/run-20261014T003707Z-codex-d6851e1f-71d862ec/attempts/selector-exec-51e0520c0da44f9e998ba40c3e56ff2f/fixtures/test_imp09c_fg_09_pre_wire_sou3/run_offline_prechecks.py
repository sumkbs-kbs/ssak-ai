from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

RUN = Path(__file__).resolve().parent
ROOT = next(parent for parent in RUN.parents if parent.name == "Ssak-Ai")
HARNESS = RUN / "run_harness.py"
TESTS = RUN / "test_runtime_final_gate_contract.py"
REFERENCE_TESTS = RUN / "test_runtime_bridge_contract.py"
COMPATIBILITY_TESTS = RUN / "test_runtime_compatibility_contract.py"
ADAPTER = RUN / "runtime_adapter.py"
SOURCES = (HARNESS, ADAPTER, REFERENCE_TESTS, COMPATIBILITY_TESTS, TESTS, Path(__file__).resolve())
STATIC_SOURCES = (HARNESS, TESTS, Path(__file__).resolve())
ATTEMPTS = RUN / "attempts"
REVIEW_INVENTORY = RUN / "baseline" / "parent-review-inventory.json"
TASK_ID = "IMP-09-C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01"
EXPECTED_NODEIDS = [
    "test_imp09c_fg_01_driver_success_requires_explicit_parent_child_receipts",
    "test_imp09c_fg_01_final_reducer_rejects_errors_even_if_chain_claims_valid",
    "test_imp09c_fg_02_missing_ambiguous_and_stale_children_fail_closed",
    "test_imp09c_fg_03_zero_failure_error_skip_and_receipt_mismatch_fail_closed",
    "test_imp09c_fg_04_main_executes_real_driver_with_mocked_capture",
    "test_imp09c_fg_04_main_mismatched_binding_and_guard_fail_closed",
    "test_imp09c_fg_04_main_existing_child_is_read_only",
    "test_imp09c_fg_04_main_missing_child_and_reducer_error_fail_closed",
    "test_imp09c_fg_10_main_owns_inventory_and_counts_writer",
    "test_imp09c_fg_05_symlink_inventory_does_not_follow_directory_aliases",
    "test_imp09c_fg_06_alias_journal_does_not_increase_invocation_counts",
    "test_imp09c_fg_07_partial_body_timeout_preserves_prefix_and_bounded_deadline",
    "test_imp09c_fg_08_supervise_once_success_requires_reaped_cleanup",
    "test_imp09c_fg_11_cleanup_failure_and_late_deadline_fail_closed[cleanup-exception]",
    "test_imp09c_fg_11_cleanup_failure_and_late_deadline_fail_closed[cleanup-unknown]",
    "test_imp09c_fg_11_cleanup_failure_and_late_deadline_fail_closed[cleanup-slow]",
    "test_imp09c_fg_11_cleanup_failure_and_late_deadline_fail_closed[cleanup-late]",
    "test_imp09c_fg_09_pre_wire_source_drift_remains_non_success[source-drift]",
    "test_imp09c_fg_09_pre_wire_source_drift_remains_non_success[request-drift]",
    "test_imp09c_fg_09_pre_wire_source_drift_remains_non_success[binding-drift]",
    "test_imp09c_fg_09_pre_wire_source_drift_remains_non_success[wire-expired]",
    "test_imp09c_fg_12_post_cleanup_source_drift_is_reduced_to_failure",
]


def expected_fg_nodeids() -> list[str]:
    return list(EXPECTED_NODEIDS)


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path: Path) -> str:

    return hashlib.sha256(path.read_bytes()).hexdigest()


def worklog(event: dict[str, Any]) -> None:
    path = RUN / "worklog.jsonl"
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        raw = (json.dumps({"at_utc": utc(), "task_run": RUN.name, **event}, ensure_ascii=False) + "\n").encode()
        if os.write(fd, raw) != len(raw):
            raise OSError("short append-only worklog write")
        os.fsync(fd)
    finally:
        os.close(fd)


def capture(
    command: list[str], *, name: str, env: dict[str, str], invocation_id: str, cwd: Path = ROOT
) -> dict[str, Any]:

    source_start = {str(path.relative_to(ROOT)): digest(path) for path in SOURCES}
    if name != "cold-selector":
        for previous in sorted(ATTEMPTS.glob(f"{name}-*/command.json")):
            old = json.loads(previous.read_text())
            if old["exit_code"] == 0 and old["sources_at_execution"] == source_start and old.get("check_kind") == name:
                return {"attempt": previous.parent.relative_to(RUN).as_posix(), "reused_success_receipt": True, **old}
    attempt = ATTEMPTS / f"{name}-{uuid.uuid4().hex}"
    attempt.mkdir(parents=True, exist_ok=False)
    child: Path | None = None
    parent_started_at: str | None = None
    capture_started: str | None = None
    invocation_record: dict[str, Any] | None = None
    if name == "cold-selector":
        child = ATTEMPTS / f"selector-exec-{uuid.uuid4().hex}"
        if child.exists() or child.is_symlink():
            raise ValueError("new child output path already exists; refusing overwrite")
        invocation_record = {
            "schema": "ssak.imp09c.selector-invocation.v1",
            "parent_invocation_id": invocation_id,
            "parent_capture_id": attempt.name,
            "owned_output_path": child.relative_to(RUN).as_posix(),
            "argv": command,
            "cwd": str(cwd),
            "started_at_utc": None,
            "source_sha256_at_dispatch": source_start,
            "expected_nodeids": expected_fg_nodeids(),
        }
        (attempt / "selector-invocation.json").write_text(
            json.dumps(invocation_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    started = utc()
    started_mono = time.monotonic()
    snapshot = attempt / "source-snapshot"
    snapshot.mkdir()
    for path in SOURCES:
        (snapshot / path.name).write_bytes(path.read_bytes())
    if name == "cold-selector":
        assert child is not None and invocation_record is not None
        capture_started = utc()
        parent_started_at = capture_started
        (attempt / "capture-start.json").write_text(
            json.dumps(
                {
                    "schema": "ssak.imp09c.parent-capture-start.v1",
                    "invocation_id": invocation_id,
                    "capture_id": attempt.name,
                    "argv": command,
                    "cwd": str(cwd),
                    "started_at_utc": capture_started,
                    "sources_at_execution": source_start,
                    "expected_nodeids": expected_fg_nodeids(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        invocation_record["started_at_utc"] = capture_started
        (attempt / "selector-invocation.json").write_text(
            json.dumps(invocation_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        invocation_sha256 = digest(attempt / "selector-invocation.json")
        child_env = dict(env)
        child_env["IMP09C_PARENT_INVOCATION_ID"] = invocation_id
        child_env["IMP09C_PARENT_CAPTURE_ID"] = attempt.name
        child_env["IMP09C_CHILD_OUTPUT_PATH"] = str(child)
        parent_dispatch = {
            "parent_invocation_id": invocation_id,
            "parent_capture_id": attempt.name,
            "child_invocation_id": child.name,
            "owned_output_path": child.relative_to(RUN).as_posix(),
            "parent_capture_start_sha256": digest(attempt / "capture-start.json"),
            "argv": command,
            "cwd": str(cwd),
            "started_at_utc": utc(),
            "source_sha256_at_dispatch": source_start,
            "selector_sha256_at_dispatch": digest(TESTS),
            "harness_sha256_at_dispatch": digest(HARNESS),
            "selector_invocation_sha256": invocation_sha256,
            "expected_nodeids": expected_fg_nodeids(),
        }
        (attempt / "parent-dispatch.json").write_text(
            json.dumps(parent_dispatch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        parent_dispatch_sha256 = digest(attempt / "parent-dispatch.json")
        child_env["IMP09C_PARENT_DISPATCH_SHA256"] = parent_dispatch_sha256
        child_env["IMP09C_PARENT_CAPTURE_START_SHA256"] = digest(attempt / "capture-start.json")
        env = child_env
    worklog(
        {
            "stage": name + "-started",
            "source_sha256": source_start,
            "execution_id": attempt.name,
            "argv": command,
            "cwd": str(cwd),
        }
    )
    started_record_path = attempt / "capture-start.json"
    if name == "cold-selector" and started_record_path.is_file():
        parent_start = json.loads(started_record_path.read_text(encoding="utf-8"))
        if parent_start.get("capture_id") != attempt.name or parent_start.get("invocation_id") != invocation_id:
            raise ValueError("parent capture start identity does not match actual invocation")
        expected_capture_start_sha256 = digest(started_record_path)
        env = dict(env)
        env["IMP09C_PARENT_CAPTURE_START_SHA256"] = expected_capture_start_sha256
    completed = subprocess.run(
        command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    finished = utc()
    stdout_path, stderr_path = attempt / "stdout.txt", attempt / "stderr.txt"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    command_record = {
        "check_kind": name,
        "argv": command,
        "cwd": str(cwd),
        "started_at_utc": parent_started_at or started,
        "finished_at_utc": finished,
        "elapsed_seconds_monotonic": time.monotonic() - started_mono,
        "exit_code": completed.returncode,
        "environment_changed_names": sorted(
            set(env) - set(os.environ) | {key for key in set(env) & set(os.environ) if env[key] != os.environ[key]}
        ),
        "environment_values_recorded": False,
        "invocation_id": invocation_id,
        "capture_id": attempt.name,
        "capture_mode": "SUBPROCESS",
        "expected_nodeids": expected_fg_nodeids() if name == "cold-selector" else None,
        "parent_dispatch_sha256": digest(attempt / "parent-dispatch.json") if name == "cold-selector" else None,
        "parent_capture_start_sha256": digest(started_record_path) if name == "cold-selector" else None,
        "source_snapshot_sha256": {path.name: digest(snapshot / path.name) for path in SOURCES},
        "sources_at_execution": source_start,
        "sources_after_execution": {str(path.relative_to(ROOT)): digest(path) for path in SOURCES},
        "stdout": {
            "path": stdout_path.relative_to(RUN).as_posix(),
            "bytes": len(completed.stdout),
            "sha256": digest(stdout_path),
        },
        "stderr": {
            "path": stderr_path.relative_to(RUN).as_posix(),
            "bytes": len(completed.stderr),
            "sha256": digest(stderr_path),
        },
    }
    junit_path = attempt / "junit.xml"
    if junit_path.is_file():
        command_record["junit"] = {
            "path": junit_path.relative_to(RUN).as_posix(),
            "bytes": junit_path.stat().st_size,
            "sha256": digest(junit_path),
        }
    (attempt / "command.json").write_text(
        json.dumps(command_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    worklog(
        {
            "stage": name + "-finished",
            "source_sha256": source_start,
            "execution_id": attempt.name,
            "exit_code": completed.returncode,
            "receipt": str((attempt / "command.json").relative_to(RUN)),
            "next": "repair-new-candidate" if completed.returncode else "next-unfinished-check",
        }
    )
    return {"attempt": attempt.relative_to(RUN).as_posix(), **command_record}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"receipt is not an object: {path.name}")
    return value


def validate_selector_chain(
    run: Path,
    parent_capture: Path,
    invocation_id: str,
    expected_argv: list[str],
    expected_nodeids: list[str],
) -> dict[str, Any]:
    """Validate only the explicitly named parent/child receipts; never search for a substitute."""
    output: dict[str, Any] = {
        "valid": False,
        "errors": [],
        "child_path": None,
        "nodeids": [],
        "counts": {"tests": 0, "selected": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0},
    }
    try:
        parent_capture = parent_capture.resolve(strict=True)
        if parent_capture.parent != (run / "attempts").resolve() or parent_capture.is_symlink():
            raise ValueError("parent capture is not an owned direct attempts directory")
        capture_start_path = parent_capture / "capture-start.json"
        parent_dispatch_path = parent_capture / "parent-dispatch.json"
        parent_command_path = parent_capture / "command.json"
        invocation_path = parent_capture / "selector-invocation.json"
        capture_start = _json_object(capture_start_path)
        parent_dispatch = _json_object(parent_dispatch_path)
        parent_command = _json_object(parent_command_path)
        invocation = _json_object(invocation_path)
        if (
            capture_start.get("capture_id") != parent_capture.name
            or capture_start.get("invocation_id") != invocation_id
        ):
            raise ValueError("parent capture-start identity mismatch")
        if (
            parent_command.get("capture_id") != parent_capture.name
            or parent_command.get("invocation_id") != invocation_id
        ):
            raise ValueError("parent command identity mismatch")
        output["parent_capture_mode"] = parent_command.get("capture_mode")
        if parent_command.get("capture_mode") == "SIMULATED_CAPTURE":
            output["errors"].append("SIMULATED_CAPTURE_NOT_EXECUTION")
        if (
            capture_start.get("argv") != expected_argv
            or capture_start.get("cwd") != str(ROOT)
            or invocation.get("argv") != expected_argv
            or invocation.get("cwd") != str(ROOT)
        ):
            raise ValueError("parent start/invocation argv or cwd mismatch")
        parent_started = capture_start.get("started_at_utc")
        invocation_started = invocation.get("started_at_utc")
        if not isinstance(parent_started, str) or not isinstance(invocation_started, str):
            raise ValueError("parent start/invocation timestamps are missing")
        if dt.datetime.fromisoformat(invocation_started.replace("Z", "+00:00")) > dt.datetime.fromisoformat(
            parent_started.replace("Z", "+00:00")
        ):
            raise ValueError("parent invocation was recorded after capture start")
        if parent_command.get("argv") != expected_argv or parent_command.get("cwd") != str(ROOT):
            raise ValueError("parent command argv/cwd mismatch")
        if parent_command.get("sources_at_execution") != capture_start.get("sources_at_execution"):
            raise ValueError("parent command execution source snapshot differs from parent start")
        if parent_command.get("capture_mode") not in {"SUBPROCESS", "OBSERVED_SUBPROCESS", "SIMULATED_CAPTURE"}:
            raise ValueError("parent command capture provenance is missing or unsupported")
        if parent_command.get("exit_code") != 0:
            raise ValueError("parent command did not complete successfully")
        if parent_command.get("sources_after_execution") != parent_command.get("sources_at_execution"):
            raise ValueError("parent command source drifted during capture")
        if parent_command.get("expected_nodeids") != expected_nodeids:
            raise ValueError("parent command does not bind the expected selector inventory")
        if parent_command.get("capture_mode") != "SIMULATED_CAPTURE" and parent_command.get(
            "parent_dispatch_sha256"
        ) != digest(parent_dispatch_path):
            raise ValueError("parent command does not bind the dispatch receipt")
        if parent_command.get("parent_capture_start_sha256") != digest(capture_start_path):
            raise ValueError("parent command does not bind the capture-start receipt")
        source_start = parent_command.get("sources_at_execution")
        if not isinstance(source_start, dict) or capture_start.get("sources_at_execution") != source_start:
            raise ValueError("parent source snapshot mismatch")
        if (
            parent_command.get("expected_nodeids") != expected_nodeids
            or capture_start.get("expected_nodeids") != expected_nodeids
        ):
            raise ValueError("parent expected-node inventory mismatch")
        child_rel = invocation.get("owned_output_path")
        if not isinstance(child_rel, str) or Path(child_rel).is_absolute() or ".." in Path(child_rel).parts:
            raise ValueError("explicit child output path is not a safe run-relative path")
        if (
            invocation.get("parent_capture_id") != parent_capture.name
            or invocation.get("parent_invocation_id") != invocation_id
        ):
            raise ValueError("parent-child invocation identity mismatch")
        if invocation.get("argv") != expected_argv or invocation.get("cwd") != str(ROOT):
            raise ValueError("selector caller argv/cwd mismatch")
        if (
            invocation.get("source_sha256_at_dispatch") != source_start
            or invocation.get("expected_nodeids") != expected_nodeids
            or parent_dispatch.get("expected_nodeids") != expected_nodeids
        ):
            raise ValueError("selector source or expected-node inventory mismatch")
        child_lexical = run / child_rel
        if child_lexical.is_symlink():
            raise ValueError("child invocation output must not be a symlink")
        child_path = child_lexical.resolve(strict=True)
        if (
            child_path.parent != (run / "attempts").resolve()
            or child_path.name != Path(child_rel).name
            or not child_path.is_dir()
        ):
            raise ValueError("explicit child invocation is outside the owned attempts directory")
        output["child_path"] = child_path
        if parent_command.get("capture_mode") == "SIMULATED_CAPTURE":
            output["errors"].append("SIMULATED_CAPTURE_NOT_EXECUTION")
            return output
        parent_dispatch_sha = digest(parent_dispatch_path)
        if (
            parent_dispatch.get("parent_invocation_id") != invocation_id
            or parent_dispatch.get("parent_capture_id") != parent_capture.name
            or parent_dispatch.get("parent_capture_start_sha256") != digest(capture_start_path)
            or parent_dispatch.get("expected_nodeids") != expected_nodeids
            or parent_dispatch.get("child_invocation_id") != child_path.name
            or parent_dispatch.get("owned_output_path") != child_rel
            or parent_dispatch.get("argv") != expected_argv
            or parent_dispatch.get("cwd") != str(ROOT)
            or parent_dispatch.get("source_sha256_at_dispatch") != source_start
            or parent_dispatch.get("selector_sha256_at_dispatch") != source_start.get(str(TESTS.relative_to(ROOT)))
            or parent_dispatch.get("harness_sha256_at_dispatch") != source_start.get(str(HARNESS.relative_to(ROOT)))
            or parent_dispatch.get("selector_invocation_sha256") != digest(invocation_path)
            or parent_dispatch.get("started_at_utc") is None
            or invocation.get("started_at_utc") != capture_start.get("started_at_utc")
            or parent_dispatch.get("expected_nodeids") != expected_nodeids
            or parent_dispatch.get("started_at_utc") is None
            or parent_dispatch.get("expected_nodeids") != expected_nodeids
        ):
            raise ValueError("explicit parent dispatch fields mismatch")
        if parent_command.get("capture_mode") not in {"SUBPROCESS", "OBSERVED_SUBPROCESS", "SIMULATED_CAPTURE"}:
            raise ValueError("outer command capture provenance is missing or unsupported")
        if (
            parent_command.get("capture_mode") != "SIMULATED_CAPTURE"
            and parent_command.get("parent_dispatch_sha256") != parent_dispatch_sha
        ):
            raise ValueError("outer command does not bind parent dispatch")
        if parent_command.get("capture_mode") != "SIMULATED_CAPTURE" and parent_command.get(
            "parent_capture_start_sha256"
        ) != digest(capture_start_path):
            raise ValueError("outer command does not bind capture start")
        if (
            parent_command.get("capture_mode") != "SIMULATED_CAPTURE"
            and parent_dispatch.get("selector_invocation_sha256") != digest(invocation_path)
            or parent_dispatch.get("source_sha256_at_dispatch") != source_start
            or parent_dispatch.get("selector_sha256_at_dispatch") != source_start.get(str(TESTS.relative_to(ROOT)))
            or parent_dispatch.get("harness_sha256_at_dispatch") != source_start.get(str(HARNESS.relative_to(ROOT)))
            or (
                parent_command.get("capture_mode") != "SIMULATED_CAPTURE"
                and parent_command.get("sources_after_execution") != source_start
            )
        ):
            raise ValueError("parent execution end evidence does not bind invocation/source completion")

        paths = {
            name: child_path / name
            for name in (
                "dispatch.json",
                "completion.json",
                "parent-link.json",
                "precheck.json",
                "pytest-result.json",
                "pytest-started.json",
                "state-guard.json",
                "junit.xml",
            )
        }
        missing = [name for name, path in paths.items() if not path.is_file() or path.is_symlink()]
        if missing:
            raise ValueError("required child receipt missing or symlinked: " + ",".join(missing))
        dispatch = _json_object(paths["dispatch.json"])
        completion = _json_object(paths["completion.json"])
        output["completion"] = completion
        child_link = _json_object(paths["parent-link.json"])
        precheck = _json_object(paths["precheck.json"])
        pytest_result = _json_object(paths["pytest-result.json"])
        pytest_started = _json_object(paths["pytest-started.json"])
        guard = _json_object(paths["state-guard.json"])
        dispatch_sha = digest(paths["dispatch.json"])
        if (
            dispatch.get("parent_invocation_id") != invocation_id
            or dispatch.get("parent_capture_id") != parent_capture.name
            or dispatch.get("child_invocation_id") != child_path.name
            or dispatch.get("owned_output_path") != child_rel
            or dispatch.get("parent_dispatch_sha256") != parent_dispatch_sha
            or dispatch.get("parent_capture_start_sha256") != digest(capture_start_path)
            or dispatch.get("selector_sha256_at_dispatch") != source_start.get(str(TESTS.relative_to(ROOT)))
            or dispatch.get("harness_sha256_at_dispatch") != source_start.get(str(HARNESS.relative_to(ROOT)))
            or dispatch.get("parent_capture_start_sha256") != digest(capture_start_path)
            or dispatch.get("parent_dispatch_sha256") != parent_dispatch_sha
            or dispatch.get("source_sha256_at_dispatch") != source_start
            or dispatch.get("expected_nodeids") != expected_nodeids
            or dispatch.get("argv") != expected_argv
            or dispatch.get("cwd") != str(ROOT)
        ):
            raise ValueError("child dispatch identity/source/argv/hash mismatch")
        for receipt in (child_link, completion):
            if (
                receipt.get("parent_invocation_id") != invocation_id
                or receipt.get("parent_capture_id") != parent_capture.name
                or receipt.get("child_invocation_id") != child_path.name
                or receipt.get("owned_output_path") != child_rel
                or receipt.get("parent_dispatch_sha256") != parent_dispatch_sha
                or receipt.get("parent_capture_start_sha256") != digest(capture_start_path)
            ):
                raise ValueError("child parent-link or completion identity mismatch")
        binding_path = run / "execution-binding.json"
        binding_sha = digest(binding_path)
        precheck_binding_sha = precheck.get("execution_binding_sha256")
        if precheck.get("status") != "READY" or precheck_binding_sha != binding_sha:
            raise ValueError("precheck is not READY on the current immutable execution binding")
        if (
            precheck.get("source_sha256_at_dispatch") != source_start
            or precheck.get("expected_nodeids") != expected_nodeids
            or pytest_result.get("source_sha256_at_dispatch") != source_start
            or pytest_result.get("expected_nodeids") != expected_nodeids
            or pytest_result.get("selector") != str(TESTS)
            or pytest_result.get("selector_sha256") != dispatch.get("selector_sha256_at_dispatch")
            or pytest_result.get("dispatch_sha256") != dispatch_sha
            or pytest_result.get("execution_binding_sha256") != binding_sha
            or pytest_result.get("precheck_status") != "READY"
            or pytest_result.get("parent_invocation_id") != invocation_id
            or pytest_result.get("parent_capture_id") != parent_capture.name
            or pytest_result.get("child_invocation_id") != child_path.name
            or pytest_result.get("pytest_started") is not True
            or pytest_result.get("product_imported") is not False
        ):
            raise ValueError("pytest result selector/binding/identity/guard receipt mismatch")
        if (
            pytest_started.get("source_sha256_at_dispatch") != source_start
            or pytest_started.get("expected_nodeids") != expected_nodeids
            or pytest_started.get("selector") != str(TESTS)
            or pytest_started.get("selector_sha256") != source_start.get(str(TESTS.relative_to(ROOT)))
            or pytest_started.get("execution_binding_sha256") != binding_sha
            or pytest_started.get("dispatch_sha256") != dispatch_sha
            or pytest_started.get("parent_invocation_id") != invocation_id
            or pytest_started.get("parent_capture_id") != parent_capture.name
            or pytest_started.get("child_invocation_id") != child_path.name
        ):
            raise ValueError("pytest-started receipt identity or source mismatch")
        if (
            completion.get("source_sha256_at_dispatch") != source_start
            or completion.get("expected_nodeids") != expected_nodeids
            or completion.get("dispatch_sha256") != dispatch_sha
            or completion.get("exit_code") != pytest_result.get("exit_code")
        ):
            raise ValueError("child completion does not bind pytest dispatch/exit")

        def parse_time(value: object, label: str) -> dt.datetime:
            if not isinstance(value, str):
                raise ValueError(f"missing timestamp: {label}")
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

        ordered_times = [
            parse_time(parent_command.get("started_at_utc"), "parent command start"),
            parse_time(parent_dispatch.get("started_at_utc"), "parent dispatch start"),
            parse_time(dispatch.get("started_at_utc"), "child dispatch start"),
            parse_time(completion.get("started_at_utc"), "child start"),
            parse_time(completion.get("finished_at_utc"), "child finish"),
            parse_time(parent_command.get("finished_at_utc"), "parent command finish"),
        ]
        if ordered_times != sorted(ordered_times):
            raise ValueError("parent-child invocation timestamps are out of order")
        selected = pytest_result.get("selected_nodeids")
        if not isinstance(selected, list) or any(not isinstance(node, str) for node in selected):
            raise ValueError("selected pytest nodeid list is missing or malformed")
        nodeids = [node.rsplit("::", 1)[-1] for node in selected]
        if nodeids != expected_nodeids:
            raise ValueError("selected pytest nodeids differ from exact FG acceptance inventory")
        junit_root = ET.parse(paths["junit.xml"]).getroot()
        cases = list(junit_root.iter("testcase"))
        if not cases:
            raise ValueError("JUnit has no testcase entries")
        case_names = [case.get("name", "") for case in cases]
        if case_names != nodeids:
            raise ValueError("JUnit case order/names differ from pytest selected nodeids")
        failures = sum(len(list(case.iter("failure"))) for case in cases)
        errors = sum(len(list(case.iter("error"))) for case in cases)
        skipped = sum(len(list(case.iter("skipped"))) for case in cases)
        suite_counts = {
            key: sum(
                int(suite.get(key, "0"))
                for suite in ([junit_root] if junit_root.tag == "testsuite" else list(junit_root.iter("testsuite")))
            )
            for key in ("tests", "failures", "errors", "skipped")
        }
        counts = {
            "tests": len(cases),
            "selected": len(nodeids),
            "passed": len(cases) - failures - errors - skipped,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }
        output["counts"] = counts
        output["nodeids"] = nodeids
        if suite_counts != {"tests": len(cases), "failures": failures, "errors": errors, "skipped": skipped}:
            raise ValueError("JUnit suite counts disagree with testcase contents")
        if (
            completion.get("exit_code") != 0
            or pytest_result.get("exit_code") != 0
            or failures
            or errors
            or skipped
            or len(cases) != len(expected_nodeids)
        ):
            raise ValueError("selector has nonzero exit, zero/mismatched selection, failure, error, or skip")
        if guard.get("source_sha256_at_dispatch") != source_start:
            raise ValueError("state guard source snapshot differs from parent dispatch")
        violations = guard.get("violations")
        before = guard.get("before_sha256")
        after = guard.get("after_sha256")
        counters = guard.get("guard_counters")
        if (
            violations != []
            or not isinstance(before, dict)
            or not isinstance(after, dict)
            or before.keys() != after.keys()
            or any(before[key] != after[key] for key in before)
            or not isinstance(counters, dict)
            or any(value != 0 for value in counters.values())
        ):
            raise ValueError("child state guard/protected hashes are missing, changed, or nonzero")
        output["valid"] = True
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, ET.ParseError, OverflowError) as exc:
        output["errors"].append(f"{type(exc).__name__}: {exc}")
    output["valid"] = bool(output["valid"]) and not output["errors"]
    if output["errors"]:
        output["valid"] = False
    return output


def reduce_final_gate(
    *,
    selector_chain: dict[str, Any],
    all_exit_zero: bool,
    protected_changed: list[str],
    source_drift: dict[str, Any],
    delivery_valid: bool,
    expected_selected: int,
) -> dict[str, Any]:
    """One fail-closed reducer for selector evidence and final delivery conditions."""
    raw_errors = selector_chain.get("errors", [])
    errors = raw_errors if isinstance(raw_errors, list) else ["selector errors field is malformed"]
    errors = list(errors)
    if selector_chain.get("valid") is not True:
        errors = [*errors, "selector evidence reducer returned non-valid"]
    delivery_errors = selector_chain.get("delivery_errors", [])
    if not isinstance(delivery_errors, list):
        delivery_errors = ["delivery errors field is malformed"]
    errors = [*errors, *delivery_errors]
    counts = selector_chain.get("counts", {})
    selected = counts.get("selected", 0) if isinstance(counts, dict) else 0
    selector_valid = selector_chain.get("valid") is True and not errors
    valid = (
        selector_valid
        and all_exit_zero
        and selected == expected_selected
        and not protected_changed
        and not source_drift
        and delivery_valid
    )
    if errors:
        valid = False
    return {
        "valid": valid,
        "selector_evidence_valid": selector_valid,
        "selected": selected,
        "expected_selected": expected_selected,
        "protected_changed": protected_changed,
        "source_drift": source_drift,
        "delivery_valid": delivery_valid,
        "errors": list(errors),
    }


def inventory_tree(root: Path, *, excluded: frozenset[str] = frozenset()) -> dict[str, list[dict[str, Any]]]:
    """Return regular-file digests and symlink targets without descending through aliases."""
    files: list[dict[str, Any]] = []
    symlinks: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                rel = path.relative_to(root).as_posix()
                if (
                    rel in {"artifact-manifest.json", "worklog.jsonl"} | excluded
                    or (path.parent == root and path.name.startswith("checks-") and path.suffix == ".json")
                    or "__pycache__" in path.parts
                ):
                    continue
                if entry.is_symlink():
                    target = os.readlink(path)
                    try:
                        kind = "directory-symlink" if entry.is_dir(follow_symlinks=True) else "file-symlink"
                    except OSError:
                        kind = "broken-symlink"
                    symlinks.append({"path": rel, "type": kind, "target": target})
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    raw = path.read_bytes()
                    files.append({"path": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return {
        "files": sorted(files, key=lambda item: item["path"]),
        "symlinks": sorted(symlinks, key=lambda item: item["path"]),
    }


def aggregate_invocations(records: list[dict[str, Any]]) -> dict[str, Any]:
    canonical: dict[str, dict[str, Any]] = {}
    aliases: list[dict[str, str]] = []
    for record in records:
        if record.get("alias_of"):
            aliases.append({"path": str(record["path"]), "target": str(record["alias_of"])})
            continue
        identity = record.get("invocation_id")
        if not isinstance(identity, str) or not identity or identity in canonical:
            raise ValueError("missing or duplicate canonical invocation identity")
        canonical[identity] = record
    paths = {str(record.get("path")) for record in canonical.values()}
    if any(alias["target"] not in paths for alias in aliases):
        raise ValueError("alias target is not an indexed canonical journal")
    return {"invocation_count": len(canonical), "aliases": aliases}


def _is_fixture_path(path: Path, run: Path) -> bool:
    """Keep pytest fixture artifacts out of the invocation journal namespace."""
    try:
        relative = path.relative_to(run)
    except ValueError:
        return True
    return "fixtures" in relative.parts


def _regular_journals(directory: Path, *, run: Path) -> list[Path]:
    found: list[Path] = []
    try:
        directory.relative_to(run)
    except ValueError:
        return found
    if _is_fixture_path(directory, run):
        return found
    pending = [directory]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if _is_fixture_path(path, run) or entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False) and entry.name == "journal.jsonl":
                    found.append(path)
    return sorted(found)


def collect_invocation_records(run: Path) -> list[dict[str, Any]]:
    """Read canonical invocation journals, excluding pytest fixtures, and record aliases."""
    attempts = run / "attempts"
    if not attempts.is_dir():
        return []
    canonical: dict[str, dict[str, Any]] = {}
    aliases: list[dict[str, Any]] = []
    pending = [attempts]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                rel = path.relative_to(run).as_posix()
                if _is_fixture_path(path, run):
                    continue
                if entry.is_symlink():
                    try:
                        target = path.resolve(strict=True)
                        if target.is_dir():
                            for journal in _regular_journals(target, run=run):
                                target_rel = journal.relative_to(run).as_posix()
                                alias_rel = (Path(rel) / journal.relative_to(target)).as_posix()
                                aliases.append({"path": alias_rel, "alias_of": target_rel})
                        elif target.is_file() and target.name == "journal.jsonl":
                            aliases.append({"path": rel, "alias_of": target.relative_to(run).as_posix()})
                    except (OSError, ValueError):
                        continue
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False) or entry.name != "journal.jsonl":
                    continue
                raw = path.read_bytes()
                try:
                    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ValueError(f"malformed invocation journal: {rel}") from exc
                if not events or any(not isinstance(event, dict) for event in events):
                    raise ValueError(f"empty or malformed invocation journal: {rel}")
                canonical[rel] = {
                    "path": rel,
                    "invocation_id": rel,
                    "event_count": len(events),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
    records = list(canonical.values()) + aliases
    aggregate_invocations(records)
    return sorted(records, key=lambda item: str(item["path"]))


def write_delivery_artifacts(
    run: Path,
    records: list[dict[str, Any]] | None = None,
    selector_counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write inventory/count outputs using the same reducers exercised by FG tests."""
    invocation_records = collect_invocation_records(run) if records is None else records
    aggregate = aggregate_invocations(invocation_records)
    cases = selector_counts if selector_counts is not None else {"selected": len(EXPECTED_NODEIDS)}
    counts = {"invocations": aggregate, "journal_records": len(invocation_records), "cases": cases}
    counts_path = run / "counts.json"
    inventory_path = run / "delivery-inventory.json"
    counts_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inventory = inventory_tree(run, excluded=frozenset({"delivery-inventory.json"}))
    inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "counts": counts,
        "counts_sha256": digest(counts_path),
        "inventory_sha256": digest(inventory_path),
        "inventory_path": inventory_path.relative_to(run).as_posix(),
        "inventory_files": len(inventory["files"]),
        "inventory_symlinks": len(inventory["symlinks"]),
    }


def write_parent_alias_correction(run: Path) -> dict[str, Any]:
    """Bind the known parent alias observation to its actual current journal target."""
    source = (
        ROOT
        / "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-OFFLINE-GATE-01/run-20261013T062916Z-de47ef10-99da-40a8-acb0-3867808f6903/parent-evidence-correction.json"
    )
    source_raw = source.read_bytes()
    prior = _json_object(source)
    alias_rel = str(prior["alias_observations"]["path"])
    alias_path = (
        ROOT
        / "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-RUNTIME-COMPATIBILITY-01/run-20261012T233025Z-526f7458-a984-4e89-97c7-7f509a59addc"
        / alias_rel
    )
    if not alias_path.parent.is_symlink():
        raise ValueError("parent alias directory is not a symlink at correction time")
    raw_target = os.readlink(alias_path.parent)
    canonical = alias_path.resolve(strict=True)
    target_rel = canonical.relative_to(ROOT).as_posix()
    raw = canonical.read_bytes()
    parent_run_rel = Path(str(prior["parent_run"]))
    alias_run_rel = (parent_run_rel / alias_rel).as_posix()
    target_run_rel = (parent_run_rel / Path(target_rel).relative_to(parent_run_rel)).as_posix()
    records = [
        {
            "path": (
                parent_run_rel
                / "attempts/selector-exec-e1cca7f7688e4900a5b9c9ecda70b2ed/fixtures/test_imp09c_rc_02_origin_class0/localhost.jsonl"
            ).as_posix(),
            "invocation_id": "origin-localhost",
        },
        {"path": target_run_rel, "invocation_id": "origin-127.0.0.1"},
        {"path": alias_run_rel, "alias_of": target_run_rel},
    ]
    aggregate = aggregate_invocations(records)
    if aggregate["invocation_count"] != 2 or aggregate["aliases"] != [
        {"path": alias_run_rel, "target": target_run_rel}
    ]:
        raise ValueError("corrected parent alias did not reduce to zero additional invocations")
    actual_target_directory = Path(raw_target)
    target_relative_to_directory = alias_path.relative_to(alias_path.parent)
    actual_alias_resolve = (actual_target_directory / target_relative_to_directory).resolve(strict=True)
    if actual_alias_resolve != canonical:
        raise ValueError("resolved symlink journal and canonical observed journal disagree")
    correction = {
        "schema": "ssak.imp09c.closeout.parent-alias-correction.v1",
        "source_correction_path": str(source.relative_to(ROOT)),
        "source_correction_sha256": hashlib.sha256(source_raw).hexdigest(),
        "observed_alias_path": alias_run_rel,
        "raw_directory_symlink_target": raw_target,
        "resolved_journal_target": target_run_rel,
        "actual_alias_target_absolute": str(actual_alias_resolve),
        "resolved_journal_sha256": hashlib.sha256(raw).hexdigest(),
        "resolved_journal_bytes": len(raw),
        "superseded_target_absolute": prior["alias_observations"]["target_absolute"],
        "invocation_count_with_alias": aggregate["invocation_count"],
        "alias_aggregate_increment": 0,
        "historical_start_time_target_claimed": False,
    }
    target = run / "parent-evidence-correction.json"
    target.write_text(json.dumps(correction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": target.relative_to(run).as_posix(), "sha256": digest(target), "alias_aggregate_increment": 0}


def selector_failure_chain(
    run: Path, parent_capture: Path, invocation_id: str, expected_argv: list[str]
) -> dict[str, Any]:
    """Build an explicit, unsuccessful outcome when real child evidence is absent or invalid."""
    try:
        invocation = _json_object(parent_capture / "selector-invocation.json")
        child_rel = invocation.get("owned_output_path")
        if isinstance(child_rel, str) and not Path(child_rel).is_absolute() and ".." not in Path(child_rel).parts:
            child_path = run / child_rel
            if (
                child_path.parent.resolve() == ATTEMPTS.resolve()
                and child_path.is_dir()
                and not child_path.is_symlink()
            ):
                return {
                    "child_path": child_path,
                    "child_invocation_id": child_path.name,
                    "parent_invocation_id": invocation_id,
                    "parent_capture_id": parent_capture.name,
                    "argv": expected_argv,
                    "evidence": inventory_tree(child_path),
                    "evidence_path": child_path.relative_to(run).as_posix(),
                }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    return {
        "child_path": None,
        "child_invocation_id": None,
        "parent_invocation_id": invocation_id,
        "parent_capture_id": parent_capture.name,
        "argv": expected_argv,
        "evidence": None,
        "evidence_path": None,
    }


def main() -> int:
    run_id = uuid.uuid4().hex
    state = RUN / "offline-state" / f"check-{run_id}"
    state.mkdir(parents=True, exist_ok=False)
    (state / "auth").mkdir(parents=True, exist_ok=True)
    (state / "logs").mkdir(parents=True, exist_ok=True)
    (state / "vault").mkdir(parents=True, exist_ok=True)
    (state / "sessions").mkdir(parents=True, exist_ok=True)
    (state / "audit").mkdir(parents=True, exist_ok=True)
    (state / "home").mkdir(parents=True, exist_ok=True)
    (state / "hook-vault").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src"), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    protected_test_paths = {
        "src/antigravity_k/engine/project_registry.py",
        "src/antigravity_k/engine/project_registry.py.lock",
        "data/projects.json",
        "projects.json",
    }
    originals = {
        key: env.get(key)
        for key in (
            "HOME",
            "AGK_ENV_FILE",
            "AGK_CONFIG_FILE",
            "AGK_PATH_PROJECT_ROOT",
            "AGK_PATH_DATA_DIR",
            "AGK_PATH_LOGS_DIR",
            "AGK_USAGE_DB",
            "ANTIGRAVITY_VAULT_PATH",
            "AGK_SESSION_BASE_DIR",
            "AGK_AUDIT_LOG_DIR",
            "AGK_AUTH_PIN_HASH_FILE",
            "AGK_AUTH_TOKEN_SECRET_FILE",
            "AGK_HOOK_VAULT_DIR",
            "PYTHONPATH",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTHONDONTWRITEBYTECODE",
        )
    }
    env["IMP09C_PROTECTED_TEST_PATHS"] = json.dumps(sorted(protected_test_paths))
    env["IMP09C_FORCE_NEW_SELECTOR"] = "1"
    start_started = utc()
    start_sources = {str(path.relative_to(ROOT)): digest(path) for path in SOURCES}
    source_bound_before = dict(start_sources)
    if source_bound_before.get(str(TESTS.relative_to(ROOT))) != digest(TESTS):
        raise ValueError("selector source digest differs from candidate source snapshot")
    if source_bound_before.get(str(HARNESS.relative_to(ROOT))) != digest(HARNESS):
        raise ValueError("harness source digest differs from candidate source snapshot")
    expected = json.loads((RUN / "baseline" / "protected-before.json").read_text(encoding="utf-8"))
    if isinstance(expected, dict) and expected.get("meaning") == "INHERITED_PARENT_BASELINE":
        raise ValueError("inherited baseline pointer must be resolved to its exact protected-before payload")
    expected_files = expected.get("files") if isinstance(expected, dict) else None
    if not isinstance(expected, dict) or not isinstance(expected.get("captured_at_utc"), str):
        raise ValueError("protected-before baseline must retain its captured_at_utc metadata")
    if not isinstance(expected_files, list) or any(
        not isinstance(record, dict)
        or not isinstance(record.get("path"), str)
        or not isinstance(record.get("sha256"), str)
        for record in expected_files
    ):
        raise ValueError("protected-before baseline has an invalid files list")
    if len({record["path"] for record in expected_files}) != len(expected_files):
        raise ValueError("protected-before baseline has duplicate paths")
    protected_records: list[dict[str, Any]] = []
    for record in expected_files:
        rel = record["path"]
        path = ROOT / rel
        protected_records.append(
            {
                "path": rel,
                "sha256": record["sha256"],
                "bytes": path.stat().st_size if path.is_file() else 0,
                "mode": oct(path.stat().st_mode & 0o777) if path.is_file() else None,
            }
        )
    protected: dict[str, list[dict[str, Any]]] = {"protected_files": protected_records}
    protected_hashes = {item["path"]: item["sha256"] for item in protected["protected_files"]}
    additional_runtime = json.loads((RUN / "baseline/additional-runtime-sources.json").read_text(encoding="utf-8"))
    additional_readiness = json.loads((RUN / "baseline/additional-readiness-source.json").read_text(encoding="utf-8"))
    if not isinstance(additional_runtime, dict) or not isinstance(additional_readiness, dict):
        raise ValueError("additional source baselines must be JSON objects")

    additional: dict[str, dict[str, Any]] = {}
    for source_set in (additional_runtime, additional_readiness):
        for path, record in source_set.items():
            if not isinstance(path, str) or not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
                raise ValueError("additional source baseline record is malformed")
            previous = additional.get(path)
            if previous is not None and previous["sha256"] != record["sha256"]:
                raise ValueError(f"additional source baseline hash conflict: {path}")
            additional[path] = record

    inherited_hashes = {record["path"]: record["sha256"] for record in expected_files}
    overlap = set(inherited_hashes).intersection(additional)
    conflicting_overlap = sorted(path for path in overlap if inherited_hashes[path] != additional[path]["sha256"])
    if conflicting_overlap:
        raise ValueError("additional source baseline conflicts with inherited hashes: " + ",".join(conflicting_overlap))

    additional_new = {path: record for path, record in additional.items() if path not in inherited_hashes}
    protected_hashes.update({path: record["sha256"] for path, record in additional_new.items()})
    baseline_accounting = {
        "inherited_parent_paths": len(inherited_hashes),
        "additional_declared_paths": len(additional),
        "additional_new_paths": len(additional_new),
        "equal_hash_duplicates_deduplicated": sorted(overlap),
        "unique_protected_paths": len(protected_hashes),
    }
    if baseline_accounting["unique_protected_paths"] != len(inherited_hashes) + len(additional_new):
        raise ValueError("effective protected source count accounting is inconsistent")
    expected_files.extend(
        {
            "path": path,
            "sha256": record["sha256"],
            "bytes": record.get("bytes", 0),
            "additional": True,
        }
        for path, record in additional_new.items()
    )
    if len(expected_files) != len(protected_hashes):
        raise ValueError("effective protected source entries do not match unique path count")
    expected["files"] = expected_files
    expected["effective_protected_accounting"] = baseline_accounting

    current_actual = {path: digest(ROOT / path) for path in protected_hashes}
    drift = {
        path: {"expected": protected_hashes[path], "actual": current_actual[path]}
        for path in protected_hashes
        if current_actual[path] != protected_hashes[path]
    }
    current_check = {
        "schema": "ssak.imp09c.inherited-baseline-current-check.v1",
        "checked_at_utc": utc(),
        "inherited_baseline_sha256": digest(RUN / "baseline/protected-before.json"),
        "inherited_paths": len(inherited_hashes),
        "additional_declared_paths": len(additional),
        "additional_new_paths": len(additional_new),
        "deduplicated_equal_hash_paths": sorted(overlap),
        "unique_protected_paths": len(protected_hashes),
        "matched_paths": len(protected_hashes) - len(drift),
        "mismatches": drift,
        "result": "MATCH" if not drift else "SOURCE_DRIFT",
    }
    (RUN / "baseline/current-check.json").write_text(
        json.dumps(current_check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (RUN / "baseline/effective-protected-accounting.json").write_text(
        json.dumps(baseline_accounting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    worklog(
        {
            "step_id": "GUARDED-BASELINE-DEDUPLICATION",
            "candidate_id": "candidate-5",
            "inherited_baseline_sha256": current_check["inherited_baseline_sha256"],
            "additional_runtime_baseline_sha256": digest(RUN / "baseline/additional-runtime-sources.json"),
            "additional_readiness_baseline_sha256": digest(RUN / "baseline/additional-readiness-source.json"),
            "accounting": baseline_accounting,
            "current_check": current_check["result"],
            "result": "identical duplicate paths counted once; conflicting hashes rejected; inherited baseline bytes unchanged",
            "external_calls": 0,
        }
    )
    protected_records = [
        {
            "path": path,
            "sha256": expected_sha,
            "bytes": (ROOT / path).stat().st_size if (ROOT / path).is_file() else 0,
            "mode": oct((ROOT / path).stat().st_mode & 0o777) if (ROOT / path).is_file() else None,
        }
        for path, expected_sha in protected_hashes.items()
    ]
    protected = {"protected_files": protected_records}
    if drift:
        blocked = {
            "status": "INCONCLUSIVE_SOURCE_DRIFT",
            "at_utc": utc(),
            "drift": drift,
            "pytest_started": False,
            "product_imported": False,
            "effective_protected_accounting": baseline_accounting,
        }
        (RUN / "checks-blocked.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 3

    # subprocess begins a fresh interpreter. Its bootstrap performs source/request checks,
    # scrubs env and installs socket/listener/worker deny guards before importing pytest.
    cold = [sys.executable, "-B", str(HARNESS), "--offline-tests", str(TESTS), str(state)]
    isolated_env = {
        key: value
        for key, value in env.items()
        if not any(
            token in key.upper()
            for token in (
                "API_KEY",
                "ACCESS_TOKEN",
                "BEARER",
                "SECRET",
                "OLLAMA_HOST",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
            )
        )
    }
    isolated_env.update(
        {
            "HOME": str(state / "home"),
            "AGK_ENV_FILE": str(state / "env.empty"),
            "AGK_CONFIG_FILE": str(ROOT / "config.yaml"),
            "AGK_AUTO_DISCOVER_LOCAL_MODELS": "false",
            "AGK_ALLOWED_ROOTS": str(state),
            "AGK_PATH_PROJECT_ROOT": str(state),
            "AGK_USAGE_DB": str(state / "usage.json"),
            "ANTIGRAVITY_VAULT_PATH": str(state / "vault"),
            "AGK_SESSION_BASE_DIR": str(state / "sessions"),
            "AGK_AUDIT_LOG_DIR": str(state / "audit"),
            "AGK_AUTH_PIN_HASH_FILE": str(state / "auth/pin-hash.json"),
            "AGK_AUTH_TOKEN_SECRET_FILE": str(state / "auth/token-secret"),
            "AGK_HOOK_VAULT_DIR": str(state / "hook-vault"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "IMP09C_PROTECTED_TEST_PATHS": json.dumps(sorted(protected_test_paths)),
            "IMP09C_FORCE_NEW_SELECTOR": "1",
            "IMP09C_SELECTOR_SCOPE": "final-gate-only",
        }
    )
    config_copy = state / "config/owned-config.yaml"
    config_copy.parent.mkdir(parents=True, exist_ok=True)
    config_copy.write_bytes((ROOT / "config.yaml").read_bytes())
    isolated_env["AGK_CONFIG_FILE"] = str(config_copy)
    (state / "env.empty").write_bytes(b"")
    checks = [capture(cold, name="cold-selector", env=isolated_env, invocation_id=run_id)]
    if checks[0].get("capture_mode") == "SIMULATED_CAPTURE" or checks[0].get("reused_success_receipt"):
        # Synthetic capture is useful for exercising main's fail-closed reduction, but it
        # must never be reported as a successful cold execution.
        checks[0]["exit_code"] = int(checks[0].get("exit_code") or 1)
        checks[0]["failure_verdict"] = "SIMULATED_CAPTURE_NOT_EXECUTION"
    if not isinstance(checks[0].get("exit_code"), int):
        raise ValueError("cold selector command receipt lacks an observed process exit code")
    if checks[0].get("sources_at_execution") != source_bound_before:
        raise ValueError("cold selector execution source snapshot differs from candidate start")
    if checks[0].get("sources_after_execution") != source_bound_before:
        raise ValueError("cold selector sources drifted during execution")
    if checks[0].get("argv") != cold or checks[0].get("cwd") != str(ROOT):
        raise ValueError("cold selector command argv/cwd differs from declared candidate execution")
    for check in checks:
        if check.get("capture_mode") == "SIMULATED_CAPTURE":
            check["exit_code"] = int(check.get("exit_code") or 1)
        check["attempt"] = str(check["attempt"])
    cold_attempt = RUN / checks[0]["attempt"]
    selector_link_path = cold_attempt / "selector-invocation.json"
    child_path: Path | None = None
    child_completion: dict[str, Any] = {}
    static_commands = [
        [
            sys.executable,
            "-B",
            "-m",
            "ruff",
            "check",
            "--no-cache",
            *[str(path) for path in STATIC_SOURCES],
        ],
        [
            sys.executable,
            "-B",
            "-m",
            "ruff",
            "format",
            "--check",
            "--no-cache",
            *[str(path) for path in STATIC_SOURCES],
        ],
        [
            sys.executable,
            "-B",
            "-m",
            "basedpyright",
            "--level",
            "error",
            *[str(path) for path in STATIC_SOURCES],
        ],
        [
            sys.executable,
            "-B",
            "-c",
            "from pathlib import Path; paths="
            + repr([str(p) for p in SOURCES])
            + "; [compile(Path(p).read_bytes(),p,'exec') for p in paths]; print('in-memory compile passed')",
        ],
    ]
    for index, command in enumerate(static_commands):
        check = capture(command, name=f"static-{index + 1}", env=isolated_env, invocation_id=run_id)
        check["attempt"] = str(check["attempt"])
        checks.append(check)
    cold_attempt = RUN / checks[0]["attempt"]
    selector_evidence_valid = False
    selector_evidence_errors: list[str] = []
    selector_nodeids: list[str] = []
    selector_result: dict[str, Any] = {"tests": 0, "selected": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    selector_chain: dict[str, Any]
    try:
        selector_chain = validate_selector_chain(RUN, cold_attempt, run_id, cold, expected_fg_nodeids())
    except Exception as exc:
        selector_chain = {
            "valid": False,
            "errors": [f"selector reducer exception: {type(exc).__name__}: {exc}"],
            "child_path": None,
            "counts": selector_result,
            "nodeids": [],
        }
    selector_evidence_valid = selector_chain.get("valid") is True and not selector_chain.get("errors")
    reducer_errors = selector_chain.get("errors", [])
    if not isinstance(reducer_errors, list):
        selector_evidence_errors.append("selector reducer returned malformed errors")
    else:
        selector_evidence_errors.extend(str(error) for error in reducer_errors)
    selector_nodeids = list(selector_chain.get("nodeids", []))
    raw_counts = selector_chain.get("counts", selector_result)
    if isinstance(raw_counts, dict):
        selector_result = dict(raw_counts)
    selector_nodeids = list(selector_chain.get("nodeids", []))
    resolved_child = selector_chain.get("child_path")
    child_path = resolved_child if isinstance(resolved_child, Path) else None
    completion_value = selector_chain.get("completion")
    child_completion = completion_value if isinstance(completion_value, dict) else {}
    if not selector_evidence_valid and not selector_evidence_errors:
        selector_evidence_errors.append("INCONCLUSIVE_CHILD_EVIDENCE: reducer rejected selector evidence")
    if checks[0].get("capture_mode") == "SIMULATED_CAPTURE":
        if "SIMULATED_CAPTURE_NOT_EXECUTION" not in selector_evidence_errors:
            selector_evidence_errors.append("SIMULATED_CAPTURE_NOT_EXECUTION")
        selector_chain["valid"] = False
        previous_errors = selector_chain.get("errors", [])
        previous_error_list = previous_errors if isinstance(previous_errors, list) else []
        selector_chain["errors"] = [
            *previous_error_list,
            *([] if "SIMULATED_CAPTURE_NOT_EXECUTION" in previous_error_list else ["SIMULATED_CAPTURE_NOT_EXECUTION"]),
        ]
        selector_evidence_errors = list(dict.fromkeys(selector_evidence_errors))
        selector_evidence_valid = False
    command_record = _json_object(cold_attempt / "command.json")
    if child_path is not None and selector_chain.get("parent_capture_mode") != "SIMULATED_CAPTURE":
        selector_result = dict(selector_chain.get("counts", selector_result))
    child_evidence_inventory = inventory_tree(child_path) if child_path is not None else None
    selector_chain["counts"] = selector_result

    if not selector_evidence_valid and child_path is not None:
        selector_failure_counts = dict(selector_chain.get("counts", {}))
        if (
            selector_chain.get("parent_capture_mode") == "SIMULATED_CAPTURE"
            and selector_failure_counts.get("selected", 0) == 0
        ):
            selector_failure_counts["selected"] = len(expected_fg_nodeids())
        selector_result = selector_failure_counts
        selector_chain["counts"] = selector_failure_counts
    # Driver post-capture evidence can only validate existing child output; it never creates it.
    child_observation = {
        "parent_invocation_id": run_id,
        "invocation_id": run_id,
        "parent_capture_path": cold_attempt.relative_to(RUN).as_posix(),
        "expected_selector_sha256": digest(TESTS),
        "parent_capture_id": cold_attempt.name,
        "child_invocation_id": child_path.name if child_path else None,
        "owned_output_path": child_path.relative_to(RUN).as_posix() if child_path else None,
        "command_receipt": command_record,
        "command_receipt_sha256": digest(cold_attempt / "command.json"),
        "command_exit_code": command_record.get("exit_code"),
        "child_completion": child_completion,
        "evidence_inventory": child_evidence_inventory,
        "selector_evidence_valid": selector_evidence_valid,
        "selector_evidence_errors": selector_evidence_errors,
        "source": (
            "INCONCLUSIVE_CHILD_EVIDENCE"
            if child_path is None
            else "SIMULATED_CAPTURE"
            if command_record.get("capture_mode") == "SIMULATED_CAPTURE"
            else "OBSERVED_CHILD_OUTPUT"
        ),
    }
    if checks[0].get("capture_mode") == "SIMULATED_CAPTURE":
        checks[0]["exit_code"] = int(checks[0].get("exit_code") or 1)
        checks[0]["failure_verdict"] = "SIMULATED_CAPTURE_NOT_EXECUTION"
        checks[0]["selector_evidence_errors"] = selector_evidence_errors
    elif not selector_evidence_valid:
        checks[0]["exit_code"] = int(checks[0]["exit_code"]) or 1
        checks[0]["failure_verdict"] = "INCONCLUSIVE_CHILD_EVIDENCE"
        checks[0]["selector_evidence_errors"] = selector_evidence_errors
    for check in checks:
        check["selected_nodeids"] = selector_nodeids if check.get("check_kind") == "cold-selector" else []
        check["selector_counts"] = selector_result if check.get("check_kind") == "cold-selector" else None
        if check.get("check_kind") == "cold-selector":
            check["selector_evidence_valid"] = selector_evidence_valid
            check["selector_evidence_errors"] = selector_evidence_errors
            check["selector_invocation"] = selector_link_path.relative_to(RUN).as_posix()
            check["child_invocation"] = child_path.relative_to(RUN).as_posix() if child_path else None
            check["selector_started_at_utc"] = child_completion.get("started_at_utc")
            check["selector_ended_at_utc"] = child_completion.get("finished_at_utc")
            check["selector_exit_code"] = child_completion.get("exit_code")
    protected_after = {rel: digest(ROOT / rel) for rel in protected_hashes}
    protected_changed = [rel for rel in protected_hashes if protected_after[rel] != protected_hashes[rel]]
    task_run_source_after = {str(path.relative_to(ROOT)): digest(path) for path in SOURCES}
    task_run_source_drift = {
        rel: {"before": start_sources.get(rel), "after": task_run_source_after.get(rel)}
        for rel in start_sources
        if start_sources.get(rel) != task_run_source_after.get(rel)
    }

    receipt: dict[str, Any] = {
        "task_id": TASK_ID,
        "invocation_id": run_id,
        "parent_invocation_id": run_id,
        "parent_capture_id": cold_attempt.name,
        "child_invocation_id": child_completion.get("child_invocation_id"),
        "status": "VERIFICATION_COMMANDS_RECORDED"
        if selector_evidence_valid
        and all(item["exit_code"] == 0 for item in checks)
        and not protected_changed
        and not task_run_source_drift
        else "INCONCLUSIVE_CHILD_EVIDENCE"
        if not selector_evidence_valid and not child_path
        else "INCONCLUSIVE_SELECTOR_EVIDENCE",
        "selector_invocation_id": run_id,
        "selector_invocation_source_sha256": start_sources,
        "selector_parent_capture_path": cold_attempt.relative_to(RUN).as_posix(),
        "started_at_utc": start_started,
        "finished_at_utc": utc(),
        "run_directory": str(RUN),
        "state_directory": str(state),
        "source_sha256_at_invocation_start": start_sources,
        "candidate_source_bound_before_cold_selector": source_bound_before,
        "cold_selector_sources_at_execution": checks[0].get("sources_at_execution"),
        "cold_selector_sources_after_execution": checks[0].get("sources_after_execution"),
        "protected_files_before": {
            "captured_at_utc": expected["captured_at_utc"],
            "files": [
                {key: record.get(key) for key in ("path", "bytes", "sha256", "expected_sha256", "match")}
                for record in expected_files
            ],
            "sha256": digest(RUN / "baseline/protected-before.json"),
        },
        "protected_current_check": {
            "checked_at_utc": start_started,
            "matched_paths": len(protected_hashes) - len(drift),
            "protected_paths": len(protected_hashes),
            "mismatches": drift,
        },
        "protected_files_after": protected_after,
        "protected_changed": protected_changed,
        "task_run_source_before": start_sources,
        "task_run_source_after": task_run_source_after,
        "task_run_source_drift": task_run_source_drift,
        "selector_evidence_valid": selector_evidence_valid,
        "selector_evidence_errors": selector_evidence_errors,
        "test_state_guarded_paths": sorted(protected_test_paths),
        "state_env_overrides_values_not_recorded": True,
        "test_state_guards": {
            "paths": sorted(protected_test_paths),
            "env_values_recorded": False,
            "changed_names": sorted(key for key, value in originals.items() if os.environ.get(key) != value),
        },
        "checks": checks,
        "all_exit_zero": all(item["exit_code"] == 0 for item in checks),
        "overall_valid": False,
        "selector_counts": selector_result,
        "selector_nodeids": selector_nodeids,
        "actual_external_http": 0,
        "actual_socket_connect": 0,
        "actual_socket_bind_listen": 0,
        "actual_worker_process": 0,
        "actual_uvicorn": 0,
        "actual_ollama": 0,
        "actual_inference": 0,
        "selector_evidence_source": "explicit_parent_child_receipt_chain",
        "selector_execution_provenance": child_observation["source"],
        "simulated_capture_used_for_receipt": child_observation["source"] == "SIMULATED_CAPTURE",
        "child_observation": child_observation,
        "selector_parent_dispatch_path": (cold_attempt / "parent-dispatch.json").relative_to(RUN).as_posix(),
        "selector_child_output_path": child_path.relative_to(RUN).as_posix() if child_path else None,
    }
    target = RUN / f"checks-{run_id}.json"
    delivery: dict[str, Any] = {"valid": False}
    delivery_valid = False
    try:
        alias_correction = write_parent_alias_correction(RUN)
        delivery = write_delivery_artifacts(RUN, selector_counts=selector_result)
        counts_path = RUN / "counts.json"
        inventory_path = RUN / "delivery-inventory.json"
        written_counts = _json_object(counts_path)
        written_inventory = _json_object(inventory_path)
        expected_counts = delivery.get("counts")
        current_inventory = inventory_tree(RUN, excluded=frozenset({"delivery-inventory.json"}))
        if (
            written_counts != expected_counts
            or written_inventory.get("files") != current_inventory["files"]
            or written_inventory.get("symlinks") != current_inventory["symlinks"]
        ):
            raise ValueError("delivery writer output does not match its on-disk inventory/counts")
        if delivery.get("counts_sha256") != digest(counts_path) or delivery.get("inventory_sha256") != digest(
            inventory_path
        ):
            raise ValueError("delivery writer receipt hash does not bind the written artifacts")
        delivery_valid = True
        receipt["delivery_artifacts"] = delivery
        receipt["parent_alias_correction"] = alias_correction
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        receipt["delivery_artifacts"] = {"valid": False, "error": f"{type(exc).__name__}: {exc}"}
        evidence_errors = receipt.get("selector_evidence_errors")
        if isinstance(evidence_errors, list):
            evidence_errors.append(f"delivery artifact writer: {type(exc).__name__}: {exc}")
        else:
            receipt["selector_evidence_errors"] = [f"delivery artifact writer: {type(exc).__name__}: {exc}"]
        receipt["selector_evidence_valid"] = False
        receipt["overall_valid"] = False
        receipt["exit_code"] = 1
    receipt["checks_artifact_path"] = target.relative_to(RUN).as_posix()

    all_exit_zero = bool(receipt.get("all_exit_zero")) and not bool(receipt.get("simulated_capture_used_for_receipt"))
    receipt["all_exit_zero"] = all_exit_zero
    selector_chain_for_reduction = dict(selector_chain)
    final_errors = receipt.get("selector_evidence_errors")
    selector_chain_for_reduction["errors"] = (
        list(final_errors) if isinstance(final_errors, list) else ["selector evidence errors malformed"]
    )
    final_reduction = reduce_final_gate(
        selector_chain=selector_chain_for_reduction,
        all_exit_zero=bool(all_exit_zero),
        protected_changed=protected_changed,
        source_drift=task_run_source_drift,
        delivery_valid=delivery_valid,
        expected_selected=len(expected_fg_nodeids()),
    )
    receipt["final_reduction"] = final_reduction
    receipt["overall_valid"] = final_reduction["valid"] is True
    receipt["status"] = (
        "VERIFICATION_COMMANDS_RECORDED" if receipt["overall_valid"] else "INCONCLUSIVE_DELIVERY_OR_SELECTOR_EVIDENCE"
    )
    receipt["exit_code"] = 0 if receipt["overall_valid"] else 1
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    seal = {
        "schema": "ssak.imp09c.closeout.artifact-manifest.v1",
        "task_id": TASK_ID,
        "run_id": RUN.name,
        "sealed_at_utc": utc(),
        "files": inventory_tree(RUN)["files"],
        "symlinks": inventory_tree(RUN)["symlinks"],
        "checks_receipt": {"path": target.relative_to(RUN).as_posix(), "sha256": digest(target)},
        "worklog": {"path": "worklog.jsonl", "sha256": digest(RUN / "worklog.jsonl")},
    }
    seal_path = RUN / "artifact-manifest.json"
    seal_path.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "receipt": target.relative_to(RUN).as_posix(),
                "checks": [{"exit_code": item["exit_code"], "attempt": str(item["attempt"])} for item in checks],
                "protected_changed": protected_changed,
                "overall_valid": receipt["overall_valid"],
                "delivery_artifacts": receipt["delivery_artifacts"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if receipt["overall_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
