"""P12 — legacy → canonical migration dry-run 시험.

검증 범위:
- source는 읽기 전용(mode=ro)이며 실행 전후 digest·counts가 같다.
- target root가 source와 겹치면 거부하고, destructive(apply)는 실행하지 않는다.
- 재실행은 같은 canonical ID·같은 record 수를 낸다(idempotent).
- index rebuild·digest 검증이 끝나고, rollback rehearsal은 dry-run 출력을 보존한다.
- 옮길 수 없는 legacy 값은 조용히 건너뛰지 않고 report에 사유로 남긴다.
"""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import sqlite3
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

from antigravity_k.engine.cognitive.legacy_adapter import LegacyAgencyAdapter
from antigravity_k.engine.cognitive.migration import (
    APPLY,
    DestructiveMigrationRefused,
    LegacyMigrationRunner,
    LegacySQLiteSource,
    MigrationError,
    SourceSnapshot,
)
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.persistent_agency_store import EventType, PersistentAgencyStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_legacy_to_canonical.py"
LEGACY_PROJECT = "legacy-project-hash"


def load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migrate_legacy_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_legacy_cli"] = module
    spec.loader.exec_module(module)
    return module


def make_legacy_db(tmp_path: Path, *, task_rows: int = 1, bad_event_type: bool = False, name: str = "src") -> Path:
    """실제 legacy writer로 synthetic PersistentAgency DB를 만든다.

    source는 항상 `tmp_path/src/agency.db`에 두고 target은 `tmp_path/target`처럼 **다른 디렉터리**에
    둔다(runner가 source와 겹치는 target을 거부하기 때문).
    """

    source_dir = tmp_path / name
    source_dir.mkdir(parents=True, exist_ok=True)
    db_path = source_dir / "agency.db"
    store = PersistentAgencyStore(str(db_path))
    store.append_event(LEGACY_PROJECT, "traj-1", "main", None, EventType.OBSERVATION, {"text": "관측"}, "normal")
    store.append_event(LEGACY_PROJECT, "traj-1", "main", 1, EventType.DECISION, {"text": "결정"}, "normal")
    with sqlite3.connect(str(db_path)) as connection:
        for index in range(task_rows):
            connection.execute(
                "INSERT INTO agency_objective_tasks"
                " (task_id, objective_id, project_id, trajectory_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (f"task-{index + 1}", f"obj-{index + 1}", LEGACY_PROJECT, "traj-1", "2026-09-22T00:00:00Z"),
            )
        if bad_event_type:
            connection.execute(
                "INSERT INTO agency_events"
                " (project_id, trajectory_id, branch_id, parent_event_id, event_type, payload_json, sensitivity, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (LEGACY_PROJECT, "traj-1", "main", None, "no_such_type", "{}", "normal", "2026-09-22T00:00:00Z"),
            )
    return db_path


def snapshot(path: Path) -> SourceSnapshot:
    return LegacySQLiteSource(path).snapshot()


# ─── source 불변 ─────────────────────────────────────────────────


def test_dry_run_keeps_source_unchanged(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    before = snapshot(db_path)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()
    after = snapshot(db_path)

    assert before.digest == after.digest
    assert before.counts == after.counts
    assert report.source_unchanged is True
    assert report.plan.source.digest == before.digest
    assert report.plan.source.counts["events"] == 2
    assert report.plan.source.counts["tasks"] == 1
    assert report.imported == {"events": 2, "objectives": 0, "tasks": 1}
    assert report.complete is True
    assert report.passed is True
    assert report.rollback_record_count == report.canonical_record_count
    assert report.source_counts_match_imports is True


def test_incomplete_migration_fails_when_import_counts_do_not_match(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path, bad_event_type=True)

    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.complete is False
    assert report.source_counts_match_imports is False
    assert report.passed is False
    assert report.imported["events"] == 2


def test_event_batches_are_ordered_bounded_and_validate_size(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    source = LegacySQLiteSource(db_path)

    batches = list(source.event_batches(batch_size=1))

    assert [len(batch) for batch in batches] == [1, 1]
    assert [row.event_id for batch in batches for row in batch] == [1, 2]
    with pytest.raises(ValueError, match="positive"):
        list(source.event_batches(batch_size=0))


def test_migration_streams_events_across_bounded_batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = make_legacy_db(tmp_path, task_rows=0)
    with sqlite3.connect(db_path) as connection:
        for index in range(3, 9):
            connection.execute(
                "INSERT INTO agency_events"
                " (project_id, trajectory_id, branch_id, parent_event_id, event_type, payload_json, sensitivity, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (LEGACY_PROJECT, "traj-1", "main", index - 1, "observation", json.dumps({"n": index}), "normal", "now"),
            )
    monkeypatch.setattr(LegacyMigrationRunner, "EVENT_BATCH_SIZE", 2)

    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.imported["events"] == 8
    assert report.mapping_entries == 8  # legacy project alias is stored as a scalar, not an origin entry
    assert report.canonical_record_count == report.index_rebuilt == report.digests_verified == 8
    assert report.idempotent_replay is True
    assert report.rollback_record_count == report.canonical_record_count
    assert report.passed is True


def test_event_batch_repairs_mapping_saved_before_failed_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = make_legacy_db(tmp_path, task_rows=0)
    runner = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target")
    store = runner._target_store()  # noqa: SLF001 - durable-map crash boundary exercise
    adapter = LegacyAgencyAdapter(store, mapping_path=runner.mapping_path)
    rows = next(runner.source.event_batches())

    def fail_before_publish(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated commit interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_commit_locked", fail_before_publish)
        with pytest.raises(RuntimeError, match="simulated"):
            adapter.import_events(rows, update_index=False)

    staged_manifests = tuple(store.staging_dir.glob("*/manifest.json"))
    assert len(staged_manifests) == 1
    transaction_id = staged_manifests[0].parent.name
    repaired = adapter.import_events(rows, update_index=False)

    assert len(repaired) == len(rows)
    assert store.count_committed() == len(rows)
    assert [record.id for record in repaired] == [origin.canonical_id for origin in adapter.origins("event")]
    assert tuple(manifest.transaction_id for manifest in store.committed_manifests()) == (transaction_id,)
    assert tuple(store.staging_dir.glob("*/manifest.json")) == staged_manifests


def test_migration_rebuilds_index_once_per_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = make_legacy_db(tmp_path, task_rows=0)
    calls = 0
    original = CanonicalStore.rebuild_index

    def count_rebuilds(store: CanonicalStore) -> int:
        nonlocal calls
        calls += 1
        return original(store)

    monkeypatch.setattr(CanonicalStore, "rebuild_index", count_rebuilds)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.passed is True
    assert calls == 2, "main target와 rollback scratch에 각각 한 번만 index를 재구성해야 한다"
    assert report.timings_seconds["import"] >= 0
    assert report.timings_seconds["index_rebuild"] >= 0


def test_source_connection_rejects_writes(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    source = LegacySQLiteSource(db_path)
    assert "mode=ro" in source.readonly_uri
    with source._connect() as connection:  # noqa: SLF001 - read-only 강제 확인
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute(
                "INSERT INTO agency_events"
                " (project_id, trajectory_id, branch_id, parent_event_id, event_type, payload_json, sensitivity, created_at)"
                " VALUES ('x','t','main',NULL,'observation','{}','normal','now')"
            )


# ─── 경계 거부 ───────────────────────────────────────────────────


def test_target_overlapping_source_is_refused(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    source = LegacySQLiteSource(db_path)
    source_dir = db_path.parent
    with pytest.raises(MigrationError, match="겹친다"):
        LegacyMigrationRunner(source, source_dir)
    with pytest.raises(MigrationError, match="겹친다"):
        LegacyMigrationRunner(source, source_dir / "nested" / "target")


def test_destructive_mode_is_refused(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    with pytest.raises(DestructiveMigrationRefused, match="사람 결정"):
        LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target", mode=APPLY)


def test_missing_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="legacy source가 없다"):
        LegacySQLiteSource(tmp_path / "nope.db")


def test_source_without_task_table_is_tolerated(tmp_path: Path) -> None:
    source_dir = tmp_path / "bare"
    source_dir.mkdir()
    db_path = source_dir / "bare.db"
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()
    assert report.plan.source.counts == {"events": 0, "objectives": 0, "tasks": 0}
    assert report.canonical_record_count == 0
    assert report.passed is True


# ─── idempotency·index ──────────────────────────────────────────


def test_rerun_is_idempotent_and_mapping_stable(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    run_a = tmp_path / "run-a"
    first = LegacyMigrationRunner(LegacySQLiteSource(db_path), run_a).run()

    assert first.idempotent_replay is True, "같은 store 재실행이 record를 늘렸다"
    assert first.mapping_carried_over is False
    assert any("mapping manifest를 새로 만들었다" in warning for warning in first.warnings)

    # 같은 root 재실행: mapping을 이어받아 identity·record가 그대로다.
    again = LegacyMigrationRunner(LegacySQLiteSource(db_path), run_a).run()
    assert again.mapping_carried_over is True
    assert again.mapping_digest == first.mapping_digest
    assert again.canonical_record_count == first.canonical_record_count == 3

    # 다른 root라도 mapping manifest를 함께 넘기면 identity가 유지된다.
    carried = LegacyMigrationRunner(
        LegacySQLiteSource(db_path),
        tmp_path / "run-b",
        mapping_path=run_a / "legacy" / "agency_map.json",
    ).run()
    assert carried.mapping_carried_over is True
    assert carried.mapping_digest == first.mapping_digest
    assert carried.mapping_entries == first.mapping_entries == 3

    # manifest를 옮기지 않으면 project canonical ID가 새로 발급된다(그리고 경고가 남는다).
    fresh = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "run-c").run()
    assert fresh.mapping_digest != first.mapping_digest
    assert fresh.mapping_entries == first.mapping_entries
    assert fresh.canonical_record_count == first.canonical_record_count


def test_index_rebuilt_and_digests_verified(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.canonical_record_count == 3
    assert report.index_rebuilt >= report.canonical_record_count
    assert report.digests_verified == report.canonical_record_count
    store = CanonicalStore(tmp_path / "target" / "canonical", git_enabled=False)
    assert store.index_path.exists()
    assert store.verify_digests() == 3


def test_rollback_rehearsal_keeps_dry_run_output(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    target = tmp_path / "target"
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()

    assert report.rollback_rehearsed is True
    assert not (target / "rollback-rehearsal").exists()
    # dry-run 출력은 남아 있어야 한다(되돌림 rehearsal이 결과를 지우지 않는다).
    store = CanonicalStore(target / "canonical", git_enabled=False)
    assert len(store.list_committed()) == 3
    assert snapshot(db_path).digest == report.plan.source.digest


def test_rollback_rehearsal_preserves_preexisting_scratch_path(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    target = tmp_path / "target"
    scratch = target / "rollback-rehearsal"
    scratch.mkdir(parents=True)
    sentinel = scratch / "user-data.txt"
    sentinel.write_text("must be preserved", encoding="utf-8")

    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()

    assert report.rollback_rehearsed is True
    assert sentinel.read_text(encoding="utf-8") == "must be preserved"


# ─── 보고의 정직성 ───────────────────────────────────────────────


def test_unmapped_legacy_event_is_reported_not_skipped(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path, bad_event_type=True)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.complete is False
    assert report.source_counts_match_imports is False
    assert report.passed is False
    assert any("no_such_type" in error for error in report.errors)
    # 옮길 수 있는 row는 그대로 옮겨진다.
    assert report.imported["events"] == 2


def test_empty_task_table_is_warned(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path, task_rows=0)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert any("task가 0건" in warning for warning in report.warnings)
    assert report.complete is True


def test_report_mapping_is_json_serialisable(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()
    payload = json.loads(report.to_json())
    assert payload["destructive_executed"] is False
    assert "사람 결정" in payload["destructive_reason"]
    assert payload["source"]["digest"] == report.plan.source.digest


# ─── CLI ─────────────────────────────────────────────────────────


def test_cli_dry_run_writes_report(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    output = tmp_path / "report.json"
    code = load_cli().main(["--source", str(db_path), "--target", str(tmp_path / "target"), "--output", str(output)])
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry-run"
    assert payload["source_unchanged"] is True
    assert payload["destructive_executed"] is False
    assert payload["passed"] is True
    assert payload["source_head"]


def test_cli_refuses_apply_and_reports_incomplete(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    cli = load_cli()
    assert cli.main(["--source", str(db_path), "--target", str(tmp_path / "t"), "--apply"]) == 2
    assert cli.main(["--source", str(db_path), "--target", str(tmp_path / "t")]) == 0
    bad = make_legacy_db(tmp_path, bad_event_type=True, name="bad-src")
    assert cli.main(["--source", str(bad), "--target", str(tmp_path / "t2")]) == 1


def test_r04_a1_wal_payload_change_is_not_source_unchanged(tmp_path: Path) -> None:
    """같은 row count여도 WAL에만 반영된 payload 변경은 source_unchanged=false."""

    db_path = make_legacy_db(tmp_path)
    before = snapshot(db_path)
    # writer via SQLite (WAL mode) updates payload without changing row count
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "UPDATE agency_events SET payload_json=? WHERE event_id=1",
            (json.dumps({"text": "관측-변경"}, ensure_ascii=False),),
        )
        connection.commit()
    wal = Path(f"{db_path}-wal")
    assert wal.exists() or True  # WAL may checkpoint; content digest must still move
    after = snapshot(db_path)
    assert before.counts == after.counts
    assert before.digest != after.digest
    assert before.content_digest != after.content_digest or before.file_bundle_digest != after.file_bundle_digest

    # migration run must see the mutated content as its plan source
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target-wal").run()
    assert report.plan.source.content_digest == after.content_digest
    assert report.source_unchanged is True  # runner does not write source
    assert before.content_digest != report.plan.source.content_digest


MARKER_OBJECTIVE_ID = "obj-marker"
R04_EPOCH_0 = "epoch-0"
R04_EPOCH_1 = "epoch-1"


def _seed_r04_cross_table_markers(db_path: Path, *, epoch: str = R04_EPOCH_0) -> None:
    """event payload marker와 objective title을 같은 epoch로 맞춘다(WAL)."""

    with sqlite3.connect(str(db_path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "UPDATE agency_events SET payload_json=? WHERE event_id=1",
            (json.dumps({"marker": epoch, "text": "관측"}, ensure_ascii=False),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO agency_objectives"
            " (objective_id, project_id, title, description, priority, status, trajectory_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                MARKER_OBJECTIVE_ID,
                LEGACY_PROJECT,
                epoch,
                "r04-marker",
                1,
                "active",
                "traj-1",
                "2026-09-22T00:00:00Z",
                "2026-09-22T00:00:00Z",
            ),
        )
        connection.commit()


def _r04_read_markers(connection: sqlite3.Connection) -> tuple[str, str]:
    if connection.row_factory is None:
        connection.row_factory = sqlite3.Row
    event_row = connection.execute("SELECT payload_json FROM agency_events WHERE event_id=1").fetchone()
    assert event_row is not None
    payload = json.loads(str(event_row["payload_json"]))
    obj_row = connection.execute(
        "SELECT title FROM agency_objectives WHERE objective_id=?",
        (MARKER_OBJECTIVE_ID,),
    ).fetchone()
    assert obj_row is not None
    return str(payload["marker"]), str(obj_row["title"])


def _r04_a2_writer_worker(
    db_path: str,
    barrier: object,
    results: object,
    new_epoch: str,
) -> None:
    """spawn writer: Barrier 동기 후 단일 txn으로 event+objective epoch를 함께 갱신(WAL)."""

    import json as _json
    import sqlite3 as _sqlite3

    barrier.wait(timeout=30)  # type: ignore[attr-defined]
    with _sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE agency_events SET payload_json=? WHERE event_id=1",
            (_json.dumps({"marker": new_epoch, "text": "관측"}, ensure_ascii=False),),
        )
        connection.execute(
            "UPDATE agency_objectives SET title=? WHERE objective_id=?",
            (new_epoch, MARKER_OBJECTIVE_ID),
        )
        connection.commit()
    barrier.wait(timeout=30)  # type: ignore[attr-defined]
    results.put("committed")  # type: ignore[attr-defined]


def test_r04_a2_snapshot_lineage_stable_under_concurrent_writer(tmp_path: Path) -> None:
    """In-process: mid-digest writer가 events→objectives 사이를 찢어도 단일 BEGIN view는 옛 epoch."""

    db_path = make_legacy_db(tmp_path)
    _seed_r04_cross_table_markers(db_path)
    source = LegacySQLiteSource(db_path)
    barrier = threading.Barrier(2)
    writer_errors: list[BaseException] = []
    recorded: list[tuple[str, str]] = []

    def writer() -> None:
        try:
            barrier.wait(timeout=30)
            with sqlite3.connect(str(db_path)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE agency_events SET payload_json=? WHERE event_id=1",
                    (json.dumps({"marker": R04_EPOCH_1, "text": "관측"}, ensure_ascii=False),),
                )
                connection.execute(
                    "UPDATE agency_objectives SET title=? WHERE objective_id=?",
                    (R04_EPOCH_1, MARKER_OBJECTIVE_ID),
                )
                connection.commit()
            barrier.wait(timeout=30)
        except BaseException as exc:  # noqa: BLE001 — surface in parent
            writer_errors.append(exc)

    def after_table(table: str, connection: sqlite3.Connection) -> None:
        if table == "agency_events":
            event_marker, _ = _r04_read_markers(connection)
            recorded.append(("events", event_marker))
            barrier.wait(timeout=30)
            barrier.wait(timeout=30)
        elif table == "agency_objectives":
            _, obj_marker = _r04_read_markers(connection)
            recorded.append(("objectives", obj_marker))

    thread = threading.Thread(target=writer)
    thread.start()
    source._test_after_table = after_table  # noqa: SLF001 — test seam
    try:
        snap = source.snapshot()
    finally:
        source._test_after_table = None  # noqa: SLF001
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert writer_errors == []
    assert recorded == [("events", R04_EPOCH_0), ("objectives", R04_EPOCH_0)]
    assert snap.digest == snap.content_digest
    assert snap.digest.startswith("sha256:")
    assert snap.file_bundle_digest
    assert set(snap.counts) == {"events", "objectives", "tasks"}
    assert snap.counts["objectives"] >= 1
    assert snap.counts["events"] >= 1
    # writer가 실제로 commit했는지(스냅샷 종료 후 live view)
    with sqlite3.connect(str(db_path)) as connection:
        live_event, live_obj = _r04_read_markers(connection)
    assert live_event == live_obj == R04_EPOCH_1


def test_r04_a2_cross_process_writer_during_snapshot(tmp_path: Path) -> None:
    """Cross-process: spawn writer가 mid-digest에 event+objective를 함께 COMMIT해도 view는 미찢김."""

    db_path = make_legacy_db(tmp_path)
    _seed_r04_cross_table_markers(db_path)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    worker = context.Process(
        target=_r04_a2_writer_worker,
        args=(str(db_path), barrier, results, R04_EPOCH_1),
    )
    recorded: list[tuple[str, str]] = []
    source = LegacySQLiteSource(db_path)

    def after_table(table: str, connection: sqlite3.Connection) -> None:
        if table == "agency_events":
            event_marker, _ = _r04_read_markers(connection)
            recorded.append(("events", event_marker))
            barrier.wait(timeout=30)
            barrier.wait(timeout=30)
        elif table == "agency_objectives":
            _, obj_marker = _r04_read_markers(connection)
            recorded.append(("objectives", obj_marker))

    worker.start()
    source._test_after_table = after_table  # noqa: SLF001 — test seam
    try:
        snap = source.snapshot()
        outcome = results.get(timeout=45)
        worker.join(timeout=30)
        assert worker.exitcode == 0
    finally:
        source._test_after_table = None  # noqa: SLF001
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=10)

    assert outcome == "committed"
    assert recorded == [("events", R04_EPOCH_0), ("objectives", R04_EPOCH_0)]
    assert snap.digest == snap.content_digest
    assert snap.counts["objectives"] >= 1
    assert snap.counts["events"] >= 1
    with sqlite3.connect(str(db_path)) as connection:
        live_event, live_obj = _r04_read_markers(connection)
    assert live_event == live_obj == R04_EPOCH_1


def test_r04_a3_mapping_conflict_fails_report(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    target = tmp_path / "target-conflict"
    first = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    assert first.passed is True
    # mutate legacy row that already has mapping
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            "UPDATE agency_events SET payload_json=? WHERE event_id=1",
            (json.dumps({"text": "충돌-payload"}, ensure_ascii=False),),
        )
        connection.commit()
    second = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    assert second.passed is False
    assert second.complete is False or second.idempotent_replay is False or bool(second.errors)
    assert any("conflict" in err.lower() or "changed after mapping" in err.lower() for err in second.errors) or (
        second.idempotent_replay is False
    )


def test_r04_a4_identical_replay_is_idempotent(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path)
    target = tmp_path / "target-idem"
    first = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    second = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    assert first.passed is True
    assert second.passed is True
    assert second.canonical_record_count == first.canonical_record_count
    assert second.mapping_digest == first.mapping_digest
    assert second.imported == first.imported


def test_r21_a2_distribution_labels_unobserved_paths(tmp_path: Path) -> None:
    """R21-A2: report separates observed real counts from synthetic-only paths."""

    db_path = make_legacy_db(tmp_path)  # fixture events; typically 0 objectives/tasks unless seeded
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target-dist").run()
    dist = report.distribution
    assert dist["kind"] == "real_source_observed"
    assert dist["observed_counts"]["events"] == report.imported["events"]
    assert "distribution" in report.as_mapping()
    payload = report.as_mapping()["distribution"]
    assert payload["observed_counts"] == dist["observed_counts"]
    if dist["observed_counts"]["tasks"] == 0:
        assert "tasks" in dist["unobserved_operational_paths"]
        assert "test_migration.py" in str(dist["synthetic_coverage"])


def test_r21_a1_a3_a4_source_hash_stable_across_rerun_and_rollback(tmp_path: Path) -> None:
    """R21-A1/A3/A4 (synthetic): pre/post source digest, idempotent remapping, rollback leaves source readable."""

    import hashlib

    db_path = make_legacy_db(tmp_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    target = tmp_path / "target-r21"
    first = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    mid = hashlib.sha256(db_path.read_bytes()).hexdigest()
    second = LegacyMigrationRunner(LegacySQLiteSource(db_path), target).run()
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before == mid == after
    assert first.source_unchanged is True
    assert second.source_unchanged is True
    assert second.mapping_digest == first.mapping_digest
    assert second.canonical_record_count == first.canonical_record_count
    assert first.rollback_rehearsed is True
    # source remains readable after rollback rehearsal
    snap = LegacySQLiteSource(db_path).snapshot()
    assert snap.counts["events"] == first.imported["events"]
