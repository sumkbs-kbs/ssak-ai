"""P02 — legacy(PersistentAgency) adapter 시험. legacy 저장소는 읽기 전용이어야 한다."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.legacy_adapter import (
    KIND_EVENT,
    KIND_OBJECTIVE,
    KIND_TASK,
    LegacyAgencyAdapter,
    LegacyMappingConflict,
    UnmappedLegacyValue,
)
from antigravity_k.engine.cognitive.models import ActionPayload, EventPayload, GoalPayload
from antigravity_k.engine.cognitive.references import REL_ORIGIN, REL_PROJECT, EntityType
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.persistent_agency_store import EventType, Objective, ObjectiveStatus, PersistentAgencyStore

LEGACY_PROJECT = "legacy-project-hash"


def make_agency_db(tmp_path: Path) -> tuple[PersistentAgencyStore, Path]:
    db_path = tmp_path / "agency.db"
    store = PersistentAgencyStore(str(db_path))
    return store, db_path


def make_adapter(tmp_path: Path) -> tuple[LegacyAgencyAdapter, CanonicalStore, PersistentAgencyStore, Path]:
    agency, db_path = make_agency_db(tmp_path)
    canonical = CanonicalStore(tmp_path / "canonical", git_enabled=False)
    return LegacyAgencyAdapter(canonical), canonical, agency, db_path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_event_import_is_idempotent_and_maps_once(tmp_path: Path) -> None:
    adapter, canonical, agency, _ = make_adapter(tmp_path)
    event = agency.append_event(
        LEGACY_PROJECT, "traj-1", "main", None, EventType.OBSERVATION, {"text": "관측"}, "normal"
    )

    first = adapter.import_event(event)
    second = adapter.import_event(event)

    assert first.id == second.id
    assert first.entity_type is EntityType.EVENT
    assert isinstance(first.payload, EventPayload)
    assert first.payload.sequence == event.event_id
    assert first.payload.episode_id == "agency:traj-1"
    assert len(canonical.committed_manifests()) == 1
    assert canonical.rebuild_index() == 1

    reference = adapter.origin_reference(
        KIND_EVENT, f"{LEGACY_PROJECT}:traj-1:{event.event_id}", expected_type=EntityType.EVENT
    )
    assert reference is not None
    assert reference.relation == REL_ORIGIN
    assert reference.target_id == first.id
    assert canonical.resolve(reference.target_id) is not None


def test_mapping_persists_across_adapter_instances(tmp_path: Path) -> None:
    adapter, canonical, agency, _ = make_adapter(tmp_path)
    event = agency.append_event(LEGACY_PROJECT, "traj-1", "main", None, EventType.THOUGHT, {"text": "생각"}, "normal")
    record = adapter.import_event(event)

    reopened = LegacyAgencyAdapter(canonical)
    assert reopened.map_legacy_id(KIND_EVENT, f"{LEGACY_PROJECT}:traj-1:{event.event_id}") == record.id
    assert reopened.import_event(event).id == record.id


def test_changed_legacy_content_is_conflict(tmp_path: Path) -> None:
    adapter, _, agency, _ = make_adapter(tmp_path)
    event = agency.append_event(LEGACY_PROJECT, "traj-1", "main", None, EventType.THOUGHT, {"text": "생각"}, "normal")
    adapter.import_event(event)

    mutated = dataclasses.replace(event, payload={"text": "다른 생각"})
    with pytest.raises(LegacyMappingConflict):
        adapter.import_event(mutated)


def test_unknown_legacy_event_type_rejected(tmp_path: Path) -> None:
    adapter, _, agency, _ = make_adapter(tmp_path)
    event = agency.append_event(LEGACY_PROJECT, "traj-1", "main", None, EventType.FAILURE, {"error": "x"}, "normal")
    mutated = dataclasses.replace(event, event_type="teleport")
    with pytest.raises(UnmappedLegacyValue):
        adapter.import_event(mutated)


def test_objective_and_task_mapping(tmp_path: Path) -> None:
    adapter, canonical, _, _ = make_adapter(tmp_path)
    objective = Objective(
        objective_id="obj-1",
        project_id=LEGACY_PROJECT,
        title="legacy objective",
        description="설명",
        priority=1,
        status=ObjectiveStatus.PENDING,
        trajectory_id="traj-1",
        created_at="2026-09-22T03:00:00+00:00",
        updated_at="2026-09-22T03:00:00+00:00",
    )

    goal = adapter.import_objective(objective)
    assert goal.entity_type is EntityType.GOAL
    assert isinstance(goal.payload, GoalPayload)
    assert goal.payload.statement == "legacy objective"
    assert goal.references == (), "Project record가 없으면 project reference를 만들지 않는다"

    project_record = adapter.ensure_project_record(LEGACY_PROJECT, premise="legacy")
    assert project_record.id == adapter.map_project(LEGACY_PROJECT)
    assert canonical.read(project_record.id) is not None

    action = adapter.import_task_submission(
        "task-1", project_id=LEGACY_PROJECT, prompt_digest="sha256:" + "a" * 64, status="running"
    )
    assert action.entity_type is EntityType.ACTION
    assert isinstance(action.payload, ActionPayload)
    assert action.payload.idempotency_key == "legacy-task:task-1"
    assert str(action.payload.execution_status) == "DISPATCHED"
    assert [reference.relation for reference in action.references] == [REL_PROJECT]
    assert adapter.map_legacy_id(KIND_TASK, "task-1") == action.id
    assert adapter.map_legacy_id(KIND_OBJECTIVE, "obj-1") == goal.id
    assert adapter.origins(KIND_TASK)[0].canonical_id == action.id


def test_unknown_legacy_task_status_rejected(tmp_path: Path) -> None:
    adapter, _, _, _ = make_adapter(tmp_path)
    with pytest.raises(UnmappedLegacyValue):
        adapter.import_task_submission(
            "task-x", project_id=LEGACY_PROJECT, prompt_digest="sha256:" + "b" * 64, status="teleported"
        )


def test_legacy_database_is_not_modified(tmp_path: Path) -> None:
    adapter, _, agency, db_path = make_adapter(tmp_path)
    event = agency.append_event(LEGACY_PROJECT, "traj-1", "main", None, EventType.ACTION, {"tool": "read"}, "normal")
    before_bytes = sha256_file(db_path)
    before_events = len(agency.list_events(LEGACY_PROJECT, "traj-1"))

    adapter.import_event(event)
    adapter.import_task_submission("task-2", project_id=LEGACY_PROJECT, prompt_digest="sha256:" + "c" * 64)

    assert sha256_file(db_path) == before_bytes
    assert len(agency.list_events(LEGACY_PROJECT, "traj-1")) == before_events


def test_project_mapping_is_stable(tmp_path: Path) -> None:
    adapter, _, _, _ = make_adapter(tmp_path)
    first = adapter.map_project(LEGACY_PROJECT)
    assert adapter.map_project(LEGACY_PROJECT) == first
    assert adapter.map_project("other-legacy-project") != first
    assert first.startswith("project:")
