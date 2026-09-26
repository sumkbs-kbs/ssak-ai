# R08 report — execution freshness / current revision check

Status: **PASS (self-review limitation)** — 2026-09-26 21:25 KST
Prior tip: `4102fdcf` (implementation commit follows)
Reviewer: implementer (마뱀). Independent R08-V not claimed.

## Before / after

- Before: `action_admission.preconditions` called `assert_fresh(readiness, intent.freshness())`, so decision/state/policy could self-compare while only authority was re-resolved.
- After:
  1. `freshness_resolver` on `ActionDispatcher` / `ActionContext` supplies authoritative live binding.
  2. `_authoritative_freshness` always overlays `action_digest=intent.args_digest()` and, when a resolver is wired, uses live decision/state/policy/authority revisions — **not** intent fields as the source of truth.
  3. ACTIVE composition requires `freshness_resolver` alongside journal/sink/authority (`CognitiveSurfaceAdapter`).
  4. Regression tests R08-A1/A2/A3 mutate a live box (decision/state/policy) and assert dispatch 0.

## Acceptance

| ID | Result | Observation |
|----|--------|-------------|
| R08-A1 | PASS | decision/state/policy drift with unchanged authority → STALE_READINESS, calls==0 |
| R08-A2 | PASS | persist-time decision reopen → refuse; mismatched args digest vs live → refuse |
| R08-A3 | PASS | concurrent reopen vs second admit → refuse or single effect; stable head → one DISPATCHED |
| R08-A4 | PASS | stable binding single dispatch (same test file) |
| R08-E | PASS | this folder + pytest logs |
| R08-V | OPEN | independent reviewer pending |

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q -p no:cacheprovider
# 42 passed
.venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py -q -p no:cacheprovider
# 36 passed
```

## Files / symbols

- `action_admission.py`: `_authoritative_freshness`
- `actions.py`: `freshness_resolver` field
- `action_context.py`: protocol property
- `cognitive_surface.py`: ACTIVE requires + wires `_active_freshness`
- `tests/cognitive/test_action_safety.py`: `test_r08_a1`…`a3`

## Limits

- Self-review ≠ independent R08-V ≠ CR-14 / ops GO.
- Implementer/secondary attack dry-run (2026-09-27): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md) — **NOT Independent R08-V**; evidence for future independent reviewer only.
- Unit tests use an injectable live box; production must wire a store-backed resolver that reads decision head / state / active policy (not request body).
- Cross-process reservation locks beyond the admit double-check are not claimed here.
