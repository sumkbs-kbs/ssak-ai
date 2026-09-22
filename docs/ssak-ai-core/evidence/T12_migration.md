---
title: "T12 — legacy → canonical migration dry-run 증거"
date: 2026-09-22
status: verified-dry-run (destructive 변환은 NOT_RUN, 사람 결정)
owner: 주 에이전트 구현(P12)
---

# T12 migration·index (P12)

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
verified_at: 2026-09-22T07:17:53Z
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

## 4. 이월·잔여

1. **destructive(in-place) 변환**은 사람 결정·별도 절차가 필요하다(NOT_RUN).
2. 실사용 vault legacy DB 대상 dry-run(용량·예외 row·긴 실행 시간)은 별도 실행이 필요하다.
3. vector/RAG index rebuild는 이 카드 범위가 아니다(CanonicalStore index만 확인).
4. P12의 나머지 항목(T14 회귀·최종 Architecture Review, 헌법 24원칙별 근거, 문서 정합성)은 별도로 남아 있다.
