from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport, DecisionEvaluationRequest


def _prediction(
    case_id: str,
    probabilities: tuple[float, float] = (0.8, 0.2),
    expected_key: str | None = "a",
    tags: tuple[str, ...] | None = None,
    *,
    underdetermined: bool = False,
) -> str:
    fields: dict[str, str | bool | None | tuple[str, ...] | tuple[float, float]] = {
        "case_id": case_id,
        "status": "prediction",
        "options": ("a", "b"),
        "probabilities": probabilities,
        "expected_key": expected_key,
        "underdetermined": underdetermined,
    }
    if tags is not None:
        fields["tags"] = tags
    return json.dumps(fields)


def _error(case_id: str, tags: tuple[str, ...]) -> str:
    return json.dumps({"case_id": case_id, "status": "error", "error_code": "timeout", "tags": tags})


def _request(cases: tuple[str, ...], risk_budget: float = 0.05) -> DecisionEvaluationRequest:
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

    return DecisionEvaluationRequest.model_validate_json(
        '{"cases":[' + ",".join(cases) + '],"risk_budget":' + str(risk_budget) + "}"
    )


def _report(cases: tuple[str, ...], risk_budget: float = 0.05) -> DecisionEvaluationReport:
    from antigravity_k.engine.decision_evaluation import evaluate_decisions

    return evaluate_decisions(_request(cases, risk_budget))


@pytest.mark.parametrize(
    ("outcomes", "lower", "upper"),
    [
        ((), None, None),
        ((True,), 0.20654329147389294, 1.0),
        ((False,), 0.0, 0.7934567085261071),
        ((True, False), 0.09452865480086614, 0.9054713451991339),
    ],
)
def test_accuracy_interval_when_scored_outcomes_have_known_values(
    outcomes: tuple[bool, ...], lower: float | None, upper: float | None
) -> None:
    # Given: cases have independent known success counts.
    cases = tuple(
        _prediction(str(index), expected_key="a" if correct else "b") for index, correct in enumerate(outcomes)
    )
    # When
    interval = _report(cases).metrics.accuracy_interval
    # Then: an empty sample has no interval; scored samples use fixed Wilson metadata.
    if not outcomes:
        assert interval is None
    else:
        assert interval is not None
        assert interval.model_dump() == {
            "method": "wilson",
            "confidence_level": 0.95,
            "z": 1.96,
            "n": len(outcomes),
            "successes": sum(outcomes),
            "lower": pytest.approx(lower),
            "upper": pytest.approx(upper),
        }


@pytest.mark.parametrize(("successes", "n"), [(0, 3), (3, 3), (0, 11), (6, 6), (50, 100), (1, 1000), (999, 1000)])
def test_accuracy_interval_when_sample_sizes_vary_contains_observed_proportion(successes: int, n: int) -> None:
    # Given
    cases = tuple(_prediction(str(index), expected_key="a" if index < successes else "b") for index in range(n))
    # When
    interval = _report(cases).metrics.accuracy_interval
    # Then
    assert interval is not None
    assert interval.n == n
    assert interval.successes == successes
    assert 0 <= interval.lower <= successes / n <= interval.upper <= 1


def test_tag_summary_when_exclusions_and_ties_mix_matches_aggregate() -> None:
    # Given: every case has the universal tag, including excluded rows.
    cases = (
        _prediction("correct", tags=("all",)),
        _prediction("wrong-tie", (0.5, 0.5), "b", ("all",)),
        _prediction("unlabeled", expected_key=None, tags=("all",)),
        _prediction("missing", expected_key="outside", tags=("all",)),
        _prediction("lenient-only", (0.5, 0.502), tags=("all",)),
        _prediction("ambiguous", (0.95, 0.05), None, ("all",), underdetermined=True),
        _error("error", ("all",)),
    )
    # When
    report = _report(cases, 0)
    # Then: one shared summary retains the scored denominator and complete confidence ties.
    group = report.tag_diagnostics.groups[0]
    assert group.tag == "all"
    assert (group.counts, group.metrics, group.ece_bins, group.selective_coverage, group.underdetermined) == (
        report.counts,
        report.metrics,
        report.ece_bins,
        report.selective_coverage,
        report.underdetermined,
    )
    assert group.metrics.accuracy_interval is not None
    assert group.metrics.accuracy_interval.n == 2
    assert group.metrics.accuracy_interval.successes == 1
    assert group.selective_coverage.selected_count == 1
    assert group.counts.tied_predictions == 1
    assert (group.counts.strict_valid, group.counts.lenient_valid, group.counts.unlabeled) == (5, 6, 2)


@pytest.mark.parametrize("reverse", [False, True])
def test_tag_groups_when_cases_overlap_count_unique_members_per_group(*, reverse: bool) -> None:
    # Given
    cases = (_prediction("a", tags=("shared", "left")), _prediction("b", expected_key="b", tags=("shared", "right")))
    if reverse:
        cases = tuple(reversed(cases))
    # When
    report = _report(cases, 0)
    # Then: overlapping counts are individual views, while aggregate still has two cases.
    diagnostics = report.tag_diagnostics
    assert diagnostics.total_tags == 3
    assert [(group.tag, group.counts.total) for group in diagnostics.groups] == [
        ("shared", 2),
        ("left", 1),
        ("right", 1),
    ]
    assert report.counts.total == report.counts.scored == 2
    shared, left, right = diagnostics.groups
    assert shared.selective_coverage.selected_count == 0
    assert (left.metrics.accuracy, right.metrics.accuracy) == (1, 0)
    assert left.metrics.accuracy_interval is not None
    assert right.metrics.accuracy_interval is not None
    assert (left.metrics.accuracy_interval.successes, right.metrics.accuracy_interval.successes) == (1, 0)
    assert left.metrics.accuracy_interval.n == right.metrics.accuracy_interval.n == 1


def test_tag_groups_when_more_than_limit_exist_rank_frequency_then_lexically() -> None:
    # Given: zzz is most frequent, while the remaining 26 tags tie in frequency.
    cases = (
        *(_error(str(index), (f"t{index:02}",)) for index in range(26)),
        _error("frequent-a", ("zzz",)),
        _error("frequent-b", ("zzz",)),
    )
    # When
    diagnostics = _report(cases).tag_diagnostics
    # Then
    assert (diagnostics.total_tags, diagnostics.omitted_tags, diagnostics.tag_limit) == (27, 2, 25)
    assert [group.tag for group in diagnostics.groups] == ["zzz", *(f"t{index:02}" for index in range(24))]


def test_tag_groups_when_single_correct_and_error_only_tags_exist_keep_low_counts() -> None:
    # Given
    cases = (_prediction("correct", tags=("small",)), _error("error", ("failed",)))
    # When
    diagnostics = _report(cases).tag_diagnostics
    # Then
    failed, small = diagnostics.groups
    assert failed.counts.errors == failed.counts.total == 1
    assert failed.metrics.accuracy_interval is None
    assert failed.selective_coverage.coverage is None
    assert len(failed.ece_bins) == 15
    assert small.metrics.accuracy_interval is not None
    assert small.metrics.accuracy_interval.n == 1


@pytest.mark.parametrize("status", ["prediction", "error"])
@pytest.mark.parametrize(
    "raw_tags",
    [
        '["duplicate","duplicate"]',
        '[""]',
        '[" "]',
        "[1]",
        "[true]",
        "null",
        json.dumps(["x" * 129]),
        json.dumps([str(index) for index in range(17)]),
    ],
)
def test_tag_boundary_when_tags_are_invalid_rejects_cases(status: str, raw_tags: str) -> None:
    # Given
    raw = _prediction("bad") if status == "prediction" else _error("bad", ())
    raw = raw.removesuffix("}") + ',"tags":' + raw_tags + "}"
    # When / Then
    with pytest.raises(ValidationError):
        _ = _request((raw,))


def test_tags_when_at_limit_are_immutable_and_leave_aggregate_metrics_unchanged() -> None:
    # Given
    tags = tuple(str(index) for index in range(16))
    request = _request((_prediction("known", tags=tags),))
    # When
    report = _report((_prediction("known", tags=tags),))
    # Then
    assert request.cases[0].tags == tags
    assert report.metrics == _report((_prediction("known"),)).metrics
    with pytest.raises(ValidationError):
        request.cases[0].tags = ()


@pytest.mark.parametrize("tags", [None, ()])
def test_digest_when_tags_are_absent_or_empty_matches_prior_canonical_input(tags: tuple[str, ...] | None) -> None:
    # Given: this literal is the pre-tags parsed-input canonical representation.
    canonical = (
        '{"cases":[{"case_id":"known","expected_key":"a","options":["a","b"],'
        '"probabilities":[0.8,0.2],"status":"prediction","underdetermined":false}],'
        '"dataset_id":null,"model_id":null,"risk_budget":0.05}'
    )
    # When
    report = _report((_prediction("known", tags=tags),))
    # Then
    assert report.input_sha256 == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_digest_when_nonempty_tags_are_supplied_includes_metadata() -> None:
    # Given
    tagged = _request((_prediction("known", tags=("category",)),))
    canonical = json.dumps(tagged.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # When
    report = _report((_prediction("known", tags=("category",)),))
    # Then
    assert report.input_sha256 == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert report.input_sha256 != _report((_prediction("known"),)).input_sha256


def test_report_parser_when_additive_fields_are_missing_supplies_safe_defaults() -> None:
    # Given
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    payload = _report((_prediction("known"),)).model_dump_json(
        exclude={"tag_diagnostics": True, "metrics": {"accuracy_interval"}}
    )
    # When
    parsed = DecisionEvaluationReport.model_validate_json(payload)
    # Then
    assert parsed.metrics.accuracy_interval is None
    assert parsed.tag_diagnostics.model_dump() == {"total_tags": 0, "omitted_tags": 0, "tag_limit": 25, "groups": ()}
