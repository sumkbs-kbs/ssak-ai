# R10 report — UNKNOWN 실행의 관찰·reconciliation·재시작

- 실행: 2026-09-27 03:57 KST (late-observation history residual)
- tip before: `52af3bfa40ded5d72f3865f1fc4205282ddeb4e5`
- reviewer: 마뱀 (self-review limitation)

## Before / after (residual)

- Before: settled conflicting observe returned `PROJECTION_SETTLED` with **no** canonical Observation history row (refuse-only).
- After:
  1. Settled + differing digest still refuses projection mutation (`accepted=False`, `PROJECTION_SETTLED`; journal revision/digest/record_id unchanged).
  2. Additionally persists `EntityType.OBSERVATION` history via `_persist` with `method=late_observation_history`, `observed_at` from submission/clock, `source=received_at:{isoformat}` so observed_at ≠ received_at is assertable.
  3. Result exposes history id on `observation_record_id` / `records`; claim.observation_record_id stays the first settle id.
  4. Missing action/receipt via `load_record` → `UNKNOWN_ACTION` without claiming history written. Idempotent same-digest replay unchanged.

## R10-A*

Prior A1–A4 still green via `test_action_safety` / `test_active_api`.

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
# 34 passed
```

## Limits

- Independent R10-V open. Single-process late-observation history append closed; multi-process live still Medium.
- Ops/CR-14 still NO-GO.
- Implementer/secondary dry-run (not V): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md)
