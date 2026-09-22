---
title: "T13 부속 — live pilot harness와 fixture/live 분리 계약"
date: 2026-09-22
status: harness-verified, live run NOT_RUN (실제 provider 미결선)
owner: 성장·ablation 담당 카드(P10) / 주 에이전트 구현
---

# T13 부속 — live pilot harness (P10)

```yaml
check_id: T13 (live pilot 부속)
status: >-
  PASS (harness·분리 계약) — 실제 provider 실행은 NOT_RUN. 이 환경에는 live provider가 없으므로
  수치를 만들지 않았고, stub은 자기 점검에만 썼다(성능 증거 아님).
owner: p10-growth
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/live_pilot.py (sha256 f15d923940d22fd7…, 신규 566 lines)
  - scripts/benchmark_cognitive_growth.py (sha256 9fda14440f9938a7…, live-pilot NOT_RUN artifact 추가)
  - tests/cognitive/test_live_pilot.py (sha256 49eb5ad5387b1ce5…, 신규 273 lines / 12 시험)
command: |
  .venv/bin/python -m pytest tests/cognitive/test_live_pilot.py -q
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive \
      src/antigravity_k/engine/growth_fixture_tools.py scripts/benchmark_cognitive_growth.py tests/cognitive/test_growth.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive \
      src/antigravity_k/engine/growth_fixture_tools.py scripts/benchmark_cognitive_growth.py tests/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive src/antigravity_k/engine/growth_fixture_tools.py
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode live-pilot --output /tmp/growth-live-out/live.json
exit_code: 0 (pytest 12 / 287, ruff·mypy clean) · 2 (--mode live-pilot NOT_RUN artifact, 의도된 거부)
observed_behavior: >-
  provider port가 없으면 status=NOT_RUN·arms={}·verdict=null로 남고 어떤 수치도 만들지 않는다. fixture spec으로는
  live pilot를 아예 시작할 수 없고(별도 등록 spec 필요), 최소 trial 미달은 실행 전에 거부된다. 완료 artifact는
  평균만이 아니라 중앙값·p95·분포·순서별 평균과 order_gap을 함께 남기고, claim_scope는 확증 표본이 등록되기
  전까지 pilot 전용으로 고정된다. fixture artifact와 live artifact를 합치려 하면 거부된다.
artifact:
  - docs/ssak-ai-core/evidence/T13_live_pilot.md (이 문서)
  - docs/ssak-ai-core/evidence/T13_growth.md (fixture 성장·ablation 증거)
  - tests/cognitive/test_live_pilot.py (12 시험)
limitations: >-
  이 카드는 **live 성능을 주장하지 않는다.** 실제 provider·model snapshot·hardware가 결선되지 않아 live run은
  NOT_RUN이다. 시험에 쓰인 stub port는 계측 경로 자기 점검이며 성능 증거로 쓸 수 없다(artifact의
  provider_attestation에 `stub-live-port`가 그대로 기록된다). 실제 pilot 실행에는 사람 결정(예산·provider 승인)과
  확증 표본 크기 등록이 필요하다. stream/CLI 사용자 표면 연결은 P11, 최종 인수는 P12다.
verified_at: 2026-09-22T06:38:30Z
```

## 구현 경계

| 인터페이스 | 구현 | 계약 |
|---|---|---|
| provider 정체성 | `ProviderAttestation` | provider/model/snapshot/decoding/hardware를 그대로 기록. stub도 그대로 드러난다 |
| 시도 표면 | `LiveTrialPort`(Protocol) · `LiveTrialRequest` · `LiveTrialOutcome` | harness는 port 표면만 알며 provider/UI를 import하지 않는다(architecture guard) |
| 실행 계획 | `LivePilotPlan` | arm별 최소 trial, split, 순서 정책, 확증 표본 크기(별도 등록) |
| 실행 | `LivePilotHarness.run` | fixture spec 거부 · 최소 trial 미달 거부 · port 없으면 NOT_RUN |
| 집계 | `Distribution` · `LiveArmSummary` | 평균·중앙값·p95·분포를 함께 남긴다 |
| 순서 효과 | `TrialOrder` · `_order_effect` | trial마다 fresh-first/mature-first 교대, mature 순서 민감도(order_gap) 보고 |
| 판정 | `LivePilotVerdict` | pilot 판정 + `claim_scope` + 확증 등록 여부 |
| 분리 보고 | `assert_live_artifact` · `merge_reports` | kind가 다르면 `FixtureLiveMixError` |
| CLI | `--mode live-pilot` | 수치 없이 NOT_RUN artifact, exit 2 |

## 시나리오별 관찰

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| 분리(A) | fixture spec으로 live pilot | `GrowthBenchmarkError: deterministic fixture spec으로 live pilot를 실행하지 않는다` |
| 분리(A) | fixture artifact를 live로 승격 | `FixtureLiveMixError: … live 결과가 아니다` |
| 분리(A) | fixture + live 병합 | `run_kind가 다른 report는 병합하지 않는다: ['DETERMINISTIC_FIXTURE', 'LIVE_PILOT']` |
| NOT_RUN(B) | port 미주입 | `status=NOT_RUN`, `arms={}`, `verdict=null`, 사유에 "fixture 결과로 대체하지 않는다(NOT_RUN)" |
| NOT_RUN(B) | CLI `--mode live-pilot` | artifact `{run_kind: LIVE_PILOT, status: NOT_RUN, mixed_with_fixture: false}`, exit 2 |
| 스냅샷(C) | snapshot 미고정 + 제한 사유 없음 | `status=INVALID`, `has_numbers=False` |
| 스냅샷(C) | snapshot 미고정 + 제한 사유 있음 | `status=COMPLETED`, `reproducibility_limited=true`, `claim_scope=LIVE_PILOT_REPRODUCIBILITY_LIMITED` |
| 최소 trial(D) | `trials_per_task=2` (< 3) | `paired trial이 부족하다: 2 < 최소 3` |
| 최소 trial(D) | FINAL task 없는 split | `task가 없다` |
| 완료(E) | stub port 자기 점검 | `trials=54`(FINAL 18 × 3), 분포 `{mean, median, p95, values}`, `order_effect` 9키, `claim_scope=LIVE_PILOT_PILOT_ONLY`, `confirmatory_sample_size_registered=false` |
| 완료(E) | 확증 표본 등록 시 | `confirmatory_sample_size_registered=true`, 사유에서 "확증 표본" 항목 제거 |
| 순서 효과(E) | 순서 민감 stub | `MATURE:FRESH_FIRST:mean_retries=3.0`, `MATURE:MATURE_FIRST:mean_retries=1.0`, `MATURE:order_gap=2.0` |
| 실패 판정(F) | mature retry 악화 / success 악화 / duplicate dispatch / safety violation | 각각 해당 flag가 false, `reasons`에 사유 기록 |

## stub 자기 점검 artifact (성능 증거 아님)

```json
{
  "run_kind": "LIVE_PILOT",
  "status": "COMPLETED",
  "provider_attestation": {"provider_id": "stub-live-port", "model_id": "stub-model",
                            "model_snapshot": "snapshot:stub-rev-1", "snapshot_pinned": true},
  "arms": {"FRESH": {"trials": 54, "retries": {"mean": 3.0, "median": 3.0, "p95": 3.0, "values": {"3": 54}}},
           "MATURE": {"trials": 54, "retries": {"mean": 1.0, "median": 1.0, "p95": 1.0, "values": {"1": 54}}}},
  "verdict": {"passed": true, "claim_scope": "LIVE_PILOT_PILOT_ONLY",
              "confirmatory_sample_size_registered": false,
              "reasons": ["확증 표본 크기가 등록되지 않았다 — 이 결과는 pilot이며 확증이 아니다"]},
  "mixed_with_fixture": false
}
```

이 표는 **계측 경로가 동작하는지**만 확인한다. `provider_id`가 stub이라는 사실이 artifact에 남으므로 live 성능으로
인용할 수 없다. 실제 pilot 수치는 실제 provider를 결선한 뒤 별도 artifact(`LIVE_PILOT` + 실제 attestation)로 남긴다.

## 이월·한계

- 실제 provider 실행, model snapshot 고정, hardware·비용 기록은 사람 결정(예산·provider 승인)이 필요하다.
- 확증 표본 크기는 pilot 변동성을 본 뒤가 아니라 **별도 등록**해야 한다. 등록 전까지 판정은 pilot 전용 scope로 남는다.
- fixture(T13_growth.md)와 live(T13_live_pilot.md) 결과는 어떤 경우에도 한 판정으로 합치지 않는다.
