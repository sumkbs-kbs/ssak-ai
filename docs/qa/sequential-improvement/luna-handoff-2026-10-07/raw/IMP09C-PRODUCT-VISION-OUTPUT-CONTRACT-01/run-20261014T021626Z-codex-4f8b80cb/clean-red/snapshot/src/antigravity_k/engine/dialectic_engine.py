"""
Ssak-Ai: 변증법적 추론 엔진 (DialecticEngine)
====================================================
Hegelion 아키텍처 이식 — Thesis → Antithesis → Synthesis 3단계 추론.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

logger = logging.getLogger(__name__)


class DialecticPhase(str, Enum):
    THESIS = "thesis"
    ANTITHESIS = "antithesis"
    SYNTHESIS = "synthesis"


class AutocodingPhase(str, Enum):
    PLAYER = "player"
    COACH = "coach"
    APPROVED = "approved"
    TIMEOUT = "timeout"


@dataclass
class DialecticalPrompt:
    phase: str
    prompt: str
    instructions: str
    expected_format: str

    def to_dict(self) -> dict[str, str]:
        return {
            "phase": self.phase,
            "prompt": self.prompt,
            "instructions": self.instructions,
            "expected_format": self.expected_format,
        }


@dataclass
class Contradiction:
    description: str
    evidence: str
    severity: str = "medium"


@dataclass
class ResearchProposal:
    proposal: str
    testable_prediction: str


@dataclass
class DialecticResult:
    query: str
    thesis: str = ""
    antithesis: str = ""
    synthesis: str = ""
    contradictions: list[Contradiction] = field(default_factory=list)
    research_proposals: list[ResearchProposal] = field(default_factory=list)
    council_critiques: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "thesis": self.thesis,
            "antithesis": self.antithesis,
            "synthesis": self.synthesis,
            "contradictions": [{"description": c.description, "evidence": c.evidence} for c in self.contradictions],
            "research_proposals": [
                {"proposal": r.proposal, "testable_prediction": r.testable_prediction} for r in self.research_proposals
            ],
        }


@dataclass
class AutocodingState:
    """Player-Coach 세션 상태 — Hegelion autocoding_state 이식."""

    session_id: str
    requirements: str
    session_name: str | None = None
    current_turn: int = 0
    max_turns: int = 5
    phase: str = AutocodingPhase.PLAYER.value
    turn_history: list[dict[str, object]] = field(default_factory=list)
    last_coach_feedback: str | None = None

    @classmethod
    def create(cls, requirements: str, max_turns: int = 5, session_name: str | None = None) -> "AutocodingState":
        return cls(
            session_id=str(uuid.uuid4()),
            session_name=session_name,
            requirements=requirements,
            max_turns=max_turns,
        )

    def advance_to_coach(self) -> "AutocodingState":
        if self.phase != AutocodingPhase.PLAYER.value:
            raise ValueError(f"Cannot advance to coach from phase: {self.phase}")
        return AutocodingState(
            session_id=self.session_id,
            session_name=self.session_name,
            requirements=self.requirements,
            current_turn=self.current_turn,
            max_turns=self.max_turns,
            phase=AutocodingPhase.COACH.value,
            turn_history=self.turn_history.copy(),
            last_coach_feedback=self.last_coach_feedback,
        )

    def advance_turn(self, coach_feedback: str, approved: bool) -> "AutocodingState":
        if self.phase != AutocodingPhase.COACH.value:
            raise ValueError(f"Cannot advance turn from phase: {self.phase}")
        new_turn = self.current_turn + 1
        new_history = self.turn_history.copy()
        new_history.append(
            {
                "turn": self.current_turn,
                "feedback": coach_feedback,
                "approved": approved,
            }
        )
        if approved:
            new_phase = AutocodingPhase.APPROVED.value
        elif new_turn >= self.max_turns:
            new_phase = AutocodingPhase.TIMEOUT.value
        else:
            new_phase = AutocodingPhase.PLAYER.value
        return AutocodingState(
            session_id=self.session_id,
            session_name=self.session_name,
            requirements=self.requirements,
            current_turn=new_turn,
            max_turns=self.max_turns,
            phase=new_phase,
            turn_history=new_history,
            last_coach_feedback=coach_feedback,
        )

    def is_complete(self) -> bool:
        return self.phase in {
            AutocodingPhase.APPROVED.value,
            AutocodingPhase.TIMEOUT.value,
        }

    def turns_remaining(self) -> int:
        return max(0, self.max_turns - self.current_turn)

    def summary(self) -> str:
        return f"Session: {self.session_name or self.session_id[:8]}\nTurn: {self.current_turn + 1}/{self.max_turns}\nPhase: {self.phase}"  # noqa: E501


class DialecticEngine:
    """변증법적 추론 엔진 — Hegelion PromptDrivenDialectic 네이티브 이식."""

    COUNCIL_MEMBERS: ClassVar[list[dict[str, str]]] = [
        {
            "name": "The Logician",
            "expertise": "논리적 일관성 및 형식적 추론",
            "focus": "논리적 오류, 내부 모순, 무효 추론, 누락된 전제",
        },
        {
            "name": "The Empiricist",
            "expertise": "증거, 사실, 경험적 근거",
            "focus": "사실 오류, 근거 없는 주장, 누락된 증거",
        },
        {
            "name": "The Ethicist",
            "expertise": "윤리적 함의 및 사회적 영향",
            "focus": "잠재적 피해, 윤리적 사각지대, 공정성 문제",
        },
    ]

    def create_single_shot_prompt(self, query: str, use_council: bool = False, use_search: bool = False) -> str:
        search_inst = (
            "\nBefore beginning, use available search tools to gather current information." if use_search else ""
        )
        council_inst = (
            """
For the ANTITHESIS phase, adopt three distinct critical perspectives:
- THE LOGICIAN: logical consistency  - THE EMPIRICIST: evidence and facts  - THE ETHICIST: ethical implications"""
            if use_council
            else ""
        )
        return f"""You will now perform Hegelian dialectical reasoning: THESIS → ANTITHESIS → SYNTHESIS.
{search_inst}
QUERY: {query}

**PHASE 1 - THESIS:** Generate a comprehensive initial position.
**PHASE 2 - ANTITHESIS:**{council_inst}
Critically examine your thesis. For each problem use: CONTRADICTION: [desc] / EVIDENCE: [explanation]
**PHASE 3 - SYNTHESIS:** Transcend both with novel insights.
Use RESEARCH_PROPOSAL: / TESTABLE_PREDICTION: if applicable.

Structure as: ## THESIS / ## ANTITHESIS / ## SYNTHESIS / ## CONTRADICTIONS IDENTIFIED / ## RESEARCH PROPOSALS

Begin now."""

    def create_workflow(self, query: str, use_council: bool = False, use_search: bool = False) -> dict[str, object]:
        steps: list[dict[str, object]] = []
        workflow: dict[str, object] = {
            "query": query,
            "workflow_type": "prompt_driven_dialectic",
            "steps": steps,
        }
        steps.append(
            {
                "step": 1,
                "name": "Generate Thesis",
                "prompt": self._thesis_prompt(query).to_dict(),
            }
        )
        if use_council:
            for i, m in enumerate(self.COUNCIL_MEMBERS):
                steps.append(
                    {
                        "step": 2 + i,
                        "name": f"Council: {m['name']}",
                        "prompt": self._council_prompt(query, "{{thesis}}", m).to_dict(),
                    }
                )
            syn_step = 2 + len(self.COUNCIL_MEMBERS)
        else:
            steps.append(
                {
                    "step": 2,
                    "name": "Generate Antithesis",
                    "prompt": self._antithesis_prompt(query, "{{thesis}}", use_search).to_dict(),
                }
            )
            syn_step = 3
        steps.append(
            {
                "step": syn_step,
                "name": "Generate Synthesis",
                "prompt": self._synthesis_prompt(query, "{{thesis}}", "{{antithesis}}").to_dict(),
            }
        )
        return workflow

    def parse_structured_response(self, raw_text: str, query: str) -> DialecticResult:
        result = DialecticResult(query=query)
        sections = self._split_sections(raw_text)
        result.thesis = sections.get("THESIS", "")
        result.antithesis = sections.get("ANTITHESIS", "")
        result.synthesis = sections.get("SYNTHESIS", "")
        result.contradictions = self._parse_contradictions(raw_text)
        result.research_proposals = self._parse_research_proposals(raw_text)
        return result

    def generate_player_prompt(self, state: AutocodingState) -> str:
        fb = f"\nPREVIOUS COACH FEEDBACK:\n{state.last_coach_feedback}" if state.last_coach_feedback else ""
        return f"PLAYER turn {state.current_turn + 1}/{state.max_turns}\nREQUIREMENTS:\n{state.requirements}{fb}\nImplement now."  # noqa: E501

    def generate_coach_prompt(self, state: AutocodingState, player_output: str) -> str:
        return f"COACH turn {state.current_turn + 1}/{state.max_turns} ({state.turns_remaining()} left)\nREQUIREMENTS:\n{state.requirements}\nPLAYER OUTPUT:\n{player_output}\nRespond APPROVED or FEEDBACK."  # noqa: E501

    @staticmethod
    def render_markdown(result: DialecticResult) -> str:
        lines = ["# ⚖️ 변증법적 추론 결과", "", f"**Query:** {result.query}", ""]
        if result.thesis:
            lines.extend(["## 📜 Thesis (정립)", "", result.thesis, ""])
        if result.antithesis:
            lines.extend(["## ⚔️ Antithesis (반립)", "", result.antithesis, ""])
        if result.synthesis:
            lines.extend(["## 🌟 Synthesis (종합)", "", result.synthesis, ""])
        if result.contradictions:
            lines.extend(["## ⚡ 식별된 모순점", ""])
            for i, c in enumerate(result.contradictions, 1):
                lines.append(f"{i}. **{c.description}** — {c.evidence}")
        if result.research_proposals:
            lines.extend(["", "## 🔬 연구 제안", ""])
            for i, r in enumerate(result.research_proposals, 1):
                lines.append(f"{i}. **{r.proposal}** → _{r.testable_prediction}_")
        return "\n".join(lines)

    # ─── Internal prompt builders ───────────────────────────────

    def _thesis_prompt(self, query: str) -> DialecticalPrompt:
        return DialecticalPrompt(
            phase="thesis",
            prompt=f"THESIS phase.\nQUERY: {query}\nGenerate a comprehensive initial position.",
            instructions="Well-structured thesis.",
            expected_format="text",
        )

    def _antithesis_prompt(self, query: str, thesis: str, use_search: bool) -> DialecticalPrompt:
        s = "\nUse search tools first." if use_search else ""
        return DialecticalPrompt(
            phase="antithesis",
            prompt=f"ANTITHESIS phase.\nQUERY: {query}\nTHESIS: {thesis}{s}\nCritique with CONTRADICTION:/EVIDENCE:.",
            instructions="Rigorous critique.",
            expected_format="text with markers",
        )

    def _council_prompt(self, query: str, thesis: str, member: dict[str, str]) -> DialecticalPrompt:
        return DialecticalPrompt(
            phase=f"council_{member['name'].lower().replace(' ', '_')}",
            prompt=f"You are {member['name']}.\nQUERY: {query}\nTHESIS: {thesis}\nFocus: {member['focus']}",
            instructions=f"Critique as {member['name']}.",
            expected_format="text with markers",
        )

    def _synthesis_prompt(self, query: str, thesis: str, antithesis: str) -> DialecticalPrompt:
        return DialecticalPrompt(
            phase="synthesis",
            prompt=f"SYNTHESIS phase.\nQUERY: {query}\nTHESIS: {thesis}\nANTITHESIS: {antithesis}\nTranscend both.",
            instructions="Novel synthesis.",
            expected_format="text",
        )

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(text))
        for i, match in enumerate(matches):
            heading = match.group(1).strip().upper()
            for key in ("THESIS", "ANTITHESIS", "SYNTHESIS"):
                if heading.strip() == key:
                    heading = key
                    break
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections[heading] = text[start:end].strip()
        return sections

    @staticmethod
    def _parse_contradictions(text: str) -> list[Contradiction]:
        pattern = re.compile(
            r"CONTRADICTION:\s*(.+?)(?:\n|$)\s*EVIDENCE:\s*(.+?)(?=\nCONTRADICTION:|\n##|\Z)",
            re.DOTALL,
        )
        return [
            Contradiction(description=m.group(1).strip(), evidence=m.group(2).strip()) for m in pattern.finditer(text)
        ]

    @staticmethod
    def _parse_research_proposals(text: str) -> list[ResearchProposal]:
        pattern = re.compile(
            r"RESEARCH_PROPOSAL:\s*(.+?)(?:\n|$)\s*TESTABLE_PREDICTION:\s*(.+?)(?=\nRESEARCH_PROPOSAL:|\n##|\Z)",
            re.DOTALL,
        )
        return [
            ResearchProposal(proposal=m.group(1).strip(), testable_prediction=m.group(2).strip())
            for m in pattern.finditer(text)
        ]
