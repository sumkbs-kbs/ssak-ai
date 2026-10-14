"""Autonomous capability policy.

Ssak-Ai can see many capability sources: built-in tools, MCP tools,
skills, local shell access, browser/DOM control, external brains, and desktop
automation.  This module gives them one decision language so the agent can use
safe capabilities by itself while escalating risky actions.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

RISK_ORDER = {
    "safe": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SAFE_TRUST_LEVELS = {"local", "verified", "partner", "system", "builtin"}
HIGH_RISK_ACTION_WORDS = {
    "delete",
    "remove",
    "rm",
    "format",
    "shutdown",
    "reboot",
    "deploy",
    "payment",
    "purchase",
    "결제",
    "삭제",
    "배포",
    "초기화",
    "포맷",
}


class MetadataTool(Protocol):
    """Metadatatool.

    Bases: Protocol
    """

    @property
    def name(self) -> str: ...

    def to_metadata(self) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class CapabilityDecision:
    """A single autonomous-use decision for a capability."""

    capability_id: str
    capability_type: str
    decision: str
    risk_level: str
    trust_level: str
    reason: str
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)

    @property
    def allows_autonomous_use(self) -> bool:
        """Allows Autonomous Use.

        Returns:
            bool: The bool result.

        """
        return self.decision == "allow"

    @property
    def requires_approval(self) -> bool:
        """Requires Approval.

        Returns:
            bool: The bool result.

        """
        return self.decision == "prompt"

    @property
    def is_blocked(self) -> bool:
        """Check if blocked.

        Returns:
            bool: The bool result.

        """
        return self.decision == "deny"


class AutonomousCapabilityPolicy:
    """Shared policy for tools, MCP servers, skills, and local PC capabilities."""

    def __init__(
        self,
        project_root: str | None = None,
        max_autonomous_risk: str = "high",
        allow_critical_autonomy: bool = False,
    ):
        """Initialize the AutonomousCapabilityPolicy.

        Args:
            project_root (str | None): str | None project root.
            max_autonomous_risk (str): str max autonomous risk.
            allow_critical_autonomy (bool): bool allow critical autonomy.

        """
        self.project_root: str = os.path.abspath(project_root or os.getcwd())
        self.max_autonomous_risk: str = max_autonomous_risk
        self.allow_critical_autonomy: bool = allow_critical_autonomy

    def set_project_root(self, project_root: str) -> None:
        """Set project root.

        Args:
            project_root (str): str project root.

        """
        self.project_root = os.path.abspath(project_root)

    def decide_tool(
        self,
        tool: MetadataTool,
        args: Mapping[str, object] | None = None,
        objective: str = "",
    ) -> CapabilityDecision:
        """Decide Tool.

        Args:
            tool (MetadataTool): MetadataTool tool.
            args (Mapping[str, Any] | None): Mapping[str, Any] | None args.
            objective (str): str objective.

        Returns:
            CapabilityDecision: The capabilitydecision result.

        """
        metadata = dict(tool.to_metadata() or {})
        risk = str(metadata.get("risk_level") or "medium")
        mcp_raw = metadata.get("mcp")
        mcp: dict[str, object] = dict(cast(Mapping[str, object], mcp_raw)) if isinstance(mcp_raw, Mapping) else {}
        mcp_trust = mcp.get("trust_level")
        trust = str(mcp_trust or metadata.get("trust_level") or "builtin")
        capability_id = str(metadata.get("name") or tool.name)

        if mcp and mcp.get("remote") and not mcp.get("authenticated"):
            return CapabilityDecision(
                capability_id,
                "mcp_tool",
                "deny",
                risk,
                trust,
                "Remote MCP tool is not authenticated.",
                evidence=["mcp.remote_without_auth"],
            )

        if not self._is_trusted(trust):
            return CapabilityDecision(
                capability_id,
                "mcp_tool" if mcp else "tool",
                "prompt",
                risk,
                trust,
                "Capability source is not trusted enough for autonomous use.",
                evidence=["trust_level"],
            )

        if self._has_high_risk_intent(objective, args):
            return CapabilityDecision(
                capability_id,
                "mcp_tool" if mcp else "tool",
                "prompt",
                risk,
                trust,
                "Objective or arguments contain irreversible/high-impact action cues.",
                evidence=["objective_risk"],
            )

        if risk == "critical" and not self.allow_critical_autonomy:
            return CapabilityDecision(
                capability_id,
                "mcp_tool" if mcp else "tool",
                "prompt",
                risk,
                trust,
                "Critical PC capabilities require explicit approval before execution.",
                evidence=["critical_capability"],
            )

        max_allowed = RISK_ORDER.get(self.max_autonomous_risk, RISK_ORDER["medium"])
        if RISK_ORDER.get(risk, RISK_ORDER["medium"]) <= max_allowed:
            return CapabilityDecision(
                capability_id,
                "mcp_tool" if mcp else "tool",
                "allow",
                risk,
                trust,
                "Risk and trust fit the autonomous execution policy.",
                evidence=["risk_policy"],
            )

        return CapabilityDecision(
            capability_id,
            "mcp_tool" if mcp else "tool",
            "prompt",
            risk,
            trust,
            "Risk exceeds autonomous execution threshold.",
            evidence=["risk_policy"],
        )

    def decide_skill(
        self,
        skill_id: str,
        skill: Mapping[str, object],
        objective: str,
    ) -> CapabilityDecision:
        """Decide Skill.

        Args:
            skill_id (str): str skill id.
            skill (Mapping[str, Any]): Mapping[str, Any] skill.
            objective (str): str objective.

        Returns:
            CapabilityDecision: The capabilitydecision result.

        """
        score = self.score_skill(skill_id, skill, objective)
        risk = str(skill.get("risk_level") or "safe").lower()
        trust = str(
            skill.get("trust_level") or ("local" if not skill.get("is_global") else "verified"),
        )

        if score <= 0:
            decision = "deny"
            reason = "Skill is not relevant to the current objective."
        elif not self._is_trusted(trust):
            decision = "prompt"
            reason = "Skill source is not trusted enough for automatic activation."
        elif risk == "critical" and not self.allow_critical_autonomy:
            decision = "prompt"
            reason = "Critical skill instructions require explicit approval."
        elif RISK_ORDER.get(risk, 0) <= RISK_ORDER.get(self.max_autonomous_risk, 2):
            decision = "allow"
            reason = "Skill relevance and risk fit the autonomous activation policy."
        else:
            decision = "prompt"
            reason = "Skill risk exceeds autonomous activation threshold."

        return CapabilityDecision(
            capability_id=skill_id,
            capability_type="skill",
            decision=decision,
            risk_level=risk,
            trust_level=trust,
            reason=reason,
            score=score,
            evidence=["skill_relevance", "skill_risk"],
        )

    def score_skill(self, skill_id: str, skill: Mapping[str, object], objective: str) -> float:
        """Score Skill.

        Args:
            skill_id (str): str skill id.
            skill (Mapping[str, Any]): Mapping[str, Any] skill.
            objective (str): str objective.

        Returns:
            float: The float result.

        """
        query = _normalize_tokens(objective)
        if not query:
            return 0.0

        name = str(skill.get("name") or skill_id)
        description = str(skill.get("description") or "")
        tags = " ".join(_string_values(skill.get("tags")))
        preview = str(skill.get("content") or "")[:1000]
        haystack = f"{skill_id} {name} {description} {tags} {preview}".lower()

        score = 0.0
        name_lower = name.lower()
        objective_lower = objective.lower()
        if skill_id.lower() in objective_lower or (name_lower and name_lower in objective_lower):
            score += 10

        for token in query:
            if token in haystack:
                score += 1.5 if len(token) > 4 else 0.5

        if any(token in {"test", "qa", "검증", "테스트"} for token in query):
            if any(word in haystack for word in ("test", "qa", "quality", "검증", "테스트")):
                score += 3

        if any(token in {"mcp", "tool", "도구", "브라우저", "browser"} for token in query):
            if any(word in haystack for word in ("mcp", "tool", "browser", "도구")):
                score += 3

        return round(score, 2)

    def render_policy_prompt(self) -> str:
        """Render policy prompt.

        Returns:
            str: The str result.

        """
        return (
            "## Autonomous Capability Policy\n"
            "- Prefer autonomous use for trusted safe/low/medium/"
            "high capabilities when they directly advance the task.\n"
            "- Use MCP tools only after config audit has accepted the server and tool annotations are mapped to risk.\n"
            "- Auto-activate relevant local or verified skills; do not inject irrelevant skills into context.\n"
            "- Ask approval before critical desktop/computer control, irreversible operations, deployment,"
            "deletion, payment, or protected-path access.\n"
            "- Deny unauthenticated remote MCP capabilities and dangerous shell patterns.\n"
        )

    def _is_trusted(self, trust_level: str) -> bool:
        return trust_level.lower() in SAFE_TRUST_LEVELS

    def _has_high_risk_intent(self, objective: str, args: Mapping[str, object] | None) -> bool:
        text = objective.lower()
        if args:
            text += " " + " ".join(str(value).lower() for value in args.values())
        return any(re.search(rf"\b{re.escape(word)}\b", text) for word in HIGH_RISK_ACTION_WORDS)


def _normalize_tokens(text: str) -> set[str]:
    tokens = cast(list[str], re.findall(r"[a-zA-Z0-9_가-힣-]{2,}", text.lower()))
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "하는",
        "있는",
        "해줘",
        "부탁",
        "사용",
        "관련",
    }
    return {token for token in tokens if token not in stopwords}


def _string_values(value: object) -> list[str]:
    items: Iterable[object]
    if isinstance(value, list):
        items = cast(list[object], value)
    elif isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
    elif isinstance(value, set):
        items = cast(set[object], value)
    else:
        return []
    return [str(item) for item in items]
