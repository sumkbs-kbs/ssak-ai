# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest", "pydantic>=2"]
# ///
# Pure fake process/clock/signals; no OS process, socket, or server operations.
"""Real ownership reducer exercised through failures at every post-spawn seam."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from startup_probe.contract import Cleanup, SourcePlan
from startup_probe.lifecycle import Process, Terminal, own_spawned


@dataclass(slots=True)
class FakeOperations:
    """Mutable deterministic clock and resource ledger, never an OS adapter."""

    clock: float = 0
    fail_writes: set[str] = field(default_factory=set)
    auto_stop: bool = True
    die_on_signal: bool = True
    disappear_on_kill: bool = False
    emergency_fails: bool = False
    empty: bool = False
    child_code: int | None = None
    signals: list[int] = field(default_factory=list)
    writes: dict[str, str] = field(default_factory=dict)
    emergency_text: list[str] = field(default_factory=list)
    waits: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds

    def signal(self, pid: int, signum: int) -> None:
        assert pid == 721
        self.signals.append(signum)
        if self.disappear_on_kill and signum == signal.SIGKILL:
            self.empty = True
            self.child_code = -9
            raise ProcessLookupError("simulated child disappearance")
        if self.die_on_signal:
            self.child_code = -int(signum)
            self.empty = True

    def group_empty(self, pid: int) -> bool:
        assert pid == 721
        return self.empty

    def write(self, path: Path, text: str) -> None:
        if path.name in self.fail_writes:
            raise OSError("injected receipt failure")
        self.writes[path.name] = text
        if path.name == "stop.requested" and self.auto_stop:
            self.child_code = 0
            self.empty = True

    def emergency(self, text: str) -> None:
        self.emergency_text.append(text)
        if self.emergency_fails:
            raise OSError("injected outer receipt/stderr failure")


@dataclass(frozen=True, slots=True)
class FakeProcess:
    ops: FakeOperations
    pid: int = 721

    def poll(self) -> int | None:
        return self.ops.child_code

    def wait(self, timeout: float) -> int:
        self.ops.waits.append(timeout)
        if self.ops.child_code is None:
            self.ops.clock += timeout
            raise subprocess.TimeoutExpired("fake-child", timeout)
        return self.ops.child_code


@pytest.fixture
def plan(tmp_path: Path) -> SourcePlan:
    return SourcePlan(
        candidate=tmp_path,
        candidate_head="frozen",
        app_version="0.1.0",
        python=tmp_path / "python",
        source_hashes={},
        dotenv_path=tmp_path / "dotenv",
        dotenv_sha256="unused",
    )


def execute(
    ops: FakeOperations, plan: SourcePlan, tmp_path: Path, *, total_deadline: float = 90, assess_failure: bool = False
) -> Terminal:
    def observe(child: Process) -> None:
        ops.write(tmp_path / "launch.json", str(child.pid))

    def assess(cleanup: Cleanup) -> bool:
        if assess_failure:
            ops.write(tmp_path / "diagnostic.json", "diagnostic")
        return cleanup.passed()

    result = own_spawned(FakeProcess(ops), plan, tmp_path, 0, total_deadline, ops, observe, assess)
    capture_root = os.environ.get("LIFECYCLE_CAPTURE_ROOT")
    if capture_root:
        directory = Path(capture_root)
        directory.mkdir(exist_ok=True)
        (directory / (tmp_path.name + ".json")).write_text(
            json.dumps(
                {
                    "outcome": result.outcome,
                    "failures": result.failures,
                    "exit_code": result.cleanup.observed.exit_code,
                    "reaped": result.cleanup.observed.reaped,
                    "group_empty": result.cleanup.observed.group_empty,
                    "forced": result.cleanup.observed.forced,
                    "deadline": result.cleanup.cleanup_deadline,
                    "clock": ops.clock,
                    "waits": ops.waits,
                    "signals": ops.signals,
                    "written_names": list(ops.writes),
                    "terminal_file_written": result.terminal_file_written,
                    "emergency_count": len(ops.emergency_text),
                },
                indent=2,
            )
        )
    return result


def test_launch_receipt_failure_still_stops_and_reaps(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(fail_writes={"launch.json"})
    result = execute(ops, plan, tmp_path)
    assert result.outcome == "NO_SUCCESS"
    assert result.cleanup.observed.reaped and result.cleanup.observed.group_empty
    assert result.cleanup.observed.exit_code == 0
    assert "result.json" in ops.writes
    assert result.failures == ("observation:OSError",)


def test_stop_write_failure_terminates_owned_child_then_reaps(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(fail_writes={"stop.requested"})
    result = execute(ops, plan, tmp_path)
    assert ops.signals == [signal.SIGTERM]
    assert result.cleanup.observed.exit_code == -15
    assert result.cleanup.observed.reaped and result.cleanup.observed.group_empty
    assert result.outcome == "NO_SUCCESS"
    assert "result.json" in ops.writes


def test_disappearing_child_before_kill_preserves_actual_exit(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(auto_stop=False, disappear_on_kill=True)
    result = execute(ops, plan, tmp_path)
    assert ops.signals == [signal.SIGKILL]
    assert result.cleanup.signal_races == 1
    assert result.cleanup.observed.exit_code == -9
    assert result.cleanup.observed.reaped and result.cleanup.observed.group_empty
    assert result.outcome == "NO_SUCCESS"
    assert ops.waits == [10, 5]


def test_unreaped_timeout_and_terminal_output_failure_use_outer_receipt(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(auto_stop=False, die_on_signal=False, fail_writes={"result.json"})
    result = execute(ops, plan, tmp_path)
    assert result.cleanup.observed.exit_code is None
    assert not result.cleanup.observed.reaped and not result.cleanup.observed.group_empty
    assert ops.clock == 15 and ops.waits == [10, 5, 0]
    assert not result.terminal_file_written and result.outcome == "NO_SUCCESS"
    assert len(ops.emergency_text) == 1


def test_cleanup_diagnostic_failure_does_not_hide_terminal(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(fail_writes={"diagnostic.json"})
    result = execute(ops, plan, tmp_path, assess_failure=True)
    assert result.cleanup.observed.reaped
    assert result.outcome == "NO_SUCCESS" and "assessment:OSError" in result.failures
    assert "result.json" in ops.writes


def test_emergency_output_failure_cannot_return_success(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(fail_writes={"result.json"}, emergency_fails=True)
    result = execute(ops, plan, tmp_path)
    assert result.outcome == "NO_SUCCESS" and not result.terminal_file_written
    assert "emergency_write:OSError" in result.failures
    assert result.cleanup.observed.reaped


def test_total_budget_does_not_reset_during_cleanup(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations(clock=88, auto_stop=False, die_on_signal=False)
    result = execute(ops, plan, tmp_path)
    assert result.cleanup.cleanup_deadline == 90
    assert ops.clock == 90 and ops.waits == [2, 0, 0]
    assert result.outcome == "NO_SUCCESS"


def test_fully_observed_normal_exit_can_pass(plan: SourcePlan, tmp_path: Path) -> None:
    ops = FakeOperations()
    result = execute(ops, plan, tmp_path)
    assert result.outcome == "PASS_SCOPED_EXTERNAL_UVICORN_AUTH_LIFESPAN_ON"
    assert result.cleanup.observed.exit_code == 0 and result.cleanup.observed.reaped
    assert result.terminal_file_written and not ops.signals
