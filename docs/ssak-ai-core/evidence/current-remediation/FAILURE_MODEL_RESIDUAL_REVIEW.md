# Failure-model residual review — priority cards

Date: 2026-09-26 21:15 KST
Tip:  ()
Scope: R01, R02, R03, R04, R08, R10, R15
Reviewer role: **implementer re-scan** (마뱀). This is **not** independent R*-V and does **not** change ops/CR-14 NO-GO.

Method: re-read pack  + repo , cross-check owned symbols with , and restate residual failure modes an independent reviewer should attack first.

## Global caveats

1. Several task cards mark  checked while the matching report says self-review only / independent open. Treat **report Limits + this note** as authoritative over the checkbox.
2. Suite green proves the coded scenarios, not every concurrent OS path (cross-process flock, Docker readonly, live multi-host).
3. Self-review PASS ≠ release / cutover GO.

## Per-card residual failure models

### R01 — protected files at execution boundary

| Failure mode | Covered by suite? | Residual risk |
|---|---|---|
| Interpreter  /  / parent rename / symlink write under seatbelt | Yes (A1) | Medium on non-macOS: Docker readonly mount **not** added; Linux path must fail-closed or deny capability |
| Quiet unsandboxed fallback that looks “safe” | A4 require_sandbox+disabled refused | Medium: any new entry that skips  still needs gate+deny |
| Wide  allow then protected deny order inverted | Claimed deny-after-allow | High for V: confirm rule order cannot be reordered by later allow |
| Approval reused on different target/args | A3 digest | Low if all write paths go through gate |
| Shell-regex-only defense | Parallel hint layer remains | High if seatbelt disabled and someone treats regex as the boundary |

**Independent V focus:** seatbelt profile rule order; non-macOS fail-closed; no path that executes shell without sandbox when .

### R02 — authority lifetime / revoke / approval binding

| Failure mode | Covered? | Residual |
|---|---|---|
| Child  outlives parent | A1 | Low in-process |
| Deep revoke misses grandchild | A2 | Low in-process |
| Governance reuses HumanApproval on digest mismatch | A3 | Medium: pure Governance vs final dispatcher both must bind digest — dispatcher path needs V eyes |
| Body self-asserts HUMAN | Task forbids | Medium: any caller that constructs authority outside  |
| Cross-process / replicated grant cache | Out of card scope | High if multi-process hosts share stale grant projections |

**Independent V focus:** ancestry evaluation on every authorize; no score-based autonomy; profile/cache callers re-read revision before allow.

### R03 — staged transaction identity

| Failure mode | Covered? | Residual |
|---|---|---|
|  overwrites  | A1 | Low in-process |
| Identical restage mutates bytes | A2 | Low |
| Two threads different payload same T | A3 | Medium→High: **cross-process flock not separately proven** (threads share FileLock) |
| Crash then hijack stage | A4 | Medium: recovery must refuse foreign content_identity |

**Independent V focus:** two OS processes racing ; crash manifest compatibility with R04/R21.

### R04 — WAL / snapshot lineage

| Failure mode | Covered? | Residual |
|---|---|---|
| Same row count + WAL payload change →  | A1 | Low if content_digest used |
| Mid-read writer tears multi-table view | A2 single-BEGIN | Medium: cross-process writer interleaving not separately stressed |
| Mapping conflict swallowed as skip | A3 | Low |
| Count parity alone as semantic PASS | Forbidden | Low if reports require content digest |
| Live user DB mutation during rehearsal | Deferred to R21 dry-run | Ops: never  without Human |

**Independent V focus:** snapshot fields bind logical content + file bundle evidence; conflict ⇒ .

### R08 — pre-dispatch current revision

| Failure mode | Covered? | Residual |
|---|---|---|
| Authority fresh but decision/state/policy stale → still dispatch | A1 claimed | **High for V**: report is thinner (evidence backfill); confirm comparison is against **authoritative current binding**, not  vs itself |
| Revoke / args change between intent persist and effect | A2 | High TOCTOU window |
| Concurrent dispatch vs reopen ordering | A3 | High: need explicit expected_revision/reservation story |
| Double execute on same binding | A4 | Medium |

**Independent V focus:** read  /  compare sites; race test nodes; no COMMIT semantic judge shortcut.

### R10 — UNKNOWN observe / reconcile / restart

| Failure mode | Covered? | Residual |
|---|---|---|
| Crash after effect → restart redispatches | A1 dispatch count 1 | Medium live multi-process |
| Duplicate observation creates new receipt IDs | A2 | Low |
| Stale revision / foreign project accepted | A3 | Low |
| Timeout clears claim and auto-retries | A4 | Low if pending_reason holds |
| UNKNOWN promoted to success | Forbidden | **Critical** if any helper maps unknown→ok |
| Late older observation downgrades projection | Only CAS reject | Medium: non-downgrading history rows **not** stored yet |

**Independent V focus:** never delete claim on timeout; observe never redispatches; external non-idempotent unknown never auto-retry.

### R15 — trusted ACTIVE composition / single owner

| Failure mode | Covered? | Residual |
|---|---|---|
| HTTP body injects service/authority/project root | A2 | High for V on composition root |
| Legacy + core both execute same action | A3 effect==1 | High if new entry points bypass owner table |
| Default ACTIVE in production boot | feature_off | **Critical** if default flipped |
| Unconfigured ACTIVE returns false success | 503 preserved | Medium |
| Test fixture ACTIVE confused with product boot | Documented | High for release reviewers |
| CLI/stream/background entry matrix drift | Task requires table | Medium: verify claimed supported paths still match code |

**Independent V focus:** OFF/SHADOW defaults; single task owner; every claimed entry has an integration test; no global ACTIVE default change.

## Priority order for independent human V

1. **R15** composition + default OFF (blast radius)
2. **R01** seatbelt/order + non-macOS fail-closed
3. **R08** live binding vs intent self-compare + race
4. **R02** digest-bound approval on all authorize paths
5. **R10** UNKNOWN never success / no timeout unlock
6. **R03** then **R04** (identity then lineage), before any R21

## Explicit non-claims

- No R*-V PASS recorded by this scan.
- No CR-14 / cutover GO.
- No code change in this scan; documentation only.

## Source paths

- Pack tasks:
- Repo reports:
