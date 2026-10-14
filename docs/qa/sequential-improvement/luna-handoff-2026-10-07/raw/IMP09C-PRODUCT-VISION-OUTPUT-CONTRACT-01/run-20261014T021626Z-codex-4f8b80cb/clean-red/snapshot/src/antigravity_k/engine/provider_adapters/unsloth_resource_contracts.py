from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final, Literal, NewType, override
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReservationId = NewType("ReservationId", str)

IMMUTABLE_REVISION_PATTERN: Final = r"^[0-9a-f]{40,64}$"
SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
IDEMPOTENCY_KEY_PATTERN: Final = r"^[A-Za-z0-9._:-]+$"

type UnslothDeviceId = Literal["unified:0"]


class UnslothResourceOperation(StrEnum):
    TRAINING = "training"
    CHECKPOINT_LOAD = "checkpoint_load"
    GGUF_EXPORT = "gguf_export"


class UnslothAdmissionCode(StrEnum):
    ACCEPTED = "accepted"
    REPLAYED = "idempotent_replay"
    DEVICE_BUSY = "device_busy"
    INSUFFICIENT_MEMORY = "insufficient_memory"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RESERVATION_RELEASED = "reservation_released"


class UnslothReservationState(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class UnslothArtifactProvenanceError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class UnslothArtifactProvenance(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source_uri: str = Field(min_length=1, max_length=2_048)
    revision: str = Field(pattern=IMMUTABLE_REVISION_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("source_uri")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.scheme or not (parsed.netloc or parsed.path):
            raise UnslothArtifactProvenanceError(
                "Artifact source must be an absolute URI.",
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise UnslothArtifactProvenanceError(
                "Artifact source URI must not contain credentials, query, or fragment data.",
            )
        return value

    def fingerprint(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class UnslothAdmissionRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    idempotency_key: str = Field(
        min_length=16,
        max_length=128,
        pattern=IDEMPOTENCY_KEY_PATTERN,
    )
    operation: UnslothResourceOperation
    device_id: UnslothDeviceId = "unified:0"
    estimated_peak_bytes: int = Field(gt=0)
    artifact: UnslothArtifactProvenance

    def request_fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"idempotency_key"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class UnslothMemorySnapshot(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    total_bytes: int = Field(gt=0)
    available_bytes: int = Field(ge=0)
    source: Literal["system"] = "system"


class UnslothAdmissionDecision(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    allowed: bool
    code: UnslothAdmissionCode
    reservation_id: str | None
    reservation_state: UnslothReservationState | None
    replayed: bool
    operation: UnslothResourceOperation
    device_id: str
    estimated_peak_bytes: int
    total_bytes: int
    available_bytes: int
    required_headroom_bytes: int
    projected_available_bytes: int
    provenance_fingerprint: str
    resource_job_id: str | None = None
    write_tools_enabled: Literal[False] = False


class UnslothReservation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    reservation_id: str
    operation: UnslothResourceOperation
    device_id: str
    estimated_peak_bytes: int
    provenance_fingerprint: str
    state: UnslothReservationState
    created_at: str
    resource_job_id: str | None = None
    released_at: str | None = None


class UnslothResourceStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    memory: UnslothMemorySnapshot
    minimum_headroom_ratio: float
    max_active_per_device: int
    active_reservations: tuple[UnslothReservation, ...]
    write_tools_enabled: Literal[False] = False


@dataclass(frozen=True, slots=True)
class UnslothResourcePolicy:
    minimum_headroom_ratio: float = 0.20
    max_active_per_device: int = 1
