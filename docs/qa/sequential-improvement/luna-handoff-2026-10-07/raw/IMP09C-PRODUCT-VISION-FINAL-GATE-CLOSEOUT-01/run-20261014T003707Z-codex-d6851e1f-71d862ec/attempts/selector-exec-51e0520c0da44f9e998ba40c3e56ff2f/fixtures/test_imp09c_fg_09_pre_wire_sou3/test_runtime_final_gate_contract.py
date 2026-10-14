from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.message import Message
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

h = import_module("run_harness")
r = import_module("runtime_adapter")
driver = cast(Any, import_module("run_offline_prechecks"))
bridge = import_module("test_runtime_bridge_contract")
RUN = Path(__file__).resolve().parent
ROOT = h.resolve_repository_root()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chain(tmp_path: Path) -> tuple[Path, Path, list[str], list[str]]:
    run = tmp_path / "run"
    attempts = run / "attempts"
    attempts.mkdir(parents=True)
    original_run, original_attempts = driver.RUN, driver.ATTEMPTS
    parent = attempts / "cold-selector-fixture"
    child = attempts / "selector-exec-fixture"
    child.mkdir(parents=True)
    setattr(driver, "RUN", run)
    setattr(driver, "ATTEMPTS", attempts)
    original_tests, original_harness = driver.TESTS, driver.HARNESS
    setattr(driver, "TESTS", (RUN / "test_runtime_final_gate_contract.py").resolve())
    setattr(driver, "HARNESS", (RUN / "run_harness.py").resolve())
    binding = run / "execution-binding.json"
    binding.write_bytes(b"synthetic immutable binding")
    binding_sha = driver.digest(binding)
    expected = driver.expected_fg_nodeids()
    argv = [sys.executable, "-B", str(driver.HARNESS), "--offline-tests", str(driver.TESTS), str(run / "offline-state")]
    source = {str(path.relative_to(ROOT)): driver.digest(path) for path in driver.SOURCES}
    start_time = "2026-10-13T00:00:00+00:00"
    dispatch_time = "2026-10-13T00:00:01+00:00"
    child_time = "2026-10-13T00:00:02+00:00"
    finish_time = "2026-10-13T00:00:03+00:00"
    parent_finish = "2026-10-13T00:00:04+00:00"
    capture_start = {
        "capture_id": parent.name,
        "invocation_id": "fixture-parent",
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": start_time,
        "sources_at_execution": source,
        "expected_nodeids": expected,
    }
    _write_json(parent / "capture-start.json", capture_start)
    invocation = {
        "parent_invocation_id": "fixture-parent",
        "parent_capture_id": parent.name,
        "owned_output_path": child.relative_to(run).as_posix(),
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": start_time,
        "source_sha256_at_dispatch": source,
        "expected_nodeids": expected,
    }
    _write_json(parent / "selector-invocation.json", invocation)
    dispatch = {
        "parent_invocation_id": "fixture-parent",
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(run).as_posix(),
        "parent_capture_start_sha256": "",
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": dispatch_time,
        "source_sha256_at_dispatch": source,
        "selector_sha256_at_dispatch": driver.digest(driver.TESTS),
        "harness_sha256_at_dispatch": driver.digest(driver.HARNESS),
        "selector_invocation_sha256": driver.digest(parent / "selector-invocation.json"),
        "expected_nodeids": expected,
    }
    parent_start_sha = driver.digest(parent / "capture-start.json")
    dispatch["parent_capture_start_sha256"] = parent_start_sha
    _write_json(parent / "parent-dispatch.json", dispatch)
    parent_dispatch_sha = driver.digest(parent / "parent-dispatch.json")
    command = {
        "capture_id": parent.name,
        "invocation_id": "fixture-parent",
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": start_time,
        "finished_at_utc": parent_finish,
        "exit_code": 0,
        "sources_at_execution": source,
        "parent_dispatch_sha256": parent_dispatch_sha,
        "parent_capture_start_sha256": parent_start_sha,
        "sources_after_execution": source,
        "expected_nodeids": expected,
        "capture_mode": "OBSERVED_SUBPROCESS",
    }
    _write_json(parent / "command.json", command)
    dispatch_child = {
        "parent_invocation_id": "fixture-parent",
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(run).as_posix(),
        "parent_dispatch_sha256": parent_dispatch_sha,
        "parent_capture_start_sha256": parent_start_sha,
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": child_time,
        "selector_sha256_at_dispatch": driver.digest(driver.TESTS),
        "harness_sha256_at_dispatch": driver.digest(driver.HARNESS),
        "source_sha256_at_dispatch": source,
        "expected_nodeids": expected,
        "capture_mode": "OBSERVED_SUBPROCESS",
    }
    _write_json(child / "dispatch.json", dispatch_child)
    dispatch_sha = driver.digest(child / "dispatch.json")
    child_link = {
        "parent_invocation_id": "fixture-parent",
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(run).as_posix(),
        "parent_dispatch_sha256": parent_dispatch_sha,
        "parent_capture_start_sha256": parent_start_sha,
    }
    _write_json(child / "parent-link.json", child_link)
    _write_json(
        child / "precheck.json",
        {
            "status": "READY",
            "execution_binding_sha256": binding_sha,
            "source_sha256_at_dispatch": source,
            "expected_nodeids": expected,
        },
    )
    _write_json(
        child / "pytest-started.json",
        {
            "source_sha256_at_dispatch": source,
            "expected_nodeids": expected,
            "selector": str(driver.TESTS),
            "selector_sha256": driver.digest(driver.TESTS),
            "execution_binding_sha256": binding_sha,
            "dispatch_sha256": dispatch_sha,
            "parent_invocation_id": "fixture-parent",
            "parent_capture_id": parent.name,
            "child_invocation_id": child.name,
        },
    )
    selected = [f"{driver.TESTS}::{node}" for node in expected]
    result = {
        "source_sha256_at_dispatch": source,
        "expected_nodeids": expected,
        "selector": str(driver.TESTS),
        "selector_sha256": driver.digest(driver.TESTS),
        "dispatch_sha256": dispatch_sha,
        "execution_binding_sha256": binding_sha,
        "precheck_status": "READY",
        "parent_invocation_id": "fixture-parent",
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "pytest_started": True,
        "product_imported": False,
        "selected_nodeids": selected,
        "exit_code": 0,
        "started_at_utc": child_time,
    }
    _write_json(child / "pytest-result.json", result)
    _write_json(
        child / "state-guard.json",
        {
            "source_sha256_at_dispatch": source,
            "violations": [],
            "before_sha256": {"protected": "abc"},
            "after_sha256": {"protected": "abc"},
            "guard_counters": {"http": 0, "socket": 0, "worker": 0},
        },
    )
    junit = ET.Element("testsuite", tests=str(len(expected)), failures="0", errors="0", skipped="0")
    for node in expected:
        ET.SubElement(junit, "testcase", name=node, classname="test_runtime_final_gate_contract")
    ET.ElementTree(junit).write(child / "junit.xml", encoding="utf-8", xml_declaration=True)
    _write_json(
        child / "completion.json",
        {
            "parent_invocation_id": "fixture-parent",
            "parent_capture_id": parent.name,
            "child_invocation_id": child.name,
            "owned_output_path": child.relative_to(run).as_posix(),
            "parent_dispatch_sha256": parent_dispatch_sha,
            "parent_capture_start_sha256": parent_start_sha,
            "dispatch_sha256": dispatch_sha,
            "source_sha256_at_dispatch": source,
            "expected_nodeids": expected,
            "started_at_utc": child_time,
            "finished_at_utc": finish_time,
            "exit_code": 0,
        },
    )
    setattr(driver, "RUN", original_run)
    setattr(driver, "ATTEMPTS", original_attempts)
    setattr(driver, "TESTS", original_tests)
    setattr(driver, "HARNESS", original_harness)
    return run, parent, expected, argv


def test_imp09c_fg_01_driver_success_requires_explicit_parent_child_receipts(tmp_path: Path) -> None:
    run, parent, expected, argv = _chain(tmp_path)
    evidence = driver.validate_selector_chain(run, parent, "fixture-parent", argv, expected)
    assert evidence["valid"] is True
    assert evidence["counts"]["selected"] == len(expected)
    assert evidence["child_path"].parent == run / "attempts"


def test_imp09c_fg_01_final_reducer_rejects_errors_even_if_chain_claims_valid() -> None:
    evidence = {"valid": True, "errors": [], "counts": {"selected": 2}}
    result = driver.reduce_final_gate(
        selector_chain={**evidence, "delivery_errors": ["injected final chain error"]},
        all_exit_zero=True,
        protected_changed=[],
        source_drift={},
        delivery_valid=True,
        expected_selected=2,
    )
    assert result["valid"] is False
    assert result["selector_evidence_valid"] is False
    assert "injected final chain error" in result["errors"]


def test_imp09c_fg_02_missing_ambiguous_and_stale_children_fail_closed(tmp_path: Path) -> None:
    run, parent, expected, argv = _chain(tmp_path / "missing")
    child = run / driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
    (child / "completion.json").unlink()
    assert driver.validate_selector_chain(run, parent, "fixture-parent", argv, expected)["valid"] is False
    run2, parent2, expected2, argv2 = _chain(tmp_path / "stale")
    dispatch_path = parent2 / "parent-dispatch.json"
    dispatch = driver._json_object(dispatch_path)
    dispatch["child_invocation_id"] = "selector-exec-from-another-invocation"
    _write_json(dispatch_path, dispatch)
    assert driver.validate_selector_chain(run2, parent2, "fixture-parent", argv2, expected2)["valid"] is False


def test_imp09c_fg_03_zero_failure_error_skip_and_receipt_mismatch_fail_closed(tmp_path: Path) -> None:
    for scenario in ("zero", "failure", "error", "skip", "mismatch"):
        run, parent, expected, argv = _chain(tmp_path / scenario)
        child = run / driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
        result_path = child / "pytest-result.json"
        result = driver._json_object(result_path)
        junit_path = child / "junit.xml"
        if scenario == "zero":
            result["selected_nodeids"] = []
            junit_path.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
        else:
            tree = ET.parse(junit_path)
            if scenario == "failure":
                ET.SubElement(tree.getroot()[0], "failure", message="synthetic failure")
            elif scenario == "error":
                ET.SubElement(tree.getroot()[0], "error", message="synthetic error")
            elif scenario == "skip":
                ET.SubElement(tree.getroot()[0], "skipped", message="synthetic skip")
            else:
                result["selector_sha256"] = "0" * 64
            tree.write(junit_path, encoding="utf-8", xml_declaration=True)
        _write_json(result_path, result)
        assert driver.validate_selector_chain(run, parent, "fixture-parent", argv, expected)["valid"] is False, scenario


def _main_fixture(
    tmp_path: Path, *, omit_child: bool = False
) -> tuple[Path, Path, list[str], list[str], dict[str, str]]:
    run, parent, expected, argv = _chain(tmp_path)
    (run / "worklog.jsonl").write_bytes(b"")
    # Main tests use a synthetic protection baseline in an isolated temporary run.
    (run / "baseline/protected-before.json").parent.mkdir(parents=True, exist_ok=True)
    (run / "baseline/protected-before.json").write_text(
        json.dumps({"captured_at_utc": "2026-10-13T00:00:00+00:00", "files": []}), encoding="utf-8"
    )
    for name in (
        "endpoint-contract.json",
        "budgets.json",
        "request.json",
        "request.binding.json",
        "runtime-bridge-contract.json",
        "execution-binding.json",
    ):
        (run / name).write_bytes((RUN / name).read_bytes() if (RUN / name).exists() else b"fixture")
    shutil.copyfile(RUN / "baseline/additional-runtime-sources.json", run / "baseline/additional-runtime-sources.json")
    shutil.copyfile(
        RUN / "baseline/additional-readiness-source.json", run / "baseline/additional-readiness-source.json"
    )
    child_rel = driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
    child = run / child_rel
    child_hashes = {p.relative_to(child).as_posix(): driver.digest(p) for p in child.rglob("*") if p.is_file()}
    shutil.rmtree(child)
    return run, parent, expected, argv, child_hashes


def _run_main_mocked(
    run: Path,
    parent: Path,
    expected: list[str],
    monkeypatch: Any,
    *,
    omit_child: bool = False,
    inject_reducer_error: bool = False,
    inject_binding_mismatch: bool = False,
    inject_guard_violation: bool = False,
) -> tuple[int, dict[str, Any], Path]:
    original_run, original_attempts = driver.RUN, driver.ATTEMPTS
    original_tests, original_harness = driver.TESTS, driver.HARNESS
    # Exercise the very same imported driver module the test suite uses, rather than a
    # second copy whose globals would diverge from the monkeypatched capture path.
    original_selector_module = driver
    child_rel = driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
    child = run / child_rel
    cold_calls = 0
    static_calls = 0
    child_hashes_after_capture: dict[str, str] = {}
    checks_before = set(run.glob("checks-*.json"))
    source_map = {str(path.relative_to(ROOT)): driver.digest(path) for path in driver.SOURCES}
    if (parent / "capture-start.json").exists():
        (parent / "capture-start.json").unlink()
    if (parent / "parent-dispatch.json").exists():
        (parent / "parent-dispatch.json").unlink()
    if (parent / "command.json").exists():
        (parent / "command.json").unlink()

    def mocked_capture(
        command: list[str], *, name: str, env: dict[str, str], invocation_id: str, cwd: Path = ROOT
    ) -> dict[str, Any]:
        nonlocal cold_calls, static_calls
        if name != "cold-selector":
            static_calls += 1
            attempt = run / "attempts" / f"{name}-simulated"
            attempt.mkdir(parents=True, exist_ok=False)
            command_record = {
                "check_kind": name,
                "argv": command,
                "cwd": str(cwd),
                "started_at_utc": "2026-10-13T00:00:00+00:00",
                "finished_at_utc": "2026-10-13T00:00:04+00:00",
                "exit_code": 0,
                "invocation_id": invocation_id,
                "capture_id": attempt.name,
                "sources_at_execution": source_map,
                "sources_after_execution": source_map,
                "capture_mode": "SIMULATED_CAPTURE",
                "stdout": {
                    "path": (attempt / "stdout.txt").relative_to(run).as_posix(),
                    "bytes": 0,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                },
                "stderr": {
                    "path": (attempt / "stderr.txt").relative_to(run).as_posix(),
                    "bytes": 0,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                },
            }
            (attempt / "stdout.txt").write_bytes(b"")
            (attempt / "stderr.txt").write_bytes(b"")
            _write_json(attempt / "command.json", command_record)
            return {"attempt": attempt.relative_to(run).as_posix(), **command_record}
        cold_calls += 1
        _write_json(
            parent / "capture-start.json",
            {
                "schema": "ssak.imp09c.parent-capture-start.v1",
                "capture_id": parent.name,
                "invocation_id": invocation_id,
                "argv": command,
                "cwd": str(cwd),
                "started_at_utc": "2026-10-13T00:00:00+00:00",
                "sources_at_execution": source_map,
                "expected_nodeids": expected,
            },
        )
        invocation_record = {
            **driver._json_object(parent / "selector-invocation.json"),
            "parent_invocation_id": invocation_id,
            "parent_capture_id": parent.name,
            "argv": command,
            "cwd": str(cwd),
            "started_at_utc": "2026-10-13T00:00:00+00:00",
            "source_sha256_at_dispatch": source_map,
            "expected_nodeids": expected,
        }
        _write_json(parent / "selector-invocation.json", invocation_record)
        parent_capture_start_sha = driver.digest(parent / "capture-start.json")
        dispatch = {
            "parent_invocation_id": invocation_id,
            "parent_capture_id": parent.name,
            "child_invocation_id": child.name,
            "owned_output_path": child.relative_to(run).as_posix(),
            "parent_capture_start_sha256": parent_capture_start_sha,
            "argv": command,
            "cwd": str(cwd),
            "source_sha256_at_dispatch": source_map,
            "selector_sha256_at_dispatch": driver.digest(driver.TESTS),
            "harness_sha256_at_dispatch": driver.digest(driver.HARNESS),
            "selector_invocation_sha256": driver.digest(parent / "selector-invocation.json"),
            "started_at_utc": "2026-10-13T00:00:01+00:00",
            "expected_nodeids": expected,
        }
        _write_json(parent / "parent-dispatch.json", dispatch)
        parent_dispatch_sha = driver.digest(parent / "parent-dispatch.json")
        if not omit_child:
            child.mkdir(parents=True, exist_ok=False)
            _refresh_chain_receipts(child, parent, invocation_id, command, source_map)
            result_path = child / "pytest-result.json"
            result_value = driver._json_object(result_path)
            if inject_binding_mismatch:
                result_value["execution_binding_sha256"] = "0" * 64
                _write_json(result_path, result_value)
        if inject_guard_violation:
            guard_path = child / "state-guard.json"
            guard_value = driver._json_object(guard_path)
            guard_value["violations"] = ["synthetic protected drift"]
            _write_json(guard_path, guard_value)
        if child.exists():
            child_hashes_after_capture.update(
                {path.relative_to(child).as_posix(): driver.digest(path) for path in child.rglob("*") if path.is_file()}
            )

        command_record = {
            "check_kind": name,
            "argv": command,
            "cwd": str(cwd),
            "started_at_utc": "2026-10-13T00:00:00+00:00",
            "finished_at_utc": "2026-10-13T00:00:04+00:00",
            "exit_code": 0,
            "invocation_id": invocation_id,
            "capture_id": parent.name,
            "parent_dispatch_sha256": parent_dispatch_sha,
            "parent_capture_start_sha256": parent_capture_start_sha,
            "sources_at_execution": source_map,
            "sources_after_execution": source_map,
            "expected_nodeids": expected,
            "capture_mode": "SIMULATED_CAPTURE",
        }
        _write_json(parent / "command.json", command_record)
        return {"attempt": parent.relative_to(run).as_posix(), **command_record}

    if inject_reducer_error:
        actual_reducer = original_selector_module.validate_selector_chain

        def reducer_with_error(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = actual_reducer(*args, **kwargs)
            errors = result.get("errors")
            result["errors"] = [*(errors if isinstance(errors, list) else []), "injected reducer error"]
            result["valid"] = True
            return result

        monkeypatch.setitem(vars(original_selector_module), "validate_selector_chain", reducer_with_error)
    monkeypatch.setitem(vars(original_selector_module), "ROOT", ROOT)
    monkeypatch.setitem(vars(original_selector_module), "capture", mocked_capture)
    monkeypatch.setitem(vars(original_selector_module), "expected_fg_nodeids", lambda: expected)
    monkeypatch.setitem(
        vars(original_selector_module), "digest", lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    )
    monkeypatch.setitem(vars(original_selector_module.time), "monotonic", lambda: 1.0)
    original_utc_module = original_selector_module.utc
    monkeypatch.setitem(vars(original_selector_module), "utc", lambda: "2026-10-13T00:00:00+00:00")
    monkeypatch.setitem(vars(driver), "RUN", run)
    monkeypatch.setitem(vars(driver), "ATTEMPTS", run / "attempts")
    monkeypatch.setitem(vars(driver), "ROOT", ROOT)
    monkeypatch.setitem(vars(driver), "capture", mocked_capture)
    monkeypatch.setitem(vars(driver), "expected_fg_nodeids", lambda: expected)
    monkeypatch.setitem(vars(driver), "digest", lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setitem(vars(driver.time), "monotonic", lambda: 1.0)
    original_now = driver.utc
    monkeypatch.setitem(vars(driver), "utc", lambda: "2026-10-13T00:00:00+00:00")
    code = original_selector_module.main()
    receipts = sorted(set(run.glob("checks-*.json")) - checks_before)
    assert len(receipts) == 1
    receipt_path = receipts[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["mock_capture_child_sha256"] = dict(child_hashes_after_capture)
    assert cold_calls == 1 and static_calls == 4
    assert all(item.get("capture_mode") == "SIMULATED_CAPTURE" for item in receipt["checks"])
    assert all((run / item["attempt"] / "command.json").is_file() for item in receipt["checks"])
    monkeypatch.setitem(vars(driver), "utc", original_now)
    monkeypatch.setitem(vars(original_selector_module), "utc", original_utc_module)
    monkeypatch.setitem(vars(driver), "RUN", original_run)
    monkeypatch.setitem(vars(driver), "ATTEMPTS", original_attempts)
    monkeypatch.setitem(vars(driver), "TESTS", original_tests)
    monkeypatch.setitem(vars(driver), "HARNESS", original_harness)
    return code, receipt, receipt_path


def _refresh_chain_receipts(
    child: Path, parent: Path, invocation_id: str, argv: list[str], source_map: dict[str, str]
) -> None:
    binding_sha = driver.digest(driver.RUN / "execution-binding.json")
    parent_start_sha = driver.digest(parent / "capture-start.json")
    invocation = driver._json_object(parent / "selector-invocation.json")
    invocation.update(
        {
            "parent_invocation_id": invocation_id,
            "parent_capture_id": parent.name,
            "argv": argv,
            "cwd": str(ROOT),
            "started_at_utc": "2026-10-13T00:00:00+00:00",
            "source_sha256_at_dispatch": source_map,
            "expected_nodeids": driver.expected_fg_nodeids(),
        }
    )
    _write_json(parent / "selector-invocation.json", invocation)
    dispatch = {
        "parent_invocation_id": invocation_id,
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(driver.RUN).as_posix(),
        "parent_capture_start_sha256": parent_start_sha,
        "argv": argv,
        "cwd": str(ROOT),
        "source_sha256_at_dispatch": source_map,
        "selector_sha256_at_dispatch": driver.digest(driver.TESTS),
        "harness_sha256_at_dispatch": driver.digest(driver.HARNESS),
        "selector_invocation_sha256": driver.digest(parent / "selector-invocation.json"),
        "expected_nodeids": driver.expected_fg_nodeids(),
        "started_at_utc": "2026-10-13T00:00:01+00:00",
    }
    _write_json(parent / "parent-dispatch.json", dispatch)
    parent_dispatch_sha = driver.digest(parent / "parent-dispatch.json")
    # Test capture models the child writing its own output before the outer command returns.
    child_dispatch = {
        "parent_invocation_id": invocation_id,
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(driver.RUN).as_posix(),
        "parent_dispatch_sha256": parent_dispatch_sha,
        "parent_capture_start_sha256": parent_start_sha,
        "argv": argv,
        "cwd": str(ROOT),
        "started_at_utc": "2026-10-13T00:00:02+00:00",
        "selector_sha256_at_dispatch": driver.digest(driver.TESTS),
        "source_sha256_at_dispatch": source_map,
        "expected_nodeids": driver.expected_fg_nodeids(),
        "capture_mode": "SIMULATED_CAPTURE",
        "harness_sha256_at_dispatch": driver.digest(driver.HARNESS),
    }
    _write_json(child / "dispatch.json", child_dispatch)
    child_dispatch_sha = driver.digest(child / "dispatch.json")
    link = {
        "parent_invocation_id": invocation_id,
        "parent_capture_id": parent.name,
        "child_invocation_id": child.name,
        "owned_output_path": child.relative_to(driver.RUN).as_posix(),
        "parent_dispatch_sha256": parent_dispatch_sha,
        "parent_capture_start_sha256": parent_start_sha,
        "source_sha256_at_dispatch": source_map,
        "expected_nodeids": driver.expected_fg_nodeids(),
    }
    _write_json(child / "parent-link.json", link)
    _write_json(
        child / "precheck.json",
        {
            "status": "READY",
            "execution_binding_sha256": binding_sha,
            "source_sha256_at_dispatch": source_map,
            "expected_nodeids": driver.expected_fg_nodeids(),
        },
    )
    _write_json(
        child / "pytest-started.json",
        {
            "started_at_utc": "2026-10-13T00:00:02+00:00",
            "source_sha256_at_dispatch": source_map,
            "expected_nodeids": driver.expected_fg_nodeids(),
            "selector": str(driver.TESTS),
            "selector_sha256": driver.digest(driver.TESTS),
            "execution_binding_sha256": binding_sha,
            "dispatch_sha256": child_dispatch_sha,
            "parent_invocation_id": invocation_id,
            "parent_capture_id": parent.name,
            "child_invocation_id": child.name,
        },
    )
    selected = [f"{driver.TESTS}::{node}" for node in driver.expected_fg_nodeids()]
    _write_json(
        child / "pytest-result.json",
        {
            "started_at_utc": "2026-10-13T00:00:02+00:00",
            "source_sha256_at_dispatch": source_map,
            "expected_nodeids": driver.expected_fg_nodeids(),
            "selector": str(driver.TESTS),
            "selector_sha256": driver.digest(driver.TESTS),
            "dispatch_sha256": child_dispatch_sha,
            "execution_binding_sha256": binding_sha,
            "precheck_status": "READY",
            "parent_invocation_id": invocation_id,
            "parent_capture_id": parent.name,
            "child_invocation_id": child.name,
            "pytest_started": True,
            "product_imported": False,
            "selected_nodeids": selected,
            "exit_code": 0,
        },
    )
    junit = ET.Element("testsuite", tests=str(len(selected)), failures="0", errors="0", skipped="0")
    for node in driver.expected_fg_nodeids():
        ET.SubElement(junit, "testcase", name=node, classname="test_runtime_final_gate_contract")
    ET.ElementTree(junit).write(child / "junit.xml", encoding="utf-8", xml_declaration=True)
    _write_json(
        child / "state-guard.json",
        {
            "source_sha256_at_dispatch": source_map,
            "violations": [],
            "before_sha256": {"protected": "same"},
            "after_sha256": {"protected": "same"},
            "guard_counters": {"http": 0, "socket": 0, "worker": 0},
        },
    )
    _write_json(
        child / "completion.json",
        {
            **link,
            "dispatch_sha256": child_dispatch_sha,
            "started_at_utc": "2026-10-13T00:00:02+00:00",
            "finished_at_utc": "2026-10-13T00:00:03+00:00",
            "exit_code": 0,
        },
    )


def test_imp09c_fg_04_main_executes_real_driver_with_mocked_capture(tmp_path: Path, monkeypatch: Any) -> None:
    run, parent, expected, _, before = _main_fixture(tmp_path / "success")
    child = run / driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
    code, receipt, _ = _run_main_mocked(run, parent, expected, monkeypatch)
    assert code != 0, receipt
    assert receipt["selector_evidence_errors"] == ["SIMULATED_CAPTURE_NOT_EXECUTION"]
    assert receipt["selector_evidence_valid"] is False
    assert receipt["selector_counts"]["selected"] == len(expected)
    assert receipt["selector_execution_provenance"] == "SIMULATED_CAPTURE"
    assert receipt["simulated_capture_used_for_receipt"] is True
    assert receipt["checks"][0]["exit_code"] == 1
    assert receipt["checks"][0]["failure_verdict"] == "SIMULATED_CAPTURE_NOT_EXECUTION"
    assert receipt["overall_valid"] is False
    assert receipt["all_exit_zero"] is False
    assert receipt["final_reduction"]["valid"] is False
    assert not receipt["delivery_artifacts"].get("error")
    assert receipt["mock_capture_child_sha256"]
    assert {p.relative_to(child).as_posix(): driver.digest(p) for p in child.rglob("*") if p.is_file()} == receipt[
        "mock_capture_child_sha256"
    ]
    assert len(receipt["checks"]) == 5
    assert [item["check_kind"] for item in receipt["checks"]] == [
        "cold-selector",
        "static-1",
        "static-2",
        "static-3",
        "static-4",
    ]
    assert len({item["attempt"] for item in receipt["checks"]}) == 5
    counts = json.loads((run / "counts.json").read_text(encoding="utf-8"))
    assert counts["cases"]["selected"] == len(expected)
    assert (run / "artifact-manifest.json").is_file()


def test_imp09c_fg_04_main_mismatched_binding_and_guard_fail_closed(tmp_path: Path, monkeypatch: Any) -> None:
    run, parent, expected, _, _ = _main_fixture(tmp_path / "mismatch")
    code, receipt, _ = _run_main_mocked(run, parent, expected, monkeypatch, inject_binding_mismatch=True)
    assert code != 0 and receipt["selector_evidence_valid"] is False
    assert any("pytest result selector/binding" in error for error in receipt["selector_evidence_errors"])
    run2, parent2, expected2, _, _ = _main_fixture(tmp_path / "guard")
    code2, receipt2, _ = _run_main_mocked(run2, parent2, expected2, monkeypatch, inject_guard_violation=True)
    assert code2 != 0 and receipt2["selector_evidence_valid"] is False
    assert any(
        "guard" in error and error != "SIMULATED_CAPTURE_NOT_EXECUTION"
        for error in receipt2["selector_evidence_errors"]
    )


def test_imp09c_fg_04_main_existing_child_is_read_only(tmp_path: Path, monkeypatch: Any) -> None:
    run, parent, expected, _, _ = _main_fixture(tmp_path / "existing")
    child = run / driver._json_object(parent / "selector-invocation.json")["owned_output_path"]
    code, receipt, _ = _run_main_mocked(run, parent, expected, monkeypatch)
    after = {p.relative_to(child).as_posix(): driver.digest(p) for p in child.rglob("*") if p.is_file()}
    assert code != 0 and receipt["selector_evidence_valid"] is False
    assert after.keys() == receipt["mock_capture_child_sha256"].keys()
    assert after == receipt["mock_capture_child_sha256"]
    assert receipt["checks"][0]["exit_code"] == 1
    assert receipt["checks"][0]["failure_verdict"] == "SIMULATED_CAPTURE_NOT_EXECUTION"
    assert after["junit.xml"] == receipt["mock_capture_child_sha256"]["junit.xml"]


def test_imp09c_fg_04_main_missing_child_and_reducer_error_fail_closed(tmp_path: Path, monkeypatch: Any) -> None:
    run, parent, expected, _, _ = _main_fixture(tmp_path / "missing", omit_child=True)
    code, receipt, _ = _run_main_mocked(run, parent, expected, monkeypatch, omit_child=True)
    assert code != 0 and receipt["selector_evidence_valid"] is False
    assert receipt["selector_execution_provenance"] == "INCONCLUSIVE_CHILD_EVIDENCE"
    assert receipt["child_observation"]["owned_output_path"] is None
    assert receipt["checks"][0]["exit_code"] == 1
    run2, parent2, expected2, _, _ = _main_fixture(tmp_path / "error")
    code2, receipt2, _ = _run_main_mocked(run2, parent2, expected2, monkeypatch, inject_reducer_error=True)
    assert code2 != 0 and receipt2["selector_evidence_valid"] is False
    assert receipt2["final_reduction"]["valid"] is False
    assert receipt2["final_reduction"]["errors"]


def inventory_tree(root: Path) -> dict[str, list[dict[str, Any]]]:
    return driver.inventory_tree(root)


def aggregate_invocations(records: list[dict[str, Any]]) -> dict[str, Any]:
    return driver.aggregate_invocations(records)


def test_imp09c_fg_10_main_owns_inventory_and_counts_writer(tmp_path: Path, monkeypatch: Any) -> None:
    run, parent, expected, _, _ = _main_fixture(tmp_path / "delivery")
    code, receipt, _ = _run_main_mocked(run, parent, expected, monkeypatch)
    assert code != 0, receipt
    assert receipt["selector_evidence_valid"] is False
    assert receipt["final_reduction"]["delivery_valid"] is True
    assert receipt["final_reduction"]["valid"] is False
    assert receipt["delivery_artifacts"]["counts"]["cases"]["selected"] == len(expected)
    assert (run / "counts.json").is_file() and (run / "artifact-manifest.json").is_file()
    written_counts = json.loads((run / "counts.json").read_text(encoding="utf-8"))
    assert written_counts == receipt["delivery_artifacts"]["counts"]
    delivery_path = run / receipt["delivery_artifacts"]["inventory_path"]
    assert delivery_path.name == "delivery-inventory.json"
    assert driver.digest(delivery_path) == receipt["delivery_artifacts"]["inventory_sha256"]
    manifest = json.loads((run / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"] == driver.inventory_tree(run)["files"]
    assert manifest["symlinks"] == driver.inventory_tree(run)["symlinks"]
    assert receipt["all_exit_zero"] is False and receipt["final_reduction"]["valid"] is False


def test_imp09c_fg_05_symlink_inventory_does_not_follow_directory_aliases(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    target = root / "real"
    target.mkdir(parents=True)
    (target / "journal.jsonl").write_text("one\n", encoding="utf-8")
    (root / "alias").symlink_to(target, target_is_directory=True)
    result = inventory_tree(root)
    assert [item["path"] for item in result["files"]] == ["real/journal.jsonl"]
    assert result["symlinks"] == [{"path": "alias", "type": "directory-symlink", "target": str(target)}]
    assert driver.inventory_tree(root) == result
    records = [
        {"path": "attempts/run-a/fixtures/class0/journal.jsonl", "invocation_id": "origin-localhost"},
        {"path": "attempts/run-a/fixtures/class1/journal.jsonl", "invocation_id": "origin-127"},
        {
            "path": "attempts/run-a/fixtures/classcurrent/class0/journal.jsonl",
            "alias_of": "attempts/run-a/fixtures/class1/journal.jsonl",
        },
    ]
    written = driver.write_delivery_artifacts(root, records=records, selector_counts={"selected": 3})
    assert json.loads((root / "counts.json").read_text(encoding="utf-8"))["invocations"]["invocation_count"] == 2
    assert written["inventory_symlinks"] == 1


def test_imp09c_fg_06_alias_journal_does_not_increase_invocation_counts(tmp_path: Path) -> None:
    result = aggregate_invocations(
        [
            {"path": "fixtures/class0/journal.jsonl", "invocation_id": "origin-localhost"},
            {"path": "fixtures/class1/journal.jsonl", "invocation_id": "origin-127"},
            {"path": "fixtures/classcurrent/journal.jsonl", "alias_of": "fixtures/class1/journal.jsonl"},
        ]
    )
    assert result["invocation_count"] == 2
    assert result["aliases"] == [
        {"path": "fixtures/classcurrent/journal.jsonl", "target": "fixtures/class1/journal.jsonl"}
    ]
    isolated = tmp_path / "run"
    attempts = isolated / "attempts"
    fixture_journal = attempts / "execution-1" / "fixtures" / "fake-test" / "journal.jsonl"
    fixture_journal.parent.mkdir(parents=True)
    fixture_journal.write_text("not an invocation journal\n", encoding="utf-8")
    (fixture_journal.parent / "inner" / "fixtures" / "broken").mkdir(parents=True)
    (fixture_journal.parent / "inner" / "fixtures" / "broken" / "journal.jsonl").write_text(
        "{not-json\n", encoding="utf-8"
    )
    invocation_journal = attempts / "execution-1" / "journal.jsonl"
    invocation_journal.write_text('{"kind":"canonical"}\n', encoding="utf-8")
    fixture_alias = attempts / "execution-1" / "fixtures-alias"
    fixture_alias.symlink_to(fixture_journal.parent, target_is_directory=True)

    captured = driver.collect_invocation_records(isolated)

    assert [record["path"] for record in captured] == ["attempts/execution-1/journal.jsonl"]
    counts = aggregate_invocations(captured)
    assert counts["invocation_count"] == 1
    assert counts["aliases"] == []


def test_imp09c_fg_07_partial_body_timeout_preserves_prefix_and_bounded_deadline(tmp_path: Path) -> None:
    class AdvancingClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            self.now += 1.0
            return self.now

    class Sock:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def settimeout(self, value: float) -> None:
            self.timeouts.append(value)

    class Body:
        def __init__(self, sock: Sock) -> None:
            self.status = self.code = 503
            self.headers = Message()
            self.headers["Content-Type"] = "application/json"
            self.raw = SimpleNamespace(_sock=sock)
            self.content = b"partial-response"
            self.reads = 0
            self.closed = False

        def read(self, amount: int = -1) -> bytes:
            self.reads += 1
            if self.reads == 2:
                raise TimeoutError("fixture body read timeout after prefix")
            chunk, self.content = self.content[:amount], self.content[amount:]
            return chunk

        def readline(self, amount: int = -1) -> bytes:
            return self.read(amount)

        def close(self) -> None:
            self.closed = True

        def isclosed(self) -> bool:
            return self.closed

    class Opener:
        def __init__(self, body: Body) -> None:
            self.body = body
            self.calls = 0

        def open(self, request: Any, *, timeout: float) -> Any:
            self.calls += 1
            raise urllib.error.HTTPError(request.full_url, 503, "fixture", self.body.headers, cast(Any, self.body))

    clock = AdvancingClock()
    sock = Sock()
    body = Body(sock)
    opener = Opener(body)
    http = r.StdlibHTTP()
    http.opener = opener
    resources = r.Resources(clock, http, lambda name: None, lambda: None, lambda: None, lambda *args: None, mock=True)
    journal = h.OneShotJournal(tmp_path / "journal.jsonl")
    harness_run = tmp_path / "harness-run"
    harness_run.mkdir()
    shutil.copyfile(RUN / "endpoint-contract.json", harness_run / "endpoint-contract.json")
    shutil.copyfile(RUN / "budgets.json", harness_run / "budgets.json")
    bridge.seed(harness_run)
    (harness_run / "execution-binding.json").unlink()
    h.freeze_execution_binding(harness_run, ROOT)
    request_bytes = (harness_run / "request.json").read_bytes()
    assert journal.reserve("product_authenticated_chat_post", "product:fg07", request_bytes)
    spec = SimpleNamespace(
        run=harness_run, root=ROOT, journal=journal.path, state=tmp_path / "worker-state", deadline=20.0
    )
    observer = r.WorkerObserver(spec, resources)
    observer.journal = journal
    observer.arm("product:fg07", h.sha256(request_bytes))
    provider_body = h.canonical_json(
        {
            "model": h.MODEL_ALIAS,
            "stream": False,
            "keep_alive": "30m",
            "think": False,
            "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0, "repeat_penalty": 1.0, "min_p": 0.0},
            "messages": [{"role": "user", "content": h.PROMPT_PREFIX + h.QUESTION, "images": [h.load_image(RUN)[1]]}],
        }
    )
    request = urllib.request.Request("http://localhost:11434/api/chat", data=provider_body, method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        observer.urlopen(request, timeout=10)
    response = caught.value
    assert response.code == 503
    assert response.read(7) == b"partial"
    with pytest.raises(TimeoutError, match="after prefix"):
        response.read(7)
    response.close()
    capture = spec.state / "captures/provider-fg07-response.bin"
    assert capture.read_bytes() == b"partial"
    assert body.closed and opener.calls == 1
    assert sock.timeouts and all(0 < timeout <= 20 for timeout in sock.timeouts)
    assert journal.counts()["response_observed"]["ollama_chat_inference_wire"] == 1


def _prepare_supervisor_fixture(tmp_path: Path) -> None:
    shutil.copyfile(RUN / "endpoint-contract.json", tmp_path / "endpoint-contract.json")
    shutil.copyfile(RUN / "budgets.json", tmp_path / "budgets.json")
    bridge.seed(tmp_path)
    (tmp_path / "execution-binding.json").unlink()
    h.freeze_execution_binding(tmp_path, ROOT)


def test_imp09c_fg_08_supervise_once_success_requires_reaped_cleanup(tmp_path: Path, monkeypatch: Any) -> None:
    _prepare_supervisor_fixture(tmp_path)
    world, adapter, result = bridge.execute(tmp_path, monkeypatch, "ok")
    assert result["verdict"] == "FIXTURE_ONLY"
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert result["cleanup"]["owned_cleanup"] is True and result["cleanup"]["reaped"] is True
    assert world.product_calls == world.provider_calls == 1


@pytest.mark.parametrize("mode", ["cleanup-exception", "cleanup-unknown", "cleanup-slow", "cleanup-late"])
def test_imp09c_fg_11_cleanup_failure_and_late_deadline_fail_closed(
    tmp_path: Path, monkeypatch: Any, mode: str
) -> None:
    _prepare_supervisor_fixture(tmp_path)
    binding_before = (tmp_path / "execution-binding.json").read_bytes()
    world, adapter, result = bridge.execute(tmp_path, monkeypatch, mode)
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert world.product_calls == world.provider_calls == 1
    assert result["pass"] is False
    assert result["dispatches"] == 1 and result["provider_wires"] == 1
    if mode == "cleanup-late":
        assert result["cleanup"]["owned_cleanup"] is True and result["cleanup"]["reaped"] is True
        assert result["gates"]["cleanup_deadline"] == "FAIL"
    else:
        assert result["gates"]["cleanup_owned_exit"] != "PASS"
    assert (tmp_path / "execution-binding.json").read_bytes() == binding_before
    assert adapter.cleanup_calls == 1


@pytest.mark.parametrize("mode", ["source-drift", "request-drift", "binding-drift", "wire-expired"])
def test_imp09c_fg_09_pre_wire_source_drift_remains_non_success(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    _prepare_supervisor_fixture(tmp_path)
    world, adapter, result = bridge.execute(tmp_path, monkeypatch, mode)
    assert result["pass"] is False and result["verdict"] != "FIXTURE_ONLY"
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert result["dispatches"] == 0
    assert world.provider_calls == 0
    assert (tmp_path / "execution-binding.json").is_file()


def test_imp09c_fg_12_post_cleanup_source_drift_is_reduced_to_failure(tmp_path: Path, monkeypatch: Any) -> None:
    _prepare_supervisor_fixture(tmp_path)
    binding_before = (tmp_path / "execution-binding.json").read_bytes()
    ready = True
    original_snapshot = h.source_snapshot

    def injected_snapshot(root: Path) -> dict[str, Any]:
        result = original_snapshot(root)
        if not ready:
            result["ready"] = False
            result["drift"] = {"injected-after-cleanup": {"expected": "protected", "actual": "changed"}}
        return result

    monkeypatch.setattr(h, "source_snapshot", injected_snapshot)
    world = bridge.World(tmp_path, "ok")
    monkeypatch.setattr(h.time, "monotonic", world.clock.monotonic)
    descriptor = h.verify_runtime_authorization(tmp_path, ROOT, bridge.approval(tmp_path), mode="OFFLINE_MOCK")
    assert descriptor is not None
    journal = h.OneShotJournal(tmp_path / "task-wire-journal.jsonl")
    adapter = r.concrete_adapter_factory(tmp_path, ROOT, journal, world.resources)
    original_cleanup = adapter.cleanup

    def cleanup_then_drift(context: Any) -> dict[str, Any]:
        nonlocal ready
        receipt = original_cleanup(context)
        ready = False
        return receipt

    adapter.cleanup = cleanup_then_drift
    result = h.supervise_once(run=tmp_path, root=ROOT, adapter=adapter, journal=journal, authorization=descriptor)
    assert world.product_calls == world.provider_calls == 1
    assert result["dispatches"] == result["provider_wires"] == 1
    assert result["pass"] is False and result["gates"]["protected_before_after"] == "FAIL"
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert (tmp_path / "execution-binding.json").read_bytes() == binding_before
