# R02 Independent V — attack dry-run (NOT Independent R02-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R02-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R02-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:57 KST  
Executor tip (docs commit parent): `1c14b1356a9f7fc0841881c2abfe2f36f7b5f959` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `12a0af54` (`fix(ssak-ai): R02 require digest on reuse and authorize`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R02  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baseline (ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_r02_digest_bound.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_governance.py -q -p no:cacheprovider
# → 38 passed in 0.64s  exit 0
# evidence: pytest_baseline_r02_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_r02_digest_bound.py::test_r02_reuse_approval_rejects_missing_digest \
  tests/cognitive/test_r02_digest_bound.py::test_r02_authorize_execution_requires_digest \
  tests/cognitive/test_r02_authority_lifecycle.py::test_r02_a1_omitted_child_expiry_inherits_parent_ceiling \
  tests/cognitive/test_r02_authority_lifecycle.py::test_r02_a2_transitive_revoke_keeps_independent_grant \
  tests/cognitive/test_r02_authority_lifecycle.py::test_r02_a3_governance_digest_mismatch_is_not_approve \
  tests/cognitive/test_r02_authority_lifecycle.py::test_r02_a4_valid_subset_and_matching_digest_succeed \
  -v -p no:cacheprovider
# → 6 passed in 0.30s  exit 0
# evidence: pytest_r02_attack_nodes_2026-09-27.txt
```

Inspection transcript: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | `reuse_approval` with omit/empty `action_digest` → DIGEST_MISMATCH | **RUN** | omit → `DIGEST_MISMATCH`; empty → `DIGEST_MISMATCH`; matching → `REUSED`. |
| 2 | `authorize_execution` with None / mismatched digest → deny | **RUN** | omit → allowed=False reason `실행 직전 action digest 결박이 없다`; mismatch → `승인된 action digest와 실행 대상이 다르다`; match → allowed=True. |
| 3 | `ToolGovernanceAdapter` passes `reauthorized.action_digest` | **RUN** (source) | Adapter body contains `action_digest=reauthorized.action_digest`. No `authorize_execution(` call sites outside `governance.py`. |
| 4 | Parent revoke → grandchild deny via ancestry | **RUN** | `test_r02_a2_transitive_revoke_keeps_independent_grant` green; `_ancestor_failure` on evaluate. |
| 5 | Child `expires=None` cannot outlive parent | **RUN** | `test_r02_a1_omitted_child_expiry_inherits_parent_ceiling` green. |
| 6 | No score-based autonomy; HumanApproval constructors; revision re-read | **RUN** (inspection) | Sole `HumanApproval(` under `src/` is `protected_targets.issue_human_approval` (requires non-empty digest + `human:` issuer). `autonomy_score` is in `AUTHORITY_WIDENING_PARAMETERS` (policy cannot widen). Cross-process grant-cache freshness **not** exercised. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R02-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Cross-process / replicated grant cache** freshness (ATTACK_NOTES §7).
3. Multi-host authority projection.
4. Profile/cache callers holding stale revision against a live multi-process authority store (beyond in-process suite).
5. **Ops / CR-14 / production enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R02-V PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R02-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
