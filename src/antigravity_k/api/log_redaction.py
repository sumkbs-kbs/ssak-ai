"""Redact ticket/token query values from server logs (uvicorn access/error and app loggers)."""

from __future__ import annotations

import logging
import re

_SECRET_QUERY = re.compile(r"(?i)\b(ticket|token|access_token|refresh_token)=([^&\s\"']+)")


def redact(text: str) -> str:
    return _SECRET_QUERY.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)


class SecretQueryRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - never drop a log line
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


_FILTER = SecretQueryRedactionFilter()


def install() -> None:
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn", ""):
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
        for handler in logger.handlers:
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)
