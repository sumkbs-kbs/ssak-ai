"""작업공간 서비스 프로세스의 start/stop/health 수명주기 어댑터."""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from typing import override

from antigravity_k.engine.workspace_service_registry import (
    ServiceNotFoundError,
    ServiceRecord,
    ServiceState,
    WorkspaceServiceRegistry,
)


@dataclass(frozen=True, slots=True)
class ServiceProcessError(Exception):
    hostname: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.hostname}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    hostname: str
    status: ServiceState
    managed: bool
    process_running: bool
    process_id: int | None


class WorkspaceServiceRuntime:
    """실제 subprocess를 추적하고 레지스트리 상태를 동기화한다."""

    def __init__(self, registry: WorkspaceServiceRegistry) -> None:
        self._registry: WorkspaceServiceRegistry = registry
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock: threading.RLock = threading.RLock()

    def start(self, hostname: str) -> ServiceRecord:
        record = self._registry.get(hostname)
        if record.command is None:
            raise ServiceProcessError(hostname, "no start command was registered")
        with self._lock:
            existing = self._processes.get(hostname)
            if existing is not None and existing.poll() is None:
                return self._registry.set_status(hostname, "ready")
            _ = self._processes.pop(hostname, None)
            _ = self._registry.set_status(hostname, "starting")
            try:
                process = subprocess.Popen(
                    list(record.command),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                )
            except OSError as exc:
                _ = self._registry.set_status(hostname, "failed")
                raise ServiceProcessError(hostname, "process could not be started") from exc
            if process.poll() is not None:
                _ = self._registry.set_status(hostname, "failed")
                raise ServiceProcessError(hostname, "process exited during startup")
            self._processes[hostname] = process
            return self._registry.set_status(hostname, "ready")

    def stop(self, hostname: str) -> ServiceRecord:
        _ = self._registry.get(hostname)
        with self._lock:
            process = self._processes.pop(hostname, None)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    _ = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    _ = process.wait(timeout=5)
        return self._registry.set_status(hostname, "stopped")

    def health(self, hostname: str) -> ServiceHealth:
        record = self._registry.get(hostname)
        with self._lock:
            process = self._processes.get(hostname)
            process_running = process is not None and process.poll() is None
            process_id = process.pid if process_running and process is not None else None
        if record.command is not None and record.status == "ready" and not process_running:
            record = self._registry.set_status(hostname, "failed")
        return ServiceHealth(
            hostname=hostname,
            status=record.status,
            managed=record.command is not None,
            process_running=process_running,
            process_id=process_id,
        )

    def stop_all(self) -> None:
        with self._lock:
            hostnames = tuple(self._processes)
        for hostname in hostnames:
            try:
                _ = self.stop(hostname)
            except ServiceNotFoundError:
                _ = self._processes.pop(hostname, None)


__all__ = ["ServiceHealth", "ServiceProcessError", "WorkspaceServiceRuntime"]
