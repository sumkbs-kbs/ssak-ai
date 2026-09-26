# R03 report — staged transaction ID를 불변 identity로

## Status
PASS (self-review limitation; 독립 인간 검토 대기)

## Files / symbols
- `store.py`: `TransactionConflictError`, `TransactionManifest.content_identity`, `_stage_locked` idempotent/conflict
- `tests/cognitive/test_store.py`: `test_r03_a1`…`a4`

## Before / after
- Before: `stage(A,T)` 후 `stage(B,T)`가 manifest를 덮어써 commit이 B를 발행.
- After: 동일 content identity → 기존 manifest 반환(바이트 불변); 다른 content → `TransactionConflictError`; A만 commit.

## Acceptance
- R03-A1: conflict + A only commit — observed
- R03-A2: identical restage keeps manifest bytes — observed
- R03-A3: two threads → exactly one success, one conflict, one published — observed
- R03-A4: crash 후 hijack stage conflict; recover publishes original only — observed

## Commands
`.venv/bin/python -m pytest tests/cognitive/test_store.py -q -p no:cacheprovider` → 25 passed

## Limits
- Cross-process flock beyond in-process FileLock not separately proven here (threads share lock).
- PASS ≠ release GO.
