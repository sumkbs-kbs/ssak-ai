"""Codex capability transfer contract.

This module turns Codex-like working strengths into deterministic,
testable Ssak-Ai operating rules. It does not copy private model
weights or hidden prompts; it implements observable engineering behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodexStrength:
    """One transferable working strength and its Ssak-Ai mapping."""

    title: str
    behavior: str
    antigravity_mapping: str
    verification_gate: str


@dataclass(frozen=True)
class CodexTransferReport:
    """Rendered output for `/codex` and prompt injection."""

    objective: str
    connected_tools: int
    known_skills: int
    strengths: tuple[CodexStrength, ...]
    operating_loop: tuple[str, ...]
    completion_gates: tuple[str, ...]


class CodexTransferEngine:
    """Build a Codex-grade, evidence-first operating contract."""

    STRENGTHS: tuple[CodexStrength, ...] = (
        CodexStrength(
            "Goal Contracting",
            "Restate the user goal, success criteria, constraints, and stop conditions before acting.",
            "Use `/goal` contracts and carry success criteria into implementation and report phases.",
            "Goal output includes Objective, Success Criteria, Risk Gate, and Next Actions.",
        ),
        CodexStrength(
            "Evidence-First Exploration",
            "Read the existing code, DOM, logs, and tests before making claims or edits.",
            "Require observe steps through file search, API checks, Browser DOM, and targeted tests.",
            "Every completed task cites changed files and executed verification commands.",
        ),
        CodexStrength(
            "Scoped Implementation",
            "Make the smallest coherent change that satisfies the objective and preserves local style.",
            "Prefer existing modules and helpers; avoid broad rewrites unless a gate requires them.",
            "Diff is limited to objective-owned paths and unrelated dirty worktree changes are preserved.",
        ),
        CodexStrength(
            "Autonomous Tool Judgment",
            "Select tools, MCP servers, skills, and local PC capabilities by risk, trust, and relevance.",
            "Route capability decisions through `AutonomousCapabilityPolicy` and `/capabilities`.",
            "Manifest shows allow/prompt/deny decisions for Tool/MCP/Skills without disconnected fallbacks.",
        ),
        CodexStrength(
            "Plan-Act-Observe Loop",
            "Iterate through plan, action, observation, repair, and re-verification until the task is done.",
            "Use TestHarness, self-test, and GoalRunner loop contracts as the default execution spine.",
            "Failures create a concrete defect entry and a follow-up verification step.",
        ),
        CodexStrength(
            "Output Quality Gate",
            "Reject thin, code-only, repetitive, unsafe, or unstructured answers when the task requires quality.",
            "Evaluate outputs with `QualityGate` and reconstruct weak responses through the orchestrator.",
            "Quality failures produce retry signals or explicit residual-risk reporting.",
        ),
        CodexStrength(
            "DOM-Grounded QA",
            "Verify user-facing UI with the same visible DOM path a user would touch.",
            "Use Browser DOM snapshots, command palette flows, console log checks, and self-test coverage.",
            "Fresh browser run has console error/warning 0 and visible success evidence.",
        ),
        CodexStrength(
            "Zero-Error Completion",
            "Treat avoidable errors, warnings, stale docs, and unverified assumptions as unfinished work.",
            "Gate completion on ruff, pytest, compileall, dashboard build, self-test, and docs update.",
            "Final handoff contains exact test results and any known residual risk.",
        ),
        CodexStrength(
            "Safety and Permission",
            "Escalate destructive, credential, deployment, payment, and critical desktop actions.",
            "Use PermissionGate plus capability risk policy before irreversible operations.",
            "Critical local PC capability reports `prompt` unless explicitly approved.",
        ),
        CodexStrength(
            "Human-Centered Handoff",
            "Explain what changed in plain language and keep reports reproducible.",
            "Update `test_report.md` and `test_process.md` with evidence instead of vague claims.",
            "Procedure documents include phase, command, result, defect, and fix history.",
        ),
    )

    OPERATING_LOOP: tuple[str, ...] = (
        "Observe: inspect files, tests, API, DOM, logs, and current docs before editing.",
        "Contract: convert the user objective into success criteria, risk gates, and verification commands.",
        "Select: choose tools/MCP/skills/local PC actions by relevance, risk, trust, and required evidence.",
        "Act: make scoped changes with existing project patterns and preserve unrelated worktree changes.",
        "Verify: run static analysis, focused tests, full regression, build, self-test, and DOM checks as applicable.",
        "Report: update test report/procedure and summarize changed behavior, tests, and residual risks.",
    )

    COMPLETION_GATES: tuple[str, ...] = (
        "No known fresh browser console error or warning for the validated path.",
        "No protected API flow fails because of missing internal authentication propagation.",
        "No user-facing output omits objective, verification, or residual-risk information.",
        "No connected tool, MCP, or skill path reports disconnected when the runtime can wire it.",
        "No final answer claims a test passed unless the exact command or DOM evidence was observed.",
    )

    def build(
        self,
        objective: str = "",
        connected_tools: int = 0,
        known_skills: int = 0,
    ) -> CodexTransferReport:
        """Build.

        Args:
            objective (str): str objective.
            connected_tools (int): int connected tools.
            known_skills (int): int known skills.

        Returns:
            CodexTransferReport: The codextransferreport result.

        """
        normalized = " ".join((objective or "general system upgrade").split())
        return CodexTransferReport(
            objective=normalized,
            connected_tools=max(0, connected_tools),
            known_skills=max(0, known_skills),
            strengths=self.STRENGTHS,
            operating_loop=self.OPERATING_LOOP,
            completion_gates=self.COMPLETION_GATES,
        )

    def render_markdown(self, report: CodexTransferReport) -> str:
        """Render markdown.

        Args:
            report (CodexTransferReport): CodexTransferReport report.

        Returns:
            str: The str result.

        """
        lines = [
            "# Codex Capability Transfer Manifest",
            "",
            f"**Objective:** `{report.objective}`",
            f"**Connected tools:** `{report.connected_tools}`",
            f"**Known skills:** `{report.known_skills}`",
            "",
            "## Transfer Boundary",
            "- Private model weights, hidden chain-of-thought, and proprietary internal prompts are not copied.",
            "- Observable working behavior is implemented as deterministic contracts, policies, gates, and tests.",
            "",
            "## Operating Loop",
        ]
        lines.extend(f"{index}. {step}" for index, step in enumerate(report.operating_loop, 1))

        lines.extend(
            [
                "",
                "## Strengths To Ssak-Ai Map",
                "",
                "| Strength | Codex-grade behavior | Ssak-Ai implementation | Verification gate |",
                "|---|---|---|---|",
            ],
        )
        for strength in report.strengths:
            lines.append(
                "| {title} | {behavior} | {mapping} | {gate} |".format(
                    title=strength.title,
                    behavior=strength.behavior,
                    mapping=strength.antigravity_mapping,
                    gate=strength.verification_gate,
                ),
            )

        lines.extend(["", "## Zero-Error Completion Gates"])
        lines.extend(f"- {gate}" for gate in report.completion_gates)

        lines.extend(
            [
                "",
                "## Immediate Commands",
                "- `/goal <objective>`: create the execution contract.",
                "- `/capabilities <objective>`: judge Tool/MCP/Skills/PC autonomy.",
                "- `/mcp radar`: inspect MCP upgrade and safety posture.",
                "- `POST /api/agent/tools/browser/self-test`: run integrated self-test.",
                "- `python -m ruff check src tests && python -m pytest`: enforce regression gates.",
            ],
        )
        return "\n".join(lines)

    def render_prompt_contract(self) -> str:
        """Render prompt contract.

        Returns:
            str: The str result.

        """
        report = self.build("agent execution policy")
        return (
            "## Codex-Grade Operating Contract\n"
            + "\n".join(f"- {step}" for step in report.operating_loop)
            + "\n\n## Codex-Grade Completion Gates\n"
            + "\n".join(f"- {gate}" for gate in report.completion_gates)
        )
