"""WAL writers cannot change the payload lineage of a migration in progress."""

import sqlite3
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.migration import LegacyMigrationRunner, LegacySQLiteSource, SourceSnapshot
from antigravity_k.engine.cognitive.store import CanonicalStore
from tests.cognitive.test_migration import make_legacy_db


def test_original_payload_mapping_survives_live_wal_aba(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real WAL source and the original logical source state.
    db = make_legacy_db(tmp_path)
    with sqlite3.connect(db) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        original = writer.execute("SELECT payload_json FROM agency_events WHERE event_id=1").fetchone()[0]
    source = LegacySQLiteSource(db)
    snapshot = source.snapshot
    before = snapshot()
    runner = LegacyMigrationRunner(source, tmp_path / "target")
    target_store = runner._target_store
    changed = False

    def write_intermediate(*, scratch: Path | None = None) -> CanonicalStore:
        nonlocal changed
        if scratch is None:
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE agency_events SET payload_json=? WHERE event_id=1", ('{"text":"B"}',))
            changed = True
            assert Path(f"{db}-wal").exists()
        return target_store(scratch=scratch)

    def restore_before_observation() -> SourceSnapshot:
        if changed:
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE agency_events SET payload_json=? WHERE event_id=1", (original,))
        return snapshot()

    monkeypatch.setattr(runner, "_target_store", write_intermediate)
    monkeypatch.setattr(source, "snapshot", restore_before_observation)
    # When B exists during import/replay and A returns before live observation.
    first = runner.run()
    second = LegacyMigrationRunner(LegacySQLiteSource(db), tmp_path / "target").run()
    # Then the report and original-payload mapping both remain truthful.
    assert first.passed and first.source_unchanged
    assert first.plan.source.content_digest == before.content_digest
    assert second.passed, second.errors
    assert second.mapping_digest == first.mapping_digest


def test_live_wal_change_is_reported_separately_from_frozen_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an original source whose writer keeps a later payload committed.
    db = make_legacy_db(tmp_path)
    source = LegacySQLiteSource(db)
    before = source.snapshot()
    runner = LegacyMigrationRunner(source, tmp_path / "target")
    target_store = runner._target_store

    def change_live_source(*, scratch: Path | None = None) -> CanonicalStore:
        if scratch is None:
            with sqlite3.connect(db) as writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("UPDATE agency_events SET payload_json=? WHERE event_id=1", ('{"text":"B"}',))
        return target_store(scratch=scratch)

    monkeypatch.setattr(runner, "_target_store", change_live_source)
    # When the live source changes after capture.
    report = runner.run()
    # Then snapshot operations stay internally valid but the live check fails.
    assert report.plan.source.content_digest == before.content_digest
    assert report.idempotent_replay and report.rollback_rehearsed
    assert report.source_unchanged is False
    assert report.passed is False
