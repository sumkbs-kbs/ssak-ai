from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, final

logger = logging.getLogger(__name__)

RetentionLimitName = Literal["max_artifacts", "max_total_bytes"]


@final
class InvalidArtifactRetentionLimitError(ValueError):
    """Raised when a context artifact retention limit is not positive."""

    def __init__(self, limit_name: RetentionLimitName, value: int):
        self.limit_name: RetentionLimitName = limit_name
        self.value: int = value
        super().__init__(f"{limit_name} must be positive, got {value}")


@final
@dataclass(frozen=True, slots=True)
class ArtifactRetentionPolicy:
    """Bound generated context artifacts by count and aggregate disk usage."""

    max_artifacts: int = 256
    max_total_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_artifacts < 1:
            raise InvalidArtifactRetentionLimitError("max_artifacts", self.max_artifacts)
        if self.max_total_bytes < 1:
            raise InvalidArtifactRetentionLimitError("max_total_bytes", self.max_total_bytes)

    def prune(self, root: Path, current_path: Path) -> None:
        entries: list[tuple[Path, int, int]] = []
        for path in root.glob("artifact-*.json"):
            try:
                stat = path.stat()
            except OSError as error:
                logger.warning("Could not inspect context artifact %s: %s", path, error)
                continue
            entries.append((path, stat.st_size, stat.st_mtime_ns))

        entries.sort(key=lambda entry: (entry[2], entry[0].name), reverse=True)
        current = next((entry for entry in entries if entry[0] == current_path), None)
        if current is None:
            return
        ordered = [current, *(entry for entry in entries if entry[0] != current_path)]
        kept_count = 0
        kept_bytes = 0
        for path, size, _modified_at in ordered:
            within_limits = kept_count < self.max_artifacts and kept_bytes + size <= self.max_total_bytes
            if path == current_path or within_limits:
                kept_count += 1
                kept_bytes += size
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                logger.warning("Could not prune context artifact %s: %s", path, error)
