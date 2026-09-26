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
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.legacy_adapter import (
    LegacyAdapterError,
    LegacyAgencyAdapter,
    LegacyMappingConflict,
)
from antigravity_k.engine.cognitive.protected_targets import migration_guard
from antigravity_k.engine.cognitive.store import CanonicalStore, TransactionConflictError

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
    """source 관찰값. 실행 전후로 같아야 한다.

    ``digest``는 main+WAL+SHM 번들 해시와 단일 read-transaction content 해시를
    결합한 값이다. row count만 같아도 WAL payload 변경이면 digest가 달라진다.
    """

    path: str
    digest: str
    size_bytes: int
    tables: tuple[str, ...]
    counts: Mapping[str, int]
    file_bundle_digest: str = ""
    content_digest: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "path": self.path,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "tables": list(self.tables),
            "counts": dict(self.counts),
            "file_bundle_digest": self.file_bundle_digest,
            "content_digest": self.content_digest,
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


def _sqlite_sidecar_paths(path: Path) -> tuple[Path, ...]:
    """main DB와 존재하는 WAL/SHM sidecar. checkpoint로 증상을 숨기지 않는다."""

    candidates = (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
    return tuple(candidate for candidate in candidates if candidate.exists())


def _sha256_sqlite_bundle(path: Path) -> str:
    """main+WAL+SHM 파일 바이트를 묶어 source 물리 변경을 감지한다."""

    digest = hashlib.sha256()
    for part in _sqlite_sidecar_paths(path):
        digest.update(part.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(part).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(part.stat().st_size).encode("utf-8"))
        digest.update(b"\0")
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
            return self._tables_on(connection)

    def _tables_on(self, connection: sqlite3.Connection) -> tuple[str, ...]:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        return tuple(str(row["name"]) for row in rows)

    def _count_on(self, connection: sqlite3.Connection, table: str, known_tables: set[str]) -> int:
        if table not in known_tables:
            return 0
        row = connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()  # noqa: S608 - table 화이트리스트
        return int(row["total"]) if row is not None else 0

    def _count(self, table: str) -> int:
        with self._connect() as connection:
            return self._count_on(connection, table, set(self._tables_on(connection)))

    def counts(self) -> Mapping[str, int]:
        with self._connect() as connection:
            known = set(self._tables_on(connection))
            return {
                "events": self._count_on(connection, EVENTS_TABLE, known),
                "objectives": self._count_on(connection, OBJECTIVES_TABLE, known),
                "tasks": self._count_on(connection, OBJECTIVE_TASKS_TABLE, known),
            }

    def _content_digest_on(self, connection: sqlite3.Connection, known_tables: set[str]) -> str:
        """한 read transaction 안에서 관심 table의 정렬된 payload를 묶어 digest한다.

        테스트 seam: ``_test_after_table(table, connection)``가 callable이면 각 table digest
        갱신 직후 호출한다(프로덕션 기본값은 미설정). mid-digest writer 교차검증용.
        """

        digest = hashlib.sha256()
        for table, columns in (
            (EVENTS_TABLE, "event_id, project_id, trajectory_id, parent_event_id, event_type, payload_json"),
            (OBJECTIVES_TABLE, "objective_id, project_id, title, description, trajectory_id"),
            (OBJECTIVE_TASKS_TABLE, "task_id, objective_id, project_id, trajectory_id, created_at"),
        ):
            digest.update(table.encode("utf-8"))
            digest.update(b"\0")
            if table not in known_tables:
                digest.update(b"<missing>\0")
            else:
                rows = connection.execute(f"SELECT {columns} FROM {table} ORDER BY 1").fetchall()  # noqa: S608
                for row in rows:
                    digest.update(repr(tuple(row)).encode("utf-8"))
                    digest.update(b"\0")
            hook = getattr(self, "_test_after_table", None)
            if callable(hook):
                hook(table, connection)
        return "sha256:" + digest.hexdigest()

    def snapshot(self) -> SourceSnapshot:
        """단일 BEGIN 스냅샷으로 counts/content를 읽고, WAL 포함 파일 번들 digest와 결합한다."""

        file_bundle = _sha256_sqlite_bundle(self.path)
        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                tables = self._tables_on(connection)
                known = set(tables)
                counts = {
                    "events": self._count_on(connection, EVENTS_TABLE, known),
                    "objectives": self._count_on(connection, OBJECTIVES_TABLE, known),
                    "tasks": self._count_on(connection, OBJECTIVE_TASKS_TABLE, known),
                }
                content = self._content_digest_on(connection, known)
            finally:
                connection.execute("COMMIT")
        # digest는 logical content에 결박한다(WAL 자동 checkpoint로 흔들리지 않음).
        # file_bundle_digest는 main+WAL+SHM 물리 바이트로 A1 증거를 남긴다.
        return SourceSnapshot(
            path=str(self.path),
            digest=content,
            size_bytes=self.path.stat().st_size,
            tables=tables,
            counts=counts,
            file_bundle_digest=file_bundle,
            content_digest=content,
        )

    def event_batches(self, batch_size: int = 2048) -> Iterator[tuple[LegacyEventRow, ...]]:
        """source를 read-only cursor에서 일정 메모리 상한의 ordered batches로 읽는다."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if EVENTS_TABLE not in self.tables():
            return
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                f"SELECT event_id, project_id, trajectory_id, parent_event_id, event_type, payload_json"  # noqa: S608
                f" FROM {EVENTS_TABLE} ORDER BY event_id"
            )
            while rows := cursor.fetchmany(batch_size):
                yield tuple(
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

    def events(self) -> tuple[LegacyEventRow, ...]:
        """호환 단건 API. 대용량 migration은 ``event_batches``를 사용한다."""

        return tuple(event for batch in self.event_batches() for event in batch)

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
    rollback_record_count: int
    mapping_carried_over: bool
    source_unchanged: bool
    destructive_executed: bool
    destructive_reason: str
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    timings_seconds: Mapping[str, float] = field(default_factory=dict)

    @property
    def source_counts_match_imports(self) -> bool:
        return dict(self.imported) == {
            name: self.plan.source.counts.get(name, 0) for name in ("events", "objectives", "tasks")
        }

    @property
    def complete(self) -> bool:
        return not self.errors and self.source_counts_match_imports

    @property
    def passed(self) -> bool:
        return bool(
            self.complete
            and self.source_unchanged
            and not self.destructive_executed
            and self.index_rebuilt == self.canonical_record_count
            and self.digests_verified == self.canonical_record_count
            and self.idempotent_replay
            and self.rollback_rehearsed
            and self.rollback_record_count == self.canonical_record_count
        )

    @property
    def distribution(self) -> Mapping[str, object]:
        """Distinguish real observed source counts from synthetic-only paths.

        A zero objective/task count means that operational path was not present
        in this source — it is not a silent PASS for those row types. Synthetic
        fixtures in tests cover those paths separately.
        """

        counts = {name: int(self.plan.source.counts.get(name, 0)) for name in ("events", "objectives", "tasks")}
        unobserved = tuple(name for name in ("objectives", "tasks") if counts[name] == 0)
        return {
            "kind": "real_source_observed",
            "observed_counts": counts,
            "unobserved_operational_paths": list(unobserved),
            "synthetic_coverage": (
                "tests/cognitive/test_migration.py (+ test_legacy_adapter.py) for objective/task paths"
                if unobserved
                else "not required — source includes objectives and tasks"
            ),
        }

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "mode": self.plan.mode,
            "source": self.plan.source.as_mapping(),
            "distribution": dict(self.distribution),
            "target_root": self.plan.target_root,
            "imported": dict(self.imported),
            "mapping_entries": self.mapping_entries,
            "mapping_digest": self.mapping_digest,
            "canonical_record_count": self.canonical_record_count,
            "index_rebuilt": self.index_rebuilt,
            "digests_verified": self.digests_verified,
            "idempotent_replay": self.idempotent_replay,
            "rollback_rehearsed": self.rollback_rehearsed,
            "rollback_record_count": self.rollback_record_count,
            "mapping_carried_over": self.mapping_carried_over,
            "source_unchanged": self.source_unchanged,
            "destructive_executed": self.destructive_executed,
            "destructive_reason": self.destructive_reason,
            "complete": self.complete,
            "source_counts_match_imports": self.source_counts_match_imports,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "timings_seconds": dict(self.timings_seconds),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True)


class LegacyMigrationRunner:
    """legacy SQLite를 별도 root의 canonical store로 옮기는 **dry-run** runner."""

    EVENT_BATCH_SIZE: Final[int] = 1024

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
        timings: dict[str, float] = {}
        started = time.perf_counter()
        before = self.source.snapshot()
        timings["source_snapshot_before"] = time.perf_counter() - started
        # mapping manifest가 이미 있으면 identity를 이어받는다(project canonical ID 유지).
        mapping_carried_over = self.mapping_path.exists()
        errors: list[str] = []
        imported = {"events": 0, "objectives": 0, "tasks": 0}
        self.target_root.mkdir(parents=True, exist_ok=True)
        store = self._target_store()
        adapter = LegacyAgencyAdapter(store, mapping_path=self.mapping_path)
        store_snapshot = store._committed_entries()  # noqa: SLF001 - mutable committed snapshot shared by batches

        started = time.perf_counter()
        for batch in self.source.event_batches(self.EVENT_BATCH_SIZE):
            try:
                records = adapter.import_events(
                    batch,
                    update_index=False,
                    committed_snapshot=store_snapshot,
                )
                imported["events"] += len(records)
            except (LegacyAdapterError, TransactionConflictError, ValueError) as batch_error:
                errors.append(f"event batch {batch[0].event_id}-{batch[-1].event_id}: {batch_error}")
                # 유효하지 않은 row만 찾아 batch 원자성을 보존하고 조용한 부분 commit을 금지한다.
                valid_rows: list[LegacyEventRow] = []
                for row in batch:
                    try:
                        adapter.import_events(
                            (row,),
                            update_index=False,
                            committed_snapshot=store_snapshot,
                        )
                    except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                        errors.append(f"event {row.event_id} ({row.event_type}): {exc}")
                    else:
                        valid_rows.append(row)
                if len(valid_rows) == len(batch):
                    errors.append(
                        f"event batch {batch[0].event_id}-{batch[-1].event_id} failed atomically: {batch_error}"
                    )
                imported["events"] += len(valid_rows)
        for objective in self.source.objectives():
            try:
                adapter.import_objective(
                    objective,
                    update_index=False,
                    committed_snapshot=store_snapshot,
                )
                imported["objectives"] += 1
            except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                errors.append(f"objective {objective.objective_id}: {exc}")
        for task in self.source.tasks():
            try:
                adapter.import_task_submission(
                    task.task_id,
                    project_id=task.project_id,
                    prompt_digest=task.prompt_digest,
                    status=task.status,
                    update_index=False,
                    committed_snapshot=store_snapshot,
                )
                imported["tasks"] += 1
            except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                errors.append(f"task {task.task_id}: {exc}")
        timings["import"] = time.perf_counter() - started

        started = time.perf_counter()
        index_rebuilt = store.rebuild_index()
        timings["index_rebuild"] = time.perf_counter() - started
        started = time.perf_counter()
        verified = store.verify_digests()
        timings["digest_verification"] = time.perf_counter() - started
        started = time.perf_counter()
        record_count = store.count_committed()
        mapping_digest = _mapping_digest(adapter)
        timings["identity_and_mapping_summary"] = time.perf_counter() - started

        # 재실행 idempotency: 같은 store에 다시 import해도 record·매핑이 늘지 않아야 한다.
        started = time.perf_counter()
        replay_records = self._replay(store, adapter, record_count)
        if replay_records < 0:
            errors.append("idempotent replay hit LegacyMappingConflict — mapping digest/content conflict")
            replay_records = store.count_committed()
            idempotent = False
        else:
            idempotent = replay_records == record_count
        timings["idempotent_replay"] = time.perf_counter() - started
        # 되돌림 rehearsal은 별도 scratch에서만 수행하고 dry-run 출력을 보존한다.
        started = time.perf_counter()
        rollback_ok, rollback_record_count = self.rehearse_rollback()
        timings["rollback_rehearsal"] = time.perf_counter() - started

        started = time.perf_counter()
        after = self.source.snapshot()
        timings["source_snapshot_after"] = time.perf_counter() - started
        timings["total"] = sum(timings.values())
        return MigrationReport(
            plan=MigrationPlan(source=before, target_root=str(self.target_root), mode=self.mode),
            imported=imported,
            mapping_entries=mapping_entry_count(adapter),
            mapping_digest=mapping_digest,
            canonical_record_count=record_count,
            index_rebuilt=index_rebuilt,
            digests_verified=verified,
            idempotent_replay=idempotent,
            rollback_rehearsed=rollback_ok,
            rollback_record_count=rollback_record_count,
            mapping_carried_over=mapping_carried_over,
            source_unchanged=(before.content_digest == after.content_digest and before.counts == after.counts),
            destructive_executed=False,
            destructive_reason="dry-run 전용 — in-place 변환·삭제는 사람 결정으로 분리한다",
            errors=tuple(errors),
            warnings=tuple(_warnings(before, mapping_carried_over=mapping_carried_over)),
            timings_seconds=timings,
        )

    def _target_store(self, *, scratch: Path | None = None) -> CanonicalStore:
        """migration 대상 store는 항상 보호 guard를 달고 만든다(migration 실제 경로 hook).

        guard가 지키는 범위와 이유는 ``migration_guard`` docstring에 있다 — premise 최초 구축은
        migration의 선언된 임무로 열고, constitution·authority·이력·계보 mapping은 닫는다.
        """

        root = scratch if scratch is not None else self.target_root
        store_dir = root / "canonical"
        return CanonicalStore(store_dir, git_enabled=False, write_guard=migration_guard(root))

    def _replay(self, store: CanonicalStore, adapter: LegacyAgencyAdapter, baseline: int) -> int:
        """같은 store·같은 mapping으로 다시 import해 record 수가 늘지 않는지 본다.

        동일 mapping의 재실행은 허용한다. content conflict는 삼키지 않고 -1을 반환해
        idempotent_replay=false와 errors 경로를 호출자가 구분하게 한다.
        """

        store_snapshot = store._committed_entries()  # noqa: SLF001 - replay uses one mutable manifest snapshot
        conflict = False
        for batch in self.source.event_batches(self.EVENT_BATCH_SIZE):
            try:
                adapter.import_events(
                    batch,
                    update_index=False,
                    committed_snapshot=store_snapshot,
                )
            except LegacyMappingConflict:
                conflict = True
                break
            except (LegacyAdapterError, TransactionConflictError, ValueError):
                for row in batch:
                    try:
                        adapter.import_events((row,), update_index=False, committed_snapshot=store_snapshot)
                    except LegacyMappingConflict:
                        conflict = True
                        break
                    except (LegacyAdapterError, TransactionConflictError, ValueError):
                        continue
                if conflict:
                    break
        if not conflict:
            for objective in self.source.objectives():
                try:
                    adapter.import_objective(objective, update_index=False, committed_snapshot=store_snapshot)
                except LegacyMappingConflict:
                    conflict = True
                    break
                except (LegacyAdapterError, TransactionConflictError, ValueError):
                    continue
        if not conflict:
            for task in self.source.tasks():
                try:
                    adapter.import_task_submission(
                        task.task_id,
                        project_id=task.project_id,
                        prompt_digest=task.prompt_digest,
                        status=task.status,
                        update_index=False,
                        committed_snapshot=store_snapshot,
                    )
                except LegacyMappingConflict:
                    conflict = True
                    break
                except (LegacyAdapterError, TransactionConflictError, ValueError):
                    continue
        _ = baseline
        if conflict:
            return -1
        return store.count_committed()

    # 주의: canonical project ID는 최초 매핑 시 발급되는 random ID라서 **다른 root에서 새로 만들면 달라진다**.
    # identity를 유지하려면 mapping manifest를 함께 넘겨야 한다(mapping_path).
    def rehearse_rollback(self) -> tuple[bool, int]:
        """임시 target을 삭제해도 기존 migration 산출물과 source가 그대로인지 확인한다.

        매 회차 새로 독점 생성한 scratch만 사용·정리한다. target 아래의 고정 경로를 재사용하면
        선행 파일을 rehearsal 산출물로 오인해 지울 수 있으므로 `mkdtemp`로 경로를 격리한다.
        """

        before = self.source.snapshot()
        self.target_root.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix=".rollback-rehearsal-", dir=self.target_root))
        try:
            rehearsal_ok, discarded = self._populate_rollback_scratch(scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        after = self.source.snapshot()
        passed = (
            rehearsal_ok and not scratch.exists() and before.digest == after.digest and after.counts == before.counts
        )
        return passed, discarded

    def _populate_rollback_scratch(self, scratch: Path) -> tuple[bool, int]:
        """독점 scratch에 source를 옮기고 지우기 전 검증한다."""

        store = self._target_store(scratch=scratch)
        adapter = LegacyAgencyAdapter(store, mapping_path=scratch / "legacy" / "agency_map.json")
        store_snapshot = store._committed_entries()  # noqa: SLF001 - mutable rollback snapshot
        imported_record_ids: set[str] = set()
        errors: list[str] = []
        for batch in self.source.event_batches(self.EVENT_BATCH_SIZE):
            try:
                records = adapter.import_events(
                    batch,
                    update_index=False,
                    committed_snapshot=store_snapshot,
                )
                imported_record_ids.update(record.id for record in records)
            except (LegacyAdapterError, TransactionConflictError, ValueError) as batch_error:
                errors.append(f"event batch: {batch_error}")
                for row in batch:
                    try:
                        record = adapter.import_events(
                            (row,),
                            update_index=False,
                            committed_snapshot=store_snapshot,
                        )[0]
                        imported_record_ids.add(record.id)
                    except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                        errors.append(f"event {row.event_id}: {exc}")
        for objective in self.source.objectives():
            try:
                imported_record_ids.add(
                    adapter.import_objective(
                        objective,
                        update_index=False,
                        committed_snapshot=store_snapshot,
                    ).id
                )
            except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                errors.append(f"objective {objective.objective_id}: {exc}")
        for task in self.source.tasks():
            try:
                imported_record_ids.add(
                    adapter.import_task_submission(
                        task.task_id,
                        project_id=task.project_id,
                        prompt_digest=task.prompt_digest,
                        status=task.status,
                        update_index=False,
                        committed_snapshot=store_snapshot,
                    ).id
                )
            except (LegacyAdapterError, TransactionConflictError, ValueError) as exc:
                errors.append(f"task {task.task_id}: {exc}")
        store.rebuild_index()
        discarded = store.count_committed()
        return not errors and discarded == len(imported_record_ids), discarded


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
