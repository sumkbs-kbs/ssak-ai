---
title: "원문 분석 및 보완 사항"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# 원문 분석 및 보완 사항

## 기본 판단

원문은 Identity, Brain/Body 경계, 인간 최종 권한, 경험 기반 성장, 복잡성 통제의 기본 방침이 명확하다.
이를 바꿀 필요 없이 구현자가 서로 다르게 해석할 수 있는 경계를 계약으로 보완했다. 아래 항목은 새로운 헌법 원칙이 아니다.

| 보완 항목 | 원문에 남아 있던 구현 질문 | 이번 명세의 답 |
|---|---|---|
| 현재 코드 기준 | 어느 branch/문서 상태를 신뢰하는가 | 현재 폴더의 dirty tree를 읽고 파일 hash로 고정 |
| 상태/계보 | 서로 다른 저장소의 ID 연결 방법 | stable ID, typed references, legacy mapping |
| append-only | Git 이력만 있으면 충분한가 | create-only record, committed manifest, crash recovery |
| Brain 교체 | provider session과 state 소유권 | canonical Body records, capability adapter, 같은 frozen context |
| COMMIT | correctness와 hard constraints 검사의 경계 | 기계 predicate/attestation, semantic 판단은 Primary, LLM 호출 0 |
| authority | 만료/취소/중복 승인/위임 | scope·digest·revision 결박, 실행 직전 재검사 |
| stop rule | 의미 delta를 Body가 어떻게 판단하는가 | Brain delta 설명 + Body ID/예산/반복 검사; stop을 READY로 간주하지 않음 |
| 간단한 task | ACTION 뒤 관찰·학습까지 강제하는가 | 가벼운/비동기 관찰, 선택적 candidate 생성, 즉시 승격 금지 |
| external action | timeout이면 다시 실행해도 되는가 | receipt reconcile 우선, 비idempotent 결과 불명은 자동 재실행 금지 |
| 경험 학습 | policy가 언제 active가 되는가 | 후보/validation/activation 분리, CAS·version pin·rollback |
| 지식의 적용 | 높은 confidence가 적용 허가인가 | confidence/applicability/assurance 별도 타입 |
| benchmark | mature에 정답이 유출되는가 | train/validation/held-out 분리, 동일 brain/code, negative transfer |
| 보호의 실체 | 헌법 문서가 있으면 변경이 막히는가 | runtime·tool·filesystem·CI 경계 시험 필요; 문서 완료와 보호 구현 분리 |
| 개인정보와 역사 | append-only가 비밀 영구 보관을 뜻하는가 | 비밀은 원본 기록에서 제외; 예외적 삭제는 인간 결정 |
| 기존 기능 | 이름이 다르면 제거하는가 | adapter 재사용, REMOVE 근거 없으면 제거하지 않음 |

## 구현 상세 결정과 인간 결정의 구분

이번에 결정한 것은 namespace 제안, envelope, reference, 상태 전이, 작업 분해, 시험 조건이다. 원문이 허용한 engineering 범위다.
헌법 의미 변경, Human authority 축소, protected 해제, premise 변경, irreversible destructive migration, critical history 삭제는 원문대로 인간 결정이다.
실험 횟수·예산·표본 크기는 v1 제안값이며 실행 전에 manifest에 고정한다. 헌법의 일부로 굳히지 않는다.

## 직접 작업과 후속 책임

직접 완료: 헌법 추출, 27-section architecture, 22-entity data contract, protocol 구체화, 현재 코드 대조, gap/ADR, roadmap/checklist/schema.
주 에이전트 직접 구현 책임: P01 데이터 모델·계보, P03 보호 경계, P06 COMMIT, P12 최종 인수.
나머지 구현 담당은 이 계약을 기준으로 작업하며 통합 담당이 공유 파일 변경을 직렬화한다.
