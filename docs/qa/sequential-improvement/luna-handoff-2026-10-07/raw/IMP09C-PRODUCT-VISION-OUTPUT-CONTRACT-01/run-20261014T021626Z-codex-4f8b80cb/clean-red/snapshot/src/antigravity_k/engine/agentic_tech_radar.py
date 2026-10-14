"""Agentic technology radar for Ssak-Ai.

The radar turns current public agent-framework patterns into a deterministic
upgrade plan.  It is intentionally dependency-free: the project can expose a
useful upgrade map even when the local model or network is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgenticTechSignal:
    """One externally observed agentic capability."""

    source: str
    capability: str
    pattern: str
    current_status: str
    recommendation: str
    priority: str
    evidence_url: str


@dataclass(frozen=True)
class AgenticUpgradeReport:
    """Structured agentic upgrade assessment."""

    objective: str
    last_reviewed: str
    signals: list[AgenticTechSignal]
    transfer_plan: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    @property
    def high_priority_count(self) -> int:
        """High Priority Count.

        Returns:
            int: The int result.

        """
        return sum(1 for signal in self.signals if signal.priority == "P0")

    @property
    def medium_priority_count(self) -> int:
        """Medium Priority Count.

        Returns:
            int: The int result.

        """
        return sum(1 for signal in self.signals if signal.priority == "P1")


class AgenticTechRadar:
    """Build a current, evidence-backed agentic upgrade matrix."""

    def __init__(self, last_reviewed: str = "2026-05-07"):
        """Initialize the AgenticTechRadar.

        Args:
            last_reviewed (str): str last reviewed.

        """
        self.last_reviewed: str = last_reviewed

    def evaluate(self, objective: str = "") -> AgenticUpgradeReport:
        """Evaluate.

        Args:
            objective (str): str objective.

        Returns:
            AgenticUpgradeReport: The agenticupgradereport result.

        """
        normalized = objective.strip() or "Ssak-Ai agentic upgrade review"
        signals = [
            AgenticTechSignal(
                source="LangGraph",
                capability="Durable state graph execution",
                pattern=(
                    "Long-running agents should persist state, resume after failures, "
                    "and expose human-in-the-loop checkpoints."
                ),
                current_status=(
                    "AgentStateGraph already exists, but durable checkpoint restore "
                    "and run replay are not yet first-class user commands."
                ),
                recommendation=(
                    "Persist StateContext checkpoints and expose replay/resume controls "
                    "through slash commands and the dashboard."
                ),
                priority="P0",
                evidence_url="https://github.com/langchain-ai/langgraph",
            ),
            AgenticTechSignal(
                source="Hugging Face smolagents",
                capability="Code-action agents with sandboxed execution",
                pattern=(
                    "CodeAgent-style action generation can be expressive, but must run "
                    "inside a constrained sandbox with explicit imports and tool bridges."
                ),
                current_status=(
                    "Ssak-Ai has PermissionGate and shell/file tools, but no separate code-action sandbox contract."
                ),
                recommendation=(
                    "Add a CodeAction lane that requires sandbox root, import allowlist, "
                    "timeout, and artifact diff before execution."
                ),
                priority="P0",
                evidence_url="https://github.com/huggingface/smolagents",
            ),
            AgenticTechSignal(
                source="Hugging Face Hub MCP",
                capability="MCP-native tool ecosystem",
                pattern=(
                    "Agents can connect to local stdio or remote HTTP/SSE MCP servers "
                    "and stream tool results back into the chat loop."
                ),
                current_status=(
                    "ToolRegistry is local and typed, but MCP server discovery/import "
                    "is not yet a native registry path."
                ),
                recommendation=(
                    "Add MCP adapter metadata to ToolRegistry and mark imported tools "
                    "with transport, trust level, and teardown policy."
                ),
                priority="P0",
                evidence_url="https://huggingface.co/docs/huggingface_hub/package_reference/mcp",
            ),
            AgenticTechSignal(
                source="OpenAI Agents SDK",
                capability="Handoffs, guardrails, sessions, tracing",
                pattern=(
                    "Production agents need explicit handoffs, input/output guardrails, "
                    "session memory, and traces over LLM/tool/handoff spans."
                ),
                current_status=(
                    "Ssak-Ai has OrchestratorAgent, QualityGate, SessionManager, "
                    "and AgentTracer, but they are not summarized as one readiness score."
                ),
                recommendation=(
                    "Compute an Agentic Readiness Score from tracing, session, guardrail, "
                    "and quality-gate coverage for every autonomous run."
                ),
                priority="P1",
                evidence_url="https://github.com/openai/openai-agents-python",
            ),
            AgenticTechSignal(
                source="Microsoft AutoGen / Agent Framework",
                capability="Multi-agent team patterns and benchmarking",
                pattern=(
                    "Magentic-style teams combine web browsing, file handling, coding, "
                    "and terminal specialists, then validate with benchmark harnesses."
                ),
                current_status=(
                    "Ssak-Ai has CEO routing, persona agents, browser QA, and "
                    "self-test, but no public benchmark profile command."
                ),
                recommendation=(
                    "Expose a benchmark mode that records task class, tool count, "
                    "retries, pass/fail, and regression trend for agentic runs."
                ),
                priority="P1",
                evidence_url="https://github.com/microsoft/autogen",
            ),
        ]

        transfer_plan = [
            "1. Gate every autonomous run with an explicit intent contract and readiness score.",
            "2. Persist StateContext checkpoints so failed long-running work can resume instead of restart.",
            "3. Treat MCP tools as first-class ToolRegistry entries with transport and trust metadata.",
            "4. Add a sandboxed CodeAction lane before enabling code-as-action execution.",
            "5. Record handoff, tool, quality, and DOM evidence into one trace-backed report.",
        ]
        guardrails = [
            "Do not import remote tools without a trust label and teardown policy.",
            "Do not run code-action snippets outside the project sandbox.",
            "Do not mark external framework parity as complete without local regression tests.",
            "Keep human approval gates for deployment, deletion, secrets, and network writes.",
        ]
        return AgenticUpgradeReport(
            objective=normalized,
            last_reviewed=self.last_reviewed,
            signals=signals,
            transfer_plan=transfer_plan,
            guardrails=guardrails,
        )

    def render_markdown(self, report: AgenticUpgradeReport) -> str:
        """Render the upgrade report for slash commands and API output."""
        lines: list[str] = [
            "# Agentic Upgrade Radar",
            "",
            f"**Objective:** {report.objective}",
            f"**Last reviewed:** {report.last_reviewed}",
            (f"**Priority mix:** P0={report.high_priority_count}, P1={report.medium_priority_count}"),
            "",
            "## Upgrade Decision Matrix",
            "",
            "| Source | Capability | Current status | Recommendation | Priority |",
            "| --- | --- | --- | --- | --- |",
        ]
        for signal in report.signals:
            lines.append(
                "| "
                + " | ".join(
                    [
                        signal.source,
                        signal.capability,
                        signal.current_status,
                        signal.recommendation,
                        signal.priority,
                    ],
                )
                + " |",
            )

        lines.extend(["", "## Transfer Plan", ""])
        lines.extend(f"- {item}" for item in report.transfer_plan)
        lines.extend(["", "## Guardrails", ""])
        lines.extend(f"- {item}" for item in report.guardrails)
        lines.extend(["", "## Evidence Sources", ""])
        for signal in report.signals:
            lines.append(f"- **{signal.source}:** {signal.evidence_url}")

        return "\n".join(lines)

    def to_dict(self, report: AgenticUpgradeReport) -> dict[str, object]:
        """Return a JSON-friendly form for future API use."""
        return {
            "objective": report.objective,
            "last_reviewed": report.last_reviewed,
            "priority": {
                "P0": report.high_priority_count,
                "P1": report.medium_priority_count,
            },
            "signals": [
                {
                    "source": signal.source,
                    "capability": signal.capability,
                    "pattern": signal.pattern,
                    "current_status": signal.current_status,
                    "recommendation": signal.recommendation,
                    "priority": signal.priority,
                    "evidence_url": signal.evidence_url,
                }
                for signal in report.signals
            ],
            "transfer_plan": report.transfer_plan,
            "guardrails": report.guardrails,
        }
