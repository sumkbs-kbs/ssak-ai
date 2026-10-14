"""Incremental Code Graph — Real-time AST symbol synchronization.

Guarantees 100% freshness of symbol index (functions, classes, methods) by incrementally
re-parsing only the modified file on every write/replace tool operation.
"""

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolNode:
    """Indexed code symbol representation."""

    name: str
    kind: str  # "class", "function", "method"
    file_path: str
    line_number: int
    end_line: int
    signature: str


class IncrementalCodeGraph:
    """In-memory symbol graph with sub-millisecond incremental update capabilities."""

    def __init__(self, project_root: str | Path):
        self.project_root: Path = Path(project_root).resolve()
        # Map: file_path -> list of symbols in that file
        self._file_symbols: dict[str, list[SymbolNode]] = {}
        # Inverted index: symbol_name -> list of symbols across files
        self._symbol_index: dict[str, list[SymbolNode]] = {}

    def update_file(self, rel_path: str, content: str | None = None) -> int:
        """Incrementally update symbols for a single modified file.

        Args:
            rel_path: Relative file path from project root.
            content: In-memory content if available, else read from disk.

        Returns:
            Number of symbols extracted and updated.
        """
        full_path = self.project_root / rel_path
        if not rel_path.endswith(".py"):
            self.remove_file(rel_path)
            return 0

        if content is None:
            try:
                content = full_path.read_text(encoding="utf-8")
            except Exception:
                self.remove_file(rel_path)
                return 0

        # Remove old symbols from this file first
        self.remove_file(rel_path)

        # Parse new AST
        new_symbols: list[SymbolNode] = []
        try:
            tree = ast.parse(content, filename=str(full_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    new_symbols.append(
                        SymbolNode(
                            name=node.name,
                            kind="class",
                            file_path=rel_path,
                            line_number=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            signature=f"class {node.name}",
                        )
                    )
                elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    args = [a.arg for a in node.args.args]
                    sig = f"def {node.name}({', '.join(args)})"
                    new_symbols.append(
                        SymbolNode(
                            name=node.name,
                            kind="function",
                            file_path=rel_path,
                            line_number=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            signature=sig,
                        )
                    )
        except Exception as e:
            logger.debug("Incremental AST parse failed for %s: %s", rel_path, e)
            return 0

        # Store into index
        self._file_symbols[rel_path] = new_symbols
        for sym in new_symbols:
            self._symbol_index.setdefault(sym.name, []).append(sym)

        return len(new_symbols)

    def remove_file(self, rel_path: str) -> None:
        """Remove all symbols associated with a deleted or modified file."""
        old_symbols = self._file_symbols.pop(rel_path, [])
        for sym in old_symbols:
            if sym.name in self._symbol_index:
                self._symbol_index[sym.name] = [s for s in self._symbol_index[sym.name] if s.file_path != rel_path]
                if not self._symbol_index[sym.name]:
                    del self._symbol_index[sym.name]

    def lookup_symbol(self, name: str) -> list[SymbolNode]:
        """Look up symbol definition locations."""
        return self._symbol_index.get(name, [])

    def get_all_symbols_in_file(self, rel_path: str) -> list[SymbolNode]:
        """Get all symbols defined within a specific file."""
        return self._file_symbols.get(rel_path, [])
