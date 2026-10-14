from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class FakeTrainingLaunch(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    argv: tuple[str, ...]
    data_dir: Path
