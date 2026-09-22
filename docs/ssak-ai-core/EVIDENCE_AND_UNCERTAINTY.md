---
title: "Evidence and Uncertainty"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Evidence and Uncertainty

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 28. Confidence Profile

단일 `confidence=0.91`을 Core Representation으로 사용하지 않는다.

최소:

```text
Evidence Strength
Evidence Independence
Replication
Contradiction
Context Coverage
```

---


# 29. Applicability Profile

현재 Context마다 동적으로 평가한다.

```text
Goal Match
Context Match
Constraint Match
Environment Match
Action Match
Known Exception
Context Drift
```

값:

```text
MATCH
PARTIAL
MISMATCH
UNKNOWN
```

---


# 30. Evidence Types

Generic `reason`으로 모두 평탄화하지 않는다.

최소:

```text
FACT
OBSERVATION
EXPERIENCE
INFERENCE
PRINCIPLE
HYPOTHESIS
UNKNOWN
HUMAN_INPUT
MODEL_JUDGMENT
```

모든 중요한 Ground는 Provenance와 연결한다.

> **No justification without provenance.**

---


# 31. Evidence Conflict

Difference와 Conflict를 구분한다.

Conflict 조사 순서:

```text
Definition
Context
Version/Time
Measurement
Source
Execution
Semantic Interpretation
```

현재 Decision을 바꿀 가능성이 없으면 조사하지 않는다.

`UNRESOLVED` 허용.

---


# 32. Unknown

v1 기본:

```text
ACCEPTABLE
MATERIAL
BLOCKING
LATENT
```

핵심 질문:

> **If resolved differently, would we act differently?**

아니면 검증하지 않는다.

---


# 34. Failure Taxonomy

최소:

```text
CONTEXT_FAILURE
EVIDENCE_FAILURE
REASONING_FAILURE
GOVERNANCE_FAILURE
TOOL_FAILURE
EXECUTION_FAILURE
VERIFICATION_FAILURE
CLOSURE_FAILURE
MEMORY_FAILURE
AUTHORITY_FAILURE
```

Root Cause가 불명확하면 UNKNOWN 허용.

---


## 실행 가능한 보완 명세


### Provenance 계약

Evidence: `id, kind, claim, source_uri, source_version, content_digest, observed_at, ingested_at, producer, independence_group, project_id, access_scope`.
서로 같은 원자료를 인용한 출처 10개는 독립 근거 10개가 아니다. `independence_group` 미확정은 UNKNOWN이다.
FACT는 모델이 선언한다고 부여되지 않는다. 승격 근거와 verifier receipt를 기록한다. 요약은 원본을 지우지 않는다.
시간은 UTC timezone-aware로 저장하고 UI에서 KST로 표시한다. 관찰 시간과 수집 시간을 분리한다.

### Unknown 및 conflict 계약

Unknown: `question, category, affected_decision_ids, potential_action_change, investigation_cost, disposition_reason`.
빈 unknown 목록은 확인 결과 없음을 뜻하며, 미평가와 구분하는 `unknowns_assessed`가 필요하다.
BLOCKING unknown이 남으면 관련 action만 차단한다. ACCEPTABLE/MATERIAL/LATENT를 일괄 금지하지 않는다.
Conflict: `evidence_ids, conflict_dimension, decision_impact, status, resolution_record_id?`.
semantic 충돌은 Primary에 재해석 요청한다. Body는 시각/버전/스키마 불일치와 자료 누락을 검출한다.

### 실패 평가

OutcomeEvaluation, DecisionEvaluation, ExecutionEvaluation을 분리한다. 결과가 좋다는 사실만으로 판단이 좋았다고 추론하지 않는다.
root cause=UNKNOWN이면 확정 원인 기반 정책으로 승격하지 않는다. 관련 증거가 늘면 Reassessment를 append한다.
