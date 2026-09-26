# R04 Independent V — attack dry-run (NOT Independent R04-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R04-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R04-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 05:00 KST  
Executor tip (docs commit parent): `c151853d0b522340a26935630651c126d44b6bf6` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `52af3bfa` (`test(ssak-ai): R04 mid-digest cross-process snapshot isolation`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R04  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baseline (ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
# → 39 passed in 1.28s  exit 0
# evidence: pytest_baseline_r04_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_migration.py::test_r04_a1_wal_payload_change_is_not_source_unchanged \
  tests/cognitive/test_migration.py::test_r04_a2_snapshot_lineage_stable_under_concurrent_writer \
  tests/cognitive/test_migration.py::test_r04_a2_cross_process_writer_during_snapshot \
  tests/cognitive/test_migration.py::test_r04_a3_mapping_conflict_fails_report \
  tests/cognitive/test_migration.py::test_r04_a4_identical_replay_is_idempotent \
  -v -p no:cacheprovider
# → 5 passed in 0.65s  exit 0
# evidence: pytest_r04_attack_nodes_2026-09-27.txt
# cross-process A2 flake 3×: 1 passed each (exit 0)
```

Inspection transcript: `attack_inspection_2026-09-27.txt`

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | WAL payload change + same row counts → content_digest changes | **RUN** | `test_r04_a1` green; `source_unchanged` binds `content_digest` + counts (not counts alone). |
| 2 | Mid-digest `_test_after_table` + cross-process WAL writer → untorn | **RUN** | Thread A2 + `test_r04_a2_cross_process_writer_during_snapshot` green; flake 3× green. Markers both pre-writer epoch under reader BEGIN; `snap.digest == snap.content_digest` path holds per suite. |
| 3 | `file_bundle_digest` vs `content_digest` (inspect) | **RUN** (source) | Logical `content_digest` inside BEGIN; `file_bundle_digest` intentional physical (main+WAL+SHM) outside. Do not treat file_bundle alone as semantic PASS. |
| 4 | Mapping conflict on remigration → `passed=False` | **RUN** | `test_r04_a3_mapping_conflict_fails_report` green. |
| 5 | Identical snapshot re-run idempotent | **RUN** | `test_r04_a4_identical_replay_is_idempotent` green; mapping_digest stable. |
| 6 | Multi-host/NFS concurrent snapshot; R21 `--apply` | **NOT_RUN** | No second host/NFS. **Never** ran `R21 --apply` (Human-only). Single-host SQLite ≠ multi-host PASS. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R04-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Multi-host / NFS** shared-DB snapshot isolation (ATTACK_NOTES §7).
3. Live user DB mutation / **R21 `--apply`** without Human.
4. Treating `file_bundle_digest` alone as semantic unchanged (forbidden).
5. **Ops / CR-14 / production enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R04-V PASS**
- **No multi-host / NFS PASS**
- **No R21 apply / ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer
- Single-host mid-digest isolation ≠ multi-host proof

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R04-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
