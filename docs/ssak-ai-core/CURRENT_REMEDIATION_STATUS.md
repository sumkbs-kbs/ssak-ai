# Current remediation status (R-series)

기준: 2026-09-27 05:45 KST · tip `5c8fcf55` — R02 grant-cache PARTIAL + R01 live Docker 3b RUN + prior R08/R10 multiproc PARTIAL; implementer secondary queue empty; Independent V still OPEN; residual-close pins unchanged · branch `codex/m1-task-events` (ahead; no push).

이 표가 **현재 작업의 유일한 진입점**이다. 아래 HISTORICAL 행의 과거 PASS는 보존하되 CURRENT_PASS로 자동 승계하지 않는다.
Source digest가 바뀌면 해당 행은 재검증 전까지 HISTORICAL이다 ([R00 evidence](evidence/current-remediation/R00/)).

감사·실행 카드 원본: `Documents/Codex/.../SSAK_AI_REVIEW_2026-09-26/`.

## Pass binding (R00-A1)

이전 실행 결과가 CURRENT_PASS가 되려면 그 evidence의 `source-manifest`에 적힌 모든 source/test/spec digest가 현재와 같아야 한다. 한 파일이라도 바뀌면 HISTORICAL이며 재실행 증거가 필요하다.

## Surface 구분

| ID | surface | status | note |
|---|---|---|---|
| P10 fixture growth | deterministic fixture | HISTORICAL_MODULE_PASS | T13; not live |
| P10 live growth | live provider | OPEN | NOT_RUN |
| P11 isolated ACTIVE | isolated HTTP + fixture Brain | HISTORICAL_ISOLATED_HTTP | audit effect1/restart0 |
| P11 production ACTIVE | production boot | OPEN | default SHADOW (F14) |
| Migration 56,961 dry-run | read-only rehearsal | HISTORICAL | 4/8 pins mismatch vs older report → R21 |
| R00 | docs + manifests | PASS (self-review) |
| R01 | sandbox deny + gate | PASS (self-review) | [report](evidence/current-remediation/R00/report.md) |
| R02–R23 | per card | OPEN | see review ACCEPTANCE_CHECKLIST |

## Card queue (from IMPLEMENTATION_ROADMAP)

1. R00 ✅
2. Parallel-capable after R00 (no file clash): R01, R02, R03, R05, R17, R20, R23
3. Then R04 (after R03), R06 (after R05), …
4. R22 last

## Progress log

| when | card | result |
|---|---|---|
| 2026-09-26 19:55 KST | R00 | PASS (A1–A3, E; V self-review limitation) |

| 2026-09-26 19:59 KST | R01 | PASS (A1–A4, E; V self-review) |

## R02 — PASS (self-review limitation) — 2026-09-26 20:01 KST
- Fix: `authority.delegate` expiry inherit; `revoke` transitive closure; `_ancestor_failure` on evaluate; `reuse_approval`/`GovernanceGate` action digest bind.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R02/`
- Tests: `tests/cognitive/test_r02_authority_lifecycle.py` + governance suite (36 passed)
- Next: R03 staged transaction identity

## R03 — PASS (self-review limitation) — 2026-09-26 20:02 KST; residual SoftFileLock cross-process 2026-09-27 03:47 KST
- Fix: `_stage_locked` content identity; `TransactionConflictError`; idempotent same-digest restage
- Residual: dual SoftFileLock in-process A3 + spawn cross-process A3; SoftFileLock retained (not FileLock)
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R03/`
- Tests: `tests/cognitive/test_store.py` **26 passed** (r03 nodes 3× flake green)
- Next: R04 (lineage residual honesty). Ops/CR-14 still **NO-GO**

## R04 — PASS (self-review limitation) — 2026-09-26 20:05 KST; residual mid-digest cross-process 2026-09-27 03:52 KST
- migration snapshot content/WAL fields; legacy staged resume
- Residual: `_test_after_table` seam; A2 in-process + spawn cross-process mid-digest writer; single-host snapshot isolation proven
- evidence: docs/ssak-ai-core/evidence/current-remediation/R04/
- Tests: migration+legacy_adapter **39 passed**; r04 nodes 3× flake green
- Next: independent V / remaining FM residuals; Ops/CR-14 still **NO-GO**

## R05 — PASS (self-review limitation) — 2026-09-26 20:07 KST
- context.py required goal / incomplete contracts
- evidence: docs/ssak-ai-core/evidence/current-remediation/R05/

## R06 — PASS (self-review limitation) — 2026-09-26 20:09 KST
- context relevance / supersedes / serialized metadata budget
- evidence: docs/ssak-ai-core/evidence/current-remediation/R06/

## R07 — PASS (self-review limitation) — 2026-09-26 20:11 KST
- runtime feedback/rethink loop
- evidence: docs/ssak-ai-core/evidence/current-remediation/R07/


## R09 — PASS (self-review limitation) — 2026-09-26 20:15 KST
- journal pending/receipt projection; durable receipt IDs; reconcile append+supersedes; persist-fail effect0
- evidence: docs/ssak-ai-core/evidence/current-remediation/R09/
- next: R10

## R10 — PASS (self-review limitation) — 2026-09-26 20:30 KST
- pending/observe recovery without redispatch; CAS + idempotent observation digest
- evidence: docs/ssak-ai-core/evidence/current-remediation/R10/
- next: R12 (via R11)

## R11 — PASS (self-review limitation) — 2026-09-26 ~21:30 KST

- STOPPED_NO_DELTA operational trail; EXPERIENCE forms core; shared surface ledger; ingest/restart
- evidence: docs/ssak-ai-core/evidence/current-remediation/R11/
- limitation: self-review only; not CR-14 / release GO
- next: R12

## R12 — PASS (self-review limitation) — 2026-09-26

- decision quality separated from outcome; readiness ≠ assessment
- evidence: docs/ssak-ai-core/evidence/current-remediation/R12/
- next: R13

## R13 — PASS (self-review limitation) — 2026-09-26

- real ContextBuilder observe for BehaviorChangeTrace; pin freeze; negative_transfer baseline; failed register refused
- evidence: docs/ssak-ai-core/evidence/current-remediation/R13/
- limitation: self-review only; not CR-14 / release GO
- next: R14 (done)

## R14 — PASS (self-review limitation) — 2026-09-26

- render_context_for_brain + StructuredSurfaceBrainPort; INCOMPLETE/overflow call0; deps wired
- evidence: docs/ssak-ai-core/evidence/current-remediation/R14/
- limitation: self-review only; not CR-14 / release GO
- next: R16 (R15 already PASS) or remaining OPEN cards per roadmap

## R16 — PASS (self-review limitation) — 2026-09-26

- DurableSurfaceHistoryStore; status/CLI project durable episode+dispatch; actual_active ≠ reaches_core
- evidence: docs/ssak-ai-core/evidence/current-remediation/R16/
- limitation: self-review only; not CR-14 / release GO
- next: R20/R21/R23 (R19 PASS)

## R17 — PASS (self-review limitation) — 2026-09-26

- PilotPreRegistration + validate_live_pilot_inputs; RawTrialLedger; NOT_COMPLETE on timeout; both-arm safety; aggregate_from_ledger
- evidence: docs/ssak-ai-core/evidence/current-remediation/R17/
- limitation: self-review only; not CR-14 / release GO
- next: R18

## R18 — PASS (self-review limitation) — 2026-09-26

- LiveTrialAdapter: model choice → ToolExecutor/store; policy gate; workspace jail; timeout ledger
- evidence: docs/ssak-ai-core/evidence/current-remediation/R18/
- limitation: self-review only; scripted model ≠ live LLM smoke; not CR-14 / release GO
- next: R19

## R19 — PASS (self-review limitation) — 2026-09-26

- freeze_registered_manifest + run_registered_live_experiment; CLI registered-live; ollama probed but 108-run not claimed
- evidence: docs/ssak-ai-core/evidence/current-remediation/R19/
- limitation: scripted contract ≠ live LLM efficacy; not CR-14 / release GO
- next: R20 / R21 / R23 (OPEN)

## 2026-09-26 — R23 PASS (self-review)

- mypy: wiki_graph / obsidian_links / wiki → Success (was 5 errors)
- CLI invalid manifest → clean exit 2, no traceback
- evidence: `evidence/current-remediation/R23/`
- next: R20 / R21 (OPEN); R22 last

## 2026-09-26 — R21 PASS (self-review)

- Current-bytes dry-run on registered agency.db with current migration code.
- evidence: `evidence/current-remediation/R21/`
- next: R20 then R22 (R23 already PASS)

## 2026-09-26 — R20 PASS (self-review)

- evidence: `evidence/current-remediation/R20/`
- next: R22 (all prior remediation cards PASS self-review)

## 2026-09-26 — R22 PASS (self-review; ops NO-GO)

- Inventory: all R00–R23 have evidence reports (R08/R15 backfilled).
- Architecture review: markers updated (cognitive_tests=901); digest_report still FAIL (drift=5, stale=25).
- Live growth: unproven. Cutover: **NO-GO**.
- HEAD: `2862584ea8f79641fefd9a78de9c145851ea515b`


## 2026-09-26 — mypy unblock for local commit

pre-commit mypy cleared (542 files Success). Remediation commit attempted after this note. Ops/cutover still **NO-GO**.

## 2026-09-26 — local commit landed

- Commit: `d3aee3d8` (`d3aee3d8ccc4c3d167841f9ce8497a08d8834487`)
- Message: chore(ssak-ai): R00–R23 remediation + mypy/ruff unblock (ops NO-GO)
- Branch: `codex/m1-task-events` (ahead of origin; **not pushed**)
- pre-commit: ruff + mypy Passed
- Ops/cutover / CR-14: still **NO-GO**

## 2026-09-26 — digest pin re-verification

- STALE/DRIFT cleared: match=9, reverified=41, drift=0, stale=0
- architecture_review: 111 passed
- Evidence: evidence/R22/digest_reverify_2026-09-26.md
- Ops/cutover still NO-GO

## 2026-09-26 — feature_off/release recheck + independent V checklist

- tip `80e43e76` (docs commit for R22 follow-up + checklist)
- feature_off + release_artifacts: **104 passed** (post-digest tip)
- architecture_review: **111 passed** (already green after digest re-verify)
- Added `evidence/current-remediation/INDEPENDENT_REVIEW_CHECKLIST.md` (V not claimed)
- Ops/cutover / CR-14 still **NO-GO**

## 2026-09-26 21:15 KST — failure-model residual re-scan (priority cards)

- Tip
- Wrote
- Cards: R01, R02, R03, R04, R08, R10, R15
- **Not** independent V; ops/CR-14 still **NO-GO**
- Top residuals: R15 default/composition, R01 non-macOS + seatbelt order, R08 live binding TOCTOU (R03 cross-process SoftFileLock closed 2026-09-27; multi-host still open)

## 2026-09-26 21:20 KST — failure-model residual re-scan (priority cards)

- Tip `c94fb491`
- Wrote evidence/current-remediation/FAILURE_MODEL_RESIDUAL_REVIEW.md
- Cards: R01, R02, R03, R04, R08, R10, R15
- Code residual highlight: R08 admit path still compares readiness to intent.freshness() (authority re-resolve separate)
- Not independent V; ops/CR-14 still NO-GO

## 2026-09-26 21:25 KST — R08 live freshness fix

- Implemented `freshness_resolver` + `_authoritative_freshness` (no intent self-compare for live axes when resolver wired)
- ACTIVE requires freshness_resolver
- Tests: action_safety+actions **42 passed**; active_api+surface **36 passed**
- Independent R08-V still open; ops/CR-14 still **NO-GO**

## 2026-09-26 21:35 KST — R15 composition residual close

- Added `test_r15_composition.py` (503 / body inject / boot skip ACTIVE / observe never ACTIVE / entry labels)
- Added `R15/ENTRY_MATRIX.md`
- Suite active+surface+feature_off+r15_composition: **48 passed**
- Independent R15-V still open; ops/CR-14 still **NO-GO**

## 2026-09-26 21:40 KST — R01 residual close

- Restored seatbelt `_protected_write_deny_section` (after broad allow)
- Docker `:ro` remounts for protected paths; Linux without Docker fail-closed
- Restored `protection_action_digest`; protection before overrides; injected guard preserved
- Suite **62 passed** (`test_r01_residual` + prior R01 suites)
- Independent R01-V still open; ops/CR-14 still **NO-GO**

## 2026-09-26 21:32 KST — R02 digest-bound residual close

- `reuse_approval` requires non-empty matching action digest
- `authorize_execution` requires digest; ToolGovernanceAdapter binds it
- Suite **38 passed** (r02 lifecycle + governance + residual)
- Independent R02-V still open; ops/CR-14 still **NO-GO**

## 2026-09-26 21:34 KST — R10 residual close

- Unobserved ActionObservation cannot declare succeeded
- Settled claim rejects conflicting observation (`PROJECTION_SETTLED`)
- Suite **33 passed** (action_safety + active_api)
- Independent R10-V still open; ops/CR-14 still **NO-GO**

## 2026-09-27 03:47 KST — R03 SoftFileLock cross-process residual close

- Tip before: `e170fbf4`
- Dual-store SoftFileLock A3 + spawn cross-process A3 green; SoftFileLock kept (Vault/legacy protocol)
- Suite: **26 passed** (`test_store.py`); r03 nodes ≥3× flake OK
- Independent R03-V still open; multi-host lock not proven
- Ops/cutover / CR-14 still **NO-GO**
- Next card: **R04**

## 2026-09-27 03:52 KST — R04 mid-digest cross-process residual close

- Tip before: `30af5c9e`
- `_test_after_table` seam + A2 thread/cross-process mid-digest writer (WAL); markers untorn (both epoch-0 under reader txn)
- Suite: **39 passed** (`test_migration.py` + `test_legacy_adapter.py`); r04 nodes ≥3× flake OK
- Independent R04-V still open; multi-host/NFS snapshot not proven; R21 `--apply` still Human
- Ops/cutover / CR-14 still **NO-GO**
- Next: remaining independent V / FM residuals (R08 code already fixed — do not reopen); not ops GO

## 2026-09-27 03:57 KST — R10 late-observation history residual close

- Tip before: `52af3bfa`
- Settled conflicting observe: `PROJECTION_SETTLED` + non-mutating `late_observation_history` Observation row (`observed_at` vs `received_at`)
- Projection journal fields unchanged; history id on result only
- Suite **34 passed** (action_safety + active_api)
- Residual honesty: single-process history Low/closed; multi-process live still Medium; Independent R10-V open
- Ops/CR-14 still **NO-GO**. Next: independent V prep — not ops GO. Do not reopen R08.


## 2026-09-27 03:58 KST — implementer priority queue flushed

- Tip: `ce9e5a2779ced64c3eede946d1c4346886284119` (docs follow-up; no push).
- Priority residuals R01, R02, R03, R04, R08, R10, and R15 are reflected at their evidence level; R08 implementer code residual is closed, while Independent R08-V and multi-process reservation remain open.
- R03/R04 multi-host or NFS behavior is not proven; R10 multi-process live history remains open/Medium. Independent V is not claimed.
- **Implementer priority residual queue is empty. Next: Independent V / multi-host review / Human ops for cutover and CR-14.** Ops/CR-14 remains **NO-GO**.

## 2026-09-27 04:18 KST — Independent V attack notes landed (no V)

- Review tip for V remains `78c2c8f6`; docs-only commit message `docs(ssak-ai): independent V attack notes (no V PASS)` lands this note (HEAD advances; no push).
- Added `evidence/current-remediation/INDEPENDENT_V_ATTACK_NOTES.md` (R08→R15→R01→R02→R10→R03→R04 playbook; executable Given/When/Then; blank Verdict slots).
- Checklist tip bumped to `78c2c8f6` + one-line pointer to attack notes; residual-close pins unchanged.
- **Still no R*-V PASS, ops GO, CR-14 GO, or multi-host PASS.**
- Next: independent reviewer executes attack notes; Human ops for cutover/CR-14 remains **NO-GO**.

## 2026-09-27 04:51 KST — R08 Independent V attack dry-run (NOT R08-V)

- Parent tip: `b745adf6`. Docs-only implementer/secondary dry-run; **no Independent R08-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R08/V_ATTACK_DRYRUN_2026-09-27.md`
- Baselines: action_safety+actions **46 passed**; active_api+surface **36 passed**. Attack nodes A1–A3 + ACTIVE-requires-resolver **4 passed**.
- Attacks RUN: 1 (ACTIVE without resolver), 2 (box-head drift), 3 (authority-alone refuse), 4 (args digest overlay), 6 (boot SHADOW-only / no `_matching_freshness` in src). **NOT_RUN:** 5 multi-process daemon race.
- OPEN: Independent R08-V, multi-process reservation, production ACTIVE store-backed resolver wiring.
- ATTACK_NOTES Verdict slots left blank/OPEN. Next: R15 dry-run or independent reviewer.

## 2026-09-27 04:53 KST — R15 Independent V attack dry-run (NOT R15-V)

- Parent tip: `42e109c4`. Docs-only implementer/secondary dry-run; **no Independent R15-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R15/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: active+surface+feature_off+r15_composition **48 passed**. Composition/feature_off nodes **12 passed**.
- Attacks RUN: 1–6 (default OFF, boot skip ACTIVE, 503, body forbid, ENTRY_MATRIX labels, observe never run_active). **NOT_RUN:** none for listed scenarios (live multi-host ACTIVE ownership remains OPEN out-of-scope).
- ATTACK_NOTES Verdict slots left blank/OPEN.

## 2026-09-27 04:55 KST — R01 Independent V attack dry-run (NOT R01-V)

- Parent tip: `13c65117`. Docs-only implementer/secondary dry-run; **no Independent R01-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R01/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: r01 residual+protected+protection_boundaries+protection+sandbox_isolation **62 passed**. Attack nodes **7 passed**.
- Attacks RUN: 1 (profile deny-after-allow), 2 (live sandbox-exec write deny), 3 (Docker `:ro` cmd-shape), 4 (require_sandbox refuse), 5 (non-Darwin fail-closed patched), 6 (digest bind). **NOT_RUN:** 3b live Docker daemon RO remount.
- OPEN: Independent R01-V, live Docker RO daemon proof, real non-Darwin host, multi-host sandbox policy.
- ATTACK_NOTES Verdict slots left blank/OPEN. Next: R02 dry-run or independent reviewer.

## 2026-09-27 04:57 KST — R02 Independent V attack dry-run (NOT R02-V)

- Parent tip: `1c14b135`. Docs-only implementer/secondary dry-run; **no Independent R02-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R02/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: digest_bound+authority_lifecycle+governance **38 passed**. Attack nodes **6 passed**.
- Attacks RUN: 1–6 (empty/omit digest reuse, authorize None/mismatch, adapter digest pass-through, revoke ancestry, expiry inherit, HumanApproval/score hunt). **NOT_RUN:** cross-process grant cache (OPEN §7).
- ATTACK_NOTES Verdict slots left blank/OPEN. Next: R10 dry-run or independent reviewer.

## 2026-09-27 04:59 KST — R10 Independent V attack dry-run (NOT R10-V)

- Parent tip: `551a55c1`. Docs-only implementer/secondary dry-run; **no Independent R10-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R10/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: action_safety+active_api **34 passed**. Attack nodes **9 passed**.
- Attacks RUN: 1–5 (unobserved ValueError, PROJECTION_SETTLED+late history, timeout leaves claim, observe redispatched=False, UNKNOWN no auto-redispatch). **NOT_RUN:** 6 multi-process live late conflicting observes.
- ATTACK_NOTES Verdict slots left blank/OPEN. Next: R03 dry-run or independent reviewer.

## 2026-09-27 05:00 KST — R03 Independent V attack dry-run (NOT R03-V)

- Parent tip: `842ecdae`. Docs-only implementer/secondary dry-run; **no Independent R03-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R03/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: test_store **26 passed**. Attack nodes **5 passed**; cross-process A3 flake 3× green.
- Attacks RUN: 1–5 (conflict, idempotent restage, SoftFileLock cross-process, crash/hijack, lock-file absence inspect). **NOT_RUN:** 6 multi-host/NFS.
- ATTACK_NOTES Verdict slots left blank/OPEN. Next: R04 dry-run or independent reviewer.

## 2026-09-27 05:01 KST — R04 Independent V attack dry-run (NOT R04-V)

- Parent tip: `c151853d`. Docs-only implementer/secondary dry-run; **no Independent R04-V PASS**, ops/CR-14 still **NO-GO**.
- Evidence: `docs/ssak-ai-core/evidence/current-remediation/R04/V_ATTACK_DRYRUN_2026-09-27.md`
- Baseline: migration+legacy_adapter **39 passed**. Attack nodes **5 passed**; cross-process A2 flake 3× green.
- Attacks RUN: 1–5 (WAL content_digest, mid-digest untorn thread+cross-process, file_bundle vs content inspect, conflict⇒non-PASS, idempotent replay). **NOT_RUN:** 6 multi-host/NFS and R21 `--apply`.
- ATTACK_NOTES Verdict slots left blank/OPEN.

## 2026-09-27 05:01 KST — Independent V dry-run sequence complete (still OPEN)

- Sequence **R08 → R15 → R01 → R02 → R10 → R03 → R04** dry-runs landed as **implementer / secondary evidence only**.
- **Independent V remains OPEN** for all seven cards (Verdict slots blank; no R*-V PASS).
- **No ops GO, cutover GO, or CR-14 GO.** Residual-close pins unchanged.
- Multi-host/NFS (R03/R04), multi-process live late-history (R10), and other §7 OPEN items remain for a future independent reviewer / Human ops.
- Next: independent reviewer executes ATTACK_NOTES; Human for cutover/CR-14 (**NO-GO**).

## 2026-09-27 05:37 KST — R08/R10 multiproc residual (implementer secondary; NOT Independent V)

- Commits: `d56cf1c9` (`test(ssak-ai): R08 multi-process admit race residual`), `e4add6b6` (`test(ssak-ai): R10 multi-process late-observe residual`). **No push.**
- **R08 Attack 5:** `test_r08_a5_cross_process_concurrent_admit_with_reopen` — `spawn`+Barrier+Queue; SoftFileLock JSON box stand-in + shared journal. Mid-admit reopen → claim winner `STALE_READINESS` / effect 0; peer refuse. Dry-run **PARTIAL** (not live ACTIVE/daemon CanonicalStore heads). Flake 3× green. Suite action_safety+actions **48 passed** (after R10 node also landed).
- **R10 Attack 6:** `test_r10_a6_cross_process_late_conflicting_observes` — settled claim + two OS late conflicting observes; both `PROJECTION_SETTLED` / `redispatched=False` / distinct `late_observation_history`; projection unchanged. Dry-run **PARTIAL** (single-host SoftFileLock). Flake 3× green. Suite action_safety+active_api **36 passed**.
- **No** Independent R*-V PASS, ops GO, cutover GO, CR-14 GO. ATTACK_NOTES Verdict slots remain OPEN.
- Remaining OPEN: production ACTIVE store-backed freshness_resolver; R08 daemon/store-head multiproc beyond JSON box; R10 multi-host/NFS late-history; residual-close pins unchanged (`3ab29d11` / `7e0fd643`).
- Next: Independent V by separate reviewer (not implementer queue reclaim). Boot stays SHADOW-only; no R21 `--apply`.

## 2026-09-27 05:45 KST — implementer secondary queue flush (R02/R01 leftovers; NOT Independent V)

- Commits: `6a1d4e42` (`test(ssak-ai): R02 cross-process grant cache residual`), `5c8fcf55` (`test(ssak-ai): R01 live Docker RO remount residual`). **No push.**
- **R02 Attack 6 / §7:** `test_r02_a6_cross_process_grant_cache_requires_reread` — spawn holder caches `AuthorityProfile`; revoker commits revoke on shared CanonicalStore SoftFileLock (`records/authority_profile`). Stale cache still allows; store re-read → `REVOKED`. Dry-run **PARTIAL** (single-host). Flake 3× green. Suite digest+lifecycle+cross_process+governance **39 passed**.
- **R01 Attack 3b:** `test_r01_live_docker_ro_remount_rejects_protected_write` — live Docker daemon on disposable `tmp_path` (forced Linux path); protected CONSTITUTION write → Errno 30 RO; scratch RW ok. Dry-run **NOT_RUN → RUN**. Flake 3× green. Suite R01+protection+sandbox **63 passed**.
- **Explicitly still OPEN (Human / independent reviewer only):** Independent R*-V Verdicts; multi-host/NFS (R03/R04/R10); multi-host/replicated grant cache; production ACTIVE enablement / store-backed resolver at boot (SHADOW-only); R21 `--apply`; CR-14; P10 live provider growth; real non-Darwin host fail-closed.
- **No** Independent R*-V PASS, ops GO, cutover GO, CR-14 GO. ATTACK_NOTES Verdict slots remain OPEN. Residual-close pins unchanged (`84210aec` / `12a0af54` / …).
- **Implementer secondary multiproc/docker leftovers closed or PARTIAL; implementer queue empty again.** Next: Independent V by separate reviewer; Human ops for cutover/CR-14 (**NO-GO**). Boot stays SHADOW-only; no R21 `--apply`.
