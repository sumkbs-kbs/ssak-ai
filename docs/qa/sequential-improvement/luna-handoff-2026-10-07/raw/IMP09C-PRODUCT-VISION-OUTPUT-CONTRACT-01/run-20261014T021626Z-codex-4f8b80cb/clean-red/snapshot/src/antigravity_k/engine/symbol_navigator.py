"""Symbol-Aware Code Graph Navigator — Fast AST Symbol Index for 27B targeting.

Allows the 27B model to instantly discover symbol locations (classes, functions, methods)
without grepping entire directories or reading irrelevant files.
"""

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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
class CodeSymbol:
    """Indexed code symbol."""

    name: str
    kind: str  # "function", "class", "method"
    file_path: str
    line_number: int
    end_line: int
    signature: str


class SymbolNavigator:
    """Builds and queries an in-memory symbol index for rapid code discovery."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root: Path = Path(project_root).resolve()
        self.symbols: dict[str, list[CodeSymbol]] = {}
        _ = self.index_project()

    def index_project(self) -> int:
        """Scan all Python files in the workspace and extract symbols."""
        self.symbols.clear()
        indexed_count = 0

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _IGNORE_DIRS]
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    try:
                        rel_path = str(full_path.relative_to(self.project_root))
                        content = full_path.read_text(encoding="utf-8")
                        tree = ast.parse(content, filename=str(full_path))
                        file_symbols = self._extract_ast_symbols(tree, rel_path)
                        for sym in file_symbols:
                            self.symbols.setdefault(sym.name, []).append(sym)
                            indexed_count += 1
                    except Exception:
                        continue

        return indexed_count

    def find_symbol(self, query: str) -> list[CodeSymbol]:
        """Find matching symbols by exact or partial name."""
        results: list[CodeSymbol] = []
        q_lower = query.lower()

        # Exact matches first
        if query in self.symbols:
            results.extend(self.symbols[query])

        # Partial matches
        for name, sym_list in self.symbols.items():
            if name != query and q_lower in name.lower():
                results.extend(sym_list)

        return results[:10]

    def _extract_ast_symbols(self, tree: ast.AST, file_path: str) -> list[CodeSymbol]:
        symbols: list[CodeSymbol] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        kind="class",
                        file_path=file_path,
                        line_number=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        signature=f"class {node.name}",
                    )
                )
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = [a.arg for a in node.args.args]
                sig = f"def {node.name}({', '.join(args)})"
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        kind="function",
                        file_path=file_path,
                        line_number=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        signature=sig,
                    )
                )
        return symbols
