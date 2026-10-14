from __future__ import annotations

from typing import TypedDict

type ActionParamValue = str | int | float | bool | None
type ActionParams = dict[str, ActionParamValue]


class ValidationResult(TypedDict):
    allowed: bool
    reason: str
    requires_hitl: bool


class DangerZoneRatio(TypedDict):
    name: str
    y_min_ratio: float
    y_max_ratio: float
    x_min_ratio: float
    x_max_ratio: float


class DangerZone(TypedDict):
    name: str
    y_min: int
    y_max: int
    x_min: int
    x_max: int


class AuditEntry(TypedDict):
    timestamp: str
    action: str
    params: ActionParams
    allowed: bool
    reason: str
    requires_hitl: bool
