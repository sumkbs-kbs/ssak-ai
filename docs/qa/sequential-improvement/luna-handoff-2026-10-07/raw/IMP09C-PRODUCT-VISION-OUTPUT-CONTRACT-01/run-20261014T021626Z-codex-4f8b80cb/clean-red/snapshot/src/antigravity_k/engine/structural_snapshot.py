"""Structural Context Snapshot — Deterministic filesystem and Git context snapshot.

For 27B-30B models (like Qwen3.8-27B), natural language summarization often drops exact
file paths and symbol names over long horizon turns.

This module deterministically builds a compact, pinned context block:
- Current Git branch & modified files status
- Active project file tree (filtered)
- Last modified files & recent actions
"""

import subprocess
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
        ".hypothesis",
        "dist",
        "build",
    }
)


@dataclass(frozen=True)
class StructuralSnapshot:
    """Immutable structural snapshot of the project."""

    branch: str
    git_status: str
    recent_modified_files: list[str]
    file_tree_snippet: str

    def format_pinned_block(self) -> str:
        """Format as a high-priority pinned context block for the 27B model."""
        lines = [
            "<!-- PINNED_STRUCTURAL_CONTEXT: DO NOT IGNORE -->",
            f"🌿 Branch: {self.branch or 'N/A'}",
        ]
        if self.git_status:
            lines.append(f"📊 Git Status Summary:\n{self.git_status}")
        if self.recent_modified_files:
            lines.append("📝 Recently Modified Files:")
            for f in self.recent_modified_files[:8]:
                lines.append(f"  - {f}")
        if self.file_tree_snippet:
            lines.append(f"📂 Workspace Map:\n{self.file_tree_snippet}")
        lines.append("<!-- END_PINNED_STRUCTURAL_CONTEXT -->")
        return "\n".join(lines)


class StructuralSnapshotBuilder:
    """Builds lightweight, deterministic structural snapshots without LLM summarization."""

    @staticmethod
    def build(project_root: str | Path, max_tree_lines: int = 25) -> StructuralSnapshot:
        """Construct the snapshot from disk and Git state.

        Args:
            project_root: Root directory of the repository.
            max_tree_lines: Maximum lines of file tree to include.

        Returns:
            StructuralSnapshot instance.
        """
        root = Path(project_root).resolve()

        branch = StructuralSnapshotBuilder._get_git_branch(root)
        status = StructuralSnapshotBuilder._get_git_status_summary(root)
        modified = StructuralSnapshotBuilder._get_recent_modified(root)
        tree = StructuralSnapshotBuilder._build_compact_tree(root, max_lines=max_tree_lines)

        return StructuralSnapshot(
            branch=branch,
            git_status=status,
            recent_modified_files=modified,
            file_tree_snippet=tree,
        )

    @staticmethod
    def _get_git_branch(root: Path) -> str:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return res.stdout.strip() if res.returncode == 0 else ""
        except Exception:
            return ""

    @staticmethod
    def _get_git_status_summary(root: Path) -> str:
        try:
            res = subprocess.run(
                ["git", "status", "--short"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            lines = res.stdout.strip().splitlines()
            if not lines:
                return "Clean workspace (no uncommitted changes)"
            if len(lines) > 8:
                return "\n".join(lines[:8]) + f"\n... and {len(lines) - 8} more changed files"
            return "\n".join(lines)
        except Exception:
            return ""

    @staticmethod
    def _get_recent_modified(root: Path) -> list[str]:
        try:
            res = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0:
                files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
                if files:
                    return files
        except Exception:
            pass
        return []

    @staticmethod
    def _build_compact_tree(root: Path, max_lines: int = 25) -> str:
        tree_lines: list[str] = []
        try:
            for top in sorted(root.iterdir()):
                if top.name.startswith(".") or top.name in _IGNORE_DIRS:
                    continue
                if top.is_dir():
                    tree_lines.append(f"📁 {top.name}/")
                    sub_count = 0
                    for child in sorted(top.iterdir()):
                        if child.name.startswith(".") or child.name in _IGNORE_DIRS:
                            continue
                        tree_lines.append(f"  📄 {child.name}")
                        sub_count += 1
                        if sub_count >= 5:
                            tree_lines.append("  ...")
                            break
                else:
                    tree_lines.append(f"📄 {top.name}")
                if len(tree_lines) >= max_lines:
                    tree_lines.append("...")
                    break
        except Exception:
            pass
        return "\n".join(tree_lines)
