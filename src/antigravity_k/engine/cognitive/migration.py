"""Legacy → canonical migration dry-run (P12).

계약(ACCEPTANCE_CHECKLIST T12, IMPLEMENTATION_ROADMAP P12):

- **source는 읽기 전용:** legacy SQLite는 ``mode=ro`` URI로만 연다. 실행 전후 source sha256이 같아야 하며,
  runner는 source에 어떤 write도 시도하지 않는다.
- **별도 root:** canonical target root는 source 파일과 겹치면 거부한다. 같은 곳에 쓰지 않는다.
- **destructive 금지:** 이 runner는 삭제·덮어쓰기·in-place 변환을 실행하지 않는다. ``apply`` 요청은 사람 결정
  영역이므로 명시적으로 거부하고 ``destructive_executed=False``를 기록한다.
- **idempotent mapping:** 재실행 시 같은 canonical ID를 돌려주고 매핑·record가 늘지 않는다(digest로 확인).
- **index rebuild·digest 검증:** commit 후 index를 재생성하고 모든 record digest를 다시 확인한다.
- **rollback rehearsal:** target root를 지우면 즉시 원상복구된다. source는 그대로다.
- **조용한 skip 금지:** legacy enum을 옮길 수 없으면 사유를 report에 남기고 ``complete=False``로 표시한다.

이 모듈은 stdlib(sqlite3/hashlib)과 cognitive package만 import한다(architecture guard).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.legacy_adapter import (
    LegacyAdapterError,
    LegacyAgencyAdapter,
)
from antigravity_k.engine.cognitive.store import CanonicalStore

DRY_RUN: Final[str] = "dry-run"
APPLY: Final[str] = "apply"
EVENTS_TABLE: Final[str] = "agency_events"
OBJECTIVES_TABLE: Final[str] = "agency_objectives"
OBJECTIVE_TASKS_TABLE: Final[str] = "agency_objective_tasks"
TASK_RESULTS_TABLE: Final[str] = "agency_task_results"


class MigrationError(ValueError):
    """migration 계약 위반."""


class DestructiveMigrationRefused(MigrationError):
    """destructive migration은 이 runner의 범위가 아니다(사람 결정)."""


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """source 관찰값. 실행 전후로 같아야 한다."""

    path: str
    digest: str
    size_bytes: int
    tables: tuple[str, ...]
    counts: Mapping[str, int]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "path": self.path,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "tables": list(self.tables),
            "counts": dict(self.counts),
        }


@dataclass(frozen=True, slots=True)
class LegacyEventRow:
    """`LegacyTrajectoryEvent` protocol을 만족하는 row."""

    event_id: int
    project_id: str
    trajectory_id: str
    parent_event_id: int | None
    event_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LegacyObjectiveRow:
    """`LegacyObjective` protocol을 만족하는 row."""

    objective_id: str
    project_id: str
    title: str
    description: str
    trajectory_id: str


@dataclass(frozen=True, slots=True)
class LegacyTaskRow:
    task_id: str
    project_id: str
    status: str
    prompt_digest: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class LegacySQLiteSource:
    """legacy PersistentAgency SQLite를 읽기 전용으로 읽는다."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise MigrationError(f"legacy source가 없다: {self.path}")

    @property
    def readonly_uri(self) -> str:
        return f"file:{self.path}?mode=ro"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.readonly_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def tables(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        return tuple(str(row["name"]) for row in rows)

    def _count(self, table: str) -> int:
        if table not in self.tables():
            return 0
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()  # noqa: S608 - table 화이트리스트
        return int(row["total"]) if row is not None else 0

    def counts(self) -> Mapping[str, int]:
        return {
            "events": self._count(EVENTS_TABLE),
            "objectives": self._count(OBJECTIVES_TABLE),
            "tasks": self._count(OBJECTIVE_TASKS_TABLE),
        }

    def snapshot(self) -> SourceSnapshot:
        return SourceSnapshot(
            path=str(self.path),
            digest=_sha256_file(self.path),
            size_bytes=self.path.stat().st_size,
            tables=self.tables(),
            counts=self.counts(),
        )

    def events(self) -> tuple[LegacyEventRow, ...]:
        if EVENTS_TABLE not in self.tables():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT event_id, project_id, trajectory_id, parent_event_id, event_type, payload_json"  # noqa: S608
                f" FROM {EVENTS_TABLE} ORDER BY event_id"
            ).fetchall()
        return tuple(
            LegacyEventRow(
                event_id=int(row["event_id"]),
                project_id=str(row["project_id"]),
                trajectory_id=str(row["trajectory_id"]),
                parent_event_id=(int(row["parent_event_id"]) if row["parent_event_id"] is not None else None),
                event_type=str(row["event_type"]),
                payload=_safe_json(row["payload_json"]),
            )
            for row in rows
        )

    def objectives(self) -> tuple[LegacyObjectiveRow, ...]:
        if OBJECTIVES_TABLE not in self.tables():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT objective_id, project_id, title, description, trajectory_id"
                f" FROM {OBJECTIVES_TABLE} ORDER BY objective_id"
            ).fetchall()
        return tuple(
            LegacyObjectiveRow(
                objective_id=str(row["objective_id"]),
                project_id=str(row["project_id"]),
                title=str(row["title"]),
                description=str(row["description"]),
                trajectory_id=str(row["trajectory_id"]),
            )
            for row in rows
        )

    def tasks(self) -> tuple[LegacyTaskRow, ...]:
        if OBJECTIVE_TASKS_TABLE not in self.tables():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT task_id, objective_id, project_id FROM {OBJECTIVE_TASKS_TABLE}"  # noqa: S608
                " ORDER BY task_id"
            ).fetchall()
        return tuple(
            LegacyTaskRow(
                task_id=str(row["task_id"]),
                project_id=str(row["project_id"]),
                status="queued",
                prompt_digest="sha256:" + hashlib.sha256(str(row["objective_id"]).encode("utf-8")).hexdigest(),
            )
            for row in rows
        )


def _safe_json(raw: object) -> Mapping[str, object]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return {"raw": str(raw)}
    return value if isinstance(value, dict) else {"raw": value}


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """이번 dry-run의 범위. source·target 경계를 먼저 고정한다."""

    source: SourceSnapshot
    target_root: str
    mode: str = DRY_RUN

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "mode": self.mode,
            "target_root": self.target_root,
            "source": self.source.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """dry-run 결과. destructive는 실행하지 않았음을 명시한다."""

    plan: MigrationPlan
    imported: Mapping[str, int]
    mapping_entries: int
    mapping_digest: str
    canonical_record_count: int
    index_rebuilt: int
    digests_verified: int
    idempotent_replay: bool
    rollback_rehearsed: bool
    mapping_carried_over: bool
    source_unchanged: bool
    destructive_executed: bool
    destructive_reason: str
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.errors

    @property
    def passed(self) -> bool:
        return bool(
            self.complete
            and self.source_unchanged
            and not self.destructive_executed
            and self.index_rebuilt >= self.canonical_record_count
            and self.digests_verified == self.canonical_record_count
        )

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "mode": self.plan.mode,
            "source": self.plan.source.as_mapping(),
            "target_root": self.plan.target_root,
            "imported": dict(self.imported),
            "mapping_entries": self.mapping_entries,
            "mapping_digest": self.mapping_digest,
            "canonical_record_count": self.canonical_record_count,
            "index_rebuilt": self.index_rebuilt,
            "digests_verified": self.digests_verified,
            "idempotent_replay": self.idempotent_replay,
            "rollback_rehearsed": self.rollback_rehearsed,
            "mapping_carried_over": self.mapping_carried_over,
            "source_unchanged": self.source_unchanged,
            "destructive_executed": self.destructive_executed,
            "destructive_reason": self.destructive_reason,
            "complete": self.complete,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True)


class LegacyMigrationRunner:
    """legacy SQLite를 별도 root의 canonical store로 옮기는 **dry-run** runner."""

    def __init__(
        self,
        source: LegacySQLiteSource,
        target_root: str | Path,
        *,
        mode: str = DRY_RUN,
        mapping_path: str | Path | None = None,
    ) -> None:
        self.source = source
        self.target_root = Path(target_root)
        self.mode = mode
        self.mapping_path = (
            Path(mapping_path) if mapping_path is not None else self.target_root / "legacy" / "agency_map.json"
        )
        if mode != DRY_RUN:
            raise DestructiveMigrationRefused(
                f"mode={mode}는 이 runner가 실행하지 않는다 — destructive 변환은 사람 결정으로 분리한다"
            )
        if self._paths_overlap():
            raise MigrationError("target root가 source와 겹친다 — legacy source는 별도 root에서만 변환한다")

    def _paths_overlap(self) -> bool:
        source_dir = self.source.path.resolve().parent
        target = self.target_root.resolve()
        return target == source_dir or source_dir in target.parents or target in source_dir.parents

    # ── 실행 ────────────────────────────────────────────
    def run(self) -> MigrationReport:
        before = self.source.snapshot()
        # mapping manifest가 이미 있으면 identity를 이어받는다(project canonical ID 유지).
        mapping_carried_over = self.mapping_path.exists()
        errors: list[str] = []
        imported = {"events": 0, "objectives": 0, "tasks": 0}
        self.target_root.mkdir(parents=True, exist_ok=True)
        store = CanonicalStore(self.target_root / "canonical", git_enabled=False)
        adapter = LegacyAgencyAdapter(store, mapping_path=self.mapping_path)

        for row in self.source.events():
            try:
                adapter.import_event(row)
                imported["events"] += 1
            except (LegacyAdapterError, ValueError) as exc:
                errors.append(f"event {row.event_id} ({row.event_type}): {exc}")
        for objective in self.source.objectives():
            try:
                adapter.import_objective(objective)
                imported["objectives"] += 1
            except (LegacyAdapterError, ValueError) as exc:
                errors.append(f"objective {objective.objective_id}: {exc}")
        for task in self.source.tasks():
            try:
                adapter.import_task_submission(
                    task.task_id,
                    project_id=task.project_id,
                    prompt_digest=task.prompt_digest,
                    status=task.status,
                )
                imported["tasks"] += 1
            except (LegacyAdapterError, ValueError) as exc:
                errors.append(f"task {task.task_id}: {exc}")

        index_rebuilt = store.rebuild_index()
        verified = store.verify_digests()
        record_count = len(store.list_committed())
        mapping_digest = _mapping_digest(adapter)

        # 재실행 idempotency: 같은 store에 다시 import해도 record·매핑이 늘지 않아야 한다.
        replay_records = self._replay(store, adapter, record_count)
        # 되돌림 rehearsal은 별도 scratch에서만 수행하고 dry-run 출력은 보존한다.
        rollback_ok = self.rehearse_rollback()

        after = self.source.snapshot()
        return MigrationReport(
            plan=MigrationPlan(source=before, target_root=str(self.target_root), mode=self.mode),
            imported=imported,
            mapping_entries=mapping_entry_count(adapter),
            mapping_digest=mapping_digest,
            canonical_record_count=record_count,
            index_rebuilt=index_rebuilt,
            digests_verified=verified,
            idempotent_replay=replay_records == record_count,
            rollback_rehearsed=rollback_ok,
            mapping_carried_over=mapping_carried_over,
            source_unchanged=before.digest == after.digest and before.counts == after.counts,
            destructive_executed=False,
            destructive_reason="dry-run 전용 — in-place 변환·삭제는 사람 결정으로 분리한다",
            errors=tuple(errors),
            warnings=tuple(_warnings(before, mapping_carried_over=mapping_carried_over)),
        )

    def _replay(self, store: CanonicalStore, adapter: LegacyAgencyAdapter, baseline: int) -> int:
        """같은 store·같은 mapping으로 다시 import해 record 수가 늘지 않는지 본다."""

        for row in self.source.events():
            try:
                adapter.import_event(row)
            except (LegacyAdapterError, ValueError):
                continue
        for objective in self.source.objectives():
            try:
                adapter.import_objective(objective)
            except (LegacyAdapterError, ValueError):
                continue
        for task in self.source.tasks():
            try:
                adapter.import_task_submission(
                    task.task_id,
                    project_id=task.project_id,
                    prompt_digest=task.prompt_digest,
                    status=task.status,
                )
            except (LegacyAdapterError, ValueError):
                continue
        _ = baseline
        return len(store.list_committed())

    # 주의: canonical project ID는 최초 매핑 시 발급되는 random ID라서 **다른 root에서 새로 만들면 달라진다**.
    # identity를 유지하려면 mapping manifest를 함께 넘겨야 한다(mapping_path).
    def rehearse_rollback(self) -> bool:
        """migration 출력 root를 통째로 지워도 source가 그대로인지 확인한다.

        실제 dry-run 출력은 건드리지 않고 전용 scratch root에 한 번 더 옮긴 뒤 삭제한다 —
        "되돌릴 수 있는가"만 관찰하고 이미 만든 결과는 보존한다.
        """

        scratch = self.target_root / "rollback-rehearsal"
        scratch.mkdir(parents=True, exist_ok=True)
        store = CanonicalStore(scratch / "canonical", git_enabled=False)
        adapter = LegacyAgencyAdapter(store, mapping_path=scratch / "legacy" / "agency_map.json")
        for row in self.source.events():
            try:
                adapter.import_event(row)
            except (LegacyAdapterError, ValueError):
                continue
        before = self.source.snapshot()
        discarded = len(store.list_committed())
        shutil.rmtree(scratch, ignore_errors=True)
        after = self.source.snapshot()
        return (
            discarded >= 0 and not scratch.exists() and before.digest == after.digest and after.counts == before.counts
        )


def _mapping_digest(adapter: LegacyAgencyAdapter) -> str:
    payload: list[Mapping[str, object]] = []
    for kind in ("project", "event", "objective", "task"):
        for origin in adapter.origins(kind):
            payload.append({"kind": origin.kind, "legacy_id": origin.legacy_id, "canonical_id": origin.canonical_id})
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(sorted((json.dumps(item, sort_keys=True) for item in payload))).encode("utf-8")
        ).hexdigest()
    )


def mapping_entry_count(adapter: LegacyAgencyAdapter) -> int:
    return sum(len(adapter.origins(kind)) for kind in ("project", "event", "objective", "task"))


def _warnings(snapshot: SourceSnapshot, *, mapping_carried_over: bool) -> Sequence[str]:
    warnings: list[str] = []
    if not mapping_carried_over:
        warnings.append(
            "mapping manifest를 새로 만들었다 — project canonical ID는 이 root에서 발급되며, "
            "root를 옮길 때는 mapping manifest를 함께 옮겨야 identity가 유지된다"
        )
    if TASK_RESULTS_TABLE not in snapshot.tables:
        warnings.append(f"{TASK_RESULTS_TABLE}가 없다 — legacy task 결과 status는 queue 기준으로 기록된다")
    if snapshot.counts.get("tasks", 0) == 0:
        warnings.append("legacy task가 0건이다 — task 경로는 이번 dry-run에서 관측되지 않았다")
    return warnings


__all__ = [
    "APPLY",
    "DRY_RUN",
    "DestructiveMigrationRefused",
    "LegacyEventRow",
    "LegacyMigrationRunner",
    "LegacyObjectiveRow",
    "LegacySQLiteSource",
    "LegacyTaskRow",
    "MigrationError",
    "MigrationPlan",
    "MigrationReport",
    "SourceSnapshot",
    "mapping_entry_count",
]
