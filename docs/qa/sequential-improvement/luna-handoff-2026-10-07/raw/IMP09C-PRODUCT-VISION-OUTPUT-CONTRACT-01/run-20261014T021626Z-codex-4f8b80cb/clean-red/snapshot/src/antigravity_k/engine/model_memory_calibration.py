from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class MemoryMeasurementOutcome(StrEnum):
    SUCCESS = "success"
    OOM = "oom"


@dataclass(frozen=True, slots=True)
class MemoryMeasurementSeriesError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ModelMemoryArtifactError(ValueError):
    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


class MemoryMeasurement(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    context_tokens: int = Field(ge=1_024)
    kv_cache_bytes: int = Field(ge=1)
    peak_memory_bytes: int = Field(ge=1)
    outcome: MemoryMeasurementOutcome


class ModelMemoryCalibrationArtifact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    artifact_type: Literal["model_memory_calibration"]
    schema_version: Literal[1]
    model: str = Field(min_length=1, max_length=512)
    backend: str = Field(min_length=1, max_length=64)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    headroom_ratio: Decimal = Field(ge=Decimal("0.1"), le=Decimal("0.5"))
    measurements: tuple[MemoryMeasurement, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_measurement_series(self) -> ModelMemoryCalibrationArtifact:
        ordered = tuple(sorted(self.measurements, key=lambda item: item.context_tokens))
        successful = tuple(item for item in ordered if item.outcome is MemoryMeasurementOutcome.SUCCESS)
        failed = tuple(item for item in ordered if item.outcome is MemoryMeasurementOutcome.OOM)
        if not successful:
            raise MemoryMeasurementSeriesError("At least one successful memory measurement is required.")
        if failed and min(item.context_tokens for item in failed) <= max(item.context_tokens for item in successful):
            raise MemoryMeasurementSeriesError("OOM context must be above every successful measurement.")
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.kv_cache_bytes < previous.kv_cache_bytes:
                raise MemoryMeasurementSeriesError("KV-cache measurements must be monotonic by context size.")
        return self

    def safe_budget(self) -> ModelMemoryBudget:
        successful = tuple(item for item in self.measurements if item.outcome is MemoryMeasurementOutcome.SUCCESS)
        highest = max(successful, key=lambda item: item.context_tokens)
        retained_ratio = Decimal(1) - self.headroom_ratio
        return ModelMemoryBudget(
            model=self.model,
            context_token_limit=int(Decimal(highest.context_tokens) * retained_ratio),
            kv_cache_byte_limit=int(Decimal(highest.kv_cache_bytes) * retained_ratio),
            source_sha256=self.source_sha256,
        )


@dataclass(frozen=True, slots=True)
class ModelMemoryBudget:
    model: str
    context_token_limit: int
    kv_cache_byte_limit: int
    source_sha256: str


def load_model_memory_budget(paths: tuple[Path, ...], model_name: str) -> ModelMemoryBudget | None:
    budgets: list[ModelMemoryBudget] = []
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ModelMemoryArtifactError(path, str(error)) from error
        try:
            artifact = ModelMemoryCalibrationArtifact.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as error:
            raise ModelMemoryArtifactError(path, str(error)) from error
        if artifact.model == model_name:
            budgets.append(artifact.safe_budget())
    if not budgets:
        return None
    return ModelMemoryBudget(
        model=model_name,
        context_token_limit=min(item.context_token_limit for item in budgets),
        kv_cache_byte_limit=min(item.kv_cache_byte_limit for item in budgets),
        source_sha256=min(item.source_sha256 for item in budgets),
    )


__all__ = [
    "MemoryMeasurement",
    "MemoryMeasurementOutcome",
    "MemoryMeasurementSeriesError",
    "ModelMemoryArtifactError",
    "ModelMemoryBudget",
    "ModelMemoryCalibrationArtifact",
    "load_model_memory_budget",
]
