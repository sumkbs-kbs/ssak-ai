# R08 Independent V — attack dry-run (NOT Independent R08-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R08-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R08-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:51 KST  
Executor tip (docs commit parent): `b745adf60e6aaee0cd969f71460ffa01f85fb143` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `3ab29d11` (`fix(ssak-ai): R08 live freshness_resolver before effect`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R08  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baselines (from ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q -p no:cacheprovider
# → 46 passed in 1.56s  exit 0
# evidence: pytest_baseline_safety_actions_2026-09-27.txt

.venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py -q -p no:cacheprovider
# → 36 passed, 1 warning in 13.41s  exit 0
# evidence: pytest_baseline_active_surface_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_action_safety.py::test_r08_a1_decision_state_policy_drift_blocks_dispatch_when_authority_unchanged \
  tests/cognitive/test_action_safety.py::test_r08_a2_live_freshness_or_args_change_during_persist_blocks_effect \
  tests/cognitive/test_action_safety.py::test_r08_a3_concurrent_reopen_and_dispatch_ordering \
  tests/cognitive/test_r15_composition.py::test_r15_active_requires_freshness_resolver \
  -v -p no:cacheprovider
# → 4 passed in 1.11s  exit 0
# evidence: pytest_r08_attack_nodes_2026-09-27.txt
```

Inspection transcript: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | ACTIVE adapter without `freshness_resolver` → refuse, effect 0 | **RUN** | Isolated construct: all ACTIVE deps present except `freshness_resolver=None` → `SurfaceNotReadyError` (message includes “live freshness resolver”). Control with resolver wired → `activate` succeeds. Also covered by `test_r15_active_requires_freshness_resolver`. Gate: `CognitiveSurfaceAdapter._require_active_dependencies` checks `freshness_resolver is None`. |
| 2 | Intent freshness still matches readiness, but live store head advanced → STALE / calls 0 | **RUN** (box stand-in) | `test_r08_a1` / `test_r08_a2` mutate `_resolver_from_box` **box** heads (decision reopen on persist), not only the intent object → `STALE_READINESS`, dispatcher calls `[]`. **Caveat:** box is an injectable store stand-in, not a live multi-process CanonicalStore/daemon head. |
| 3 | Authority fresh while decision/state/policy stale → still refuse | **RUN** | A1 + inspection: authority resolver still allows; box `decision_revision+1` → refuse `STALE_READINESS`, calls `[]`. Authority alone does not green-light. |
| 4 | Args mutated / digest drift; overlay uses `intent.args_digest()` | **RUN** | A2 mismatched readiness+args → STALE. Inspection: evil resolver returns `action_digest="EVIL"`; `_authoritative_freshness` always overlays `action_digest=intent.args_digest()` (both resolver and fallback branches). |
| 5 | Two concurrent admit paths; multi-process preferred | **NOT_RUN** | Reason: no Human/live multi-process daemon harness in this dry-run. Existing `test_r08_a3` is **in-process threads** only; ATTACK_NOTES explicitly say multi-process reservation remains open and in-process alone must not claim PASS. |
| 6 | Production boot wired resolver reads durable heads (not intent / `_matching_freshness`) | **RUN** (inspection) | `_attach_cognitive_surface` is **SHADOW-only**; early-returns unless `effective_mode == SHADOW`; never installs ACTIVE and never wires `freshness_resolver`. `_matching_freshness` appears **only in tests** (`src/` hits: NONE). `run_active` wires `freshness_resolver=self._active_freshness` → injected callable after require-deps. **Production durable store/policy head resolver for ACTIVE is not installed at boot** — remains OPEN for independent V / ops composition. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R08-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Multi-process** admit/reservation race against a real shared store/daemon (Attack 5).
3. **Production ACTIVE** composition that supplies a **store/policy-backed** `freshness_resolver` (Attack 6 gap): boot path currently refuses silent ACTIVE; no durable-head wiring to attack live yet.
4. Do not treat fixture `_matching_freshness` or suite green as production evidence.
5. **Ops / CR-14 / production ACTIVE enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R08-V PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R08-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
