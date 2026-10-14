"""TDD Verifier & Feedback Engine — Red-Green-Refactor enforcement for 27B.

This module automates the execution of unit tests whenever relevant code files are touched,
extracting assertion errors and producing high-signal, zero-noise repair prompts.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from antigravity_k.engine.sandbox import run_sandboxed_argv

logger = logging.getLogger(__name__)

_PYTEST_FAILURE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"FAILED\s+(?P<test_path>[^:\s]+)::(?P<test_func>[^\s]+)\s+-\s+(?P<err_msg>.+)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TDDExecutionResult:
    """Outcome of automated test run."""

    passed: bool
    total_tests: int
    failed_tests: int
    failure_details: list[str]
    raw_output: str

    def format_tdd_feedback(self) -> str:
        """Format clean, targeted TDD feedback for the model."""
        if self.passed:
            return f"✅ [TDD Verified] All {self.total_tests} unit tests passed successfully."

        lines = [
            f"❌ [TDD Test Failures: {self.failed_tests}/{self.total_tests} Tests Failed]",
            "Please fix the implementation to satisfy the failing assertions below:",
        ]
        for idx, detail in enumerate(self.failure_details[:5], 1):
            lines.append(f"  {idx}. {detail}")
        lines.append("\n💡 Action: Focus only on fixing these specific failing assertions.")
        return "\n".join(lines)


class TDDVerifier:
    """Executes relevant test suites and summarizes results."""

    @staticmethod
    def run_tests_for_file(project_root: str | Path, target_file: str | Path) -> TDDExecutionResult:
        """Find and run tests matching the target file (e.g. tests/test_<file>.py)."""
        root = Path(project_root).resolve()
        target = Path(target_file)
        stem = target.stem

        # Look for corresponding test file
        candidate_test = root / "tests" / f"test_{stem}.py"
        test_path_to_run = str(candidate_test) if candidate_test.exists() else str(root / "tests")

        try:
            res = run_sandboxed_argv(
                ["pytest", test_path_to_run, "-q", "--tb=short"],
                cwd=str(root),
                timeout=15,
            )
            output = res.stdout + "\n" + res.stderr
            return TDDVerifier._parse_pytest_output(output, res.return_code == 0)
        except Exception as err:
            return TDDExecutionResult(
                passed=False,
                total_tests=0,
                failed_tests=1,
                failure_details=[f"Test runner execution error: {err}"],
                raw_output=str(err),
            )

    @staticmethod
    def _parse_pytest_output(output: str, is_zero_return: bool) -> TDDExecutionResult:
        failures: list[str] = []
        for match in _PYTEST_FAILURE_PATTERN.finditer(output):
            t_path = match.group("test_path")
            t_func = match.group("test_func")
            msg = match.group("err_msg").strip()
            failures.append(f"{t_path}::{t_func} -> {msg}")

        # If zero exit code and no explicit failures parsed
        if is_zero_return and not failures:
            return TDDExecutionResult(
                passed=True,
                total_tests=1,
                failed_tests=0,
                failure_details=[],
                raw_output=output,
            )

        return TDDExecutionResult(
            passed=False,
            total_tests=max(len(failures), 1),
            failed_tests=max(len(failures), 1),
            failure_details=failures or ["Pytest failed. Check logs for details."],
            raw_output=output,
        )
