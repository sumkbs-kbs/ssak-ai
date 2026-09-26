---
title: "T12 — legacy → canonical migration dry-run 증거"
date: 2026-09-22
status: "historical-module-contract-verified; post-fix-registered-snapshot-full-dry-run-pass; destructive-NOT_RUN"
owner: 주 에이전트 구현(P12)
current_verification_head: 0a9498e3846a48bbf158bf870957064cdc9bbb11
current_full_snapshot_evidence: docs/ssak-ai-core/evidence/2026-09-25-review/migration-real-post-independent-review-2026-09-26.json
current_full_cognitive_evidence: docs/ssak-ai-core/evidence/2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.json
current_snapshot_digest: 7d69ed65667db079957a9277b59ebcfb232293582beb6d53f267a4f61e726836
---

# T12 migration·index (P12)

> 아래 최초 YAML 및 §1~3은 2026-09-22 synthetic/module 실행 당시 기록이다. 수정 후 등록 실데이터 snapshot의 2026-09-26 full dry-run과 전체 cognitive 회귀는 §4에서 별도 증거로 갱신한다.

```yaml
check_id: T12
status: >-
  PASS (dry-run 표면) — source read-only·별도 root·ID mapping·index rebuild·digest 검증·rollback rehearsal을
  실제 legacy SQLite(PersistentAgency schema)로 관찰했다. destructive(in-place) 변환은 실행하지 않았고
  사람 결정으로 남긴다.
owner: p12-migration
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/migration.py (sha256 f45e974f01a6e124…, 신규 489 lines)
  - scripts/migrate_legacy_to_canonical.py (sha256 23df5ed576da56a2…, 신규 155 lines)
  - tests/cognitive/test_migration.py (sha256 ea48c4080eb65f42…, 신규 263 lines / 14 시험)
command: |
  .venv/bin/python scripts/migrate_legacy_to_canonical.py --source /tmp/p12/src/agency.db \
      --target /tmp/p12/target --output /tmp/p12/report.json
  .venv/bin/python scripts/migrate_legacy_to_canonical.py --source /tmp/p12/src/agency.db \
      --target /tmp/p12/target2 --apply          # destructive 거부(exit 2)
  .venv/bin/python -m pytest tests/cognitive/test_migration.py -q
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/test_persistent_agency.py tests/test_cognitive_loop_events.py \
      tests/test_cognitive_recovery.py tests/test_tool_executor.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive \
      scripts/migrate_legacy_to_canonical.py tests/cognitive/test_migration.py
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive src/antigravity_k/engine/cognitive_surface.py \
      scripts/migrate_legacy_to_canonical.py
exit_code: 0 (dry-run·pytest 14 / 326 / 59, ruff·mypy clean) · 2 (--apply 거부, 의도)
observed_behavior: >-
  dry-run은 source를 mode=ro로만 열며 실행 전후 source sha256·counts가 같다. canonical 기록은 별도 root에만
  생기고, 같은 store 재실행은 record를 늘리지 않는다(idempotent replay True). index를 재생성하고 모든 record
  digest를 확인했다(5/5). rollback rehearsal은 전용 scratch에서만 수행돼 dry-run 출력이 보존된다.
  옮길 수 없는 legacy event type은 조용히 건너뛰지 않고 report.errors에 남고 exit 1로 알린다.
  project canonical ID는 최초 매핑 시 발급되는 random ID이므로, root를 새로 만들면 달라진다 — mapping manifest를
  함께 넘겨야 identity가 유지된다(warning으로 보고).
artifact:
  - docs/ssak-ai-core/evidence/T12_migration.md (이 문서)
  - /tmp/p12/report.json (dry-run report artifact)
  - tests/cognitive/test_migration.py (14 시험)
limitations: >-
  destructive migration(in-place 변환·삭제·덮어쓰기)은 **실행하지 않았다**(NOT_RUN, 사람 결정). 실사용 vault의
  legacy DB가 아니라 **실제 schema로 만든 synthetic DB**를 대상으로 관찰했으므로, 실제 데이터 분포·용량·
  예외 row는 별도 dry-run이 필요하다. canonical index rebuild는 CanonicalStore index 기준이며 vector/RAG
  index 재구축은 이 카드 범위가 아니다. objective 테이블은 비어 있었고(0건) task status는 queue 기준으로 기록된다.
verified_at: "2026-09-22T07:17:53Z (original synthetic/module run; post-fix real snapshot run is recorded in §4)"
```

## 1. 실행 흐름과 경계

| 단계 | 구현 | 관찰 |
|---|---|---|
| source 열기 | `LegacySQLiteSource(readonly_uri=file:…?mode=ro)` | `INSERT` 시도 시 `sqlite3.OperationalError: attempt to write a readonly database` |
| source 관찰 | `snapshot()` → sha256·size·tables·counts | 실행 전후 digest 동일 |
| target 경계 | `LegacyMigrationRunner` overlap guard | target이 source 디렉터리·그 하위면 `MigrationError` |
| destructive 차단 | `mode=apply` → `DestructiveMigrationRefused` | `--apply`는 exit 2 + `NOT_RUN` 안내 |
| mapping | `LegacyAgencyAdapter`(append-only manifest) | 재실행 시 canonical ID 재사용, 늘지 않음 |
| index | `CanonicalStore.rebuild_index()` / `verify_digests()` | `index_rebuilt=5`, `digests_verified=5` |
| rollback rehearsal | 전용 scratch에 옮긴 뒤 삭제 | `rollback_rehearsed=True`, dry-run 출력 5 records 유지 |

## 2. 관찰 결과 (dry-run, source digest `sha256:e5a1eaf3ee0b9a21…`)

```
mode: dry-run · source digest sha256:e5a1eaf3ee0b9a21…
source counts: {'events': 3, 'objectives': 0, 'tasks': 2}
imported: {'events': 3, 'objectives': 0, 'tasks': 2} · canonical records 5
mapping entries 5 · digest sha256:d443b08635c6e3bd…
index rebuilt 5 · digests verified 5 · idempotent replay True
source unchanged True · rollback rehearsed True · destructive executed False
verdict: passed=True complete=True
```

| 시나리오 | 관찰 |
|---|---|
| dry-run (synthetic legacy DB 3 events·2 tasks) | records 5, mapping 5, `passed=True` |
| 같은 root 재실행 | `mapping_carried_over=True`, 같은 mapping digest, records 5 유지 |
| 다른 root + mapping manifest 이관 | mapping digest 동일(identity 유지) |
| 다른 root + manifest 미이관 | project canonical ID 새 발급 → mapping digest 달라짐 + warning |
| `--apply` | exit 2, `destructive_executed=False` |
| target이 source 디렉터리·하위 | `MigrationError: target root가 source와 겹친다` |
| 옮길 수 없는 event type | `report.errors`에 `no_such_type` 포함, `complete=False`, exit 1 |
| legacy table이 없는 DB | counts 0, records 0, `passed=True`(빈 source도 계약은 성립) |
| task 0건 | warning `legacy task가 0건이다 …` |

## 3. ID mapping·identity 계약 (P12에서 확정)

- canonical project ID는 **최초 매핑 시 발급되는 random ID**이며, 같은 root·같은 manifest에서는 항상 같은 값을 돌려준다.
- **root를 옮길 때는 mapping manifest(`legacy/agency_map.json`)를 함께 옮겨야** identity가 유지된다. 옮기지 않으면
  같은 legacy 데이터가 다른 canonical project ID로 매핑되고, report가 그 사실을 warning으로 남긴다.
- event/objective/task mapping은 legacy key 기반이라 재실행·재이관에 대해 idempotent하다(uuid5가 아니라 manifest 값 재사용).

## 4. 독립 검토 보완 — 2026-09-26

수정 후 별도 synthetic DB 회귀에서 두 문제를 재현·수정했다.

1. rollback rehearsal이 고정 경로 `target/rollback-rehearsal`을 `exist_ok`로 재사용하고 마지막에 재귀 삭제해, 해당 디렉터리가 미리 있으면 기존 sentinel 파일도 삭제됐다. 매회 `mkdtemp`로 새 경로를 만들고 생성 회차가 소유한 그 scratch만 정리하도록 바꿨다. 기존 경로에 놓은 파일을 dry-run이 보존하는 regression을 추가했다.
2. objective/task adapter는 mapping manifest 저장 뒤 record publish가 중단되면 다음 동일 입력에서 `mapped record is not committed`를 던져 영구 복구 불능이었다. mapping의 canonical ID로 record를 재생성하고, record ID/kind 기반 결정적 transaction ID로 재시도해 staged transaction도 재사용하도록 했다. objective/task × public commit/migration batch commit crash·retry 시험을 추가했다.

검증: `tests/cognitive/test_migration.py`, `test_legacy_adapter.py`, `test_store.py`, `test_protection.py`, `test_protection_boundaries.py`, `tests/test_tool_sandbox_coverage.py` 묶음 100 passed, exit0(4.64초). Ruff PASS, changed `migration.py`·`legacy_adapter.py` basedpyright `--level error` 0 errors/warnings/notes. JUnit: [독립 검토 회귀](2026-09-25-review/pytest-migration-independent-review-2026-09-26.xml).

수정 후 전체 검증(2026-09-26): [등록 snapshot full dry-run 증거](2026-09-25-review/migration-real-post-independent-review-2026-09-26.json)는 exit0, 170.47초(170.07초 report total), errors0, passed/complete=true다. 기대 snapshot digest `7d69ed65667db079957a9277b59ebcfb232293582beb6d53f267a4f61e726836`; 56,961 observation event 전량 import·mapping·canonical record·index·digest·replay·rollback rehearsal 각각 56,961로 일치했고 source bytes/count 및 code/test/driver hash는 실행 전후 불변, destructive=false다. 원본 agency.db는 26,206,208 bytes, SHA-256 `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5`; objectives/tasks는 각각 0건이다. 같은 수정 후 source tree의 [전체 cognitive 회귀](2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.json)는 822 collected, 821 passed, 0 failed, 1 skipped, 1 warning, exit0, 733.65초다. 이 전체 회귀와 migration dry-run은 별도 검증 범위다. 과거 full run들은 해당 이전 code/test hash에 대한 역사 기록으로 유지하고 최신 증거는 위 두 artifact를 참조한다.

한계: 이 snapshot에서 objectives/tasks가 0건이므로 해당 실데이터 분포는 미관측이며, event 표본은 observation type 56,961건이다. 이 dry-run은 read-only full rehearsal일 뿐 destructive/apply migration, 운영 cutover·release 또는 rollback의 운영 승인 결과가 아니다. `KGBinaryValidator.validate() -> OK=True`도 별도 미실행 gate다.

## 5. 이월·잔여

1. **destructive(in-place) 변환**은 사람 결정·별도 절차가 필요하다(NOT_RUN).
2. 등록된 `.antigravity_k/agency.db` snapshot은 수정 후 전체 read-only dry-run을 마쳤다. 다른 실사용 vault/DB 또는 다른 데이터 분포가 적용 대상이면 별도 hash 결박 dry-run이 필요하다.
3. vector/RAG index rebuild는 이 카드 범위가 아니다(CanonicalStore index만 확인).
4. P12의 나머지 항목(T14 회귀·최종 Architecture Review, 헌법 24원칙별 근거, 문서 정합성)은 별도로 남아 있다.
