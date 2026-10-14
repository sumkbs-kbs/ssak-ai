from collections.abc import Mapping
from typing import Final

IMPORTANCE_WEIGHTS: Final[Mapping[str, float]] = {
    "system": 1.0,
    "user": 0.9,
    "tool": 0.8,
    "assistant": 0.5,
}

TASK_COMPRESSION: Final[Mapping[str, Mapping[str, int]]] = {
    "SEARCH": {"keep_last_n": 4, "max_tool_chars": 2000},
    "CODE": {"keep_last_n": 8, "max_tool_chars": 4000},
    "ANALYSIS": {"keep_last_n": 6, "max_tool_chars": 3000},
    "CREATIVE": {"keep_last_n": 6, "max_tool_chars": 2000},
    "GENERAL": {"keep_last_n": 6, "max_tool_chars": 3000},
}
