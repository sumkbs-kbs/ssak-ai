"""Call-Hierarchy & Impact Analyzer Engine — Zero-latency static caller-callee resolution.

When a 27B model refactors a function signature or class method, it often overlooks
downstream callers in other modules.

This module builds a workspace-wide invocation graph using Python AST parsing:
- Finds all callers of a target symbol (Inbound Callers)
- Finds all callees of a target symbol (Outbound Callees)
- Identifies associated unit test files that must be executed or updated
"""

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, override

logger = logging.getLogger(__name__)

_IGNORE_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)


@dataclass(frozen=True)
class FunctionCallSite:
    """Represents a specific invocation of a function."""

    caller_function: str
    caller_file: str
    called_function: str
    line_number: int


@dataclass
class ImpactAnalysisReport:
    """Report detailing the blast radius of modifying a target symbol/file."""

    target_symbol: str
    target_file: str
    impacted_callers: list[FunctionCallSite] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    recommended_tests: list[str] = field(default_factory=list)

    def format_for_model(self) -> str:
        """Format a clear, high-signal impact advisory for the 27B model."""
        if not self.impacted_callers and not self.impacted_files:
            return (
                f"ℹ️ [Impact Analysis] No external callers detected for `{self.target_symbol}` in `{self.target_file}`."
            )

        lines = [
            f"🔍 **[Call-Hierarchy Impact Analysis for `{self.target_symbol}`]**",
            f"   Modifying this will affect the following {len(self.impacted_callers)} caller(s) across {len(self.impacted_files)} file(s):",
        ]
        for site in self.impacted_callers[:6]:
            lines.append(
                f"   • `{site.caller_file}:{site.line_number}` in `{site.caller_function}()` calls `{site.called_function}()`"
            )

        if self.recommended_tests:
            lines.append("\n🧪 **Recommended Tests to Re-verify:**")
            for t in self.recommended_tests[:4]:
                lines.append(f"   - `{t}`")

        lines.append("\n💡 **Action:** Ensure you update these callers or verify compatibility.")
        return "\n".join(lines)


class CallHierarchyGraph:
    """Maintains an in-memory invocation graph across all Python files in the workspace."""

    def __init__(self, project_root: str | Path):
        self.project_root: Path = Path(project_root).resolve()
        # Map: called_function_name -> list of FunctionCallSite
        self._inbound_calls: dict[str, list[FunctionCallSite]] = {}
        # Map: file_path -> list of FunctionCallSite originating from that file
        self._file_call_sites: dict[str, list[FunctionCallSite]] = {}
        _ = self.rebuild_graph()

    def rebuild_graph(self) -> int:
        """Scan workspace and construct the full caller-callee invocation graph."""
        self._inbound_calls.clear()
        self._file_call_sites.clear()
        total_calls = 0

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _IGNORE_DIRS]
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    rel_path = str(full_path.relative_to(self.project_root))
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        calls = self._parse_calls_in_file(content, rel_path)
                        self._file_call_sites[rel_path] = calls
                        for site in calls:
                            self._inbound_calls.setdefault(site.called_function, []).append(site)
                            total_calls += 1
                    except Exception:
                        continue

        return total_calls

    def analyze_impact(self, symbol_name: str, file_path: str = "") -> ImpactAnalysisReport:
        """Analyze the impact of modifying a function or class.

        Args:
            symbol_name: The name of the function or method.
            file_path: Optional relative file path of the symbol.

        Returns:
            ImpactAnalysisReport detailing callers and recommended test files.
        """
        callers = self._inbound_calls.get(symbol_name, [])
        # Filter out self-calls within the same function
        external_callers = [c for c in callers if not (c.caller_file == file_path and c.caller_function == symbol_name)]

        impacted_files = sorted({c.caller_file for c in external_callers})

        # Discover relevant test files
        tests: set[str] = set()
        for f in impacted_files + ([file_path] if file_path else []):
            stem = Path(f).stem
            test_candidate = self.project_root / "tests" / f"test_{stem}.py"
            if test_candidate.exists():
                tests.add(str(test_candidate.relative_to(self.project_root)))

        return ImpactAnalysisReport(
            target_symbol=symbol_name,
            target_file=file_path,
            impacted_callers=external_callers,
            impacted_files=impacted_files,
            recommended_tests=sorted(tests),
        )

    def _parse_calls_in_file(self, code: str, file_path: str) -> list[FunctionCallSite]:
        call_sites: list[FunctionCallSite] = []
        try:
            tree = ast.parse(code, filename=file_path)
        except Exception:
            return []

        class CallVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_function: str = "<module>"

            @override
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                prev = self.current_function
                self.current_function = node.name
                self.generic_visit(node)
                self.current_function = prev

            @override
            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                prev = self.current_function
                self.current_function = node.name
                self.generic_visit(node)
                self.current_function = prev

            @override
            def visit_Call(self, node: ast.Call) -> None:
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name:
                    call_sites.append(
                        FunctionCallSite(
                            caller_function=self.current_function,
                            caller_file=file_path,
                            called_function=func_name,
                            line_number=node.lineno,
                        )
                    )
                self.generic_visit(node)

        visitor = CallVisitor()
        visitor.visit(tree)
        return call_sites
