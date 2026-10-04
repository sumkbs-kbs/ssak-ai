# Independent storage / recovery review

Date: 2026-09-27. Read-only source audit; disposable real SQLite and CanonicalStore runtime probes. Reviewed HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

**Verdict: FAIL at reviewed revision.** R03 transaction identity passes the examined single-host cases. R04 migration lineage and R09/R10 recovery have reproducible defects. R08 has no production store-backed freshness implementation at this revision, only the injectable callback seam. This report is not operations/cutover approval. Concurrent implementer changes after the hashes below require re-review.

## P1 — First conflicting observations both accept; settlement lacks CAS

`src/antigravity_k/engine/cognitive/actions.py:263` reads a journal claim, then reconciles outside a journal transaction. `action_lifecycle.py:98` updates the receipt projection before `actions.py:451` attaches observation. `action_journal.py:146` updates by project/action key without expected receipt ID, revision, or status predicate.

Repro: `code-repro.py`, scenario race. Two independent dispatchers use the real same SQLite journal and CanonicalStore. A Barrier after reading the original receipt ensures both first observations use revision zero; one reports success and the other failure. Observed:

```
race accepted= [True, True] revisions= [1, 1] distinct_receipts= 2
race claim= settled revision= 1 ... pending= 0
```

Both return accepted and the last writer replaces the settled result. The existing late-observation test starts after settlement and does not cover this first-settlement race. Fix with atomic expected-revision/expected-receipt reservation or CAS; persist evidence before publishing settlement, and return acceptance only for the winner. Receipt reconciliation must not independently overwrite the projection.

## P1 — Observation storage failure hides a settled action without observation

`action_lifecycle.py:98-101` attaches a SETTLED receipt inside reconcile. `actions.py:447` persists the observation only afterward. Inject OSError specifically when the canonical sink receives an Observation. Observed by `code-repro.py` scenario crash:

```
crash exception= injected observation sink failure
crash claim= settled revision= 0 observation= None pending= 0
```

Restart pending lookup drops this action despite absent durable observation linkage. Original submission retry also uses the old receipt ID and is rejected. Publish the receipt/observation atomically to canonical storage, then conditionally publish the journal projection, with restart repair for the intervening window.

## P1 — Migration report can PASS while its source snapshot describes different data

`migration.py:467` takes the before snapshot, but `event_batches`, `objectives`, and `tasks` open separate connections. Replay and rollback also re-read the live source. `migration.py:583` checks only endpoint content digest/count equality.

Repro: `migration-lineage-repro.py` uses a temporary real legacy SQLite fixture, changing event 1 payload after the initial snapshot and restoring it before the final snapshot. The reader subclass only schedules actual writer commits; all migration methods otherwise run unchanged. Observed:

```
first_passed True first_unchanged True second_passed False
second_error event batch 1-2: legacy event legacy-project-hash:traj-1:1 changed after mapping: sha256:e50e489b285424c91a7e8a7fbe7576abe4b2773cf0bec784be2ace6886991adf -> sha256:27f90990aaf56fe43b7b99634110d73f87fb0c5d65eb9249cdf6916a86cb7a9f
```

The first report certifies the original source digest while importing the intermediate contents. Immediate ordinary rerun against exactly the reported source fails mapping conflict. Pin all reads to the same SQLite snapshot (or immutable backup) and bind report lineage to that snapshot. Single-BEGIN inside `snapshot()` alone is insufficient.

## R08 — Integration remains unproven at this revision

`action_admission.py:130-157` correctly recomputes action digest and uses injected live binding when present. `cognitive_surface.py:425-431` simply delegates to the injected callback. Existing self-report explicitly acknowledges fixture boxes and no production store-head proof. Parent owns current-store composition correction; this review cannot award live production freshness PASS from the old callback tests.

## R09/R10 — Additional crash recovery gap

`actions.py:278` refuses observations for claims without receipts. A process termination after effect but before `_finish` leaves precisely that state. Existing `test_durable_claim_survives_crash_and_dispatcher_restart` proves duplicate prevention but not reconciliation. No receipt-less recovery route was found in this revision. Recovery worker has been notified to cover this window as well.

## R03 and narrow verification

`store.py:509-544` compares immutable content identity before returning an existing staged manifest. `_publish_locked` rechecks committed uniqueness before materialization. No additional R03 identity defect found. Narrow R03/R04 test run result is recorded separately when complete. Power-loss, NFS, and multi-host behavior are not claimed.

An extra killed-owner lock probe was negative: filelock recovered an existing lock from a terminated local process; no stale-lock defect is alleged.

## Reviewed file SHA-256

```
58a02a89cd66fca9ab4430ce6db0f042156d758ba35a3b1a163f0303fa777b78  store.py
8995543bac39a7c0b519038eea7b217b5f34892846a004844d35760fdf554395  migration.py
4754c46c5f1170d99513a1ad6f9ebad22514d2309ebff66dfb8c0a6407f94c23  actions.py
9173060e9994d70c937eb6e6be6bdf2b56e308dc32fa5c63948b0401542340e1  action_journal.py
fff196c4d2db1e11c8770436b5ab3289ead8aed9b8bbd015d73383d94acd0356  action_lifecycle.py
3b3741310562ae86860f8c0bfb01b178628c3ec086da24d0a9d295d3f0191a53  action_admission.py
b63cfb53c2e074ac51b688996a85567ab291b98fb30e591733c7c7d828691e4b  cognitive_surface.py
```

Scripts and temporary DB lifecycle are journaled in `code-debug-journal.md`. No live user DB, production state, or repository source was modified by this reviewer.

Verification completed: `.venv/bin/python -m pytest tests/cognitive/test_store.py -k r03 tests/cognitive/test_migration.py -k 'r03 or r04' -q -p no:cacheprovider` → **10 passed, 43 deselected in 1.12s**. These existing tests pass despite the independent reproductions above.
