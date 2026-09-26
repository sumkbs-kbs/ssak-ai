# R10 report — UNKNOWN 실행의 관찰·reconciliation·재시작

- 실행: 2026-09-26 21:34 KST (residual close)
- tip before: `261b5e66`
- reviewer: 마뱀 (self-review limitation)

## Before / after (residual)

- Before: `ActionObservation(observed=False, succeeded=True)` was constructible; settled claims could accept a conflicting observation and mutate projection (success↔fail flip).
- After:
  1. `ActionObservation.__post_init__` rejects unobserved + succeeded.
  2. `submit_observation` returns `PROJECTION_SETTLED` when claim status is settled and digest differs (idempotent same-digest replay still allowed).
  3. Residual tests cover forge, UNKNOWN-on-crash, and non-downgrade.

## R10-A*

Prior A1–A4 still green via `test_action_safety` / `test_active_api`.

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
# 33 passed
```

## Limits

- Independent R10-V open. Full late-observation history append (non-mutating rows) still not implemented — conflicting observe is refused instead.
- Ops/CR-14 still NO-GO.
