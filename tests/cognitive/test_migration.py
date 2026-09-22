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
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

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


# ─── 보고의 정직성 ───────────────────────────────────────────────


def test_unmapped_legacy_event_is_reported_not_skipped(tmp_path: Path) -> None:
    db_path = make_legacy_db(tmp_path, bad_event_type=True)
    report = LegacyMigrationRunner(LegacySQLiteSource(db_path), tmp_path / "target").run()

    assert report.complete is False
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
