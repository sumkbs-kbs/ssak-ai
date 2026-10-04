---
title: T13 실제 provider pilot 실행 가능성 및 에이전트 인계 계획
date: 2026-09-25
status: PLAN_READY_LIVE_NOT_RUN
owner: leader / delegated live-pilot implementer
source_head: 6be0263d121c1e2a7ade92d3127af226c5e0581f
observed_at: 2026-09-25T11:40:11Z
---

# 판정

로컬 provider는 존재한다. 실제 Fresh/Mature 성장 시험은 아직 실행되지 않았다. 현재 장애물은 provider 부재가 아니라 **실제 모델을 판단 경로에 넣는 LiveTrialPort 구현과 검증된 학습 상태 결선 부재**다. 기존 fixture의 계획된 retry 수에 모델 호출 하나를 덧붙이는 방식은 실제 성장 시험으로 인정하지 않는다. 이 문서는 실행 인계 계획이며 성능 PASS나 최종 인수 PASS가 아니다. 리더가 구현 담당자를 지정하고 아래 사전 조건을 만족한 뒤 격리된 로컬 pilot을 실행한다.

기본 방침은 유지한다: Brain이 의미 판단, Body가 기계적 제약 집행, COMMIT은 실행 허가와 분리, 사람 권한/헌법은 학습 대상 아님, 관찰→후보→독립 validation→activation 순서를 생략하지 않음, 역사 기록은 append.

# 현장 확인

읽기 전용으로 `curl --max-time 5`를 사용하여 `http://127.0.0.1:11434/api/tags`, `/api/version`, `/api/ps`를 조회했다. HTTP 응답을 관찰했으며 generation/download/benchmark는 수행하지 않았다.

| 항목 | 관찰 |
|---|---|
| Ollama | version 0.34.4, API 정상 응답 |
| 기본 pilot 후보 | ssak-finetuned:qwen2.5-0.5b, 494.03M, F16, 994156434 bytes |
| 위 모델 digest | bac64e9e331da16c10ffe68d54fe3569c72f92826c829f7a0c71f6ffc6c9ba1c |
| 별도 대형 모델 | qwen3.8:latest, 27.3B, Q4_K_M, 17741872154 bytes |
| 위 모델 digest | 22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643 |
| 기타 설치 모델 | nomic-embed-text:latest, llava:latest, llama3.2-vision:11b |
| 현재 로드 모델 | /api/ps의 models=[] |
| host | arm64, Apple M5 Max, hw.memsize=137438953472 (128 GiB) |

태그 및 capabilities는 서버가 보고한 메타데이터다. 실제 schema 준수/도구 선택 품질, 속도, 재현성을 보장하지 않는다. 설치 모델의 학습 corpus를 이번 조사로 확인하지 않았으므로 pretraining/finetuning 오염 없음도 주장할 수 없다. 실행 시 동일 digest를 매 trial 전후 확인하고 바뀌면 INVALID로 중단한다. 임의 태그 고정만으로 snapshot_pinned=true를 쓰지 않는다.

# 현재 코드와 보완 지점

- `src/antigravity_k/engine/cognitive/live_pilot.py`: `LiveTrialPort`는 Protocol이다. graph 검색 결과 구현은 시험용 `StubLivePort`뿐이다. `LivePilotHarness`는 주입된 outcome의 카운터를 그대로 집계한다. raw request/outcome 개별 행은 report에 보존하지 않는다.
- `src/antigravity_k/engine/cognitive/growth.py`: `GrowthRunner`는 FixtureThink, 미리 정해진 missing evidence와 correction append로 retry를 만드는 결정적 fixture다. `growth_phase`도 그 결과로 후보와 validation을 만든다. 해당 수치를 그대로 live outcome으로 복사하지 않는다.
- `scripts/benchmark_cognitive_growth.py`: `--mode live-pilot`는 수치 없는 NOT_RUN과 exit 2를 반환한다. 이는 지금의 정확한 동작이다. 새 live 실행 경로가 검증되기 전 바꾸지 않는다.
- harness는 현재 run_kind, 최소 repetition, split에 task 존재만 검사한다. 등록 corpus digest, split ID 정확 일치/중복, held_out_min_samples를 실행 전에 검증해야 한다. order_policy는 문자열이지만 실제 실행은 항상 alternating이므로 다른 값 거부가 필요하다.
- `mechanisms`를 받지만 LiveTrialRequest로 전하지 않아 live ablation 동작을 증명하지 못한다. 최초 pilot에는 live ablation 완료 주장을 제외하고 별도 후속 카드로 둔다.
- `_verdict`는 primary 이름과 무관하게 retries를 비교하고, safety/duplicate는 mature만 검사한다. 현재 고정 primary=total_retries를 명시적으로 제한하거나 등록 metric대로 계산해야 한다. 어느 arm이든 safety/duplicate 위반이면 전체 안전 게이트 실패로 기록한다.
- timeout/예산 초과/port exception의 partial artifact가 없고 invalid counter(음수, NaN 등)를 거부하지 않는다. 관측 누락을 0으로 바꾸지 않는 계약이 먼저 필요하다.

# 작업 소유권과 순서

## LP-A: harness와 측정 계약 담당

소유: `engine/cognitive/live_pilot.py` 및 필요 시 같은 package의 작은 types/report 모듈, `tests/cognitive/test_live_pilot.py`. LP-B와 public API를 먼저 합의한다. 기존 fixture 파일은 수정하지 않는다.

- [ ] 실행 전 등록 spec와 전체 corpus digest/split 목록/중복/FINAL unique task 수를 검증한다. 기준 완화는 새 experiment ID와 사전 등록 artifact를 요구한다.
- [ ] raw trial ledger를 append한다: run_id, task_id, arm, repetition, order, 시작/종료, seed, policy/advisory digest, source SHA+dirty manifest, prompt/response artifact hash, 실제 event/receipt refs, outcome.
- [ ] nonnegative finite metric 검증; 누락 provider token usage는 unknown/INVALID로 남기며 0으로 성공 집계하지 않는다. 새 명시적 측정 상태 또는 strict rejection 중 API에 맞는 방법을 정한다.
- [ ] 예산/취소/timeout/exception은 이미 관찰된 raw ledger를 보존하고 INCOMPLETE 또는 INVALID artifact를 쓴다. 완료 분모를 몰래 축소하지 않고 verdict는 미판정으로 남긴다.
- [ ] safety와 duplicate를 양 arm에서 검사한다. actual brain_calls를 raw row에 보존하고 summary에도 보고한다.
- [ ] 회귀시험: corpus 변조/중복/표본 부족, negative/NaN counter, 중간 실패, fresh-only 안전 위반, unsupported order/primary, fixture-live 혼합 거부.

인수: 실패 케이스에서 provider 호출 0 또는 완료 전 중단과 정확한 partial 행 보존; 기존 fixture/stub 결과는 계속 자체 시험으로만 표시.

## LP-B: 실제 trial port와 성장 사슬 담당 (주요 구현)

소유 제안: 신규 engine 디렉터리의 신규 예정 파일 `cognitive_live_trials.py` 및 작고 응집된 외부 adapter 모듈, cognitive 시험 디렉터리의 신규 예정 파일 `test_live_trial_adapter.py`. core cognitive package에서 provider/UI import 금지 유지. 현재 수정 중인 actions/surface/protection 파일과 충돌하지 않도록 리더와 계약한다.

- [ ] 실제 local model 요청이 task 해석/계획/재판단에 사용되도록 연결한다. 미리 정해진 correct action을 실행하고 모델 답변을 버리는 구현은 거부한다.
- [ ] 본문/도구 명세를 제한된 JSON으로 제공하고 파싱 실패·거부·수정 시도를 실제 event로 남긴다. 모델이 반환한 operation/args를 schema와 governance로 검증한다. 모델의 self-reported success나 retry는 metric으로 사용하지 않는다.
- [ ] TRAIN의 실제 실패/성공 관찰로 ExperienceEvaluator→CandidateProposer 경로를 사용하고, VALIDATION 실제 trial로 HeldOutValidator를 거쳐 PolicyLifecycle의 activation 증거를 얻는다. fixture `GrowthRunner.growth_phase()` 산출물을 live 정책으로 옮기지 않는다.
- [ ] validation 미통과 시 임의 mature 효과를 만들지 않는다. 정책 후보 미활성 상태/성장 미확인으로 보고한다. 학습 실패도 정확한 pilot 결과다.
- [ ] FINAL 전에 정책/경험 snapshot을 고정한다. Fresh에는 동일 baseline만, Mature에는 검증된 train/validation 유래 상태만 제공한다. 각 trial은 별도 새 canonical store/action journal/tool directory로 시작하며 앞선 FINAL 결과는 다음 trial의 prompt·policy·cache에 입력하지 않는다.
- [ ] 도구는 격리 root에서만 실제 읽기/append를 수행한다. production vault, 네트워크 side effect, shell arbitrary execution, 헌법/권한 변경은 trial 도구 목록에 넣지 않는다. body/readiness/authority/journal/receipt를 우회하지 않는다.
- [ ] 실제 파일 결과/receipt/trace에 기반한 독립 deterministic evaluator로 success 판정. model text와 evaluator answer-key는 분리한다.
- [ ] 단위 mock은 오류 경로 검증에만 사용하고 live report는 real local HTTP+runtime으로만 만든다.

인수: 1회 smoke에서 response가 action 결정에 사용된 trace, 실제 제한 도구 receipt, 평가기 결과, token/latency 원천, 정책 미검증 시 승격 거부가 모두 관찰된다. smoke는 성장 증거가 아니다.

## LP-C: live CLI와 실행 담당 (LP-A/B 완료 후)

소유 제안: 신규 scripts 디렉터리의 신규 예정 파일 `benchmark_cognitive_live.py`, cognitive 시험 디렉터리의 신규 예정 파일 `test_live_cli.py`, 별도 `evidence/.../live-pilot/` 결과 디렉터리. fixture CLI는 이전 NOT_RUN 계약을 유지하거나 명시적으로 신규 CLI 안내만 추가한다.

- [ ] `--register-spec`, `--manifest`, `--corpus`, `--store-root`, `--output`, local endpoint/model digest, `--max-calls`, `--max-seconds`, `--max-output-tokens`를 제공한다. default invocation은 등록/검증이며 실험 실행에는 명시적 run 인자가 필요하다.
- [ ] 아래 budget을 실행 전에 저장하고 요청 수/시간/토큰 상한을 기계적으로 집행한다. endpoint는 이 pilot에서 loopback만 허용한다. 설치 모델만 사용한다.
- [ ] CLI help, 나쁜 manifest, provider unavailable, 1-task smoke, 등록된 완전 paired pilot을 직접 실행한다. real HTTP generation임을 artifact에서 검증한다.
- [ ] 최종 결과는 PASS/FAIL 포함 실제 관찰 그대로 기록한다. improved=false도 정상적인 완결된 시험이다. 완수하지 못하면 NOT_RUN/INCOMPLETE와 실제 사유를 남긴다.

## LP-D: 독립 검증 담당 / 리더 최종 판단

- [ ] raw ledger에서 summary를 다시 계산하고 arm×task×trial Cartesian product 누락/중복을 검사한다.
- [ ] source SHA+dirty hash를 고정하고 모든 산출물이 그 tree를 가리키는지 확인한다.
- [ ] train/validation/final 겹침, 정책 근거에 final 노출, fresh→mature 가변 데이터 공유, answer-key prompt 누출을 감사한다.
- [ ] fixture 수치 또는 1회 shadow 응답을 live growth 증거로 가져오지 않았는지 검사한다.
- [ ] T13 문서와 최종 인수 체크리스트를 실제 상태에 맞게 갱신한다. 리더는 기본 방침 준수와 증거 완결성을 판단한다.

# 사전 등록할 최소 실험과 예산 제안

이 숫자는 실행 제안이며 이번 조사에서 실행/등록된 spec이 아니다. 기준/예산을 정한 뒤 artifact를 저장하고 실행한다.

| 항목 | 제안 |
|---|---|
| corpus | 별도 live synthetic task 명세: TRAIN 2, VALIDATION 4, FINAL 18 unique tasks; 기존 분류·negative transfer 3 이상 유지 |
| 오염 방지 | live task의 새 evidence 내용/정답을 등록 시 고정, task family 분리 기록, pretraining 오염 불명 제한 명시 |
| repetitions | task당 arm별 3회; FINAL 18×3×2=108 trial (독립 task는 18이지 108 아님) |
| growth calls | TRAIN 2 + VALIDATION 4; 추가 validation arm 비교가 필요하면 4 trial을 사전 예산에 추가 |
| order | repetition별 Fresh-first/Mature-first 교대; 3회라 2:1 불균형임을 그대로 보고 |
| model | ssak-finetuned:qwen2.5-0.5b 위 digest; 대형 모델로 조용히 바꾸지 않음 |
| decoding | temperature=0, seed=20260922+trial_index를 두 arm에 동일하게 적용, num_ctx=4096, num_predict=256; 실제 지원/echo 확인 |
| per trial | 최대 Brain 요청 3, provider request timeout 30초, 추가 자동 HTTP retry 없음 |
| 전체 상한 | 최대 360 generation calls, generated tokens 최대 92160, wall-clock 20분, 동시 실행1, 외부 비용0; 초과 시 partial 보존 후 INCOMPLETE |
| warmup/cache | run당 명시적 warmup1을 측정 외로 기록, model resident 상태 공유 제한 명시; task prompt/response 캐시 없음. cold-fixture-cache라는 잘못된 라벨 사용 금지 |
| claim | LIVE_PILOT_PILOT_ONLY; 확증 표본 크기 미등록, 일반 성능 우위/통계적 유의성 주장 없음 |

3회 반복은 sample independence를 추가하지 않으며 p95도 작은 표본의 기술 통계다. pilot 변동성을 보고 동일 run의 확증 기준을 사후 변경하지 않는다. 초기 1-task smoke는 본 pilot corpus와 분리하며 정책 학습 데이터에 섞지 않는다.

# 실제로 인정할 지표

| 지표 | 허용 원천 | 금지되는 대체 |
|---|---|---|
| success | task별 사전 evaluator + 실제 파일 결과/receipt | 모델의 성공 선언, 고정 True |
| retries | 최초 계획 이후 실제 재판단/재제출 event 수, 정의 사전 고정 | fixture missing 여부로 합성한 수치 |
| tool_calls | executor dispatch/receipt event 수 (거부는 별도) | Brain text 속 도구 언급 수 |
| brain_calls | 실제 완료/실패 HTTP 시도 ledger | 항상1 |
| tokens | provider 응답의 prompt_eval_count+eval_count 원문 | 문자열 길이 또는 fixture0을 실측 token으로 표기 |
| latency | monotonic end-to-end trial 시간; load/provider duration은 별도 | fixture0 |
| duplicate | action-key/journal·receipt와 실제 effect ledger 비교 | 예외 없으면 False |
| safety | 제약 거부/이탈 시도와 실제 effect containment 점검 | 에러 없으면 빈 문자열 |
| negative transfer | 사전 label된 동일 task의 paired success 차이 | 실패 task를 사후 목록에서 제거 |
| 경험 재사용/정책 변화 | 검증·activation ID와 실제 selection/behavior trace | policy_version 문자열만 전달 |

# 조사한 tree fingerprint

HEAD만으로 dirty tree를 대표하지 않는다. 아래는 위 시점에 읽은 관련 파일 SHA256이며 후속 편집 후 재계산한다.

```text
16697ffda06f006fd5d7fee3575bcd19c10a98a03db23da240cddca36bf7b374  src/antigravity_k/engine/cognitive/live_pilot.py
745f1c105fa4ab6b3d92bf087db0e0dc632610389f85eb76db7c199da0d54111  src/antigravity_k/engine/cognitive/growth.py
c3d0a151d9133abd69e618b890416dac01e674f0966d62e74d9b23e199c9bd7b  scripts/benchmark_cognitive_growth.py
49eb5ad5387b1ce5bbcd9d0d626b537c6aef16f106d16323200526402b7abeb1  tests/cognitive/test_live_pilot.py
43809f9822f769569fbe842819a4c2a4087021d6ce1463ed309045b96784ac84  docs/ssak-ai-core/evidence/T13_live_pilot.md
aa99e6c5e5eba817b1ef5613b0e31eaab71e96a7ca86f32261e7af1729e8ddda  docs/ssak-ai-core/evidence/T13_growth.md
```

이번 담당자의 변경은 이 계획 문서 하나뿐이다. 코드/생산 데이터/모델은 수정하지 않았으며 실제 performance 결과는 생성하지 않았다.
