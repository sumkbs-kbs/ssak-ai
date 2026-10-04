# Independent deferred-view review

- Date: 2026-10-03
- Lane: bounded independent source review and real library runtime QA
- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Verdict: **PASS within the scope below**, not a repository-wide approval or release gate.
- Dirty-tree production hash: `7763f0a1cd80a751da13dcefae5f228c21d6a4e999448e17373beca59f310fbf`
- Test hash: `fb538d46279988b62e8e5a65551bd96a9a6860cb2f8c1fb6f340b542c0c5e80a`
- Full file mappings: `independent-hashes.txt`. Any source change invalidates this bounded verdict until reassessed.

## Scope and findings

Reviewed `conversation_store.py` against `conversation-store-preimage.txt`, focused new tests, cross-process lock, journal refresh/reconciliation and tombstone paths. Graph search reported project absent; requested fast indexing failed with Transport closed, so precise file/diff reading was used.

No blocking defect found in this patch's deferred flush behavior:

1. Deferred flush acquires both the instance lock and shared flock, invalidates tail memo on new lock entry, and refreshes authoritative state before persistence. Peer deletes are honored from either durable deletion marker or journal tombstone, and clear the stale record/dirty entry.
2. A peer append invalidates the cached sequence equality, causing reconstruction and persistence before the stale writer flushes. The old cached view does not overwrite a newer journal state.
3. Dirty state is added before a potentially failing write and removed only after persistence succeeds. Explicit flush, public-read flush and bounded-window write failures retain retryable work.
4. The local dirty counter does not cause unbounded aggregate lag across cooperating writers: switching writers with a stale cache reconstructs and persists the current journal before the next append. Tested with actual child processes, not only two instances sharing one process.
5. Treating a nonexistent projection as sequence zero in the test helper is legitimate: the journal remains authoritative, a newly deferred conversation may have no projection yet, and the assertion still bounds journal-minus-view lag strictly below eight. Public-read tests subsequently require an actual materialized file at exact journal sequence. This does not waive a safety assertion.

## Executed evidence

- `PYTHONPATH=src .venv/bin/python docs/qa/2026-10-03-residual-close/independent-driver.py` — exit 0, output in `independent-runtime.txt`.
  - Child-process newer append followed by stale-parent flush: revision 2 and both exact messages preserved.
  - Five alternating blocks of seven parent appends plus seven child appends: final revision 72, maximum measured projection lag 7 with configured maximum 8.
  - Child-process delete followed by stale-parent flush: absent projection, public get returns None, durable marker retained.
  - All temporary stores cleaned by TemporaryDirectory.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_view_freshness_contract.py -q -k 'failed or public_read or finite'` — exit 0, **9 passed, 4 deselected in 0.41s**. Covers the three retry paths, five public read surfaces and finite lag.

## Limits

No production data, external model calls, simultaneous write contention stress, full cognitive suite or full application/browser lifecycle were exercised here. Broader worker suite results belong to the worker's evidence; this report does not replace them. `flush_views()` is an explicit convergence point; this bounded review does not claim automatic process-exit flushing. Abrupt termination still relies on journal recovery. No production or test files were changed by this reviewer.
