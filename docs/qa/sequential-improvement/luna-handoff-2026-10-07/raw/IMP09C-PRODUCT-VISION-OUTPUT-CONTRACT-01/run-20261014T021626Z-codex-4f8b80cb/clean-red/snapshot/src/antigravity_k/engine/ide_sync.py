"""Ide Sync module."""

import json
import logging
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar, Final, override

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonMap = dict[str, JsonValue]

_JSON_MAP_ADAPTER: Final[TypeAdapter[JsonMap]] = TypeAdapter(JsonMap)


class IDEContextManager:
    """전역 IDE 상태 관리자 (싱글톤)."""

    _instance: ClassVar["IDEContextManager | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _state: dict[str, JsonValue]

    def __new__(cls) -> "IDEContextManager":
        """Create a new instance."""
        with cls._lock:
            instance = cls._instance
            if instance is None:
                instance = super().__new__(cls)
                instance._state = {
                    "active_file": None,
                    "cursor_line": None,
                    "open_files": [],
                }
                cls._instance = instance
        return instance

    def __init__(self) -> None:
        if not hasattr(self, "_state"):
            self._state = {"active_file": None, "cursor_line": None, "open_files": []}

    def update_state(self, new_state: Mapping[str, JsonValue]) -> None:
        """Update state.

        Args:
            new_state (dict[str, Any]): dict[str, Any] new state.

        """
        with self._lock:
            self._state.update(new_state)
            logger.debug("IDE Context updated: %s", self._state)

    def get_state(self) -> dict[str, JsonValue]:
        """Retrieve state.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        with self._lock:
            return dict(self._state)

    def format_prompt(self) -> str:
        """Format prompt.

        Returns:
            str: The str result.

        """
        state = self.get_state()
        active_file = state.get("active_file")
        if not isinstance(active_file, str) or not active_file:
            return ""

        prompt = "\n\n<ADDITIONAL_METADATA>\n"
        prompt += "The user's current state is as follows:\n"
        prompt += f"Active Document: {active_file}\n"
        cursor_line = state.get("cursor_line")
        if cursor_line:
            prompt += f"Cursor is on line: {cursor_line}\n"
        open_files = state.get("open_files")
        if isinstance(open_files, list) and open_files:
            prompt += "Other open documents:\n"
            for file_name in open_files:
                if isinstance(file_name, str) and file_name != active_file:
                    prompt += f"- {file_name}\n"
        prompt += "</ADDITIONAL_METADATA>\n"
        return prompt


class IDESyncHandler(BaseHTTPRequestHandler):
    """Idesynchandler.

    Bases: BaseHTTPRequestHandler
    """

    def do_POST(self) -> None:
        """Do Post."""
        if self.path == "/update":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    payload = _JSON_MAP_ADAPTER.validate_json(post_data)
                    IDEContextManager().update_state(payload)

                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    _ = self.wfile.write(b'{"status": "ok"}')
                    return
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.warning("Failed to decode IDE Sync JSON payload: %s", e)

        self.send_response(400)
        self.end_headers()
        _ = self.wfile.write(b'{"status": "error", "message": "Invalid JSON"}')

    @override
    def log_message(self, format: str, *args: JsonValue) -> None:
        """Log Message.

        Args:
            format: format.
            *args: args.

        """
        # HTTP 로그 끄기
        pass


def start_ide_sync_server(port: int = 54321) -> threading.Thread:
    """백그라운드 스레드에서 IDE Sync HTTP 서버를 시작합니다."""

    def run_server() -> None:
        try:
            server = HTTPServer(("127.0.0.1", port), IDESyncHandler)
            logger.info("IDE Sync Server started on port %s", port)
            server.serve_forever()
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - background server boundary
            logger.exception("Failed to start IDE Sync Server on port %s", port)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
