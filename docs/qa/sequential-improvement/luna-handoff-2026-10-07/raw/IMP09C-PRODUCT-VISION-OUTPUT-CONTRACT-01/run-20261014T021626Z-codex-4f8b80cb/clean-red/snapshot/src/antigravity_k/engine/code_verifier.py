"""Deterministic Code Verifier — Immediate post-write syntax verification.

30B-class models frequently generate subtle syntax errors (unmatched parentheses,
indentation errors, unclosed strings) when writing long files.

This module provides zero-latency deterministic AST verification before execution:
- Python AST parsing
- JSON / YAML structural validation
- Returns actionable syntax error report immediately
"""

import ast
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyntaxVerificationResult:
    """Result of deterministic syntax validation."""

    is_valid: bool
    error_type: str = ""
    error_message: str = ""
    line_number: int | None = None
    column_offset: int | None = None
    culprit_snippet: str = ""

    def format_feedback(self, file_path: str) -> str:
        """Format an immediate correction prompt for the model."""
        if self.is_valid:
            return f"✅ [{file_path}] Syntax verified cleanly."

        lines = [
            f"❌ [SyntaxError Detected in {file_path}]",
            f"   Type: {self.error_type}",
            f"   Message: {self.error_message}",
        ]
        if self.line_number is not None:
            lines.append(f"   Line: {self.line_number}, Column: {self.column_offset or 'N/A'}")
        if self.culprit_snippet:
            lines.append(f"   Snippet:\n       {self.culprit_snippet.strip()}")
        lines.append("   Action: Please fix the syntax error in this file immediately.")
        return "\n".join(lines)


class DeterministicCodeVerifier:
    """Performs deterministic, fast syntax checks on modified code files."""

    @staticmethod
    def verify_file(file_path: str | Path, content: str | None = None) -> SyntaxVerificationResult:
        """Verify the syntax of a file based on its extension.

        Args:
            file_path: Path to the target file.
            content: Optional in-memory string content (reads from disk if None).

        Returns:
            SyntaxVerificationResult indicating validity and location of errors.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if content is None:
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                return SyntaxVerificationResult(
                    is_valid=False,
                    error_type="FileReadError",
                    error_message=str(e),
                )

        if ext == ".py":
            return DeterministicCodeVerifier._verify_python(content)
        elif ext == ".json":
            return DeterministicCodeVerifier._verify_json(content)
        elif ext in (".yaml", ".yml"):
            return DeterministicCodeVerifier._verify_yaml(content)

        # Non-parsable or other extensions pass by default
        return SyntaxVerificationResult(is_valid=True)

    @staticmethod
    def _verify_python(code: str) -> SyntaxVerificationResult:
        """Verify Python code via ast.parse."""
        try:
            _ = ast.parse(code)
            return SyntaxVerificationResult(is_valid=True)
        except SyntaxError as err:
            return SyntaxVerificationResult(
                is_valid=False,
                error_type="SyntaxError",
                error_message=err.msg,
                line_number=err.lineno,
                column_offset=err.offset,
                culprit_snippet=err.text or "",
            )
        except Exception as err:
            return SyntaxVerificationResult(
                is_valid=False,
                error_type="PythonParseError",
                error_message=str(err),
            )

    @staticmethod
    def _verify_json(content: str) -> SyntaxVerificationResult:
        """Verify JSON syntax."""
        try:
            json.loads(content)
            return SyntaxVerificationResult(is_valid=True)
        except json.JSONDecodeError as err:
            return SyntaxVerificationResult(
                is_valid=False,
                error_type="JSONDecodeError",
                error_message=err.msg,
                line_number=err.lineno,
                column_offset=err.colno,
            )

    @staticmethod
    def _verify_yaml(content: str) -> SyntaxVerificationResult:
        """Verify YAML syntax."""
        try:
            yaml.safe_load(content)
            return SyntaxVerificationResult(is_valid=True)
        except yaml.MarkedYAMLError as err:
            line = err.problem_mark.line + 1 if err.problem_mark is not None else None
            return SyntaxVerificationResult(
                is_valid=False,
                error_type="YAMLParseError",
                error_message=str(err),
                line_number=line,
            )
        except yaml.YAMLError as err:
            return SyntaxVerificationResult(
                is_valid=False,
                error_type="YAMLParseError",
                error_message=str(err),
            )
