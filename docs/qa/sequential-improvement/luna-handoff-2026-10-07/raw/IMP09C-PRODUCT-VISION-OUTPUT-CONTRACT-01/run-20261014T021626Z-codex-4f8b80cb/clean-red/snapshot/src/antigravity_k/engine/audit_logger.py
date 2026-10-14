"""Audit Logger module."""

import json
import logging
import os
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final, Self, TypedDict, cast

logger = logging.getLogger("antigravity_k.engine.audit_logger")


# OCSF Enums and Constants
class ActivityId:
    """Enumeration of auditable activity types."""

    UNKNOWN: Final = 0
    OPEN: Final = 1
    EXECUTE: Final = 2
    READ: Final = 3
    WRITE: Final = 4
    CONNECT: Final = 5


class ActionId:
    """Enumeration of auditable action types."""

    UNKNOWN: Final = 0
    ALLOWED: Final = 1
    DENIED: Final = 2
    ERROR: Final = 3


class SeverityId:
    """Enumeration of audit event severity levels."""

    UNKNOWN: Final = 0
    INFORMATIONAL: Final = 1
    LOW: Final = 2
    MEDIUM: Final = 3
    HIGH: Final = 4
    CRITICAL: Final = 5
    FATAL: Final = 6


class StatusId:
    """Enumeration of audit event outcome statuses."""

    UNKNOWN: Final = 0
    SUCCESS: Final = 1
    FAILURE: Final = 2


class AuditEvent(TypedDict, total=False):
    metadata: dict[str, object]
    class_uid: int
    class_name: str
    severity_id: int
    status_id: int
    time: int
    unmapped: dict[str, object]
    activity_id: int
    action_id: int
    message: str
    finding: dict[str, str]
    event_type: str
    details: dict[str, object]
    timestamp: str


class OCSFEventBuilder:
    """Builds OCSF-format audit event dictionaries."""

    def __init__(self, class_uid: int, class_name: str):
        """Initialize the OCSFEventBuilder.

        Args:
            class_uid (int): int class uid.
            class_name (str): str class name.

        """
        self._unmapped: dict[str, object] = {}
        self.event: AuditEvent = {
            "metadata": {
                "version": "1.1.0",
                "product": {"name": "Ssak-Ai", "vendor_name": "Ssak-Ai"},
            },
            "class_uid": class_uid,
            "class_name": class_name,
            "severity_id": SeverityId.INFORMATIONAL,
            "status_id": StatusId.SUCCESS,
            "time": int(time.time() * 1000),
            "unmapped": self._unmapped,
        }

    def activity(self, activity_id: int) -> Self:
        """Activity.

        Args:
            activity_id (int): int activity id.

        """
        self.event["activity_id"] = activity_id
        return self

    def action(self, action_id: int) -> Self:
        """Set the action.

        Args:
            action_id (int): int action id.

        """
        self.event["action_id"] = action_id
        return self

    def severity(self, severity_id: int) -> Self:
        """Severity.

        Args:
            severity_id (int): int severity id.

        """
        self.event["severity_id"] = severity_id
        return self

    def status(self, status_id: int) -> Self:
        """Status.

        Args:
            status_id (int): int status id.

        """
        self.event["status_id"] = status_id
        return self

    def message(self, msg: str) -> Self:
        """Message.

        Args:
            msg (str): str msg.

        """
        self.event["message"] = msg
        return self

    def unmapped(self, key: str, value: object) -> Self:
        """Unmapped.

        Args:
            key (str): str key.
            value (Any): value.

        """
        self._unmapped[key] = value
        return self

    def build(self) -> AuditEvent:
        """Build.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self.event


class ToolExecutionActivityBuilder(OCSFEventBuilder):
    """Toolexecutionactivitybuilder.

    Bases: OCSFEventBuilder
    """

    def __init__(self):
        """Initialize the ToolExecutionActivityBuilder."""
        super().__init__(1007, "Tool Execution Activity")

    def tool_name(self, name: str) -> Self:
        """Tool Name.

        Args:
            name (str): str name.

        """
        _ = self.unmapped("tool_name", name)
        return self


class SecurityDetectionBuilder(OCSFEventBuilder):
    """Securitydetectionbuilder.

    Bases: OCSFEventBuilder
    """

    def __init__(self):
        """Initialize the SecurityDetectionBuilder."""
        super().__init__(2001, "Security Detection Finding")

    def finding_info(self, title: str, description: str) -> Self:
        """Set finding info.

        Args:
            title (str): str title.
            description (str): str description.

        """
        self.event["finding"] = {"title": title, "desc": description}
        return self


class AuditLogger:
    """OCSF-compliant Audit Logging System."""

    def __init__(self, log_dir: str | Path = "logs"):
        """Initialize the AuditLogger.

        Args:
            log_dir (str | Path): log directory path.

        """
        p = Path(log_dir)
        try:
            if not p.is_absolute() and os.getcwd() == "/":
                from antigravity_k.config import config

                p = config.paths.logs_dir
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            self.log_dir = p
        except OSError:
            fallback_dir = Path.home() / ".antigravity-k" / "logs"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.log_dir = fallback_dir
        self.log_file = self.log_dir / f"audit_ocsf_{datetime.now().strftime('%Y%m')}.jsonl"

    def _mask_sensitive_data(self, data: object) -> object:
        if isinstance(data, dict):
            masked: dict[str, object] = {}
            data_dict = cast(dict[object, object], data)
            for k, v in data_dict.items():
                key = str(k)
                if any(sec in key.lower() for sec in ["key", "token", "password", "secret", "credential"]):
                    masked[key] = "***MASKED***"
                else:
                    masked[key] = self._mask_sensitive_data(v)
            return masked
        elif isinstance(data, list):
            items = cast(list[object], data)
            return [self._mask_sensitive_data(item) for item in items]
        return data

    def log_event(self, event_type: str, details: Mapping[str, object]) -> None:
        """Legacy compatibility method. Routes to OCSF format where possible."""
        masked_details = self._mask_sensitive_data(details)
        masked_mapping = cast(dict[str, object], masked_details) if isinstance(masked_details, dict) else {}
        builder = OCSFEventBuilder(9999, "Legacy Event")
        _ = builder.message(f"Legacy Event: {event_type}")
        for k, v in masked_mapping.items():
            _ = builder.unmapped(k, v)
        event = builder.build()
        event["event_type"] = event_type
        event["details"] = masked_mapping
        event_time = event.get("time")
        timestamp_ms = event_time if isinstance(event_time, (int, float)) else time.time() * 1000
        event["timestamp"] = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
        self.emit(event)

    def emit(self, event_dict: Mapping[str, object]) -> None:
        """Emit an OCSF structured event dictionary.

        JSONL 파일 + SQLite 듀얼 싱크 (Sidabari audit_log.rs 패턴).
        SQLite 실패 시 JSONL만으로 폴백 — 데이터 손실 방지.
        """
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                _ = f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to write audit log")

        # SQLite 듀얼 싱크
        try:
            from antigravity_k.engine.audit_db import get_audit_db

            db = get_audit_db()
            if bool(getattr(db, "_initialized", False)):
                db.insert_from_dict(dict(event_dict))
        except ImportError:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        except Exception as e:
            logger.exception("Unhandled exception")
            # SQLite 실패는 JSONL 적재를 막지 않음
            logger.debug("SQLite dual-sync failed (non-blocking): %s", e)


# Singleton Instance
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Retrieve audit logger.

    Returns:
        AuditLogger: The auditlogger result.

    """
    return audit_logger
