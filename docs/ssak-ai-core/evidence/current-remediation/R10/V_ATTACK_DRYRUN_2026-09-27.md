# R10 Independent V — attack dry-run (NOT Independent R10-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R10-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R10-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:59 KST  
Executor tip (docs commit parent): `551a55c1365f0d8271aaf22c9d35d7225e276840` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `7e0fd643` (`fix(ssak-ai): R10 late-observation history without projection mutate`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R10  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baseline (ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
# → 34 passed in 6.66s  exit 0
# evidence: pytest_baseline_r10_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_action_safety.py::test_r10_unobserved_cannot_declare_succeeded \
  tests/cognitive/test_action_safety.py::test_r10_settled_projection_rejects_conflicting_observation \
  tests/cognitive/test_action_safety.py::test_r10_late_older_observation_does_not_flip_projection \
  tests/cognitive/test_action_safety.py::test_r10_a4_timeout_does_not_release_claim \
  tests/cognitive/test_active_api.py::test_r10_a1_restart_observe_keeps_dispatch_count_one \
  tests/cognitive/test_action_safety.py::test_r10_dispatch_exception_stays_unknown_until_observation \
  tests/cognitive/test_action_safety.py::test_r10_a2_identical_observation_keeps_ids \
  tests/cognitive/test_action_safety.py::test_r10_a3_stale_or_foreign_observation_refused \
  tests/cognitive/test_active_api.py::test_r10_http_observe_and_pending \
  -v -p no:cacheprovider
# → 9 passed in 1.57s  exit 0
# evidence: pytest_r10_attack_nodes_2026-09-27.txt
```

Inspection transcript: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | Unobserved `ActionObservation` declaring `succeeded` → ValueError | **RUN** | `ActionObservation(observed=False, succeeded=True)` → `ValueError('unobserved ActionObservation cannot declare succeeded')`. `observed=False` alone OK. |
| 2 | Settled claim + conflicting digest → PROJECTION_SETTLED + late history | **RUN** | `test_r10_settled_projection_rejects_conflicting_observation` + `test_r10_late_older_observation_does_not_flip_projection` green; source writes `method="late_observation_history"` with `refusal=PROJECTION_SETTLED`; claim projection fields unchanged. |
| 3 | UNKNOWN/timeout pending — timeout does not clear claim | **RUN** | `test_r10_a4_timeout_does_not_release_claim` green; `pending_with_reasons` docstring: *timeout never clears these rows*. |
| 4 | Crash/restart observe never redispatches | **RUN** | `test_r10_a1_restart_observe_keeps_dispatch_count_one` green (`redispatched is False`, dispatch count 1); HTTP observe also `redispatched: false`. |
| 5 | External UNKNOWN — no auto redispatch without auth | **RUN** | `test_r10_dispatch_exception_stays_unknown_until_observation` green; `observe` docstring *Never redispatches*; all observe return paths set `redispatched=False`. |
| 6 | Two processes late conflicting observes on settled claim | **NOT_RUN** | No R10 multi-process late-observe harness. Existing multiprocessing in `test_action_safety` is R08 dual-dispatch, not late-history. Multi-process live remains Medium/OPEN. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R10-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Multi-process live** late-history / concurrent conflicting observe races (ATTACK_NOTES §7).
3. Mapping UNKNOWN → success in any helper (must stay forbidden).
4. **Ops / CR-14 / production enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R10-V PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer
- Single-process late-history ≠ multi-process PASS

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R10-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
