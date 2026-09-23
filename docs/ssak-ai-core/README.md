---
title: "SSAK-AI Cognitive Core 개발·인수 기준"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# SSAK-AI Cognitive Core 개발·인수 기준

SSAK-AI는 교체 가능한 Neural Brain을 활용하는 Persistent Adaptive Cognitive System이며, Human Partner에게는 Persistent Adaptive Cognitive Partner다. Brain이 의미를 판단하고, SSAK-AI Body는 상태·Context·근거·권한·실행·경험의 연속성을 소유한다.

이 문서는 Constitution을 변경하지 않고 개발계획과 인수 조건을 구체화한 v1.1이다. 문서 완성과 runtime 완성은 별개다. 원본 저장소의 파일을 덮어쓰지 않은 배포용 완성본이며, 함께 제공된 상위·참고 문서는 작성 시점의 읽기용 사본이다.

## 1. 문서 권위와 읽기 순서

1. [Constitution](SSAK_AI_CONSTITUTION.md): 최상위 원칙, 인간의 보호 권한, 헌법 변경 절차.
2. [Architecture Specification](SSAK_AI_ARCHITECTURE_SPEC_V1.md): 시스템 경계와 Architecture Invariants.
3. 해당 작업의 세부 Protocol: 아래 목록에서 선택한다.
4. [Gap Analysis](SSAK_AI_GAP_ANALYSIS_V1.md): 현재 근거, 미확인 사항, 변경 이유.
5. [Implementation Roadmap](IMPLEMENTATION_ROADMAP.md): P00~P12 구현 계약과 선행 조건.
6. [Acceptance Checklist](ACCEPTANCE_CHECKLIST.md): 시험 시나리오와 증거를 통한 완료 판정.

하위 문서, 현재 코드, 구현 편의, 성능 최적화는 상위 원칙을 변경할 근거가 될 수 없다. 충돌하면 상위 계약을 유지하고 Architecture Conflict를 기록한다. 헌법 의미·Human Authority·Protected Authority·Project Premise 변경은 명시적인 인간 결정이 필요하다. 그 밖의 구현 세부사항은 상위 계약 안에서 진행한다.

각 카드는 `상위 원칙 → Gap 근거 → 구현 → 실제 표면 검증 → 인수 증거 → 다음 카드` 순서로 닫는다. 다른 문서의 짧은 설명을 근거로 이 패키지의 상세 인수 조건을 생략하지 않는다.

## 2. 반드시 보존할 설계 경계

| 영역 | 구현 계약 | 담당 카드 / 인수 |
|---|---|---|
| Brain 교체·연속성 | State/Memory/Experience/Decision/Knowledge/Governance/Authority/Human Partnership은 특정 provider session에 종속되지 않음 | P01/P02/P04/P11, T04/T11/T12 |
| Brain/Body | 의미 해석·가설·최종 semantic integration은 Primary Brain. Body는 구조화·비교·provenance·권한·실행을 담당 | P04/P05/P08/P09, T04/T05/T08/T10 |
| Context | 현재 상태에서 재구성. 최소충분 주입, handle 기반 선택적 확장, 과거 결론 강제 금지 | P04, T03 |
| Governance | 요청 변경을 숨기지 않음. 다차원 권한과 Risk Shaping, protected boundary 유지 | P03/P05/P07, T01b/T05/T07 |
| COMMIT | 9개 readiness 조건만 검사. LLM·규칙·점수 어느 방식으로도 결론의 의미적 정답을 재심사하지 않음 | P06, T06 |
| Stop·Closure | 의미 변화가 없으면 확장 중단. Stop은 READY가 아니며 Material Trigger로 최소 범위 reopen | P06/P08, T06/T08 |
| Experience | 운영 기록과 선별된 Experience 구분. 관찰·평가·해석 분리. 과거 원본 보존 | P08, T09 |
| 성장 | Experience→Evaluation→Candidate→Validation→Versioned Policy→실제 Future Behavior Change | P09/P10, T10/T13 |
| 복잡성 | Simple to start, designed to mature. 조건부 기능은 필요할 때만 활성화, 새 복잡성은 증거로 정당화 | P00/P08/P10, T00b/T08/T13 |
| 인간과의 관계 | Human Partner가 최종 Value/Authority Owner. 기존 승인 범위는 존중하며 불필요한 승인 반복 금지 | P03/P05/P12, T01b/T05/T14 |

헌법 24개 원칙 전체가 적용된다. 이 표는 헌법을 대체하는 축약 헌법이 아니라 구현·검증 위치를 찾기 위한 안내다.

## 3. 영구 설계 문서

- [운영 루프](COGNITIVE_OPERATING_LOOP.md), [데이터 모델](COGNITIVE_DATA_MODEL.md).
- [Brain Engagement](BRAIN_ENGAGEMENT_PROTOCOL.md), [Context·Memory](CONTEXT_AND_MEMORY.md).
- [Evidence·Unknown](EVIDENCE_AND_UNCERTAINTY.md), [Decision·COMMIT](DECISION_AND_COMMIT.md).
- [Governance·Authority](GOVERNANCE_AND_AUTHORITY.md), [Experience·Learning](EXPERIENCE_AND_LEARNING.md).
- [Self-improvement](SELF_IMPROVEMENT_POLICY.md), [Benchmark·Ablation](BENCHMARK_AND_ABLATION.md).
- ADR: [Primary/COMMIT](ARCHITECTURE_DECISIONS/ADR-0001-primary-brain-authority.md), [Context](ARCHITECTURE_DECISIONS/ADR-0002-context-reconstruction.md), [Experience](ARCHITECTURE_DECISIONS/ADR-0003-experience-ownership.md), [Loop ownership](ARCHITECTURE_DECISIONS/ADR-0004-cognitive-loop-ownership.md).

세부 Protocol의 추가 보완은 Roadmap §공통 의미 계약과 해당 카드에 명시했다. Protocol·schema·구현이 이 계약과 어긋나면 담당 카드에서 함께 정합화하고 변경 근거를 남긴다. Constitution의 문구를 자동 수정하는 방법으로 해결하지 않는다.

## 4. 구현 선택과 불변조건의 구분

v1은 Canonical Markdown + explicit references, Git persistence, rebuild 가능한 index, versioned policy activation을 사용한다. 저장 형식·CAS 방식·예산·표본 수·namespace는 구현 선택이며 헌법 그 자체가 아니다. 현재 Architecture Spec의 계약으로서는 준수하고, 변경하려면 ADR·관련 명세·migration 및 검증 근거를 함께 갱신한다.

초기 rule-based 구현과 human-assisted candidate 작성은 허용한다. 그러나 경험이 쌓여도 행동이 바뀔 수 없는 구조, 검증 없이 정책을 적용하는 구조, Context 학습만 가능하도록 나머지 성장 경로를 영구 차단하는 구조는 허용하지 않는다.

## 5. 현재 상태와 증거 사용법

아래는 기존 증거 문서의 보고 내용이다. 이번 v1.1 문서 편집에서 코드·시험을 재실행했다는 뜻이 아니다. source SHA뿐 아니라 dirty-file digest, 시험 범위, limitation을 대조해야 한다.

| 영역 | 기존 보고 | 남은 인수 |
|---|---|---|
| P00 | [기준선](evidence/T00_baseline.md): 일부 경계·회귀 기록 | 전체 entrypoint 기준선, T00b 초기 계측 |
| P01 | [Typed model](evidence/T01a_typed_model.md): 모듈 시험 PASS | 현재 소스 재대조, v1.1 선별·계보 계약과 schema 정합화 |
| P02 | [Canonical store](evidence/T02_canonical_store.md): 모듈 시험 PASS | 실제 Vault 동시성·사용자 경로 통합 |
| P03 | [보호 경계](evidence/T01b_protection.md): 모듈/tool gate/store PASS | migration/evolution 실제 hook, 승인 발급·검증 |
| P04 | [Context·Brain](evidence/T03_T04_context_brain.md): 모듈 시험 PASS | 최소충분 Context·의미 경계 추가 시험, 실제 provider/router 통합 |
| P05 | [Governance](evidence/T05_governance.md): module + tool_executor surface PASS (31 시험) | CLI/API/stream/background 연결, 승인 발급 주체 검증은 P11 이월 |
| P06 | [COMMIT](evidence/T06_commit.md): module + canonical store 표면 PASS (28 시험) | loop(P08)·사용자 표면(P11) 실행 경로 연결 이월 |
| P07 | [Action](evidence/T07_actions.md): module + ToolExecutor·CanonicalStore 표면 PASS (17 시험) | task_state_store 재시작 복구, OBSERVE 경험 형성은 P08/P11 이월 |
| P08 | [Loop·Experience](evidence/T08_T09_episode.md): module + ToolExecutor·CanonicalStore 표면 PASS (21 시험) | production 대화 경로 opt-in(P11), Knowledge/Policy 승격(P09) 이월 |
| P09 | [Learning lifecycle](evidence/T10_learning.md): module + CanonicalStore 표면 PASS (29 시험) | 실제 성장 효과 계측(P10), runtime·사용자 표면 연결(P11) |
| P10 | [성장·ablation](evidence/T13_growth.md): deterministic fixture PASS (17 시험 + CLI artifact) | live pilot NOT_RUN, 실제 provider·표본 확대·실측 latency 이월 |
| P10 (live) | [live pilot harness](evidence/T13_live_pilot.md): harness·분리 계약 PASS (12 시험) | 실제 provider·확증 표본 등록은 사람 결정 필요 |
| P11 (부분) | [사용자 표면 opt-in](evidence/T11_surface.md): 실측 + adapter + read-only CLI/API(SSE 포함) + feature-off 회귀 PASS (36 시험) | 대화 스트림/background 배선, 실모델 QA, ACTIVE 실검증 이월 |
| P12 (부분) | [migration dry-run](evidence/T12_migration.md): source read-only·별도 root·mapping·index·rollback PASS (14 시험) | destructive 변환 NOT_RUN, 실사용 DB dry-run 이월 |
| P12 (T14) | [최종 Architecture Review](ARCHITECTURE_REVIEW.md): 헌법 24원칙(covered 15·partial 9·gap 0)·§63 12질문·§52 10질문 매핑 + 기계 검증 15 checks PASS(인용의 실재·추적, 증거 digest 의 drift, 증거 산문의 상태 주장까지 측정) · 고정 순서 전량 회귀 5 failed/7666 passed(cognitive 실패 0), 남은 5건은 커밋 이력·패키징·문서 기준선으로 분리 · 회귀가 찾은 enum identity 결함을 `same_enum`으로 95곳 통일 + 감사 위반 0 (8 시험) | 실표면 QA(P11)·사람 승인 이월 |
| P12 (T14 증거 digest) | [증거 digest drift](ARCHITECTURE_REVIEW.md): pin 50개를 실제 파일과 대조하는 harness(`scripts/digest_drift.py`) — 그대로 29 · **재확인 21** · 미확인 0 · 재확인 무효 0, 재확인은 `--method` 없이 기록 불가 (25 시험) | 실모델·실 vault 재확인은 이월 |
| P12 (T14 상태 주장) | [증거 산문의 상태 주장 재판정](ARCHITECTURE_REVIEW.md): “이 시험은 실패한다” 류 문장(test node 지정)을 현재 트리와 대조하는 감사(`scripts/audit_state_claims.py`) — 주장 4건 중 그대로 0 · **정정 붙임 4** · 낡음 0, 정정 없이 실제와 어긋나면 리뷰 실패 · 감사자 자신이 매 실행 **자기시험 17건**으로 자기 눈을 확인하고, 하한(mention 6≥1 여유 5 · 주장 4≥1 여유 3)을 **근거(`why`)·여유(`margin`)와 함께 artifact 로 기록**해 리뷰가 저장본과 새 측정을 대조 (이빨 22 시험 · 기계 검증 **14 checks PASS**) | 실모델·사람 승인 표면은 이월 |
| P12 (T14 harness 자기시험) | [공통 계약](ARCHITECTURE_REVIEW.md): 자기가 못 보면 조용히 통과하는 병을 여섯 harness 에서 공유 계약(`scripts/harness_contract.py`)으로 막는다 — 매 실행 자기 판독 재판정(digest 9 · 원장 11 · 상태 주장 17 · enum 5 · purge 6 · 표면 6건) + 탐지력 하한(여섯 harness 모두 **값 + 근거(`why`) + 여유(`margin`)** 를 artifact 에 기록) + **카나리아**가 각 하한을 눈멀게 한 사본으로 시험해 장식이 아님을 확인, 자기시험 부재·근거 없는 하한도 실패 (38 시험 · **14 checks PASS**) | 각 harness 의 실측 재검토는 이월 |
| P12 (T14 카나리아 종료 코드) | [판정과 진단을 함께 낸다](ARCHITECTURE_REVIEW.md): `--emit-json` 이 결과와 무관하게 exit 0 이던 이음매를 닫았다 — 장식 하한이 있으면 JSON 을 내면서도 exit 1, 리뷰는 0 이 아닌 종료 코드에서도 JSON 을 살려 **어느 harness 가 못 물었는지** 이름을 남기고, 모순(보고는 통과인데 스스로 실패)·종료 코드 없는 보고·합계 불일치를 실패로 잡는다 (7 시험 · **14 checks PASS**) | 하한을 내리는 판단은 사람 몫으로 이월 |
| P12 (T14 카나리아 이빨) | [카나리아를 리뷰가 지키게](ARCHITECTURE_REVIEW.md): “각 하한이 실제로 무는가” 를 보는 검사에 **스스로의 이빨**을 달았다 — 못 돌린 경우 · 장식 하한 · 정상 측정을 막는 하한 · 근거 없는 하한 · harness 0개 보기 · 마커 계산 · 저장소 카나리아 실물 확인 (7 시험 · **14 checks PASS**) | 하한을 내리는 판단은 사람 몫으로 이월 |
| P12 (T14 증거 게이트 CI 배선) | [판정·추이가 리뷰어에게 닿게](ARCHITECTURE_REVIEW.md): ① `ci.yml` 이 `docs/**`·`**.md` 를 무시해 **문서만 바꾼 PR 은 게이트를 건너뛰던 구멍**을 `evidence.yml` 이 그 여집합으로 맡아 닫았고(둘을 합치면 모든 변경이 덮인다) ② 게이트가 `--summary` 로 **markdown 요약**을 내면 두 워크플로가 `$GITHUB_STEP_SUMMARY` 와 PR 댓글(같은 댓글 갱신)로 보여 주고 artifact 2종을 올린다 — **빨간 실행도 요약을 남긴다**. 배선은 시험이 txt 수준으로 본다 (4 시험) | PR 댓글은 문서 변경 워크플로에서만 |
| P12 (T14 배포 산출물) | [`build` 를 NOT_RUN 에서 빼냈다](ARCHITECTURE_REVIEW.md): wheel·sdist 를 실제로 만들어(둘 다) **저장소 밖 신규 venv** 에 설치해 CLI·모듈·API·auth 를 돌리고, **sdist 왕복**(sdist 를 풀어 그 안에서 다시 빌드한 wheel 과 파일 목록 비교 — 664개 · 빠짐 0)과 **red 재현 둘** — ‘빠진 배포판’(module 하나를 빼고 RECORD 를 다시 쓴 wheel)은 검증기가 막고, ‘빠진 sdist’(같은 파일을 뺀 sdist)는 왕복이 **이름으로 지목**한다. red 재현이 없으면 “설치만 됐다” 와 구분할 수 없다. 게이트의 **로컬(`--tier full`) stage**(50초)이고 CI fast 는 이 층을 ‘보지 않은 층’ 으로 적는다(그 자리는 CI build job) (계약 시험 33 · **15 checks PASS**) | 카나리아는 50초 하한 때문에 이 층을 보지 않는다(이유를 §1.4 에 적음) · 왕복은 심은 종류의 결함만 증명 |
| P12 (T14 red 리허설) | [위반 0건인 감사에 red 를 심어 본다](ARCHITECTURE_REVIEW.md): 두 감사는 위반이 0건이라 green 이 “다 봤는데 깨끗하다” 인지 “한 번도 빨간을 본 적이 없다” 인지 실행으로 갈리지 않았다 — 저장소 밖 임시 트리에 **진짜 파일로 위반을 심고** 감사에 열린 `--root` 로 돌려 확인한다: 심은 트리 exit 1 + 파일 지목 · **경계 사례 8개를 같은 실행에 심어 오탐 0** · 대조군(허용 형태) 초록 · 없는 트리 차단. 리허설되지 않는 층은 **이유와 함께 선언**하고 게이트가 그 회계를 roster 와 대조한다 (이빨 14+11 시험 · **15 checks PASS**) | 경계 사례는 표본이라 allow-list 전체는 아님 |
| P12 (T14 층별 수치 추이) | [어제보다 얇아졌는가](ARCHITECTURE_REVIEW.md): 게이트가 층마다 **한 번의 실행으로 판정 + 수치**를 받아(이음매가 먼저 필요했다) 65개 수치를 저장소의 **기준**(사람이 마지막으로 승인한 파일)과 대조한다 — 줄어든 수를 먼저, 그대로인 수는 접어서. 이동은 판정이 아니고, 실패하는 것은 **수를 못 읽은 층**·**못 돌린 층**·**깨진 기준**이다. 기준은 `--record-baseline --method` 로만 갱신되고(날짜·무엇을 보고 승인했는지 함께) 게이트는 기준을 읽기만 한다 (이빨 19 시험) | 첫 실행은 “기준 없음” 이라고 말한다 |
| P12 (T14 이음매 전수) | [JSON 을 낸다고 통과는 아니다](ARCHITECTURE_REVIEW.md): 카나리아에서 고친 이음매(`--emit-json` 이 결과와 무관하게 exit 0)를 전수 확인해 **두 층이 같은 병을 앓고 있음**을 찾았다 — `digest_drift` 는 없는 artifact 에서 `--gate` exit 1 인데 `--emit-json` 은 exit 0(JSON 은 그대로 냈다), `audit_state_claims` 도 같다. 두 경로가 이제 같은 판정을 쓰고, 리뷰는 세 층(카나리아·digest·상태 주장)을 같은 규칙으로 읽는다 — 종료 코드 없는 보고는 판정이 아니고, 보고서는 통과인데 스스로 실패했다고 말하면 모순으로 실패한다 (이빨 9 시험) | — |
| P12 (T14 증거 게이트) | [여섯 층을 한 번에](ARCHITECTURE_REVIEW.md): 층마다 있는 게이트를 **도는 자리**가 사람의 기억뿐이었다 — `scripts/evidence_gate.py` 가 stage 마다 독립 process 로 돌려 종료 코드·소요 시간·**첫 실패 문장**을 모아 어느 층이 빨간지 이름으로 말한다(fast 8초 · full 17초). 없는 스크립트·없는 산출물·제한 시간 초과는 `unrun`(실패)이고, **tier 밖 층은 “보지 않은 층”** 으로 적는다(회귀 원장의 회차 산출물은 커밋되지 않는다). 게이트도 카나리아가 일곱 번째로 보고(하한이 장식이 아님을 확인), 리뷰는 14번째 검사로 stage roster·tier·자기시험 25건·하한 근거를 본다 (이빨 32 시험 · **14 checks PASS**) | `--tier full` 은 로컬 회차 필요, CI 는 fast |
| P12 (T14 회귀 원장) | [회귀 원장](evidence/T14_regression_ledger.md): 502 파일을 9 scope 로 나눠 **variant(seed 101·202 + 순서 뒤집은 3회)** 로 측정 — 결정적 11 · variant 민감 0 · 무소유 0, 중단 회차는 자동 재시도하되 횟수·로그를 남김 (32 시험 + 리뷰 계약) | scope 사이 순서·중단 회차 원인은 이월 |
| P12 (T14 격리) | [namespace 오염 제거](evidence/T14_namespace_isolation.md): import 시점 `sys.modules` purge를 미러 리허설에서만 하도록 조건화 + 감사·계약 시험 (5 시험) · 미러 리허설 PASS 17/FAIL 0 | 남은 순서 민감성은 별도 분리 |

상세 상태는 Acceptance Checklist가 관리한다. 기존 module PASS는 보존하지만 새로운 시험이나 실제 사용자 경로 PASS로 확대하지 않는다. 참고 문서의 과거 완료 표현보다 시험 범위와 근거가 우선한다.

## 6. 실행 책임

P01/P03/P06/P12는 주 담당자, P00/P08/P11은 통합 담당자가 책임진다. 나머지 역할은 Roadmap에 명시한다. 역할 배정은 별도 에이전트가 실행됐다는 뜻이 아니다. 공유 runtime/tool/config 파일은 통합 담당 한 명이 수정한다.

완료 상태는 문서·모듈·통합·최종 인수를 분리한다. 신규 인수 항목은 미실행으로 시작하고 실제 증거를 얻은 뒤에만 체크한다. 원래 작업의 수정·데이터·검증 이력을 되돌리지 않는다.

## 7. 원문과 참고 기록

[Master Prompt 원문](MASTER_PROMPT_V2_SOURCE.md), [원문 digest](SOURCE_MANIFEST.json), [코드 기준선 manifest](CURRENT_TREE_MANIFEST.json), [Envelope schema](contracts/record-envelope.schema.json), [Payload schema](contracts/record-entities.schema.json).

[요구사항 추적표](REQUIREMENTS_TRACEABILITY.md), [기존 보완 분석](SUPPLEMENT_ANALYSIS.md), [기존 산출물 보고](IMPLEMENTATION_REPORT.md), [기존 문서 검증 결과](VALIDATION_REPORT.md)는 당시 기록이다. v1.1 신규 요구의 통과 증거로 자동 재사용하지 않는다.
