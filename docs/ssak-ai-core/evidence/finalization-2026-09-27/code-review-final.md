# Independent final recovery / migration rereview

Date: 2026-09-27. Repository `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.
HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus the uncommitted file bytes pinned below.

**Scoped verdict: PASS for the repaired R04 snapshot-lineage and R09/R10 observation-publication defects.** The original FAIL report remains valid for the original hashes only. No remaining blocker found in these two fixes. This verdict does not cover the parent-owned R08/ACTIVE composition, whole-suite verification, real-corpus rehearsal, multi-host storage, power-loss, or operational cutover.

## Independent executed evidence

1. Re-ran the original `code-repro.py` logic against current source, changing only its race barrier to fire once per thread. This is necessary because the corrected implementation re-reads records during canonical retry; an unconditional barrier on every read would introduce a test deadlock. Observed:

```
race accepted= [False, True] revisions= [0, 1]
race claim= settled revision= 1 observation= observation:<stable-id> pending= 0
crash exception= injected observation sink failure
crash claim= pending revision= 0 observation= None pending= 1
```

The conflicting first submission now has one winner. Failed canonical observation storage leaves the original pending claim discoverable, reversing both original failures.

2. Re-ran the original real-SQLite A→B→A mutation schedule, adapting its first boundary from `source.snapshot()` to `_run_snapshot()` because the initial snapshot is now made from a private backup. Actual WAL commits change event 1 after the backup and restore it before the final live measurement. The first run imports the original snapshot; the immediate ordinary rerun observes the original source:

```
first_passed True first_unchanged True second_passed True mapping_identical True
```

This directly reverses the original `second_passed False` mapping conflict. The mutable live source is no longer the import/replay/rollback source.

3. Independently executed:

```
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/cognitive/test_observation_atomicity.py \
  tests/cognitive/test_migration.py::test_run_imports_original_payload_when_wal_source_changes_and_returns \
  tests/cognitive/test_migration.py::test_dry_run_keeps_source_unchanged \
  -q -p no:cacheprovider
```

Result: **10 passed in 2.29s**. This includes two independent process publishers, actual `os._exit(23)` between canonical append and SQLite publication, retry preserving original canonical timestamps/IDs, receipt-less recovery, exact replay, late receipt refusal, sink failure, WAL ABA, and ordinary quiet-source migration.

## Source review

- `action_journal.py:123`: `BEGIN IMMEDIATE` serializes writers before comparing expected receipt/revision/status. The canonical append callback runs only for the matching pending claim. SQLite commits the projection after the callback; callback exceptions or process termination roll back the projection.
- `action_recovery.py`: reconciliation prepares records without publishing. Stable IDs bind project, action, expected receipt, observation digest (including observed_at). Existing canonical records are reused after an interrupted publication, preserving their original timestamps. A lost CAS re-reads the winner and rejects a conflicting stale request; exact request replay remains idempotent.
- `action_journal.py:109`: dispatch receipt attachment cannot overwrite a published observation revision. Receipt-less recovery reconstructs the durable claim intent and an UNKNOWN base receipt without dispatching.
- `migration.py:466`: SQLite backup captures committed WAL contents into a private temporary DB. The report's initial logical digest is calculated from this backup. Import, replay, and rollback explicitly receive that frozen source; only the final unchanged check reads the live source. Temporary source copy is removed after the run. Physical file-bundle digest remains auxiliary evidence, not an atomic physical backup checksum.
- `store.py` is unchanged from the original review. Existing immutable transaction identity checks remain intact.

## Scope caveats

The SQLite journal and canonical store are still separate durable systems. The implemented contract permits canonical rows ahead of the journal after a crash and repairs the projection on an identical observation retry; it does not claim an atomic cross-system commit. The executed process-death regression verifies that intended contract. Local SQLite/CanonicalStore semantics are covered; distributed NFS or multiple independent journals are not.

Runtime direct reconciliation has its own observation-before-receipt path; this review's publication verdict is specifically for `submit_observation` recovery. Parent-owned R08 canonical digest/freshness composition must receive its own final review. No live user database or repository source was changed by this reviewer.

## SHA-256 binding

```
58a02a89cd66fca9ab4430ce6db0f042156d758ba35a3b1a163f0303fa777b78  src/antigravity_k/engine/cognitive/store.py
22ea2874342c0654df30382c81efea9d9f63f5603b19673a02d847250c920fb2  src/antigravity_k/engine/cognitive/migration.py
5542dda257238612d91a71a68604836570f4e556787eccfa74f699128797b597  src/antigravity_k/engine/cognitive/actions.py
d114faa3a849af6cc4397e11a8d76ffd7d0d6a1b4b0b1deccaaa87e5c0c11a3b  src/antigravity_k/engine/cognitive/action_journal.py
26811552ea5cad1e970fe7eda7867a02a2bc8994ae5f597011bde156ba7d2db2  src/antigravity_k/engine/cognitive/action_lifecycle.py
52ea1fad166a1837ea5e4f31ef8474354aa91025f6dec77a1f711e7e3e857bf8  src/antigravity_k/engine/cognitive/action_recovery.py
7d1819849b35d4ebf617c821afdb284ce9981edc39f848ed545f17210c36c756  src/antigravity_k/engine/cognitive/action_recovery_records.py
00e6ccd76376d7a815c9ef0a24216094c0b368f83ef28023f7ddbf91a5e0c6f3  tests/cognitive/test_observation_atomicity.py
9819c35ea34bd68b5ef15e3bb461e7986f5d07d15d1ba559edd698fe2f199005  tests/cognitive/test_migration.py
```

## Addendum: additive receipt detail dependency change

The later production structured-read integration revealed that canonical receipts dropped in-memory tool result detail. `ExecutionReceiptPayload.detail` now defaults to an empty string for compatibility; serialization and recovery decoding preserve it. Independently re-read these changes and re-ran all eight `test_observation_atomicity.py` regressions in the 30-test composition selection (**30 passed in 7.99s**). Actual process crash/CAS/retry behavior remains green; canonical read-result text also survives reopening the store.

Scoped recovery PASS is extended to these new dependency hashes:

```
0a600600ded4597271eb0fe530fb4423c1d9bb3085b1051ada367f573c58e37f  src/antigravity_k/engine/cognitive/models.py
a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7  src/antigravity_k/engine/cognitive/action_types.py
f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c  src/antigravity_k/engine/cognitive/action_recovery_records.py
```

Journal/lifecycle/recovery hashes and migration hash above remain unchanged. Composition's separate final verdict and full selection command are in `composition-review-final.md`.

## Final compatibility dependency repin (supersedes earlier model hash)

**Scoped PASS reaffirmed** at HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus current dirty dependencies. Independently reviewed targeted absent-additive-field preservation in `to_wire` and all ten dedicated tests. Real pre-upgrade persisted bytes/issued ContextHandle resolve correctly; explicit defaults and nondefault result detail remain intact. Compatibility + recovery + installed composition selection: **38 passed in 11.22s**.

Final `models.py` SHA-256: `afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945`. Dedicated compatibility test SHA-256: `38c31ac70f2854681fcaa16bd3f3b255daebbe451e7802503bf3bcfd18f58fca`. `action_types.py` remains `a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7`; `action_recovery_records.py` remains `f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c`. Other recovery/migration pins remain unchanged. Full method and command: `wire-compatibility-review.md`.
