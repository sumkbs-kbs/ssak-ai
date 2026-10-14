from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Final, Literal, Protocol

import psutil

from antigravity_k.engine.provider_adapters.unsloth_capability_contracts import (
    AcceleratorKind,
    AcceleratorPreflight,
    CapabilityOperation,
    CapabilityProvider,
    CapabilityStatus,
    DiskPreflight,
    MemoryPreflight,
    PlatformKind,
    ProviderCapabilityRecord,
    SystemCapabilityReading,
    SystemPreflight,
    ThermalPreflight,
    ThermalState,
    UnslothCapabilitySnapshot,
)
from antigravity_k.engine.provider_adapters.unsloth_platform_policy import host_platform

MINIMUM_DISK_BYTES: Final = 10 * 1024**3
ELEVATED_THERMAL_CELSIUS: Final = 80.0
CRITICAL_THERMAL_CELSIUS: Final = 95.0


class CapabilityReadingProbe(Protocol):
    def reading(self) -> SystemCapabilityReading: ...


class _VirtualMemory(Protocol):
    @property
    def total(self) -> int: ...

    @property
    def available(self) -> int: ...


class _MemorySource(Protocol):
    def virtual_memory(self) -> _VirtualMemory: ...


class SystemCapabilityProbe:
    def __init__(self, output_root: Path, memory_source: _MemorySource = psutil) -> None:
        self._output_root: Path = output_root
        self._memory_source: _MemorySource = memory_source

    def reading(self) -> SystemCapabilityReading:
        memory = self._memory_source.virtual_memory()
        disk = shutil.disk_usage(self._output_root)
        platform_kind = host_platform()
        return SystemCapabilityReading(
            platform=platform_kind,
            memory_total_bytes=memory.total,
            memory_available_bytes=memory.available,
            disk_free_bytes=disk.free,
            thermal_state=self._thermal_state(),
            accelerator_kind=self._accelerator_kind(platform_kind),
            accelerator_status=("not_required" if platform_kind.startswith("darwin") else self._cuda_status()),
            accelerator_detail=self._accelerator_detail(platform_kind),
            ollama_installed=_module_installed("ollama"),
            mlx_installed=_module_installed("mlx_lm"),
            unsloth_installed=_module_installed("unsloth"),
            cuda_available=shutil.which("nvidia-smi") is not None,
        )

    @staticmethod
    def _thermal_state() -> ThermalState:
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, OSError, NotImplementedError):
            return "unknown"
        if not sensors:
            return "unknown"
        readings = [entry.current for entries in sensors.values() for entry in entries]
        if not readings:
            return "unknown"
        hottest = max(readings)
        if hottest >= CRITICAL_THERMAL_CELSIUS:
            return "critical"
        if hottest >= ELEVATED_THERMAL_CELSIUS:
            return "elevated"
        return "nominal"

    @staticmethod
    def _accelerator_kind(platform_kind: PlatformKind) -> AcceleratorKind:
        darwin = platform_kind in {PlatformKind.DARWIN_ARM64, PlatformKind.DARWIN_OTHER}
        if darwin:
            return "apple_unified"
        return "cuda" if shutil.which("nvidia-smi") is not None else "none"

    @staticmethod
    def _cuda_status() -> Literal["available", "unavailable"]:
        return "available" if shutil.which("nvidia-smi") is not None else "unavailable"

    @staticmethod
    def _accelerator_detail(platform_kind: PlatformKind) -> str:
        darwin = platform_kind in {PlatformKind.DARWIN_ARM64, PlatformKind.DARWIN_OTHER}
        if darwin:
            return "Apple unified memory is managed by the MLX resource policy."
        return "CUDA tooling detected." if shutil.which("nvidia-smi") else "No CUDA tooling was detected."


def _module_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class UnslothCapabilityPreflight:
    def __init__(self, probe: CapabilityReadingProbe) -> None:
        self._probe: CapabilityReadingProbe = probe

    def snapshot(self) -> UnslothCapabilitySnapshot:
        reading = self._probe.reading()
        return UnslothCapabilitySnapshot(
            platform=reading.platform,
            system=self._system(reading),
            capabilities=self._capabilities(reading),
        )

    @staticmethod
    def _system(reading: SystemCapabilityReading) -> SystemPreflight:
        disk_status: Literal["sufficient", "insufficient"] = (
            "sufficient" if reading.disk_free_bytes >= MINIMUM_DISK_BYTES else "insufficient"
        )
        return SystemPreflight(
            memory=MemoryPreflight(
                total_bytes=reading.memory_total_bytes,
                available_bytes=reading.memory_available_bytes,
            ),
            disk=DiskPreflight(
                status=disk_status,
                free_bytes=reading.disk_free_bytes,
                minimum_bytes=MINIMUM_DISK_BYTES,
            ),
            accelerator=AcceleratorPreflight(
                kind=reading.accelerator_kind,
                status=reading.accelerator_status,
                detail=reading.accelerator_detail,
            ),
            thermal=ThermalPreflight(state=reading.thermal_state),
        )

    @staticmethod
    def _capabilities(reading: SystemCapabilityReading) -> tuple[ProviderCapabilityRecord, ...]:
        darwin = reading.platform in {PlatformKind.DARWIN_ARM64, PlatformKind.DARWIN_OTHER}
        if darwin:
            return (
                _record(
                    CapabilityOperation.INFERENCE,
                    CapabilityProvider.OLLAMA,
                    reading.ollama_installed,
                    is_default=True,
                ),
                _record(CapabilityOperation.TRAINING, CapabilityProvider.MLX, reading.mlx_installed, is_default=True),
                _record(CapabilityOperation.EXPORT, CapabilityProvider.MLX, reading.mlx_installed, is_default=True),
                _optional_remote_record(CapabilityOperation.TRAINING),
                _optional_remote_record(CapabilityOperation.EXPORT),
            )
        return (
            _record(
                CapabilityOperation.INFERENCE, CapabilityProvider.OLLAMA, reading.ollama_installed, is_default=True
            ),
            _unsloth_record(CapabilityOperation.TRAINING, reading),
            _unsloth_record(CapabilityOperation.EXPORT, reading),
            _record(CapabilityOperation.TRAINING, CapabilityProvider.MLX, available=False, is_default=False),
            _record(CapabilityOperation.EXPORT, CapabilityProvider.MLX, available=False, is_default=False),
        )


def _record(
    operation: CapabilityOperation,
    provider: CapabilityProvider,
    available: bool,
    *,
    is_default: bool,
) -> ProviderCapabilityRecord:
    status: CapabilityStatus = "available" if available else "unavailable"
    detail = "Provider runtime is installed." if available else "Provider runtime is not installed."
    return ProviderCapabilityRecord(
        operation=operation,
        provider=provider,
        status=status,
        is_default=is_default,
        max_concurrent=1,
        detail=detail,
    )


def _unsloth_record(
    operation: CapabilityOperation,
    reading: SystemCapabilityReading,
) -> ProviderCapabilityRecord:
    if not reading.unsloth_installed:
        return _optional_remote_record(operation)
    if not reading.cuda_available:
        return ProviderCapabilityRecord(
            operation=operation,
            provider=CapabilityProvider.UNSLOTH,
            status="unavailable",
            is_default=False,
            max_concurrent=1,
            detail="Unsloth is installed, but CUDA is unavailable for this operation.",
        )
    return ProviderCapabilityRecord(
        operation=operation,
        provider=CapabilityProvider.UNSLOTH,
        status="available",
        is_default=True,
        max_concurrent=1,
        detail="Unsloth and CUDA are available in the configured worker environment.",
    )


def _optional_remote_record(operation: CapabilityOperation) -> ProviderCapabilityRecord:
    return ProviderCapabilityRecord(
        operation=operation,
        provider=CapabilityProvider.UNSLOTH,
        status="unavailable",
        is_default=False,
        max_concurrent=1,
        detail="Unsloth is optional and requires a separately configured local or remote worker.",
    )
