# Failure-model residual review — priority cards

Date: 2026-09-26 21:20 KST
Tip at write: `c94fb491` (`c94fb491752037432eb8823c044fac73cfc84584`)
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
| Interpreter write_bytes / os.replace / parent rename / symlink write under seatbelt | Yes (A1) | Medium on non-macOS: Docker readonly mount not added; Linux path must fail-closed or deny capability |
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
| Two threads different payload same T | A3 | Medium to High: **cross-process flock not separately proven** (threads share FileLock) |
| Crash then hijack stage | A4 | Medium: recovery must refuse foreign content_identity |

**Independent V focus:** two OS processes racing `_stage_locked`; crash manifest compatibility with R04/R21.

### R04 — WAL / snapshot lineage

| Failure mode | Covered? | Residual |
|---|---|---|
| Same row count + WAL payload change marks source_unchanged | A1 | Low if content_digest used |
| Mid-read writer tears multi-table view | A2 single-BEGIN | Medium: cross-process writer interleaving not separately stressed |
| Mapping conflict swallowed as skip | A3 | Low |
| Count parity alone as semantic PASS | Forbidden | Low if reports require content digest |
| Live user DB mutation during rehearsal | Deferred to R21 dry-run | Ops: never `--apply` without Human |

**Independent V focus:** snapshot fields bind logical content + file bundle evidence; conflict implies passed=False.

### R08 — pre-dispatch current revision  (**highest code residual in this scan**)

| Failure mode | Covered? | Residual |
|---|---|---|
| Authority fresh but decision/state/policy stale still dispatches | Partially | **High** |
| Revoke / args change between intent persist and effect | Authority re-resolve + args_digest vs readiness | Medium for args/authority; High for decision/state/policy |
| Concurrent dispatch vs reopen ordering | Suite claimed A3 | High: need explicit expected_revision/reservation story |
| Double execute on same binding | A4 | Medium |

**Code finding (2026-09-26):** `action_admission.preconditions` calls

`ReadinessGate().assert_fresh(readiness, intent.freshness())`

`intent.freshness()` rebuilds a FreshnessBinding from the **same intent fields** that typically populated `readiness.freshness`. Authority is re-read via `authority_resolver` when wired, but this call site does **not** load an authoritative live decision/state/policy binding from the store. That matches the card's forbidden shortcut (intent freshness compared to itself) for those three axes unless another layer refreshes intent fields before admit.

**Independent V focus:** prove a live store/head read for decision_revision, state_revision, and policy_version immediately before effect; race tests must mutate the store, not only the intent object.

### R10 — UNKNOWN observe / reconcile / restart

| Failure mode | Covered? | Residual |
|---|---|---|
| Crash after effect then restart redispatches | A1 dispatch count 1 | Medium live multi-process |
| Duplicate observation creates new receipt IDs | A2 | Low |
| Stale revision / foreign project accepted | A3 | Low |
| Timeout clears claim and auto-retries | A4 | Low if pending_reason holds |
| UNKNOWN promoted to success | Forbidden in actions module docstring | Critical if any helper maps unknown to ok |
| Late older observation downgrades projection | Only CAS reject | Medium: non-downgrading history rows not stored yet |

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

## Update 2026-09-26 21:25 KST — R08 code fix landed (self-review)

`freshness_resolver` + `_authoritative_freshness` address the admit self-compare finding when a resolver is wired; ACTIVE requires the resolver.
Residual for independent V: prove the **production** resolver reads store heads (not fixture `_matching_freshness`), and race/reservation story under multi-process load.

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
Now invariant + PROJECTION_SETTLED refuse. History-append for late obs still open for V.
Next implementer priority: **R03** staged transaction identity (then R04).
