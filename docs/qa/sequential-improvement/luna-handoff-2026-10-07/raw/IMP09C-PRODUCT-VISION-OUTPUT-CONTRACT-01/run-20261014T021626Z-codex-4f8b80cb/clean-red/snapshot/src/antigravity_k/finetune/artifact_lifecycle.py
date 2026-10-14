from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.finetune.evaluation import evaluation_pair_sha256, load_evaluation_pair
from antigravity_k.finetune.training_adapter import TrainingRunResult, TrainingRunStatus


@dataclass(frozen=True, slots=True)
class ArtifactLifecycleError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class FusedArtifactStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class FusedArtifactResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: FusedArtifactStatus
    return_code: int
    base_model: str
    base_revision: str
    adapter_path: Path
    output_path: Path
    dataset_sha256: str
    recipe_sha256: str
    environment: dict[str, str]
    evaluation_sha256: str
    iterations: int = Field(ge=1)
    stdout: str
    stderr: str


def fuse_training_artifact(
    training: TrainingRunResult,
    *,
    output_path: Path,
    evaluation_path: Path | None = None,
) -> FusedArtifactResult:
    if training.status is not TrainingRunStatus.SUCCESS:
        raise ArtifactLifecycleError("Successful training run is required before fusion.")
    output_path.mkdir(parents=True, exist_ok=True)
    command = (
        sys.executable,
        "-m",
        "mlx_lm",
        "fuse",
        "--model",
        training.base_model,
        "--adapter-path",
        str(training.adapter_path),
        "--save-path",
        str(output_path),
    )
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    status = FusedArtifactStatus.SUCCESS if process.returncode == 0 else FusedArtifactStatus.FAILED
    evaluation_sha256 = training.evaluation_sha256
    if evaluation_path is not None:
        pair = load_evaluation_pair(
            evaluation_path,
            model=training.base_model,
            model_revision=training.base_revision,
        )
        if pair.tuned.recipe_sha256 != training.recipe_sha256:
            raise ArtifactLifecycleError("Evaluation recipe provenance does not match training run.")
        if pair.tuned.adapter_path != training.adapter_path:
            raise ArtifactLifecycleError("Evaluation adapter provenance does not match training run.")
        evaluation_sha256 = evaluation_pair_sha256(pair)
    result = FusedArtifactResult(
        status=status,
        return_code=process.returncode,
        base_model=training.base_model,
        base_revision=training.base_revision,
        adapter_path=training.adapter_path,
        output_path=output_path,
        dataset_sha256=training.dataset_sha256,
        recipe_sha256=training.recipe_sha256,
        environment=training.environment,
        evaluation_sha256=evaluation_sha256,
        iterations=training.iterations,
        stdout=process.stdout,
        stderr=process.stderr,
    )
    _ = (output_path / "artifact_manifest.json").write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return result
