---
title: "Self Improvement Policy"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Self Improvement Policy

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 37. Self-Improvement

Self-improvement는 다음 순서로 진행한다.

```text
Observation
↓
Problem Diagnosis
↓
Improvement Hypothesis
↓
Evidence
↓
Candidate
↓
Sandbox
↓
Benchmark
↓
Regression
↓
Promotion
```

Experience 하나로 Core Architecture 자동 변경 금지.

---


# 44. FlyCortex / Executive Layer

현재 또는 향후 FlyCortex와 유사한 구조가 있다면 이를 Semantic Brain으로 만들지 않는다.

가능한 역할:

```text
State Coordination
Sparse Activation
Memory Gate
Context Gate
Resource Allocation
Execution Control
Policy Signal
```

모든 기능은 Benchmark/Ablation으로 가치를 증명한다.

---


# 50. Architecture Guardrails

가능한 경우 automated architecture tests 또는 validation scripts를 만든다.

예:

```text
Constitution file exists

Constitution version exists

Required invariants present

Learned policy cannot overwrite constitution store

Experience schema preserves observation/interpretation separation

Decision reassessment appends rather than overwrites

COMMIT implementation does not invoke semantic judge path

Protected Authority requires Human gate
```

모든 것을 완벽하게 자동 검사할 필요는 없다.

v1에서는 핵심 Invariant부터 시작한다.

---


# 51. Documentation Change Policy

Architecture 문서는 Code와 함께 Versioning한다.

다음 변경은 Documentation Update 없이 완료로 간주하지 않는다.

```text
New Cognitive Entity
New Governance Mode
Changed Authority Boundary
Changed Experience Lifecycle
Changed Decision Lifecycle
Changed Brain Responsibility
Changed Learning Path
```

---


# 52. Constitution Drift Detection

향후 Refactor/Feature 추가 시 다음 질문을 자동/수동 Review Checklist에 포함한다.

```text
Does this make Body a semantic Brain?

Does this reduce Brain replaceability?

Does this make memory dependent on conversation history?

Does this allow experience to dictate conclusions?

Does this bypass Human Constitutional Authority?

Does this create unbounded cognitive loops?

Does this make COMMIT re-evaluate semantic correctness?

Does this add complexity without measured value?

Does this prevent future learning?

Does this erase cognitive history?
```

YES가 있다면 Architecture Review가 필요하다.

---


# 56. Core와 Advanced 분리

Architecture 요소를 세 그룹으로 관리한다.

```text
CORE
현재 반드시 필요한 것

CONDITIONAL
특정 Trigger에서만 필요한 것

ADVANCED
Evidence가 쌓인 후 검토할 것
```

예:

CORE:

```text
State
Context
Primary Brain
Evidence
Decision
Action
Observation
Experience
Basic Governance
```

CONDITIONAL:

```text
Secondary Brain
Conflict Deep Review
Latent Reactivation
Risk Reshaping
```

ADVANCED:

```text
Multi-brain comparison
Causal discovery
Automated architectural self-improvement
Complex graph reasoning
Advanced meta-learning
```

Advanced를 v1 Core로 끌어오지 않는다.

---


# 57. Anti-pattern Checklist

다음 패턴을 발견하면 우선적으로 Architecture 위반 여부를 검토한다.

```text
Always call multiple brains

Always retrieve large memory

Always verify everything

Always ask human for high risk

Always summarize full history

Always reopen uncertain decisions

LLM output stored as fact

Experience directly converted to principle

Policy changed after one failure

Self-improvement edits constitution

Body merges all semantic judgments

COMMIT invokes another LLM judge

Risk collapsed into one score

Autonomy collapsed into one score

Confidence collapsed into one score
```

---


# 58. 구현 중 질문이 생겼을 때 판단 우선순위

```text
1. Human-approved Constitution

2. Architecture Invariants

3. Cognitive Continuity

4. Data Integrity / Authority / Safety

5. Experience → Learning Path

6. Runtime Correctness

7. Simplicity

8. Measured Performance

9. Convenience
```

---


# 59. Philosophy Conflict 처리

현재 코드 또는 기존 Design이 Constitution과 충돌하는 경우 즉시 제거하지 않는다.

다음 형식으로 기록한다.

```text
ARCHITECTURE CONFLICT

Current Behavior:

Constitutional Conflict:

Why it exists:

Risk of changing it:

Migration options:

Recommended path:

Temporary compatibility layer:

Validation:
```

가능하면 단계적으로 migration한다.

---


## 실행 가능한 보완 명세


Self-improvement는 후보 제안과 active 적용을 분리한다. 코드 수정 후보는 isolated worktree에서 시험하며 default runtime을 직접 덮어쓰지 않는다.
기존 evolution grade/cooldown은 후보 발생 trigger로 재사용 가능하나, promotion의 충분조건으로 사용하지 않는다.
헌법 충돌을 발견하면 `ARCHITECTURE CONFLICT`를 기록하고 현 기능은 호환 경로로 유지한다. 자동 삭제는 하지 않는다.
새 mechanism은 experimental로 시작하고 benchmark + ablation으로 이득이 재현되면 conditional/validated/core 승격을 검토한다.
실험 스위치를 끄면 기존 경로로 복귀해야 한다. 복귀가 역사 record를 삭제하거나 이미 발생한 action을 취소한 것으로 기록해서는 안 된다.
