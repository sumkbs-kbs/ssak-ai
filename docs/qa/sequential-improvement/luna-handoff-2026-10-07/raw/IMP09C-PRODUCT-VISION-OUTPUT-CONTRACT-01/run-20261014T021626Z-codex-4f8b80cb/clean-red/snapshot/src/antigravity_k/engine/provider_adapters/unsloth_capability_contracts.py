from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

type CapabilityStatus = Literal["available", "unavailable", "not_required"]
type DiskStatus = Literal["sufficient", "insufficient"]
type AcceleratorKind = Literal["apple_unified", "cuda", "none"]
type ThermalState = Literal["nominal", "elevated", "critical", "unknown"]


class CapabilityOperation(StrEnum):
    INFERENCE = "inference"
    TRAINING = "training"
    EXPORT = "export"


class CapabilityProvider(StrEnum):
    OLLAMA = "ollama"
    MLX = "mlx"
    UNSLOTH = "unsloth"


class PlatformKind(StrEnum):
    DARWIN_ARM64 = "darwin_arm64"
    DARWIN_OTHER = "darwin_other"
    NON_DARWIN = "non_darwin"


class SystemCapabilityReading(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    platform: PlatformKind
    memory_total_bytes: int = Field(gt=0)
    memory_available_bytes: int = Field(ge=0)
    disk_free_bytes: int = Field(ge=0)
    thermal_state: ThermalState
    accelerator_kind: AcceleratorKind
    accelerator_status: CapabilityStatus
    accelerator_detail: str
    ollama_installed: bool
    mlx_installed: bool
    unsloth_installed: bool
    cuda_available: bool


class MemoryPreflight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    total_bytes: int = Field(gt=0)
    available_bytes: int = Field(ge=0)


class DiskPreflight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: DiskStatus
    free_bytes: int = Field(ge=0)
    minimum_bytes: int = Field(gt=0)


class AcceleratorPreflight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: AcceleratorKind
    status: CapabilityStatus
    detail: str


class ThermalPreflight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    state: ThermalState


class SystemPreflight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    memory: MemoryPreflight
    disk: DiskPreflight
    accelerator: AcceleratorPreflight
    thermal: ThermalPreflight


class ProviderCapabilityRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    operation: CapabilityOperation
    provider: CapabilityProvider
    status: CapabilityStatus
    is_default: bool
    max_concurrent: int = Field(ge=1)
    detail: str


class UnslothCapabilitySnapshot(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    platform: PlatformKind
    system: SystemPreflight
    capabilities: tuple[ProviderCapabilityRecord, ...]
    write_tools_enabled: Literal[False] = False
