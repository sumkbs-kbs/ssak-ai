from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.finetune.dataset_contract import (
    DatasetContractError,
    FinetuneDatasetContract,
    inspect_dataset,
)


@dataclass(frozen=True, slots=True)
class TrainingRecipeError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


_CHECKPOINT_PATTERN = re.compile(r"^(?P<iteration>[0-9]{7})_adapters\.safetensors$")


class TrainingRecipe(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    base_model: str = Field(min_length=1, max_length=4_096)
    base_revision: str = Field(min_length=1, max_length=512)
    output_dir: Path
    dataset: FinetuneDatasetContract
    epochs: int = Field(ge=1, le=100)
    batch_size: int = Field(ge=1, le=128)
    gradient_accumulation_steps: int = Field(ge=1, le=4_096)
    learning_rate: Decimal = Field(gt=0, lt=1)
    lora_rank: int = Field(ge=1, le=1_024)
    lora_alpha: int = Field(ge=1, le=2_048)
    save_every: int = Field(ge=1, le=100_000)
    seed: int = Field(ge=0, le=2_147_483_647)
    gradient_checkpointing: bool = False


class ResolvedTrainingRecipe(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    command: tuple[str, ...]
    dataset_sha256: str
    dataset_record_count: int
    train_path: Path
    valid_path: Path
    adapter_path: Path
    data_dir: Path
    iterations: int = Field(ge=1)
    base_model: str
    base_revision: str
    recipe_sha256: str
    environment: dict[str, str]
    evaluation_sha256: str
    resume_adapter_path: Path | None = None
    resume_source_sha256: str | None = None
    gradient_checkpointing: bool = False


def _latest_checkpoint(adapter_path: Path) -> Path | None:
    candidates: list[tuple[int, Path]] = []
    for path in adapter_path.glob("*_adapters.safetensors"):
        match = _CHECKPOINT_PATTERN.match(path.name)
        if match is not None:
            candidates.append((int(match["iteration"]), path))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def resolve_training_recipe(recipe: TrainingRecipe, *, resume: bool = False) -> ResolvedTrainingRecipe:
    try:
        report = inspect_dataset(recipe.dataset)
    except DatasetContractError as error:
        raise TrainingRecipeError(str(error)) from error

    train_path = recipe.dataset.path.with_name(f"{recipe.dataset.path.stem}_train.jsonl")
    valid_path = recipe.dataset.path.with_name(f"{recipe.dataset.path.stem}_valid.jsonl")
    adapter_path = recipe.output_dir / "adapters"
    effective_batch = recipe.batch_size * recipe.gradient_accumulation_steps
    steps_per_epoch = (report.train_record_count + effective_batch - 1) // effective_batch
    iterations = max(1, steps_per_epoch) * recipe.epochs
    data_dir = recipe.output_dir / "data"
    resume_adapter_path = _latest_checkpoint(adapter_path) if resume else None
    if resume and resume_adapter_path is None:
        raise TrainingRecipeError("Resumable checkpoint is required before training.")
    resume_source_sha256 = hashlib.sha256(resume_adapter_path.read_bytes()).hexdigest() if resume_adapter_path else None
    recipe_canonical = recipe.model_dump_json(exclude={"dataset"})
    recipe_sha256 = hashlib.sha256(recipe_canonical.encode("utf-8")).hexdigest()
    try:
        mlx_lm_version = importlib.metadata.version("mlx_lm")
    except importlib.metadata.PackageNotFoundError:
        mlx_lm_version = "unknown"
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "mlx_lm": mlx_lm_version,
    }
    command: tuple[str, ...] = (
        sys.executable,
        "-m",
        "mlx_lm",
        "lora",
        "--model",
        recipe.base_model,
        "--train",
        "--data",
        str(data_dir),
        "--adapter-path",
        str(adapter_path),
        "--iters",
        str(iterations),
        "--batch-size",
        str(recipe.batch_size),
        "--learning-rate",
        str(recipe.learning_rate),
        "--num-layers",
        str(recipe.lora_rank),
        "--save-every",
        str(recipe.save_every),
        "--seed",
        str(recipe.seed),
    )
    if recipe.gradient_checkpointing:
        command = (*command, "--grad-checkpoint")
    if resume_adapter_path is not None:
        command = (*command, "--resume-adapter-file", str(resume_adapter_path))
    return ResolvedTrainingRecipe(
        command=command,
        dataset_sha256=report.sha256,
        dataset_record_count=report.record_count,
        train_path=train_path,
        valid_path=valid_path,
        adapter_path=adapter_path,
        data_dir=data_dir,
        iterations=iterations,
        base_model=recipe.base_model,
        base_revision=recipe.base_revision,
        recipe_sha256=recipe_sha256,
        environment=environment,
        evaluation_sha256=hashlib.sha256(b"").hexdigest(),
        resume_adapter_path=resume_adapter_path,
        resume_source_sha256=resume_source_sha256,
        gradient_checkpointing=recipe.gradient_checkpointing,
    )
