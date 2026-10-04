"""Recovery publication uses the real canonical store and SQLite journal."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest

from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionObservation,
    CallablePort,
    ObservationSubmission,
)
from antigravity_k.engine.cognitive.references import EntityType
from antigravity_k.engine.cognitive.store import CanonicalStore
from tests.cognitive.test_actions import BODY, NOW, PROJECT, make_intent


def setup_action(tmp_path):
    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *_: "ok"),
        journal=journal,
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    run = dispatcher.execute(make_intent(action_key="atomic"), project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    submission = ObservationSubmission(
        PROJECT, "atomic", run.receipt.receipt_id, ActionObservation(observed=True, succeeded=True)
    )
    return store, journal, dispatcher, submission


def test_conflicting_first_observations_have_one_winner(tmp_path):
    # Given two readers of the same durable receipt.
    store, journal, dispatcher, submission = setup_action(tmp_path)
    barrier = Barrier(2)

    def submit(succeeded):
        waited = False

        def load(record_id):
            nonlocal waited
            record = store.read(record_id)
            if record_id == submission.expected_receipt_id and not waited:
                waited = True
                barrier.wait(timeout=10)
            return record

        worker = replace(dispatcher)
        return worker.submit_observation(
            replace(submission, observation=ActionObservation(observed=True, succeeded=succeeded)),
            producer=BODY,
            load_record=load,
            now=NOW,
        )

    # When both publish conflicting observations.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [True, False]))
    # Then exactly one observation changes the authoritative projection.
    assert sum(result.accepted for result in results) == 1
    claim = journal.get(PROJECT, "atomic")
    assert claim is not None and claim.projection_revision == 1
    assert store.read(claim.observation_record_id) is not None


def test_failed_observation_append_keeps_claim_pending(tmp_path):
    # Given a durable dispatched action and an unavailable observation sink.
    store, journal, dispatcher, submission = setup_action(tmp_path)

    def fail(records):
        if any(record.entity_type == EntityType.OBSERVATION for record in records):
            raise OSError("observation storage unavailable")
        store.commit_records(list(records))

    # When canonical observation publication fails.
    with pytest.raises(OSError):
        replace(dispatcher, record_sink=fail).submit_observation(
            submission, producer=BODY, load_record=store.read, now=NOW
        )
    # Then no successful settlement is visible.
    claim = journal.get(PROJECT, "atomic")
    assert claim is not None and claim.status == "pending"
    assert claim.receipt_id == submission.expected_receipt_id
    assert claim.projection_revision == 0
    assert len(journal.list_pending(PROJECT)) == 1


def test_crash_after_canonical_append_retries_same_ids(tmp_path):
    # Given a crash after canonical persistence but before projection commit.
    store, journal, dispatcher, submission = setup_action(tmp_path)
    persisted = []

    def crash(records):
        store.commit_records(list(records))
        persisted.extend(records)
        raise OSError("crash after durable append")

    with pytest.raises(OSError):
        replace(dispatcher, record_sink=crash).submit_observation(
            submission, producer=BODY, load_record=store.read, now=NOW
        )
    # When another dispatcher repeats the original request at a later time.
    result = replace(dispatcher).submit_observation(
        submission, producer=BODY, load_record=store.read, now=NOW + timedelta(minutes=1)
    )
    replay = replace(dispatcher).submit_observation(
        submission, producer=BODY, load_record=store.read, now=NOW + timedelta(minutes=2)
    )
    # Then IDs survive both the crash and exact request replay.
    assert result.accepted and replay.accepted
    assert result.observation_record_id in {record.id for record in persisted}
    assert result.receipt_id in {record.id for record in persisted}
    assert result.receipt_id == replay.receipt_id
    assert result.observation_record_id == replay.observation_record_id
    assert replay.records == ()
    assert journal.get(PROJECT, "atomic").projection_revision == 1


def test_receiptless_claim_is_recovered_without_dispatch(tmp_path):
    # Given a crash after the durable intent claim, before receipt persistence.
    store, journal, dispatcher, submission = setup_action(tmp_path)
    intent = make_intent(action_key="receiptless")
    from antigravity_k.engine.cognitive.action_records import create_action_record

    record = create_action_record(intent, project_id=PROJECT, producer=BODY, created_at=NOW)
    journal.claim(PROJECT, "receiptless", record)
    # When an observation identifies the receipt-less claim with an empty receipt ID.
    result = dispatcher.submit_observation(
        ObservationSubmission(PROJECT, "receiptless", "", ActionObservation(observed=True, succeeded=True)),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    # Then recovery creates durable records without running the external action.
    assert result.accepted and not result.redispatched
    assert store.read(record.id) is not None
    claim = journal.get(PROJECT, "receiptless")
    assert claim is not None and claim.status == "settled"


def _crash_after_publication(store_path, journal_path, submission):
    """Abrupt exit models process loss after durable canonical append."""
    import os
    from pathlib import Path

    store = CanonicalStore(Path(store_path), git_enabled=False)

    def append_then_exit(records):
        store.commit_records(list(records))
        os._exit(23)

    ActionDispatcher(journal=SqliteActionJournal(Path(journal_path)), record_sink=append_then_exit).submit_observation(
        submission, producer=BODY, load_record=store.read, now=NOW
    )


def test_process_crash_after_append_recovers_original_request(tmp_path):
    # Given an independent worker that dies after its canonical append.
    import multiprocessing

    store, journal, dispatcher, submission = setup_action(tmp_path)
    context = multiprocessing.get_context("spawn")
    worker = context.Process(
        target=_crash_after_publication, args=(str(tmp_path / "store"), str(journal.path), submission)
    )
    # When SQLite rolls back the interrupted projection transaction.
    worker.start()
    worker.join(timeout=20)
    assert worker.exitcode == 23
    pending = journal.get(PROJECT, "atomic")
    assert pending is not None and pending.projection_revision == 0
    result = dispatcher.submit_observation(
        submission, producer=BODY, load_record=store.read, now=NOW + timedelta(minutes=3)
    )
    # Then retry repairs the projection from the original durable records.
    assert result.accepted and result.projection_revision == 1
    receipt = store.read(result.receipt_id)
    observation = store.read(result.observation_record_id)
    assert receipt.created_at == NOW
    assert observation.created_at == NOW
    assert result.records[-1] == observation


def _concurrent_publication(store_path, journal_path, submission, barrier, queue):
    from pathlib import Path

    store = CanonicalStore(Path(store_path), git_enabled=False)
    waited = False

    def load(record_id):
        nonlocal waited
        record = store.read(record_id)
        if record_id == submission.expected_receipt_id and not waited:
            waited = True
            barrier.wait(timeout=10)
        return record

    dispatcher = ActionDispatcher(
        journal=SqliteActionJournal(Path(journal_path)), record_sink=lambda records: store.commit_records(list(records))
    )
    result = dispatcher.submit_observation(submission, producer=BODY, load_record=load, now=NOW)
    queue.put(result)


def test_independent_processes_cannot_publish_conflicting_first_observations(tmp_path):
    # Given two processes holding the same initial projection revision.
    import multiprocessing

    store, journal, dispatcher, submission = setup_action(tmp_path)
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    workers = [
        context.Process(
            target=_concurrent_publication,
            args=(
                str(tmp_path / "store"),
                str(journal.path),
                replace(submission, observation=ActionObservation(observed=True, succeeded=succeeded)),
                barrier,
                queue,
            ),
        )
        for succeeded in (True, False)
    ]
    # When their first observations conflict.
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    # Then one winner owns revision 1 across process boundaries.
    assert sum(result.accepted for result in results) == 1
    claim = journal.get(PROJECT, "atomic")
    assert claim.projection_revision == 1
    assert claim.receipt_id == next(result.receipt_id for result in results if result.accepted)


def test_late_dispatch_receipt_cannot_replace_observation_projection(tmp_path):
    # Given a settled recovery publication.
    store, journal, dispatcher, submission = setup_action(tmp_path)
    result = dispatcher.submit_observation(submission, producer=BODY, load_record=store.read, now=NOW)
    # When an in-flight dispatch tries to attach its older receipt afterwards.
    with pytest.raises(LookupError):
        journal.attach_receipt(PROJECT, "atomic", submission.expected_receipt_id)
    # Then observation authority is retained.
    assert journal.get(PROJECT, "atomic").receipt_id == result.receipt_id


def test_published_observation_updates_dispatcher_receipt(tmp_path):
    # Given a dispatcher holding the original dispatch receipt.
    store, journal, dispatcher, submission = setup_action(tmp_path)
    # When recovery publishes its durable result.
    result = dispatcher.submit_observation(submission, producer=BODY, load_record=store.read, now=NOW)
    # Then local pending inspection agrees with durable publication.
    assert dispatcher.receipt_for("atomic").receipt_id == result.receipt_id
    assert dispatcher.pending_reconciliation() == ()
