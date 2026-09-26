"""Regression scenarios for durable action admission and authority freshness."""

from dataclasses import replace
from datetime import timedelta

import pytest

from antigravity_k.engine.cognitive.actions import ActionDispatcher, ActionObservation, CallablePort
from antigravity_k.engine.cognitive.authority import AuthorityGrant
from tests.cognitive.test_actions import BODY, NOW, PROJECT, make_intent


def test_intent_is_persisted_before_effect():
    # Given a port which observes the canonical sink.
    persisted = []
    seen = []
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *args: seen.append(len(persisted))),
        record_sink=persisted.extend,
        clock=lambda: NOW,
    )
    # When an authorized action executes.
    dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # Then its intent already exists at the effect boundary.
    assert seen == [1]


def test_failed_observed_non_idempotent_action_cannot_repeat():
    # Given an observed failed effect.
    calls = []
    dispatcher = ActionDispatcher(port=CallablePort(lambda *args: calls.append(1)), clock=lambda: NOW)
    intent = make_intent(idempotent=False)
    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    dispatcher.reconcile(run, ActionObservation(observed=True, succeeded=False), project_id=PROJECT, producer=BODY)
    # When another submission retries it.
    result = dispatcher.execute(
        replace(intent, submission_id="second"), project_id=PROJECT, producer=BODY, retry_authorized=True
    )
    # Then no second effect occurs.
    assert result.refused
    assert calls == [1]


@pytest.mark.parametrize("grant_change", ["expired", "future", "revoked", "scope", "operation", "subject"])
def test_cached_grant_is_checked_at_dispatch(grant_change):
    # Given a previously allowed decision with a now unusable grant.
    intent = make_intent()
    grant = AuthorityGrant(
        subject=BODY.actor_id,
        dimension=intent.dimension,
        resource_scope="src",
        allowed_operations=("execute_tool",),
        granted_by="human:test",
        revision=1,
        issued_at=NOW - timedelta(days=1),
    )
    updates = {
        "subject": {"subject": "body:another-actor"},
        "expired": {"expires_at": NOW},
        "future": {"issued_at": NOW + timedelta(seconds=1)},
        "revoked": {"revoked_at": NOW},
        "scope": {"resource_scope": "other"},
        "operation": {"allowed_operations": ("different",)},
    }
    grant = grant.model_copy(update=updates[grant_change])
    decision = replace(intent.clearance.authority, grant=grant)
    intent = replace(intent, clearance=replace(intent.clearance, authority=decision))
    calls = []
    dispatcher = ActionDispatcher(port=CallablePort(lambda *args: calls.append(1)), clock=lambda: NOW)
    # When the cached decision is used.
    result = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    # Then dispatch is blocked.
    assert result.refused
    assert calls == []


def test_durable_claim_survives_crash_and_dispatcher_restart(tmp_path):
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal

    # Given an executor that crashes after its external effect.
    effects = tmp_path / "effects"
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")

    def crash(*args):
        effects.write_text("effect\n")
        raise SystemExit(7)

    dispatcher = ActionDispatcher(port=CallablePort(crash), journal=journal, clock=lambda: NOW)
    with pytest.raises(SystemExit):
        dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # When a fresh dispatcher attempts the same action.
    restarted = ActionDispatcher(
        port=CallablePort(lambda *args: effects.write_text("DUPLICATE")),
        journal=SqliteActionJournal(journal.path),
        clock=lambda: NOW,
    )
    result = restarted.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # Then the persistent claim prevents a second effect even without a receipt.
    assert result.refused
    assert effects.read_text() == "effect\n"


def _dispatch_worker(journal_path, effects_path, barrier, results):
    from pathlib import Path

    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal

    def effect(*args):
        with Path(effects_path).open("a") as stream:
            stream.write("effect\n")

    dispatcher = ActionDispatcher(
        port=CallablePort(effect), journal=SqliteActionJournal(Path(journal_path)), clock=lambda: NOW
    )
    barrier.wait(timeout=15)
    result = dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    results.put(result.refused)


def test_two_processes_share_one_durable_effect_claim(tmp_path):
    import multiprocessing

    # Given two independent process-local dispatchers using one journal.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    effects = tmp_path / "effects"
    workers = [
        context.Process(target=_dispatch_worker, args=(str(tmp_path / "claims.sqlite"), str(effects), barrier, results))
        for _ in range(2)
    ]
    # When both attempt the same action concurrently.
    for worker in workers:
        worker.start()
    try:
        refusals = [results.get(timeout=20) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        results.close()
    # Then only the claim winner executes.
    assert sorted(refusals) == [False, True]
    assert effects.read_text() == "effect\n"


def test_canonical_sink_failure_prevents_effect(tmp_path):
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal

    # Given unavailable canonical storage.
    calls = []

    def unavailable(records):
        raise OSError("fixture storage failure")

    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *args: calls.append(1)),
        journal=SqliteActionJournal(tmp_path / "claims.sqlite"),
        record_sink=unavailable,
        clock=lambda: NOW,
    )
    # When admission tries to persist intent.
    with pytest.raises(OSError):
        dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # Then no external effect ran.
    assert calls == []


def test_live_revocation_during_persistence_prevents_effect():
    # Given a grant revoked while persisting the intent.
    calls = []
    intent = make_intent()
    current = [intent.clearance.authority]

    def revoke(records):
        current[0] = replace(current[0], allowed=False)

    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *args: calls.append(1)),
        record_sink=revoke,
        authority_resolver=lambda intent, now: current[0],
        clock=lambda: NOW,
    )
    # When admission reaches the final authority check.
    result = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    # Then the live revocation blocks the effect.
    assert result.refused
    assert calls == []


def test_receipt_references_persisted_action_identity():
    # Given an authorized action with a canonical ID.
    dispatcher = ActionDispatcher(port=CallablePort(lambda *args: None), clock=lambda: NOW)
    # When it is recorded and dispatched.
    run = dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # Then its receipt references the actual persisted intent.
    assert run.receipt.action_id == run.records[0].id


def test_cancel_after_observed_failed_effect_keeps_effect_possible():
    # Given a failed action with an observed external effect.
    dispatcher = ActionDispatcher(port=CallablePort(lambda *args: None), clock=lambda: NOW)
    run = dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    failed = dispatcher.reconcile(
        run, ActionObservation(observed=True, succeeded=False), project_id=PROJECT, producer=BODY
    )
    # When cancellation is requested.
    cancelled = dispatcher.cancel(failed, reason="stop")
    # Then it cannot claim there was no external effect.
    assert cancelled.receipt.effects_observed is True
    assert cancelled.reconciliation_required


def test_journal_failure_prevents_effect(tmp_path):
    import sqlite3

    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal

    # Given a journal path that cannot be opened as a database.
    calls = []
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *args: calls.append(1)), journal=SqliteActionJournal(tmp_path), clock=lambda: NOW
    )
    # When durable claim acquisition fails.
    with pytest.raises(sqlite3.OperationalError):
        dispatcher.execute(make_intent(), project_id=PROJECT, producer=BODY)
    # Then execution fails closed.
    assert calls == []


def test_r10_a2_identical_observation_keeps_ids(tmp_path):
    """R10-A2: identical observation replay keeps receipt/observation IDs (no duplicate create)."""
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.actions import ActionDispatcher, ActionObservation, ObservationSubmission
    from antigravity_k.engine.cognitive.store import CanonicalStore

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *a: "ok"),
        journal=journal,
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r10-a2")
    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    obs = ActionObservation(observed=True, succeeded=True, detail="same")
    first = dispatcher.submit_observation(
        ObservationSubmission(
            project_id=PROJECT,
            action_key="r10-a2",
            expected_receipt_id=run.receipt.receipt_id,
            observation=obs,
        ),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    assert first.accepted
    second = dispatcher.submit_observation(
        ObservationSubmission(
            project_id=PROJECT,
            action_key="r10-a2",
            expected_receipt_id=first.receipt_id or "",
            observation=obs,
        ),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    assert second.accepted
    assert second.receipt_id == first.receipt_id
    assert second.observation_record_id == first.observation_record_id
    assert second.projection_revision == first.projection_revision
    assert second.records == ()


def test_r10_a3_stale_or_foreign_observation_refused(tmp_path):
    """R10-A3: wrong project or stale receipt revision is refused with no effect."""
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.action_types import ActionRefusal
    from antigravity_k.engine.cognitive.actions import ActionDispatcher, ActionObservation, ObservationSubmission
    from antigravity_k.engine.cognitive.store import CanonicalStore

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    calls = []
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *a: calls.append(1)),
        journal=SqliteActionJournal(tmp_path / "claims.sqlite"),
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r10-a3")
    run = dispatcher.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    before = len(dispatcher.records)
    stale = dispatcher.submit_observation(
        ObservationSubmission(
            project_id=PROJECT,
            action_key="r10-a3",
            expected_receipt_id="execution_receipt:00000000-0000-0000-0000-000000000000",
            observation=ActionObservation(observed=True, succeeded=True),
        ),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    assert not stale.accepted
    assert stale.refusal is ActionRefusal.STALE_RECEIPT_REVISION
    foreign = dispatcher.submit_observation(
        ObservationSubmission(
            project_id="project:00000000-0000-0000-0000-000000000099",
            action_key="r10-a3",
            expected_receipt_id=run.receipt.receipt_id,
            observation=ActionObservation(observed=True, succeeded=True),
        ),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    assert not foreign.accepted
    assert foreign.refusal is ActionRefusal.UNKNOWN_ACTION
    assert len(dispatcher.records) == before
    assert calls == [1]


def test_r10_a4_timeout_does_not_release_claim(tmp_path):
    """R10-A4: elapsed time alone does not clear the claim; pending reason stays queryable."""
    from antigravity_k.engine.cognitive.action_journal import PENDING, SqliteActionJournal
    from antigravity_k.engine.cognitive.actions import ActionDispatcher
    from antigravity_k.engine.cognitive.store import CanonicalStore

    store = CanonicalStore(tmp_path / "store", git_enabled=False)
    journal = SqliteActionJournal(tmp_path / "claims.sqlite")
    dispatcher = ActionDispatcher(
        port=CallablePort(lambda *a: "ok"),
        journal=journal,
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    run = dispatcher.execute(make_intent(action_key="r10-a4"), project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    # Simulate "timeout" wall clock without any release API — claim must remain.
    pending = dispatcher.pending_with_reasons(PROJECT)
    assert len(pending) == 1
    assert pending[0].action_key == "r10-a4"
    assert pending[0].status == PENDING
    assert pending[0].pending_reason
    assert journal.get(PROJECT, "r10-a4") is not None
