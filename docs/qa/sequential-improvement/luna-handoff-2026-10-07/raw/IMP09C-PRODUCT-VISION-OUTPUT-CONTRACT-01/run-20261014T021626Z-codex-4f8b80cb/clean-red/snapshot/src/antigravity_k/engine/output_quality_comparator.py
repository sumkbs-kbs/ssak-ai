"""Ssak-Ai: Output Quality Comparator.

=========================================
동일 질문에 대한 참조 출력과 실제 출력의 품질을 다차원으로 비교합니다.

비교 차원:
  1. 구조: heading/list/table/code block 비율
  2. 정보 밀도: 고유 개념 비율, 반복 패턴
  3. 언어 순수성: CJK 오염, 내부 추론 유출
  4. 한국어 가독성: 띄어쓰기, 문장 길이
  5. 코드 정확성: 구문 검증

사용법:
    comparator = OutputQualityComparator()
    result = comparator.compare(
        question="React와 Vue를 비교해줘",
        reference_output="...",   # 참조 출력 (Codex/Claude 수준)
        actual_output="...",      # Ssak-Ai 실제 출력
    )
    print(result.to_markdown())
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DimensionScore:
    """개별 비교 차원의 점수."""

    name: str
    reference_score: float  # 0.0 ~ 1.0
    actual_score: float  # 0.0 ~ 1.0
    delta: float = 0.0  # actual - reference (양수면 개선)
    notes: str = ""

    def __post_init__(self):
        """Post Init."""
        self.delta = round(self.actual_score - self.reference_score, 3)


@dataclass
class ComparisonResult:
    """비교 결과 종합."""

    question: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    reference_grade: str = ""
    actual_grade: str = ""
    winner: str = ""  # "reference", "actual", "tie"
    summary: str = ""

    @property
    def overall_delta(self) -> float:
        """Overall Delta.

        Returns:
            float: The float result.

        """
        if not self.dimensions:
            return 0.0
        return sum(d.delta for d in self.dimensions) / len(self.dimensions)

    def to_markdown(self) -> str:
        """To Markdown.

        Returns:
            str: The str result.

        """
        lines = [
            "## 📊 Output Quality Comparison",
            f"**Question**: {self.question[:80]}",
            "",
            "| 차원 | 참조 | 실제 | Δ | 비고 |",
            "|------|------|------|---|------|",
        ]
        for d in self.dimensions:
            delta_str = f"+{d.delta:.2f}" if d.delta >= 0 else f"{d.delta:.2f}"
            icon = "✅" if d.delta >= 0 else "⚠️"
            lines.append(
                f"| {d.name} | {d.reference_score:.2f} | {d.actual_score:.2f} | {icon} {delta_str} | {d.notes} |",
            )
        lines.extend(
            [
                "",
                f"**참조 등급**: {self.reference_grade}  |  **실제 등급**: {self.actual_grade}",
                f"**승자**: {'🏆 실제 출력' if self.winner == 'actual' else '📋 참조 출력' if self.winner == 'reference' else '🤝 동점'}",  # noqa: E501
                f"**종합 Δ**: {self.overall_delta:+.3f}",
                "",
                f"> {self.summary}",
            ],
        )
        return "\n".join(lines)


class OutputQualityComparator:
    """출력 품질 비교 엔진."""

    def compare(
        self,
        question: str,
        reference_output: str,
        actual_output: str,
    ) -> ComparisonResult:
        """두 출력을 다차원으로 비교합니다."""
        result = ComparisonResult(question=question)

        # 1. 구조 밀도
        ref_struct = self._structure_score(reference_output)
        act_struct = self._structure_score(actual_output)
        result.dimensions.append(
            DimensionScore("구조 밀도", ref_struct, act_struct, notes="heading/list/table/code"),
        )

        # 2. 정보 밀도
        ref_info = self._information_density(reference_output)
        act_info = self._information_density(actual_output)
        result.dimensions.append(
            DimensionScore("정보 밀도", ref_info, act_info, notes="고유 개념 비율"),
        )

        # 3. 언어 순수성
        ref_purity = self._language_purity(reference_output)
        act_purity = self._language_purity(actual_output)
        result.dimensions.append(
            DimensionScore("언어 순수성", ref_purity, act_purity, notes="CJK/내부추론 유출"),
        )

        # 4. 한국어 가독성
        ref_read = self._korean_readability(reference_output)
        act_read = self._korean_readability(actual_output)
        result.dimensions.append(
            DimensionScore("한국어 가독성", ref_read, act_read, notes="띄어쓰기/문장 길이"),
        )

        # 5. 코드 정확성
        ref_code = self._code_accuracy(reference_output)
        act_code = self._code_accuracy(actual_output)
        result.dimensions.append(
            DimensionScore("코드 정확성", ref_code, act_code, notes="구문 검증"),
        )

        # 등급 산정
        ref_avg = sum(d.reference_score for d in result.dimensions) / len(result.dimensions)
        act_avg = sum(d.actual_score for d in result.dimensions) / len(result.dimensions)
        result.reference_grade = self._grade(ref_avg)
        result.actual_grade = self._grade(act_avg)

        if act_avg > ref_avg + 0.03:
            result.winner = "actual"
            result.summary = "실제 출력이 참조 출력보다 품질이 높습니다."
        elif ref_avg > act_avg + 0.03:
            result.winner = "reference"
            result.summary = "참조 출력이 더 높은 품질을 보였습니다. 개선이 필요합니다."
        else:
            result.winner = "tie"
            result.summary = "두 출력의 품질이 유사합니다."

        return result

    def _structure_score(self, text: str) -> float:
        """구조 요소 밀도 점수."""
        if not text or len(text) < 50:
            return 0.5
        headings = len(re.findall(r"^#{1,3}\s", text, re.MULTILINE))
        lists = len(re.findall(r"^\s*[-*]\s", text, re.MULTILINE))
        code_blocks = len(re.findall(r"```", text)) // 2
        tables = len(re.findall(r"^\s*\|.+\|.+\|\s*$", text, re.MULTILINE))
        total = headings + lists + code_blocks + tables
        # chars_per_structure
        ratio = total / (len(text) / 200)
        return min(1.0, ratio)

    def _information_density(self, text: str) -> float:
        """정보 밀도 점수 (어휘 다양성 기반)."""
        prose = re.sub(r"```(?:\w+)?\s*.*?```", "", text, flags=re.DOTALL)
        words = re.findall(r"[가-힣a-zA-Z]{2,}", prose.lower())
        if len(words) < 10:
            return 0.5
        unique = set(words)
        return min(1.0, len(unique) / len(words) * 1.5)

    def _language_purity(self, text: str) -> float:
        """언어 순수성 점수."""
        score = 1.0
        cjk = len(re.findall(r"[\u4e00-\u9fff]{3,}", text))
        if cjk > 0:
            score -= min(0.5, cjk * 0.1)
        think_blocks = len(re.findall(r"<(?:think|thought)>", text, re.IGNORECASE))
        if think_blocks > 0:
            score -= 0.3
        internal_tags = len(re.findall(r"%%THINK_|<scratch_pad>|<algorithm>", text))
        if internal_tags > 0:
            score -= 0.2
        return max(0.0, score)

    def _korean_readability(self, text: str) -> float:
        """한국어 가독성 점수."""
        korean_lines = [line for line in text.split("\n") if re.search(r"[가-힣]", line)]
        if not korean_lines:
            return 0.8

        score = 1.0
        # 과도하게 긴 문장 (200자 이상)
        long_sentences = sum(1 for line in korean_lines if len(line.strip()) > 200)
        if long_sentences > len(korean_lines) * 0.3:
            score -= 0.2

        # 띄어쓰기 밀도 (한국어 문장에서 공백 비율)
        total_chars = sum(len(line) for line in korean_lines)
        spaces = sum(line.count(" ") for line in korean_lines)
        if total_chars > 0:
            space_ratio = spaces / total_chars
            if space_ratio < 0.1:  # 띄어쓰기 부족
                score -= 0.15

        return max(0.0, score)

    def _code_accuracy(self, text: str) -> float:
        """코드 블록의 구문 정확성."""
        code_blocks: list[str] = re.findall(
            r"```(?:python)?\s*\n(.*?)```",
            text,
            re.DOTALL,
        )
        if not code_blocks:
            return 1.0

        valid = 0
        for block in code_blocks:
            try:
                _ = compile(block.strip(), "<test>", "exec")
                valid += 1
            except SyntaxError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
            except Exception:
                logger.exception("Unhandled exception")
                valid += 1  # 비-Python 코드는 통과로 간주

        return valid / len(code_blocks) if code_blocks else 1.0

    def _grade(self, score: float) -> str:
        if score >= 0.85:
            return "A (Excellent)"
        if score >= 0.7:
            return "B (Good)"
        if score >= 0.5:
            return "C (Acceptable)"
        if score >= 0.3:
            return "D (Below Standard)"
        return "F (Fail)"
