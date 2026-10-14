"""Ssak-Ai: Self-Improvement Feedback Loop.

===============================================
매 턴의 QualityGate 점수를 누적 기록하고, 반복적으로 낮은 점수를 받는
패턴에 대해 프롬프트를 자동 보강하는 자기 개선 시스템.

핵심 기능:
  1. 턴별 QualityGate 점수 누적 기록
  2. 반복 실패 패턴 자동 감지 (비교 요청, 코드 전용, 언어 오염)
  3. 패턴별 프롬프트 보강 주입
  4. /self-improvement report 명령으로 개선 추이 확인
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TypedDict, cast

logger = logging.getLogger("antigravity_k.engine.self_improvement")


class TurnRecordPayload(TypedDict):
    timestamp: float
    user_request: str
    grade: str
    score: float
    issues: list[str]
    retry_count: int


@dataclass
class TurnRecord:
    """단일 턴의 품질 기록."""

    timestamp: float
    user_request: str
    grade: str  # A, B, C, D, F
    score: float
    issues: list[str]
    retry_count: int = 0


@dataclass
class PatternInsight:
    """반복 패턴 분석 결과."""

    pattern_name: str
    occurrence_count: int
    avg_score: float
    common_issues: list[str]
    recommended_prompt: str


class SelfImprovementLoop:
    """자기 개선 피드백 루프."""

    # 패턴별 프롬프트 보강 템플릿
    _REINFORCEMENT_PROMPTS: dict[str, str] = {
        "비교표": (
            "⚠️ [품질 가이드] 비교 요청에는 반드시 Markdown 비교표(| 항목 | A | B |)를 포함하세요. "
            "비교표 없는 비교 응답은 감점됩니다."
        ),
        "중국어": (
            "⚠️ [언어 순수성] 한국어 응답에 중국어/일본어를 혼입하지 마세요. "
            "모든 외래 기술 용어는 영어 원문을 사용하고, 설명은 순수 한국어로 작성하세요."
        ),
        "일본어": ("⚠️ [언어 순수성] 일본어 혼입이 감지됩니다. 한국어와 영어만 사용하세요."),
        "구조": (
            "⚠️ [구조 가이드] 응답이 800자를 넘는 경우 반드시 heading(##), "
            "목록(-), 코드 블록(```)을 사용하여 구조화하세요."
        ),
        "반복": (
            "⚠️ [중복 방지] 같은 내용을 반복하지 마세요. "
            "핵심 포인트를 한 번만 명확히 설명하고, 각 섹션은 새로운 정보를 제공해야 합니다."
        ),
        "밀도": ("⚠️ [정보 밀도] 장황한 설명 대신 핵심 개념에 집중하세요. 구체적인 예시, 수치, 코드를 통해 설명하세요."),
    }

    def __init__(
        self,
        data_dir: str | None = None,
        window_size: int = 50,
        pattern_threshold: int = 3,
    ):
        """Initialize the SelfImprovementLoop.

        Args:
            data_dir (str | None): str | None data dir.
            window_size (int): int window size.
            pattern_threshold (int): int pattern threshold.

        """
        self._data_dir: str = data_dir or os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "data",
        )
        self._records: list[TurnRecord] = []
        self._window_size: int = window_size
        self._pattern_threshold: int = pattern_threshold
        self._issue_counter: dict[str, int] = defaultdict(int)
        self._load_history()

    def record_turn(
        self,
        user_request: str,
        grade: str,
        score: float,
        issues: list[str],
        retry_count: int = 0,
    ) -> None:
        """턴 결과를 기록합니다."""
        record = TurnRecord(
            timestamp=time.time(),
            user_request=user_request[:200],
            grade=grade,
            score=score,
            issues=issues,
            retry_count=retry_count,
        )
        self._records.append(record)

        for issue in issues:
            for pattern in self._REINFORCEMENT_PROMPTS:
                if pattern in issue:
                    self._issue_counter[pattern] += 1

        # 윈도우 초과 시 오래된 기록 제거
        if len(self._records) > self._window_size * 2:
            self._records = self._records[-self._window_size :]

        self._save_history()

    def get_reinforcement_prompt(self) -> str:
        """현재 반복 실패 패턴에 대한 보강 프롬프트를 생성합니다."""
        prompts: list[str] = []
        for pattern, count in self._issue_counter.items():
            if count >= self._pattern_threshold:
                if pattern in self._REINFORCEMENT_PROMPTS:
                    prompts.append(self._REINFORCEMENT_PROMPTS[pattern])

        return "\n".join(prompts) if prompts else ""

    def get_insights(self) -> list[PatternInsight]:
        """반복 패턴 분석 결과를 반환합니다."""
        insights: list[PatternInsight] = []
        for pattern, count in sorted(self._issue_counter.items(), key=lambda x: x[1], reverse=True):
            if count < 2:
                continue
            # 해당 패턴이 포함된 턴의 평균 점수 계산
            matching = [r for r in self._records if any(pattern in issue for issue in r.issues)]
            avg_score = sum(r.score for r in matching) / len(matching) if matching else 0.0
            insights.append(
                PatternInsight(
                    pattern_name=pattern,
                    occurrence_count=count,
                    avg_score=round(avg_score, 3),
                    common_issues=[pattern],
                    recommended_prompt=self._REINFORCEMENT_PROMPTS.get(pattern, ""),
                ),
            )
        return insights

    def generate_report(self) -> str:
        """개선 추이 보고서를 생성합니다."""
        if not self._records:
            return "## 📈 Self-Improvement Report\n\n기록된 턴이 없습니다."

        recent = self._records[-self._window_size :]
        total = len(recent)
        avg_score = sum(r.score for r in recent) / total
        grade_dist: defaultdict[str, int] = defaultdict(int)
        for r in recent:
            grade_dist[r.grade] += 1

        retry_total = sum(r.retry_count for r in recent)
        insights = self.get_insights()

        lines = [
            "## 📈 Self-Improvement Report",
            "",
            f"**분석 기간**: 최근 {total}턴",
            f"**평균 점수**: {avg_score:.3f}",
            f"**총 재시도 횟수**: {retry_total}",
            "",
            "### 등급 분포",
            "| 등급 | 횟수 | 비율 |",
            "|------|------|------|",
        ]
        for grade in ["excellent", "good", "acceptable", "retry", "fail"]:
            count = grade_dist.get(grade, 0)
            pct = count / total * 100 if total > 0 else 0
            lines.append(f"| {grade} | {count} | {pct:.1f}% |")

        if insights:
            lines.extend(
                [
                    "",
                    "### 반복 패턴 분석",
                    "| 패턴 | 발생 횟수 | 평균 점수 | 권장 조치 |",
                    "|------|----------|----------|----------|",
                ],
            )
            for insight in insights:
                lines.append(
                    f"| {insight.pattern_name} | {insight.occurrence_count} | "
                    + f"{insight.avg_score:.3f} | {insight.recommended_prompt[:50]}... |",
                )

        reinforcement = self.get_reinforcement_prompt()
        if reinforcement:
            lines.extend(
                [
                    "",
                    "### 현재 활성 보강 프롬프트",
                    "```",
                    reinforcement,
                    "```",
                ],
            )

        return "\n".join(lines)

    def _save_history(self) -> None:
        """기록을 파일에 저장합니다."""
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            filepath = os.path.join(self._data_dir, "self_improvement_history.json")
            data = {
                "records": [
                    {
                        "timestamp": r.timestamp,
                        "user_request": r.user_request,
                        "grade": r.grade,
                        "score": r.score,
                        "issues": r.issues,
                        "retry_count": r.retry_count,
                    }
                    for r in self._records[-self._window_size :]
                ],
                "issue_counter": dict(self._issue_counter),
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to save improvement history: %s", e)

    def _load_history(self) -> None:
        """기록을 파일에서 복원합니다."""
        try:
            filepath = os.path.join(self._data_dir, "self_improvement_history.json")
            if os.path.exists(filepath):
                with open(filepath, encoding="utf-8") as f:
                    data = cast(object, json.load(f))
                if not isinstance(data, dict):
                    return
                payload = cast(dict[str, object], cast(object, data))
                raw_records = payload.get("records", [])
                if isinstance(raw_records, list):
                    records = cast(list[object], cast(object, raw_records))
                    self._records = [
                        TurnRecord(**cast(TurnRecordPayload, cast(object, record)))
                        for record in records
                        if isinstance(record, dict)
                    ]
                raw_counter = payload.get("issue_counter", {})
                if isinstance(raw_counter, dict):
                    counter = cast(dict[str, int], cast(object, raw_counter))
                    self._issue_counter = defaultdict(int, counter)
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to load improvement history: %s", e)
