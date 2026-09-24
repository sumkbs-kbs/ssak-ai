---
title: "T00b — 사전 등록 benchmark 명세의 소유와 계약"
date: 2026-09-24
status: verified-registration
owner: 통합 담당(P00)
tags: [ssak-ai, benchmark, preregistration]
---

# T00b 사전 등록 명세 (P00)

이 문서는 P00의 소유 산출물로, **사전 등록(preregistration) 명세가 어디에 실재하고 무엇을 약속하는지**를
밝힌다. 값(실험 ID·metric 숫자·split 목록)은 이 문서에 박지 않는다 — 값의 소유자는
`src/antigravity_k/engine/cognitive/growth.py`의 spec 구조와 그것을 출력하는
`scripts/benchmark_cognitive_growth.py --print-spec` 산출물이며, 값을 문서에 옮기면 다음 변경마다
낡는다(이 문서화 패키지의 규칙). 실행 뒤 기준을 바꾸지 않는다는 계약은 `BenchmarkSpec` docstring이 소유한다.

## 1. 사전 등록 소유자

| 계약 | 소유 자리 | 내용 |
|---|---|---|
| metric 정의 | `growth.py default_metrics()` — 12개 `MetricSpec` | name·unit·**denominator(분모)**·window(측정 구간)·direction(`higher_better`/`lower_better`/`report_only`) |
| 실행 명세 | `growth.py BenchmarkSpec` | experiment_id·registered_at·seed·corpus_digest·**split_ids**·metrics·primary_improvement_metric·성공 비열등 margin·negative-transfer 상한·held-out 최소 표본·live pilot 최소 trial·cache_mode·policy target/params·validation 최소 성공 |
| split 분리 | `growth.py SplitRole`(TRAIN/VALIDATION/FINAL)·`corpus_tasks()` | 12 fixture를 **고정 목록**으로 나누고 corpus 전체를 `corpus_digest`로 봉인한다 |
| 등록 산출물 | `benchmark_cognitive_growth.py --print-spec --output spec.json` | 등록용 spec JSON — 매 실행 같은 구조로 재생성되며, 실행 시 `--manifest`로 이 파일을 제출한다 |
| 실행 재현 | `growth.py RunManifest`(18필드) | 매 실행마다 기록된다(§3) |

deterministic fixture의 성공 기준(사전 등록됨): FINAL held-out success 비열등 · 사전 지정 metric 개선 ·
사전 등록 negative-transfer fixture에서 success 감소 0 — 근거·실측은 [T13_growth.md](T13_growth.md)와
[T13_live_pilot.md](T13_live_pilot.md)가 소유한다.

## 2. T00b-A 칸별 소재 — source/brain/prompt/policy/hardware/task/cache/seed

| 요구 칸 | 소유 자리 | 관찰(2026-09-24) |
|---|---|---|
| source | `RunManifest.source_head` | 기록됨 |
| brain | `RunManifest.brain_version` | `fixture-brain/v1` |
| policy | `RunManifest.policy_version` · `advisory_refs` | mature arm만 policy 버전을 갖는다 |
| task | `RunManifest.split`·`task_ids`·`corpus_digest` | split·과제 목록·corpus 봉인 |
| cache | `RunManifest.cache_mode` | `cold-fixture-cache` |
| seed | `RunManifest.seed`(+ `spec.seed`) | 기록됨 |
| prompt | 별도 필드 없음 — **deterministic fixture는 prompt를 corpus에서 파생**한다 | corpus의 task 정의가 곧 입력이며 `corpus_digest`가 그 봉인이다. prompt 템플릿 실험은 live pilot 이월 |
| hardware | 별도 필드 없음 — **deterministic fixture는 하드웨어 독립**이다(시간 기반 metric 없음) | 실측 하드웨어·스냅샷은 live pilot의 `ProviderAttestation`(model_id·model_snapshot·hardware)이 소유한다(빈 스냅샷은 거부) |

## 3. T00b-B — skeleton 직접 관찰 (2026-09-24)

격리 store root에서 CLI 표면을 직접 돌렸다(/tmp 임시 root, production vault 아님).

| 명령 | exit | 관찰 |
|---|---:|---|
| `--help` | 0 | 사용법·5개 mode·계약 인자 노출 |
| `--print-spec --output spec.json` | 0 | 등록용 spec JSON 생성 |
| `--mode demo --manifest spec.json --store-root <root>` | 0 | Fresh/Mature paired·ablation 포함 아티팩트(JSON: spec·comparison·ablations) — 실행마다 `RunManifest` 8회 기록 |
| `--mode fresh` / `--mode mature` / `--mode ablation --mechanism RISK_SHAPING` | 0 | 단일 mode 각각 통과 |
| `--mode live-pilot` | 2 | **NOT_RUN** — "이 CLI는 deterministic fixture harness다"(fixture 결과를 live로 대체하지 않는다) |
| `--mode bogus` | 2 | argparse 사용법 오류로 거부 |

**이 관찰이 잡은 결함(수정함):** `--store-root`에 **상대 경로**를 주면 target `file_path`가 상대로
내려가 executor sandbox가 project_root에 다시 붙여 이중 경로를 만들고, fixture 쓰기 실패가
validation 실패 → `PromotionRefused`로 **다른 얼굴로** 나타났다(2026-09-22 P10 실측은 절대 경로라
드러나지 않았다). CLI가 store root를 절대 경로로 정규화해 막았고, 상대·절대 모두 exit 0임을 재실측했다.

## 4. 한계

- 값은 이 문서에 없다 — 위 소유자를 직접 읽을 것. metric 표의 `LATENCY_P50` unit 표기는 `ms`지만
  deterministic fixture의 값은 retry 중앙값 대리값이며 실측 latency는 live pilot 이월이다.
- 실제 provider·하드웨어·prompt 템플릿·확증 표본 등록은 live pilot 회차이며 확증 표본 등록은 사람 결정이다.
- Fresh baseline 보존 계약(데이터 오염 0): fresh arm은 advisory 없이 **분리 저장 root**에서 돈다 —
  계약 문은 growth.py 모듈 docstring이 소유한다.
