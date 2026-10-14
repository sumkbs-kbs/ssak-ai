from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar


def _empty_json_map() -> dict[str, object]:
    return {}


ToolArgument = TypeVar("ToolArgument")


class Permission(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    risk_level: str
    category: str = "custom"
    description: str = ""
    requires_approval: bool = False
    parameters_schema: Mapping[str, object] = field(default_factory=_empty_json_map)


@dataclass(frozen=True, slots=True)
class ToolInvocation(Generic[ToolArgument]):
    spec: ToolSpec
    arguments: Mapping[str, ToolArgument]
    objective: str = ""


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    spec: ToolSpec
    permission: Permission
    source: str
    reason: str
    # WS-02: path inspected by the gate (same absolute path tools must open).
    inspected_path: str | None = None
    executed_path: str | None = None

    @property
    def allows_execution(self) -> bool:
        return self.permission is Permission.ALLOW

    @property
    def requires_approval(self) -> bool:
        return self.permission is Permission.PROMPT

    @property
    def is_denied(self) -> bool:
        return self.permission is Permission.DENY

    @property
    def path_correlated(self) -> bool:
        if self.inspected_path is None or self.executed_path is None:
            return self.inspected_path is None and self.executed_path is None
        return self.inspected_path == self.executed_path
