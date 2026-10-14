"""
Ssak-Ai: Decision Anchor System
=======================================
Anthropic 컨텍스트 엔지니어링 핵심 원칙 이식:
"핵심 결정사항을 컨텍스트 상단에 고정하여 AI 망각 방지"

AI가 긴 작업에서 초기 합의를 망각하는 핵심 원인:
결정 사항이 대화 중간에 묻혀서 후속 턴에서 컨텍스트 밖으로 밀려남.

해결: 결정 앵커를 시스템 프롬프트 바로 뒤에 항상 주입하여,
대화가 아무리 길어져도 핵심 합의를 보존합니다.
"""

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import ClassVar, TypeAlias

logger = logging.getLogger("antigravity_k.engine.decision_anchor")
Message: TypeAlias = dict[str, str]

# ─── 결정 사항 감지 패턴 ───
_DECISION_PATTERNS = [
    # 한국어 합의/결정 패턴
    re.compile(
        r"(.{5,80})\s*(?:로|으로)\s*(?:하자|하겠습니다|합시다|결정|확정|합의)",
        re.UNICODE,
    ),
    re.compile(
        r"(.{5,80})\s*(?:방식|방법|구조|스택|프레임워크)(?:으?로)\s*(?:가자|가겠습니다|진행)",
        re.UNICODE,
    ),
    re.compile(r"(?:결정|확정|합의)[:\s]+(.{5,120})", re.UNICODE),
    re.compile(r"(?:승인|approve|agreed|decided)[:\s]+(.{5,120})", re.IGNORECASE),
    # 영어 결정 패턴
    re.compile(r"(?:let'?s\s+(?:go with|use|proceed with))\s+(.{5,80})", re.IGNORECASE),
    re.compile(r"(?:we(?:'ll| will)\s+(?:use|go with|proceed with))\s+(.{5,80})", re.IGNORECASE),
]


@dataclass
class Anchor:
    """단일 결정 앵커."""

    anchor_id: str
    decision: str
    category: str  # architecture, tooling, convention, scope, general
    priority: int  # 1-10, 높을수록 중요
    created_at: float
    source: str = ""  # 추출 원본 (user/auto)

    def to_display(self) -> str:
        return f"🔒 [{self.category}] {self.decision}"


class DecisionAnchor:
    """핵심 결정사항을 컨텍스트 상단에 고정하는 앵커 시스템.

    Anthropic 컨텍스트 엔지니어링 핵심 원칙:
    - 결정 사항은 절대 컨텍스트 밖으로 밀려나면 안 됨
    - 시스템 프롬프트 바로 뒤에 항상 주입
    - 대화가 길어져도 핵심 합의를 보존

    사용 시나리오:
    - "이 프로젝트는 Python 3.12 + FastAPI로 진행하기로 함"
    - "DB 스키마는 A 방식으로 확정"
    - "API 응답 형식은 JSON으로 통일"
    """

    MAX_ANCHORS: ClassVar[int] = 10  # 앵커도 토큰 예산 소모 → 제한

    def __init__(self) -> None:
        self._anchors: list[Anchor] = []

    @property
    def anchors(self) -> list[Anchor]:
        return list(self._anchors)

    @property
    def count(self) -> int:
        return len(self._anchors)

    def add(
        self,
        decision: str,
        category: str = "general",
        priority: int = 5,
        source: str = "user",
    ) -> str:
        """결정 사항을 앵커에 추가합니다.

        Returns:
            생성된 앵커 ID
        """
        if len(self._anchors) >= self.MAX_ANCHORS:
            # 우선순위가 가장 낮은 앵커를 제거
            self._anchors.sort(key=lambda a: a.priority)
            evicted = self._anchors.pop(0)
            logger.info(
                "[DecisionAnchor] 앵커 한도 도달, 최저 우선순위 제거: %s",
                evicted.decision[:50],
            )

        anchor_id = uuid.uuid4().hex[:8]
        anchor = Anchor(
            anchor_id=anchor_id,
            decision=decision.strip(),
            category=category,
            priority=max(1, min(10, priority)),
            created_at=time.time(),
            source=source,
        )
        self._anchors.append(anchor)
        logger.info("[DecisionAnchor] 앵커 추가: [%s] %s", category, decision[:60])
        return anchor_id

    def remove(self, anchor_id: str) -> bool:
        """앵커를 ID로 제거합니다."""
        for i, a in enumerate(self._anchors):
            if a.anchor_id == anchor_id:
                removed = self._anchors.pop(i)
                logger.info("[DecisionAnchor] 앵커 제거: %s", removed.decision[:50])
                return True
        return False

    def clear(self) -> None:
        """모든 앵커를 초기화합니다."""
        self._anchors.clear()

    def inject_into_messages(self, messages: list[Message]) -> list[Message]:
        """시스템 프롬프트 바로 뒤에 결정 앵커 블록을 주입합니다.

        Anthropic 원칙: 핵심 결정은 항상 컨텍스트 최상단에 배치.
        """
        if not self._anchors:
            return messages

        sorted_anchors = sorted(self._anchors, key=lambda a: a.priority, reverse=True)

        lines = ["[DECISION ANCHORS — 현재 세션의 핵심 합의 사항]"]
        for a in sorted_anchors:
            lines.append(f"  {a.to_display()}")
        lines.append("위 결정 사항을 항상 준수하며, 이에 반하는 행동은 하지 마세요.")
        lines.append("[END ANCHORS]")

        anchor_msg = {"role": "system", "content": "\n".join(lines)}

        result: list[Message] = []
        inserted = False
        for msg in messages:
            result.append(msg)
            if msg.get("role") == "system" and not inserted:
                result.append(anchor_msg)
                inserted = True

        if not inserted:
            result.insert(0, anchor_msg)

        return result

    def auto_extract(self, user_msg: str, assistant_msg: str) -> dict[str, str] | None:
        """대화에서 결정 사항을 자동 감지하여 앵커 후보를 반환합니다.

        정규식 기반 패턴 매칭 (Option A: 가볍고 LLM 호출 없음).

        Returns:
            감지된 경우 {"decision": str, "category": str}, 없으면 None
        """
        combined = f"{user_msg}\n{assistant_msg}"

        for pattern in _DECISION_PATTERNS:
            match = pattern.search(combined)
            if match:
                candidate = match.group(1).strip()
                # 너무 짧거나 너무 긴 후보는 무시
                if len(candidate) < 5 or len(candidate) > 150:
                    continue

                # 이미 동일한 앵커가 있으면 무시
                if any(
                    candidate.lower() in a.decision.lower() or a.decision.lower() in candidate.lower()
                    for a in self._anchors
                ):
                    continue

                category = self._classify_category(candidate)
                return {"decision": candidate, "category": category}

        return None

    @staticmethod
    def _classify_category(text: str) -> str:
        """결정 사항의 카테고리를 휴리스틱으로 분류합니다."""
        text_lower = text.lower()

        if any(
            kw in text_lower
            for kw in [
                "아키텍처",
                "구조",
                "패턴",
                "architecture",
                "structure",
                "design",
                "설계",
            ]
        ):
            return "architecture"

        if any(
            kw in text_lower
            for kw in [
                "프레임워크",
                "라이브러리",
                "도구",
                "스택",
                "framework",
                "library",
                "tool",
                "stack",
                "python",
                "typescript",
            ]
        ):
            return "tooling"

        if any(
            kw in text_lower
            for kw in [
                "규칙",
                "컨벤션",
                "형식",
                "스타일",
                "convention",
                "format",
                "naming",
                "style",
            ]
        ):
            return "convention"

        if any(
            kw in text_lower
            for kw in [
                "범위",
                "스코프",
                "scope",
                "mvp",
                "기능",
                "feature",
            ]
        ):
            return "scope"

        return "general"

    def render_status(self) -> str:
        """현재 앵커 상태를 사람이 읽을 수 있는 문자열로 반환합니다."""
        if not self._anchors:
            return "🔓 활성 결정 앵커 없음"

        lines = [f"🔒 활성 결정 앵커: {len(self._anchors)}개"]
        for a in sorted(self._anchors, key=lambda x: x.priority, reverse=True):
            lines.append(f"  {a.to_display()}")
        return "\n".join(lines)

    def get_stats(self) -> dict[str, object]:
        """앵커 시스템 통계를 반환합니다."""
        categories: dict[str, int] = {}
        for a in self._anchors:
            categories[a.category] = categories.get(a.category, 0) + 1
        return {
            "total_anchors": len(self._anchors),
            "max_anchors": self.MAX_ANCHORS,
            "categories": categories,
            "source_breakdown": {
                "user": sum(1 for a in self._anchors if a.source == "user"),
                "auto": sum(1 for a in self._anchors if a.source == "auto"),
            },
        }
