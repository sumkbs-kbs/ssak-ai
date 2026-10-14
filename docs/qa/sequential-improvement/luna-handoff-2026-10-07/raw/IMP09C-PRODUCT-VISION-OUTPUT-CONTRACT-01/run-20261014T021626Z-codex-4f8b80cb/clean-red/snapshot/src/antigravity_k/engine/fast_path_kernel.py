"""Fast-Path Direct Kernel — Zero-latency query resolution bypass.

First Principle: Delete the Process.
80% of developer agent queries (e.g. "Where is class X?", "What does file Y look like?",
"Check git status") do not need an expensive, high-latency multi-turn LLM generation cycle.

This kernel intercepts deterministic intent and resolves queries directly in <5ms.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from antigravity_k.engine.incremental_code_graph import IncrementalCodeGraph
from antigravity_k.engine.symbol_navigator import SymbolNavigator

_SYMBOL_QUERY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""(?i)^(?:where\s+is|find\s+symbol|locate|show\s+definition\s+of)\s+[`"']?(?P<sym>[a-zA-Z_][a-zA-Z0-9_]*)['"]?""",
)

_FILE_READ_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""(?i)^(?:view|cat|read|show\s+file)\s+[`"']?(?P<path>[a-zA-Z0-9_\-\.\/]+)['"]?""",
)


@dataclass
class FastPathResult:
    """Result of direct fast-path execution."""

    handled: bool
    response: str
    latency_ms: float
    source: str


class FastPathKernel:
    """Bypasses LLM orchestration loops for deterministic queries."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root: Path = Path(project_root).resolve()
        self.navigator: SymbolNavigator = SymbolNavigator(self.project_root)
        self.code_graph: IncrementalCodeGraph = IncrementalCodeGraph(self.project_root)

    def try_execute(self, user_query: str) -> FastPathResult:
        """Attempt to resolve user query directly without invoking LLM."""
        import time

        start = time.perf_counter()
        q = user_query.strip()

        # 1. Check for symbol discovery intent
        sym_match = _SYMBOL_QUERY_PATTERN.match(q)
        if sym_match:
            sym_name = sym_match.group("sym")
            matches = self.navigator.find_symbol(sym_name)
            elapsed = (time.perf_counter() - start) * 1000
            if matches:
                lines = [
                    f"⚡ [Fast-Path Discovery: <{elapsed:.1f}ms] Found `{len(matches)}` definition(s) for `{sym_name}`:"
                ]
                for m in matches:
                    lines.append(
                        f"  • `{m.kind} {m.name}` at `{m.file_path}:{m.line_number}-{m.end_line}` -> `{m.signature}`"
                    )
                return FastPathResult(
                    handled=True, response="\n".join(lines), latency_ms=elapsed, source="SymbolNavigator"
                )
            else:
                return FastPathResult(
                    handled=True,
                    response=f"⚡ [Fast-Path Discovery: <{elapsed:.1f}ms] Symbol `{sym_name}` not found in workspace.",
                    latency_ms=elapsed,
                    source="SymbolNavigator",
                )

        # 2. Check for direct file read intent
        file_match = _FILE_READ_PATTERN.match(q)
        if file_match:
            rel_file = file_match.group("path")
            target = self.project_root / rel_file
            elapsed = (time.perf_counter() - start) * 1000
            if target.exists() and target.is_file():
                try:
                    content = target.read_text(encoding="utf-8")
                    resp = f"⚡ [Fast-Path Direct Read: <{elapsed:.1f}ms] `{rel_file}` ({len(content.splitlines())} lines):\n```\n{content}\n```"
                    return FastPathResult(handled=True, response=resp, latency_ms=elapsed, source="DirectFileRead")
                except Exception as ex:
                    return FastPathResult(
                        handled=True,
                        response=f"⚡ [Fast-Path Error] Failed to read `{rel_file}`: {ex}",
                        latency_ms=elapsed,
                        source="DirectFileRead",
                    )

        return FastPathResult(handled=False, response="", latency_ms=0.0, source="Bypassed")
