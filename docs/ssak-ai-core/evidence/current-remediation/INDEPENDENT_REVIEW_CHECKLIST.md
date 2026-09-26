# Independent R*-V review checklist (prep only; not executed)

Prepared: 2026-09-27 03:58 KST · tip bump 2026-09-27 04:18 KST
Code/docs tip under review: `78c2c8f6` (`78c2c8f6f041d6cffce44107612d31c97a2ba1aa`) (`codex/m1-task-events`; no push)
Residual-close pins below are unchanged from the 03:58 prep (R01 `84210aec` … R15 `c21f0695`). Docs-only attack-notes commit advances HEAD afterward; V still attacks tip `78c2c8f6` + residual pins.

Purpose: give a separate reviewer a reproducible punch-list after the implementer priority queue was flushed. **This file does not satisfy any R*-V checkbox and records no V PASS.**

Richer attack playbook (scenarios beyond suite claims): [INDEPENDENT_V_ATTACK_NOTES.md](./INDEPENDENT_V_ATTACK_NOTES.md) — also records no V PASS.

## Review rules

1. The reviewer must be independent of the implementer and must inspect the pinned tip, task card, report, and linked evidence.
2. Run the exact commands below from `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai` with the pinned environment; suite green is evidence, not V PASS.
3. For every card, record dated initials, the attack performed, observed result, and remaining limits before changing any V status.
4. Authority/concurrency cards require failure-model review, not suite green alone.

## Priority cards and residual-close pins

### R01 — protected files at the execution boundary

- Residual-close pin: `84210aec` (`fix(ssak-ai): R01 seatbelt deny + gate digest residual`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_r01_residual.py tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_protection_boundaries.py tests/cognitive/test_protection.py tests/test_sandbox_isolation.py -q -p no:cacheprovider
  ```
- Independent V attack focus: seatbelt profile deny-after-allow rule order; non-Darwin fail-closed behavior; every `require_sandbox` path must refuse shell execution without a sandbox. The `:ro` mount shape is code/test evidence, not a real-daemon V result.

### R02 — authority lifetime, revoke, and approval binding

- Residual-close pin: `12a0af54` (`fix(ssak-ai): R02 require digest on reuse and authorize`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_r02_digest_bound.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_governance.py -q -p no:cacheprovider
  ```
- Independent V attack focus: ancestry evaluation on every authorize; no score-based autonomy; profile/cache callers re-read the revision before allow; all dispatcher and governance paths bind the digest.

### R03 — staged transaction identity

- Residual-close pin: `30af5c9e` (`test(ssak-ai): R03 SoftFileLock cross-process stage identity`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_store.py -q -p no:cacheprovider
  ```
- Independent V attack focus: multi-host/NFS lock semantics beyond the one-host two-process proof; crash-manifest compatibility with R04/R21; foreign `content_identity` must not be hijacked.

### R04 — WAL/snapshot lineage

- Residual-close pin: `52af3bfa` (`test(ssak-ai): R04 mid-digest cross-process snapshot isolation`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
  ```
- Independent V attack focus: snapshot fields must bind logical content and file-bundle evidence; conflicts must imply `passed=False`; multi-host/NFS shared-DB semantics remain unproven.

### R08 — pre-dispatch current revision

- Residual-close pin: `3ab29d11` (`fix(ssak-ai): R08 live freshness_resolver before effect`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest commands:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q -p no:cacheprovider
  .venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py -q -p no:cacheprovider
  ```
- Independent V attack focus: prove production live store/head reads for decision revision, state revision, and policy version immediately before effect; mutate the store in race tests (not only the intent); inspect multi-process reservation/ordering. The implementer code residual is closed; do not turn that into R08-V PASS.

### R10 — UNKNOWN observe/reconcile/restart

- Residual-close pin: `7e0fd643` (`fix(ssak-ai): R10 late-observation history without projection mutate`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
  ```
- Independent V attack focus: timeout must never delete the claim/unlock retry; observe must never redispatch; external non-idempotent UNKNOWN must never auto-retry; multi-process late-history behavior remains open.

### R15 — trusted ACTIVE composition / single owner

- Residual-close pin: `c21f0695` (`test(ssak-ai): R15 composition residual + entry matrix`); review tip `78c2c8f6` (residual-close pin unchanged).
- Exact pytest command:
  ```bash
  .venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py tests/cognitive/test_feature_off_regression.py tests/cognitive/test_r15_composition.py -q -p no:cacheprovider
  ```
- Independent V attack focus: OFF/SHADOW defaults; one task owner; every claimed entry has an integration test; no global ACTIVE default change; verify the composition root against live boot rather than a fixture.

## Explicit non-claims and gates

- **No R*-V PASS is claimed** by this prep document or the implementer evidence.
- **No ops GO, cutover GO, or CR-14 GO** is claimed; ops/CR-14 remains **NO-GO**.
- No multi-host or NFS safety/pass is claimed for R03/R04 or any other card.
- Do not run destructive migration or `R21 --apply` without Human authorization.
- Do not treat architecture/digest/suite green, isolated ACTIVE, or scripted harness results as release GO.

## Next handoff

Implementer priority queue is empty for these cards. Next handoff is Independent V using [INDEPENDENT_V_ATTACK_NOTES.md](./INDEPENDENT_V_ATTACK_NOTES.md), then Human ops judgment; this checklist remains open until an independent reviewer signs each card. **No R*-V / ops / CR-14 GO is recorded here.**
