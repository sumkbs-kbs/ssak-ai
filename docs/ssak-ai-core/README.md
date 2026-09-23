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
| P12 (T14) | [최종 Architecture Review](ARCHITECTURE_REVIEW.md): 헌법 24원칙(covered 15·partial 9·gap 0)·§63 12질문·§52 10질문 매핑 + 기계 검증 12 checks PASS(인용의 실재·추적, 증거 digest 의 drift, 증거 산문의 상태 주장까지 측정) · 고정 순서 전량 회귀 5 failed/7666 passed(cognitive 실패 0), 남은 5건은 커밋 이력·패키징·문서 기준선으로 분리 · 회귀가 찾은 enum identity 결함을 `same_enum`으로 95곳 통일 + 감사 위반 0 (8 시험) | 실표면 QA(P11)·build job(NOT_RUN)·사람 승인 이월 |
| P12 (T14 증거 digest) | [증거 digest drift](ARCHITECTURE_REVIEW.md): pin 50개를 실제 파일과 대조하는 harness(`scripts/digest_drift.py`) — 그대로 29 · **재확인 21** · 미확인 0 · 재확인 무효 0, 재확인은 `--method` 없이 기록 불가 (25 시험) | 실모델·실 vault 재확인은 이월 |
| P12 (T14 상태 주장) | [증거 산문의 상태 주장 재판정](ARCHITECTURE_REVIEW.md): “이 시험은 실패한다” 류 문장(test node 지정)을 현재 트리와 대조하는 감사(`scripts/audit_state_claims.py`) — 주장 4건 중 그대로 0 · **정정 붙임 4** · 낡음 0, 정정 없이 실제와 어긋나면 리뷰 실패 · 감사자 자신이 매 실행 **자기시험 17건**으로 자기 눈을 확인하고, node 지목 산문 하한(6줄)도 검사 (18 시험 · 기계 검증 **12 checks PASS**) | 실모델·사람 승인 표면은 이월 |
| P12 (T14 harness 자기시험) | [공통 계약](ARCHITECTURE_REVIEW.md): 자기가 못 보면 조용히 통과하는 병을 다섯 harness 에서 공유 계약(`scripts/harness_contract.py`)으로 막는다 — 매 실행 자기 판독 재판정(9·11·17·5·6건) + 탐지력 하한(pin 50 · 회차 21 · mention 6 · 스캔 파일 537 …), 자기시험 부재도 실패 (18 시험) | 각 harness 의 실측 재검토는 이월 |
| P12 (T14 회귀 원장) | [회귀 원장](evidence/T14_regression_ledger.md): 502 파일을 9 scope 로 나눠 **variant(seed 101·202 + 순서 뒤집은 3회)** 로 측정 — 결정적 11 · variant 민감 0 · 무소유 0, 중단 회차는 자동 재시도하되 횟수·로그를 남김 (32 시험 + 리뷰 계약) | scope 사이 순서·중단 회차 원인은 이월 |
| P12 (T14 격리) | [namespace 오염 제거](evidence/T14_namespace_isolation.md): import 시점 `sys.modules` purge를 미러 리허설에서만 하도록 조건화 + 감사·계약 시험 (5 시험) · 미러 리허설 PASS 17/FAIL 0 | 남은 순서 민감성은 별도 분리 |

상세 상태는 Acceptance Checklist가 관리한다. 기존 module PASS는 보존하지만 새로운 시험이나 실제 사용자 경로 PASS로 확대하지 않는다. 참고 문서의 과거 완료 표현보다 시험 범위와 근거가 우선한다.

## 6. 실행 책임

P01/P03/P06/P12는 주 담당자, P00/P08/P11은 통합 담당자가 책임진다. 나머지 역할은 Roadmap에 명시한다. 역할 배정은 별도 에이전트가 실행됐다는 뜻이 아니다. 공유 runtime/tool/config 파일은 통합 담당 한 명이 수정한다.

완료 상태는 문서·모듈·통합·최종 인수를 분리한다. 신규 인수 항목은 미실행으로 시작하고 실제 증거를 얻은 뒤에만 체크한다. 원래 작업의 수정·데이터·검증 이력을 되돌리지 않는다.

## 7. 원문과 참고 기록

[Master Prompt 원문](MASTER_PROMPT_V2_SOURCE.md), [원문 digest](SOURCE_MANIFEST.json), [코드 기준선 manifest](CURRENT_TREE_MANIFEST.json), [Envelope schema](contracts/record-envelope.schema.json), [Payload schema](contracts/record-entities.schema.json).

[요구사항 추적표](REQUIREMENTS_TRACEABILITY.md), [기존 보완 분석](SUPPLEMENT_ANALYSIS.md), [기존 산출물 보고](IMPLEMENTATION_REPORT.md), [기존 문서 검증 결과](VALIDATION_REPORT.md)는 당시 기록이다. v1.1 신규 요구의 통과 증거로 자동 재사용하지 않는다.
