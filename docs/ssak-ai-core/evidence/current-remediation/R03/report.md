# R03 report — staged transaction ID를 불변 identity로

## Status
PASS (self-review limitation; 독립 인간 검토 대기) — residual close 2026-09-27 03:47 KST

Tip before residual: `e170fbf4`

## Files / symbols
- `store.py`: `TransactionConflictError`, `TransactionManifest.content_identity`, `_stage_locked` idempotent/conflict; **keeps `SoftFileLock`** (shared protocol with VaultEngine / legacy_adapter)
- `tests/cognitive/test_store.py`:
  - `test_r03_a1`…`a4`
  - strengthened `test_r03_a3_concurrent_different_payload_one_wins` (two `CanonicalStore` / two SoftFileLock objects, same lock path)
  - NEW `test_r03_a3_cross_process_different_payload_one_wins` + module `_r03_a3_stage_worker` (`multiprocessing.get_context("spawn")`, Barrier, Queue)

## Before / after
- Before (original): `stage(A,T)` 후 `stage(B,T)`가 manifest를 덮어써 commit이 B를 발행.
- After (card): 동일 content identity → 기존 manifest 반환(바이트 불변); 다른 content → `TransactionConflictError`; A만 commit.
- Residual before 2026-09-27: A3만 in-process threads sharing one SoftFileLock/RLock — **cross-process flock not separately proven**.
- Residual after: two OS processes each construct `CanonicalStore(root, git_enabled=False)` → distinct SoftFileLock objects on the same lock path; Barrier then stage different payloads / same `transaction_id`; exactly one `ok` + one `TransactionConflictError`; commit publishes exactly one statement in `{concurrent-A, concurrent-B}`. SoftFileLock **did serialize**; no switch to `FileLock`.

## Acceptance
- R03-A1: conflict + A only commit — observed
- R03-A2: identical restage keeps manifest bytes — observed
- R03-A3 (threads, dual SoftFileLock instances): exactly one success, one conflict, one published — observed
- R03-A3 (cross-process SoftFileLock): spawn×2 → one ok / one conflict / one published — observed (repeat ≥3 green)
- R03-A4: crash 후 hijack stage conflict; recover publishes original only — observed (spot-check still holds)

## Commands
```
.venv/bin/python -m pytest tests/cognitive/test_store.py -q -p no:cacheprovider
# 26 passed in ~2.6s, exit 0

# r03 nodes flake (3×): 5 passed each
# cross-process node extra 2×: 1 passed each
```

## Limits
- Cross-process SoftFileLock serialization on **one host / one filesystem** is now proven. Still **not** multi-host / multi-volume / NFS-vs-local lock semantics.
- SoftFileLock lock file is removed on release (path identity asserted; file may not exist after unlock).
- PASS ≠ release GO. Ops/CR-14 remains **NO-GO**. Independent R03-V still open.
- Implementer/secondary dry-run (not V): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md)
