# 증거 게이트 — tier fast

**verdict: PASS** · stage 9개 (PASS 9 · FAIL 0 · 못 돌림 0 · tier 밖 2)

| stage | 결과 | exit | 초 | 수치 | 무엇을 보는가 |
|---|---|---:|---:|---:|---|
| `review` | pass | 0 | 17.9 | 37개 | 24원칙·§63·§52 매핑과 증거의 정합 |
| `canary` | pass | 0 | 7.8 | 4개 | 탐지력 하한이 실제로 무는가 |
| `floor_ledger` | pass | 0 | 4.2 | 31개 | 하한을 한 자리에서 — 무엇이 있고, 무엇을 보고, 언제 누가 승인했는가 |
| `digest_drift` | pass | 0 | 0.1 | 9개 | 증거가 못 박은 digest 의 현재 일치 |
| `audit_state_claims` | pass | 0 | 1.6 | 8개 | 산문의 현재-상태 주장 재판정 |
| `audit_enum_identity` | pass | 0 | 0.1 | 2개 | enum identity 비교 감사 |
| `audit_test_namespace_purge` | pass | 0 | 0.5 | 2개 | import 시점 purge 감사 |
| `measure_cognitive_surface` | pass | 0 | 3.8 | 3개 | legacy→core 도달 표 측정 |
| `red_rehearsal` | pass | 0 | 0.2 | 7개 | 위반 0건인 감사가 실제로 빨간을 낼 수 있는가 |
| `release_artifacts` | outside_tier | - | - | - | 배포 산출물(wheel/sdist)을 만들어 저장소 밖에서 써 보고 빠진 배포판도 만들어 본다 |
| `regression_ledger` | outside_tier | - | - | - | 전량 회귀 원장(scope 별 seed 두 회차) |

## 이 실행이 보지 않은 층 (통과가 아니다)

- `release_artifacts` — tier fast 밖이다 — 이 실행은 이 층을 보지 않았다
- `regression_ledger` — tier fast 밖이다 — 이 실행은 이 층을 보지 않았다

[추이] 기준 docs/ssak-ai-core/evidence/evidence_gate_baseline.json · 승인 2026-09-25
  · digest_drift · counts.match 19 → 10 ▼
  · regression_ledger · 이번 실행이 수치를 내지 않았다(기준에는 있었다)
  · release_artifacts · 이번 실행이 수치를 내지 않았다(기준에는 있었다)
  · audit_enum_identity · scanned_files 21 → 37 ▲
  · audit_test_namespace_purge · coverage.scanned 543 → 574 ▲
  · digest_drift · counts.reverified 31 → 40 ▲
  · floor_ledger · counts.record_moved 2 → 4 ▲
  · review · measured.cognitive_tests 778 → 1061 ▲
  · review · measured.digest_reverified 31 → 40 ▲
  − ↓1 · ↑6 · 그대로 96 · 기준에 없던 수 0 · 사라진 수 2 · 기준 없는 층 0  *(이동 자체는 판정이 아니다 — 하한을 깨는 감소는 그 층의 자체 게이트가 실패시킨다)*
