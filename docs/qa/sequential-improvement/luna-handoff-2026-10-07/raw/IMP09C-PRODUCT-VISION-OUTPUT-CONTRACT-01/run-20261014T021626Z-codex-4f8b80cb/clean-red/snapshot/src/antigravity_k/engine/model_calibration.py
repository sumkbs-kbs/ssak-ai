from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger("antigravity_k.model_calibration")


class BenchmarkResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    case_id: str
    quality_score: float = Field(ge=0.0, le=1.0)
    benchmark_score: float = Field(ge=0.0, le=1.0)
    quality_grade: str
    error: str = ""


class BenchmarkRun(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    error_count: int = Field(default=0, ge=0)


class BenchmarkStability(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    repeat_count: int = Field(ge=1)
    result_count: int = Field(ge=1)
    mean_benchmark_score: float = Field(ge=0.0, le=1.0)
    min_benchmark_score: float = Field(ge=0.0, le=1.0)
    excellent_rate: float = Field(ge=0.0, le=1.0)
    all_excellent_run_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    runs: tuple[BenchmarkRun, ...] = ()


class BenchmarkArtifact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    model: str = Field(min_length=1)
    results: tuple[BenchmarkResult, ...] = Field(min_length=1)
    stability: BenchmarkStability | None = None


class TaskBenchmarkMetrics(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    outcome_count: int = Field(ge=1)
    task_success_rate: float = Field(ge=0.0, le=1.0)
    tool_accuracy: float = Field(ge=0.0, le=1.0)
    retry_rate: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: float = Field(ge=0.0)
    avg_cost_usd: float = Field(ge=0.0)
    error_count: int = Field(default=0, ge=0)


class TaskBenchmarkArtifact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    artifact_type: str
    model: str = Field(min_length=1)
    task_benchmark: TaskBenchmarkMetrics


class ModelQualityCalibrationConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = False
    artifact_paths: tuple[Path, ...] = ()
    artifact_globs: tuple[str, ...] = ()
    min_mean_benchmark_score: float = Field(default=0.8, ge=0.0, le=1.0)
    min_min_benchmark_score: float = Field(default=0.7, ge=0.0, le=1.0)
    min_excellent_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    min_all_excellent_run_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    min_task_outcome_count: int = Field(default=1, ge=1)
    min_task_success_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    min_task_tool_accuracy: float = Field(default=0.8, ge=0.0, le=1.0)
    max_task_retry_rate: float = Field(default=0.5, ge=0.0, le=1.0)


@dataclass(frozen=True, slots=True)
class ModelQualitySummary:
    model_name: str
    mean_benchmark_score: float
    minimum_benchmark_score: float
    excellent_rate: float
    case_count: int
    repeat_count: int
    all_excellent_run_rate: float
    error_count: int
    artifact_paths: tuple[Path, ...]
    task_outcome_count: int = 0
    task_success_rate: float | None = None
    task_tool_accuracy: float | None = None
    task_retry_rate: float | None = None


class ModelQualityCalibrationStore:
    _config: ModelQualityCalibrationConfig
    _summaries: dict[str, ModelQualitySummary]

    def __init__(
        self,
        config: ModelQualityCalibrationConfig,
        summaries: tuple[ModelQualitySummary, ...],
    ) -> None:
        self._config = config
        self._summaries = {summary.model_name: summary for summary in summaries}
        self._observed_task_metrics: dict[str, TaskBenchmarkMetrics] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @classmethod
    def from_config(
        cls,
        config: ModelQualityCalibrationConfig,
        config_directory: Path,
    ) -> ModelQualityCalibrationStore:
        if not config.enabled:
            return cls(config, ())

        by_model: dict[str, list[ModelQualitySummary]] = {}
        for artifact_path in cls._artifact_paths(config, config_directory):
            try:
                raw_artifact = artifact_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("모델 품질 benchmark artifact를 읽지 못했습니다: %s", artifact_path)
                continue
            try:
                artifact = BenchmarkArtifact.model_validate_json(raw_artifact)
            except ValidationError:
                try:
                    task_artifact = TaskBenchmarkArtifact.model_validate_json(raw_artifact)
                except ValidationError:
                    logger.warning("모델 품질 benchmark artifact 형식이 올바르지 않습니다: %s", artifact_path)
                    continue
                by_model.setdefault(task_artifact.model, []).append(
                    _summary_from_task_artifact(task_artifact, artifact_path)
                )
            else:
                by_model.setdefault(artifact.model, []).append(_summary_from_artifact(artifact, artifact_path))

        return cls(
            config,
            tuple(_combine_summaries(model_name, items) for model_name, items in by_model.items()),
        )

    @staticmethod
    def _artifact_paths(
        config: ModelQualityCalibrationConfig,
        config_directory: Path,
    ) -> tuple[Path, ...]:
        paths = [
            configured_path if configured_path.is_absolute() else config_directory / configured_path
            for configured_path in config.artifact_paths
        ]
        for pattern in config.artifact_globs:
            try:
                pattern_path = Path(pattern).expanduser()
                if pattern_path.is_absolute():
                    paths.extend(sorted(pattern_path.parent.glob(pattern_path.name)))
                else:
                    paths.extend(sorted(config_directory.glob(pattern)))
            except (NotImplementedError, OSError, ValueError):
                logger.warning("모델 품질 benchmark artifact glob이 올바르지 않습니다: %s", pattern)
        return tuple(dict.fromkeys(paths))

    def is_eligible(self, model_name: str) -> bool:
        if not self._config.enabled:
            return True
        observed_metrics = self._observed_task_metrics.get(model_name)
        include_observed_metrics = (
            observed_metrics is None or observed_metrics.outcome_count >= self._config.min_task_outcome_count
        )
        summary = self._summary_for(model_name, include_observed_metrics)
        if summary is None:
            return True
        benchmark_passes = summary.case_count == 0 or (
            summary.mean_benchmark_score >= self._config.min_mean_benchmark_score
            and summary.minimum_benchmark_score >= self._config.min_min_benchmark_score
            and summary.excellent_rate >= self._config.min_excellent_rate
            and summary.all_excellent_run_rate >= self._config.min_all_excellent_run_rate
        )
        task_passes = summary.task_outcome_count == 0 or (
            summary.task_outcome_count >= self._config.min_task_outcome_count
            and summary.task_success_rate is not None
            and summary.task_success_rate >= self._config.min_task_success_rate
            and summary.task_tool_accuracy is not None
            and summary.task_tool_accuracy >= self._config.min_task_tool_accuracy
            and summary.task_retry_rate is not None
            and summary.task_retry_rate <= self._config.max_task_retry_rate
        )
        return summary.error_count == 0 and benchmark_passes and task_passes

    def summaries(self) -> tuple[ModelQualitySummary, ...]:
        return tuple(
            sorted(
                (
                    summary
                    for model_name in self._summaries.keys() | self._observed_task_metrics.keys()
                    if (summary := self._summary_for(model_name)) is not None
                ),
                key=lambda summary: summary.model_name,
            ),
        )

    def set_task_metrics(self, model_name: str, metrics: TaskBenchmarkMetrics | None) -> None:
        if metrics is None:
            _ = self._observed_task_metrics.pop(model_name, None)
            return
        self._observed_task_metrics[model_name] = metrics

    def _summary_for(
        self,
        model_name: str,
        include_observed_metrics: bool = True,
    ) -> ModelQualitySummary | None:
        artifact_summary = self._summaries.get(model_name)
        observed_metrics = self._observed_task_metrics.get(model_name)
        if observed_metrics is None or not include_observed_metrics:
            return artifact_summary
        observed_summary = _summary_from_task_metrics(model_name, observed_metrics)
        if artifact_summary is None:
            return observed_summary
        return _combine_summaries(model_name, [artifact_summary, observed_summary])


def _summary_from_artifact(artifact: BenchmarkArtifact, artifact_path: Path) -> ModelQualitySummary:
    results = artifact.results
    latest_error_count = sum(bool(result.error) for result in results)
    match artifact.stability:
        case BenchmarkStability() as stability:
            return ModelQualitySummary(
                model_name=artifact.model,
                mean_benchmark_score=stability.mean_benchmark_score,
                minimum_benchmark_score=stability.min_benchmark_score,
                excellent_rate=stability.excellent_rate,
                case_count=stability.result_count,
                repeat_count=stability.repeat_count,
                all_excellent_run_rate=(
                    stability.all_excellent_run_rate
                    if stability.all_excellent_run_rate is not None
                    else float(stability.excellent_rate == 1.0)
                ),
                error_count=max(latest_error_count, sum(run.error_count for run in stability.runs)),
                artifact_paths=(artifact_path,),
            )
        case None:
            case_count = len(results)
            scores = tuple(result.benchmark_score for result in results)
            return ModelQualitySummary(
                model_name=artifact.model,
                mean_benchmark_score=sum(scores) / case_count,
                minimum_benchmark_score=min(scores),
                excellent_rate=sum(result.quality_grade == "excellent" for result in results) / case_count,
                case_count=case_count,
                repeat_count=1,
                all_excellent_run_rate=float(all(result.quality_grade == "excellent" for result in results)),
                error_count=latest_error_count,
                artifact_paths=(artifact_path,),
            )


def _summary_from_task_artifact(
    artifact: TaskBenchmarkArtifact,
    artifact_path: Path,
) -> ModelQualitySummary:
    metrics = artifact.task_benchmark
    return ModelQualitySummary(
        model_name=artifact.model,
        mean_benchmark_score=0.0,
        minimum_benchmark_score=0.0,
        excellent_rate=0.0,
        case_count=0,
        repeat_count=0,
        all_excellent_run_rate=1.0,
        error_count=metrics.error_count,
        artifact_paths=(artifact_path,),
        task_outcome_count=metrics.outcome_count,
        task_success_rate=metrics.task_success_rate,
        task_tool_accuracy=metrics.tool_accuracy,
        task_retry_rate=metrics.retry_rate,
    )


def _summary_from_task_metrics(
    model_name: str,
    metrics: TaskBenchmarkMetrics,
) -> ModelQualitySummary:
    return ModelQualitySummary(
        model_name=model_name,
        mean_benchmark_score=0.0,
        minimum_benchmark_score=0.0,
        excellent_rate=0.0,
        case_count=0,
        repeat_count=0,
        all_excellent_run_rate=1.0,
        error_count=metrics.error_count,
        artifact_paths=(),
        task_outcome_count=metrics.outcome_count,
        task_success_rate=metrics.task_success_rate,
        task_tool_accuracy=metrics.tool_accuracy,
        task_retry_rate=metrics.retry_rate,
    )


def _combine_summaries(
    model_name: str,
    summaries: list[ModelQualitySummary],
) -> ModelQualitySummary:
    benchmark_summaries = [summary for summary in summaries if summary.case_count > 0]
    task_summaries = [summary for summary in summaries if summary.task_outcome_count > 0]
    case_count = sum(summary.case_count for summary in benchmark_summaries)
    repeat_count = sum(summary.repeat_count for summary in benchmark_summaries)
    task_outcome_count = sum(summary.task_outcome_count for summary in task_summaries)
    return ModelQualitySummary(
        model_name=model_name,
        mean_benchmark_score=(
            sum(summary.mean_benchmark_score * summary.case_count for summary in benchmark_summaries) / case_count
            if case_count
            else 0.0
        ),
        minimum_benchmark_score=(
            min(summary.minimum_benchmark_score for summary in benchmark_summaries) if benchmark_summaries else 0.0
        ),
        excellent_rate=(
            sum(summary.excellent_rate * summary.case_count for summary in benchmark_summaries) / case_count
            if case_count
            else 0.0
        ),
        case_count=case_count,
        repeat_count=repeat_count,
        all_excellent_run_rate=(
            sum(summary.all_excellent_run_rate * summary.repeat_count for summary in benchmark_summaries) / repeat_count
            if repeat_count
            else 1.0
        ),
        error_count=sum(summary.error_count for summary in summaries),
        artifact_paths=tuple(path for summary in summaries for path in summary.artifact_paths),
        task_outcome_count=task_outcome_count,
        task_success_rate=(
            sum(
                summary.task_success_rate * summary.task_outcome_count
                for summary in task_summaries
                if summary.task_success_rate is not None
            )
            / task_outcome_count
            if task_outcome_count
            else None
        ),
        task_tool_accuracy=(
            sum(
                summary.task_tool_accuracy * summary.task_outcome_count
                for summary in task_summaries
                if summary.task_tool_accuracy is not None
            )
            / task_outcome_count
            if task_outcome_count
            else None
        ),
        task_retry_rate=(
            sum(
                summary.task_retry_rate * summary.task_outcome_count
                for summary in task_summaries
                if summary.task_retry_rate is not None
            )
            / task_outcome_count
            if task_outcome_count
            else None
        ),
    )
