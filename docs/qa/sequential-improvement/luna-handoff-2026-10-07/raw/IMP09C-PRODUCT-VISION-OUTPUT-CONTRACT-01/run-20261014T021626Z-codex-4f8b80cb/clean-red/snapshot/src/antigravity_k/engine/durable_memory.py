from collections.abc import Callable
from typing import final, override

from antigravity_k.engine.memory_contracts import (
    InvalidRetentionAgeError,
    JsonValue,
    MemoryProvider,
    MemoryScope,
    normalize_memory_scope,
)


@final
class DurableMemoryProvider(MemoryProvider):
    _provider_name: str
    _clear_all: Callable[[], int]
    _export_all: Callable[[], list[dict[str, JsonValue]]] | None
    _redact_all: Callable[[], int] | None
    _retention: Callable[[int], int] | None

    def __init__(
        self,
        provider_name: str,
        clear_all: Callable[[], int],
        export_all: Callable[[], list[dict[str, JsonValue]]] | None = None,
        redact_all: Callable[[], int] | None = None,
        retention: Callable[[int], int] | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._clear_all = clear_all
        self._export_all = export_all
        self._redact_all = redact_all
        self._retention = retention

    @property
    @override
    def name(self) -> str:
        return self._provider_name

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        return ""

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        return None

    @override
    def clear(self, scope: MemoryScope = "all") -> int:
        if normalize_memory_scope(scope) == "all":
            return self._clear_all()
        return 0

    @override
    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        if normalize_memory_scope(scope) == "all" and self._export_all is not None:
            return self._export_all()
        return []

    @override
    def redact(self, scope: MemoryScope = "all") -> int:
        if normalize_memory_scope(scope) == "all" and self._redact_all is not None:
            return self._redact_all()
        return 0

    @override
    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise InvalidRetentionAgeError(max_age_days)
        return self._retention(max_age_days) if self._retention is not None else 0
