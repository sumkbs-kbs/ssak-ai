"""Binary Tools module."""

import logging
import os
from typing import final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)


@final
class HexDumpTool(BaseTool):
    """바이너리 파일의 특정 영역을 읽어 Hex Dump 포맷(xxd 스타일)으로 반환합니다.

    LLM이 바이너리 매직 넘버나 내부 구조를 텍스트 형태로 읽어낼 수 있게 해줍니다.
    """

    category = ToolCategory.SEARCH
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.SAFE
    icon = "🔍"
    tags = ["binary", "hex", "analysis", "reverse-engineering"]

    def __init__(self):
        """Initialize the HexDumpTool."""
        super().__init__()
        self._name: str = "hex_dump"
        self._description: str = (
            "Reads a binary file and outputs a hex dump (similar to 'xxd'). "
            "Use this tool to analyze executable files (ELF, PE), core dumps, or any binary data "
            "that would normally crash a text editor."
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the binary file to analyze.",
                },
                "offset": {
                    "type": "integer",
                    "description": "The byte offset to start reading from. Default is 0.",
                    "default": 0,
                },
                "length": {
                    "type": "integer",
                    "description": "Number of bytes to read. Default is 256. Max is 4096.",
                    "default": 256,
                },
            },
            "required": ["file_path"],
        }

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            str: The str result.

        """
        file_path_value = kwargs.get("file_path")
        if not isinstance(file_path_value, (str, bytes, os.PathLike)):
            return "Error: file_path is required."
        file_path = file_path_value
        offset_value = kwargs.get("offset", 0)
        offset = offset_value if isinstance(offset_value, int) and not isinstance(offset_value, bool) else 0
        length_value = kwargs.get("length", 256)
        length_int = length_value if isinstance(length_value, int) and not isinstance(length_value, bool) else 256
        length = min(length_int, 4096)

        if not file_path:
            return "Error: file_path is required."
        display_path = os.fsdecode(file_path)
        if not os.path.exists(file_path):
            return f"Error: File '{display_path}' does not exist."

        try:
            with open(file_path, "rb") as f:
                _ = f.seek(offset)
                data = f.read(length)

            if not data:
                return f"Reached EOF at offset {offset}."

            result: list[str] = []
            for i in range(0, len(data), 16):
                chunk = data[i : i + 16]
                hex_offset = f"{offset + i:08x}"
                hex_values = " ".join(f"{b:02x}" for b in chunk)
                hex_values += "   " * (16 - len(chunk))
                hex_values = hex_values[:23] + " " + hex_values[23:]
                ascii_chars = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
                result.append(f"{hex_offset}: {hex_values}  |{ascii_chars}|")

            header = f"Hex Dump of '{display_path}' (Offset: {offset}, Length: {len(data)} bytes):\n"
            header += "-" * 75 + "\n"
            return header + "\n".join(result)

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error reading binary file: {e}"
