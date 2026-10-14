from __future__ import annotations

import hashlib
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.engine.provider_adapters.unsloth_resource_broker import (
    SystemMemoryProbe,
    UnslothResourceBroker,
)
from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    IDEMPOTENCY_KEY_PATTERN,
    ReservationId,
    UnslothAdmissionCode,
    UnslothAdmissionDecision,
    UnslothAdmissionRequest,
    UnslothArtifactProvenance,
    UnslothResourceOperation,
)
from antigravity_k.finetune.training_adapter import TrainingRunResult
from antigravity_k.finetune.training_recipe import ResolvedTrainingRecipe


class FinetuneResourceSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    database_path: Path
    estimated_peak_bytes: int = Field(gt=0)
    idempotency_key: str | None = Field(
        default=None,
        min_length=16,
        max_length=128,
        pattern=IDEMPOTENCY_KEY_PATTERN,
    )


@dataclass(frozen=True, slots=True)
class FinetuneResourceAdmission:
    broker: UnslothResourceBroker
    request: UnslothAdmissionRequest


@dataclass(frozen=True, slots=True)
class FinetuneResourceArtifact:
    operation: UnslothResourceOperation
    source_path: Path
    revision: str


@dataclass(frozen=True, slots=True)
class FinetuneResourceAdmissionError(RuntimeError):
    code: UnslothAdmissionCode

    @override
    def __str__(self) -> str:
        return f"Finetune resource admission denied: {self.code.value}."


@dataclass(frozen=True, slots=True)
class FinetuneResourceInvariantError(RuntimeError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


def build_training_admission_request(
    resolved: ResolvedTrainingRecipe,
    settings: FinetuneResourceSettings,
) -> UnslothAdmissionRequest:
    return _build_request(
        settings,
        FinetuneResourceArtifact(
            operation=UnslothResourceOperation.TRAINING,
            source_path=resolved.train_path,
            revision=resolved.recipe_sha256,
        ),
    )


def build_merge_admission_request(
    run_path: Path,
    training: TrainingRunResult,
    settings: FinetuneResourceSettings,
) -> UnslothAdmissionRequest:
    return _build_request(
        settings,
        FinetuneResourceArtifact(
            operation=UnslothResourceOperation.CHECKPOINT_LOAD,
            source_path=run_path,
            revision=training.recipe_sha256,
        ),
    )


def build_finetune_resource_admission(
    request: UnslothAdmissionRequest,
    settings: FinetuneResourceSettings,
) -> FinetuneResourceAdmission:
    return FinetuneResourceAdmission(
        broker=UnslothResourceBroker(settings.database_path, SystemMemoryProbe()),
        request=request,
    )


@contextmanager
def reserve_finetune_resource(
    admission: FinetuneResourceAdmission,
) -> Generator[UnslothAdmissionDecision]:
    decision = admission.broker.admit(admission.request)
    match decision.code:
        case UnslothAdmissionCode.ACCEPTED:
            if decision.reservation_id is None:
                raise FinetuneResourceInvariantError("Accepted resource admission requires a reservation identifier.")
            try:
                yield decision
            finally:
                _ = admission.broker.release(ReservationId(decision.reservation_id))
        case (
            UnslothAdmissionCode.REPLAYED
            | UnslothAdmissionCode.DEVICE_BUSY
            | UnslothAdmissionCode.INSUFFICIENT_MEMORY
            | UnslothAdmissionCode.IDEMPOTENCY_CONFLICT
            | UnslothAdmissionCode.RESERVATION_RELEASED
        ):
            raise FinetuneResourceAdmissionError(decision.code)


def _build_request(
    settings: FinetuneResourceSettings,
    artifact: FinetuneResourceArtifact,
) -> UnslothAdmissionRequest:
    source_bytes = artifact.source_path.read_bytes()
    return UnslothAdmissionRequest(
        idempotency_key=settings.idempotency_key or f"local-{artifact.operation.value}:{uuid.uuid4()}",
        operation=artifact.operation,
        estimated_peak_bytes=settings.estimated_peak_bytes,
        artifact=UnslothArtifactProvenance(
            source_uri=artifact.source_path.resolve().as_uri(),
            revision=artifact.revision,
            sha256=hashlib.sha256(source_bytes).hexdigest(),
        ),
    )
