# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Imported only by the owned child entry; offline tests exercise the policy directly.
"""Fail observation on external network, model calls, or nonowned writes."""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import TypeVar

from startup_contract import ProbeError

T = TypeVar("T")


@dataclass(slots=True)
class Guard:
    """Mutable counters record audit events without replacing product behavior."""

    owned: Path
    violations: list[str] = field(default_factory=list)
    binds: int = 0
    model_calls: int = 0
    scheduled_ticks: int = 0
    subprocesses: list[str] = field(default_factory=list)

    def deny(self, reason: str) -> None:
        self.violations.append(reason)
        raise ProbeError(reason)

    def audit(self, event: str, args: tuple[T, ...]) -> None:
        if event == "socket.connect":
            self.deny("Child outbound socket attempted")
        if event == "socket.bind":
            address = args[1]
            if address != ("127.0.0.1", 0) or self.binds != 0:
                self.deny("Unexpected child bind")
            self.binds += 1
        if event == "open":
            path, mode, flags = args[:3]
            writable = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            )
            if writable and isinstance(path, str) and path != os.devnull:
                if not Path(path).resolve().is_relative_to(self.owned):
                    self.deny("Nonowned file write: " + path)
        if event in ("os.mkdir", "os.remove", "os.rmdir", "os.rename"):
            for path in args[:2] if event == "os.rename" else args[:1]:
                if isinstance(path, str) and not Path(path).resolve().is_relative_to(self.owned):
                    self.deny("Nonowned filesystem mutation: " + path)
        if event == "subprocess.Popen":
            executable = args[0]
            if isinstance(executable, str):
                self.subprocesses.append(executable)
                if Path(executable).name not in ("git", "code-server"):
                    self.deny("Unexpected child subprocess: " + executable)

    def profile(self, frame: FrameType, event: str, arg: T) -> None:
        if event != "call":
            return
        path, name = frame.f_code.co_filename, frame.f_code.co_name
        if path.endswith("scheduled_job_service.py") and name == "tick":
            self.scheduled_ticks += 1
        provider = path.endswith(
            ("inference_providers.py", "embedding_providers.py", "embeddings.py", "model_manager.py")
        )
        model_method = name in ("generate", "stream_generate", "embed", "load_model", "unload_model", "_load_model")
        download = "huggingface" in path and name in ("snapshot_download", "hf_hub_download")
        if (provider and model_method) or download:
            self.model_calls += 1
            self.deny("Model or download call: " + name)

    def install(self) -> None:
        sys.addaudithook(self.audit)
        sys.setprofile(self.profile)
        threading.setprofile(self.profile)

    def save(self) -> None:
        (self.owned / "guard.json").write_text(
            json.dumps(
                {
                    "violations": self.violations,
                    "binds": self.binds,
                    "model_calls": self.model_calls,
                    "scheduled_ticks": self.scheduled_ticks,
                    "subprocesses": self.subprocesses,
                },
                indent=2,
            )
        )
