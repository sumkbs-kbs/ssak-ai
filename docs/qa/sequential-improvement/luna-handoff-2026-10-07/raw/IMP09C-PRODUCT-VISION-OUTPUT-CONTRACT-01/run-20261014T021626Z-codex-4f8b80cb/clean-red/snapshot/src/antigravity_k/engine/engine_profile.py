"""Engine Profile module."""

from enum import Enum


class EngineProfile(str, Enum):
    """Execution profile selected by the preflight validator."""

    STRICT_ENGINEER = "strict_engineer"
    FAST_PROTOTYPER = "fast_prototyper"
