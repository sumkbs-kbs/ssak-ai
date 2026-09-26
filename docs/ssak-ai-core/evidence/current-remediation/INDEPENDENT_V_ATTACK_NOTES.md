# Independent V attack notes (playbook only; no V PASS)

Prepared: 2026-09-27 04:18 KST  
Review tip: `78c2c8f6` (`78c2c8f6f041d6cffce44107612d31c97a2ba1aa`) on `codex/m1-task-events` (ahead; **no push**) — product/code tip for V; this file lands in a docs-only follow-up commit  
Residual-close pins: still those in [INDEPENDENT_REVIEW_CHECKLIST.md](./INDEPENDENT_REVIEW_CHECKLIST.md) (R01 `84210aec`, R02 `12a0af54`, R03 `30af5c9e`, R04 `52af3bfa`, R08 `3ab29d11`, R10 `7e0fd643`, R15 `c21f0695`) — tip advances docs/queue only. Tip note 2026-09-27 05:37 KST: dry-runs + R08/R10 multiproc PARTIAL through `e4add6b6`; residual-close pins unchanged; no V PASS.

## Purpose

별도 검토자(implementer ≠ reviewer)가 R*-V를 **공격적으로** 검증하기 위한 실행형 playbook이다.  
**스위트 green ≠ Independent V PASS.** 이 문서는 V를 닫지 않으며, 각 카드 Result 칸은 비워 둔다.

관련 문서:

- Checklist: [INDEPENDENT_REVIEW_CHECKLIST.md](./INDEPENDENT_REVIEW_CHECKLIST.md)
- Failure model: [FAILURE_MODEL_RESIDUAL_REVIEW.md](./FAILURE_MODEL_RESIDUAL_REVIEW.md)
- Status: [../../CURRENT_REMEDIATION_STATUS.md](../../CURRENT_REMEDIATION_STATUS.md)
- Per-card reports: [R01/report.md](./R01/report.md) · [R02/report.md](./R02/report.md) · [R03/report.md](./R03/report.md) · [R04/report.md](./R04/report.md) · [R08/report.md](./R08/report.md) · [R10/report.md](./R10/report.md) · [R15/report.md](./R15/report.md) · [R15/ENTRY_MATRIX.md](./R15/ENTRY_MATRIX.md)

## Explicit non-claims

- **No R*-V PASS** (R01–R04, R08, R10, R15 포함) is claimed by this file or by suite green.
- **No ops GO, cutover GO, or CR-14 GO.**
- **No multi-host / NFS PASS** for R03/R04 (or any card).
- Do not treat self-review PASS, digest/architecture green, isolated ACTIVE, or scripted harness as release GO.
- Do not run destructive migration or `R21 --apply` without Human authorization.

## Recommended review sequence

FM priority (blast radius → boundary → identity → lineage):

1. **R08** — live freshness vs intent / production wiring  
2. **R15** — composition root + ACTIVE defaults  
3. **R01** — seatbelt deny-after-allow + require_sandbox  
4. **R02** — digest-bound reuse / authorize  
5. **R10** — UNKNOWN / timeout / late history  
6. **R03** — SoftFileLock stage identity (then multi-host note)  
7. **R04** — snapshot BEGIN + content vs file_bundle (before any R21 apply)

카드 본문은 위 순서와 동일하게 둔다.

Working directory for all baseline commands:

`/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

---

## R08 — pre-dispatch current revision

### 1. Goal of V

프로덕션이 effect 직전에 **store/head 기반** `freshness_resolver`로 decision/state/policy/authority를 읽고, intent self-compare나 fixture `_matching_freshness`로 우회되지 않음을 증명한다.

### 2. Pins

- Residual-close: `3ab29d11` (`fix(ssak-ai): R08 live freshness_resolver before effect`)
- Evidence: [R08/](./R08/) · [R08/report.md](./R08/report.md)
- Review tip: `78c2c8f6` (checklist residual pins unchanged)

### 3. Symbols to re-read

- `src/antigravity_k/engine/cognitive/action_admission.py` — `_authoritative_freshness`, `preconditions` → `assert_fresh`
- `src/antigravity_k/engine/cognitive/actions.py` — `ActionDispatcher.freshness_resolver`
- `src/antigravity_k/engine/cognitive/action_context.py` — protocol `freshness_resolver`
- `src/antigravity_k/engine/cognitive_surface.py` — ACTIVE requires resolver; `_active_freshness`
- Fixture trap: `tests/cognitive/test_surface.py` / `test_active_api.py` — `_matching_freshness` (테스트 전용; production 근거로 쓰지 말 것)
- Live-box style: `tests/cognitive/test_action_safety.py` — `test_r08_a1`…`a3`, `_resolver_from_box`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** ACTIVE adapter without `freshness_resolver`  
   **When** construct / activate path runs  
   **Then** `SurfaceNotReadyError` (or equivalent refuse) — effect 0. Inspect `CognitiveSurfaceAdapter` ACTIVE gate (`freshness_resolver is None`).

2. **Given** intent.freshness() still matches readiness, but live store head for `decision_revision` (or state/policy) advanced after persist  
   **When** admit/dispatch uses `_authoritative_freshness` with a **store-backed** resolver (not `_matching_freshness`)  
   **Then** STALE / refuse, dispatcher call count 0. Mutate the **store/box**, not only the intent object.

3. **Given** authority_revision fresh while decision/state/policy stale  
   **When** effect attempted  
   **Then** still refuse (authority alone must not green-light). Compare against R08-A1 shape in `test_action_safety.py`.

4. **Given** args mutated between intent persist and effect (digest drift)  
   **When** resolver returns live revisions but `action_digest` overlays `intent.args_digest()`  
   **Then** mismatch refuse; no effect. Confirm overlay always uses args digest, never request-body digest alone.

5. **Given** two concurrent admit paths on same binding (multi-process preferred over threads)  
   **When** one reopens decision head mid-admit  
   **Then** at most one DISPATCHED; other refuse or single-effect. Multi-process reservation remains **open** — document observed ordering; do not claim PASS from in-process alone.

6. **Given** production boot (`_attach_cognitive_surface` / ACTIVE service install)  
   **When** inspect wired resolver callable  
   **Then** it must read durable heads (store/policy), not echo intent or HTTP body. Fixture `_matching_freshness` appearing only in tests is expected; production wiring must differ.

### 6. Pass bar for reviewer (later)

Dated initials + (a) production resolver source listing proving store/head reads, (b) race evidence that mutates store not only intent, (c) ACTIVE refuse without resolver, (d) explicit multi-process reservation note (PASS only if that scope was attacked). Suite green alone is insufficient.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R08/V_ATTACK_DRYRUN_2026-09-27.md](./R08/V_ATTACK_DRYRUN_2026-09-27.md)
- Multi-process reservation/ordering beyond single-host SoftFileLock JSON box stand-in (see R08 dry-run Attack 5 PARTIAL; production ACTIVE/daemon store-head still open)
- Treating fixture `_matching_freshness` as production evidence
- Ops / CR-14 / production ACTIVE enablement

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R15 — trusted ACTIVE composition / single owner

### 1. Goal of V

프로덕션 composition root가 OFF/SHADOW 기본을 유지하고, ACTIVE effect는 단일 owner(`CognitiveActiveService`)만 가지며, HTTP body/boot가 권한·서비스 객체를 주입하지 못함을 증명한다.

### 2. Pins

- Residual-close: `c21f0695` (`test(ssak-ai): R15 composition residual + entry matrix`)
- Evidence: [R15/](./R15/) · [R15/report.md](./R15/report.md) · [R15/ENTRY_MATRIX.md](./R15/ENTRY_MATRIX.md)

### 3. Symbols to re-read

- `src/antigravity_k/api/dependencies.py` — `_attach_cognitive_surface` (SHADOW-only attach; ACTIVE skipped)
- `src/antigravity_k/api/routes/cognitive_active_api.py` — `extra: forbid` models; unconfigured → **503**
- `src/antigravity_k/engine/cognitive_surface.py` — ACTIVE deps (journal/sink/authority/**freshness_resolver**/activation_authorizer)
- `src/antigravity_k/engine/cognitive_surface_types.py` — `SurfaceMode`, `effective_mode` (enabled=false → OFF)
- `src/antigravity_k/engine/agent_runtime.py` — `observe_interaction` SHADOW-only
- `src/antigravity_k/engine/cognitive_surface_measurement.py` — `measure_surface_reach`
- `tests/cognitive/test_r15_composition.py` — composition residual nodes

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_active_api.py tests/cognitive/test_surface.py tests/cognitive/test_feature_off_regression.py tests/cognitive/test_r15_composition.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** default / missing cognitive_core config  
   **When** `CognitiveCoreSettings.from_config` / feature_off path  
   **Then** `effective_mode` is OFF (or SHADOW only when explicitly enabled+shadow) — never silent ACTIVE.

2. **Given** config `mode=active` at boot  
   **When** `_attach_cognitive_surface` runs  
   **Then** attach returns without installing ACTIVE adapter (SHADOW-only branch). Read source; do not trust fixture ACTIVE as boot.

3. **Given** ACTIVE HTTP without `app.state` service  
   **When** POST prepare/activate/observe  
   **Then** **503** `"Cognitive ACTIVE service is not configured"` — never false success.

4. **Given** request body with extras (`authority`, `project_root`, `service`, `approver` injection fields, readiness objects, etc.)  
   **When** Pydantic models with `model_config = {"extra": "forbid"}` validate  
   **Then** **422**; no trust elevation from body.

5. **Given** ENTRY_MATRIX.md claimed rows  
   **When** re-run `measure_surface_reach(source_root=Path("src"))` and diff labels/owners  
   **Then** every claimed entry still matches matrix; no new entry that both reaches core and can effect without documented owner. Static `reaches_core` ≠ `actual_active`.

6. **Given** SHADOW adapter + `observe_interaction`  
   **When** episode completes  
   **Then** observe never calls `run_active`; effect owner remains legacy ToolExecutor. Attempt to force ACTIVE observe path must no-op or refuse.

### 6. Pass bar for reviewer (later)

Composition-root reading against **live boot** (not only `test_r15_composition`), ENTRY_MATRIX vs fresh `measure_surface_reach`, 503 + forbid body probes, and written confirmation that production default was not flipped. Still not CR-14 GO.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R15/V_ATTACK_DRYRUN_2026-09-27.md](./R15/V_ATTACK_DRYRUN_2026-09-27.md)
- Enabling production ACTIVE / ops cutover
- Confusing isolated HTTP fixture Brain with production boot
- Multi-host ACTIVE ownership

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R01 — protected files at the execution boundary

### 1. Goal of V

보호 경로 write가 seatbelt **deny-after-allow**·Docker `:ro`·`require_sandbox` refuse로 실제 실행 경계에서 막히는지, regex/hint만으로 대체되지 않는지 공격한다.

### 2. Pins

- Residual-close: `84210aec` (`fix(ssak-ai): R01 seatbelt deny + gate digest residual`)
- Evidence: [R01/](./R01/) · [R01/report.md](./R01/report.md)

### 3. Symbols to re-read

- `src/antigravity_k/engine/sandbox.py` — `SandboxRunner`, `_protected_write_deny_section`, seatbelt profile assembly (deny after `/var/folders` allow), Docker `-v …:ro`, `require_sandbox` refuse when disabled
- `src/antigravity_k/tools/permission_gate.py` — `protection_action_digest`, gate before overrides
- `src/antigravity_k/api/routes/agent_tools.py` — call sites with `require_sandbox=True`
- Tests: `tests/cognitive/test_r01_residual.py`, `test_r01_protected_sandbox.py`, `test_protection_boundaries.py`, `tests/test_sandbox_isolation.py`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_r01_residual.py tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_protection_boundaries.py tests/cognitive/test_protection.py tests/test_sandbox_isolation.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** generated seatbelt profile text (restrict mode)  
   **When** inspect rule order: broad `/tmp`·`/var/folders` allow vs `_protected_write_deny_section`  
   **Then** protected deny **follows** broad allow (later rule wins on Darwin). Print/profile dump; fail if deny precedes and can be re-opened by later allow.

2. **Given** project root under `/var/folders/…` (pytest tmp) with protected relative paths  
   **When** sandboxed write/unlink via interpreter targeting protected path  
   **Then** deny at seatbelt; no quiet host write. Beyond suite: try parent-dir rename / symlink write shapes if not already covered.

3. **Given** Docker sandbox path  
   **When** inspect `docker_cmd` mount lines for protected host paths  
   **Then** `:ro` remount over `/workspace/{rel}`. Cmd-shape alone ≠ live-daemon V — note if real daemon not exercised.

4. **Given** `SandboxRunner(..., enabled=False, require_sandbox=True)`  
   **When** execute shell  
   **Then** refuse (`Sandbox is disabled… raw execution is refused`) — no unsandboxed fallback.

5. **Given** non-Darwin host without Docker (or forced fail-closed path)  
   **When** sandbox enabled  
   **Then** fail-closed; no silent raw host shell. Document platform actually tested.

6. **Given** `protection_action_digest` bound approval for path A  
   **When** same approval reused for path/args B  
   **Then** gate deny. Confirm cognitive protection runs **before** tool overrides; injected guard root preserved.

### 6. Pass bar for reviewer (later)

Profile text order evidence + at least one real sandbox execution deny + require_sandbox refuse + platform note (Darwin/Linux/Docker). `:ro` live daemon optional but required for claiming Docker mount V; otherwise leave Docker as code-shape only.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R01/V_ATTACK_DRYRUN_2026-09-27.md](./R01/V_ATTACK_DRYRUN_2026-09-27.md)
- Live Docker daemon RO proof if not run
- Treating shell-regex hints as the boundary when seatbelt disabled
- Multi-host sandbox policy

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R02 — authority lifetime, revoke, and approval binding

### 1. Goal of V

모든 reuse/authorize 경로가 **non-empty action digest**에 결박되고, ancestry/revoke가 우회되지 않으며 score-based autonomy가 없음을 증명한다.

### 2. Pins

- Residual-close: `12a0af54` (`fix(ssak-ai): R02 require digest on reuse and authorize`)
- Evidence: [R02/](./R02/) · [R02/report.md](./R02/report.md)

### 3. Symbols to re-read

- `src/antigravity_k/engine/cognitive/authority.py` — `AuthorityProfile.reuse_approval` (empty digest → `DIGEST_MISMATCH`)
- `src/antigravity_k/engine/cognitive/governance.py` — `GovernanceGate.authorize_execution` (None/missing → deny `"실행 직전 action digest 결박이 없다"`); `ToolGovernanceAdapter`
- Lifecycle: delegate expiry inherit, transitive `revoke`, `_ancestor_failure` (see `test_r02_authority_lifecycle.py`)
- Tests: `tests/cognitive/test_r02_digest_bound.py`, `test_r02_authority_lifecycle.py`, `test_governance.py`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_r02_digest_bound.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_governance.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** valid `ApprovalUse`  
   **When** `reuse_approval(..., action_digest="")` or omit digest  
   **Then** `DIGEST_MISMATCH` / not reusable — empty must not skip check.

2. **Given** `GovernanceOutcome` with digest D  
   **When** `authorize_execution(..., action_digest=None)` or mismatched digest  
   **Then** `allowed=False` with missing-binding or mismatch reason.

3. **Given** `ToolGovernanceAdapter` admit path  
   **When** reauthorized outcome flows to `authorize_execution`  
   **Then** adapter passes `reauthorized.action_digest` (rg call sites; no omit).

4. **Given** parent grant revoked  
   **When** grandchild evaluates / authorizes  
   **Then** deny via ancestry (`_ancestor_failure`); no orphan allow.

5. **Given** child grant with `expires=None` while parent has finite expiry  
   **When** past parent expiry  
   **Then** child cannot outlive parent.

6. **Given** profile/cache caller holding stale revision  
   **When** allow decision  
   **Then** must re-read authority revision before allow (no score-based autonomy shortcut). Hunt any caller constructing HumanApproval outside `authority.py`.

### 6. Pass bar for reviewer (later)

All authorize/reuse entry points listed with digest-required evidence; revoke ancestry probe; statement that no score-autonomy path was found (or FAIL with path). Cross-process grant cache still not required for card PASS unless scoped in.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R02/V_ATTACK_DRYRUN_2026-09-27.md](./R02/V_ATTACK_DRYRUN_2026-09-27.md)
- Cross-process / replicated grant cache freshness
- Multi-host authority projection

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R10 — UNKNOWN observe / reconcile / restart

### 1. Goal of V

timeout·crash 후 claim이 지워지거나 자동 redispatch되지 않고, unobserved success가 불가능하며, settled 충돌 observe는 projection을 바꾸지 않고 late history만 남김을 증명한다.

### 2. Pins

- Residual-close: `7e0fd643` (`fix(ssak-ai): R10 late-observation history without projection mutate`)
- Evidence: [R10/](./R10/) · [R10/report.md](./R10/report.md)

### 3. Symbols to re-read

- `src/antigravity_k/engine/cognitive/actions.py` — `reconcile` / observe; `late_observation_history`; `pending_with_reasons` docstring (*timeout never clears*); `redispatched=False`
- `src/antigravity_k/engine/cognitive/action_types.py` — unobserved invariant (`ValueError`); `ActionRefusal.PROJECTION_SETTLED`
- `src/antigravity_k/engine/cognitive/action_journal.py` — claim / `pending_reason` / SETTLED
- Tests: `tests/cognitive/test_action_safety.py` (`test_r10_unobserved_cannot_declare_succeeded`, settled + late history nodes), `test_active_api.py`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** `ActionObservation` with unobserved / missing measurement declaring `succeeded`  
   **When** construct or submit  
   **Then** `ValueError` matching `unobserved` — cannot forge success.

2. **Given** settled claim + conflicting observation digest  
   **When** reconcile/observe  
   **Then** `accepted=False`, `PROJECTION_SETTLED`; journal revision/digest/`claim.observation_record_id` unchanged; history row `method=late_observation_history` with `source=received_at:…` and distinct `observed_at`; result may expose history id only.

3. **Given** UNKNOWN / timeout pending claim  
   **When** operator timeout path / `pending_with_reasons`  
   **Then** claim row remains; timeout does **not** unlock/delete for auto-retry. Inspect journal pending_reason.

4. **Given** crash after effect, process restart  
   **When** recovery observe then any dispatch attempt  
   **Then** observe never redispatches (`redispatched=False`); dispatch count stays 1 for original binding.

5. **Given** external non-idempotent tool UNKNOWN  
   **When** retry without explicit human/retry authorization  
   **Then** no auto redispatch (module contract).

6. **Given** two processes submitting late conflicting observes on same settled claim  
   **When** concurrent reconcile  
   **Then** projection non-downgrade holds; history append semantics documented. Single-host SoftFileLock spawn is PARTIAL (see dry-run Attack 6); multi-host/NFS remains **Medium/open** — do not claim PASS from single-process or single-host alone.

### 6. Pass bar for reviewer (later)

Evidence that timeout leaves claim, observe never redispatches, unobserved cannot succeed, settled+conflict → PROJECTION_SETTLED + late history without projection mutate. Multi-process note required if claiming beyond single-process.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R10/V_ATTACK_DRYRUN_2026-09-27.md](./R10/V_ATTACK_DRYRUN_2026-09-27.md)
- Multi-host/NFS late-history races beyond single-host SoftFileLock CanonicalStore (see R10 dry-run Attack 6 PARTIAL)
- Mapping UNKNOWN → success in any helper
- Ops GO

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R03 — staged transaction identity

### 1. Goal of V

동일 `transaction_id`에 다른 `content_identity` stage가 SoftFileLock 하에서 충돌하고, foreign identity hijack/crash recovery가 깨지지 않음을 재확인한 뒤, **multi-host/NFS는 열린 채** 둔다.

### 2. Pins

- Residual-close: `30af5c9e` (`test(ssak-ai): R03 SoftFileLock cross-process stage identity`)
- Evidence: [R03/](./R03/) · [R03/report.md](./R03/report.md)

### 3. Symbols to re-read

- `src/antigravity_k/engine/cognitive/store.py` — `TransactionManifest.content_identity`, `_stage_locked`, `TransactionConflictError`, `SoftFileLock`
- `src/antigravity_k/engine/cognitive/legacy_adapter.py` — shared SoftFileLock protocol
- Tests: `tests/cognitive/test_store.py` — `test_r03_a1`…`a4`, dual-store A3, `test_r03_a3_cross_process_different_payload_one_wins` + `_r03_a3_stage_worker`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_store.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** `stage(A,T)` committed identity  
   **When** `stage(B,T)` with different payload  
   **Then** `TransactionConflictError`; commit publishes A only.

2. **Given** identical content restage  
   **When** `stage` again  
   **Then** same manifest bytes / identity; no silent mutate.

3. **Given** baseline cross-process proof (spawn ×2, Barrier, two `CanonicalStore` SoftFileLock objects, same lock path)  
   **When** re-run `test_r03_a3_cross_process_different_payload_one_wins` (≥3×)  
   **Then** exactly one ok / one conflict / one published. SoftFileLock retained (not FileLock).

4. **Given** crash mid-stage then foreign `content_identity` hijack attempt  
   **When** recover / stage  
   **Then** refusal for foreign identity; recover publishes original only (A4).

5. **Given** (inspect only) lock file path after release  
   **When** SoftFileLock deletes lock file on unlock  
   **Then** path identity still shared; document that absence of lock file after unlock is expected — not a PASS for NFS.

6. **Given** two hosts or NFS-mounted shared root (if environment available)  
   **When** concurrent stage  
   **Then** record outcome; **do not** mark V PASS for multi-host from single-host proof. If not available, leave **OPEN** explicitly.

### 6. Pass bar for reviewer (later)

One-host SoftFileLock cross-process reconfirm + crash/hijack probe + written multi-host/NFS residual still open (or separate multi-host evidence). Compatibility note with R04/R21 crash-manifest if touched.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R03/V_ATTACK_DRYRUN_2026-09-27.md](./R03/V_ATTACK_DRYRUN_2026-09-27.md)
- Multi-host / multi-volume / NFS lock semantics
- Switching to `FileLock` without Vault/legacy protocol review
- R21 `--apply`

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## R04 — WAL / snapshot lineage

### 1. Goal of V

`snapshot()`의 단일 BEGIN `content_digest`가 multi-table tear 없이 logical content에 결박되고, `file_bundle_digest`는 물리 증거이며, conflict ⇒ `passed=False`임을 재공격한다 (multi-host/NFS·R21 apply는 열어둠).

### 2. Pins

- Residual-close: `52af3bfa` (`test(ssak-ai): R04 mid-digest cross-process snapshot isolation`)
- Evidence: [R04/](./R04/) · [R04/report.md](./R04/report.md)

### 3. Symbols to re-read

- `src/antigravity_k/engine/cognitive/migration.py` — `SourceSnapshot` (`content_digest`, `file_bundle_digest`); `snapshot()` BEGIN; `_content_digest_on`; test seam `_test_after_table`; `source_unchanged`; `_sha256_sqlite_bundle`
- `src/antigravity_k/engine/cognitive/legacy_adapter.py` — staged resume / R03-compatible repair
- Tests: `tests/cognitive/test_migration.py` — `test_r04_a1`…`a4`, mid-digest thread + `test_r04_a2_cross_process_writer_during_snapshot`; `test_legacy_adapter.py`

### 4. Baseline command

```bash
.venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
```

### 5. Attack scenarios

1. **Given** WAL payload change with unchanged row counts  
   **When** `snapshot()` before/after  
   **Then** `content_digest` changes (or file_bundle evidence moves); `source_unchanged` must not be true on count parity alone.

2. **Given** mid-digest `_test_after_table` Barrier + cross-process WAL writer updating event marker + objective title same epoch  
   **When** reader snapshot in BEGIN  
   **Then** recorded markers both pre-writer epoch (untorn); `snap.digest == snap.content_digest`; live post-snap shows writer epoch.

3. **Given** `file_bundle_digest` vs `content_digest`  
   **When** inspect `snapshot()` code  
   **Then** logical fields inside BEGIN; file_bundle intentionally outside (physical). Do not treat file_bundle equality as semantic PASS.

4. **Given** mapping conflict on remigration  
   **When** report produced  
   **Then** `passed=False` + conflict errors (not silent skip).

5. **Given** identical snapshot re-run  
   **When** A4 idempotent path  
   **Then** mapping_digest stable; no false drift.

6. **Given** shared DB on NFS / second host (if any)  
   **When** concurrent snapshot/writer  
   **Then** record; **no multi-host PASS** from single-host SQLite proof. **Never** `R21 --apply` without Human.

### 6. Pass bar for reviewer (later)

Reconfirmed content vs counts, mid-digest untorn evidence, conflict⇒non-PASS, and explicit multi-host/R21-apply residuals still open. Count-parity-only PASS is forbidden.

### 7. Must remain open / out of scope

- Implementer/secondary dry-run evidence (not V): [R04/V_ATTACK_DRYRUN_2026-09-27.md](./R04/V_ATTACK_DRYRUN_2026-09-27.md)
- Multi-host / NFS shared-DB snapshot isolation
- Live user DB mutation / `R21 --apply` without Human
- Treating `file_bundle_digest` alone as semantic unchanged

### 8. Verdict slot

`Reviewer: ___ Date: ___ Result: OPEN|PASS|FAIL Notes: ___`

---

## After independent V (handoff only)

1. Filled Verdict slots only for cards actually attacked.  
2. Update checklist/status with dated reviewer initials — still no ops GO unless Human says so.  
3. R03→R04 order before any migration apply discussion.  
4. R08/R15 production wiring notes feed Human ops judgment for CR-14 (**currently NO-GO**).
