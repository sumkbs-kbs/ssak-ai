# R15 report — trusted ACTIVE composition

Status: **PASS (self-review limitation)** — 2026-09-26 KST
Reviewer: implementer (same agent). Independent R15-V not claimed.

## Evidence basis

- Owned modules: `dependencies.py`, `cognitive_active_api.py`, `cognitive_surface.py`, `agent_runtime.py`
- Suite: `test_active_api.py` + `test_surface.py` + `test_feature_off_regression.py` + `test_r15_composition.py` → **48 passed**
- OFF/SHADOW defaults preserved in feature_off suite (also part of R22-A2).
- Entry matrix: `ENTRY_MATRIX.md` (code + `measure_surface_reach`).

## Acceptance (suite-backed)

| ID | Result |
|----|--------|
| R15-A1..A6 | PASS via active/surface/feature_off suites (self-review) |
| R15 residual composition | PASS via `test_r15_composition` (503 / body inject / boot skip ACTIVE / observe never ACTIVE / entry labels / freshness required) |
| R15-E | PASS |
| R15-V | NOT independent |

## 2026-09-26 follow-up (failure-model residual)

Closed implementer residuals without flipping production default:

- Unconfigured ACTIVE → 503
- Body cannot inject approver/project_id/project_root/authority/readiness/args/tool/service
- `_attach_cognitive_surface` skips `mode=active`
- `observe_interaction` ignores ACTIVE adapters
- ENTRY_MATRIX documented + labels regression

## Limits

- Production default remains OFF / not ops-enabled. Self-review ≠ release GO.
- Implementer/secondary attack dry-run (2026-09-27): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md) — **NOT Independent R15-V**.
- Independent R15-V still open.
- Production ACTIVE service must wire store-backed freshness_resolver (not fixture `_matching_freshness`).
