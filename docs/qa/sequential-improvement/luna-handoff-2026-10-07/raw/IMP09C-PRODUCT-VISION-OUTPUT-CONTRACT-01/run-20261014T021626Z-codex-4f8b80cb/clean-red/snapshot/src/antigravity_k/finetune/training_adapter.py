from __future__ import annotations

import logging
import threading
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.finetune.training_recipe import ResolvedTrainingRecipe
from antigravity_k.finetune.training_supervision import supervise_command

logger = logging.getLogger("agk.finetune")


class TrainingRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class TrainingRunResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: TrainingRunStatus
    return_code: int
    dataset_sha256: str
    adapter_path: Path
    data_dir: Path
    iterations: int = Field(ge=1)
    stdout: str
    stderr: str
    base_model: str
    base_revision: str
    recipe_sha256: str
    environment: dict[str, str]
    evaluation_sha256: str
    resume_adapter_path: Path | None = None
    resume_source_sha256: str | None = None


def run_resolved_training(
    resolved: ResolvedTrainingRecipe,
    *,
    cwd: Path | None = None,
    timeout_sec: float | None = None,
    no_output_timeout_sec: float | None = None,
    cancel_event: threading.Event | None = None,
) -> TrainingRunResult:
    """해석된 학습 명령을 감독 실행한다 (TRN-02).

    subprocess.run 대신 training_supervision.supervise_command를 사용해
    새 프로세스 그룹으로 실행하고 timeout / 무출력 hang / cancel_event를
    감독한다. SIGTERM → grace → SIGKILL로 parent+descendant가 함께 종료된다.
    """
    data_dir = resolved.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    _stage_file(resolved.train_path, data_dir / "train.jsonl")
    _stage_file(resolved.valid_path, data_dir / "valid.jsonl")
    resolved.adapter_path.mkdir(parents=True, exist_ok=True)
    command = resolved.command
    outcome = supervise_command(
        command,
        cwd=None if cwd is None else str(cwd),
        timeout_sec=timeout_sec,
        no_output_timeout_sec=no_output_timeout_sec,
        cancel_event=cancel_event,
    )
    return_code = outcome.return_code if outcome.return_code is not None else -1
    status = TrainingRunStatus.SUCCESS if outcome.success else TrainingRunStatus.FAILED
    result = TrainingRunResult(
        status=status,
        return_code=return_code,
        dataset_sha256=resolved.dataset_sha256,
        adapter_path=resolved.adapter_path,
        data_dir=data_dir,
        iterations=resolved.iterations,
        stdout="\n".join(outcome.output),
        stderr="" if outcome.success else outcome.detail,
        base_model=resolved.base_model,
        base_revision=resolved.base_revision,
        recipe_sha256=resolved.recipe_sha256,
        environment=resolved.environment,
        evaluation_sha256=resolved.evaluation_sha256,
        resume_adapter_path=resolved.resume_adapter_path,
        resume_source_sha256=resolved.resume_source_sha256,
    )
    _ = (resolved.adapter_path.parent / "training_result.json").write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "MLX 학습 종료: status=%s return_code=%s dataset=%s",
        status.value,
        return_code,
        resolved.dataset_sha256,
    )
    return result


def _stage_file(source: Path, destination: Path) -> None:
    _ = destination.write_bytes(source.read_bytes())
