"""Durable, bounded operational alert storage for local runtime failures."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Final, Literal, final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

AlertSeverity = Literal["warning", "critical"]


@final
class InvalidAlertLimitError(ValueError):
    """Raised when the durable alert limit is not positive."""

    def __init__(self, max_alerts: int) -> None:
        super().__init__(f"max_alerts must be positive, got {max_alerts}")


@final
class InvalidAlertMessageError(ValueError):
    """Raised when an alert has no meaningful message."""

    def __init__(self) -> None:
        super().__init__("alert message must not be empty")


@final
class OperationalAlertStoreError(RuntimeError):
    """Raised when durable alert data cannot be read or written."""


class OperationalAlert(BaseModel):
    """One persisted warning or critical operational event."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    alert_id: str = Field(min_length=1)
    severity: AlertSeverity
    source: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2_000)
    fingerprint: str = Field(min_length=16, max_length=64)
    created_at: str = Field(min_length=1)
    acknowledged: bool = False


_ALERTS_JSON: Final = TypeAdapter(tuple[OperationalAlert, ...])


@final
class OperationalAlertStore:
    """Persist bounded alerts and expose pending alerts across restarts."""

    def __init__(self, path: str | Path, *, max_alerts: int = 500) -> None:
        if max_alerts < 1:
            raise InvalidAlertLimitError(max_alerts)
        self.path = Path(path)
        self._max_alerts = max_alerts
        self._lock = threading.Lock()

    def record(
        self,
        source: str,
        message: str,
        *,
        severity: AlertSeverity = "warning",
        fingerprint: str | None = None,
    ) -> OperationalAlert:
        """Record an alert unless an identical pending alert already exists."""
        normalized_message = message.strip()
        if not normalized_message:
            raise InvalidAlertMessageError
        normalized_source = source.strip() or "runtime"
        alert_fingerprint = (
            fingerprint
            or hashlib.sha256(
                f"{normalized_source}\x00{normalized_message}".encode("utf-8"),
            ).hexdigest()
        )
        with self._lock:
            alerts = list(self._load())
            for alert in reversed(alerts):
                if alert.fingerprint == alert_fingerprint and not alert.acknowledged:
                    return alert
            alert = OperationalAlert(
                alert_id=hashlib.sha256(
                    f"{alert_fingerprint}\x00{datetime.now(UTC).isoformat()}".encode("utf-8"),
                ).hexdigest()[:24],
                severity=severity,
                source=normalized_source,
                message=normalized_message,
                fingerprint=alert_fingerprint,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._write(self._prune((*alerts, alert)))
            return alert

    def pending(self, limit: int = 100) -> tuple[OperationalAlert, ...]:
        """Return unacknowledged alerts in creation order."""
        return self.list_alerts(limit=limit)

    def list_alerts(
        self,
        *,
        limit: int = 100,
        include_acknowledged: bool = False,
    ) -> tuple[OperationalAlert, ...]:
        if limit < 1:
            return ()
        with self._lock:
            alerts = tuple(alert for alert in self._load() if include_acknowledged or not alert.acknowledged)
        return alerts[:limit]

    def acknowledge(self, alert_ids: Sequence[str]) -> None:
        """Mark the supplied alert IDs as delivered to the user."""
        ids = frozenset(alert_ids)
        if not ids:
            return
        with self._lock:
            updated = tuple(
                alert.model_copy(update={"acknowledged": True}) if alert.alert_id in ids else alert
                for alert in self._load()
            )
            self._write(updated)

    def acknowledge_one(self, alert_id: str) -> OperationalAlert | None:
        normalized_id = alert_id.strip()
        if not normalized_id:
            return None
        with self._lock:
            alerts = self._load()
            target = next(
                (alert for alert in alerts if alert.alert_id == normalized_id and not alert.acknowledged),
                None,
            )
            if target is None:
                return None
            updated_target = target.model_copy(update={"acknowledged": True})
            updated = tuple(updated_target if alert.alert_id == normalized_id else alert for alert in alerts)
            self._write(updated)
            return updated_target

    def _load(self) -> tuple[OperationalAlert, ...]:
        if not self.path.exists():
            return ()
        try:
            return _ALERTS_JSON.validate_json(self.path.read_bytes())
        except (OSError, ValidationError, ValueError) as exc:
            raise OperationalAlertStoreError(f"cannot read alert store: {self.path}") from exc

    def _write(self, alerts: Sequence[OperationalAlert]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = json.dumps(
            [alert.model_dump(mode="json") for alert in alerts],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            _ = temporary_path.write_text(payload, encoding="utf-8")
            _ = temporary_path.replace(self.path)
        except OSError as exc:
            raise OperationalAlertStoreError(f"cannot write alert store: {self.path}") from exc

    def _prune(self, alerts: Sequence[OperationalAlert]) -> tuple[OperationalAlert, ...]:
        if len(alerts) <= self._max_alerts:
            return tuple(alerts)
        pending = tuple(alert for alert in alerts if not alert.acknowledged)
        acknowledged = tuple(alert for alert in alerts if alert.acknowledged)
        slots = max(0, self._max_alerts - len(pending))
        return (*pending, *acknowledged[-slots:])
