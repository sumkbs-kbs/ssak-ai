from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Final

import pytest
import typer
from fastapi.routing import APIRoute
from httpx import Client
from pydantic import AliasPath, BaseModel, ConfigDict, Field
from starlette.testclient import TestClient
from typer.testing import CliRunner

PAYLOAD: Final = (
    '{"model_id":"fixture-model","dataset_id":"fixture-set","cases":['
    '{"case_id":"one","status":"prediction","options":["yes","no"],'
    '"probabilities":[0.8,0.2],"expected_key":"yes"}]}'
)
ENDPOINT: Final = "/api/benchmarks/decisions/evaluate"
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024


def _isolate_home(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    def home(_cls: type[Path]) -> Path:
        return path

    monkeypatch.setattr(Path, "home", classmethod(home))


@pytest.fixture
def cli_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> typer.Typer:
    _isolate_home(monkeypatch, tmp_path)
    from antigravity_k.cli import app

    return app


@dataclass(frozen=True, slots=True)
class AuthenticatedClient:
    client: Client
    authorization: str = field(repr=False)


class ValidationErrorBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    detail: str


class ValidationErrorOpenAPI(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    schema_reference: str = Field(
        validation_alias=AliasPath(
            "paths",
            ENDPOINT,
            "post",
            "responses",
            "422",
            "content",
            "application/json",
            "schema",
            "$ref",
        )
    )
    detail_type: str = Field(
        validation_alias=AliasPath(
            "components",
            "schemas",
            "DecisionEvaluationInputError",
            "properties",
            "detail",
            "type",
        )
    )
    required_fields: tuple[str, ...] = Field(
        validation_alias=AliasPath(
            "components",
            "schemas",
            "DecisionEvaluationInputError",
            "required",
        )
    )


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[AuthenticatedClient]:
    _isolate_home(monkeypatch, tmp_path)
    from antigravity_k.api import auth_policy, auth_routes
    from antigravity_k.api.auth_policy import AuthPolicy
    from antigravity_k.api.server import app
    from antigravity_k.engine.auth import TokenService

    service = TokenService(epoch_provider=lambda: 0)
    policy = AuthPolicy(stored_pin_hash=lambda: "fixture-hash", plaintext_pin=lambda: "")
    monkeypatch.setattr(auth_routes, "_token_service", service)
    monkeypatch.setattr(auth_policy, "_shared_auth_policy", policy)
    # Closing avoids production subsystem startup while retaining the real app,
    # registered routers, HTTP middleware and bearer verification.
    with closing(TestClient(app, raise_server_exceptions=False)) as client:
        yield AuthenticatedClient(client, f"Bearer {service.issue_token('fixture-user')}")


def test_cli_help_when_registered(cli_app: typer.Typer) -> None:
    # Given: the production Typer application.
    # When: command-specific help is requested.
    result = CliRunner().invoke(cli_app, ["decision-eval", "--help"])
    # Then: the public command and input argument are discoverable.
    assert result.exit_code == 0
    assert "decision-eval" in result.stdout
    assert "INPUT" in result.stdout


def test_cli_report_when_valid_json(cli_app: typer.Typer, tmp_path: Path) -> None:
    # Given: one labelled caller-supplied prediction.
    path = tmp_path / "input.json"
    _ = path.write_text(PAYLOAD, encoding="utf-8")
    # When: the actual registered CLI command evaluates it.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: stdout is a typed JSON report with the known metric denominator.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert result.exit_code == 0
    report = DecisionEvaluationReport.model_validate_json(result.stdout)
    assert report.counts.scored == 1
    assert report.metrics.accuracy == 1
    assert report.metrics.brier == pytest.approx(0.08)
    assert report.calibration_status == "unverified"
    assert result.stderr == ""


@pytest.mark.parametrize("raw", [b'{"cases":"SECRET_SENTINEL"}', b"\xff", b"not-json"])
def test_cli_safe_error_when_invalid_input(cli_app: typer.Typer, tmp_path: Path, raw: bytes) -> None:
    # Given: invalid input whose content must not be echoed.
    path = tmp_path / "invalid.json"
    _ = path.write_bytes(raw)
    # When: the public command reads the file.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: input failure has a safe stderr message and no JSON or traceback.
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr
    assert "SECRET_SENTINEL" not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("directory", [False, True])
def test_cli_safe_error_when_file_unreadable(cli_app: typer.Typer, tmp_path: Path, directory: bool) -> None:
    # Given: a missing file or a directory instead of a regular input.
    path = tmp_path / "unreadable.json"
    if directory:
        path.mkdir()
    # When: the public command tries to open it.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: file errors follow the same safe exit contract.
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr
    assert str(path) not in result.stderr


@pytest.mark.parametrize("extra_bytes", [0, 1])
def test_cli_bounded_read_when_size_boundary(cli_app: typer.Typer, tmp_path: Path, extra_bytes: int) -> None:
    # Given: valid JSON padded to the exact byte limit or one byte beyond it.
    path = tmp_path / "boundary.json"
    raw = PAYLOAD.encode("utf-8")
    _ = path.write_bytes(raw + b" " * (MAX_INPUT_BYTES + extra_bytes - len(raw)))
    # When: the CLI evaluates the bounded file.
    result = CliRunner().invoke(cli_app, ["decision-eval", str(path)])
    # Then: the inclusive limit succeeds and overflow fails safely.
    assert result.exit_code == (2 if extra_bytes else 0)
    assert bool(result.stderr) == bool(extra_bytes)


@pytest.mark.usefixtures("api_client")
def test_api_registered_when_production_router_loaded() -> None:
    # Given: the full production app already imported by the client fixture.
    from antigravity_k.api.server import app

    # When: routes are inspected through their public FastAPI representation.
    paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    # Then: the endpoint is connected to the app, rather than an unused router.
    assert ENDPOINT in paths


def test_api_denied_when_credentials_missing(api_client: AuthenticatedClient) -> None:
    # Given: valid input and a configured protected auth policy.
    # When: no bearer credential accompanies the request.
    response = api_client.client.post(ENDPOINT, content=PAYLOAD, headers={"Content-Type": "application/json"})
    # Then: the production authentication middleware denies it.
    assert response.status_code == 401


def test_api_report_when_bearer_valid(api_client: AuthenticatedClient) -> None:
    # Given: a real ephemeral JWT and a labelled prediction.
    # When: the authenticated production route is called.
    response = api_client.client.post(
        ENDPOINT,
        content=PAYLOAD,
        headers={"Authorization": api_client.authorization, "Content-Type": "application/json"},
    )
    # Then: the API returns the same typed metric semantics as the CLI.
    from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationReport

    assert response.status_code == 200
    report = DecisionEvaluationReport.model_validate_json(response.content)
    assert report.counts.scored == 1
    assert report.metrics.ece == pytest.approx(0.2)
    assert report.calibration_status == "unverified"


def test_api_documented_error_when_actual_validation_fails(api_client: AuthenticatedClient) -> None:
    # Given: the observed generic validation response from the production route.
    actual_response = api_client.client.post(
        ENDPOINT,
        content='{"cases":"SECRET_SENTINEL"}',
        headers={"Authorization": api_client.authorization, "Content-Type": "application/json"},
    )
    assert actual_response.status_code == 422
    actual_body = ValidationErrorBody.model_validate_json(actual_response.content)
    # When: a consumer reads the production public OpenAPI contract.
    response = api_client.client.get("/openapi.json")
    # Then: the declared 422 schema describes the observed required string detail.
    assert response.status_code == 200
    contract = ValidationErrorOpenAPI.model_validate_json(response.content)
    assert contract.schema_reference == "#/components/schemas/DecisionEvaluationInputError"
    assert contract.detail_type == "string"
    assert "detail" in contract.required_fields
    assert actual_body.detail == "Invalid decision evaluation input"


@pytest.mark.parametrize(
    "raw",
    [
        '{"cases":"SECRET_SENTINEL"}',
        "not-json SECRET_SENTINEL",
        PAYLOAD.replace("0.8", "NaN"),
        PAYLOAD.replace("0.8", "Infinity"),
        PAYLOAD.replace("0.8", "true"),
        PAYLOAD.replace("0.8", '"SECRET_SENTINEL"'),
        PAYLOAD.replace('["yes","no"]', '["yes","yes"]'),
        '{"cases":[{"case_id":"same","status":"error","error_code":"timeout"},'
        + '{"case_id":"same","status":"error","error_code":"timeout"}]}',
    ],
)
def test_api_safe_validation_when_malformed(api_client: AuthenticatedClient, raw: str) -> None:
    # Given: malformed input and valid authentication.
    # When: FastAPI parses the request through the endpoint-local boundary.
    response = api_client.client.post(
        ENDPOINT,
        content=raw,
        headers={"Authorization": api_client.authorization, "Content-Type": "application/json"},
    )
    # Then: validation stays 422 even for nonfinite JSON and never echoes payload.
    assert response.status_code == 422
    assert "SECRET_SENTINEL" not in response.text
    assert "probabilities" not in response.text
    assert "Traceback" not in response.text
