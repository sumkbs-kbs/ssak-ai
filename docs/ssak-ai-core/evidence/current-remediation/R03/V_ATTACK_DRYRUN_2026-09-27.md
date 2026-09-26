# R03 Independent V — attack dry-run (NOT Independent R03-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R03-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R03-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:59 KST  
Executor tip (docs commit parent): `842ecdae961e77a830bb1fb260e314c40a6a54c4` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `30af5c9e` (`test(ssak-ai): R03 SoftFileLock cross-process stage identity`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R03  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baseline (ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_store.py -q -p no:cacheprovider
# → 26 passed in 2.31s  exit 0
# evidence: pytest_baseline_r03_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_store.py::test_r03_a1_second_stage_with_different_content_conflicts \
  tests/cognitive/test_store.py::test_r03_a2_identical_restage_is_idempotent \
  tests/cognitive/test_store.py::test_r03_a3_concurrent_different_payload_one_wins \
  tests/cognitive/test_store.py::test_r03_a3_cross_process_different_payload_one_wins \
  tests/cognitive/test_store.py::test_r03_a4_crash_recover_preserves_original_digest \
  -v -p no:cacheprovider
# → 5 passed in 0.71s  exit 0
# evidence: pytest_r03_attack_nodes_2026-09-27.txt
# cross-process A3 flake 3×: 1 passed each (exit 0)
```

Inspection transcript: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | `stage(B,T)` different payload after `stage(A,T)` → conflict | **RUN** | `test_r03_a1` green; `TransactionConflictError` when `content_identity` differs; commit publishes A only. |
| 2 | Identical content restage idempotent | **RUN** | `test_r03_a2` green; same manifest bytes / identity. |
| 3 | Cross-process SoftFileLock (spawn×2, Barrier) | **RUN** | `test_r03_a3_cross_process_different_payload_one_wins` green (+ dual-store in-process A3); flake 3× green. SoftFileLock retained (shared with Vault/legacy); not FileLock. |
| 4 | Crash mid-stage + foreign identity hijack | **RUN** | `test_r03_a4_crash_recover_preserves_original_digest` green; foreign identity refused; recover publishes original. |
| 5 | SoftFileLock lock-file absence after unlock | **RUN** (inspect) | Held → lock file exists; after unlock → absent. Expected SoftFileLock behavior — **not** NFS PASS. |
| 6 | Multi-host / NFS concurrent stage | **NOT_RUN** | No second host / NFS shared root in this environment. Single-host SoftFileLock ≠ multi-host PASS. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R03-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Multi-host / multi-volume / NFS** lock semantics (ATTACK_NOTES §7).
3. Switching to `FileLock` without Vault/legacy protocol review.
4. **R21 `--apply`** — still Human-only.
5. **Ops / CR-14 / production enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R03-V PASS**
- **No multi-host / NFS PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer
- One-host SoftFileLock cross-process ≠ multi-host proof

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R03-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
