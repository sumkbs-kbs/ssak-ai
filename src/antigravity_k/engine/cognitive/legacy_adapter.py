"""Legacy adapter (P02) — 기존 저장소 ID를 canonical record에 연결한다.

계약:
- 기존 SQLite/PersistentAgency 데이터는 **읽기 전용**이다. 이 adapter는 legacy DB를 수정하지 않는다.
- legacy ID → canonical ID mapping은 append-only manifest로 보존한다. 재매핑·덮어쓰기는 거부한다.
- 같은 legacy 원자료를 다시 import하면 같은 canonical ID를 돌려주고 digest가 다르면 충돌로 기록한다.
- reference는 mapping이 존재할 때만 만들어진다. origin reference는 계보 표시이며 권한이 아니다.

lock은 store와 같은 file(`.git/.agk_vault.lock`)을 사용한다. 별도 lock 순서를 만들지 않는다.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast, final

from filelock import SoftFileLock

from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    ActionPayload,
    EventPayload,
    GoalPayload,
    LoopState,
    Producer,
    ProducerKind,
    ProjectPayload,
    Record,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.references import (
    REL_ORIGIN,
    REL_PROJECT,
    EntityType,
    Reference,
    new_id,
)
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest

MAP_VERSION: Final[str] = "1.0"
MAP_RELATIVE_PATH: Final[str] = ".cognitive/legacy/agency_map.json"

KIND_PROJECT: Final[str] = "project"
KIND_EVENT: Final[str] = "event"
KIND_OBJECTIVE: Final[str] = "objective"
KIND_TASK: Final[str] = "task"

#: legacy trajectory event type → 운영 루프 상태. 미정의 타입은 조용히 넘기지 않고 거부한다.
LEGACY_EVENT_STATE: Final[Mapping[str, LoopState]] = {
    "observation": LoopState.OBSERVE,
    "thought": LoopState.THINK,
    "decision": LoopState.COMMIT,
    "action": LoopState.ACTION,
    "action_result": LoopState.OBSERVE,
    "summary": LoopState.EXPERIENCE,
    "failure": LoopState.BRAIN_FAILED,
}

LEGACY_TASK_STATUS: Final[Mapping[str, ActionExecutionStatus]] = {
    "queued": ActionExecutionStatus.PLANNED,
    "running": ActionExecutionStatus.DISPATCHED,
    "done": ActionExecutionStatus.SUCCEEDED,
    "failed": ActionExecutionStatus.FAILED,
    "cancelled": ActionExecutionStatus.CANCELLED,
    "unknown": ActionExecutionStatus.UNKNOWN,
}


class LegacyAdapterError(ValueError):
    """legacy 연결 계약 위반."""


class LegacyMappingConflict(LegacyAdapterError):
    """같은 legacy ID가 다른 내용으로 다시 들어왔다(append-only 위반 신호)."""


class UnmappedLegacyValue(LegacyAdapterError):
    """legacy enum/type을 canonical 상태로 옮길 수 없다."""


class LegacyTrajectoryEvent(Protocol):
    @property
    def event_id(self) -> int: ...

    @property
    def project_id(self) -> str: ...

    @property
    def trajectory_id(self) -> str: ...

    @property
    def parent_event_id(self) -> int | None: ...

    @property
    def event_type(self) -> object: ...

    @property
    def payload(self) -> Mapping[str, object]: ...


class LegacyObjective(Protocol):
    @property
    def objective_id(self) -> str: ...

    @property
    def project_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def trajectory_id(self) -> str: ...


@dataclass(frozen=True, slots=True)
class LegacyOrigin:
    kind: str
    legacy_id: str
    canonical_id: str
    digest: str


@final
class LegacyAgencyAdapter:
    """PersistentAgency event/objective/task를 canonical record로 연결한다."""

    def __init__(
        self,
        store: CanonicalStore,
        *,
        mapping_path: Path | None = None,
        actor_id: str = "body:legacy-adapter",
        lock_timeout: float = 30.0,
    ) -> None:
        self.store = store
        self.mapping_path = mapping_path if mapping_path is not None else store.root / MAP_RELATIVE_PATH
        self.producer = Producer(kind=ProducerKind.BODY, actor_id=actor_id)
        self._file_lock = SoftFileLock(str(store.lock_path), timeout=lock_timeout)

    # ── mapping manifest ────────────────────────────────
    def _load(self) -> dict[str, object]:
        if not self.mapping_path.exists():
            return {"version": MAP_VERSION, KIND_PROJECT: {}, KIND_EVENT: {}, KIND_OBJECTIVE: {}, KIND_TASK: {}}
        loaded = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise LegacyAdapterError(f"legacy mapping is not a mapping: {self.mapping_path}")
        data = cast(dict[str, object], loaded)
        for kind in (KIND_PROJECT, KIND_EVENT, KIND_OBJECTIVE, KIND_TASK):
            data.setdefault(kind, {})
        return data

    def _save(self, data: Mapping[str, object]) -> None:
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.mapping_path.with_name(f".{self.mapping_path.name}.tmp-{uuid.uuid4().hex}")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.mapping_path)

    def _bucket(self, data: Mapping[str, object], kind: str) -> dict[str, object]:
        bucket = data.get(kind)
        if not isinstance(bucket, dict):
            raise LegacyAdapterError(f"legacy mapping bucket missing: {kind}")
        return cast(dict[str, object], bucket)

    def map_legacy_id(self, kind: str, legacy_id: str) -> str | None:
        entry = self._bucket(self._load(), kind).get(legacy_id)
        if entry is None:
            return None
        if isinstance(entry, str):
            return entry
        return str(cast(Mapping[str, object], entry).get("canonical_id"))

    def origins(self, kind: str) -> tuple[LegacyOrigin, ...]:
        origins: list[LegacyOrigin] = []
        for legacy_id, entry in sorted(self._bucket(self._load(), kind).items()):
            if not isinstance(entry, dict):
                continue
            record = cast(Mapping[str, object], entry)
            origins.append(
                LegacyOrigin(
                    kind=kind,
                    legacy_id=legacy_id,
                    canonical_id=str(record.get("canonical_id")),
                    digest=str(record.get("digest", "")),
                )
            )
        return tuple(origins)

    def origin_reference(self, kind: str, legacy_id: str, *, expected_type: EntityType) -> Reference | None:
        canonical_id = self.map_legacy_id(kind, legacy_id)
        if canonical_id is None:
            return None
        return Reference(relation=REL_ORIGIN, target_id=canonical_id, expected_type=expected_type)

    def map_project(self, legacy_project_id: str) -> str:
        """legacy project 문자열을 canonical project ID로 고정 매핑한다."""

        with self._file_lock:
            data = self._load()
            projects = self._bucket(data, KIND_PROJECT)
            existing = projects.get(legacy_project_id)
            if isinstance(existing, str) and existing:
                return existing
            canonical_id = new_id(EntityType.PROJECT)
            projects[legacy_project_id] = canonical_id
            self._save(data)
            return canonical_id

    def ensure_project_record(self, legacy_project_id: str, *, premise: str) -> Record:
        """canonical Project record를 만들거나 기존 것을 돌려준다."""

        canonical_id = self.map_project(legacy_project_id)
        existing = self.store.read(canonical_id)
        if existing is not None:
            return existing
        record = Record.create(
            entity_type=EntityType.PROJECT,
            project_id=canonical_id,
            producer=self.producer,
            payload=ProjectPayload(name="legacy-project", premise=premise),
            record_id=canonical_id,
        )
        self.store.commit_records([record], transaction_id=f"legacy-project-{uuid.uuid4().hex}")
        return record

    # ── import ──────────────────────────────────────────
    def import_event(self, event: LegacyTrajectoryEvent, *, project_id: str | None = None) -> Record:
        legacy_project = project_id if project_id is not None else event.project_id
        legacy_key = f"{legacy_project}:{event.trajectory_id}:{event.event_id}"
        state = LEGACY_EVENT_STATE.get(str(event.event_type))
        if state is None:
            raise UnmappedLegacyValue(f"unknown legacy event type: {event.event_type}")

        digest_payload = {
            "kind": KIND_EVENT,
            "legacy_key": legacy_key,
            "event_type": str(event.event_type),
            "payload": _stable(event.payload),
            "parent_event_id": event.parent_event_id,
        }
        canonical_project = self.map_project(legacy_project)
        return self._map_and_commit(
            kind=KIND_EVENT,
            legacy_id=legacy_key,
            digest_source=digest_payload,
            canonical_project=canonical_project,
            expected_type=EntityType.EVENT,
            build=lambda record_id: Record.create(
                entity_type=EntityType.EVENT,
                project_id=canonical_project,
                producer=self.producer,
                payload=EventPayload(
                    sequence=event.event_id,
                    episode_id=f"agency:{event.trajectory_id}",
                    state=state,
                    caused_by=str(event.parent_event_id) if event.parent_event_id is not None else None,
                    state_revision=max(event.event_id, 1),
                ),
                references=self._project_reference(canonical_project, entity_type=EntityType.EVENT),
                record_id=record_id,
            ),
        )

    def import_objective(self, objective: LegacyObjective, *, project_id: str | None = None) -> Record:
        legacy_project = project_id if project_id is not None else objective.project_id
        digest_payload = {
            "kind": KIND_OBJECTIVE,
            "legacy_id": objective.objective_id,
            "title": objective.title,
            "description": objective.description,
            "trajectory_id": objective.trajectory_id,
        }
        canonical_project = self.map_project(legacy_project)
        return self._map_and_commit(
            kind=KIND_OBJECTIVE,
            legacy_id=objective.objective_id,
            digest_source=digest_payload,
            canonical_project=canonical_project,
            expected_type=EntityType.GOAL,
            build=lambda record_id: Record.create(
                entity_type=EntityType.GOAL,
                project_id=canonical_project,
                producer=self.producer,
                payload=GoalPayload(
                    statement=objective.title or objective.objective_id,
                    success_criteria=(),
                    constraints=(),
                ),
                references=self._project_reference(canonical_project, entity_type=EntityType.GOAL),
                record_id=record_id,
            ),
        )

    def import_task_submission(
        self,
        task_id: str,
        *,
        project_id: str,
        prompt_digest: str,
        status: str = "running",
        tool: str = "legacy_task_runner",
    ) -> Record:
        """legacy background task 제출을 canonical Action으로 기록한다(제출 idempotency 분리)."""

        execution_status = LEGACY_TASK_STATUS.get(status)
        if execution_status is None:
            raise UnmappedLegacyValue(f"unknown legacy task status: {status}")
        canonical_project = self.map_project(project_id)
        digest_payload = {
            "kind": KIND_TASK,
            "legacy_id": task_id,
            "prompt_digest": prompt_digest,
            "tool": tool,
        }
        return self._map_and_commit(
            kind=KIND_TASK,
            legacy_id=task_id,
            digest_source=digest_payload,
            canonical_project=canonical_project,
            expected_type=EntityType.ACTION,
            build=lambda record_id: Record.create(
                entity_type=EntityType.ACTION,
                project_id=canonical_project,
                producer=self.producer,
                payload=ActionPayload(
                    tool=tool,
                    args_digest=prompt_digest,
                    scope="legacy-task-runner",
                    risk_profile=RiskProfile(),
                    idempotency_key=f"legacy-task:{task_id}",
                    execution_status=execution_status,
                ),
                references=self._project_reference(canonical_project, entity_type=EntityType.ACTION),
                record_id=record_id,
            ),
        )

    # ── 내부 ────────────────────────────────────────────
    def _project_reference(self, canonical_project: str, *, entity_type: EntityType) -> tuple[Reference, ...]:
        if same_enum(entity_type, EntityType.PROJECT):
            return ()
        if self.store.resolve(canonical_project) is None:
            return ()
        return (Reference(relation=REL_PROJECT, target_id=canonical_project, expected_type=EntityType.PROJECT),)

    def _map_and_commit(
        self,
        *,
        kind: str,
        legacy_id: str,
        digest_source: Mapping[str, object],
        canonical_project: str,
        expected_type: EntityType,
        build: Callable[[str], Record],
    ) -> Record:
        digest = canonical_digest(digest_source)

        with self._file_lock:
            data = self._load()
            bucket = self._bucket(data, kind)
            existing = bucket.get(legacy_id)
            if isinstance(existing, dict):
                entry = cast(Mapping[str, object], existing)
                if entry.get("digest") != digest:
                    raise LegacyMappingConflict(
                        f"legacy {kind} {legacy_id} changed after mapping: {entry.get('digest')} -> {digest}"
                    )
                record = self.store.read(str(entry.get("canonical_id")))
                if record is None:
                    raise LegacyAdapterError(f"mapped record is not committed: {entry.get('canonical_id')}")
                return record

            record_id = new_id(expected_type)
            record = build(record_id)
            if record.project_id != canonical_project:
                raise LegacyAdapterError(f"record project mismatch: {record.project_id} != {canonical_project}")
            bucket[legacy_id] = {"canonical_id": record_id, "digest": digest}
            self._save(data)

        self.store.commit_records([record], transaction_id=f"legacy-{kind}-{uuid.uuid4().hex}")
        return record


def _stable(value: object) -> object:
    """digest 계산용 정규화. dict/list는 정렬하고 그 외는 문자열로 둔다."""

    if isinstance(value, Mapping):
        return {
            str(key): _stable(item)
            for key, item in sorted(cast(Mapping[object, object], value).items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in cast(list[object], value)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


__all__ = [
    "KIND_EVENT",
    "KIND_OBJECTIVE",
    "KIND_PROJECT",
    "KIND_TASK",
    "LEGACY_EVENT_STATE",
    "LEGACY_TASK_STATUS",
    "LegacyAdapterError",
    "LegacyAgencyAdapter",
    "LegacyMappingConflict",
    "LegacyObjective",
    "LegacyOrigin",
    "LegacyTrajectoryEvent",
    "UnmappedLegacyValue",
]
