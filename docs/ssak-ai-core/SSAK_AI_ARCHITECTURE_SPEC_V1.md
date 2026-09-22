---
title: "SSAK-AI Architecture Specification v1"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# SSAK-AI Architecture Specification v1

이 문서는 원문 헌법을 Engineering Contract로 구체화한다. 신규 runtime 구현 완료 선언이 아니다.
원문은 [MASTER_PROMPT_V2_SOURCE.md](MASTER_PROMPT_V2_SOURCE.md), 변경할 수 없는 원칙은 [헌법](SSAK_AI_CONSTITUTION.md)이 소유한다.

## 1. Purpose

교체 가능한 Brain과 지속 가능한 Body를 연결하고, 검증된 경험이 미래 행동을 바꿀 수 있게 한다. 기능 수 증가를 목표로 하지 않는다.

## 2. System Identity

Architecture Identity는 SSAK-AI. 기존 `antigravity_k` import/CLI/package는 유지한다. rename은 별도 migration이다.

## 3. Architectural Invariants

헌법 24개 원칙 전부를 적용한다. 불변 데이터와 가변 해석 분리, Primary semantic authority, Human protected authority, 현재 상태 우선, 검증 후 학습, 최소 복잡성이 구현 판정 기준이다.

## 4. Human / SSAK / Brain / Reality Boundary

Human은 premise와 최종 보호 권한, Brain은 의미 판단, Body는 state/evidence/resource/governance, Reality는 독립된 관찰 결과를 제공한다.
Body는 판단의 출처·실행 요건을 검증하지만 의미 결론을 별도 모델로 재심사하지 않는다.

## 5. Cognitive Operating Loop

[상태 전이 명세](COGNITIVE_OPERATING_LOOP.md)를 따른다. 단순 경로와 확장 경로가 하나의 episode/lineage 계약을 공유한다.

## 6. Context Architecture

[Context 명세](CONTEXT_AND_MEMORY.md). ContextBuilder를 message compressor 앞에 둔다. L0 제약은 압축으로 잃을 수 없다.

## 7. Brain Engagement Protocol

[Brain 명세](BRAIN_ENGAGEMENT_PROTOCOL.md). Structured envelope와 공개 가능한 설명을 결합한다. adapter는 판단을 생성하되 권한을 부여하지 않는다.

## 8. Cognitive Expansion

의사결정에 필요한 요청만 활성화한다. signature, delta, 시간·비용·횟수 예산으로 제한한다. Secondary는 conditional이다.

## 9. Governance

request 승인/제한/재구성/보류/거부를 구조화한다. 모든 변경을 Primary에게 feedback한다. deny도 경험의 일부다.

## 10. COMMIT

[Decision 명세](DECISION_AND_COMMIT.md). 9개 readiness check를 순수 함수로 구현한다. semantics judge 호출은 금지한다.

## 11. Decision Lifecycle

open → closed_for_action → material_trigger → reopened. 과거 trace는 append-only로 남긴다. action에 대한 closure는 truth의 확정이 아니다.

## 12. Action Governance

인자 digest·권한 revision에 결박된 실행 permit, guard, receipt를 사용한다. ToolExecutor를 우회하는 신규 executor를 만들지 않는다.

## 13. Authority

[권한 명세](GOVERNANCE_AND_AUTHORITY.md). dimension별 grant, scope, 만료, 취소, protected ceiling을 적용한다.

## 14. Evidence

[Evidence 명세](EVIDENCE_AND_UNCERTAINTY.md). 모델 판단과 관측을 별도 kind로 보관한다. source/version/time/digest를 추적한다.

## 15. Unknown / Uncertainty

UNKNOWN은 유효하다. unknown 미평가와 평가 후 없음은 다르다. materiality가 action을 바꾸는 경우에만 조사한다.

## 16. Conflict Handling

definition→context→time/version→measurement→source→execution→semantic 순서. unresolved 유지가 가능하다.

## 17. Observation

Expected와 Observed를 연결한다. 지연·부분 결과·관측 불능은 정상 상태이며 성공으로 치환하지 않는다.

## 18. Experience

[경험 명세](EXPERIENCE_AND_LEARNING.md). HistoricalCore와 Interpretation을 별도 ID로 둔다. Brain output만으로 episode 성공 경험을 만들지 않는다.

## 19. Knowledge Maturation

candidate/provisional/supported/established 및 challenged/scoped/revised/retired. confidence, applicability, decision assurance를 각각 기록한다.

## 20. Memory Architecture

Canonical Markdown records + explicit references를 원본으로 삼고 SQLite/검색/embedding은 rebuild 가능한 index/projection으로 사용한다.
기존 memory 저장은 legacy adapter로 보존하고 migration 확인 전 폐기하지 않는다.

## 21. Policy Learning

검증 report에 귀속된 후보를 versioned activation으로 승격한다. 실제 선택 변화와 outcome을 BehaviorChangeTrace에 연결한다.

## 22. Self-improvement

[자기개선 명세](SELF_IMPROVEMENT_POLICY.md). 후보 생성은 자동화할 수 있어도 헌법·권한 ceiling 변경은 불가하다.

## 23. Benchmark / Ablation

[평가 명세](BENCHMARK_AND_ABLATION.md). 같은 Brain/code/hardware/task 분포에서 Fresh/Mature를 비교한다. 실험 누수와 negative transfer를 점검한다.

## 24. Data Model

[데이터 계약](COGNITIVE_DATA_MODEL.md). 공통 envelope와 typed reference를 먼저 구현한다. schema 예시는 persistence 구현을 대신하지 않는다.

## 25. Failure Recovery

Persist intent → authorize → dispatch → receipt → observe → append experience 순서를 지킨다.
외부 성공 뒤 crash가 나면 receipt reconciliation을 먼저 한다. idempotency 지원 없는 외부 action은 결과 불명 상태에서 자동 재실행하지 않는다.
Git commit 실패와 파일 작성 성공을 분리해서 재시작 시 복구한다. durable marker가 없는 record는 검색/정책 적용에 노출하지 않는다.
index 장애는 검색 성능 저하로 표시하고 원본 손상으로 처리하지 않는다. canonical write 실패 후에는 후속 side effect를 시작하지 않는다.

## 26. Migration

feature flag 기본 off → isolated fixture → shadow(read-only, 외부 action 0) → project opt-in → 검증 후 default 제안.
기존 API response/CLI 계약을 유지한다. schema backfill은 별도 root에서 dry-run하고 구형 ID와 새 ID mapping을 보존한다.
rollback은 새 경로를 disable하고 마지막 검증된 policy로 복귀한다. 원본·migration manifest·새 역사 record는 삭제하지 않는다.

## 27. Anti-patterns

항상 multi-brain, 항상 대규모 recall, 항상 verifier, 과거 결론 강제, 모델 출력을 FACT 저장, 한 실패로 policy 변경, COMMIT semantic judge, 단일 risk/autonomy/confidence 점수는 금지한다.
FlyCortex/graph/meta-learning은 실증 전 core 필수 의존성이 아니다.

## 설계의 읽기 순서와 의존 방향

```text
Human intent / approved constraints
        ↓
Canonical records → ContextBuilder → BrainAdapter
        ↑                              ↓
Observation ← Action ← Readiness ← Governance / Judgment
        ↓
Experience → Candidate → Validation → Versioned Policy
                                     ↓
                              Future Context / Operations
```

권장 신규 namespace는 `src/antigravity_k/engine/cognitive/`이다. core model/readiness/store는 provider 및 UI를 import하지 않는다.
기존 engine와의 결합은 adapter/integration 한 곳에서 한다. 모델 인터페이스 역전으로 Brain 교체 후에도 같은 record를 읽는다.

## 원문 Mantra

헌법 §66의 문장들을 그대로 적용한다.
 최종 SSAK-AI Mantra

이 문장들은 Constitution과 Architecture 문서에도 포함하고 구현 판단의 기준으로 사용한다.

> **Brain is replaceable.**

> **The Brain thinks. SSAK-AI makes thinking effective.**

> **Do not compete with the Brain. Become better at leading the Brain.**

> **Reasoning belongs primarily to the Brain. Judgment governance belongs to SSAK-AI.**

> **Brains contribute judgments. SSAK-AI owns experience.**

> **Context is reconstructed, not accumulated.**

> **Minimum sufficient context, progressively expandable.**

> **Retrieve broadly, inject narrowly.**

> **Guide the question, not the answer.**

> **Expand cognition with purpose.**

> **Retry the weak reasoning, not the whole reasoning.**

> **No Material Cognitive Delta → Stop.**

> **COMMIT checks readiness, not correctness.**

> **Unknown is a valid state.**

> **Risk-aware, not risk-averse.**

> **Closed for action, open to learning.**

> **Do not rewrite history; append new understanding.**

> **The past informs the present, but the present decides.**

> **Experience proposes change; validation earns adoption.**

> **Experience must change future behavior.**

> **Complexity must be earned by evidence.**

> **Simple to start, designed to mature.**

> **Maturity may reduce runtime complexity.**

> **The most important connection of SSAK-AI is not to any Brain, but to its Human Partner.**

---
