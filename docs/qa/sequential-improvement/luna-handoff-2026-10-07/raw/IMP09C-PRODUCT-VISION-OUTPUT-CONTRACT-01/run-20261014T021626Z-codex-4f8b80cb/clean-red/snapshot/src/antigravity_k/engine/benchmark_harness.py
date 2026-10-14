"""Ssak-Ai: 벤치마크 하네스 (BenchmarkHarness).

===================================================
collective-council vs 단일 모델 품질/속도/토큰 효율 A/B 비교 엔진.

동일 코딩 과제를 복수 타겟(collective-council, 개별 모델)에 순차 투입하고
QualityGate 자동 채점 → JSON DB 누적 저장 → 마크다운 비교표 생성.

사용법:
    harness = BenchmarkHarness(model_manager)
    report = harness.run_suite("all", targets=["collective-council", "deepseek-r1:32b"])
    print(harness.comparison_table())
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Final, Protocol, TypedDict, cast

from antigravity_k.engine.benchmark_cases import BenchmarkCase, get_suite
from antigravity_k.engine.model_calibration import TaskBenchmarkMetrics
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.prompt_builder import PromptBuilder
from antigravity_k.engine.quality_gate import QualityGate

logger = logging.getLogger("antigravity_k.benchmark_harness")
_PROVIDER_ERROR_PREFIX: Final[str] = "[API Error for "

# CR-14 F-02: 기본 벤치마크 DB 위치를 **단일 결정 지점**으로 분리한다.
#
# 이전에는 클래스 상수 `Path("data/benchmark_results.json")`(CWD 상대)가 유일한 정의였고,
# API 런타임이 `AgentRuntime(task_outcome_recorder=benchmark_harness.record_task_outcome)` 로
# **모든 작업 완료를 그 파일에 기록**했다(`api/dependencies.py`). 그 결과 작업을 실행하는
# 테스트가 하나라도 있으면 검증 실행이 **저장소 추적 파일을 다시 써서** 후보 트리를 더럽혔고
# (CR-13 R03 드리프트의 뿌리), 게이트 코드 지문도 실행마다 이동했다.
#
# 프로덕션 기본값(`data/benchmark_results.json`)은 그대로 둔다 — 이 파일은 추적되는 누적
# 결과 DB라는 제품 계약이 있다. 대신 **테스트·배포가 인자 없이도 경로를 바꿀 수 있게**
# 리졸버 하나로 모은다. `tests/conftest.py` 는 CR-02 D-07(`default_session_base_dir`)과
# 같은 방식으로 이 함수를 패치해 사용자 저장소를 보호한다.
BENCHMARK_DB_ENV_VAR: Final[str] = "AGK_BENCHMARK_DB"
DEFAULT_BENCHMARK_DB_RELATIVE: Final[Path] = Path("data/benchmark_results.json")


def resolve_benchmark_db_path(environ: Mapping[str, str] | None = None) -> Path:
    """환경 값으로부터 DB 경로를 계산하는 **순수** 함수(전역 상태를 읽지 않는다).

    ``environ`` 을 주면 그 매핑을, 주지 않으면 ``os.environ`` 을 읽는다. 순수 함수로 분리한
    이유: ``tests/conftest.py`` 가 ``default_benchmark_db_path`` 를 패치해 저장소 파일을
    보호하므로, 우선순위 규칙 자체는 패치와 무관하게 검증할 수 있어야 한다.
    ``~`` 는 확장한다. 빈 값/공백은 '설정하지 않음'으로 본다.
    """
    source = os.environ if environ is None else environ
    override = source.get(BENCHMARK_DB_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_BENCHMARK_DB_RELATIVE


def default_benchmark_db_path() -> Path:
    """기본 벤치마크 결과 DB 경로.

    ``AGK_BENCHMARK_DB`` 가 설정되어 있으면 그 경로를(``~`` 확장 후), 아니면 프로덕션
    기본값을 돌려준다. 테스트는 이 함수를 패치할 수 있다(저장소 파일 보호).
    """
    return resolve_benchmark_db_path()


class BenchmarkResultDict(TypedDict):
    case_id: str
    target: str
    quality_score: float
    quality_grade: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    output_preview: str
    timestamp: float
    issues: list[str]
    benchmark_score: float
    keyword_coverage: float
    passed_keywords: list[str]
    missing_keywords: list[str]
    error: str
    quality_revision_count: int
    quality_revision_applied: bool
    verified: bool
    verified_output: str


class TaskOutcomeDict(TypedDict):
    case_id: str
    target: str
    success: bool
    completion_reason: str
    expected_tools: tuple[str, ...]
    used_tools: tuple[str, ...]
    retry_count: int
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: str
    calibration_eligible: bool


class TaskBenchmarkReportDict(TypedDict):
    task_success_rate: float
    tool_accuracy: float
    retry_rate: float
    recovery_success_rate: float
    avg_latency_ms: float
    total_tokens: int
    total_cost_usd: float
    avg_cost_usd: float
    error_count: int
    outcomes: list[TaskOutcomeDict]


class BenchmarkReportDict(TypedDict):
    suite_name: str
    targets: list[str]
    started_at: float
    finished_at: float
    duration_s: float
    results: list[BenchmarkResultDict]


class AmplificationModeStats(TypedDict):
    mean_score: float
    excellent_rate: float
    fail_rate: float
    n: int


class AmplificationImprovement(TypedDict, total=False):
    baseline: str
    mean_delta: float
    improved: int
    worse: int
    same: int


class AmplificationStats(TypedDict):
    by_mode: dict[str, AmplificationModeStats]
    improvement: AmplificationImprovement


class AmplificationOutput(TypedDict):
    by_case: dict[str, dict[str, "BenchmarkResult"]]
    summary: str
    stats: AmplificationStats


class BenchmarkResultData(TypedDict, total=False):
    case_id: str
    target: str
    quality_score: float
    quality_grade: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    output_preview: str
    timestamp: float
    issues: list[str]
    benchmark_score: float
    keyword_coverage: float
    passed_keywords: list[str]
    missing_keywords: list[str]
    error: str
    quality_revision_count: int
    quality_revision_applied: bool
    verified: bool
    verified_output: str


class TaskOutcomeData(TypedDict, total=False):
    case_id: str
    target: str
    success: bool
    completion_reason: str
    expected_tools: tuple[str, ...]
    used_tools: tuple[str, ...]
    retry_count: int
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: str
    calibration_eligible: bool


class _OutcomeRecorder(Protocol):
    @property
    def outcome_recorder(self) -> Callable[[TaskOutcome], object] | None: ...


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _as_object_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping)]


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


# ─── 데이터 클래스 ───────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    """벤치마크 과제 1건의 실행 결과."""

    case_id: str
    target: str  # "collective-council" or "deepseek-r1:32b" etc.
    quality_score: float  # 0.0 ~ 1.0
    quality_grade: str  # A / B / C / F
    latency_ms: float
    tokens_in: int
    tokens_out: int
    output_preview: str  # 첫 500자
    timestamp: float
    issues: list[str] = field(default_factory=list)
    benchmark_score: float = 0.0  # QualityGate + expected keyword coverage composite
    keyword_coverage: float = 0.0  # 0.0 ~ 1.0
    passed_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    error: str = ""
    quality_revision_count: int = 0
    quality_revision_applied: bool = False
    verified: bool = False
    verified_output: str = ""

    def to_dict(self) -> BenchmarkResultDict:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return {
            "case_id": self.case_id,
            "target": self.target,
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade,
            "latency_ms": self.latency_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "output_preview": self.output_preview,
            "timestamp": self.timestamp,
            "issues": list(self.issues),
            "benchmark_score": self.benchmark_score,
            "keyword_coverage": self.keyword_coverage,
            "passed_keywords": list(self.passed_keywords),
            "missing_keywords": list(self.missing_keywords),
            "error": self.error,
            "quality_revision_count": self.quality_revision_count,
            "quality_revision_applied": self.quality_revision_applied,
            "verified": self.verified,
            "verified_output": self.verified_output,
        }


@dataclass(frozen=True)
class TaskOutcome:
    case_id: str
    target: str
    success: bool
    completion_reason: str
    expected_tools: tuple[str, ...] = ()
    used_tools: tuple[str, ...] = ()
    retry_count: int = 0
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str = ""
    calibration_eligible: bool = False

    def __post_init__(self) -> None:
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")
        if self.latency_ms < 0 or self.tokens_in < 0 or self.tokens_out < 0 or self.cost_usd < 0:
            raise ValueError("execution metrics must be non-negative")

    @property
    def tool_recall(self) -> float:
        expected = set(self.expected_tools)
        if not expected:
            return 1.0 if not self.used_tools else 0.0
        return len(expected & set(self.used_tools)) / len(expected)

    @property
    def tool_precision(self) -> float:
        used = set(self.used_tools)
        if not used:
            return 1.0 if not self.expected_tools else 0.0
        return len(used & set(self.expected_tools)) / len(used)

    @property
    def tool_accuracy(self) -> float:
        return self.tool_recall

    def to_dict(self) -> TaskOutcomeDict:
        return {
            "case_id": self.case_id,
            "target": self.target,
            "success": self.success,
            "completion_reason": self.completion_reason,
            "expected_tools": self.expected_tools,
            "used_tools": self.used_tools,
            "retry_count": self.retry_count,
            "latency_ms": self.latency_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "calibration_eligible": self.calibration_eligible,
        }


@dataclass(frozen=True)
class TaskThresholds:
    min_success_rate: float = 0.8
    min_tool_accuracy: float = 0.8
    max_retry_rate: float = 0.5
    max_avg_latency_ms: float = 30_000.0
    max_total_cost_usd: float = 1.0

    def __post_init__(self) -> None:
        bounded = (
            self.min_success_rate,
            self.min_tool_accuracy,
            self.max_retry_rate,
        )
        if any(value < 0 or value > 1 for value in bounded):
            raise ValueError("rate thresholds must be between 0 and 1")
        if self.max_avg_latency_ms < 0 or self.max_total_cost_usd < 0:
            raise ValueError("maximum thresholds must be non-negative")


@dataclass
class TaskBenchmarkReport:
    outcomes: list[TaskOutcome] = field(default_factory=list)

    @property
    def task_success_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(outcome.success for outcome in self.outcomes) / len(self.outcomes)

    @property
    def tool_accuracy(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(outcome.tool_accuracy for outcome in self.outcomes) / len(self.outcomes)

    @property
    def retry_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(outcome.retry_count > 0 for outcome in self.outcomes) / len(self.outcomes)

    @property
    def recovery_success_rate(self) -> float:
        """Fraction of retried tasks that ultimately succeeded.

        Distinct from retry_rate (how often retries happen) and task_success_rate
        (overall success): this measures whether the retry/recovery loop actually
        rescued a task that initially struggled. Returns 0.0 when no task retried.
        """
        retried = [o for o in self.outcomes if o.retry_count > 0]
        if not retried:
            return 0.0
        return sum(o.success for o in retried) / len(retried)

    @property
    def avg_latency_ms(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(outcome.latency_ms for outcome in self.outcomes) / len(self.outcomes)

    @property
    def total_tokens(self) -> int:
        return sum(outcome.tokens_in + outcome.tokens_out for outcome in self.outcomes)

    @property
    def total_cost_usd(self) -> float:
        return sum(outcome.cost_usd for outcome in self.outcomes)

    @property
    def avg_cost_usd(self) -> float:
        if not self.outcomes:
            return 0.0
        return self.total_cost_usd / len(self.outcomes)

    @property
    def error_count(self) -> int:
        return sum(not outcome.success for outcome in self.outcomes)

    def check_thresholds(self, thresholds: TaskThresholds) -> tuple[str, ...]:
        if not self.outcomes:
            return ("no_outcomes",)
        failures: list[str] = []
        if self.task_success_rate < thresholds.min_success_rate:
            failures.append("success_rate")
        if self.tool_accuracy < thresholds.min_tool_accuracy:
            failures.append("tool_accuracy")
        if self.retry_rate > thresholds.max_retry_rate:
            failures.append("retry_rate")
        if self.avg_latency_ms > thresholds.max_avg_latency_ms:
            failures.append("avg_latency_ms")
        if self.total_cost_usd > thresholds.max_total_cost_usd:
            failures.append("total_cost_usd")
        return tuple(failures)

    def to_dict(self) -> TaskBenchmarkReportDict:
        return {
            "task_success_rate": self.task_success_rate,
            "tool_accuracy": self.tool_accuracy,
            "retry_rate": self.retry_rate,
            "recovery_success_rate": self.recovery_success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "avg_cost_usd": self.avg_cost_usd,
            "error_count": self.error_count,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }


@dataclass
class BenchmarkReport:
    """스위트 실행 전체 리포트."""

    suite_name: str
    targets: list[str]
    results: list[BenchmarkResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration_s(self) -> float:
        """Duration S.

        Returns:
            float: The float result.

        """
        return self.finished_at - self.started_at

    def to_dict(self) -> BenchmarkReportDict:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return {
            "suite_name": self.suite_name,
            "targets": self.targets,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.duration_s, 1),
            "results": [r.to_dict() for r in self.results],
        }


# ─── 메인 하네스 ─────────────────────────────────────────────────────


class BenchmarkHarness:
    """Collective-council vs 단일 모델 벤치마크 실행기."""

    # 하위 호환을 위해 상수는 남기지만, 실제 기본값은 `default_benchmark_db_path()` 가
    # 결정한다(테스트/배포가 그 한 지점만 바꾸면 된다).
    DEFAULT_DB_PATH: ClassVar[Path] = DEFAULT_BENCHMARK_DB_RELATIVE
    _manager: ModelManager
    _db_path: Path
    _quality_gate: QualityGate
    _task_calibration_updater: Callable[[str, TaskBenchmarkMetrics | None], None] | None
    _prompt_builder: PromptBuilder

    def __init__(
        self,
        model_manager: ModelManager,
        db_path: Path | None = None,
        quality_gate: QualityGate | None = None,
        task_calibration_updater: Callable[[str, TaskBenchmarkMetrics | None], None] | None = None,
    ):
        """Initialize the BenchmarkHarness.

        Args:
            model_manager: model manager.
            db_path (Path | None): Path | None db path.
            quality_gate (QualityGate | None): QualityGate | None quality gate.

        """
        self._manager = model_manager
        self._db_path = db_path or default_benchmark_db_path()
        self._quality_gate = quality_gate or QualityGate(max_retries=2)
        self._task_calibration_updater = task_calibration_updater
        self._prompt_builder = PromptBuilder()
        self._history: list[BenchmarkResult] = []
        self._task_history: list[TaskOutcome] = []
        self._load_history()
        self._sync_task_calibration()

    @staticmethod
    def task_context_for_case(case: BenchmarkCase) -> dict[str, object]:
        return {
            "benchmark_case_id": case.id,
            "benchmark_category": case.category,
            "benchmark_difficulty": case.difficulty,
            "expected_keywords": list(case.expected_keywords),
            "expected_tools": list(case.expected_tools),
            "benchmark_read_only": True,
            "use_worktree": False,
        }

    # ─── 공개 API ────────────────────────────────────────────────────

    def run_case(
        self,
        case: BenchmarkCase,
        targets: list[str],
    ) -> list[BenchmarkResult]:
        """단일 과제를 복수 타겟에 순차 실행합니다."""
        results: list[BenchmarkResult] = []
        for target in targets:
            result = self._execute_single(case, target)
            results.append(result)
            self._history.append(result)
            logger.info(
                "[Benchmark] %s × %s → %s (%.0f%%, %.1fs)",
                case.id,
                target,
                result.quality_grade,
                result.quality_score * 100,
                result.latency_ms / 1000,
            )
        self._save_history()
        return results

    def run_suite(
        self,
        suite_name: str = "all",
        targets: list[str] | None = None,
    ) -> BenchmarkReport:
        """과제 스위트를 실행합니다.

        Args:
            suite_name: "all", "simple", "algorithm", 또는 개별 ID
            targets: 비교 대상 목록. None이면 config에서 자동 결정.

        """
        if targets is None:
            targets = self._default_targets()

        cases = get_suite(suite_name)
        report = BenchmarkReport(
            suite_name=suite_name,
            targets=targets,
            started_at=time.time(),
        )

        total = len(cases) * len(targets)
        logger.info(
            "[Benchmark] 스위트 '%s' 시작: %d 과제 × %d 타겟 = %d 실행",
            suite_name,
            len(cases),
            len(targets),
            total,
        )

        for idx, case in enumerate(cases, start=1):
            logger.info(
                "[Benchmark] [%d/%d] %s (%s, 난이도 %d)",
                idx,
                len(cases),
                case.id,
                case.description,
                case.difficulty,
            )
            case_results = self.run_case(case, targets)
            report.results.extend(case_results)

        report.finished_at = time.time()
        logger.info(
            "[Benchmark] 스위트 '%s' 완료: %.1fs, %d 결과",
            suite_name,
            report.duration_s,
            len(report.results),
        )
        return report

    def comparison_table(self, suite_name: str = "all") -> str:
        """누적 결과를 기반으로 마크다운 비교표를 생성합니다."""
        cases = get_suite(suite_name)
        case_ids = {c.id for c in cases}

        # 해당 스위트의 결과만 필터
        relevant = [r for r in self._history if r.case_id in case_ids]
        if not relevant:
            return "벤치마크 결과가 없습니다. `/benchmark run`으로 실행하세요."

        # 타겟별 집계
        targets: dict[str, list[BenchmarkResult]] = {}
        for r in relevant:
            targets.setdefault(r.target, []).append(r)

        # ── 요약 테이블 ──
        lines = [
            "## 📊 Benchmark 비교표\n",
            "| 타겟 | 실행 수 | 평균 종합점수 | 평균 품질 | 키워드 커버리지 | A/B 비율 | 평균 레이턴시 | 평균 토큰(out) |",
            "|------|---------|---------------|----------|----------------|---------|-------------|---------------|",
        ]

        target_summaries: list[tuple[str, float, float, float, float]] = []
        for target, results in sorted(targets.items()):
            n = len(results)
            avg_b = sum(r.benchmark_score for r in results) / n
            avg_q = sum(r.quality_score for r in results) / n
            avg_k = sum(r.keyword_coverage for r in results) / n
            ab_count = sum(1 for r in results if r.quality_grade in ("excellent", "good"))
            ab_ratio = ab_count / n * 100
            avg_lat = sum(r.latency_ms for r in results) / n / 1000
            avg_tok = sum(r.tokens_out for r in results) / n
            target_summaries.append((target, avg_b, avg_q, avg_k, avg_lat))
            lines.append(
                f"| `{target}` | {n} | {avg_b:.0%} | {avg_q:.0%} | {avg_k:.0%} | {ab_ratio:.0f}% | {avg_lat:.1f}s | {avg_tok:.0f} |",
            )

        if target_summaries:
            leader = max(target_summaries, key=lambda item: item[1])
            lines.insert(
                1,
                f"> 현재 우세 타겟: `{leader[0]}` (종합 {leader[1]:.0%}, 품질 {leader[2]:.0%}, 키워드 "
                + f"{leader[3]:.0%}, 평균 {leader[4]:.1f}s)\n",
            )

        # ── 과제별 상세 ──
        lines.append("\n### 과제별 상세\n")
        target_names = sorted(targets.keys())
        header = "| 과제 | 난이도 | " + " | ".join(f"`{t}`" for t in target_names) + " |"
        sep = "|------|--------|" + "|".join("--------" for _ in target_names) + "|"
        lines.append(header)
        lines.append(sep)

        for case in cases:
            row = f"| {case.id} | {'⭐' * case.difficulty} |"
            for target in target_names:
                # 가장 최근 결과 사용
                matching = [r for r in relevant if r.case_id == case.id and r.target == target]
                if matching:
                    latest = max(matching, key=lambda r: r.timestamp)
                    grade_emoji = {
                        "excellent": "🟢A",
                        "good": "🔵B",
                        "retry": "🟡C",
                        "fail": "🔴F",
                    }.get(latest.quality_grade, latest.quality_grade)
                    row += f" {grade_emoji} (종합 {latest.benchmark_score:.0%}, {latest.latency_ms / 1000:.1f}s) |"
                else:
                    row += " — |"
            lines.append(row)

        return "\n".join(lines)

    def compare_amplification(
        self,
        case_ids: list[str],
        target: str,
        modes: list[str] | None = None,
    ) -> AmplificationOutput:
        """같은 과제를 증폭 모드(cascade on/off)로 실행해 효과를 비교한다.

        cascade ON이 낮은 신뢰도 응답을 상위 티어로 재생성해 품질을
        끌어올리는지 수치로 보여준다. 작은 모델 성능 증폭 목표의 객관 증거.

        """
        modes = modes or ["cascade_off", "cascade_on"]
        suite = {c.id: c for c in get_suite("all")}
        router = self._manager.router
        original = router.cascade_on_low_confidence
        # revision(재생성 기반) 증폭 비교 모드는 QualityGate.max_retries를 스왑한다.
        # revision_off → 0(루프 미발화), revision_on → 2(재생성 증폭). 원복은 finally에서.
        original_retries = self._quality_gate.max_retries

        results: dict[str, dict[str, BenchmarkResult]] = {}
        try:
            for cid in case_ids:
                case = suite.get(cid)
                if case is None:
                    continue
                results[cid] = {}
                for mode in modes:
                    router.cascade_on_low_confidence = mode == "cascade_on"
                    if mode == "revision_off":
                        self._quality_gate.max_retries = 0
                    elif mode == "revision_on":
                        self._quality_gate.max_retries = 2
                    elif mode in ("avo_on", "bon_avo"):
                        # AVO 감독 재시도 예산. baseline/bon 계열(0회)과의 생성 횟수
                        # 형평을 위해 2회로 고정한다 — BoN(n=3)과 동일한 상한.
                        self._quality_gate.max_retries = 2
                    else:
                        self._quality_gate.max_retries = original_retries
                    # sc_on 모드는 초기 답을 self-consistency(N샘플링)로 생성한다.
                    use_sc = mode == "sc_on"
                    # decomp_on 모드는 초기 답을 LLM 단계 분해 경로로 생성한다.
                    use_td = mode == "decomp_on"
                    # bon_on/bon_avo 모드는 초기 답을 실행 검증 Best-of-N 경로로 생성한다.
                    use_bon = mode in ("bon_on", "bon_avo")
                    # avo_on/bon_avo 모드는 AVO 감독축(반복 차단·유사 오류 클러스터·
                    # 무진행 윈도우)으로 재시도를 통제한다.
                    supervised = mode in ("avo_on", "bon_avo")
                    results[cid][mode] = self._execute_single(
                        case,
                        target,
                        self_consistent=use_sc,
                        decomposed=use_td,
                        best_of_n=use_bon,
                        supervised=supervised,
                    )
        finally:
            router.cascade_on_low_confidence = original
            self._quality_gate.max_retries = original_retries

        return {
            "by_case": results,
            "summary": self._amplification_summary(results, modes),
            "stats": self._amplification_stats(results, modes),
        }

    def _amplification_stats(
        self,
        results: dict[str, dict[str, BenchmarkResult]],
        modes: list[str],
    ) -> AmplificationStats:
        """증폭 모드 간 평균 점수/등급 분포/개선 케이스 비율 등 통계.

        노이즈가 큰 단일 케이스 측정을 보완하기 위해 여러 케이스에 걸친
        평균으로 증폭 효과의 안정성을 판단한다.
        """
        from statistics import fmean

        mode_stats: dict[str, AmplificationModeStats] = {}
        valid = {cid: by for cid, by in results.items() if all(m in by for m in modes)}
        for mode in modes:
            scores = [by[mode].benchmark_score for by in valid.values() if not by[mode].error]
            grades = [by[mode].quality_grade for by in valid.values() if not by[mode].error]
            mode_stats[mode] = {
                "mean_score": fmean(scores) if scores else 0.0,
                "excellent_rate": grades.count("excellent") / len(grades) if grades else 0.0,
                "fail_rate": sum(1 for g in grades if g in ("fail", "retry")) / len(grades) if grades else 0.0,
                "n": len(scores),
            }
        # 첫 모드를 baseline으로 후속 모드가 얼마나 개선했는지 비율.
        improvement: AmplificationImprovement = {}
        if len(modes) >= 2 and valid:
            base = modes[0]
            improved = worse = same = 0
            deltas: list[float] = []
            for by in valid.values():
                b = by[base]
                for other in modes[1:]:
                    o = by[other]
                    if b.error or o.error:
                        continue
                    delta = o.benchmark_score - b.benchmark_score
                    deltas.append(delta)
                    if delta > 1e-9:
                        improved += 1
                    elif delta < -1e-9:
                        worse += 1
                    else:
                        same += 1
            if deltas:
                improvement = {
                    "baseline": base,
                    "mean_delta": fmean(deltas),
                    "improved": improved,
                    "worse": worse,
                    "same": same,
                }
        return {"by_mode": mode_stats, "improvement": improvement}

    def record_task_outcome(self, outcome: TaskOutcome) -> TaskOutcome:
        self._task_history.append(outcome)
        self._save_history()
        self._sync_task_calibration(outcome.target)
        return outcome

    def bind_task_runner(self, runner: _OutcomeRecorder) -> _OutcomeRecorder:
        setattr(runner, "outcome_recorder", self.record_task_outcome)
        return runner

    def bind_tool_loop(self, tool_loop: _OutcomeRecorder) -> _OutcomeRecorder:
        setattr(tool_loop, "outcome_recorder", self.record_task_outcome)
        return tool_loop

    def task_report(self, target: str | None = None) -> TaskBenchmarkReport:
        outcomes = (
            self._task_history
            if target is None
            else [outcome for outcome in self._task_history if outcome.target == target]
        )
        return TaskBenchmarkReport(outcomes=list(outcomes))

    def _calibration_task_report(self, target: str) -> TaskBenchmarkReport:
        outcomes = [
            outcome for outcome in self._task_history if outcome.target == target and outcome.calibration_eligible
        ]
        return TaskBenchmarkReport(outcomes=outcomes)

    def _sync_task_calibration(self, target: str | None = None) -> None:
        if self._task_calibration_updater is None:
            return
        targets = {outcome.target for outcome in self._task_history} if target is None else {target}
        for model_name in targets:
            report = self._calibration_task_report(model_name)
            if not report.outcomes:
                self._task_calibration_updater(model_name, None)
                continue
            self._task_calibration_updater(
                model_name,
                TaskBenchmarkMetrics(
                    outcome_count=len(report.outcomes),
                    task_success_rate=report.task_success_rate,
                    tool_accuracy=report.tool_accuracy,
                    retry_rate=report.retry_rate,
                    avg_latency_ms=report.avg_latency_ms,
                    avg_cost_usd=report.avg_cost_usd,
                    error_count=report.error_count,
                ),
            )

    def export_task_calibration_artifact(self, target: str, path: Path | None = None) -> Path:
        report = self._calibration_task_report(target)
        if not report.outcomes:
            raise ValueError(f"No task outcomes are recorded for target '{target}'")
        destination = (
            path or Path("data/benchmarks") / f"task-calibration-{target.replace('/', '_').replace(':', '_')}.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "artifact_type": "task_benchmark",
            "model": target,
            "task_benchmark": {
                "outcome_count": len(report.outcomes),
                "task_success_rate": report.task_success_rate,
                "tool_accuracy": report.tool_accuracy,
                "retry_rate": report.retry_rate,
                "avg_latency_ms": report.avg_latency_ms,
                "avg_cost_usd": report.avg_cost_usd,
                "error_count": report.error_count,
            },
        }
        _ = destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    def task_comparison_table(self) -> str:
        report = self.task_report()
        if not report.outcomes:
            return "Task Benchmark 결과가 없습니다. record_task_outcome()으로 결과를 기록하세요."
        return "\n".join(
            [
                "## Task Benchmark",
                "",
                "| 지표 | 값 |",
                "|---|---:|",
                f"| 성공률 | {report.task_success_rate:.0%} |",
                f"| Tool accuracy | {report.tool_accuracy:.0%} |",
                f"| 재시도율 | {report.retry_rate:.0%} |",
                f"| 평균 지연 | {report.avg_latency_ms:.1f}ms |",
                f"| 총 토큰 | {report.total_tokens} |",
                f"| 비용 | ${report.total_cost_usd:.4f} |",
            ],
        )

    def _amplification_summary(self, results: dict[str, dict[str, BenchmarkResult]], modes: list[str]) -> str:
        """증폭 비교 결과 요약표."""
        lines = ["| 과제 | " + " | ".join(modes) + " |", "|" + "---|" * (len(modes) + 1)]
        for cid, by_mode in results.items():
            cells = [cid]
            for mode in modes:
                r = by_mode.get(mode)
                if r and not r.error:
                    cells.append(f"{r.benchmark_score:.0%}/{r.quality_grade}/{r.latency_ms / 1000:.1f}s")
                else:
                    cells.append("ERR")
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    # ─── 내부 실행 ───────────────────────────────────────────────────

    def _execute_single(
        self,
        case: BenchmarkCase,
        target: str,
        self_consistent: bool = False,
        decomposed: bool = False,
        best_of_n: bool = False,
        supervised: bool = False,
    ) -> BenchmarkResult:
        """단일 과제 × 단일 타겟 실행.

        supervised=True면 재시도 루프에 AVO 감독축을 적용한다:
        실패 결과를 HarnessEnforcer에 적재하고, 임계 도달 시 STALL 전략수정
        지시문을 feedback에 주입해 구조적으로 다른 시도를 강제한다.
        """
        start = time.time()
        output = ""
        error = ""
        prompt = self._benchmark_prompt(case)
        quality_revision_count = 0
        quality_revision_applied = False
        supervisor = None
        seen_failure_sigs: set[str] = set()
        if supervised:
            from antigravity_k.engine.harness_enforcer import HarnessEnforcer

            # 단기 예산(재시작 ≤2회)에서도 감독축이 발화하도록 임계값 보정 —
            # scripts/simulate_stall_supervision.py의 보정 절차와 동일 원칙.
            supervisor = HarnessEnforcer(
                project_root=str(Path.cwd()),
                no_progress_window=2,
                error_cluster_threshold=2,
            )

        try:
            gen_kwargs = self._generation_kwargs(target, revision=False)
            # decomposed=True면 복잡 작업을 단계 분해 후 단계별 실행해 통합한다.
            # lh-001류 장기 워크플로 누락 요소 확보가 목적이다.
            if decomposed and hasattr(self._manager, "generate_decomposed"):
                generate_decomposed = cast(Callable[..., str], self._manager.generate_decomposed)
                output = generate_decomposed(
                    prompt=prompt,
                    target=target,
                    **gen_kwargs,
                )
            # best_of_n=True면 실행 검증 Best-of-N 증폭으로 초기 답을 생성한다.
            # 검증자 통과 답변이 실행 가능성을 보장하므로 코드 과제에서 강한 신호다.
            elif best_of_n and hasattr(self._manager, "generate_best_of_n"):
                generate_best_of_n = cast(Callable[..., str], self._manager.generate_best_of_n)
                output = generate_best_of_n(
                    prompt=prompt,
                    target=target,
                    **gen_kwargs,
                )
            # self_consistent=True면 단일 모델 N샘플링 증폭으로 초기 답을 생성한다.
            # revision 루프는 동일하게 적용되어 증폭+재생성이 조합된다.
            elif self_consistent and hasattr(self._manager, "generate_self_consistent"):
                output = self._manager.generate_self_consistent(
                    prompt=prompt,
                    target=target,
                    **gen_kwargs,
                )
            else:
                output = self._manager.generate(
                    prompt=prompt,
                    target=target,
                    **gen_kwargs,
                )
            if output.startswith(_PROVIDER_ERROR_PREFIX):
                error = output
                output = ""
        except Exception as exc:
            error = str(exc)
            logger.exception("[Benchmark] %s × %s 실행 실패", case.id, target)

        elapsed_ms = (time.time() - start) * 1000
        keyword_coverage, passed_keywords, missing_keywords = self._score_keywords(case, output)
        verified, verified_output = self._verify_executed_code(output, case.expected_output)

        # QualityGate 평가
        if output and not error:
            self._quality_gate.reset()
            qscore = self._quality_gate.evaluate(case.category, case.prompt, output)
            best_benchmark_score = self._compose_benchmark_score(
                quality_score=qscore.score,
                keyword_coverage=keyword_coverage,
                error=error,
                expected_output=case.expected_output,
                verified=verified,
            )
            while quality_revision_count < self._quality_gate.max_retries:
                needs_revision = bool(qscore.should_retry and qscore.feedback) or bool(missing_keywords)
                # verified_code: 실행 결과가 기대값과 다르면 코드를 고치도록 유도한다.
                if case.expected_output and not verified:
                    needs_revision = True
                if not needs_revision:
                    break
                self._quality_gate.mark_retry()
                quality_revision_count += 1
                feedback = qscore.feedback or ("[QUALITY GATE] 필수 요구사항 누락: " + ", ".join(missing_keywords))
                if case.expected_output and not verified:
                    feedback = (
                        f"생성한 코드를 실행한 결과가 기대값과 다릅니다. "
                        f"기대 출력: {case.expected_output!r}. 실행 가능한 올바른 Python 코드를 다시 작성하세요."
                    )
                if supervisor is not None:
                    # AVO 감독축 적용: 실패 적재 → 임계 도달 시 1회용 STALL 개입 소비.
                    # 오류 지문은 누락 키워드/게이트 피드백에서 뽑는다.
                    failure_sig = (
                        ",".join(sorted(missing_keywords)) if missing_keywords else (qscore.feedback or "")[:120]
                    )
                    supervisor.record_outcome(failed=True, error_text=failure_sig)
                    intervention = supervisor.consume_pending_intervention()
                    if intervention and intervention.get("stall"):
                        feedback = f"{intervention['reason']}\n{feedback}"
                    elif failure_sig in seen_failure_sigs:
                        # 클러스터 임계 미달 상태의 동일 지문 재시도도 차단한다.
                        feedback = f"{type(supervisor).build_stall_message('revision')}\n{feedback}"
                    seen_failure_sigs.add(failure_sig)
                revised = self._quality_revision(case, output, feedback, target)
                if not revised:
                    continue
                revised_score = self._quality_gate.evaluate(case.category, case.prompt, revised)
                revised_keyword_coverage, revised_passed_keywords, revised_missing_keywords = self._score_keywords(
                    case,
                    revised,
                )
                revised_verified, revised_verified_output = self._verify_executed_code(revised, case.expected_output)
                revised_benchmark_score = self._compose_benchmark_score(
                    quality_score=revised_score.score,
                    keyword_coverage=revised_keyword_coverage,
                    error=error,
                    expected_output=case.expected_output,
                    verified=revised_verified,
                )
                if revised_benchmark_score > best_benchmark_score:
                    output = revised
                    qscore = revised_score
                    keyword_coverage = revised_keyword_coverage
                    passed_keywords = revised_passed_keywords
                    missing_keywords = revised_missing_keywords
                    best_benchmark_score = revised_benchmark_score
                    verified = revised_verified
                    verified_output = revised_verified_output
                    quality_revision_applied = True
            quality_score = qscore.score
            quality_grade = qscore.grade.value
            issues = qscore.issues
        else:
            quality_score = 0.0
            quality_grade = "fail"
            issues = [error] if error else ["empty_output"]
            if case.expected_output and not verified:
                issues.append("execution_mismatch")

        # 토큰 추정
        tokens_in = len(prompt) // 4
        tokens_out = len(output) // 4
        benchmark_score = self._compose_benchmark_score(
            quality_score=quality_score,
            keyword_coverage=keyword_coverage,
            error=error,
            expected_output=case.expected_output,
            verified=verified,
        )

        if missing_keywords:
            issues = list(issues)
            issues.append("missing_keywords:" + ",".join(missing_keywords))

        return BenchmarkResult(
            case_id=case.id,
            target=target,
            benchmark_score=benchmark_score,
            quality_score=round(quality_score, 3),
            quality_grade=quality_grade,
            keyword_coverage=keyword_coverage,
            latency_ms=round(elapsed_ms, 1),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            output_preview=output[:500] if output else "",
            timestamp=time.time(),
            issues=issues,
            passed_keywords=passed_keywords,
            missing_keywords=missing_keywords,
            error=error,
            quality_revision_count=quality_revision_count,
            quality_revision_applied=quality_revision_applied,
            verified=verified,
            verified_output=verified_output,
        )

    def _quality_revision(self, case: BenchmarkCase, output: str, feedback: str, target: str) -> str:
        repeat_issue = "반복" in feedback or "repeat" in feedback.lower()
        prior_answer = "기존 답변은 반복 문제가 있어 폐기하고 처음부터 새로 작성하세요." if repeat_issue else output
        prompt = (
            "[QUALITY REVISION]\n"
            "아래 답변을 품질 게이트 피드백에 맞춰 다시 작성하세요.\n"
            "내부 사고 과정, thinking process, 작업 독백은 절대 출력하지 말고 최종 답변만 작성하세요.\n"
            "자연스러운 한국어, 요청 항목 전체, 근거와 검증 방법을 포함하세요.\n"
            "한국어 문장을 다시 읽어 '할 수', '될 수', '사용할 수'처럼 띄어쓰고, 마침표 뒤 문장을 붙이지 마세요.\n"
            "아래 출력 형식과 요구사항을 모두 지키고, 답변을 축약하지 마세요.\n\n"
            f"[구조화된 요청]\n{self._benchmark_prompt(case)}\n\n"
            f"[필수 키워드]\n{', '.join(case.expected_keywords)}\n\n"
            f"[기존 답변]\n{prior_answer}\n\n"
            f"[품질 피드백]\n{feedback}\n\n"
            "[수정된 최종 답변]\n"
        )
        try:
            candidate = self._manager.generate(
                prompt=prompt,
                target=target,
                **self._generation_kwargs(target, revision=True),
            )
        except Exception:
            logger.exception("[Benchmark] quality revision failed")
            return ""
        return candidate.strip()

    @staticmethod
    def _generation_kwargs(target: str, *, revision: bool) -> dict[str, object]:
        if "qwen3" in target.lower():
            return {
                "max_tokens": 3072,
                "temperature": 0.08 if revision else 0.15,
                "min_p": 0.0,
                "repeat_penalty": 1.15 if revision else 1.1,
                "task_type": "CODE",
            }
        return {
            "max_tokens": 4096,
            "temperature": 0.2 if revision else 0.4,
        }

    def _benchmark_prompt(self, case: BenchmarkCase) -> str:
        category = case.category.lower()
        constraints = [
            "반드시 자연스러운 한국어로 답하고, 기술 용어와 코드 식별자는 필요한 경우에만 영어로 유지하세요.",
            "요청의 모든 항목을 답변 전에 점검하고, 확인한 사실과 가정을 구분하세요.",
            "내부 추론이나 작업 독백은 출력하지 말고 최종 답변만 작성하세요.",
            "답변 마지막에 요구사항 충족 여부와 검증 방법을 짧게 확인하세요.",
            "같은 문장이나 섹션을 반복하지 말고, 요구사항에 필요한 범위에서 답변을 마무리하세요.",
        ]
        output_format = "핵심 답변 → 근거/설명 → 검증 및 남은 위험"
        if category in {"search", "research"}:
            constraints.extend(
                [
                    "각 주장 또는 동향에 출처와 근거를 연결하고, 확인할 수 없는 최신 정보는 추측하지 마세요.",
                    "출처가 충돌하면 차이와 불확실성을 명시하세요.",
                ],
            )
            output_format = "핵심 요약 → 동향별 근거 목록 → 출처와 불확실성"
        elif category == "analysis":
            constraints.extend(
                [
                    "가정과 평가 기준을 먼저 밝히세요.",
                    "비교 대상이 여러 개면 마크다운 비교 표를 사용하고 결론과 위험을 분리하세요.",
                ],
            )
            output_format = "가정/기준 → 비교 표 → 권고안 → 위험과 다음 검증"
        elif category in {"long_horizon", "architecture"}:
            constraints.extend(
                [
                    "계획과 의존성 순서를 먼저 제시하세요.",
                    "checkpoint, idempotency, recovery, retry, rollback, 성공 조건과 최종 검증을 모두 포함하세요.",
                ],
            )
            output_format = "계획 → 단계별 checkpoint/도구/성공 조건 → recovery/retry/rollback → 최종 검증"
        elif category == "refactor":
            constraints.append("리팩토링 계획과 의존성 순서를 먼저 제시하세요.")
            constraints.append("변경 전후 비교는 Markdown 표로 제시하세요.")
            output_format = "리팩토링 계획 → 전/후 구조 비교 → 코드 → SOLID 적용 설명 → 테스트 및 주의점"
        elif category in {"coding", "algorithm", "simple", "refactor"}:
            constraints.extend(
                [
                    "코드만 출력하지 말고 선택 이유, 동작 설명, 테스트 방법을 함께 제시하세요.",
                    "알고리즘이나 성능을 요청한 경우 시간·공간 복잡도를 반드시 Big-O 표기(O(...))로 설명하세요.",
                ],
            )
            output_format = "선택 이유와 동작 설명 → 코드 → 테스트/복잡도 → 주의점"
            if "비교" in case.prompt or "compare" in case.prompt.lower():
                constraints.append("비교를 요청한 경우 비교 기준과 결론을 마크다운 표로 반드시 제시하세요.")
                output_format = "선택 이유와 동작 설명 → 비교 표 → 코드 → 테스트/복잡도 → 주의점"
        return self._prompt_builder.structured_prompt(
            role="실행과 검증을 중시하는 로컬 에이전트",
            task=case.prompt,
            constraints=constraints,
            output_format=output_format,
        )

    @staticmethod
    def _score_keywords(
        case: BenchmarkCase,
        output: str,
    ) -> tuple[float, list[str], list[str]]:
        """과제별 기대 키워드 충족률을 계산합니다."""
        expected = list(case.expected_keywords or ())
        if not expected:
            return 1.0, [], []

        output_lower = (output or "").lower()
        passed = [kw for kw in expected if kw.lower() in output_lower]
        missing = [kw for kw in expected if kw.lower() not in output_lower]
        coverage = len(passed) / len(expected)
        return round(coverage, 3), passed, missing

    @staticmethod
    def _verify_executed_code(output: str, expected_output: str) -> tuple[bool, str]:
        """Execute the last Python code block in ``output`` and compare its stdout.

        Returns ``(passed, actual_or_reason)``. A verified_code case is scored on
        what the generated code actually produces when run, not on keyword presence,
        so a model cannot pass by merely narrating the correct answer.
        """
        import re
        import subprocess
        import tempfile
        from pathlib import Path

        if not expected_output:
            return False, "not_applicable"
        blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", output or "", re.DOTALL)
        if not blocks:
            return False, "no_code_block"
        blocks = cast(list[str], re.findall(r"```(?:python|py)?\s*\n(.*?)```", output or "", re.DOTALL))
        code = blocks[-1]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / "solution.py"
                _ = script.write_text(code, encoding="utf-8")
                proc = subprocess.run(
                    ["python3", str(script)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=tmp,
                )
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as exc:  # noqa: BLE001
            return False, f"exec_error: {exc}"
        actual = (proc.stdout or "").strip()
        if proc.returncode != 0:
            return False, f"runtime_error: {(proc.stderr or '').strip()[:200]}"
        return actual == expected_output.strip(), actual

    @staticmethod
    def _compose_benchmark_score(
        *,
        quality_score: float,
        keyword_coverage: float,
        error: str,
        expected_output: str = "",
        verified: bool = False,
    ) -> float:
        """품질 점수와 과제 충족률을 결합한 종합 점수."""
        if error:
            return 0.0
        # verified_code: 실제 실행 결과가 정답 기준. 실행이 맞으면 통과, 틀리면 0점.
        if expected_output:
            return 1.0 if verified else 0.0
        return round((quality_score * 0.7) + (keyword_coverage * 0.3), 3)

    def _default_targets(self) -> list[str]:
        """config.yaml에서 벤치마크 비교 대상을 결정합니다."""
        # collective-council + 개별 모델 중 가용한 것
        targets = ["collective-council"]
        registry = cast(object, getattr(self._manager, "_registry"))
        raw = _as_mapping(cast(object, getattr(registry, "_raw", {})))
        combo = _as_mapping(_as_mapping(raw.get("combos")).get("collective-council"))
        models_value = combo.get("models")
        if isinstance(models_value, Sequence) and not isinstance(models_value, (str, bytes)):
            targets.extend(item for item in models_value if isinstance(item, str))
        return targets

    # ─── 영속화 ──────────────────────────────────────────────────────

    def _load_history(self) -> None:
        """기존 결과를 JSON에서 로드합니다."""
        if not self._db_path.exists():
            return
        try:
            with open(self._db_path, encoding="utf-8") as f:
                data = _as_mapping(cast(object, json.load(f)))
            self._history = []
            self._task_history = []
            for raw_result in _as_object_list(data.get("results")):
                result = BenchmarkResult(**cast(BenchmarkResultData, raw_result))
                if "benchmark_score" not in raw_result:
                    result.benchmark_score = result.quality_score
                if "keyword_coverage" not in raw_result:
                    result.keyword_coverage = 1.0 if result.output_preview and not result.error else 0.0
                self._history.append(result)
            task_history: list[TaskOutcome] = []
            for raw_outcome in _as_object_list(data.get("task_results")):
                outcome_data = dict(raw_outcome)
                outcome_data["expected_tools"] = _as_str_tuple(outcome_data.get("expected_tools"))
                outcome_data["used_tools"] = _as_str_tuple(outcome_data.get("used_tools"))
                task_history.append(TaskOutcome(**cast(TaskOutcomeData, cast(object, outcome_data))))
            self._task_history = task_history
            logger.info("[Benchmark] %d개 기존 결과 로드", len(self._history))
        except Exception:
            logger.exception("[Benchmark] 기존 결과 로드 실패")
            self._history = []
            self._task_history = []

    def _save_history(self) -> None:
        """누적 결과를 JSON에 저장합니다."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "total_results": len(self._history),
            "results": [r.to_dict() for r in self._history],
            "total_task_results": len(self._task_history),
            "task_results": [outcome.to_dict() for outcome in self._task_history],
        }
        try:
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("[Benchmark] 결과 저장: %s", self._db_path)
        except Exception:
            logger.exception("[Benchmark] 결과 저장 실패")

    def clear_history(self) -> None:
        """누적 결과를 초기화합니다."""
        task_targets = {outcome.target for outcome in self._task_history}
        self._history.clear()
        self._task_history.clear()
        self._save_history()
        if self._task_calibration_updater is not None:
            for model_name in task_targets:
                self._task_calibration_updater(model_name, None)
        logger.info("[Benchmark] 누적 결과 초기화")
