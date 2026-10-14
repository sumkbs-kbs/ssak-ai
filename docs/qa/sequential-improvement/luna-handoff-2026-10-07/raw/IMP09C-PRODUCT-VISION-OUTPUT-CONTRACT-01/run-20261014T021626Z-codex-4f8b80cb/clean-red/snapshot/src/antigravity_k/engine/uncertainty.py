"""Ssak-Ai: 불확실성 인식기 (UncertaintyEstimator).

====================================================
E-2: 에이전트가 자신의 확신도를 평가하는 메타인지 모듈.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import final

from pydantic import JsonValue

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidencelevel.

    Bases: Enum
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class UncertaintyResult:
    """Quantified uncertainty assessment for an agent output."""

    confidence: ConfidenceLevel
    uncertainties: list[str]
    should_ask_user: bool
    clarification: str  # 사용자에게 할 확인 질문


@final
class UncertaintyEstimator:
    """에이전트가 '나는 이것을 확실히 알고 있는가?'를 판단합니다.

    판단 기준:
    1. CEO 분석의 confidence 필드
    2. 사용자 요청의 모호성 수준
    3. KI/Memory에서 유사 사례 존재 여부
    4. 도구 실행 전 인자 완전성
    """

    def __init__(self):
        """Initialize the UncertaintyEstimator."""
        self._ambiguity_patterns_ko: list[str] = [
            r"잘\s*모르겠",
            r"아마",
            r"적당히",
            r"알아서",
            r"대충",
            r"그런\s*거",
            r"뭔가",
        ]
        self._ambiguity_patterns_en: list[str] = [
            r"\bmaybe\b",
            r"\bperhaps\b",
            r"\bsomething like\b",
            r"\bkind of\b",
            r"\bnot sure\b",
            r"\bwhatever\b",
        ]

    def estimate(
        self,
        user_message: str,
        ceo_analysis: Mapping[str, JsonValue],
        ki_matches: int = 0,
    ) -> UncertaintyResult:
        """사용자 요청에 대한 에이전트의 확신도를 평가합니다."""
        uncertainties: list[str] = []
        confidence_score = 1.0

        # 1. CEO 분석의 confidence
        ceo_confidence = ceo_analysis.get("confidence", "medium")
        if ceo_confidence == "low":
            confidence_score *= 0.5
            uncertainties.append("CEO 분석의 확신도가 낮습니다")
        elif ceo_confidence == "medium":
            confidence_score *= 0.8

        # 2. 요청 모호성 검사
        ambiguity = self._check_ambiguity(user_message)
        if ambiguity > 0.5:
            confidence_score *= 0.6
            uncertainties.append("사용자 요청이 모호합니다")
        elif ambiguity > 0.3:
            confidence_score *= 0.8
            uncertainties.append("사용자 요청에 일부 모호한 부분이 있습니다")

        # 3. 요청 복잡도 분석
        complexity = self._assess_complexity(user_message)
        if complexity > 0.7:
            confidence_score *= 0.7
            uncertainties.append("요청이 매우 복잡합니다")

        # 4. KI 매칭 — 유사 경험이 있으면 확신도 상승
        if ki_matches > 2:
            confidence_score = min(1.0, confidence_score * 1.2)
        elif ki_matches == 0:
            confidence_score *= 0.9
            uncertainties.append("유사한 과거 경험이 없습니다")

        # 5. 정보 부족 감지
        if self._has_missing_info(user_message):
            confidence_score *= 0.6
            uncertainties.append("필수 정보(파일 경로, 버전 등)가 누락되었을 수 있습니다")

        # 확신도 레벨 결정
        if confidence_score >= 0.7:
            level = ConfidenceLevel.HIGH
        elif confidence_score >= 0.4:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        should_ask = level == ConfidenceLevel.LOW
        clarification = self._build_clarification(uncertainties) if should_ask else ""

        return UncertaintyResult(
            confidence=level,
            uncertainties=uncertainties,
            should_ask_user=should_ask,
            clarification=clarification,
        )

    def format_prompt_injection(self, result: UncertaintyResult) -> str:
        """에이전트 프롬프트에 주입할 불확실성 컨텍스트."""
        if result.confidence is ConfidenceLevel.HIGH:
            return ""
        suffix = {
            ConfidenceLevel.LOW: "⚠️ 확신도가 낮습니다. 불확실한 부분은 사용자에게 확인하세요.",
            ConfidenceLevel.MEDIUM: "💡 일부 불확실한 부분이 있습니다. 가정을 명시하세요.",
        }[result.confidence]

        lines = ["\n<uncertainty_awareness>", f"현재 확신도: {result.confidence.value}"]
        lines.extend(f"- {uncertainty}" for uncertainty in result.uncertainties)
        lines.append(suffix)
        lines.append("</uncertainty_awareness>")
        return "\n".join(lines)

    def _check_ambiguity(self, text: str) -> float:
        """텍스트의 모호성 수준 (0.0~1.0)."""
        matches = 0
        total_patterns = len(self._ambiguity_patterns_ko) + len(self._ambiguity_patterns_en)

        for pat in self._ambiguity_patterns_ko:
            if re.search(pat, text):
                matches += 1
        for pat in self._ambiguity_patterns_en:
            if re.search(pat, text, re.IGNORECASE):
                matches += 1

        return min(1.0, matches / max(1, total_patterns) * 3)

    def _assess_complexity(self, text: str) -> float:
        """요청 복잡도 평가 (0.0~1.0)."""
        score = 0.0

        # 문장 수
        sentences = re.split(r"[.!?。\n]", text)
        if len(sentences) > 5:
            score += 0.3

        # 기술 용어 밀도
        tech_terms = re.findall(r"\b[A-Z][a-zA-Z]+(?:\.[a-zA-Z]+)*\b", text)
        if len(tech_terms) > 5:
            score += 0.2

        # 다중 작업 감지
        multi_markers = [
            "그리고",
            "또한",
            "추가로",
            "and also",
            "additionally",
            "그 후에",
        ]
        if any(m in text.lower() for m in multi_markers):
            score += 0.2

        # 길이
        if len(text) > 500:
            score += 0.2

        return min(1.0, score)

    def _has_missing_info(self, text: str) -> bool:
        """필수 정보가 누락되었는지 감지합니다."""
        # 파일/경로 관련 작업인데 구체적 경로 없음
        file_keywords = [
            "파일",
            "file",
            "수정",
            "edit",
            "생성",
            "create",
            "삭제",
            "delete",
        ]
        if any(kw in text.lower() for kw in file_keywords):
            if not re.search(r"[\w/\\]+\.\w+", text):  # 파일 경로 패턴 없음
                return True
        return False

    def _build_clarification(self, uncertainties: list[str]) -> str:
        """사용자에게 할 확인 질문을 생성합니다."""
        questions: list[str] = []

        if "모호" in str(uncertainties):
            questions.append("구체적으로 어떤 결과를 원하시나요?")
        if "필수 정보" in str(uncertainties):
            questions.append("대상 파일이나 경로를 지정해 주실 수 있나요?")
        if "복잡" in str(uncertainties):
            questions.append("가장 우선순위가 높은 부분은 어떤 것인가요?")
        if "경험" in str(uncertainties):
            questions.append("이전에 비슷한 작업을 하신 적이 있나요? 참고할 만한 예시가 있나요?")

        if not questions:
            questions.append("요청을 좀 더 구체적으로 설명해 주시겠어요?")

        return " ".join(questions[:2])
