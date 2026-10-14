from __future__ import annotations

import platform
from typing import Literal

from antigravity_k.engine.provider_adapters.unsloth_capability_contracts import PlatformKind

TrainingPlatform = Literal["mlx", "unsloth"]


def host_platform() -> PlatformKind:
    if platform.system() != "Darwin":
        return PlatformKind.NON_DARWIN
    if platform.machine() == "arm64":
        return PlatformKind.DARWIN_ARM64
    return PlatformKind.DARWIN_OTHER


def default_training_platform(platform: PlatformKind) -> TrainingPlatform:
    darwin = platform in {PlatformKind.DARWIN_ARM64, PlatformKind.DARWIN_OTHER}
    return "mlx" if darwin else "unsloth"
