"""Ssak-Ai: 구조화된 JSON 로거 (Structured JSON Logger).

======================================================
에이전트 시스템 전체의 이벤트를 JSON 형태로 포맷팅하여 저장합니다.
추적성(Traceability) 향상을 위해 세션 ID(Trace ID)와
실행 컨텍스트(Tool, Step 등)를 주입합니다.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Protocol, override


class _LogRecordFields(Protocol):
    __dict__: dict[str, object]


def _extra_fields(record: _LogRecordFields) -> dict[str, object]:
    return record.__dict__


class JSONFormatter(logging.Formatter):
    """표준 로깅을 구조화된 JSON으로 변환하는 커스텀 포매터."""

    def __init__(self, **kwargs: object) -> None:
        """Initialize the JSONFormatter.

        Args:
            **kwargs: kwargs.

        """
        super().__init__()
        self.static_fields: dict[str, object] = kwargs

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Format.

        Args:
            record (logging.LogRecord): logging.LogRecord record.

        Returns:
            str: The str result.

        """
        log_data: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 정적 필드 주입 (예: app_name="antigravity-k")
        log_data.update(self.static_fields)

        # 예외(Exception) 정보 추가
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
            log_data["stack_trace"] = traceback.format_exc()

        # extra로 주입된 추가 필드 (예: logger.info("msg", extra={"tool": "search"}))
        for key, value in _extra_fields(record).items():
            if key not in [
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "message",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
                "color_message",
            ]:
                if isinstance(value, (str, int, float, bool)) or value is None:
                    log_data[key] = value
                else:
                    log_data[key] = str(value)

        return json.dumps(log_data, ensure_ascii=False)


def setup_json_logger(
    log_file_path: str = "logs/agent_json.log",
    level: int = logging.INFO,
) -> logging.Logger:
    """JSON 파일 기반 로거를 설정합니다."""
    import os
    from logging.handlers import TimedRotatingFileHandler

    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # 매일 자정에 로그 로테이션, 최대 30일 보관
    file_handler = TimedRotatingFileHandler(
        log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )

    formatter = JSONFormatter(app_name="antigravity-k")
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()

    # 중복 핸들러 방지
    has_json_handler = any(
        isinstance(h, TimedRotatingFileHandler) and getattr(h, "baseFilename", "").endswith(".log")
        for h in root_logger.handlers
    )

    if not has_json_handler:
        root_logger.addHandler(file_handler)
        root_logger.setLevel(level)

    return logging.getLogger("antigravity_k")
