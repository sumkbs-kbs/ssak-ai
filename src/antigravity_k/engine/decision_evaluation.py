from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Final, assert_never

from antigravity_k.engine.decision_evaluation_models import (
    AccuracyInterval,
    DecisionCase,
    DecisionError,
    DecisionEvaluationCounts,
    DecisionEvaluationMetrics,
    DecisionEvaluationReport,
    DecisionEvaluationRequest,
    DecisionEvaluationSummary,
    DecisionPrediction,
    DecisionTagGroup,
    ReliabilityBin,
    SelectiveCoverage,
    TagDiagnostics,
    UnderdeterminedDiagnostics,
)

STRICT_SUM_TOLERANCE: Final = 1e-3
LENIENT_SUM_TOLERANCE: Final = 2e-2
ECE_BIN_COUNT: Final = 15
NLL_PROBABILITY_FLOOR: Final = 1e-15
HIGH_CONFIDENCE_THRESHOLD: Final = 0.9
TAG_LIMIT: Final = 25
WILSON_Z: Final = 1.96


@dataclass(frozen=True, slots=True)
class _ScoredPrediction:
    confidence: float
    correct: bool
    brier: float
    nll: float


def _valid_sum(case: DecisionPrediction, tolerance: float) -> bool:
    return 1 - tolerance <= math.fsum(case.probabilities) <= 1 + tolerance


def _reliability_bins(scored: Sequence[_ScoredPrediction]) -> tuple[ReliabilityBin, ...]:
    grouped: list[list[_ScoredPrediction]] = [[] for _ in range(ECE_BIN_COUNT)]
    for row in scored:
        grouped[min(int(row.confidence * ECE_BIN_COUNT), ECE_BIN_COUNT - 1)].append(row)
    return tuple(
        ReliabilityBin(
            lower_bound=index / ECE_BIN_COUNT,
            upper_bound=(index + 1) / ECE_BIN_COUNT,
            count=len(rows),
            mean_confidence=math.fsum(row.confidence for row in rows) / len(rows) if rows else None,
            accuracy=sum(row.correct for row in rows) / len(rows) if rows else None,
        )
        for index, rows in enumerate(grouped)
    )


def _selective_coverage(scored: Sequence[_ScoredPrediction], risk_budget: float) -> SelectiveCoverage:
    selected = SelectiveCoverage(
        risk_budget=risk_budget,
        selected_count=0,
        confidence_threshold=None,
        coverage=0.0 if scored else None,
        empirical_risk=None,
    )
    prefix_count = prefix_errors = 0
    ordered = sorted(scored, key=lambda row: row.confidence, reverse=True)
    for confidence, group in groupby(ordered, key=lambda row: row.confidence):
        rows = tuple(group)
        prefix_count += len(rows)
        prefix_errors += sum(not row.correct for row in rows)
        risk = prefix_errors / prefix_count
        if risk <= risk_budget:
            selected = SelectiveCoverage(
                risk_budget=risk_budget,
                selected_count=prefix_count,
                confidence_threshold=confidence,
                coverage=prefix_count / len(scored),
                empirical_risk=risk,
            )
    return selected


def _accuracy_interval(successes: int, n: int) -> AccuracyInterval | None:
    if not n:
        return None
    proportion = successes / n
    z_squared = WILSON_Z * WILSON_Z
    denominator = 1 + z_squared / n
    center = (proportion + z_squared / (2 * n)) / denominator
    radius = WILSON_Z * math.sqrt(proportion * (1 - proportion) / n + z_squared / (4 * n * n)) / denominator
    return AccuracyInterval(
        n=n,
        successes=successes,
        lower=max(0.0, min(proportion, center - radius)),
        upper=min(1.0, max(proportion, center + radius)),
    )


def _summarize_decisions(cases: Sequence[DecisionCase], risk_budget: float) -> DecisionEvaluationSummary:
    predictions: list[DecisionPrediction] = []
    valid: list[DecisionPrediction] = []
    ambiguous: list[DecisionPrediction] = []
    scored: list[_ScoredPrediction] = []
    errors = unlabeled = missing_truth = tied = 0
    for case in cases:
        match case:
            case DecisionError():
                errors += 1
            case DecisionPrediction():
                predictions.append(case)
                if not _valid_sum(case, STRICT_SUM_TOLERANCE):
                    continue
                valid.append(case)
                confidence = max(case.probabilities)
                tied += sum(probability == confidence for probability in case.probabilities) > 1
                if case.underdetermined:
                    ambiguous.append(case)
                if case.expected_key is None:
                    unlabeled += 1
                    continue
                if case.expected_key not in case.options:
                    missing_truth += 1
                    continue
                winner = min(
                    key
                    for key, probability in zip(case.options, case.probabilities, strict=True)
                    if probability == confidence
                )
                brier = math.fsum(
                    (probability - (key == case.expected_key)) ** 2
                    for key, probability in zip(case.options, case.probabilities, strict=True)
                )
                truth_probability = case.probabilities[case.options.index(case.expected_key)]
                scored.append(
                    _ScoredPrediction(
                        confidence,
                        winner == case.expected_key,
                        brier,
                        -math.log(max(truth_probability, NLL_PROBABILITY_FLOOR)),
                    )
                )
            case _:
                assert_never(case)

    bins = _reliability_bins(scored)
    scored_count = len(scored)
    lenient_count = sum(_valid_sum(case, LENIENT_SUM_TOLERANCE) for case in predictions)
    metrics = DecisionEvaluationMetrics(
        accuracy=sum(row.correct for row in scored) / scored_count if scored_count else None,
        accuracy_interval=_accuracy_interval(sum(row.correct for row in scored), scored_count),
        ece=math.fsum(
            bucket.count * abs(bucket.mean_confidence - bucket.accuracy)
            for bucket in bins
            if bucket.mean_confidence is not None and bucket.accuracy is not None
        )
        / scored_count
        if scored_count
        else None,
        brier=math.fsum(row.brier for row in scored) / scored_count if scored_count else None,
        nll=math.fsum(row.nll for row in scored) / scored_count if scored_count else None,
        strict_valid_rate=len(valid) / len(predictions) if predictions else None,
        lenient_valid_rate=lenient_count / len(predictions) if predictions else None,
        error_rate=errors / len(cases) if cases else None,
    )
    ambiguity = UnderdeterminedDiagnostics(
        count=len(ambiguous),
        mean_max_probability=math.fsum(max(case.probabilities) for case in ambiguous) / len(ambiguous)
        if ambiguous
        else None,
        high_confidence_rate=sum(max(case.probabilities) >= HIGH_CONFIDENCE_THRESHOLD for case in ambiguous)
        / len(ambiguous)
        if ambiguous
        else None,
        uniform_deviation=math.fsum(abs(max(case.probabilities) - 1 / len(case.options)) for case in ambiguous)
        / len(ambiguous)
        if ambiguous
        else None,
    )
    return DecisionEvaluationSummary(
        counts=DecisionEvaluationCounts(
            total=len(cases),
            predictions=len(predictions),
            errors=errors,
            strict_valid=len(valid),
            lenient_valid=lenient_count,
            invalid_sum=len(predictions) - len(valid),
            scored=scored_count,
            unlabeled=unlabeled,
            missing_expected_label=missing_truth,
            underdetermined=len(ambiguous),
            tied_predictions=tied,
        ),
        metrics=metrics,
        ece_bins=bins,
        selective_coverage=_selective_coverage(scored, risk_budget),
        underdetermined=ambiguity,
    )


def evaluate_decisions(request: DecisionEvaluationRequest) -> DecisionEvaluationReport:
    """Measure caller-provided probabilities without certifying calibration or changing runtime policy."""
    summary = _summarize_decisions(request.cases, request.risk_budget)
    tagged_cases: dict[str, list[DecisionCase]] = {}
    for case in request.cases:
        for tag in case.tags:
            tagged_cases.setdefault(tag, []).append(case)
    ranked_tags = sorted(tagged_cases, key=lambda tag: (-len(tagged_cases[tag]), tag))
    groups: list[DecisionTagGroup] = []
    for tag in ranked_tags[:TAG_LIMIT]:
        group = _summarize_decisions(tagged_cases[tag], request.risk_budget)
        groups.append(
            DecisionTagGroup(
                tag=tag,
                counts=group.counts,
                metrics=group.metrics,
                ece_bins=group.ece_bins,
                selective_coverage=group.selective_coverage,
                underdetermined=group.underdetermined,
            )
        )
    empty_tags = {index: {"tags"} for index, case in enumerate(request.cases) if not case.tags}
    canonical_input = json.dumps(
        request.model_dump(mode="json", exclude={"cases": empty_tags}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return DecisionEvaluationReport(
        model_id=request.model_id,
        dataset_id=request.dataset_id,
        input_sha256=hashlib.sha256(canonical_input.encode("utf-8")).hexdigest(),
        counts=summary.counts,
        metrics=summary.metrics,
        ece_bins=summary.ece_bins,
        selective_coverage=summary.selective_coverage,
        underdetermined=summary.underdetermined,
        tag_diagnostics=TagDiagnostics(
            total_tags=len(ranked_tags),
            omitted_tags=max(0, len(ranked_tags) - TAG_LIMIT),
            groups=tuple(groups),
        ),
    )
