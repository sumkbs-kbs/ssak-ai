#!/usr/bin/env python3
"""One bounded continuation; launch only after reviewing prepared-plan.json."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import pwd
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLAN = json.loads((BASE / "prepared-plan.json").read_text())
REPO, FRESH, HELPER = (Path(PLAN[key]) for key in ("repo", "fresh", "soak_helper"))
SOAK, PYTHON = HELPER.parent / "soak", str(REPO / ".venv/bin/python")
HEAD, FP = PLAN["head"], PLAN["fingerprint"]
ACCOUNT = pwd.getpwuid(os.getuid())
ENV = {"HOME": ACCOUNT.pw_dir, "USER": ACCOUNT.pw_name, "LOGNAME": ACCOUNT.pw_name,
       "PATH": "/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
       "TMPDIR": "/tmp", "LANG": "en_US.UTF-8", "TERM": "dumb",
       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    try:
        return json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def write(name, value, exclusive=False):
    path = BASE / name
    payload = json.dumps({"recorded_at": now(), **value}, indent=2) + "\n"
    target = path if exclusive else path.with_suffix(path.suffix + ".tmp")
    with target.open("x" if exclusive else "w") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        target.replace(path)


def state(status, **detail):
    value = {"status": status, "supervisor_pid": os.getpid(), **detail}
    with (BASE / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"recorded_at": now(), **value}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    write("state.json", value)


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def bound_inputs():
    require(all(sha(path) == expected for path, expected in PLAN["input_sha256"].items()), "input hash drift")
    require(sha(BASE / "continuation.py") == PLAN["wrapper_sha256"], "wrapper drift")


def source():
    spec = importlib.util.spec_from_file_location("continuation_source", REPO / "scripts/ga_gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(REPO), *args], env=ENV, text=True, timeout=60).strip()
    observed = {"head": git("rev-parse", "HEAD"), "status": git("status", "--porcelain"),
                "working_fingerprint": gate.worktree_fingerprint(REPO),
                "commit_fingerprint": gate.tree_fingerprint_of_commit(REPO, "HEAD")}
    require(observed == {"head": HEAD, "status": "", "working_fingerprint": FP, "commit_fingerprint": FP}, "candidate drift")
    return observed


def wait_for(predicate, seconds, phase):
    state(phase, timeout_seconds=seconds)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(min(30, max(0, deadline - time.monotonic())))
    raise TimeoutError(phase + ": deadline expired; existing processes not restarted")


def child(name, command, timeout):
    write(name + "-claim.json", {"command": command, "cwd": str(REPO)}, exclusive=True)
    with (BASE / (name + ".stdout.txt")).open("xb") as out, (BASE / (name + ".stderr.txt")).open("xb") as err:
        process = subprocess.Popen(command, cwd=REPO, env=ENV, stdout=out, stderr=err)
        write(name + "-pid.json", {"pid": process.pid, "command": command}, exclusive=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            write(name + "-receipt.json", {"pid": process.pid, "exit_code": None, "reaped": False, "status": "UNOBSERVED_TIMEOUT_NO_RETRY"}, exclusive=True)
            raise
    write(name + "-receipt.json", {"pid": process.pid, "command": command, "exit_code": code, "reaped": True}, exclusive=True)
    return code


def supervise():
    write("supervisor-claim.json", {"pid": os.getpid(), "plan_sha256": sha(BASE / "prepared-plan.json")}, exclusive=True)
    try:
        bound_inputs()
        require(read(BASE / "start-claim.json")["plan_sha256"] == sha(BASE / "prepared-plan.json"), "plan changed after claim")
        source()
        wait_for(lambda: read(FRESH / "launch-receipt.json") and read(FRESH / "runner-receipt.json"), PLAN["gate_wait_seconds"], "WAITING_GATES")
        if not (FRESH / "result.json").exists():
            state("FINALIZING_GATES")
            # Cooperating callers honor this claim; a pre-existing result is always reused.
            write("finalizer-ownership.json", {"result": str(FRESH / "result.json")}, exclusive=True)
            if not (FRESH / "result.json").exists():
                require(child("finalizer", [PYTHON, "-B", str(FRESH / "finalize.py")], 600) == 0, "finalizer actual exit nonzero")
        result = wait_for(lambda: read(FRESH / "result.json") and read(FRESH / "artifact-manifest.json"), 120, "WAITING_FINALIZER_FLUSH")
        result = read(FRESH / "result.json")
        require(result["status"] == "PASS_FRESH_SAME_CANDIDATE_23" and result["head"] == HEAD and result["soak_eligible"] is True, "fresh gates are not eligible")
        require(set(result["checks"]) == set(PLAN["gate_checks"]) and all(v is True for v in result["checks"].values()), "gate check false/missing")
        require(result["gate_process_exit"] == result["runner_exit"] == 0 and result["historical_results_merged"] is False, "nonzero gate exit or merged results")
        bound_inputs()
        source()
        require(not SOAK.exists(), "soak output already exists; reconcile without relaunch")
        state("LAUNCHING_SOAK", new8hsoak="START_REQUESTED_COMPLETION_UNOBSERVED")
        require(child("soak-helper", [PYTHON, "-I", "-B", str(HELPER), "--launch"], 1800) == 0, "soak helper failed; no retry")
        wait_for(lambda: read(SOAK / "soak-recovery-latest.json") and read(SOAK / "collector-receipt.json"), 43800, "WAITING_EXISTING_COLLECTOR")
        recovery, collector = (read(SOAK / name) for name in ("soak-recovery-latest.json", "collector-receipt.json"))
        execution = read(SOAK / "execution-plan.json")
        expected = [PYTHON, "-B", "scripts/ga_gate_verify.py", "--report", str(FRESH / "gate-report.json"), "--manifest", "scripts/commercial_ga_gates.json", "--expected-sha", HEAD, "--soak-artifact", str(SOAK / "soak-28800.json"), "--min-soak-seconds", "28800"]
        require(execution["commands"]["official_final_verify"] == expected and execution["head"] == HEAD, "final verifier command/candidate drift")
        state("VERIFYING_SOAK")
        bound_inputs()
        verified = child("official-final-verify", execution["commands"]["official_final_verify"], 600)
        current = source()
        require(execution["gate_report_sha256"] == sha(FRESH / "gate-report.json") and execution["fresh_result_sha256"] == sha(FRESH / "result.json") and execution["fresh_artifact_manifest_sha256"] == sha(FRESH / "artifact-manifest.json"), "gate evidence changed after soak launch")
        metrics = read(SOAK / "soak-28800.json")
        runner = recovery["runner"]
        rows = metrics["scenarios"]
        sc6 = next(row for row in rows if row["scenario"] == "SC-6-soak")
        checks = {
            "official_verifier": verified == 0,
            "collector_exit": collector["actual_exit"] == collector["propagated_exit"] == 0 and collector["reaped"] is True and collector["command"] == [PYTHON, str(REPO / "scripts/collect_soak_result.py")] and collector["cwd"] == str(REPO) and collector["source_sha256"] == execution["measurement_sources"]["scripts/collect_soak_result.py"] and collector["proxy_sha256"] == sha(BASE / "collector_proxy.py") and collector["pid"] == read(SOAK / "collector-pid.json")["pid"],
            "collector_verdict": recovery["verdict"] == "PASS" and len(recovery["checks"]) == 6 and all(row["ok"] is True for row in recovery["checks"]),
            "runner": runner["exit"] == "0" and runner["soak_seconds"] == "28800" and recovery["duration_seconds"] >= 28800,
            "source": recovery["expected_fingerprint"] == runner["start_fingerprint"] == runner["end_fingerprint"] == recovery["worktree_fingerprint_now"] == FP,
            "metrics": metrics["all_pass"] is True and metrics["missing_required"] == [] and len(rows) == 6 and {row["scenario"] for row in rows} == set(PLAN["scenarios"]) and all(row["pass"] is True for row in rows),
            "measured_duration": sc6.get("actual_duration_s", sc6.get("duration_s", 0)) >= 28800,
        }
        status = "PASS" if all(checks.values()) else "FAIL"
        write("result.json", {"status": status, "checks": checks, "current": current, "collector_exit": collector["actual_exit"], "scope": "Current candidate full gates and actual 8h SC1-6 soak only", "release_approval": "NOT_ISSUED", "evidence_sha256": {str(path): sha(path) for path in (SOAK / "collector-receipt.json", SOAK / "soak-recovery-latest.json", SOAK / "soak-28800.json", SOAK / "soak-exit.txt", FRESH / "result.json", FRESH / "gate-report.json")}})
        state(status)
        write("supervisor-terminal-receipt.json", {"pid": os.getpid(), "status": status, "return_code": 0 if status == "PASS" else 1, "scope": "Supervisor return decision; child exits are in their actual wait receipts"}, exclusive=True)
        return 0 if status == "PASS" else 1
    except Exception as exc:
        status = "UNOBSERVED" if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else "HOLD"
        write("result.json", {"status": status, "reason": str(exc), "error_type": type(exc).__name__, "new8hsoak": "START_REQUESTED_OR_RUNNING_UNOBSERVED" if SOAK.exists() else "NOT_RUN", "release_approval": "NOT_ISSUED"})
        state(status, reason=str(exc))
        write("supervisor-terminal-receipt.json", {"pid": os.getpid(), "status": status, "return_code": 1}, exclusive=True)
        return 1


def main():
    require(sys.argv[1:] in (["--launch"], ["--supervise"]), "explicit --launch required")
    os.environ.clear()
    os.environ.update(ENV)
    if sys.argv[1:] == ["--supervise"]:
        return supervise()
    bound_inputs()
    source()
    require(not SOAK.exists(), "existing soak; no relaunch")
    write("start-claim.json", {"head": HEAD, "plan_sha256": sha(BASE / "prepared-plan.json")}, exclusive=True)
    command = ["/usr/bin/caffeinate", "-i", PYTHON, "-I", "-B", str(BASE / "continuation.py"), "--supervise"]
    with (BASE / "supervisor.stdout.txt").open("xb") as out, (BASE / "supervisor.stderr.txt").open("xb") as err:
        process = subprocess.Popen(command, cwd=REPO, env=ENV, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
    write("launch-receipt.json", {"pid": process.pid, "command": command, "cwd": str(REPO), "detached": True, "completion": "UNOBSERVED"}, exclusive=True)
    print(json.dumps({"status": "LAUNCHED_COMPLETION_PENDING", "pid": process.pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
