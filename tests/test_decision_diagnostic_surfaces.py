from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Literal, assert_never

import pytest
import typer
from pydantic import AliasPath, BaseModel, ConfigDict, Field
from typer.testing import CliRunner

from tests.test_decision_evaluation_surfaces import (
    ENDPOINT,
    PAYLOAD,
    AuthenticatedClient,
    ValidationErrorBody,
)
from tests.test_decision_evaluation_surfaces import (
    api_client as api_client,
)
from tests.test_decision_evaluation_surfaces import (
    cli_app as cli_app,
)

if TYPE_CHECKING:
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

MIXED: Final = json.dumps(
    {
        "cases": [
            {
                "case_id": "right",
                "status": "prediction",
                "options": ["yes", "no"],
                "probabilities": [0.8, 0.2],
                "expected_key": "yes",
                "tags": ["all", "pair", "solo"],
            },
            {
                "case_id": "wrong",
                "status": "prediction",
                "options": ["yes", "no"],
                "probabilities": [0.7, 0.3],
                "expected_key": "no",
                "tags": ["all", "pair"],
            },
            {
                "case_id": "invalid",
                "status": "prediction",
                "options": ["yes", "no"],
                "probabilities": [0.4, 0.3],
                "expected_key": "yes",
                "tags": ["all", "invalid"],
            },
            {
                "case_id": "unlabeled",
                "status": "prediction",
                "options": ["yes", "no"],
                "probabilities": [0.5, 0.5],
                "tags": ["all", "unlabeled"],
            },
            {"case_id": "failed", "status": "error", "error_code": "timeout", "tags": ["all", "error"]},
        ]
    }
)
INVALID_TAGS: Final = [
    ("SECRET_SENTINEL", "SECRET_SENTINEL"),
    ("",),
    ("   ",),
    ("x" * 129,),
    (True,),
    tuple(f"tag-{index}" for index in range(17)),
]


def _tagged_payload(tags: tuple[str | bool, ...], status: Literal["prediction", "error"] = "prediction") -> str:
    case = f'"tags":{json.dumps(tags)}'
    match status:
        case "error":
            return '{"cases":[{"case_id":"error","status":"error","error_code":"timeout",' + case + "}]}"
        case "prediction":
            return PAYLOAD.replace('"expected_key":"yes"', '"expected_key":"yes",' + case)
        case _:
            assert_never(status)


def _assert_mixed_diagnostics(report: DecisionEvaluationReport) -> None:
    assert report.schema_version == 1
    assert report.score_source == "provided_probabilities"
    assert report.calibration_status == "unverified"
    assert report.counts.scored == 2
    interval = report.metrics.accuracy_interval
    assert interval is not None
    assert (interval.method, interval.confidence_level, interval.z, interval.n, interval.successes) == (
        "wilson",
        0.95,
        1.96,
        2,
        1,
    )
    assert interval.lower == pytest.approx(0.09452865480086614)
    assert interval.upper == pytest.approx(0.9054713451991339)
    diagnostics = report.tag_diagnostics
    assert (diagnostics.total_tags, diagnostics.omitted_tags, diagnostics.tag_limit) == (6, 0, 25)
    assert tuple(group.tag for group in diagnostics.groups) == ("all", "pair", "error", "invalid", "solo", "unlabeled")
    groups = {group.tag: group for group in diagnostics.groups}
    assert groups["all"].counts == report.counts
    assert groups["all"].metrics == report.metrics
    assert groups["all"].ece_bins == report.ece_bins
    assert groups["all"].selective_coverage == report.selective_coverage
    assert groups["all"].underdetermined == report.underdetermined
    assert groups["pair"].counts.total == 2
    assert groups["pair"].metrics.accuracy_interval == interval
    assert groups["solo"].counts.scored == 1
    assert groups["error"].counts.errors == 1
    assert groups["error"].metrics.accuracy_interval is None
    assert groups["invalid"].counts.invalid_sum == 1
    assert groups["unlabeled"].counts.unlabeled == 1


def test_api_interval_when_untagged_prediction(api_client: AuthenticatedClient) -> None:
    # Given: the prior untagged request and a protected synthetic JWT.
    # When: the registered API evaluates the request.
    response = api_client.client.post(
        ENDPOINT,
        content=PAYLOAD,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: the typed report includes the known one-success Wilson interval.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    interval = DecisionEvaluationReport.model_validate_json(response.content).metrics.accuracy_interval
    assert interval is not None
    assert (interval.n, interval.successes) == (1, 1)
    assert interval.lower == pytest.approx(0.20654329147389294)
    assert interval.upper == 1


def test_api_diagnostics_when_mixed_tags(api_client: AuthenticatedClient) -> None:
    # Given: tagged correct, wrong, invalid, unlabelled and error cases.
    # When: the authenticated production route parses and evaluates them.
    response = api_client.client.post(
        ENDPOINT,
        content=MIXED,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: output retains the shared aggregate and group scoring contract.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    _assert_mixed_diagnostics(DecisionEvaluationReport.model_validate_json(response.content))


def test_cli_diagnostics_when_mixed_tags(cli_app: typer.Typer, tmp_path: Path) -> None:
    # Given: the same synthetic cases in a temporary input file.
    path = tmp_path / "mixed.json"
    _ = path.write_text(MIXED, encoding="utf-8")
    # When: the real registered Typer command evaluates the file.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: stdout is a typed report with the same diagnostics as the API.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert result.exit_code == 0
    assert result.stderr == ""
    _assert_mixed_diagnostics(DecisionEvaluationReport.model_validate_json(result.stdout))


@pytest.mark.parametrize("status", ["prediction", "error"])
def test_api_accepts_when_sixteen_unique_tags(
    api_client: AuthenticatedClient,
    status: Literal["prediction", "error"],
) -> None:
    # Given: a case at the inclusive per-case tag limit.
    payload = _tagged_payload(tuple(f"tag-{index}" for index in range(16)), status)
    # When: the authenticated route evaluates that bounded request.
    response = api_client.client.post(
        ENDPOINT,
        content=payload,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: all distinct tags are exposed instead of rejected or discarded.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    report = DecisionEvaluationReport.model_validate_json(response.content)
    assert report.tag_diagnostics.total_tags == 16
    assert len(report.tag_diagnostics.groups) == 16


def test_cli_accepts_when_sixteen_unique_tags(cli_app: typer.Typer, tmp_path: Path) -> None:
    # Given: a prediction at the inclusive tag limit in an isolated input file.
    path = tmp_path / "bounded.json"
    _ = path.write_text(_tagged_payload(tuple(f"tag-{index}" for index in range(16))), encoding="utf-8")
    # When: the registered CLI command reads the bounded tagged request.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: JSON stdout retains every accepted tag.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert result.exit_code == 0 and result.stderr == ""
    assert DecisionEvaluationReport.model_validate_json(result.stdout).tag_diagnostics.total_tags == 16


@pytest.mark.parametrize("payload", ['{"cases":[]}', _tagged_payload(("error-only",), "error")])
def test_api_interval_is_null_when_scored_set_empty(api_client: AuthenticatedClient, payload: str) -> None:
    # Given: an empty dataset or an error-only group with no labelled scored predictions.
    # When: the production endpoint evaluates that synthetic request.
    response = api_client.client.post(
        ENDPOINT,
        content=payload,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: the public JSON interval remains nullable instead of inventing samples.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    report = DecisionEvaluationReport.model_validate_json(response.content)
    assert report.metrics.accuracy_interval is None
    assert all(group.metrics.accuracy_interval is None for group in report.tag_diagnostics.groups)


def test_api_omitted_tags_when_group_limit_exceeded(api_client: AuthenticatedClient) -> None:
    # Given: two error cases with 32 distinct accepted tags in total.
    payload = json.dumps(
        {
            "cases": [
                {
                    "case_id": f"case-{batch}",
                    "status": "error",
                    "error_code": "timeout",
                    "tags": [f"tag-{index:02}" for index in range(batch * 16, (batch + 1) * 16)],
                }
                for batch in range(2)
            ]
        }
    )
    # When: the authenticated route builds the bounded diagnostics report.
    response = api_client.client.post(
        ENDPOINT,
        content=payload,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: output exposes the omitted count and deterministic top 25 groups.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    diagnostics = DecisionEvaluationReport.model_validate_json(response.content).tag_diagnostics
    assert (diagnostics.total_tags, diagnostics.omitted_tags, diagnostics.tag_limit) == (32, 7, 25)
    assert tuple(group.tag for group in diagnostics.groups) == tuple(f"tag-{index:02}" for index in range(25))


@pytest.mark.parametrize("tags", INVALID_TAGS)
@pytest.mark.parametrize("status", ["prediction", "error"])
def test_api_safe_validation_when_tags_invalid(
    api_client: AuthenticatedClient,
    tags: tuple[str | bool, ...],
    status: Literal["prediction", "error"],
) -> None:
    # Given: a duplicate, invalid key, invalid type or excessive tag count.
    payload = _tagged_payload(tags, status)
    # When: the request crosses the production typed boundary.
    response = api_client.client.post(
        ENDPOINT,
        content=payload,
        headers={
            "Authorization": api_client.authorization,
            "Content-Type": "application/json",
        },
    )
    # Then: the generic error stays safe and compatible.
    assert response.status_code == 422
    assert ValidationErrorBody.model_validate_json(response.content).detail == "Invalid decision evaluation input"
    assert "SECRET_SENTINEL" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("tags", INVALID_TAGS)
def test_cli_safe_error_when_tags_invalid(cli_app: typer.Typer, tmp_path: Path, tags: tuple[str | bool, ...]) -> None:
    # Given: synthetic invalid tagged JSON stored under the isolated home.
    path = tmp_path / "invalid.json"
    _ = path.write_text(_tagged_payload(tags), encoding="utf-8")
    # When: the real CLI reads and parses the file.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: validation uses exit 2 with safe stderr and no report.
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr
    assert "SECRET_SENTINEL" not in result.stderr
    assert "Traceback" not in result.stderr


def test_api_denied_when_tagged_request_has_missing_credentials(api_client: AuthenticatedClient) -> None:
    # Given: valid synthetic tagged input under a protected auth policy.
    # When: the request omits the bearer credential.
    response = api_client.client.post(ENDPOINT, content=MIXED, headers={"Content-Type": "application/json"})
    # Then: the additional input fields preserve the authentication boundary.
    assert response.status_code == 401


class SchemaProperty(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    reference: str | None = Field(default=None, alias="$ref")
    kind: str | None = Field(default=None, alias="type")
    const_value: str | float | int | None = Field(default=None, alias="const")
    maximum_items: int | None = Field(default=None, alias="maxItems")
    minimum: float | None = None
    maximum: float | None = None
    alternatives: tuple[SchemaProperty, ...] = Field(default=(), alias="anyOf")
    items: SchemaProperty | None = None


class ComponentSchema(SchemaProperty):
    properties: dict[str, SchemaProperty] = Field(default_factory=dict)


class DiagnosticOpenAPI(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    schemas: dict[str, ComponentSchema] = Field(validation_alias=AliasPath("components", "schemas"))


def test_api_openapi_when_diagnostics_are_documented(api_client: AuthenticatedClient) -> None:
    # Given: the registered production app with the typed response model.
    # When: a consumer reads its public OpenAPI document in memory.
    response = api_client.client.get("/openapi.json")
    # Then: additive fields use references to typed bounded structures.
    assert response.status_code == 200
    schemas = DiagnosticOpenAPI.model_validate_json(response.content).schemas
    interval_property = schemas["DecisionEvaluationMetrics"].properties["accuracy_interval"]
    assert any(item.kind == "null" for item in interval_property.alternatives)
    interval_ref = next(item.reference for item in interval_property.alternatives if item.reference is not None)
    interval = schemas[interval_ref.removeprefix("#/components/schemas/")].properties
    for key, expected_kind in (("n", "integer"), ("successes", "integer"), ("lower", "number"), ("upper", "number")):
        property_schema = interval[key]
        if property_schema.reference is not None:
            property_schema = schemas[property_schema.reference.removeprefix("#/components/schemas/")]
        assert property_schema.kind == expected_kind
    assert interval["method"].const_value == "wilson"
    for key, expected_value in (("confidence_level", 0.95), ("z", 1.96)):
        assert interval[key].kind == "number"
        assert interval[key].minimum == interval[key].maximum == expected_value
    diagnostic_ref = schemas["DecisionEvaluationReport"].properties["tag_diagnostics"].reference
    assert diagnostic_ref is not None
    diagnostics = schemas[diagnostic_ref.removeprefix("#/components/schemas/")].properties
    assert diagnostics["total_tags"].kind == diagnostics["omitted_tags"].kind == "integer"
    assert diagnostics["tag_limit"].const_value == 25
    assert diagnostics["groups"].kind == "array"
    group_items = diagnostics["groups"].items
    assert group_items is not None and group_items.reference is not None
    group = schemas[group_items.reference.removeprefix("#/components/schemas/")].properties
    assert {"tag", "counts", "metrics", "ece_bins", "selective_coverage", "underdetermined"} <= group.keys()
    for key in ("counts", "metrics", "ece_bins", "selective_coverage", "underdetermined"):
        assert group[key] == schemas["DecisionEvaluationReport"].properties[key]
    for case in ("DecisionPrediction", "DecisionError"):
        assert schemas[case].properties["tags"].kind == "array"
        assert schemas[case].properties["tags"].maximum_items == 16
