from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import ValidationError

from antigravity_k.engine.decision_evaluation import evaluate_decisions
from antigravity_k.engine.decision_evaluation_models import DecisionEvaluationRequest

MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
INPUT_ERROR: Final = "Unable to evaluate input. Supply a readable UTF-8 JSON file of at most 2 MiB matching the decision evaluation schema."


def decision_eval(
    input_path: Annotated[Path, typer.Argument(metavar="INPUT.json", help="Caller-supplied prediction JSON file.")],
) -> None:
    """Measure caller-supplied probabilities; calibration remains unverified."""
    try:
        with input_path.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            typer.echo(INPUT_ERROR, err=True)
            raise typer.Exit(code=2)
        text = raw.decode("utf-8")
    except (OSError, ValueError):
        typer.echo(INPUT_ERROR, err=True)
        raise typer.Exit(code=2) from None
    try:
        request = DecisionEvaluationRequest.model_validate_json(text)
    except ValidationError:
        typer.echo(INPUT_ERROR, err=True)
        raise typer.Exit(code=2) from None
    typer.echo(evaluate_decisions(request).model_dump_json())
