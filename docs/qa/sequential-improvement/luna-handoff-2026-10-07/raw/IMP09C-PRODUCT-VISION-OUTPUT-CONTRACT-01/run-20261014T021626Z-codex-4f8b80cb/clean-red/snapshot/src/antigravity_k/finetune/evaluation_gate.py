from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from math import sqrt
from pathlib import Path
from statistics import fmean, stdev
from typing import ClassVar, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from antigravity_k.finetune.evaluation import (
    EvaluationCase,
    EvaluationError,
    EvaluationPair,
    evaluation_pair_sha256,
)

_DEFAULT_PROMOTION_DATASET_SHA256 = "cf202bd9360381270525d9801dcbb4fa1a3f6ec6491ccf6bfd57776dbe2acbde"
_T_CRITICAL_95: Final[tuple[float, ...]] = (
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


class EvaluationCategory(StrEnum):
    LONG_HORIZON = "long_horizon"
    VERIFIED_CODE = "verified_code"
    TOOL_RECOVERY = "tool_recovery"
    KOREAN_REASONING = "korean_reasoning"


class PromotionGatePolicy(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    approved_dataset_sha256: str = Field(
        default=_DEFAULT_PROMOTION_DATASET_SHA256,
        pattern=r"^[0-9a-f]{64}$",
    )
    required_categories: tuple[EvaluationCategory, ...] = tuple(EvaluationCategory)
    minimum_category_score: float = Field(default=0.5, ge=0.0, le=1.0)
    maximum_category_regression: float = Field(default=0.0, ge=0.0, le=1.0)
    minimum_overall_improvement: float = Field(default=0.01, ge=0.0, le=1.0)
    minimum_case_count: int = Field(default=4, ge=2)


class CategoryComparison(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    category: EvaluationCategory
    case_ids: tuple[str, ...] = Field(min_length=1)
    base_score: float = Field(ge=0.0, le=1.0)
    tuned_score: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=-1.0, le=1.0)
    passed: bool


class PromotionBenchmarkResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    quality_score: float = Field(ge=0.0, le=1.0)
    benchmark_score: float = Field(ge=0.0, le=1.0)
    quality_grade: str = Field(min_length=1)
    error: str = ""


class PairedStatisticalEvidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    confidence_level: float = Field(default=0.95, ge=0.95, le=0.95)
    observation_count: int = Field(ge=1)
    paired_deltas: tuple[float, ...] = Field(min_length=1)
    mean_delta: float = Field(ge=-1.0, le=1.0)
    standard_error: float = Field(ge=0.0)
    confidence_lower_bound: float = Field(ge=-1.0, le=1.0)
    confidence_upper_bound: float = Field(ge=-1.0, le=1.0)


class PromotionDecision(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[3] = 3
    artifact_type: Literal["promotion_decision"] = "promotion_decision"
    model: str = Field(min_length=1)
    evaluated_model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: PromotionGatePolicy
    categories: tuple[CategoryComparison, ...]
    missing_categories: tuple[EvaluationCategory, ...]
    base_score: float = Field(ge=0.0, le=1.0)
    tuned_score: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=-1.0, le=1.0)
    statistical_evidence: PairedStatisticalEvidence
    eligible: bool
    reasons: tuple[str, ...]
    results: tuple[PromotionBenchmarkResult, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        observed_categories = tuple(item.category for item in self.categories)
        missing = tuple(category for category in self.policy.required_categories if category not in observed_categories)
        if missing != self.missing_categories:
            raise ValueError("Promotion decision missing categories are inconsistent.")
        if self.delta != _delta(self.tuned_score, self.base_score):
            raise ValueError("Promotion decision overall delta is inconsistent.")
        if self.statistical_evidence != _paired_statistical_evidence(self.statistical_evidence.paired_deltas):
            raise ValueError("Promotion decision statistical evidence is inconsistent.")
        if self.statistical_evidence.mean_delta != self.delta:
            raise ValueError("Promotion decision paired mean delta is inconsistent.")
        for comparison in self.categories:
            expected = (
                comparison.tuned_score >= self.policy.minimum_category_score
                and comparison.delta >= -self.policy.maximum_category_regression
                and comparison.delta == _delta(comparison.tuned_score, comparison.base_score)
            )
            if comparison.passed is not expected:
                raise ValueError("Promotion decision category verdict is inconsistent.")
        expected_eligible = (
            self.dataset_sha256 == self.policy.approved_dataset_sha256
            and not missing
            and all(item.passed for item in self.categories)
            and self.delta >= self.policy.minimum_overall_improvement
            and self.statistical_evidence.observation_count >= self.policy.minimum_case_count
            and self.statistical_evidence.confidence_lower_bound >= self.policy.minimum_overall_improvement
        )
        if self.eligible is not expected_eligible or self.eligible is bool(self.reasons):
            raise ValueError("Promotion decision eligibility is inconsistent.")
        if tuple(item.case_id for item in self.results) != tuple(item.value for item in observed_categories):
            raise ValueError("Promotion decision calibration cases are inconsistent.")
        for comparison, result in zip(self.categories, self.results, strict=True):
            expected_grade = "excellent" if self.eligible else "fail"
            expected_error = "" if self.eligible else "; ".join(self.reasons)
            if (
                result.quality_score != comparison.tuned_score
                or result.benchmark_score != comparison.tuned_score
                or result.quality_grade != expected_grade
                or result.error != expected_error
            ):
                raise ValueError("Promotion decision calibration result is inconsistent.")
        return self


_pair_adapter: TypeAdapter[EvaluationPair] = TypeAdapter(EvaluationPair)


def build_promotion_decision(
    pair: EvaluationPair,
    *,
    policy: PromotionGatePolicy | None = None,
    routing_model_name: str | None = None,
) -> PromotionDecision:
    active_policy = policy or PromotionGatePolicy()
    pair_sha256 = evaluation_pair_sha256(pair)
    _validate_same_conditions(pair)
    if pair.tuned.recipe_sha256 is None:
        raise EvaluationError("Tuned evaluation recipe provenance is required.")
    cases = _load_cases(pair)
    category_by_id = {case.id: _parse_category(case) for case in cases}
    comparisons: list[CategoryComparison] = []
    missing: list[EvaluationCategory] = []
    reasons: list[str] = []
    if pair.dataset.sha256 != active_policy.approved_dataset_sha256:
        reasons.append("dataset digest is not approved by promotion policy")

    for category in active_policy.required_categories:
        indices = tuple(
            index for index, case_id in enumerate(pair.dataset.case_ids) if category_by_id[case_id] is category
        )
        if not indices:
            missing.append(category)
            continue
        base_score = _mean(tuple(pair.base.scores[index] for index in indices))
        tuned_score = _mean(tuple(pair.tuned.scores[index] for index in indices))
        delta = _delta(tuned_score, base_score)
        score_passed = tuned_score >= active_policy.minimum_category_score
        regression_passed = delta >= -active_policy.maximum_category_regression
        if not score_passed:
            reasons.append(f"category score below minimum: {category.value}")
        if not regression_passed:
            reasons.append(f"category regression: {category.value}")
        comparisons.append(
            CategoryComparison(
                category=category,
                case_ids=tuple(pair.dataset.case_ids[index] for index in indices),
                base_score=base_score,
                tuned_score=tuned_score,
                delta=delta,
                passed=score_passed and regression_passed,
            ),
        )

    if missing:
        reasons.insert(0, f"missing required categories: {','.join(category.value for category in missing)}")
    base_score = _mean(pair.base.scores)
    tuned_score = _mean(pair.tuned.scores)
    delta = _delta(tuned_score, base_score)
    statistical_evidence = _paired_statistical_evidence(
        tuple(_delta(tuned, base) for base, tuned in zip(pair.base.scores, pair.tuned.scores, strict=True)),
    )
    if delta < active_policy.minimum_overall_improvement:
        reasons.append("overall improvement below minimum")
    if statistical_evidence.observation_count < active_policy.minimum_case_count:
        reasons.append(
            f"insufficient evaluation cases: {statistical_evidence.observation_count} < {active_policy.minimum_case_count}",
        )
    if statistical_evidence.confidence_lower_bound < active_policy.minimum_overall_improvement:
        reasons.append("paired improvement confidence lower bound below minimum")
    return PromotionDecision(
        model=routing_model_name or pair.tuned.model,
        evaluated_model=pair.tuned.model,
        model_revision=pair.tuned.model_revision,
        recipe_sha256=pair.tuned.recipe_sha256,
        evaluation_pair_sha256=pair_sha256,
        evaluation_sha256=evaluation_result_sha256(pair),
        dataset_sha256=pair.dataset.sha256,
        policy=active_policy,
        categories=tuple(comparisons),
        missing_categories=tuple(missing),
        base_score=base_score,
        tuned_score=tuned_score,
        delta=delta,
        statistical_evidence=statistical_evidence,
        eligible=not reasons,
        reasons=tuple(reasons),
        results=tuple(
            PromotionBenchmarkResult(
                case_id=comparison.category.value,
                quality_score=comparison.tuned_score,
                benchmark_score=comparison.tuned_score,
                quality_grade="excellent" if not reasons else "fail",
                error="" if not reasons else "; ".join(reasons),
            )
            for comparison in comparisons
        ),
    )


def load_promotion_decision(
    evaluation_path: Path,
    *,
    policy: PromotionGatePolicy | None = None,
    routing_model_name: str | None = None,
) -> PromotionDecision:
    try:
        pair = _pair_adapter.validate_json(evaluation_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvaluationError(f"Evaluation result is unavailable at {evaluation_path}.") from error
    except ValueError as error:
        raise EvaluationError(f"Invalid evaluation result at {evaluation_path}: {error}") from error
    return build_promotion_decision(pair, policy=policy, routing_model_name=routing_model_name)


def load_promotion_decision_artifact(path: Path) -> PromotionDecision:
    try:
        return PromotionDecision.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvaluationError(f"Promotion decision is unavailable at {path}.") from error
    except ValueError as error:
        raise EvaluationError(f"Invalid promotion decision at {path}: {error}") from error


def evaluation_result_sha256(pair: EvaluationPair) -> str:
    canonical = json.dumps(
        pair.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def promotion_decision_sha256(decision: PromotionDecision) -> str:
    canonical = json.dumps(
        decision.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_cases(pair: EvaluationPair) -> tuple[EvaluationCase, ...]:
    try:
        cases = tuple(
            EvaluationCase.model_validate_json(line)
            for line in pair.dataset.path.read_text(encoding="utf-8").splitlines()
            if line
        )
    except (OSError, ValueError) as error:
        raise EvaluationError("Frozen evaluation cases are invalid or unavailable.") from error
    if tuple(case.id for case in cases) != pair.dataset.case_ids:
        raise EvaluationError("Evaluation case IDs must match the frozen dataset order.")
    return cases


def _parse_category(case: EvaluationCase) -> EvaluationCategory:
    try:
        return EvaluationCategory(case.category)
    except ValueError as error:
        raise EvaluationError(f"Unsupported held-out category: {case.category}.") from error


def _validate_same_conditions(pair: EvaluationPair) -> None:
    if pair.base.model != pair.tuned.model:
        raise EvaluationError("Base and tuned evaluations must use the same model.")
    if pair.base.model_revision != pair.tuned.model_revision:
        raise EvaluationError("Base and tuned evaluations must use the same model revision.")
    if pair.base.environment != pair.tuned.environment:
        raise EvaluationError("Base and tuned evaluations must use the same environment.")


def _mean(scores: tuple[float, ...]) -> float:
    return round(fmean(scores), 12)


def _delta(tuned_score: float, base_score: float) -> float:
    return round(tuned_score - base_score, 12)


def _paired_statistical_evidence(paired_deltas: tuple[float, ...]) -> PairedStatisticalEvidence:
    observation_count = len(paired_deltas)
    mean_delta = _mean(paired_deltas)
    standard_error = 0.0 if observation_count == 1 else stdev(paired_deltas) / sqrt(observation_count)
    degrees_of_freedom = observation_count - 1
    critical_value = _T_CRITICAL_95[degrees_of_freedom - 1] if degrees_of_freedom <= 30 else 1.96
    margin = critical_value * standard_error
    return PairedStatisticalEvidence(
        observation_count=observation_count,
        paired_deltas=paired_deltas,
        mean_delta=mean_delta,
        standard_error=round(standard_error, 12),
        confidence_lower_bound=round(max(-1.0, mean_delta - margin), 12),
        confidence_upper_bound=round(min(1.0, mean_delta + margin), 12),
    )
