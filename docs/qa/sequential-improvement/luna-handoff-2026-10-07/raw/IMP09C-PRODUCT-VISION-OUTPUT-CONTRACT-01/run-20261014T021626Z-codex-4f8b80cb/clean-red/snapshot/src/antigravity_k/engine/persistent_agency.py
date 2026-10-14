"""Durable, bounded agency primitives inspired by Headlong.

The module deliberately stops at scheduling and context projection.  It does
not execute tools or create an autonomous loop, so callers must continue to
route side effects through the existing task runner and permission gates.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, final, override

from antigravity_k.engine.persistent_agency_store import (
    EventType,
    JsonValue,
    Objective,
    ObjectiveStatus,
    PersistentAgencyStore,
    TrajectoryEvent,
)

_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|(?:token|secret|password|api[_-]?key)\s*[:=]\s*)[^\s,;]+",
)
_RESULT_TEXT_LIMIT: Final[int] = 4_000


@dataclass(frozen=True, slots=True)
class AgencyInputError(Exception):
    """Raised when a required agency boundary value is invalid."""

    field: str

    @override
    def __str__(self) -> str:
        return f"agency field {self.field!r} must not be empty"


@dataclass(frozen=True, slots=True)
class AgencyConfig:
    """Safe defaults for the projection and idle scheduler."""

    enabled: bool = False
    recent_event_limit: int = 12
    summary_event_limit: int = 6
    raw_recall_limit: int = 4
    base_idle_delay_seconds: int = 5
    max_idle_delay_seconds: int = 300
    objective_lease_seconds: int = 900


def persistent_agency_config_from_raw(config: Mapping[str, JsonValue]) -> AgencyConfig:
    """Parse the optional `persistent_agency` configuration section."""
    section = config.get("persistent_agency", {})
    values = section if isinstance(section, dict) else {}

    def setting(name: str, default: int, minimum: int) -> int:
        raw = values.get(name)
        return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= minimum else default

    return AgencyConfig(
        enabled=bool(values.get("enabled", False)),
        recent_event_limit=setting("recent_event_limit", 12, 1),
        summary_event_limit=setting("summary_event_limit", 6, 0),
        raw_recall_limit=setting("raw_recall_limit", 4, 0),
        base_idle_delay_seconds=setting("base_idle_delay_seconds", 5, 0),
        max_idle_delay_seconds=setting("max_idle_delay_seconds", 300, 0),
        objective_lease_seconds=setting("objective_lease_seconds", 900, 1),
    )


@dataclass(frozen=True, slots=True)
class ProjectedContext:
    """Compact model-facing projection with event ids for raw recall."""

    text: str
    event_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    """Deterministic decision; execution remains outside this module."""

    should_wake: bool
    reason: str
    delay_seconds: int
    objective_id: str | None = None


@final
class PersistentAgencyController:
    """Safe facade for Headlong-inspired persistence and scheduling."""

    config: AgencyConfig
    project_root: str
    project_id: str
    store: PersistentAgencyStore

    def __init__(self, project_root: str, config: AgencyConfig | None = None) -> None:
        self.config = config or AgencyConfig()
        self.project_root = str(Path(project_root).resolve())
        self.project_id = self.project_root
        self.store = PersistentAgencyStore(str(Path(self.project_root) / ".antigravity_k" / "agency.db"))

    def append_event(
        self,
        project_id: str,
        trajectory_id: str,
        event_type: EventType,
        payload: Mapping[str, JsonValue],
        branch_id: str = "main",
        parent_event_id: int | None = None,
        sensitivity: str = "normal",
    ) -> TrajectoryEvent:
        self._require_scope(project_id, "project_id")
        self._require_scope(trajectory_id, "trajectory_id")
        safe_payload = self._redact_mapping(payload)
        return self.store.append_event(
            project_id, trajectory_id, branch_id, parent_event_id, event_type, safe_payload, sensitivity
        )

    def record_observation(self, project_id: str, trajectory_id: str, text: str) -> TrajectoryEvent:
        return self.append_event(project_id, trajectory_id, EventType.OBSERVATION, {"text": text})

    def record_thought(self, project_id: str, trajectory_id: str, text: str) -> TrajectoryEvent:
        return self.append_event(project_id, trajectory_id, EventType.THOUGHT, {"text": text})

    def record_summary(self, project_id: str, trajectory_id: str, text: str) -> TrajectoryEvent:
        return self.append_event(project_id, trajectory_id, EventType.SUMMARY, {"text": text})

    def record_external_event(
        self,
        project_id: str,
        trajectory_id: str,
        event_name: str,
        payload: Mapping[str, object] | None = None,
    ) -> TrajectoryEvent:
        """Persist a bounded, redacted observation from an external event source."""
        self._require_scope(event_name, "event_name")
        serialized = json.dumps(payload or {}, ensure_ascii=False, default=str)
        return self.append_event(
            project_id,
            trajectory_id,
            EventType.OBSERVATION,
            {"event_name": event_name, "text": f"{event_name}: {serialized}"},
        )

    def record_task_event(
        self,
        project_id: str,
        trajectory_id: str,
        task_id: str,
        status: str,
        prompt: str = "",
    ) -> TrajectoryEvent:
        """Persist a task lifecycle marker without owning task execution."""
        self._require_scope(task_id, "task_id")
        self._require_scope(status, "status")
        text = f"task {task_id} {status}"
        if prompt.strip():
            text = f"{text}: {prompt}"
        return self.append_event(
            project_id,
            trajectory_id,
            EventType.OBSERVATION,
            {"task_id": task_id, "status": status, "text": text},
        )

    def record_task_result(
        self,
        task_id: str,
        status: str,
        output: str = "",
        error: str = "",
    ) -> TrajectoryEvent | None:
        """Persist one bounded result summary for a mapped objective task."""
        self._require_scope(task_id, "task_id")
        relation = self.store.objective_task(task_id)
        if relation is None or status not in {"done", "failed", "cancelled"}:
            return None
        if not self.store.mark_task_result(task_id, status):
            return None
        _, project_id, trajectory_id = relation
        detail = output if status == "done" else error or output
        detail = detail[:_RESULT_TEXT_LIMIT]
        event_type = EventType.SUMMARY if status == "done" else EventType.FAILURE
        text = f"task {task_id} {status}: {detail}" if detail else f"task {task_id} {status}"
        return self.append_event(
            project_id,
            trajectory_id,
            event_type,
            {"task_id": task_id, "status": status, "text": text},
        )

    def enqueue_objective(
        self, project_id: str, title: str, description: str = "", priority: int = 0, trajectory_id: str = "main"
    ) -> Objective:
        self._require_scope(project_id, "project_id")
        now = datetime.now(UTC).isoformat()
        objective = Objective(
            f"objective_{uuid.uuid4().hex[:12]}",
            project_id,
            title,
            description,
            priority,
            ObjectiveStatus.PENDING,
            trajectory_id,
            now,
            now,
        )
        return self.store.create_objective(objective)

    def claim_next_objective(self, project_id: str) -> Objective | None:
        self._require_scope(project_id, "project_id")
        _ = self.store.reclaim_stale_objectives(self.config.objective_lease_seconds)
        return self.store.claim_next_objective(project_id)

    def complete_objective(self, objective_id: str) -> bool:
        self._require_scope(objective_id, "objective_id")
        return self.store.complete_objective(objective_id)

    def get_objective(self, objective_id: str) -> Objective | None:
        self._require_scope(objective_id, "objective_id")
        return self.store.get_objective(objective_id)

    def list_objectives(self, project_id: str, limit: int = 100) -> list[Objective]:
        self._require_scope(project_id, "project_id")
        return self.store.list_objectives(project_id, limit=limit)

    def requeue_objective(self, objective_id: str) -> bool:
        self._require_scope(objective_id, "objective_id")
        return self.store.requeue_objective(objective_id)

    def bind_objective_task(self, task_id: str, objective_id: str, project_id: str, trajectory_id: str) -> None:
        self._require_scope(task_id, "task_id")
        self._require_scope(objective_id, "objective_id")
        self._require_scope(project_id, "project_id")
        self._require_scope(trajectory_id, "trajectory_id")
        self.store.bind_objective_task(task_id, objective_id, project_id, trajectory_id)

    def reconcile_task_status(self, task_id: str, status: str) -> bool | None:
        self._require_scope(task_id, "task_id")
        relation = self.store.objective_task(task_id)
        if relation is None:
            return None
        objective_id, project_id, trajectory_id = relation
        if status == "done":
            changed = self.complete_objective(objective_id)
            if changed:
                _ = self.record_task_event(project_id, trajectory_id, task_id, "objective_done")
            return changed
        if status in {"failed", "cancelled"}:
            changed = self.requeue_objective(objective_id)
            if changed:
                _ = self.record_task_event(project_id, trajectory_id, task_id, "objective_requeued")
            return changed
        return False

    def list_objective_tasks(self, project_id: str) -> list[str]:
        self._require_scope(project_id, "project_id")
        return self.store.list_objective_tasks(project_id)

    def project_context(self, project_id: str, trajectory_id: str, query: str = "") -> ProjectedContext:
        events = self.store.list_events(project_id, trajectory_id)
        recent = events[-max(1, self.config.recent_event_limit) :]
        summaries = [event for event in events if event.event_type in (EventType.SUMMARY, EventType.DECISION)][
            -max(0, self.config.summary_event_limit) :
        ]
        terms = set(re.findall(r"[\w-]+", query.casefold()))
        recalled = [
            event
            for event in events
            if event not in recent and terms and terms & set(re.findall(r"[\w-]+", self._event_text(event).casefold()))
        ][-max(0, self.config.raw_recall_limit) :]
        selected = {event.event_id: event for event in (*summaries, *recalled, *recent)}
        ordered = tuple(sorted(selected.values(), key=lambda event: event.event_id))
        return ProjectedContext(
            "\n".join(f"[{event.event_type.value}] {self._event_text(event)}" for event in ordered),
            tuple(event.event_id for event in ordered),
        )

    def scheduler_decision(self, project_id: str, idle_cycles: int = 0) -> SchedulerDecision:
        self._require_scope(project_id, "project_id")
        if not self.config.enabled:
            return SchedulerDecision(False, "disabled", 0)
        if self.store.is_paused(project_id):
            return SchedulerDecision(False, "paused", 0)
        if self.store.has_pending_objective(project_id):
            return SchedulerDecision(True, "objective_ready", 0)
        return SchedulerDecision(False, "idle_backoff", self.wakeup_delay(idle_cycles))

    def wakeup_delay(self, idle_cycles: int) -> int:
        cycles = max(0, idle_cycles)
        delay = self.config.base_idle_delay_seconds
        for _ in range(cycles):
            delay *= 2
            if delay >= self.config.max_idle_delay_seconds:
                return self.config.max_idle_delay_seconds
        return min(self.config.max_idle_delay_seconds, max(0, delay))

    def pause(self, project_id: str) -> None:
        self._require_scope(project_id, "project_id")
        self.store.set_paused(project_id, True)

    def resume(self, project_id: str) -> None:
        self._require_scope(project_id, "project_id")
        self.store.set_paused(project_id, False)

    @staticmethod
    def _event_text(event: TrajectoryEvent) -> str:
        value = event.payload.get("text")
        return value if isinstance(value, str) else json.dumps(event.payload, ensure_ascii=False)

    @classmethod
    def _redact_mapping(cls, payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return {str(key): cls._redact_value(value) for key, value in payload.items()}

    @classmethod
    def _redact_value(cls, value: JsonValue) -> JsonValue:
        if isinstance(value, str):
            return _SECRET_RE.sub("[REDACTED]", value)
        if isinstance(value, list):
            return [cls._redact_value(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._redact_value(item) for key, item in value.items()}
        return value

    @staticmethod
    def _require_scope(value: str, field: str) -> None:
        if not value.strip():
            raise AgencyInputError(field)


__all__ = [
    "AgencyConfig",
    "AgencyInputError",
    "EventType",
    "JsonValue",
    "Objective",
    "ObjectiveStatus",
    "PersistentAgencyController",
    "PersistentAgencyStore",
    "ProjectedContext",
    "SchedulerDecision",
    "TrajectoryEvent",
    "persistent_agency_config_from_raw",
]
