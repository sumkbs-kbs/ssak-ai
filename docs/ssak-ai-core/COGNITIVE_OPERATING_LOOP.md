---
title: "Cognitive Operating Loop"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Cognitive Operating Loop

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 5. Cognitive Operating Loop

Target Runtime Loop:

```text
PREPARE
↓
THINK
↓
COGNITIVE REQUEST
↓
GOVERN
↓
EXECUTE
↓
FEEDBACK
↓
TARGETED RE-THINK
↓
COMMIT
↓
ACTION
↓
OBSERVE
↓
EXPERIENCE
↓
LEARN
↓
FUTURE BEHAVIOR CHANGE
```

모든 Task에서 전 단계를 강제로 실행하지 않는다.

```text
Simple Task
PREPARE → THINK → COMMIT → ACTION
```

도 정상이다.

Architecture Principle:

> **Highly Connected, Sparsely Activated.**

---


# 13. Intentional Cognitive Expansion

SSAK-AI는 필요하면 Proactive Expansion을 제안할 수 있다.

예:

```text
Relevant Experience
Missing Evidence
Counterexample
Secondary Specialist
Relevant Tool
Past Failure
Context mismatch
```

그러나 Brain Conclusion을 암시하지 않는다.

---


# 14. Cognitive Expansion Stop Conditions

다음 변화가 없다면 Expansion을 중단한다.

```text
Judgment Delta
Ground Delta
Alternative Delta
Unknown Delta
Risk Delta
Action Delta
```

> **No Material Cognitive Delta → Stop.**

Request Signature를 통해 반복 사고도 감지한다.

---


# 15. Secondary Brain Architecture

기본적으로 하나의 Primary Brain이 Lead Thinker다.

Secondary Brain은 필요 시:

```text
Specialist
Critic
Alternative Interpreter
```

로 사용한다.

Multi-agent Debate를 기본 Mode로 만들지 않는다.

최종 Semantic Integration은 Primary Brain이 수행한다.

---


## 실행 가능한 보완 명세


### 상태와 전이

각 전이는 `episode_id`, `event_id`, `sequence`, `caused_by`, `state_revision`을 가진다. 실행 상태와 인식 상태를 혼합하지 않는다.

| 상태 | 진입 조건 | 성공 전이 | 실패/대기 전이 |
|---|---|---|---|
| PREPARE | Goal 및 현재 revision 확인 | THINK | BLOCKED_CONTEXT |
| THINK | 유효한 ContextPackage | GOVERN 또는 COMMIT | BRAIN_FAILED |
| GOVERN | 요청 envelope 유효 | EXECUTE / FEEDBACK | DEFERRED / FEEDBACK(DENY) |
| EXECUTE | 요청 단위 권한·예산 재확인 | FEEDBACK | FEEDBACK(실패 또는 결과 불명) |
| FEEDBACK | 요청별 결정·결과 존재 | TARGETED_RETHINK | WAITING_RESOURCE |
| TARGETED_RETHINK | 변경된 grounds/unknown IDs 명시 | GOVERN / COMMIT | BRAIN_FAILED |
| COMMIT | 고정된 decision/action digest | ACTION | BLOCKED_READINESS |
| ACTION | 최신 권한·대상 revision 일치 | OBSERVE | ACTION_OUTCOME_UNKNOWN |
| OBSERVE | receipt 또는 관측 계획 | EXPERIENCE | OBSERVATION_PENDING |
| EXPERIENCE | 기록 또는 pending 관찰의 명시 | LEARN 후보 큐 또는 종료 | PERSISTENCE_FAILED |
| LEARN | 평가 가능한 episode | 후보 생성 / 변화 없음 | VALIDATION_PENDING |

`BLOCKED_*`, `FAILED`, `CANCELLED`, `WAITING_*`는 다른 의미다. 취소도 이벤트를 남긴다. 취소 당시 실행 중이던 외부 행동을 성공/실패로 추측하지 않는다.
Simple Task는 확장 경로를 생략한다. ACTION 이후 관찰은 가벼운 receipt 또는 비동기로 기록할 수 있으며, 매 요청마다 학습·승격하지 않는다.
읽기 도구도 network/cost/privacy 측면에서는 행동이므로 EXECUTE에서 권한 검사를 생략하지 않는다.

### 반복 제한

v1 기본 설정 제안: expansion_rounds=3, 동일 signature 재요청=1회, schema repair=1회. 이는 헌법이 아닌 task별 조정 가능한 예산이다.
Signature는 request type + 정규화 target/args + 목적 + evidence revision으로 계산한다. 새 evidence revision은 재시도 사유로 기록한다.
Body는 ID·버전 변화, 예산, 반복을 비교한다. 의미 변화의 크기는 Primary Brain의 delta 설명에 맡기며 별도 LLM 심판을 두지 않는다.
Stop은 강제 READY가 아니다. readiness 부족이면 BLOCKED 또는 안전한 축소 Action으로 끝낸다.
