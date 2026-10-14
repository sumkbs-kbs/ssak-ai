"""작업공간별 로컬 서비스 주소와 수명주기 상태를 관리한다."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

ServiceState = Literal["starting", "ready", "stopped", "failed"]
_DNS_LABEL = re.compile(r"[^a-z0-9-]+")


class ServiceRegistryError(Exception):
    """서비스 레지스트리 경계에서 발생하는 오류."""


class ServiceConflictError(ServiceRegistryError):
    """같은 결정적 호스트명에 다른 서비스가 등록된 경우."""


class ServiceNotFoundError(ServiceRegistryError):
    """등록되지 않은 서비스에 접근한 경우."""


class InvalidServiceTargetError(ServiceRegistryError):
    """프록시 대상이 로컬 루프백이 아닌 경우."""


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    slug = _DNS_LABEL.sub("-", normalized).strip("-")
    if slug:
        return slug
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"service-{digest}"


def build_service_hostname(service: str, branch: str, project: str) -> str:
    """서비스 메타데이터를 DNS-safe localhost 호스트명으로 변환한다."""
    parts = (_slug(service), _slug(branch), _slug(project))
    label = "--".join(parts)
    if len(label) > 63:
        digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:8]
        label = f"{label[:54].rstrip('-')}-{digest}"
    return f"{label}.localhost"


def validate_service_target(host: str) -> str:
    """프록시 SSRF 경계를 위해 loopback 대상만 허용한다."""
    normalized = host.strip().lower()
    if normalized == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise InvalidServiceTargetError("service target must be localhost or a loopback IP") from exc
    if not address.is_loopback:
        raise InvalidServiceTargetError("service target must be localhost or a loopback IP")
    return normalized


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    service: str
    branch: str
    project: str
    host: str
    port: int
    hostname: str
    status: ServiceState
    command: tuple[str, ...] | None = None
    health_path: str = "/health"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def websocket_base_url(self) -> str:
        return f"ws://{self.host}:{self.port}"


class WorkspaceServiceRegistry:
    """프로세스 수명 동안 작업공간 서비스 등록을 보관하는 thread-safe 레지스트리."""

    def __init__(self) -> None:
        self._records: dict[str, ServiceRecord] = {}
        self._lock: threading.RLock = threading.RLock()

    def register(
        self,
        service: str,
        branch: str,
        project: str,
        port: int,
        host: str = "127.0.0.1",
        status: ServiceState = "ready",
        command: Sequence[str] | None = None,
        health_path: str = "/health",
    ) -> ServiceRecord:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        target = validate_service_target(host)
        command_values = None if command is None else tuple(item.strip() for item in command)
        if command_values is not None and (not command_values or any(not item for item in command_values)):
            raise ValueError("command must contain non-empty arguments")
        normalized_health_path = health_path.strip() or "/"
        if not normalized_health_path.startswith("/"):
            raise ValueError("health_path must start with '/'")
        effective_status: ServiceState = "stopped" if command_values is not None and status == "ready" else status
        hostname = build_service_hostname(service, branch, project)
        candidate = ServiceRecord(
            service=service.strip(),
            branch=branch.strip(),
            project=project.strip(),
            host=target,
            port=port,
            hostname=hostname,
            status=effective_status,
            command=command_values,
            health_path=normalized_health_path,
        )
        with self._lock:
            existing = self._records.get(hostname)
            if existing is not None and existing != candidate:
                raise ServiceConflictError(f"service hostname already registered: {hostname}")
            self._records[hostname] = candidate
        return candidate

    def get(self, hostname: str) -> ServiceRecord:
        with self._lock:
            record = self._records.get(hostname)
        if record is None:
            raise ServiceNotFoundError(f"unknown service hostname: {hostname}")
        return record

    def list(self) -> list[ServiceRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda record: record.hostname)

    def set_status(self, hostname: str, status: ServiceState) -> ServiceRecord:
        with self._lock:
            record = self._records.get(hostname)
            if record is None:
                raise ServiceNotFoundError(f"unknown service hostname: {hostname}")
            updated = ServiceRecord(
                service=record.service,
                branch=record.branch,
                project=record.project,
                host=record.host,
                port=record.port,
                hostname=record.hostname,
                status=status,
                command=record.command,
                health_path=record.health_path,
            )
            self._records[hostname] = updated
            return updated

    def remove(self, hostname: str) -> None:
        with self._lock:
            if hostname not in self._records:
                raise ServiceNotFoundError(f"unknown service hostname: {hostname}")
            del self._records[hostname]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
