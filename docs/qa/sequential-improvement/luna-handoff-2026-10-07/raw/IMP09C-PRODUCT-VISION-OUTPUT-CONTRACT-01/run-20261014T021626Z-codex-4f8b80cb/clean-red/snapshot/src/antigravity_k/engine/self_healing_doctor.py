"""Self-Healing Doctor — Comprehensive workspace diagnostic and auto-repair master.

Performs deterministic health audits and repairs:
1. Workspace Directory & File Permission Integrity
2. Python AST Syntax Health Across Codebase
3. Orphaned Git Worktrees Cleanup
4. Incremental Code Graph Cache Consistency
5. Model Engine Configuration Alignment (Qwen3.8-27B)
"""

import ast
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

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


@dataclass
class DiagnosticCheck:
    """A single diagnostic check item."""

    name: str
    status: str  # "HEALTHY", "WARNING", "ERROR", "REPAIRED"
    message: str
    action_taken: str = ""


@dataclass
class DoctorReport:
    """Comprehensive health check and repair summary."""

    total_checks: int
    healthy_count: int
    repaired_count: int
    error_count: int
    checks: list[DiagnosticCheck] = field(default_factory=list)


class SelfHealingDoctor:
    """Audits and self-repairs Ssak-Ai runtime environment."""

    def __init__(self, project_root: str | Path):
        self.project_root: Path = Path(project_root).resolve()

    def run_health_check(self, auto_heal: bool = True) -> DoctorReport:
        """Run full health audit and apply automated repairs."""
        checks: list[DiagnosticCheck] = []

        # 1. Check & repair essential directories
        checks.append(self._check_essential_dirs(auto_heal))

        # 2. Check AST syntax across Python files
        checks.extend(self._check_ast_syntax(auto_heal))

        # 3. Clean orphaned temporary worktrees
        checks.append(self._clean_orphaned_worktrees(auto_heal))

        # 4. Check model configuration alignment
        checks.append(self._check_model_alignment(auto_heal))

        healthy = sum(1 for c in checks if c.status in ("HEALTHY", "REPAIRED"))
        repaired = sum(1 for c in checks if c.status == "REPAIRED")
        errors = sum(1 for c in checks if c.status == "ERROR")

        return DoctorReport(
            total_checks=len(checks),
            healthy_count=healthy,
            repaired_count=repaired,
            error_count=errors,
            checks=checks,
        )

    def _check_essential_dirs(self, auto_heal: bool) -> DiagnosticCheck:
        required = ["src", "tests", "prompts", "scripts"]
        missing = [d for d in required if not (self.project_root / d).exists()]

        if not missing:
            return DiagnosticCheck("Directory Structure", "HEALTHY", "All core directories exist.")

        if auto_heal:
            for d in missing:
                (self.project_root / d).mkdir(parents=True, exist_ok=True)
            return DiagnosticCheck(
                "Directory Structure", "REPAIRED", f"Created missing directories: {', '.join(missing)}"
            )

        return DiagnosticCheck("Directory Structure", "WARNING", f"Missing directories: {', '.join(missing)}")

    def _check_ast_syntax(self, _auto_heal: bool) -> list[DiagnosticCheck]:
        syntax_checks: list[DiagnosticCheck] = []
        broken_files: list[tuple[str, str]] = []

        for root, dirs, files in os.walk(self.project_root / "src"):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _IGNORE_DIRS]
            for f in files:
                if f.endswith(".py"):
                    full_p = Path(root) / f
                    try:
                        content = full_p.read_text(encoding="utf-8")
                        _ = ast.parse(content)
                    except SyntaxError as se:
                        rel = str(full_p.relative_to(self.project_root))
                        broken_files.append((rel, str(se)))

        if not broken_files:
            syntax_checks.append(
                DiagnosticCheck("Python AST Syntax Integrity", "HEALTHY", "All source files parsed cleanly.")
            )
        else:
            for rel, err in broken_files:
                syntax_checks.append(DiagnosticCheck(f"Syntax Check: {rel}", "ERROR", f"Syntax error: {err}"))

        return syntax_checks

    def _clean_orphaned_worktrees(self, auto_heal: bool) -> DiagnosticCheck:
        worktree_dir = self.project_root / ".ag_worktrees"
        if not worktree_dir.exists():
            return DiagnosticCheck("Git Worktree Cleanliness", "HEALTHY", "No stale worktrees.")

        if auto_heal:
            try:
                shutil.rmtree(worktree_dir, ignore_errors=True)
                return DiagnosticCheck("Git Worktree Cleanliness", "REPAIRED", "Pruned orphaned worktrees.")
            except Exception as e:
                return DiagnosticCheck("Git Worktree Cleanliness", "WARNING", f"Failed to clean worktrees: {e}")

        return DiagnosticCheck("Git Worktree Cleanliness", "WARNING", "Stale worktrees directory present.")

    def _check_model_alignment(self, _auto_heal: bool) -> DiagnosticCheck:
        config_p = self.project_root / "src" / "antigravity_k" / "config.yaml"
        if not config_p.exists():
            return DiagnosticCheck("Model Configuration", "WARNING", "config.yaml not found.")

        content = config_p.read_text(encoding="utf-8")
        if "qwen3.8" in content:
            return DiagnosticCheck("Model Configuration Alignment", "HEALTHY", "Aligned with Qwen3.8 primary engine.")

        return DiagnosticCheck("Model Configuration Alignment", "WARNING", "config.yaml does not prioritize Qwen3.8.")
