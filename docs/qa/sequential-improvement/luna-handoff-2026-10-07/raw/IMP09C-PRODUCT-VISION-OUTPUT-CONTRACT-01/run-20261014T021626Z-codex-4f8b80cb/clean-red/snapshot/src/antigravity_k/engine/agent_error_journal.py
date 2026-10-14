"""Agent Error Journal — Detailed runtime error diagnostics for autonomous AI agents.

This module captures comprehensive diagnostic snapshots when runtime errors occur,
including:
- Exact failing file, line, function, and code snippet with line context
- Stack frames and sanitized local variables
- HTTP request context with sensitive headers automatically redacted
- System environment metadata (version, git sha, platform)
- Structured AI Fix Prompt formatted specifically for Agentic AI code improvement
- Dual persistence: machine-readable JSONL journal and human/agent-readable Markdown cards
"""

from __future__ import annotations

import json
import logging
import platform
import re
import sys
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from antigravity_k import __version__
from antigravity_k.config import config

logger = logging.getLogger("antigravity_k.engine.agent_error_journal")

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|secret|password|credential|cookie|bearer|access[_-]?pin)"
)


def _sanitize_value(key: str, val: Any) -> Any:
    """Mask sensitive values if key matches sensitive patterns."""
    if _SENSITIVE_KEY_PATTERN.search(key):
        return "[REDACTED]"
    if isinstance(val, dict):
        return {k: _sanitize_value(str(k), v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_value(key, v) for v in val]
    return val


def _sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Sanitize HTTP headers for safe logging."""
    sanitized: dict[str, str] = {}
    for k, v in headers.items():
        if _SENSITIVE_KEY_PATTERN.search(k):
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = v
    return sanitized


@dataclass
class StackFrameInfo:
    """Information about a single stack frame."""

    file: str
    line: int
    function: str
    code_line: str
    locals: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentErrorRecord:
    """Complete diagnostic record of an error, ready for an Agentic AI to fix."""

    error_id: str
    timestamp: str
    component: str
    error_type: str
    message: str
    correlation_id: str
    failing_file: str
    failing_line: int
    failing_function: str
    code_context: str
    stack_trace: str
    request_context: dict[str, Any]
    environment: dict[str, str]
    ai_fix_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentErrorRecord:
        return cls(**data)


def _extract_code_context(filepath: str, line_no: int, context_lines: int = 5) -> str:
    """Read source code around the failing line if file is accessible."""
    try:
        path = Path(filepath)
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, line_no - context_lines - 1)
        end = min(len(lines), line_no + context_lines)

        formatted: list[str] = []
        for idx in range(start, end):
            curr_line = idx + 1
            marker = ">>>" if curr_line == line_no else "   "
            formatted.append(f"{marker} {curr_line:5d} | {lines[idx]}")
        return "\n".join(formatted)
    except Exception as exc:
        return f"<Failed to extract source context: {exc}>"


def _generate_ai_fix_prompt(
    error_id: str,
    error_type: str,
    message: str,
    failing_file: str,
    failing_line: int,
    failing_function: str,
    code_context: str,
    stack_trace: str,
    request_context: dict[str, Any],
) -> str:
    """Generate a high-context prompt for an autonomous AI agent to fix the issue."""
    prompt_lines = [
        f"### 🤖 [Agentic AI Code Fix Task: {error_id}]",
        "",
        "**Objective**: Analyze and resolve the following runtime exception in the Ssak-Ai codebase.",
        "",
        f"- **Exception**: `{error_type}`: {message}",
        f"- **Failure Point**: `{failing_file}:{failing_line}` in function `{failing_function}`",
        "",
        "#### Failing Code Snippet:",
        "```python",
        code_context or "# Source snippet unavailable",
        "```",
        "",
        "#### Stack Trace:",
        "```text",
        stack_trace.strip(),
        "```",
    ]

    if request_context:
        prompt_lines.extend(
            [
                "",
                "#### Triggering Request Context:",
                f"- **Method**: {request_context.get('method', 'N/A')}",
                f"- **Path**: {request_context.get('path', 'N/A')}",
                f"- **Query**: {request_context.get('query', {})}",
                f"- **Client**: {request_context.get('client_ip', 'N/A')}",
            ]
        )

    prompt_lines.extend(
        [
            "",
            "#### Recommended Remediation Steps for AI Agent:",
            f"1. Open `{failing_file}` at line `{failing_line}` and inspect the logic in `{failing_function}`.",
            "2. Identify why the exception was raised with the given input/state.",
            "3. Write a regression unit test replicating the failure conditions.",
            "4. Apply defensive validation, error handling, or algorithm correction.",
            "5. Run `pytest` to confirm the fix passes and does not break existing functionality.",
        ]
    )

    return "\n".join(prompt_lines)


class AgentErrorJournal:
    """Journaling engine for recording and managing agent diagnostic logs."""

    def __init__(self, logs_dir: Path | None = None) -> None:
        self.logs_dir = logs_dir or config.paths.logs_dir
        self.journal_file = self.logs_dir / "agent_errors.jsonl"
        self.cards_dir = self.logs_dir / "agent_diagnostics"

        # Ensure directory structures exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    def record_error(
        self,
        exc: BaseException,
        component: str = "general",
        correlation_id: str = "",
        request_context: dict[str, Any] | None = None,
    ) -> AgentErrorRecord:
        """Capture and persist a detailed diagnostic snapshot of a runtime exception."""
        now = datetime.now(UTC)
        error_uuid = uuid.uuid4().hex[:6]
        error_id = f"ERR-{now.strftime('%Y%m%d-%H%M%S')}-{error_uuid}"

        # 1. Parse traceback and locate failing application frame
        tb = exc.__traceback__
        frames = traceback.extract_tb(tb)

        failing_file = ""
        failing_line = 0
        failing_function = ""

        # Find the innermost frame inside project or the very last frame
        if frames:
            app_frames = [f for f in frames if "antigravity_k" in f.filename or "src/" in f.filename]
            target_frame = app_frames[-1] if app_frames else frames[-1]
            failing_file = target_frame.filename
            failing_line = target_frame.lineno or 0
            failing_function = target_frame.name
        else:
            failing_file = "<unknown>"
            failing_line = 0
            failing_function = "<unknown>"

        # 2. Extract source code context around failing line
        code_context = _extract_code_context(failing_file, failing_line) if failing_file != "<unknown>" else ""

        # 3. Format full stack trace
        stack_trace = "".join(traceback.format_exception(type(exc), exc, tb))

        # 4. Sanitize request context
        sanitized_request: dict[str, Any] = {}
        if request_context:
            for k, v in request_context.items():
                if k == "headers" and isinstance(v, Mapping):
                    sanitized_request[k] = _sanitize_headers(
                        {str(header): str(value) for header, value in v.items()},
                    )
                else:
                    sanitized_request[k] = _sanitize_value(k, v)

        # 5. Environment snapshot
        env_snapshot = {
            "python_version": sys.version.split()[0],
            "antigravity_k_version": __version__,
            "os_platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        }

        # 6. Generate AI Fix Prompt
        ai_fix_prompt = _generate_ai_fix_prompt(
            error_id=error_id,
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
            failing_file=failing_file,
            failing_line=failing_line,
            failing_function=failing_function,
            code_context=code_context,
            stack_trace=stack_trace,
            request_context=sanitized_request,
        )

        record = AgentErrorRecord(
            error_id=error_id,
            timestamp=now.isoformat(),
            component=component,
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
            correlation_id=correlation_id,
            failing_file=failing_file,
            failing_line=failing_line,
            failing_function=failing_function,
            code_context=code_context,
            stack_trace=stack_trace,
            request_context=sanitized_request,
            environment=env_snapshot,
            ai_fix_prompt=ai_fix_prompt,
        )

        # 7. Persist to JSONL journal
        self._append_to_journal(record)

        # 8. Persist Markdown card
        self._write_markdown_card(record)

        logger.info(
            "Agent Error Journal recorded [%s] %s in %s:%d (correlation_id=%s)",
            record.error_id,
            record.error_type,
            record.failing_file,
            record.failing_line,
            record.correlation_id,
        )

        return record

    def _append_to_journal(self, record: AgentErrorRecord) -> None:
        """Append record as a single JSON line."""
        try:
            with open(self.journal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as err:
            logger.error("Failed to append error record to %s: %s", self.journal_file, err)

    def _write_markdown_card(self, record: AgentErrorRecord) -> None:
        """Write a formatted Markdown diagnostic card for human and agent review."""
        card_path = self.cards_dir / f"{record.error_id}.md"
        try:
            content = f"""---
title: "Incident Diagnostic: {record.error_id}"
error_id: "{record.error_id}"
error_type: "{record.error_type}"
timestamp: "{record.timestamp}"
component: "{record.component}"
correlation_id: "{record.correlation_id}"
failing_file: "{record.failing_file}"
failing_line: {record.failing_line}
failing_function: "{record.failing_function}"
status: "open"
---

# 🚨 Runtime Incident Diagnostic: `{record.error_id}`

- **Error Type**: `{record.error_type}`
- **Message**: `{record.message}`
- **Component**: `{record.component}`
- **Timestamp**: `{record.timestamp}`
- **Correlation ID**: `{record.correlation_id}`
- **Failure Location**: `{record.failing_file}:{record.failing_line}` (`{record.failing_function}`)

---

## 💻 Source Code Context

```python
{record.code_context or "# No code context available"}
```

---

## 📜 Full Stack Trace

```text
{record.stack_trace.strip()}
```

---

## 🌐 Request & Environment Context

- **Request Context**:
```json
{json.dumps(record.request_context, indent=2, ensure_ascii=False)}
```

- **System Environment**:
  - Python: `{record.environment.get("python_version")}`
  - Ssak-Ai: `{record.environment.get("antigravity_k_version")}`
  - OS: `{record.environment.get("os_platform")}`

---

## 🛠️ AI Agent Fix Prompt

{record.ai_fix_prompt}
"""
            card_path.write_text(content, encoding="utf-8")
        except Exception as err:
            logger.error("Failed to write diagnostic markdown card to %s: %s", card_path, err)

    def list_errors(self, limit: int = 50, component: str | None = None) -> list[AgentErrorRecord]:
        """List recorded errors in reverse chronological order."""
        if not self.journal_file.is_file():
            return []

        records: list[AgentErrorRecord] = []
        try:
            with open(self.journal_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec = AgentErrorRecord.from_dict(data)
                        if component and rec.component != component:
                            continue
                        records.append(rec)
                    except Exception:
                        continue
        except Exception as err:
            logger.error("Failed to read error journal: %s", err)

        records.reverse()
        return records[:limit]

    def get_error(self, error_id: str) -> AgentErrorRecord | None:
        """Fetch a specific error record by ID."""
        for rec in self.list_errors(limit=500):
            if rec.error_id == error_id:
                return rec
        return None

    def clear(self) -> None:
        """Clear all logged errors (useful for testing/maintenance)."""
        if self.journal_file.is_file():
            self.journal_file.unlink()
        for card in self.cards_dir.glob("ERR-*.md"):
            try:
                card.unlink()
            except Exception:
                pass


# Global singleton instance
_journal_instance: AgentErrorJournal | None = None


def get_agent_error_journal() -> AgentErrorJournal:
    """Get or initialize the global AgentErrorJournal singleton."""
    global _journal_instance
    if _journal_instance is None:
        _journal_instance = AgentErrorJournal()
    return _journal_instance


def record_agent_error(
    exc: BaseException,
    component: str = "general",
    correlation_id: str = "",
    request_context: dict[str, Any] | None = None,
) -> AgentErrorRecord:
    """Convenience helper to record an error in the global AgentErrorJournal."""
    return get_agent_error_journal().record_error(
        exc=exc,
        component=component,
        correlation_id=correlation_id,
        request_context=request_context,
    )
