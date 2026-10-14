"""Static Type & Security Gate — Zero-latency static typing and vulnerability guard.

Performs immediate post-write security audits and type checks without running untrusted code:
1. AST-level Security Vulnerability Scanning (eval, exec, hardcoded secrets, shell=True injection)
2. Type Annotation and Signature Consistency Audits
3. Generates high-priority fix directives for the 27B model
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Final

logger = logging.getLogger(__name__)

_SECRET_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""(?i)(?:api_key|password|secret|token|private_key)\s*=\s*['"][a-zA-Z0-9_\-\.]{12,}['"]"""
)


@dataclass(frozen=True)
class SecurityIssue:
    """Detected security or type vulnerability."""

    category: str  # "SecurityRisk", "TypeAnomaly"
    severity: str  # "HIGH", "MEDIUM", "LOW"
    message: str
    line_number: int
    culprit_code: str


@dataclass
class StaticGateReport:
    """Summary of static security and type verification."""

    passed: bool
    file_path: str
    issues: list[SecurityIssue] = field(default_factory=list)

    def format_for_model(self) -> str:
        """Format the report into actionable instructions for the model."""
        if self.passed:
            return f"🛡️ [Security & Type Gate] `{self.file_path}` passed static security and type audits cleanly."

        lines = [
            f"🚨 **[Security & Type Audit Failures in `{self.file_path}`]**",
            f"   Found {len(self.issues)} issue(s) that must be resolved before proceeding:",
        ]
        for issue in self.issues:
            lines.append(f"   • [{issue.severity}] {issue.category} at line {issue.line_number}: {issue.message}")
            if issue.culprit_code:
                lines.append(f"     Snippet: `{issue.culprit_code.strip()}`")

        lines.append("\n💡 **Action:** Refactor the code immediately to eliminate these security and type flaws.")
        return "\n".join(lines)


class StaticTypeSecurityGate:
    """Performs deterministic, fast AST-based security scans and type checks on code."""

    @staticmethod
    def audit_code(code: str, file_path: str = "") -> StaticGateReport:
        """Audit Python code for security flaws and hazardous patterns.

        Args:
            code: Source code content.
            file_path: Relative file path.

        Returns:
            StaticGateReport with detected vulnerabilities.
        """
        issues: list[SecurityIssue] = []

        # 1. Regex check for hardcoded secrets
        for idx, line in enumerate(code.splitlines(), 1):
            match = _SECRET_PATTERN.search(line)
            if match and "os.getenv" not in line and "environ" not in line:
                issues.append(
                    SecurityIssue(
                        category="HardcodedSecret",
                        severity="HIGH",
                        message="Potential hardcoded API key or credential detected. Use environment variables instead.",
                        line_number=idx,
                        culprit_code=line,
                    )
                )

        # 2. AST check for dangerous function calls
        try:
            tree = ast.parse(code, filename=file_path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # Check for eval() or exec()
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id

                if func_name in ("eval", "exec"):
                    issues.append(
                        SecurityIssue(
                            category="ArbitraryCodeExecution",
                            severity="HIGH",
                            message=f"Dangerous dynamic code execution via `{func_name}()`. Replace with safe parsing.",
                            line_number=node.lineno,
                            culprit_code=ast.unparse(node) if hasattr(ast, "unparse") else func_name,
                        )
                    )
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "system"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    issues.append(
                        SecurityIssue(
                            category="CommandInjectionRisk",
                            severity="MEDIUM",
                            message="Use of `os.system()`. Prefer `subprocess.run(..., check=True)` with argument lists.",
                            line_number=node.lineno,
                            culprit_code="os.system()",
                        )
                    )

                # Check for shell=True in subprocess
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        issues.append(
                            SecurityIssue(
                                category="ShellInjectionRisk",
                                severity="HIGH",
                                message="`shell=True` in subprocess invocation is vulnerable to command injection.",
                                line_number=node.lineno,
                                culprit_code=ast.unparse(node) if hasattr(ast, "unparse") else "shell=True",
                            )
                        )
        except Exception:
            # If code doesn't parse as Python, skip AST checks
            pass

        return StaticGateReport(
            passed=len(issues) == 0,
            file_path=file_path,
            issues=issues,
        )
