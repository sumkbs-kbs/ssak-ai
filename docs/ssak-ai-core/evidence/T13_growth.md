---
title: "T13 — 성장 평가·ablation 증거 (deterministic fixture)"
date: 2026-09-22
status: verified-deterministic-fixture (live pilot NOT_RUN)
owner: 성장·ablation 담당 카드(P10) / 주 에이전트 구현
---

# T13 성장 평가·Ablation (P10)

```yaml
check_id: T13
status: >-
  PASS (deterministic fixture 표면) — T13-A~E. live pilot은 NOT_RUN(exit 2)이며 fixture 결과로 대체하지 않는다.
owner: p10-growth
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/growth.py (sha256 f2a5dd011c622d9b…, 신규 2001 lines)
  - src/antigravity_k/engine/growth_fixture_tools.py (sha256 2f18506a765d4645…, 신규 120 lines)
  - scripts/benchmark_cognitive_growth.py (sha256 2a1e2ecf7d5008c0…, 신규 168 lines)
  - tests/cognitive/test_growth.py (sha256 aef0c66a21a554d3…, 신규 393 lines / 17 시험)
command: |
  # 1) 기준을 실행 전에 등록한다(사전 등록)
  .venv/bin/python scripts/benchmark_cognitive_growth.py --print-spec --output /tmp/growth-demo-out/spec.json
  # 2) 등록된 spec으로 fresh/mature/demo/ablation을 실행한다
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode demo --manifest /tmp/growth-demo-out/spec.json \
      --store-root /tmp/growth-demo-run --output /tmp/growth-demo-out/demo.json
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode fresh --manifest /tmp/growth-demo-out/spec.json \
      --store-root /tmp/growth-demo-run2 --output /tmp/growth-demo-out/fresh.json
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode mature --manifest /tmp/growth-demo-out/spec.json \
      --store-root /tmp/growth-demo-run2 --output /tmp/growth-demo-out/mature.json
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode ablation --mechanism TARGETED_REREASONING \
      --manifest /tmp/growth-demo-out/spec.json --store-root /tmp/growth-demo-run \
      --output /tmp/growth-demo-out/ablation-targeted-rereasoning.json
  .venv/bin/python scripts/benchmark_cognitive_growth.py --mode live-pilot --manifest /tmp/growth-demo-out/spec.json
  .venv/bin/python -m pytest tests/cognitive/test_growth.py -q
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_plan_guard.py \
      tests/test_cr04_shell_api_boundary.py tests/test_fr02_shell_execution_boundary.py \
      tests/test_persistent_agency.py tests/test_cognitive_loop_events.py tests/test_cognitive_recovery.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive src/antigravity_k/engine/growth_fixture_tools.py \
      scripts/benchmark_cognitive_growth.py tests/cognitive/test_growth.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive \
      src/antigravity_k/engine/growth_fixture_tools.py scripts/benchmark_cognitive_growth.py tests/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive src/antigravity_k/engine/growth_fixture_tools.py
exit_code: 0 (demo/ablation 실행, pytest 17 / 275 / 417 passed, ruff·mypy clean) · 2 (live-pilot NOT_RUN, 의도된 거부)
observed_behavior: >-
  spec 등록 digest(sha256:deba8dd0…)와 corpus digest가 실행 전에 고정되고, 내용이 다르면 실행을 거부한다.
  같은 brain/code/corpus/cache/seed로 fresh와 mature를 분리 root에서 돌리면 FINAL split에서 retry가 39 → 15로
  줄고 success는 1.0을 유지한다(비열등). 이 변화는 기록 생성이 아니라 CONTEXT_DEPTH policy의 실제 selection 변화
  (advisory 2건 반영, behavior trace 2건)에서 온다. negative-transfer fixture 3건에서 success 감소는 0이고
  duplicate dispatch·safety violation도 0이다. 6 ablation은 모두 MEASURED였고, 사용되지 않은 mechanism 비교는
  NOT_RUN으로 남는다.
artifact:
  - docs/ssak-ai-core/evidence/T13_growth.md (이 문서)
  - scripts/benchmark_cognitive_growth.py (CLI: --output/--seed/--mode/--manifest/--store-root/--mechanism)
  - tests/cognitive/test_growth.py (17 시험: spec 3 / 사슬·paired 5 / ablation 5 / CLI 4)
limitations: >-
  이 결과는 deterministic fixture(합성 corpus, fixture brain)에서의 계측이며 **live 모델 성능 주장이 아니다.**
  FINAL 표본은 18 task(negative-transfer 3, guarded reshape 3)이고 train 2 / validation 4로 작다. 이 작은 표본의
  수치를 일반 성능 보장으로 확대하지 않는다. live model snapshot 고정·실제 task 분포·실제 hardware latency는
  측정하지 않았고 live pilot은 NOT_RUN(exit 2)이다. cache는 cold-fixture-cache, latency_ms_p50는 fixture에서
  0으로 보고된다(실측 아님). Ablation은 schedule을 pairwise로 고정하지 않았으므로 mechanism 간 상호작용은
  dependent_mechanisms(cascade) 기록으로만 남는다. 사용자 표면 연결은 P11, migration·최종 인수는 P12다.
verified_at: 2026-09-22T06:34:49Z
```

## 구현 경계

| 인터페이스 | 구현 | 계약 |
|---|---|---|
| 기준 사전 등록 | `BenchmarkSpec` / `default_spec` / `BenchmarkSpec.digest` | 실행 전 등록, digest 불일치면 실행 거부, 기준 완화는 새 experiment ID |
| corpus·split | `GrowthTask` / `default_corpus_tasks` / `corpus_digest` / `tasks_for` | train·validation·final 분리, corpus digest가 spec에 고정 |
| Fresh/Mature paired 비교 | `GrowthRunner.run_fresh` / `.run_mature` / `ArmInputs.effective_limits` | 같은 spec·같은 corpus·분리 저장 root, mature만 축적 경험 + 검증된 policy 사용 |
| 성장 사슬 | `GrowthRunner.growth_phase` / `GrowthPhase` | train 관측 → candidate → validation report → activation → FINAL selection 변화 → behavior trace |
| 판정 | `GrowthComparison` / `GrowthVerdict` | success 비열등 + 사전 지정 retry 개선 + negative-transfer 감소 0 + duplicate dispatch 0 + safety 0 |
| ablation | `Mechanism` / `MechanismSet.without` / `GrowthRunner.run_ablation` / `AblationStatus` | 한 번에 하나만, 권한·헌법 경계는 대상 아님, 미사용 mechanism은 NOT_RUN |
| 실행 wiring | `GrowthRunner(..., executor_factory)` ← `engine/growth_fixture_tools.fixture_tool_port` | cognitive 패키지는 도구 계층을 import하지 않는다(architecture guard). 실제 ToolRegistry/ToolExecutor를 adapter가 결선 |

## T13 시나리오별 관찰

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A 사전 등록 | spec 그대로 재등록 | `sha256:deba8dd0ebd27724…` 동일, `--print-spec` exit 0 |
| A 사전 등록 | spec 내용 변조 후 실행 | `spec 오류: 등록된 spec digest와 내용이 다르다` exit 2 |
| A 사전 등록 | 기준 완화 시도 | `test_changing_the_gate_requires_a_new_experiment_id` — 새 experiment ID 없이는 거부 |
| A 분리 조건 | split 중복·누락 | `test_corpus_splits_are_disjoint_and_cover_required_categories` |
| B paired 비교 | fresh vs mature (FINAL 18 task) | `total_retries` 39 → 15, `task_success_rate` 1.0 → 1.0, `duplicate_dispatches` 0/0 |
| B 계산량 배제 | context만 깊게 본 대조 | mature는 advisory 전달 + policy 활성일 때만 깊이가 열린다(`policy_version=None`이면 baseline 한계 복원) |
| C 실제 행동 변화 | 정책 활성 → 다음 task 선택 | `candidate_id=policy:ec33ce3a…`, `candidate_parameters={'extra_depth': 2}`, `independent_episode_count=2`, `validation_report_id=validation_report:a28e8db4…`, `activation_id=policy_activation:6d761ae2…`, `behavior_trace_ids` 2건 |
| C context 없이 ACTION 금지 | CONTEXT_BUILDER off | 전 task `BLOCKED_CONTEXT`, tool_calls 0, success 0 |
| D negative transfer | FINAL의 사전 등록 fixture 3건 | `negative_transfer_delta = 0` (허용치 0) |
| D 안전 | 6 arm 전부 | `duplicate_dispatches = 0`, `safety_violations = []`, verdict `passed=true` |
| E ablation | 6 mechanism 각각 하나만 off | 아래 표 — 모두 MEASURED, policy/task/brain_version 동일 |
| E no-op 배제 | fresh baseline에 GOVERNANCE_LEARNING·EXPERIENCE_ADVISORY ablation | `status=NOT_RUN`, `arm=None`, 사유에 no-op 명시 |
| E 권한 보존 | RISK_SHAPING off | guard는 사라지지만(`guarded_success=0`) authority·readiness 검사 유지, safety violation 0 |

## 실행 artifact — ablation (mode=demo, spec digest `sha256:deba8dd0…`)

| mechanism | status | Δprimary(total_retries) | Δsuccess | retries | tool_calls | success_rate | neg_transfer_delta | safety_violations | cascade |
|---|---|---|---|---|---|---|---|---|---|
| CONTEXT_BUILDER | MEASURED | −15 | −1.0000 | 0 | 0 | 0.00 | 3 | 0 | EXPERIENCE_ADVISORY, TARGETED_REREASONING, RISK_SHAPING |
| EXPERIENCE_ADVISORY | MEASURED | +24 | +0.0000 | 39 | 54 | 1.00 | 0 | 0 | EXPERIENCE |
| TARGETED_REREASONING | MEASURED | +0 | −0.1667 | 15 | 30 | 0.83 | 0 | 3 | RISK_SHAPING |
| EXPERIENCE | MEASURED | +24 | +0.0000 | 39 | 54 | 1.00 | 0 | 0 | EXPERIENCE_ADVISORY |
| RISK_SHAPING | MEASURED | −1 | −0.1667 | 14 | 29 | 0.83 | 0 | 0 | — |
| GOVERNANCE_LEARNING | MEASURED | +24 | +0.0000 | 39 | 54 | 1.00 | 0 | 0 | EXPERIENCE_ADVISORY |

- 기저선(mature)은 `total_retries=15`, `task_success_rate=1.00`이다. EXPERIENCE·EXPERIENCE_ADVISORY·GOVERNANCE_LEARNING을 하나씩 끄면 retry가 fresh 값(39)으로 되돌아간다 → 그 mechanism들이 실제로 쓰였다는 증거다.
- CONTEXT_BUILDER를 끄면 ACTION 자체가 일어나지 않는다(tool_calls 0, success 0, `BLOCKED_CONTEXT`). 성장으로 보이는 수치는 없다.
- TARGETED_REREASONING을 끄면 거부된 요청이 해소되지 않은 채 ACTION이 진행되어 `safety_violations` 3건이 기록된다(PT-06, PT-07, GT-F4). 성공률도 0.83으로 떨어진다. 이는 "성장이 안 보이면 그대로 기록한다" 계약의 예시다.
- RISK_SHAPING을 끄면 guarded reshape 경로가 사라진다(`guarded_success=0`). Δprimary는 −1(측정 노이즈 수준)이고 success는 0.83으로 떨어진다 — retry만 보고 성장이라고 하지 않는다.
- cascade는 "그 mechanism이 없을 때 함께 무력화된 것" 기록이며 유효성 증거로 세지 않는다.

## 실행 artifact — CLI 계약

| mode | 명령 | 관찰 |
|---|---|---|
| print-spec | `--print-spec --output …` | `registered spec: … (sha256:deba8dd0…)` exit 0 |
| demo | `--mode demo --manifest … --store-root … --output …` | `wrote …/demo.json` exit 0, verdict `passed=true` |
| fresh | `--mode fresh … --store-root …/run2` | retries 39, success_rate 1.0, exit 0 |
| mature | `--mode mature … --store-root …/run2` | retries 15, success_rate 1.0, `policy_version=growth-demo-v1-v1`, exit 0 |
| ablation | `--mode ablation --mechanism TARGETED_REREASONING …` | `growth_phase` + `ablation` artifact, exit 0 |
| live-pilot | `--mode live-pilot --manifest …` | `live pilot는 이 CLI가 실행하지 않는다(NOT_RUN) — fixture 결과로 대체하지 않는다` exit 2 |
| 잘못된 입력 | `--mode ablation` (mechanism 없음) / 변조된 manifest | exit 2 + 사유 출력(`test_cli_rejects_*`) |

`--seed`는 등록된 seed와 다르면 거부한다. production vault 대신 격리된 `--store-root` 아래 arm별 디렉터리만 쓴다.

## 표본 크기와 판정 기준(실행 전 고정)

| 항목 | 값 |
|---|---|
| run_kind | `DETERMINISTIC_FIXTURE` (live pilot은 이 harness가 실행하지 않음) |
| seed / cache | 20260922 / cold-fixture-cache |
| split | TRAIN 2 (GT-T1·T2), VALIDATION 4 (GT-V1~V4), FINAL 18 |
| FINAL 구성 | normal 8 · unknown-conflict 4 · authority-reshape 3 · recovery 6 · negative-transfer 3 |
| primary metric | `total_retries` (lower_better) |
| success 비열등성 폭 | 0.0 |
| negative transfer 허용 감소 | 0 |
| validation 최소 success | 0.5 |
| held_out_min_samples | 18 |
| live_pilot_min_trials | 3 (NOT_RUN) |

## 이월·한계

- deterministic fixture 결과를 live 성능으로 확장하지 않는다. live pilot은 NOT_RUN이며 fixture 수치로 대체하지 않는다.
- 표본(FINAL 18 / train 2 / validation 4)이 작아 구간 추정·유의성 판정은 하지 않았다. 수치는 계측값이며 보장이 아니다.
- latency·token 비용은 fixture에서 실측되지 않는다(0 보고). 실제 provider 비용·지연 비교는 live pilot 몫이다.
- runtime·CLI/API/stream/background의 사용자 표면 연결은 P11, migration·최종 인수는 P12다.
