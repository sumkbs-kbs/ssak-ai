# R04 report — SQLite WAL을 포함한 일관된 migration 증거

## Status
PASS (self-review limitation; 독립 인간 검토 대기) — residual close 2026-09-27 03:52 KST

Tip before residual: `30af5c9e`

## Files / symbols
- `migration.py`: `_sha256_sqlite_bundle`; single-BEGIN `snapshot()` with `content_digest`/`file_bundle_digest`; `_content_digest_on` + **test seam** `_test_after_table(table, connection)` (prod unused); `_replay` propagates `LegacyMappingConflict`; `source_unchanged` binds content+counts
- `legacy_adapter.py`: unchanged this residual (R03-compatible crash repair already present)
- tests: `test_r04_a1`…`a4` in `test_migration.py`
  - strengthened `test_r04_a2_snapshot_lineage_stable_under_concurrent_writer` (in-process thread + Barrier; mid-digest writer updates event marker + objective title together)
  - NEW `test_r04_a2_cross_process_writer_during_snapshot` + `_r04_a2_writer_worker` (`multiprocessing.get_context("spawn")`, Barrier, Queue; WAL writer)

## Before / after
- Before (original): main DB file hash만 비교 → WAL payload 변경+동일 row count에서 source_unchanged=true 가능
- After (card): logical content digest(단일 read txn)로 unchanged 판정; WAL 번들은 증거 필드; mapping conflict는 report non-PASS
- Residual before 2026-09-27: A2는 필드 존재 + quiet 재스냅샷만 — **concurrent writer 없음**; mid-digest cross-table tear 미검증
- Residual after: events digest 직후 Barrier로 writer가 event payload marker와 objective title을 같은 새 epoch로 단일 txn COMMIT; reader txn 안 SELECT는 둘 다 옛 epoch → 단일 호스트 SQLite snapshot isolation로 multi-table view 미찢김 증명. SoftFileLock/FileLock out of scope.

## Acceptance
- R04-A1: payload WAL/update → content_digest 변경 관측
- R04-A2 (threads): mid-digest writer; recorded event marker == objective marker == epoch-0; live post-snap == epoch-1; digest==content_digest
- R04-A2 (cross-process): spawn writer mid-digest; same untorn assertion; WAL journal mode; no forced checkpoint
- R04-A3: remigration after mutate → passed=False + conflict errors
- R04-A4: 동일 snapshot 재실행 idempotent + mapping_digest 유지

## Commands
```
.venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
# 39 passed in ~1.3s, exit 0

# r04 nodes flake (3×): 5 passed each
```

## Limits
- Single-host SQLite WAL snapshot isolation for multi-table logical digest is now proven (in-process + cross-process). Still **not** multi-host / NFS / multi-volume shared DB semantics.
- `file_bundle_digest` remains outside BEGIN (intentional physical evidence); logical `content_digest`/`digest`/`counts` stay one-txn.
- PASS ≠ release GO. Ops/CR-14 remains **NO-GO**. Independent R04-V still open. R21 `--apply` still Human.
- Implementer/secondary dry-run (not V): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md)
