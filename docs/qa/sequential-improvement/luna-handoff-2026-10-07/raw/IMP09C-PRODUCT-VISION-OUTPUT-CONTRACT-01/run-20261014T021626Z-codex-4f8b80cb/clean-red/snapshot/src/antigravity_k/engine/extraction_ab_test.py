#!/usr/bin/env python3
"""
Ssak-Ai: 데이터 추출 A/B 테스트 프레임워크
==================================================
두 가지 버전의 데이터 추출 로직을 동일한 입력에 대해 실행하고
그 결과를 정량적으로 비교/평가합니다.

사용 예:
    runner = ExtractionABTestRunner()
    case = ExtractionABTestCase(
        name="한화에어로스페이스 주가",
        query="한화에어로스페이스 주가",
        input_texts=[SNIPPET_HANWHA],
        expected=ExtractionResult(stock_prices=[...]),
    )
    report = runner.run_suite([case])
    print(report.to_markdown())
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from antigravity_k.engine.data_extractor import (
    DataExtractor,
    ExtractedExchangeRate,
    ExtractedStockPrice,
    ExtractedWeather,
    ExtractionResult,
)

logger = logging.getLogger("extraction_ab_test")


# ─── 데이터 모델 ──────────────────────────────────────────────────


@dataclass
class ExtractionABTestCase:
    """A/B 테스트 케이스 하나: 입력 + 기대 출력."""

    name: str
    query: str
    input_texts: list[str]
    expected: ExtractionResult
    tags: list[str] = field(default_factory=list)  # e.g. ["stock", "korean", "manwon"]
    difficulty: str = "normal"  # easy / normal / hard


@dataclass
class FieldScore:
    """개별 필드 추출 정확도 점수."""

    field_name: str  # e.g. "close_price", "ticker", "temperature"
    expected_value: object | None = None
    actual_value: object | None = None
    match: bool = False  # 완전 일치
    partial: bool = False  # 부분 일치 (null vs value 등)


@dataclass
class ExtractionComparison:
    """하나의 테스트 케이스에 대한 A/B 비교 결과."""

    case_name: str
    duration_ms: float = 0.0  # 실행 시간 (ms)
    field_scores: list[FieldScore] = field(default_factory=list)
    fields_matched: int = 0
    fields_total: int = 0
    accuracy_pct: float = 0.0  # 0~100%
    has_expected: bool = True  # 기대값이 있는 경우만 True
    has_data: bool = False  # 실제 추출 데이터가 있는지

    @property
    def summary(self) -> str:
        """한 줄 요약."""
        if not self.has_expected:
            return f"[{self.case_name}] 기대값 없음 (스킵)"
        return (
            f"[{self.case_name}] 정확도 {self.accuracy_pct:.1f}% "
            f"({self.fields_matched}/{self.fields_total}) "
            f"[{self.duration_ms:.0f}ms]"
        )


@dataclass
class ABTestReport:
    """전체 A/B 테스트 스위트 결과 보고서."""

    timestamp: str = ""
    version_label: str = "current"
    total_cases: int = 0
    comparisons: list[ExtractionComparison] = field(default_factory=list)
    total_fields_matched: int = 0
    total_fields: int = 0
    avg_accuracy: float = 0.0  # 0~100%
    avg_duration_ms: float = 0.0
    by_tag: dict[str, float] = field(default_factory=dict)  # tag -> accuracy

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def passed(self) -> int:
        """정확도 100%인 테스트 케이스 수."""
        return sum(1 for c in self.comparisons if c.has_expected and c.accuracy_pct == 100.0)

    @property
    def failed(self) -> int:
        """정확도 < 100%인 테스트 케이스 수."""
        return sum(1 for c in self.comparisons if c.has_expected and c.accuracy_pct < 100.0)

    def to_dict(self) -> dict[str, object]:
        """JSON 직렬화용 dict 변환."""
        return {
            "timestamp": self.timestamp,
            "version_label": self.version_label,
            "total_cases": self.total_cases,
            "avg_accuracy": self.avg_accuracy,
            "avg_duration_ms": self.avg_duration_ms,
            "passed": self.passed,
            "failed": self.failed,
            "total_fields_matched": self.total_fields_matched,
            "total_fields": self.total_fields,
            "by_tag": self.by_tag,
            "comparisons": [
                {
                    "case_name": c.case_name,
                    "duration_ms": c.duration_ms,
                    "accuracy_pct": c.accuracy_pct,
                    "fields_matched": c.fields_matched,
                    "fields_total": c.fields_total,
                    "has_data": c.has_data,
                    "has_expected": c.has_expected,
                    "summary": c.summary,
                    "field_scores": [
                        {
                            "field_name": f.field_name,
                            "expected": _serialize_value(f.expected_value),
                            "actual": _serialize_value(f.actual_value),
                            "match": f.match,
                        }
                        for f in c.field_scores
                    ],
                }
                for c in self.comparisons
            ],
        }

    @staticmethod
    def _safe_pct(numerator: int, denominator: int) -> float:
        """안전한 백분율 계산."""
        return round(numerator / max(1, denominator) * 100, 1)

    def to_markdown(self) -> str:
        """마크다운 보고서 생성."""
        lines = [
            "# 📊 데이터 추출 A/B 테스트 보고서",
            "",
            f"- **버전:** {self.version_label}",
            f"- **실행 시간:** {self.timestamp}",
            f"- **총 테스트:** {self.total_cases}개",
            f"- **통과:** {self.passed}개 | **실패:** {self.failed}개",
            f"- **평균 정확도:** {self.avg_accuracy:.1f}%",
            f"- **평균 지연 시간:** {self.avg_duration_ms:.0f}ms",
            f"- **필드 매칭:** {self.total_fields_matched}/{self.total_fields} ({self._safe_pct(self.total_fields_matched, self.total_fields):.1f}%)",
            "",
        ]

        # 태그별 정확도
        if self.by_tag:
            lines.append("### 태그별 정확도")
            lines.append("")
            lines.append("| 태그 | 정확도 | 케이스 수 |")
            lines.append("| :--- | :---: | :---: |")
            for tag, acc in sorted(self.by_tag.items()):
                tag_count = sum(1 for c in self.comparisons if tag in c.case_name)
                lines.append(f"| {tag} | {acc:.1f}% | {tag_count}개 |")
            lines.append("")

        # 상세 비교
        lines.append("### 상세 결과")
        lines.append("")
        lines.append("| 케이스 | 정확도 | 매칭 | 시간 | 상태 |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        for c in self.comparisons:
            if not c.has_expected:
                status = "⏭️"
            elif c.accuracy_pct == 100.0:
                status = "✅"
            elif c.accuracy_pct >= 80.0:
                status = "🟡"
            elif c.accuracy_pct >= 50.0:
                status = "🟠"
            else:
                status = "❌"
            lines.append(
                f"| {c.case_name} | {c.accuracy_pct:.1f}% | "
                + f"{c.fields_matched}/{c.fields_total} | {c.duration_ms:.0f}ms | {status} |"
            )

        # 실패 케이스 상세
        failed_cases = [c for c in self.comparisons if c.has_expected and c.accuracy_pct < 100.0]
        if failed_cases:
            lines.append("")
            lines.append("### ❌ 실패 케이스 상세")
            lines.append("")
            for c in failed_cases:
                lines.append(f"#### {c.case_name} ({c.accuracy_pct:.1f}%)")
                lines.append("")
                lines.append("| 필드 | 기대값 | 실제값 | 일치 |")
                lines.append("| :--- | :--- | :--- | :---: |")
                for fs in c.field_scores:
                    exp = _serialize_value(fs.expected_value)
                    act = _serialize_value(fs.actual_value)
                    icon = "✅" if fs.match else "❌"
                    lines.append(f"| {fs.field_name} | {exp} | {act} | {icon} |")
                lines.append("")

        return "\n".join(lines)


# ─── 헬퍼 ─────────────────────────────────────────────────────────


def _serialize_value(val: object | None) -> str:
    """값을 문자열로 직렬화 (None 처리)."""
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.2f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _compare_fields(
    expected: object | None,
    actual: object | None,
    field_name: str,
) -> FieldScore | None:
    """하나의 필드값을 비교하여 FieldScore 반환.

    양쪽 모두 None이면 None 반환 (점수 집계에서 제외).

    Returns:
        FieldScore (비교 가능한 필드) 또는 None (양쪽 None으로 비교 불필요)
    """
    if expected is None and actual is None:
        # 양쪽 모두 None: 비교 대상 아님 → 점수 집계에서 제외
        return None
    if expected is not None and actual is not None and expected == actual:
        # 정확히 일치
        return FieldScore(
            field_name=field_name,
            expected_value=expected,
            actual_value=actual,
            match=True,
            partial=False,
        )
    # 불일치 또는 한쪽만 None
    is_partial = (expected is not None and actual is None) or (expected is None and actual is not None)
    return FieldScore(
        field_name=field_name,
        expected_value=expected,
        actual_value=actual,
        match=False,
        partial=is_partial,
    )


# ─── 비교 로직 ────────────────────────────────────────────────────


def _compare_extraction_results(
    actual: ExtractionResult,
    expected: ExtractionResult,
    case_name: str,
    duration_ms: float,
) -> ExtractionComparison:
    """두 ExtractionResult를 비교하여 ExtractionComparison 생성."""
    comparison = ExtractionComparison(
        case_name=case_name,
        duration_ms=duration_ms,
    )

    # 기대값이 전혀 없으면 스킵
    if not expected.has_data():
        comparison.has_expected = False
        comparison.has_data = actual.has_data()
        return comparison

    comparison.has_expected = True
    comparison.has_data = actual.has_data()

    # ── 주식 데이터 비교 ──
    for i, exp_sp in enumerate(expected.stock_prices):
        actual_sp: ExtractedStockPrice | None = None
        if i < len(actual.stock_prices):
            actual_sp = actual.stock_prices[i]

        prefix = f"stock[{i}]."
        for field_name in [
            "name",
            "ticker",
            "close_price",
            "open_price",
            "high_price",
            "low_price",
            "change_percent",
            "change_amount",
            "volume",
        ]:
            exp_val = getattr(exp_sp, field_name, None)
            act_val = getattr(actual_sp, field_name, None) if actual_sp else None
            fs = _compare_fields(exp_val, act_val, f"{prefix}{field_name}")
            if fs is not None:
                comparison.field_scores.append(fs)

        # ── 날씨 데이터 비교 ──
    for i, exp_w in enumerate(expected.weather):
        actual_w: ExtractedWeather | None = None
        if i < len(actual.weather):
            actual_w = actual.weather[i]

        prefix = f"weather[{i}]."
        for field_name in ["location", "temperature", "feels_like", "humidity", "condition"]:
            exp_val = getattr(exp_w, field_name, None)
            act_val = getattr(actual_w, field_name, None) if actual_w else None
            fs = _compare_fields(exp_val, act_val, f"{prefix}{field_name}")
            if fs is not None:
                comparison.field_scores.append(fs)

        # ── 환율 데이터 비교 ──
    for i, exp_er in enumerate(expected.exchange_rates):
        actual_er: ExtractedExchangeRate | None = None
        if i < len(actual.exchange_rates):
            actual_er = actual.exchange_rates[i]

        prefix = f"exchange[{i}]."
        for field_name in ["currency_pair", "rate", "change_percent"]:
            exp_val = getattr(exp_er, field_name, None)
            act_val = getattr(actual_er, field_name, None) if actual_er else None
            fs = _compare_fields(exp_val, act_val, f"{prefix}{field_name}")
            if fs is not None:
                comparison.field_scores.append(fs)

        # ── 날짜 데이터 비교 ──
    exp_dates = set(expected.dates_found)
    act_dates = set(actual.dates_found)
    all_dates = exp_dates | act_dates
    for d in sorted(all_dates):
        fs = _compare_fields(
            d if d in exp_dates else None,
            d if d in act_dates else None,
            f"date: {d}",
        )
        if fs is not None:
            comparison.field_scores.append(fs)

    # 점수 집계
    comparison.fields_total = len(comparison.field_scores)
    comparison.fields_matched = sum(1 for fs in comparison.field_scores if fs.match)
    comparison.accuracy_pct = (
        round(comparison.fields_matched / max(1, comparison.fields_total) * 100, 1)
        if comparison.fields_total > 0
        else 0.0
    )

    return comparison


# ─── 실행기 ────────────────────────────────────────────────────────


class ExtractionABTestRunner:
    """데이터 추출 A/B 테스트 실행기.

    테스트 케이스 스위트를 실행하고 정확도 보고서를 생성합니다.
    """

    def __init__(self, extractor: DataExtractor | None = None) -> None:
        self._extractor: DataExtractor = extractor or DataExtractor()

    def run_test(
        self,
        case: ExtractionABTestCase,
    ) -> ExtractionComparison:
        """단일 테스트 케이스 실행.

        Args:
            case: 실행할 테스트 케이스

        Returns:
            추출 결과와 기대값을 비교한 ExtractionComparison
        """
        start = time.perf_counter()
        result = self._extractor.extract_all(case.input_texts, query=case.query)
        duration_ms = (time.perf_counter() - start) * 1000

        return _compare_extraction_results(result, case.expected, case.name, duration_ms)

    def run_suite(
        self,
        cases: list[ExtractionABTestCase],
        version_label: str = "current",
    ) -> ABTestReport:
        """여러 테스트 케이스를 실행하고 보고서 생성.

        Args:
            cases: 테스트 케이스 목록
            version_label: 실행 버전 레이블 (대시보드 표시용)

        Returns:
            전체 테스트 결과를 담은 ABTestReport
        """
        comparisons: list[ExtractionComparison] = []
        total_matched = 0
        total_fields = 0
        total_duration = 0.0
        tag_accuracies: dict[str, list[float]] = {}

        for case in cases:
            comparison = self.run_test(case)
            comparisons.append(comparison)
            total_matched += comparison.fields_matched
            total_fields += comparison.fields_total
            total_duration += comparison.duration_ms

            # 태그별 정확도 집계
            for tag in case.tags:
                if tag not in tag_accuracies:
                    tag_accuracies[tag] = []
                tag_accuracies[tag].append(comparison.accuracy_pct)

        avg_acc = round(total_matched / max(1, total_fields) * 100, 1) if total_fields > 0 else 0.0
        avg_dur = round(total_duration / max(1, len(cases)), 1)

        # 태그별 평균 정확도
        by_tag = {tag: round(sum(accs) / len(accs), 1) for tag, accs in tag_accuracies.items()}

        return ABTestReport(
            timestamp=datetime.now().isoformat(),
            version_label=version_label,
            total_cases=len(cases),
            comparisons=comparisons,
            total_fields_matched=total_matched,
            total_fields=total_fields,
            avg_accuracy=avg_acc,
            avg_duration_ms=avg_dur,
            by_tag=by_tag,
        )


# ─── 내장 테스트 케이스 ────────────────────────────────────────────

# 테스트 스니펫
_SNIPPET_HANWHA = (
    "📊 한화에어로스페이스 (012450) 943,000원 ▲14,000원 +1.51% (상승)\n"
    "종가: 943,000원 | 시가: 930,000원 | 고가: 970,000원 | "
    "저가: 905,000원 | 거래량: 142,859주 | 등락률: +1.51%\n"
    'Markdown Content:\n{"query":"한화에어로스페이스","answer":{"text":"'
    '한화에어로스페이스 현재 943,000원에 거래되었습니다."}}'
)

_SNIPPET_SAMSUNG = (
    "삼성전자(005930) 84,500원 (-0.82%)\n"
    'Markdown Content:\n{"query":"삼성전자","answer":{"text":"'
    '삼성전자 현재 84,500원에 거래되었습니다."}}'
)

_SNIPPET_WEATHER = "서울 날씨: 기온 28.5°C, 습도 65%, 맑음\nWeather report: Seoul"

_SNIPPET_EXCHANGE = "원/달러 환율 1,382.50원 (-0.12%)"

# 내장 테스트 케이스
BUILTIN_CASES: list[ExtractionABTestCase] = [
    ExtractionABTestCase(
        name="한화에어로스페이스",
        query="한화에어로스페이스 주가",
        input_texts=[_SNIPPET_HANWHA],
        tags=["stock", "korean", "manwon"],
        expected=ExtractionResult(
            stock_prices=[
                ExtractedStockPrice(
                    name="한화에어로스페이스",
                    ticker="012450",
                    close_price=943000,
                    open_price=930000,
                    high_price=970000,
                    low_price=905000,
                    change_percent=1.51,
                    change_amount=14000,
                    volume=142859,
                ),
            ],
            dates_found=[],
        ),
    ),
    ExtractionABTestCase(
        name="삼성전자",
        query="삼성전자 주가",
        input_texts=[_SNIPPET_SAMSUNG],
        tags=["stock", "korean"],
        expected=ExtractionResult(
            stock_prices=[
                ExtractedStockPrice(
                    name="삼성전자",
                    ticker="005930",
                    close_price=84500,
                    change_percent=-0.82,
                ),
            ],
        ),
    ),
    ExtractionABTestCase(
        name="서울 날씨",
        query="서울 날씨",
        input_texts=[_SNIPPET_WEATHER],
        tags=["weather", "korean"],
        expected=ExtractionResult(
            weather=[
                ExtractedWeather(
                    location="Seoul",
                    temperature=28.5,
                    humidity=65,
                    condition="맑음",
                ),
            ],
        ),
    ),
    ExtractionABTestCase(
        name="원달러 환율",
        query="원달러 환율",
        input_texts=[_SNIPPET_EXCHANGE],
        tags=["exchange", "korean"],
        expected=ExtractionResult(
            exchange_rates=[
                ExtractedExchangeRate(
                    currency_pair="원/달러",
                    rate=1382.50,
                    change_percent=-0.12,
                ),
            ],
        ),
    ),
]


def run_builtin_suite(version_label: str = "builtin") -> ABTestReport:
    """내장 테스트 케이스로 전체 스위트 실행."""
    runner = ExtractionABTestRunner()
    return runner.run_suite(BUILTIN_CASES, version_label=version_label)


# ─── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_builtin_suite()
    print(report.to_markdown())
    print(f"\nJSON: {json.dumps(report.to_dict(), indent=2, ensure_ascii=False)}")
