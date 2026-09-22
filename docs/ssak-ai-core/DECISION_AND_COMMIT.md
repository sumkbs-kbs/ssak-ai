---
title: "Decision and Commit"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Decision and Commit

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 16. COMMIT Gate

COMMIT은 다음만 확인한다.

```text
Ground exists
Evidence provenance linked
Material Unknown explicit
Hard constraints satisfied
Residual risk manageable
Authority sufficient
Verification sufficient
Rollback sufficient where necessary
Action scope clear
```

COMMIT 결과:

```text
READY
READY_WITH_GUARDS
NOT_READY
```

NOT_READY는 Semantic Rejection이 아니다.

Blocking Condition을 반환한다.

---


# 17. Decision Closure

Closure는 다음 의미다.

> 현재 추가 Cognition보다 Action 또는 Reality Feedback의 Expected Value가 더 크다.

Decision Trace에는 최소:

```text
Decision
Context
Grounds
Alternatives
Why selected
Why not selected
Evidence
Unknowns
Risk
Authority
Expected Outcome
Reopen Triggers
```

를 남긴다.

---


# 18. Reopening

Material Trigger만 Reopen 가능.

```text
NEW_MATERIAL_EVIDENCE
UNEXPECTED_OUTCOME
MATERIAL_CONTRADICTION
CONTEXT_DRIFT
ASSUMPTION_FAILURE
RISK_CHANGE
AUTHORITY_CHANGE
HUMAN_REOPEN
```

다시 열 때:

> **Reopen the smallest justified scope first.**

---


## 실행 가능한 보완 명세


### 순수 readiness 함수

`check_readiness(decision, action, evidence_refs, authority_snapshot, verification_receipts) -> ReadinessResult`.
이 함수는 모델 호출, 지식 검색 확장, 의미 재판정, 외부 쓰기를 하지 않는다.
9개 check 각각 PASS/FAIL/UNKNOWN/N_A와 근거 reference를 반환한다. N_A에도 이유가 있어야 한다.
`Hard constraints satisfied`는 기계 검증 가능한 predicate 또는 명시적 human attest로 확인한다. 의미적 불확실성은 Primary에 돌려보낸다.
`Verification sufficient`는 action profile에 미리 정한 시험·관찰 요구의 충족 여부다. 항상 verifier LLM을 호출한다는 뜻이 아니다.
READY_WITH_GUARDS의 guards는 executor가 실제 강제할 수 있어야 한다. 문자열로만 존재하는 rollback은 충족이 아니다.

### 실행 전 freshness

ReadinessResult는 `(decision_revision, action_digest, authority_revision, state_revision, policy_version)`에 귀속된다.
권한 취소·args 변경·대상 변경 시 ACTION 직전에 재평가한다. COMMIT을 한 번 통과했다고 영구 허가하지 않는다.
COMMIT은 cognitive gate이며 `git commit`과 별개다.

### 재개

DecisionClosed는 append-only 사건이다. Reopened는 trigger evidence와 smallest_scope를 기록한 새 사건이다.
예전 DecisionTrace를 수정하지 않는다. 새 판단은 기존 결정을 대체하는 별도 ID로 연결한다.
Human reopen은 즉시 허용하되 원본 이력을 보존한다. 재개 중 이미 발생한 외부 행동을 되돌린 것으로 가정하지 않는다.
