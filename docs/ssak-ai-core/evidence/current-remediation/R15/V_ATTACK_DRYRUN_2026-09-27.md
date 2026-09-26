# R15 Independent V — attack dry-run (NOT Independent R15-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R15-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R15-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:53 KST  
Executor tip (parent): `42e109c4c5471471e3744305a0ede4dc40fcf9ec` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `c21f0695` (`test(ssak-ai): R15 composition residual + entry matrix`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R15  
Verdict slots in ATTACK_NOTES: **left blank / OPEN**

## Pytest baseline (ATTACK_NOTES §4)

```bash
.venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py \
  tests/cognitive/test_feature_off_regression.py tests/cognitive/test_r15_composition.py \
  -q -p no:cacheprovider
# → 48 passed, 1 warning in 16.75s  exit 0
# evidence: pytest_baseline_r15_2026-09-27.txt
```

Composition / feature_off nodes also re-run: **12 passed** (`pytest_r15_attack_nodes_2026-09-27.txt`).

Inspection: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario | Status | Observed |
|---|----------|--------|----------|
| 1 | Default / missing cognitive_core → never silent ACTIVE | **RUN** | `CognitiveCoreSettings.from_config` with empty/`enabled=false` (+`mode=active`) → `effective_mode=OFF`. Covered by `test_r15_default_config_is_off` + feature_off suite. |
| 2 | Boot `mode=active` does not install ACTIVE adapter | **RUN** | Source: `_attach_cognitive_surface` early-returns unless `effective_mode == SHADOW`. `test_r15_boot_attach_never_installs_active` green. Fixture ACTIVE ≠ boot. |
| 3 | ACTIVE HTTP without app.state service → 503 | **RUN** | `test_r15_unconfigured_active_returns_503` asserts 503 / “not configured”. |
| 4 | Body extras forbidden → 422 | **RUN** | `test_r15_body_cannot_inject_composition_fields` (extra: forbid). |
| 5 | ENTRY_MATRIX vs fresh `measure_surface_reach` | **RUN** | Re-ran `measure_surface_reach(source_root=Path("src"))`; test required labels still present (`missing=NONE`). Matrix still documents ACTIVE HTTP owner = `CognitiveActiveService` only; static `reaches_core` ≠ `actual_active`. |
| 6 | SHADOW `observe_interaction` never `run_active` | **RUN** | Source calls only `surface.run_shadow`; returns None unless SHADOW. Docstring mentions `run_active` as the separate Human path — not invoked. `test_r15_observe_interaction_never_runs_active` green. |

## Remaining OPEN

1. **Independent R15-V** — this is dry-run only.
2. Live production boot probe beyond unit/`_attach` source (pass bar asks composition-root vs live boot).
3. Enabling production ACTIVE / ops cutover / CR-14 — **NO-GO**.
4. Production ACTIVE must still wire store-backed `freshness_resolver` (not `_matching_freshness`) when Human enables service.
5. Multi-host ACTIVE ownership.

## Explicit non-claims

- **No Independent R15-V PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
