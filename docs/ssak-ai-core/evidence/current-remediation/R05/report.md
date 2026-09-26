# R05 report — 필수 Context와 COMPLETE 계약

## Status
PASS (self-review limitation)

## Changes
- Required goal packed before optional L1 limit/budget
- Goal absent from package → INCOMPLETE + missing_ids
- stale state_revision (< projection head) → INCOMPLETE
- Missing evidence referenced by goal → INCOMPLETE

## Acceptance
A1–A4 observed via test_r05_* ; pytest test_context.py → 20 passed

## Limits
THINK blocking at caller is R14/R15. PASS ≠ release GO.
