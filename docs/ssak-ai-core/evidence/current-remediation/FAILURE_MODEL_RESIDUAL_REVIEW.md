# Failure-model residual review — priority cards

Date: 2026-09-27 03:58 KST
Tip at write: `ce9e5a27` (`ce9e5a2779ced64c3eede946d1c4346886284119`)
Scope: R01, R02, R03, R04, R08, R10, R15
Reviewer role: **implementer re-scan** (마뱀). This is **not** independent R*-V and does **not** change ops/CR-14 NO-GO.

Method: re-read pack tasks plus repo evidence reports, spot-check owned symbols with ripgrep, and restate residual failure modes an independent reviewer should attack first.

## Global caveats

1. Several task cards mark Rxx-V checked while the matching report says self-review only / independent open. Treat **report Limits + this note** as authoritative over the checkbox.
2. Suite green proves the coded scenarios, not every concurrent OS path (cross-process flock, Docker readonly, live multi-host).
3. Self-review PASS is not release or cutover GO.

## Per-card residual failure models

### R01 — protected files at execution boundary

| Failure mode | Covered by suite? | Residual risk |
|---|---|---|
| Interpreter write_bytes / os.replace / parent rename / symlink write under seatbelt | Yes (A1) | **Low in code evidence:** Docker protected paths now use `:ro` mounts and non-Darwin without Docker fails closed; real-daemon/V boundary confirmation remains open |
| Quiet unsandboxed fallback that looks safe | A4 require_sandbox+disabled refused | Medium: any new entry that skips SandboxRunner still needs gate+deny |
| Wide /var/folders allow then protected deny order inverted | deny section appended after root allow in restrict mode | High for V: confirm later allow cannot re-open protected paths |
| Approval reused on different target/args | A3 digest | Low if all write paths go through gate |
| Shell-regex-only defense | Parallel hint layer remains | High if seatbelt disabled and someone treats regex as the boundary |

**Independent V focus:** seatbelt profile rule order; non-macOS fail-closed; no path that executes shell without sandbox when require_sandbox is set.

Code note: `_protected_write_deny_section` is documented to follow allow(root); unsandboxed mode exists as explicit compatibility.

### R02 — authority lifetime / revoke / approval binding

| Failure mode | Covered? | Residual |
|---|---|---|
| Child expires=None outlives parent | A1 | Low in-process |
| Deep revoke misses grandchild | A2 | Low in-process |
| Governance reuses HumanApproval on digest mismatch | A3 | Medium: pure Governance vs final dispatcher both must bind digest |
| Body self-asserts HUMAN | Task forbids | Medium: any caller that constructs authority outside authority.py |
| Cross-process / replicated grant cache | Out of card scope | High if multi-process hosts share stale grant projections |

**Independent V focus:** ancestry evaluation on every authorize; no score-based autonomy; profile/cache callers re-read revision before allow.

### R03 — staged transaction identity

| Failure mode | Covered? | Residual |
|---|---|---|
| stage(B,T) overwrites stage(A,T) | A1 | Low in-process |
| Identical restage mutates bytes | A2 | Low |
| Two writers different payload same T | A3 dual SoftFileLock + A3 cross-process spawn | **Low on one host**: SoftFileLock multiprocess proven 2026-09-27 (two OS processes / two SoftFileLock objects). Still not multi-host / cross-FS. SoftFileLock retained (Vault/legacy protocol). |
| Crash then hijack stage | A4 | **Low on one host:** recovery refusal for foreign `content_identity` is covered; Independent V should attack crash-manifest compatibility and multi-host behavior |

**Independent V focus:** multi-host / NFS lock semantics (out of SoftFileLock single-host proof); crash manifest compatibility with R04/R21.

### R04 — WAL / snapshot lineage

| Failure mode | Covered? | Residual |
|---|---|---|
| Same row count + WAL payload change marks source_unchanged | A1 | Low if content_digest used |
| Mid-read writer tears multi-table view | A2 single-BEGIN + mid-digest hook + cross-process writer | Low on single-host WAL snapshot isolation; multi-host/NFS still open |
| Mapping conflict swallowed as skip | A3 | Low |
| Count parity alone as semantic PASS | Forbidden | Low if reports require content digest |
| Live user DB mutation during rehearsal | Deferred to R21 dry-run | Ops: never `--apply` without Human |

**Independent V focus:** snapshot fields bind logical content + file bundle evidence; conflict implies passed=False; multi-host/NFS shared DB still unproven; R21 apply Human.

### R08 — pre-dispatch current revision (code residual closed 2026-09-26; Independent V open)

| Failure mode | Covered? | Residual risk |
|---|---|---|
| Authority fresh but decision/state/policy stale still dispatches | Yes, live-resolver regression suite | **Closed in implementer code/tests 2026-09-26; Independent V must verify the production store-backed resolver** |
| Revoke / args change between intent persist and effect | Yes, resolver + args binding tests | Low code residual; Independent V must exercise the timing window |
| Concurrent dispatch vs reopen ordering | A3 race + A5 cross-process spawn (2026-09-27) | **Low/PARTIAL single-host** SoftFileLock JSON box + shared journal (`test_r08_a5…`); production ACTIVE/daemon store-head multiproc still **Medium/OPEN** for Independent V |
| Double execute on same binding | A4 | Low in code evidence; Independent V may still challenge duplicate-binding behavior |

The prior 2026-09-26 self-compare finding was addressed by `freshness_resolver` + `_authoritative_freshness`: when wired, decision/state/policy/authority revisions come from the live resolver rather than intent fields. The implementer code residual is therefore closed at the 2026-09-26 fix tip; this does **not** establish R08-V PASS.

**Independent V focus:** prove a live store/head read for decision_revision, state_revision, and policy_version immediately before effect; race tests must mutate the store, not only the intent object; inspect the multi-process reservation story. Do not reopen implementer R08 code solely from the superseded self-compare note.

### R10 — UNKNOWN observe / reconcile / restart

| Failure mode | Covered? | Residual |
|---|---|---|
| Crash after effect then restart redispatches | A1 dispatch count 1 | Medium live multi-process |
| Duplicate observation creates new receipt IDs | A2 | Low |
| Stale revision / foreign project accepted | A3 | Low |
| Timeout clears claim and auto-retries | A4 | Low if pending_reason holds |
| UNKNOWN promoted to success | Forbidden in actions module docstring | Critical if any helper maps unknown to ok |
| Late older observation downgrades projection | CAS refuse + history append + A6 cross-process spawn (2026-09-27) | **Low/closed single-process; Low/PARTIAL single-host SoftFileLock** (`test_r10_a6…`); multi-host/NFS still **Medium/OPEN** |

**Independent V focus:** never delete claim on timeout; observe never redispatches; external non-idempotent unknown never auto-retry.

### R15 — trusted ACTIVE composition / single owner

| Failure mode | Covered? | Residual |
|---|---|---|
| HTTP body injects service/authority/project root | A2 | High for V on composition root |
| Legacy + core both execute same action | A3 effect==1 | High if new entry points bypass owner table |
| Default ACTIVE in production boot | feature_off; dependencies comment says ACTIVE not attached here | Critical if default flipped |
| Unconfigured ACTIVE returns false success | 503 preserved | Medium |
| Test fixture ACTIVE confused with product boot | Documented | High for release reviewers |
| CLI/stream/background entry matrix drift | Task requires table | Medium: verify claimed supported paths still match code |

**Independent V focus:** OFF/SHADOW defaults; single task owner; every claimed entry has an integration test; no global ACTIVE default change.

## Priority order for independent human V

1. **R08** live binding vs intent self-compare (code finding above)
2. **R15** composition + default OFF (blast radius)
3. **R01** seatbelt order + non-macOS fail-closed
4. **R02** digest-bound approval on all authorize paths
5. **R10** UNKNOWN never success / no timeout unlock
6. **R03** then **R04** (identity then lineage), before any R21 `--apply`

## Explicit non-claims

- No R*-V PASS recorded by this scan.
- No CR-14 / cutover GO.
- Documentation update only in the follow-up commit; no product behavior change in this scan.

## Source paths

- Pack tasks under SSAK_AI_REVIEW_2026-09-26/tasks/
- Repo reports under docs/ssak-ai-core/evidence/current-remediation/R*/
- Spot-check: action_admission.py assert_fresh call; sandbox.py protected deny section; store.py content_identity; actions.py UNKNOWN / submit_observation; dependencies.py ACTIVE not default-wired

## Update 2026-09-26 21:25 KST — R08 code residual closed (self-review)

`freshness_resolver` + `_authoritative_freshness` address the admit self-compare finding when a resolver is wired; ACTIVE requires the resolver. The implementer residual is closed by code/tests. Independent R08-V remains open: prove the **production** resolver reads store heads (not fixture `_matching_freshness`) and review the multi-process race/reservation story.

## Update 2026-09-26 21:35 KST — R15 composition residual tests

Implementer closed documented R15 residuals with `test_r15_composition.py` + `ENTRY_MATRIX.md` (no production default change).
Remaining for independent V: human review of composition root + entry table vs live boot; still not CR-14 GO.
Next code priority for implementer: **R01** seatbelt order + non-macOS fail-closed.

## Update 2026-09-26 21:40 KST — R01 seatbelt deny re-wired

Code finding: deny helpers existed but tip seatbelt profile omitted them; also missing `protection_action_digest` and override-before-protection.
Restored deny-after-allow, Docker RO mounts, gate digest binding. Independent R01-V still open.
Next implementer priority: **R02** digest-bound approval on all authorize paths.

## Update 2026-09-26 21:32 KST — R02 digest binding required

Code finding: empty `action_digest` skipped reuse checks; `authorize_execution(None)` skipped execution binding; adapter admit omitted digest.
Now deny on missing digest. Independent R02-V still open.
Next implementer priority: **R10** UNKNOWN never success / no timeout unlock.

## Update 2026-09-26 21:34 KST — R10 settled non-downgrade + unobserved invariant

Code finding: forged unobserved success was constructible; settled claims could flip via conflicting observe.
Now invariant + PROJECTION_SETTLED refuse. History-append residual closed 2026-09-27 (see below).
Next implementer priority was R03 (closed 2026-09-27 SoftFileLock cross-process); then R04.

## Update 2026-09-27 03:57 KST — R10 late-observation history append

- Settled + differing digest: still `PROJECTION_SETTLED` / no journal mutate; additionally persists canonical Observation with `method=late_observation_history`, `source=received_at:…`, distinct `observed_at`.
- Result returns history id; claim.observation_record_id stays first settle id.
- Suite action_safety + active_api: **34 passed**.
- Residual: single-process history closed (Low); multi-process live still Medium. Independent R10-V open. Ops/CR-14 **NO-GO**.
- Next: independent V prep (not ops GO); do not reopen R08.

## Update 2026-09-27 03:47 KST — R03 SoftFileLock cross-process residual close

- Strengthened A3 to two `CanonicalStore` instances (two SoftFileLock objects, same lock path).
- Added `test_r03_a3_cross_process_different_payload_one_wins` (`spawn` + Barrier + Queue). SoftFileLock **serialized**; no FileLock switch.
- Suite `tests/cognitive/test_store.py`: **26 passed**; r03 nodes 3× flake green.
- Residual lowered to single-host SoftFileLock proven; multi-host still open.
- Ops/CR-14 still **NO-GO**. Next implementer priority was **R04** (closed 2026-09-27 mid-digest cross-process).

## Update 2026-09-27 03:52 KST — R04 mid-digest cross-process residual close

- Added `_test_after_table` seam on `_content_digest_on` (prod unused).
- Strengthened A2 in-process thread Barrier mid-digest writer (event marker + objective title same epoch).
- Added `test_r04_a2_cross_process_writer_during_snapshot` (`spawn` + Barrier + Queue, WAL writer). Recorded markers both pre-writer epoch → untorn multi-table view.
- Suite `test_migration.py` + `test_legacy_adapter.py`: **39 passed**; r04 nodes 3× flake green.
- Residual lowered: single-host SQLite snapshot isolation proven; multi-host/NFS still open; R21 `--apply` still Human.
- Ops/CR-14 still **NO-GO**. Next implementer priority: check status — remaining independent V / ops cards (R08 already code-fixed; do not reopen unless status says). Prefer next FM residual honesty card or independent V prep; not ops GO.


## Queue state — 2026-09-27 03:58 KST

**Implementer queue empty for priority cards:** R01, R02, R03, R04, R08, R10, and R15 have their documented implementer residuals closed or lowered to the evidence above. This is not an R*-V or operations approval.

Next is **Independent V**, including the explicitly open multi-host/multi-process boundaries, followed by **Human ops** review for cutover/CR-14. No production ACTIVE, migration `--apply`, ops GO, multi-host PASS, or CR-14 GO is claimed.

## Update 2026-09-27 05:37 KST — R08/R10 single-host multiproc residuals (NOT Independent V)

- R08: `test_r08_a5_cross_process_concurrent_admit_with_reopen` — SoftFileLock JSON box stand-in; Attack 5 dry-run **PARTIAL**. Production ACTIVE store-backed resolver / daemon head race still OPEN.
- R10: `test_r10_a6_cross_process_late_conflicting_observes` — SoftFileLock CanonicalStore; Attack 6 dry-run **PARTIAL**. Multi-host/NFS still OPEN.
- Suites green; flake 3× on new nodes. **No** R*-V PASS / ops / CR-14 GO. Residual-close pins unchanged. Implementer priority queue still empty for Independent V reclaim — secondary evidence only.
