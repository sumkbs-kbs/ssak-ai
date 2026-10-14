from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Literal

MemoryScope = Literal["session", "working", "project", "global", "all"]
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class MemoryFactAuthority(IntEnum):
    INFERRED_PREFERENCE = 40
    PROJECT_DECISION = 60
    DURABLE_PREFERENCE = 70
    DURABLE_IDENTITY = 80
    CURRENT_USER = 100


@dataclass(frozen=True, slots=True)
class MemoryFact:
    key: str
    value: str
    source: str
    scope: MemoryScope
    authority: MemoryFactAuthority
    observed_at: float


class UnsupportedMemoryScopeError(ValueError):
    def __init__(self, scope: str) -> None:
        super().__init__(f"Unsupported memory scope: {scope}")


class InvalidRetentionAgeError(ValueError):
    def __init__(self, max_age_days: int) -> None:
        super().__init__(f"max_age_days must be non-negative, got {max_age_days}")


class ProjectMemoryBindingError(ValueError):
    def __init__(self, current: Path, requested: Path) -> None:
        super().__init__(f"Memory manager is bound to {current}, not {requested}")


def normalize_memory_scope(scope: str) -> MemoryScope:
    if scope == "session":
        return "session"
    if scope == "working":
        return "working"
    if scope == "project":
        return "project"
    if scope == "global":
        return "global"
    if scope == "all":
        return "all"
    raise UnsupportedMemoryScopeError(scope)


class MemoryProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def is_external(self) -> bool:
        return False

    @abstractmethod
    def prefetch(self, query: str, session_id: str | None = None) -> str: ...

    @abstractmethod
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None: ...

    def get_tool_schemas(self) -> list[dict[str, JsonValue]]:
        return []

    def on_session_switch(self, _new_session_id: str) -> None:
        return None

    def authoritative_facts(self) -> tuple[MemoryFact, ...]:
        return ()

    def clear(self, scope: MemoryScope = "all") -> int:
        _ = normalize_memory_scope(scope)
        return 0

    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        _ = normalize_memory_scope(scope)
        return []

    def redact(self, scope: MemoryScope = "all") -> int:
        _ = normalize_memory_scope(scope)
        return 0

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise InvalidRetentionAgeError(max_age_days)
        return 0
