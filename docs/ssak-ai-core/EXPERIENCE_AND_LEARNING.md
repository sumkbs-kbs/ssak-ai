---
title: "Experience and Learning"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Experience and Learning

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

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


# 22. Experience Record

최소 Schema:

```text
Experience ID

Context

Trigger

Brain Judgment

Grounds

Assumptions

Unknowns

SSAK Governance

Action

Expected Outcome

Observed Outcome

Delta

Outcome Evaluation

Decision Evaluation

Execution Evaluation

Current Interpretation

Remaining Unknowns

Future Attention

Evidence Provenance
```

---


# 23. Immutable Historical Core

Experience에는 두 Layer가 있다.

```text
HISTORICAL CORE
- Context
- Judgment
- Action
- Observation
- Evidence

INTERPRETATION LAYER
- Current meaning
- Hypothesis
- Confidence
- applicability
```

Historical Core는 가능한 한 Append-only로 유지한다.

Interpretation은 versioning한다.

---


# 26. Experience → Knowledge

```text
EXPERIENCE
↓
OBSERVATION
↓
PATTERN CANDIDATE
↓
HYPOTHESIS
↓
STRATEGY CANDIDATE
↓
CONTROLLED VALIDATION
↓
SUPPORTED STRATEGY
↓
PRINCIPLE CANDIDATE
↓
BROADER VALIDATION
↓
PRINCIPLE
```

자동으로 Experience 하나를 Principle로 승격하지 않는다.

---


# 27. Knowledge Lifecycle

```text
CANDIDATE
PROVISIONAL
SUPPORTED
ESTABLISHED

CHALLENGED
SCOPED
REVISED
RETIRED
```

Retired Knowledge도 삭제하지 않는다.

---


# 35. Policy Learning Architecture

반드시 다음 Interface가 존재해야 한다.

```text
Experience Evaluator

Pattern Candidate Builder

Policy Candidate Store

Validation Interface

Benchmark Interface

Policy Versioning

Policy Promotion

Policy Rollback

Policy Retirement

Behavior Change Trace
```

초기에는 Human-assisted여도 괜찮다.

그러나 향후 자동화 가능하도록 분리한다.

---


# 36. Experience가 개선해야 할 영역

최소:

```text
Context Selection
Context Depth
Experience Retrieval
Brain Engagement Depth
Cognitive Expansion
Tool Selection
Secondary Brain Usage
Conflict Investigation
Unknown Investigation
Closure Timing
Risk Shaping
Verification Depth
Action Governance
Authority Delegation
```

---


## 실행 가능한 보완 명세


### Episode와 해석 분리

`ExperienceCore`는 context/judgment/governance/decision/action/observation/outcome의 ID를 연결한 불변 기록이다.
`Interpretation`은 별도 `experience_id, revision, supersedes, evidence_ids, author, meaning, confidence_profile, applicability_profile`을 가진다.
관측이 늦거나 불명확하면 `outcome_status=PENDING|UNKNOWN`으로 저장한다. 이를 성공 경험으로 학습하지 않는다.
후속 관측은 새 Observation과 ExperienceSupplement로 연결하고 기존 core bytes를 바꾸지 않는다.

### 학습 인터페이스

Evaluator.evaluate(episode) → 세 평가 / PatternBuilder.propose(evaluations) → candidate.
CandidateStore.append(candidate) / Validator.validate(candidate, frozen_split) → ValidationReport.
PolicyStore.promote(candidate_id, report_id, expected_active_version) → 새 activation event.
rollback(target_version, reason) 및 retire(version, reason)는 append 사건이며 과거 policy를 지우지 않는다.
Promotion은 compare-and-swap으로 동시 승격을 직렬화한다. 실행 중 episode는 시작 policy version을 pin하고 권한 취소만 즉시 반영한다.

### 승격 기본값

최초 구현은 human-assisted candidate 작성 가능. 검증 없이 active policy를 편집하는 경로는 금지한다.
학습·검증·최종 평가 task IDs는 분리한다. 중복 원자료에서 파생된 episode를 독립 replication으로 세지 않는다.
최소 2개 독립 episode + 사전 등록된 held-out 검증 통과는 v1의 후보 승격 시작 조건이지 일반적 인과 증명은 아니다.
숫자·비열등성 폭·대상 범위는 BenchmarkSpec에 실행 전에 고정한다. 실패한 뒤 기준을 완화하면 새 실험 ID를 만든다.

### 실제 성장 데모

fixture 문제: 도구 결과의 필수 config evidence가 얕은 context에 빠져 read tool 재시도가 생긴다.
독립 학습 episode에서 누락을 관찰 → 특정 goal/environment에서 해당 evidence handle을 한 단계 더 열라는 policy candidate → 별도 validation → activation.
fresh/mature는 동일 brain/code/task를 사용하고, mature에서만 검증된 policy와 관련 advisory를 제공한다.
증거: before/after context selection, policy_version, tool_calls/retries, 성공 여부, negative-transfer task 결과.
`BehaviorChangeTrace`는 policy 없이 같은 입력에 대한 shadow 선택과 실제 선택 차이를 기록한다.
정답 문자열을 policy에 넣거나 테스트 정답을 학습 저장소에 주입하는 데모는 무효다.
