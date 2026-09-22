---
title: "Current Working Tree Assessment and Gap Analysis"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Current Working Tree Assessment and Gap Analysis

## 분석 기준과 한계

대상 저장소는 `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`다. 이 v1.1은 이전 코드 조사 기록과 최신 문서에 보고된 구현 증거를 구분하고, 철학 검토에서 발견한 실행 계약 누락을 보완한다. 이번 문서 편집에서 source graph·실제 코드·runtime 시험을 다시 감사한 것은 아니다.

아래 G01~G16의 현재 구현 열과 runtime 흐름은 기존 v1.0 조사 기록이다. 당시 미커밋 변경분을 포함한 파일과 [CURRENT_TREE_MANIFEST.json](CURRENT_TREE_MANIFEST.json)에 근거했으며, 최신 구현이 없다는 뜻으로 재사용하지 않는다. 위치 anchor는 P00에서 재확인한다. HEAD 하나로 dirty tree를 대체하지 않는다.

Constitution → Architecture Invariants → 관련 Protocol이 목표 기준이다. 현재 구현이 편리하다는 이유로 목표를 줄이지 않으며, 문서에 목표가 있다는 이유로 구현 완료로 간주하지 않는다. 미확인은 부재나 위반의 확정이 아니다.

### 최신 문서에 추가된 구현 보고

| 영역 | 보고된 진척 | 남은 확인 |
|---|---|---|
| P00 / G01 등 | [T00](evidence/T00_baseline.md): 일부 경계·회귀·당시 manifest 대조 | 현 파일과의 일치, 전체 진입점 실호출, 초기 benchmark |
| P01 / 모델 | [T01a](evidence/T01a_typed_model.md): typed model·schema module PASS | v1.1 선별 기록·의미 주체·schema 정합화 |
| P02 / G02/G04/G05 | [T02](evidence/T02_canonical_store.md): canonical store·legacy adapter module PASS | 실제 Vault writer 동시성, 사용자 경로 통합, migration |
| P03 / G13 | [T01b](evidence/T01b_protection.md): module/tool gate/store 보호 PASS | migration/evolution hook, 승인 발급과 실제 경로 검증 |
| P04 / G03/G06 | [T03/T04](evidence/T03_T04_context_brain.md): Context/Brain module PASS | 최소충분·semantic 경계 시험, 실제 provider/router 연결 |

보고된 PASS는 해당 문서의 범위와 시점에 한정한다. 현 코드의 동일성·신규 인수 조건은 Acceptance Checklist에 별도로 기록한다. 새 증거가 기존 분석을 대체할 때 이전 근거를 지우지 않고 reassessment를 추가한다.

## 기존 조사에서 기록한 runtime 흐름

`AgentRuntime.start_stream → DirectTaskExecution`, `submit_task → plan_task + TaskRunner.submit_task`가 존재한다.
AgentRuntime은 model resolution, task idempotency key 전달, resume/status/event replay, persistent objective 연계를 담당한다.
ToolExecutor.execute는 PlanGuard/GatePipeline/preflight/registry permission을 거친다.
ContextShaper.shape는 메시지 절삭·압축·handle collapse를 제공한다.
PersistentAgencyController는 durable objective와 bounded event projection, PersistentAgencyStore는 append-only trajectory와 SQLite 저장을 제공한다.
VaultEngine.write_note는 lock·atomic replace·Git commit 뒤 RAG/wiki/event 동기화를 한다. same-path append-only API는 아니다.
CognitiveLoop는 Verify/Reflect/Adapt 기반이며 dialectic 기본값은 생성자에서 True다. 실제 활성 여부는 호출부 config를 추가 확인해야 한다.

## Component inventory와 gap

현재 구현 열은 기존 조사 시점의 기록이며 최신 구현 보고는 위 표와 함께 읽는다. 목표와 validation은 v1.1 인수 계약이며 통과 선언이 아니다. C번호는 헌법 원칙 번호다. G17~G22는 추가 문서 검토에서 드러난 요구·검증 공백이다.

| ID / 요구·헌법 | 현재 구현·근거 | 목표 / gap / 변경 권고 | 분류·우선순위 | 위험·의존성 | 검증 |
|---|---|---|---|---|---|
| G01 연속성 C1/4 | `engine/agent_runtime.py:94` AgentRuntime; submit/resume/event 연결 | 같은 entry point에 cognitive adapter 연결; 공통 episode 계약 추가 | MODIFY CORE | stream/API 회귀; P01/P03 | T11 brain 교체·resume |
| G02 역사 C7 | `engine/persistent_agency_store.py:91` SQLite trajectory; `persistent_agency.py:96` controller | 기존 event/objective ID를 canonical ID에 매핑; 별도 중복 scheduler 금지 | MODIFY CORE | 이중 원본 위험; P01/P02 | T02 replay·동일 결과 |
| G03 context C19 | `engine/context_shaper.py:101` 압축; ProjectedContext event IDs 존재 | Goal/state/evidence 중심 ContextPackage + 관련성 선별·최소 advisory·handle 확장 | MODIFY CORE | 제약 누락·context overflow; P02/P04 | T03-A~D 최소충분·비강제·L0 보존 |
| G04 영속 C7/8 | `engine/vault.py:627` atomic replace+Git+RAG | create-only canonical API, transaction publish/recovery 추가 | MODIFY CORE | 기존파일 덮어쓰기·부분 publish; P01 | T02 fault injection |
| G05 memory C1/19 | `knowledge/memory_service.py:367` SQLite snapshot 저장 | canonical episode와 snapshot/index 구분·adapter | MODIFY CORE | migration/ID 손실; P02 | T12 index rebuild |
| G06 Brain C1/2/20 | `engine/model_router.py` routing strategies; AgentRuntime.resolve_model | routing 재사용 + Structured BrainAdapter | KEEP CORE + NEW 계약 | fallback output 차이; P01/P04 | T04-A~C 교체·protocol·Primary 통합 |
| G07 governance C4/12/16 | `engine/tool_executor.py:188` 다층 gate와 문자열 반환 | 기존 gate 앞/뒤 typed request/result/feedback adapter | MODIFY CORE | 중복 승인·우회; P05 | T05 reshape feedback |
| G08 commit C14/15 | 읽은 runtime 경계에 원문 9-check COMMIT 연결 미확인 | provider-free readiness module 신설 후 연결 | NEW CORE | 기존 quality gate와 혼동; P01/P05 | T06-A~D LLM/규칙 semantic judge 0 |
| G09 실행 복구 C4/7 | `engine/task_state_store.py:62` CAS/event transaction/idempotency | task 제출 보장을 action receipt/reconciliation까지 연결 | MODIFY CORE | 외부 중복 실행; P02/P06 | T07 crash 후 dispatch 중복 0 |
| G10 기존 인지 C2/13/21 | `engine/cognitive_loop.py:107` Verify/Reflect/Adapt·dialectic 설정 | mechanical verification 재사용, 의미 해석은 Primary; simple/expanded 및 stop≠READY 보장 | REFACTOR CORE | 호출부에 따른 의미 변경; P04/P05 | T08-A~D sparse/targeted/stop |
| G11 경험 C8/9 | PersistentAgency task result와 memory snapshot 기반 존재 | 공통 계보·해석 분리 + 운영 기록/Experience 선별·세 평가 분리 | NEW 계약 / MODIFY 저장 CORE | 원본과 해석 혼합; P02/P07 | T09-A~E 선별·평가·원본 불변 |
| G12 학습 C9/10/18 | `self_evolution_coordinator.py:432` grade/cooldown trigger | candidate/validation/promotion/rollback/trace 분리 | REFACTOR CORE | trigger를 promotion으로 오해; P08/P09 | T10-A~E 검증·적용·rollback; T13 전이 |
| G13 보호 C5 | 기존 tool gate 존재; 헌법 write-protection 전체 경로 미감사 | shell/plugin/evolution 포함 protected target enforcement | NEW CORE | 문서 선언만 보호; P03/P05/P07/P11 | T01b 실제 우회 경로 거부 |
| G14 평가 C11/23 | `benchmark_harness.py:486` multi-target/task outcome harness | P00/P01 초기 계측 + 같은 Brain/code/hardware/task의 fresh/mature 비교 | MODIFY CORE | answer leakage·사후 기준 변경; P00/P01/P09/P10 | T00b/T13 |
| G15 Swarm/Fly/graph C2/11 | ModelRouter에 COLLECTIVE enum; Fly 실행 연결은 미확인 | multi-brain은 conditional, graph/meta-learning은 evidence 후 | DEFER CONDITIONAL/ADVANCED | 이름만 보고 삭제 금지; P00 | config·caller 추가 감사 |
| G16 제거 결정 C11 | 이번 조사에서 즉시 제거할 충분한 근거 없음 | REMOVE 없음; migration 증거 뒤 별도 ADR | REMOVE 후보 없음 | 불필요한 기능 손실 예방 | 별도 ADR |
| G17 경험 선별 C8/9/19 | 기존 P08/T09에 Operational Record와 Experience의 선별 인수 조건이 명시되지 않았음 | 선별 사유·provenance·주체·보류·후속 형성, 예상 일치의 중요 재검증 허용 | MODIFY CORE 계약 | 모든 로그의 경험화·Context 오염; P01/P08 | T01a/T09-A~E |
| G18 학습 의미 경계 C2/4/20 | Evaluator/PatternBuilder interface는 있으나 의미 해석 책임이 구체적이지 않았음 | 기계 집계는 Body, 의미 해석·가설은 Primary/human-assisted; provenance 보존 | MODIFY CORE 계약 | Body의 semantic Brain화; P08/P09 | T09-C/E, T10-B |
| G19 초기 평가 C9/11/23 | 원문은 초기 skeleton, 기존 실행 카드는 P10에만 benchmark 명시 | P00 metric/split/manifest, P01 실행 skeleton, P10 성장 평가 | MODIFY CORE 순서 | 사후 평가·기준 변경·누수; P00/P01/P10 | T00b-A/B, T13 |
| G20 희소 활성 C11/12/13/21 | simple/expanded 선언은 있으나 불필요한 호출·stop≠READY 시험이 부족 | 단순 task는 필요한 경로만, bounded expansion, Primary delta와 Body budget 분리 | MODIFY CORE 인수 | 상시 multi-brain·무한 검증; P04/P08 | T04-C, T08-A~D |
| G21 문서 우선순위·증거 C5/11 | README가 계획을 먼저 안내; module PASS와 전체 인수의 혼동 가능 | 상위 계약 우선, scope/spec/source별 증거, 신규 시험 미실행 분리 | MODIFY CORE 개발 절차 | 편의에 따른 철학 변경·허위 완료; P00/P12 | T14와 전체 scope 대조 |
| G22 성장 범위 C9/10/18 | Context 데모는 구체적이나 다른 성장 영역으로의 확장·권한 경계 추적이 약함 | target/scope/validation/trace 확장, 기존 grant 안의 위임 선택, 신규 ceiling 자동 생성 금지 | MODIFY CORE 계약 | Context-only 고착 또는 자율 권한 확대; P09/P10 | T10-E/T13 |

파일 경로는 모두 repository의 `src/antigravity_k/` 기준이다. line은 이번 확인 시점의 anchor이며 변경 후 재탐색한다.

## 기존 Compatibility 평가와 v1.1 재확인 지점

| 점검 | 확인 결과 | 후속 작업 |
|---|---|---|
| Body가 semantic Brain인가 | CognitiveLoop/Orchestrator 및 Evaluator/PatternBuilder 의미 책임의 실제 경로 확인 필요 | P00/P04/P08/P09, T04-C/T10-B |
| history가 유일한 memory인가 | PersistentAgency/SQLite/Vault가 이미 존재; 단순 history-only라고 할 수 없음 | P02/P04 |
| Swarm이 Primary를 대체하는가 | collective 전략 존재; 기본 활성·최종 통합 주체 미확정 | P00 |
| tool raw output injection | ToolExecutor 문자열 반환 확인; 최종 injection 처리 미확정 | P04/P07 |
| decision overwrite | trajectory append 기반 존재; core Decision 계약 미확인 | P02/P06 |
| experience/interpretation 혼합 | typed model의 분리 시험 보고는 있으나 실제 선별·형성·재해석 흐름은 별도 인수 | P08, T09-A~E |
| COMMIT이 semantic judge인가 | 신규 COMMIT 미연결; 기존 verifier를 COMMIT으로 재명명 금지 | P06 |
| 위험이면 항상 human인가 | gate denial/pause/allow가 모두 존재; reshape 계약 미확인 | P05 |
| single autonomy score인가 | 전체 authority profile 미감사 | P00/P05 |
| 경험 저장만 하고 안 쓰는가 | persistent context 재주입 경로 존재; validated policy behavior trace 미확인 | P09/P10 |
| evolution이 헌법을 바꿀 수 있는가 | 기존 조사 후 P03 module/gate 보호 보고가 추가됨; 실제 evolution/migration hook은 미완료로 보고 | P03/P05/P11, T01b |

## Architecture conflict record AC-001

Current Behavior: Vault는 동일 path를 atomic replace하며, 기존 agency canonical event는 SQLite다.
Constitutional Conflict: SQLite나 atomic replace 자체는 헌법 위반이 아니다. 헌법적 요구는 역사·계보·권한·연속성 보존이다. Canonical Markdown/Files-first와 Git persistence는 현 Architecture Spec의 engineering 선택이며 자동으로 새 헌법 원칙이 되지 않는다. 기존 API만으로 새 불변 기록 계약을 보장하는지는 별도로 확인한다.
Why it exists: 일반 노트 편집과 task 운영에 적합한 기존 저장 모델이다.
Risk of changing it: 검색·위키 동기화·task 복구 회귀 및 이중 원본.
Migration options: 기존 DB 전면 이관 / 기존DB adapter+새 cognitive 원본 / 새 독립 저장소.
Recommended path: 기존DB adapter+새 cognitive 원본, ID mapping으로 기존 계보 보존.
Temporary compatibility layer: legacy refs와 origin digest를 read-only로 가져온다.
Validation: T02/T09/T12와 기존 vault/task-state 회귀. irreversible migration은 별도 human 결정.

## v1.1 Architecture Conflict / Gap 처리 기록

### AC-002 — Experience 형성 기준 누락

Current Behavior: 기존 개발 문서에는 episode 기록과 Experience 선별의 구분이 명시되지 않았다. 모든 로그가 실제로 Experience가 되는지는 runtime 미확인이다.
Constitutional/Agreement Concern: SSAK-AI 소유의 경험은 당시 Context·판단·실행·현실 feedback을 연결하며 미래 판단에 가치가 있어야 한다. 운영 기록 보존과 경험 선별은 별개다.
Why it exists: 원문을 개발 카드로 요약하면서 선별 단계가 빠졌다.
Risk of changing it: 선별되지 않은 기존 이력을 삭제하거나 새 선별 정책으로 과거를 재작성할 위험.
Migration options: 기존 record 유지 + 선별 metadata/projection 추가 / 새 Experience reference 생성.
Recommended path: 운영 기록을 유지하고 새 선별 기록·Experience를 append한다. 의미 가치 해석은 Primary/human-assisted 경로로 남긴다.
Temporary compatibility layer: 기존 Experience는 legacy 분류로 보존하고 새 선별 기준 통과를 소급 주장하지 않는다.
Validation: P01/P08, T01a/T09-A~E. 예상 일치의 중요한 재검증과 원인 UNKNOWN 종료를 포함한다.

### AC-003 — 초기 Benchmark와 후행 평가의 혼동

Current Behavior: 초기 Benchmark Skeleton 요구가 기존 Roadmap의 P10 후행 작업에만 배치됐다.
Constitutional/Agreement Concern: 경험의 실제 효과와 복잡성의 가치를 증명하려면 사전 기준선·측정·split이 필요하다.
Why it exists: 최종 성장 평가와 초기 계측 준비를 하나의 카드로 묶었다.
Risk of changing it: 이미 얻은 결과에 맞춰 baseline·성공 기준을 소급 작성할 위험.
Migration options: P10만 유지 / P00/P01 준비와 P10 평가로 분리.
Recommended path: P00 사전 metric/split/manifest, P01 실행 skeleton, P10 frozen 평가. 이미 관측된 데이터는 exploratory로 명시하고 새 final split을 분리한다.
Temporary compatibility layer: 기존 benchmark harness를 재사용하되 미지원 metric은 미측정으로 표시한다.
Validation: T00b-A/B, T13. source/code/Brain/hardware/task 조건·negative transfer·실제 선택 변화를 연결한다.

## 변경 분류와 완료 판정

KEEP/MODIFY/REFACTOR/REMOVE/NEW/DEFER는 변경 전략이며 구현 완료 상태가 아니다. CORE/CONDITIONAL/ADVANCED는 필요성·활성화 범위이며 상시 실행을 뜻하지 않는다. Primary Brain·기본 Governance·Experience 성장 경로는 Core이지만 Secondary·심층 conflict 조사·Risk Shaping은 해당 trigger가 있을 때 활성화한다. Advanced graph/meta-learning/자동 architecture self-improvement는 실증 없이 v1 필수 의존성으로 만들지 않는다.

각 G 항목은 상위 원칙, 현재 근거의 날짜/source, 담당 카드, 시험 ID, 관찰 artifact, 미해결 제한을 연결한다. 문서 내용이 존재한다는 이유로 gap을 닫지 않는다. 현 파일과 과거 근거가 다르면 P00에서 재조사하고 재평가 기록을 추가한다.

## 후속 문서 정합화

P01/P08은 COGNITIVE_DATA_MODEL·EXPERIENCE_AND_LEARNING·COGNITIVE_OPERATING_LOOP의 선별 표현을 정합화한다. P04/P09는 Brain/Context/학습 의미 책임을 명시한다. P00/P01/P10은 BENCHMARK_AND_ABLATION과 초기 계측 계약을 연결한다. P12는 Architecture Invariants→카드→시험→증거의 추적표와 기존 보고서를 갱신한다.

이는 누락된 실행 계약의 구체화이며 헌법을 수정하는 작업이 아니다. 세부 명세와의 실제 충돌이 발견되면 상위 원칙을 유지하고 별도 Architecture Conflict를 기록한다. 이번 완성본 작성만으로 해당 코드 변경이나 runtime 인수를 완료했다고 주장하지 않는다.
