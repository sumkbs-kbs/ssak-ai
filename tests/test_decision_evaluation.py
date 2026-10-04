from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport, DecisionEvaluationRequest


def _prediction(case_id: str, probabilities: tuple[float, ...], expected_key: str | None = "a") -> str:
    return json.dumps(
        {
            "case_id": case_id,
            "status": "prediction",
            "options": ["a", "b"],
            "probabilities": probabilities,
            "expected_key": expected_key,
        }
    )


def _request(cases: tuple[str, ...], risk_budget: float = 0.05) -> DecisionEvaluationRequest:
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

    return DecisionEvaluationRequest.model_validate_json(
        '{"cases":[' + ",".join(cases) + '],"risk_budget":' + str(risk_budget) + "}"
    )


def _report(cases: tuple[str, ...], risk_budget: float = 0.05) -> DecisionEvaluationReport:
    from antigravity_k.engine.decision_evaluation import evaluate_decisions

    return evaluate_decisions(_request(cases, risk_budget))


def test_metrics_when_two_labeled_cases_have_known_probabilities() -> None:
    # Given: one correct 0.8 prediction and one incorrect 0.6 prediction.
    cases = (_prediction("correct", (0.8, 0.2)), _prediction("wrong", (0.4, 0.6)))
    # When
    report = _report(cases)
    # Then: Brier sums option errors; all four metrics use the same two rows.
    assert report.counts.scored == 2
    assert report.metrics.accuracy == pytest.approx(0.5)
    assert report.metrics.ece == pytest.approx(0.4)
    assert report.metrics.brier == pytest.approx(0.4)
    assert report.metrics.nll == pytest.approx(-(math.log(0.8) + math.log(0.4)) / 2)


def test_counts_when_errors_unlabeled_missing_truth_and_invalid_sums_mix() -> None:
    # Given
    cases = (
        _prediction("scored", (0.8, 0.2)),
        _prediction("unlabeled", (0.8, 0.2), None),
        _prediction("missing", (0.8, 0.2), "outside"),
        _prediction("invalid", (0.5, 0.4)),
        '{"case_id":"error","status":"error","error_code":"timeout"}',
    )
    # When
    report = _report(cases)
    # Then
    assert report.counts.model_dump() == {
        "total": 5,
        "predictions": 4,
        "errors": 1,
        "strict_valid": 3,
        "lenient_valid": 3,
        "invalid_sum": 1,
        "scored": 1,
        "unlabeled": 1,
        "missing_expected_label": 1,
        "underdetermined": 0,
        "tied_predictions": 0,
    }
    assert report.metrics.accuracy == 1
    assert report.metrics.ece == pytest.approx(0.2)
    assert report.metrics.brier == pytest.approx(0.08)
    assert report.metrics.nll == pytest.approx(-math.log(0.8))
    assert report.metrics.strict_valid_rate == 0.75
    assert report.metrics.error_rate == 0.2


def test_metrics_when_no_cases_return_null_instead_of_success() -> None:
    # Given / When
    report = _report(())
    # Then
    assert report.counts.total == 0
    metrics = report.metrics
    assert (
        metrics.accuracy,
        metrics.ece,
        metrics.brier,
        metrics.nll,
        metrics.strict_valid_rate,
        metrics.lenient_valid_rate,
        metrics.error_rate,
    ) == (None,) * 7
    assert report.selective_coverage.coverage is None
    assert report.selective_coverage.selected_count == 0
    assert len(report.ece_bins) == 15
    assert all(bucket.count == 0 and bucket.accuracy is None for bucket in report.ece_bins)


def test_ambiguity_when_truth_is_underdetermined_stays_out_of_scoring() -> None:
    # Given
    case = _prediction("ambiguous", (0.95, 0.05), None).replace('"expected_key": null', '"underdetermined": true')
    # When
    report = _report((case,))
    # Then
    assert report.counts.unlabeled == report.counts.underdetermined == 1
    assert report.metrics.accuracy is report.metrics.ece is report.metrics.brier is report.metrics.nll is None
    assert report.underdetermined.count == 1
    assert report.underdetermined.mean_max_probability == 0.95
    assert report.underdetermined.high_confidence_rate == 1
    assert report.underdetermined.uniform_deviation == pytest.approx(0.45)


def test_coverage_when_equal_confidences_have_mixed_outcomes_is_order_invariant() -> None:
    # Given: including just the correct member of this tie would falsely satisfy risk 0.
    cases = (_prediction("correct", (0.8, 0.2)), _prediction("wrong", (0.8, 0.2), "b"))
    # When
    reports = (_report(cases, 0), _report(tuple(reversed(cases)), 0))
    # Then
    assert reports[0].selective_coverage == reports[1].selective_coverage
    assert reports[0].selective_coverage.coverage == 0
    assert reports[0].selective_coverage.selected_count == 0
    assert reports[0].selective_coverage.confidence_threshold is None
    assert reports[0].selective_coverage.empirical_risk is None


def test_coverage_when_lower_confidence_rows_recover_the_risk_budget() -> None:
    # Given: the highest-confidence prefix fails, the full prefix meets risk 1/3.
    cases = (
        _prediction("wrong", (0.99, 0.01), "b"),
        _prediction("correct1", (0.9, 0.1)),
        _prediction("correct2", (0.7, 0.3)),
    )
    # When
    report = _report(cases, 1 / 3)
    # Then
    assert report.selective_coverage.selected_count == 3
    assert report.selective_coverage.coverage == 1
    assert report.selective_coverage.empirical_risk == pytest.approx(1 / 3)
    assert report.selective_coverage.confidence_threshold == 0.7


def test_tied_prediction_when_option_order_changes_uses_lexical_key() -> None:
    # Given
    case = _prediction("tie", (0.5, 0.5))
    swapped = case.replace('["a", "b"]', '["b", "a"]')
    # When
    reports = (_report((case,)), _report((swapped,)))
    # Then
    assert reports[0].metrics == reports[1].metrics
    assert reports[0].metrics.accuracy == 1
    assert reports[0].counts.tied_predictions == reports[1].counts.tied_predictions == 1


def test_probability_endpoints_when_truth_has_zero_mass_and_top_confidence_is_one() -> None:
    # Given / When
    report = _report((_prediction("wrong", (0, 1)),))
    # Then
    assert report.metrics.brier == 2
    assert report.metrics.nll == pytest.approx(-math.log(1e-15))
    assert report.metrics.ece == 1
    assert report.ece_bins[-1].count == 1
    assert report.ece_bins[-1].upper_bound == 1


@pytest.mark.parametrize(
    ("probabilities", "strict", "lenient"),
    [((0.5, 0.501), 1, 1), ((0.5, 0.502), 0, 1), ((0.5, 0.52), 0, 1), ((0.5, 0.521), 0, 0)],
)
def test_validity_when_sum_is_on_or_beyond_tolerance(
    probabilities: tuple[float, ...], strict: int, lenient: int
) -> None:
    # Given / When
    report = _report((_prediction("sum", probabilities),))
    # Then
    assert report.counts.strict_valid == strict
    assert report.counts.lenient_valid == lenient
    assert report.counts.invalid_sum == 1 - strict
    assert report.counts.scored == strict


@pytest.mark.parametrize("value", ['"0.8"', "true", "null", "NaN", "Infinity", "-Infinity", "-0.1", "1.1"])
def test_boundary_when_probability_is_not_finite_numeric_in_range(value: str) -> None:
    # Given
    case = _prediction("bad", (0.8, 0.2)).replace("0.8", value)
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request((case,))


@pytest.mark.parametrize(
    "replacement",
    ['"risk_budget":true', '"risk_budget":"0.05"', '"risk_budget":NaN', '"risk_budget":-0.1', '"risk_budget":1.1'],
)
def test_boundary_when_risk_budget_is_invalid(replacement: str) -> None:
    # Given
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

    raw = '{"cases":[],' + replacement + "}"
    # When / Then
    with pytest.raises(ValidationError):
        _ = DecisionEvaluationRequest.model_validate_json(raw)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('["a", "b"]', '["a", "a"]'),
        ('["a", "b"]', '["a", " "]'),
        ('["a", "b"]', '["a"]'),
        ("[0.8, 0.2]", "[0.8]"),
        ('"case_id": "bad"', '"case_id": " "'),
        ('"case_id": "bad"', '"case_id": 1'),
        ('"expected_key": "a"', '"expected_key": "a", "underdetermined": true'),
        ('"expected_key": "a"', '"expected_key": "a", "underdetermined": 0'),
        ('"expected_key": "a"', '"expected_key": "a", "prompt": "private"'),
    ],
)
def test_boundary_when_prediction_shape_is_invalid(old: str, new: str) -> None:
    # Given
    case = _prediction("bad", (0.8, 0.2)).replace(old, new)
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request((case,))


def test_boundary_when_case_ids_repeat_rejects_the_request() -> None:
    # Given
    case = _prediction("duplicate", (0.8, 0.2))
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request((case, case))


def test_provenance_when_canonical_input_is_reformatted_has_stable_digest() -> None:
    # Given
    from antigravity_k.engine.decision_evaluation import evaluate_decisions
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

    request = _request((_prediction("known", (0.8, 0.2)),))
    canonical = json.dumps(
        request.model_dump(mode="json", exclude={"cases": {0: {"tags"}}}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # When
    report = evaluate_decisions(DecisionEvaluationRequest.model_validate_json(request.model_dump_json(indent=2)))
    # Then
    assert report.input_sha256 == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert report.calibration_status == "unverified"
    assert report.score_source == "provided_probabilities"


def test_input_when_parsed_is_deeply_immutable() -> None:
    # Given
    request = _request((_prediction("known", (0.8, 0.2)),))
    # When / Then
    with pytest.raises(ValidationError):
        request.risk_budget = 0.5
    assert isinstance(request.cases, tuple)
    prediction = request.cases[0]
    assert prediction.status == "prediction"
    assert isinstance(prediction.options, tuple)


def test_ece_when_rows_share_one_bin_compares_bin_accuracy() -> None:
    # Given / When
    report = _report((_prediction("correct", (0.6, 0.4)), _prediction("wrong", (0.6, 0.4), "b")))
    # Then
    assert report.metrics.ece == pytest.approx(0.1)
    assert report.ece_bins[9].count == 2
    assert report.ece_bins[9].accuracy == 0.5


def test_brier_when_three_options_use_multiclass_sum() -> None:
    # Given
    raw = '{"case_id":"three","status":"prediction","options":["a","b","c"],"probabilities":[0.1,0.2,0.7],"expected_key":"b"}'
    # When
    report = _report((raw,))
    # Then
    assert report.metrics.brier == pytest.approx(1.14)
    assert report.metrics.nll == pytest.approx(-math.log(0.2))


def test_coverage_when_low_confidence_errors_exceed_budget_preserves_largest_valid_prefix() -> None:
    # Given / When
    report = _report((_prediction("correct", (0.99, 0.01)), _prediction("wrong", (0.8, 0.2), "b")), 0)
    # Then
    assert report.selective_coverage.selected_count == 1
    assert report.selective_coverage.coverage == 0.5
    assert report.selective_coverage.confidence_threshold == 0.99
    assert report.selective_coverage.empirical_risk == 0


def test_invalid_ambiguity_when_probability_sum_is_zero_is_never_repaired() -> None:
    # Given
    case = _prediction("zero", (0, 0), None).replace('"expected_key": null', '"underdetermined": true')
    # When
    report = _report((case,))
    # Then
    assert report.counts.invalid_sum == 1
    assert report.counts.unlabeled == report.counts.underdetermined == report.counts.tied_predictions == 0
    assert report.underdetermined.mean_max_probability is None
    assert report.metrics.accuracy is None


@pytest.mark.parametrize(
    "raw",
    [
        '{"case_id":"error","status":"error","error_code":"unknown"}',
        '{"case_id":"error","status":"error","error_code":"timeout","message":"secret"}',
        '{"case_id":"missing","status":"unknown"}',
        '{"case_id":"missing","options":["a","b"],"probabilities":[0.8,0.2]}',
    ],
)
def test_boundary_when_case_variant_is_unknown_or_leaks_extra_fields(raw: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        _ = _request((raw,))


def test_boundary_when_case_count_exceeds_limit_rejects_request() -> None:
    # Given
    cases = tuple(_prediction(str(index), (0.8, 0.2)) for index in range(1001))
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request(cases)


def test_boundary_when_option_count_exceeds_limit_rejects_request() -> None:
    # Given
    raw = json.dumps(
        {
            "case_id": "large",
            "status": "prediction",
            "options": [str(index) for index in range(65)],
            "probabilities": [1 / 65] * 65,
        }
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request((raw,))


@pytest.mark.parametrize(
    "raw",
    ['{"cases":[],"model_id":" "}', '{"cases":[],"dataset_id":1}', '{"cases":[],"dataset_id":"' + "a" * 129 + '"}'],
)
def test_boundary_when_metadata_is_blank_coerced_or_oversized(raw: str) -> None:
    # Given
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

    # When / Then
    with pytest.raises(ValidationError):
        _ = DecisionEvaluationRequest.model_validate_json(raw)
