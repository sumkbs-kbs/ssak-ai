---
title: "Context and Memory"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Context and Memory

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 6. Context Package v1

Primary Brain에 전달할 기본 Context:

```text
GOAL

CURRENT_STATE

HARD_CONSTRAINTS

CRITICAL_EVIDENCE

MATERIAL_UNKNOWNS
```

조건부:

```text
EXPERIENCE_ADVISORY

CURRENT_DECISION_STATE

AVAILABLE_COGNITIVE_RESOURCES

CONTEXT_HANDLES
```

Context Builder는 Semantic Answer를 생성하는 Engine이 아니다.

> **Cognitive Workspace Constructor**

로 구현한다.

---


# 7. Context Reconstruction Hierarchy

```text
L0 PROJECT IDENTITY
- premise
- purpose
- human intent
- protected constraints

L1 CURRENT COGNITIVE STATE
- current goals
- decisions
- open questions
- risks

L2 RELEVANT HISTORY
- experience
- failures
- experiments
- decision rationale

L3 RAW EVIDENCE
- conversation
- logs
- commits
- tests
- documents
- tool outputs
```

Long-running Project의 Continuity가 Brain Context Window에 종속되어서는 안 된다.

---


# 8. Context Handles

예:

```text
H1 = relevant failure experience
H2 = previous decision trace
H3 = benchmark details
H4 = raw logs
H5 = historical discussion
```

Brain은 필요 시 Handle을 요청한다.

전체 자료를 처음부터 Context에 주입하지 않는다.

---


# 19. Action Governance

Action Profile:

```text
Reversibility
Blast Radius
Data/State Loss
External Impact
Security/Privacy
Authority Sensitivity
Verification
Rollback
Cost
Goal/Premise Impact
```

처리:

```text
AUTO_EXECUTE

EXECUTE_WITH_GUARDS

RISK_RESHAPE

HUMAN_APPROVAL

BLOCK
```

---


# 24. Experience Advisory

새 Brain에게 Experience 전체를 기본 제공하지 않는다.

최소 형태:

```text
PAST SIGNAL

ATTENTION POINT

CURRENT RELEVANCE

UNCERTAINTY

DETAIL HANDLE
```

과거 Conclusion을 현재 Conclusion으로 강제하지 않는다.

---


# 25. Progressive Experience Disclosure

```text
L0 SIGNAL
↓
L1 SUMMARY
↓
L2 DETAIL
↓
L3 RAW EVIDENCE
```

Default는 최소 Advisory다.

---


# 33. Memory Accessibility

필요하면:

```text
ACTIVE
WATCH
LATENT
DORMANT
ARCHIVED
```

상태를 지원한다.

중요하다는 이유만으로 항상 Active Context에 유지하지 않는다.

---


# 42. 처음부터 Graph Database를 요구하지 않는다

v1에서는 우선:

```text
Structured Record
+
Stable ID
+
Explicit Reference
```

로 구현 가능한지 확인한다.

Graph DB는 실제 필요가 증명된 후 도입한다.

---


# 43. Canonical Memory vs Retrieval Index

Canonical Cognitive Record와 Search/Embedding/Vector Index를 분리한다.

Embedding Index는 재생성 가능해야 한다.

Decision/Experience의 원본이 Vector Database 자체에 종속되지 않게 한다.

---


## 실행 가능한 보완 명세


### ContextBuilder 계약

`build(goal_id, state_revision, brain_capabilities, budget, policy_version) -> ContextPackage`.
필수 필드가 없는 경우 빈 문자열로 성공하지 않는다. `CONTEXT_INCOMPLETE`와 누락 ID를 반환한다.
읽기 순서: L0 protected constraints → L1 현 상태 → 결정 관련 L2 advisory → 필요한 L3 evidence.
검색은 넓게 수행해도 권한 필터는 검색 결과와 handle 조회 모두에 적용한다. 다른 project/owner의 자료는 주입하지 않는다.
필수 제약이 예산을 초과하면 조용히 버리지 않고 요청 범위를 줄이거나 지원 모델을 선택한다. 각 항목의 선택/제외 이유와 token 수를 저장한다.

### Handle 계약

`handle_id, project_id, owner_scope, record_id, record_revision, content_digest, disclosure_level, expires_at`를 가진다.
`resolve(handle, principal, max_bytes)`는 현재 권한과 digest를 확인한다. 만료·삭제·권한 부족은 서로 구분되는 결과다.
handle은 capability token이 아니다. handle을 알고 있다는 이유로 읽기 권한을 부여하지 않는다.
현재 Snapshot은 `(projection_version, last_event_sequence)`를 표시한다. stale projection은 canonical replay로 복원한다.

### 영속 경계

원본: versioned Markdown + YAML frontmatter와 명시적 reference. JSON은 wire format 및 재생성 가능한 projection에 사용한다.
기존 SQLite/Vector 저장소는 삭제하지 않는다. 신규 canonical record의 저장 원본과 검색 인덱스를 구분하는 adapter로 연결한다.
Brain 교체 시 provider session ID를 canonical ID로 사용하지 않는다. State/Experience/Decision은 Body 저장소에서 재구성한다.
원문에 없는 개인정보 무기한 보관 권한을 추론하지 않는다. 민감 원문은 Git에 넣지 않고 digest·비밀 저장소 handle만 보관한다.
역사 삭제가 필요한 예외는 인간 결정 사안으로 남기며 자동 삭제/자동 보존 정책 변경을 하지 않는다.
