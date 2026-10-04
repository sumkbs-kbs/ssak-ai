"""Process-safe creation and migration of the durable action journal."""

import multiprocessing
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal


def _initialize_schema(path, start, migration_race, outcomes):
    # Force unsynchronized migrators to reach their first ALTER together. An
    # explicit transaction serializes this interval, so it needs no scheduling.
    synchronized = False
    with closing(sqlite3.connect(path, timeout=10)) as connection:

        def trace(statement):
            nonlocal synchronized
            if statement.startswith("ALTER TABLE") and not synchronized and not connection.in_transaction:
                synchronized = True
                migration_race.wait(timeout=10)

        connection.set_trace_callback(trace)
        start.wait(timeout=10)
        try:
            SqliteActionJournal._ensure_schema(connection)
        except sqlite3.OperationalError as error:
            outcomes.put(str(error))
        else:
            outcomes.put("ok")


@pytest.mark.parametrize("legacy", [False, True], ids=["new-database", "legacy-upgrade"])
def test_concurrent_schema_initialization_preserves_claims(tmp_path: Path, legacy: bool) -> None:
    # Given two independent processes and either a fresh or legacy journal.
    path = tmp_path / "claims.sqlite"
    if legacy:
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE action_claims (project_id TEXT, action_key TEXT, intent TEXT, "
                "PRIMARY KEY (project_id, action_key))"
            )
            connection.execute("INSERT INTO action_claims VALUES ('project', 'action', 'original-intent')")
    context = multiprocessing.get_context("spawn")
    start, migration_race, outcomes = context.Barrier(2), context.Barrier(2), context.Queue()
    workers = [
        context.Process(target=_initialize_schema, args=(path, start, migration_race, outcomes)) for _ in range(2)
    ]
    # When both initialize the same schema simultaneously.
    for worker in workers:
        worker.start()
    results = [outcomes.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    # Then both callers complete and all migrations are durable without losing claims.
    assert results == ["ok", "ok"]
    with closing(sqlite3.connect(path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(action_claims)")}
        assert {
            "action_record_id",
            "receipt_id",
            "observation_digest",
            "observation_record_id",
            "projection_revision",
        } <= columns
        if legacy:
            assert connection.execute("SELECT intent FROM action_claims").fetchone() == ("original-intent",)
