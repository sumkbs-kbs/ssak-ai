"""Error Distiller — Verbose tool error and stacktrace summarizer for 30B models.

30B-class models often get trapped or hallucinate when confronted with hundreds of lines
of raw traceback. This module distills errors into a structured, concise 1-3 line feedback:
- Location (file, line number)
- Error type & clear message
- Recommended action
"""

import re
from dataclasses import dataclass
from typing import Final

_PYTHON_TRACEBACK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)\n\s*(?P<code>.+?)\n(?P<err_type>\w+(?:Error|Exception|Warning)?):\s*(?P<err_msg>.+)',
    re.MULTILINE | re.DOTALL,
)

_COMMAND_NOT_FOUND_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:zsh|bash|sh):\s*(?:command not found|line \d+):\s*(?P<cmd>\S+)",
    re.IGNORECASE,
)

_PERMISSION_DENIED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"Permission denied:? '?(?P<target>[^\n']+)'?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DistilledError:
    """Distilled error representation."""

    error_type: str
    summary: str
    location: str = ""
    suggested_action: str = ""

    def format_for_model(self) -> str:
        """Format the error in a compact, token-efficient structure."""
        parts = [f"❌ [{self.error_type}] {self.summary}"]
        if self.location:
            parts.append(f"   📍 Location: {self.location}")
        if self.suggested_action:
            parts.append(f"   💡 Suggestion: {self.suggested_action}")
        return "\n".join(parts)


class ErrorDistiller:
    """Extracts compact, actionable error messages from raw tool execution outputs."""

    @staticmethod
    def distill(tool_name: str, raw_error: str, max_chars: int = 600) -> str:
        """Distill raw tool error output into concise feedback.

        Args:
            tool_name: Name of the tool that produced the error.
            raw_error: Raw stderr or error message string.
            max_chars: Maximum character limit for fallback truncation.

        Returns:
            Structured and concise error feedback.
        """
        if not raw_error or not raw_error.strip():
            return "❌ [ToolExecutionError] Tool failed with empty output."

        text = raw_error.strip()

        # 1. Check for Python Traceback
        if "Traceback (most recent call last):" in text:
            distilled = ErrorDistiller._parse_python_traceback(text)
            if distilled:
                return distilled.format_for_model()

        # 2. Check for Command Not Found
        cmd_match = _COMMAND_NOT_FOUND_PATTERN.search(text)
        if cmd_match:
            cmd = cmd_match.group("cmd")
            return DistilledError(
                error_type="CommandNotFound",
                summary=f"Command '{cmd}' is not installed or not in PATH.",
                suggested_action=f"Verify if '{cmd}' is installed or use an alternative tool.",
            ).format_for_model()

        # 3. Check for Permission Denied
        perm_match = _PERMISSION_DENIED_PATTERN.search(text)
        if perm_match:
            target = perm_match.group("target")
            return DistilledError(
                error_type="PermissionDenied",
                summary=f"Access denied to '{target}'.",
                suggested_action="Check file permissions or request required approval.",
            ).format_for_model()

        # 4. Check for JSON syntax or parse error
        if "JSONDecodeError" in text or "Expecting value" in text or "Invalid JSON" in text:
            return DistilledError(
                error_type="JSONParseError",
                summary="Invalid JSON structure provided in tool arguments.",
                suggested_action="Ensure all quotes are closed and keys are valid JSON.",
            ).format_for_model()

        # 5. Fallback: Compact head + tail truncation with indicator
        if len(text) > max_chars:
            head = text[: max_chars // 2]
            tail = text[-(max_chars // 2) :]
            text = f"{head}\n... [TRUNCATED {len(text) - max_chars} chars] ...\n{tail}"

        return f"❌ [{tool_name} Error]\n{text}"

    @staticmethod
    def _parse_python_traceback(text: str) -> DistilledError | None:
        """Extract the last and most critical frame from a Python traceback."""
        lines = text.splitlines()
        last_error_line = ""
        location_line = ""

        for line in reversed(lines):
            line_str = line.strip()
            if not last_error_line and line_str and not line_str.startswith("File "):
                if any(err in line_str for err in (":", "Error", "Exception")):
                    last_error_line = line_str
            elif "File " in line_str and not location_line:
                location_line = line_str

        if last_error_line:
            err_type = "PythonRuntimeError"
            if ":" in last_error_line:
                err_type = last_error_line.split(":", 1)[0].strip()

            return DistilledError(
                error_type=err_type,
                summary=last_error_line,
                location=location_line,
                suggested_action="Review the error line and adjust arguments or syntax.",
            )
        return None
