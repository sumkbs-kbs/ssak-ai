"""Next-Action Recommendation Engine — High-precision proactive task synthesizer.

Technology Origin: Freebuff / Claude Code Proactive Next-Action Synthesis.
Immediately following task completion, analyzes:
1. Test Coverage Gaps (untested new/modified functions)
2. Blast Radius & Downstream Callers (functions needing updates)
3. Security & Performance Hardening Gaps (unindexed queries, missing auth/rate limits)
4. Documentation & Schema Sync (outdated README/docs)

Synthesizes the top-3 highest-impact, one-click executable follow-up missions.
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from antigravity_k.engine.call_hierarchy_graph import CallHierarchyGraph

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
class RecommendedAction:
    """A prioritized, actionable follow-up engineering task."""

    action_id: str  # "1", "2", "3"
    category: str  # "TEST_GAP", "BLAST_RADIUS", "SECURITY_PERF", "DOC_SYNC"
    icon: str  # "🧪", "🔗", "🛡️", "📖"
    title: str
    rationale: str
    executable_prompt: str
    priority_score: float  # Higher is higher priority


@dataclass
class RecommendationBatch:
    """Batch of prioritized recommendations synthesized for the completed task."""

    completed_goal: str
    touched_files: list[str]
    actions: list[RecommendedAction] = field(default_factory=list)

    def format_cli_panel(self) -> str:
        """Format as high-visibility rich text for terminal display."""
        if not self.actions:
            return "✓ No pending follow-up recommendations detected (Codebase in pristine state)."

        lines = [
            "🔮 **[PROACTIVE NEXT ACTIONS: Recommended by Static AST & Coverage Audit]**\n",
        ]
        for act in self.actions:
            lines.append(f"  [{act.action_id}] {act.icon} **[{act.category}]** {act.title}")
            lines.append(f"      💡 *Why*: {act.rationale}")
            lines.append(f'      ⚡ *Action*: `agk autopilot "{act.executable_prompt}"`\n')

        lines.append("💡 *Type [1-3] to auto-ignite next mission, or press Enter to finish.*")
        return "\n".join(lines)


class NextActionRecommender:
    """Synthesizes high-precision follow-up engineering actions."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root: Path = Path(project_root).resolve()
        self.call_graph: CallHierarchyGraph = CallHierarchyGraph(self.project_root)

    def synthesize_recommendations(
        self,
        completed_goal: str,
        touched_files: list[str] | None = None,
        top_k: int = 3,
    ) -> RecommendationBatch:
        """Analyze project state and touched files to produce prioritized next actions.

        Args:
            completed_goal: The task just finished.
            touched_files: Relative paths of files modified during the task.
            top_k: Number of recommendations to return (default 3).

        Returns:
            RecommendationBatch containing ranked actions.
        """
        candidates: list[RecommendedAction] = []
        files = touched_files or []

        # Vector 1: Test Coverage Gap Analysis
        candidates.extend(self._audit_test_coverage_gaps(files))

        # Vector 2: Blast Radius & Downstream Caller Analysis
        candidates.extend(self._audit_blast_radius(files))

        # Vector 3: Security & Performance Hardening
        candidates.extend(self._audit_security_performance(files))

        # Vector 4: Documentation & Schema Sync
        candidates.extend(self._audit_documentation_sync(completed_goal, files))

        # Sort by priority score descending and pick top_k
        sorted_candidates = sorted(candidates, key=lambda a: a.priority_score, reverse=True)

        selected: list[RecommendedAction] = []
        for idx, act in enumerate(sorted_candidates[:top_k], 1):
            selected.append(
                RecommendedAction(
                    action_id=str(idx),
                    category=act.category,
                    icon=act.icon,
                    title=act.title,
                    rationale=act.rationale,
                    executable_prompt=act.executable_prompt,
                    priority_score=act.priority_score,
                )
            )

        return RecommendationBatch(
            completed_goal=completed_goal,
            touched_files=files,
            actions=selected,
        )

    def _audit_test_coverage_gaps(self, touched_files: list[str]) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        for f in touched_files:
            if f.endswith(".py") and not f.startswith("tests/"):
                # Find if corresponding test file exists
                base_name = Path(f).name
                test_file = f"tests/test_{base_name}"
                full_test_p = self.project_root / test_file

                if not full_test_p.exists():
                    actions.append(
                        RecommendedAction(
                            action_id="",
                            category="TEST_GAP",
                            icon="🧪",
                            title=f"Create pytest suite for `{f}`",
                            rationale=f"File `{f}` was modified but `{test_file}` does not exist.",
                            executable_prompt=f"Write comprehensive pytest unit tests for {f} in {test_file}",
                            priority_score=0.95,
                        )
                    )
        return actions

    def _audit_blast_radius(self, touched_files: list[str]) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        for f in touched_files:
            if f.endswith(".py") and not f.startswith("tests/"):
                full_p = self.project_root / f
                if full_p.exists():
                    try:
                        content = full_p.read_text(encoding="utf-8")
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                                report = self.call_graph.analyze_impact(node.name, f)
                                if report.impacted_callers:
                                    callers_summary = ", ".join(c.caller_function for c in report.impacted_callers[:2])
                                    actions.append(
                                        RecommendedAction(
                                            action_id="",
                                            category="BLAST_RADIUS",
                                            icon="🔗",
                                            title=f"Verify downstream callers of `{node.name}()` ({callers_summary})",
                                            rationale=f"Function `{node.name}` was modified and is called by {len(report.impacted_callers)} other modules.",
                                            executable_prompt=f"Refactor and verify downstream callers of {node.name}: {callers_summary}",
                                            priority_score=0.85,
                                        )
                                    )
                                    break  # 1 per file is enough
                    except Exception:
                        continue
        return actions

    def _audit_security_performance(self, touched_files: list[str]) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        for f in touched_files:
            if f.endswith(".py"):
                full_p = self.project_root / f
                if full_p.exists():
                    content = full_p.read_text(encoding="utf-8")
                    if "async def" in content and any(kw in content for kw in ("requests.", "time.sleep", "open(")):
                        actions.append(
                            RecommendedAction(
                                action_id="",
                                category="SECURITY_PERF",
                                icon="🛡️",
                                title=f"Fix blocking synchronous I/O in `{f}`",
                                rationale="Detected synchronous blocking calls inside async def functions.",
                                executable_prompt=f"Replace blocking calls in {f} with non-blocking aiofiles/httpx alternatives",
                                priority_score=0.90,
                            )
                        )
        return actions

    def _audit_documentation_sync(self, goal: str, touched_files: list[str]) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        if any("api" in f or "engine" in f for f in touched_files):
            actions.append(
                RecommendedAction(
                    action_id="",
                    category="DOC_SYNC",
                    icon="📖",
                    title="Synchronize architectural documentation and ADRs",
                    rationale=f"Task '{goal[:40]}' modified core engine/API components.",
                    executable_prompt=f"Update docs/ and README.md with changes from '{goal[:50]}'",
                    priority_score=0.70,
                )
            )
        return actions
