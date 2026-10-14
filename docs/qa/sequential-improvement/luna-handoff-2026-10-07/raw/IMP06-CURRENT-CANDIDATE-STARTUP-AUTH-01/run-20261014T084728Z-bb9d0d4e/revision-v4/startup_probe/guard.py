# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Imported only by the owned child entry; offline tests exercise the policy directly.
"""Fail observation on external network, model calls, or nonowned writes."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import TypeVar

from startup_probe.contract import ProbeError

T = TypeVar("T")
_FILE_SHA = "8014815e1028410f48966f1880f99c842a5678cf2fcaa010e8d7e9e498f651d0"
_PLATFORM_SHA = "882e24bdc7bff673962c502d8904cf26d574cf7b1db1e113ecfbcb073aaaeec0"


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
                if executable in ("file", "/usr/bin/file"):
                    expected = [executable, "-b", str(Path(sys.executable).resolve())]
                    environment = args[3]
                    safe_path = isinstance(environment, dict) and environment.get("PATH") == "/usr/bin:/bin"
                    if args[1] != expected or not safe_path:
                        self.deny("Unexpected readonly probe arguments")
                    file_sha = hashlib.sha256(Path("/usr/bin/file").read_bytes()).hexdigest()
                    platform_sha = hashlib.sha256(Path(platform.__file__).read_bytes()).hexdigest()
                    if file_sha != _FILE_SHA or platform_sha != _PLATFORM_SHA:
                        self.deny("Readonly probe implementation drift")
                    self.subprocesses.append(
                        json.dumps({"argv": expected, "file_sha256": file_sha, "platform_sha256": platform_sha})
                    )
                elif Path(executable).name not in ("git", "code-server"):
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
        default_embedding = "embedding_functions" in path and name in ("__call__", "embed_query", "embed_documents")
        local_encoder = "sentence_transformers" in path and name in ("encode", "encode_query", "encode_document")
        if (provider and model_method) or download or default_embedding or local_encoder:
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
