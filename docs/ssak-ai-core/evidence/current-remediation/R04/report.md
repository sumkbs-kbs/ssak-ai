# R04 report — SQLite WAL을 포함한 일관된 migration 증거

## Status
PASS (self-review limitation)

## Files / symbols
- `migration.py`: `_sha256_sqlite_bundle`, single-BEGIN `snapshot()` with `content_digest`/`file_bundle_digest`; `_replay` propagates `LegacyMappingConflict`; `source_unchanged` binds content+counts
- `legacy_adapter.py`: `_publish_with_stable_transaction` resumes staged txn (R03-compatible crash repair)
- tests: `test_r04_a1`…`a4` in `test_migration.py`

## Before / after
- Before: main DB file hash만 비교 → WAL payload 변경+동일 row count에서 source_unchanged=true 가능
- After: logical content digest(단일 read txn)로 unchanged 판정; WAL 번들은 증거 필드; mapping conflict는 report non-PASS

## Acceptance
- R04-A1: payload WAL/update → content_digest 변경 관측
- R04-A2: snapshot 필드 일관성
- R04-A3: remigration after mutate → passed=False + conflict errors
- R04-A4: 동일 snapshot 재실행 idempotent + mapping_digest 유지

## Commands
`pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q` → 36 passed (with store suite earlier 61 total including store)

## Limits
- Cross-process writer interleaving during multi-table read not separately stressed beyond single-BEGIN snapshot.
- PASS ≠ release GO.
