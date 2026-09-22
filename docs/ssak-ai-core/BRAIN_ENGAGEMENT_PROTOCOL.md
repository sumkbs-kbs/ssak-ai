---
title: "Brain Engagement Protocol"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Brain Engagement Protocol

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 9. Primary Brain Contract

Primary Brain Response는 최소 다음 구조를 가진다.

```text
CURRENT_JUDGMENT

GROUNDS[]

ASSUMPTIONS[]

MATERIAL_UNKNOWNS[]

ALTERNATIVES[]

REQUESTED_COGNITIVE_ACTIONS[]

CONFIDENCE

CONFIDENCE_REASON
```

가능하면 Machine-readable schema를 정의한다.

JSON/Pydantic/dataclass 등 현재 Stack에 적합한 방식 사용.

단 Natural Language Reasoning 자유를 지나치게 제한하지 않는다.

Structured Envelope + Free-form reasoning 조합을 허용할 수 있다.

---


# 10. Cognitive Request

초기 Type:

```text
MORE_CONTEXT
MEMORY
TOOL
TEST_OR_SIMULATION
SECONDARY_BRAIN
EXTERNAL_EVIDENCE
```

각 Request는 가능하면:

```text
Purpose
Target
Expected Value
Expected Decision Impact
```

를 가진다.

---


# 11. Governance Contract

가능한 결과:

```text
APPROVE
APPROVE_WITH_LIMITS
RESHAPE
DEFER
DENY
```

검토 대상:

```text
Availability
Resource
Cost
Latency
Authority
Risk
Duplication
Loop Potential
Execution Feasibility
Alternative Operational Path
```

검토 대상이 아닌 것:

```text
"Brain conclusion is semantically correct?"
```

---


# 12. No Silent Governance

Brain 요청을 변경한 경우 반드시 다음을 Feedback한다.

```text
Original Request

Governance Decision

What Changed

Why Changed

Remaining Constraint

Available Alternative
```

Brain은 변경된 조건을 알고 Reasoning을 계속한다.

---


# 20. Authority Profile

단일 Autonomy Score 금지.

예:

```text
Reasoning Freedom
Memory Read Authority
Tool Read Authority
Tool Write Authority
Secondary Brain Authority
Code Modification Authority
External Action Authority
Resource Authority
Financial Authority
Constitutional Authority
```

각 권한은 독립적으로 증가·감소 가능하다.

---


# 21. Observation / Experience

Action 이후 반드시 Expected Outcome과 Observed Outcome을 연결한다.

```text
EXPECTED
↓
ACTION
↓
OBSERVED
↓
DELTA
```

Observation과 Interpretation은 분리한다.

---


## 실행 가능한 보완 명세


### Provider 독립 인터페이스

`think(context, request_id, capabilities) -> BrainJudgment | BrainFailure`.
`rethink(previous_judgment_id, feedback_ids, affected_ground_ids, context_delta) -> BrainJudgment | BrainFailure`.
입출력은 schema_version을 포함한다. 원래 판단은 수정하지 않고 새 판단의 `supersedes`로 연결한다.
이 프로토콜의 rethink는 제공자의 비공개 사고과정 접근을 요구하지 않는다. 공개 가능한 판단 근거·가정·수정 요약만 저장한다.
공통 Brain capability: structured_output, tool_request, context_limit, timeout, provider_model_version.

### 오류 및 호환성

모델 출력은 신뢰할 수 없는 입력이다. 알 수 없는 enum, 잘못된 ID, 다른 project reference, oversize 응답을 거부한다.
형식 오류는 1회 제한 repair 가능. repair에도 모델·비용·시간을 계상하고 실패하면 `BRAIN_PROTOCOL_ERROR`로 종료한다.
모델이 생성한 tool arguments는 실행 권한이 아니다. 검증된 CognitiveRequest를 Governance로 전달한다.
Provider fallback은 같은 frozen ContextPackage를 새 adapter에 전달하며 새 BrainJudgment ID를 만든다.
기존 plain-text 응답을 FACT나 READY로 포장하지 않는다. 미지원 경로는 legacy로 남기고 core 보장을 주장하지 않는다.

### Feedback envelope

`request_id, original_request_digest, governance_decision_id, what_changed, why_changed, remaining_constraints, available_alternatives, execution_receipt_id?`.
DENY/DEFER/RESHAPE도 반드시 feedback을 남긴다. reshape된 args는 별도 digest와 재권한 검사 대상이다.
Secondary 응답은 MODEL_JUDGMENT evidence로 Primary에 전달한다. 다수결을 최종 의사결정 권한으로 삼지 않는다.
Brain CONFIDENCE는 self-report이며 Knowledge ConfidenceProfile 및 DecisionAssurance와 별도로 둔다.
