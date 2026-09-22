---
title: "Benchmark and Ablation"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Benchmark and Ablation

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

# 38. Benchmark

처음부터 Benchmark Skeleton을 만든다.

가장 중요한 Benchmark:

```text
Same Brain
Same Code
Same Hardware
Same Task Distribution

Fresh SSAK-AI
vs
Mature SSAK-AI
```

측정:

```text
Task Success
Decision Stability
Repeated Failure
Context Size
Context Pollution
Brain Calls
Tool Calls
Retries
Tokens
Latency
Verification Count
Reopen Count
Recovery Speed
Risk Reshaping
Experience Reuse
Negative Transfer
```

---


# 39. Ablation

Mechanism의 가치를 증명한다.

```text
Without Context Builder
Without Experience Advisory
Without Targeted Re-reasoning
Without Experience
Without Risk Shaping
Without Governance Learning
```

효과 없는 복잡성은 제거할 수 있어야 한다.

---


# 54. 첫 Growth Demonstration을 반드시 만든다

Cognitive Core v1 완료 전, 최소 한 종류의 Experience-driven improvement를 실제로 증명한다.

추천 예:

### Context Selection Learning

초기:

```text
Context Policy v1
Rule-based
```

Experience 축적:

```text
Repeated context overload
Repeated missing evidence
```

Policy Candidate:

```text
Context Policy v2
```

Benchmark:

```text
v1 vs v2
```

승격 후:

```text
Future Task에서 실제 Context 구성 변경
```

즉 다음이 실제로 보여야 한다.

```text
EXPERIENCE
↓
POLICY CHANGE
↓
FUTURE BEHAVIOR CHANGE
```

단순 Database Record만 만들어서는 완료가 아니다.

---


# 55. Fresh vs Mature SSAK-AI Test

가능하면 같은 Brain Snapshot과 같은 Task를 사용한다.

```text
Fresh State:
No relevant accumulated Experience

Mature State:
Relevant Experience + validated Policy
```

그리고 비교한다.

```text
Outcome Quality
Brain Calls
Context Size
Tool Calls
Retry
Reopen
Failure Repetition
Latency
```

Mature가 더 많이 계산한다고 성공으로 보지 않는다.

---


## 실행 가능한 보완 명세


### 실행 manifest

매 실행에 source SHA + dirty-file digests, schema/policy/brain/prompt versions, hardware/runtime configuration, seed, task corpus digest, split IDs, cache mode, start/end time을 남긴다.
Fresh는 관련 경험 없음, Mature는 training split에서 축적한 경험 + validation 통과 policy만 사용한다.
두 실행은 분리 저장 root와 같은 brain snapshot을 사용한다. 순서 효과는 fresh→mature / mature→fresh 교대 및 반복으로 확인한다.
외부 live model의 고정이 불가능하면 reproducibility 제한을 보고한다. stub demo를 live 성능 증거로 사용하지 않는다.

### v1 사전 등록 게이트 제안

1. 결정적 fixture 12개: 정상 4, unknown/conflict 2, authority/reshape 2, recovery 2, context drift/negative transfer 2.
2. growth fixture는 train 2개 이상, validation 4개 이상, final held-out 6개 이상을 별도 생성한다. task ID 중복 0.
3. 결정적 safety/authority/history 위반 0. 같은 조건 재생 시 action dispatch 중복 0.
4. growth held-out에서 success count는 fresh 이상, 총 retry 또는 총 tool calls 중 사전 지정 metric 최소 1 감소.
5. negative-transfer fixture success 감소 0. 실측 latency/token은 전부 보고하며 작은 표본으로 일반 성능 우위를 선언하지 않는다.
6. live pilot는 동일 task paired trial을 최소 3회 실행하고 평균·중앙값·p95·분포를 보고한다. 확증 표본 크기는 pilot 변동성으로 별도 등록한다.

모든 metric에는 분모와 측정 구간을 기록한다. context pollution은 사전 라벨된 irrelevant injected tokens / total injected tokens로 정의하고 라벨이 없으면 N_A로 보고한다.
Decision stability는 새 material trigger 없이 바뀐 closed decision 비율, negative transfer는 무관/변경 context에서 mature 실패 증가로 측정한다.
Risk reshaping은 성공한 guarded action 수와 reshaping 비용·실패를 함께 보고한다.

### Ablation 실행

원문 6개 ablation을 하나씩 끈다. policy/version/task/code/hardware는 고정하고 삭제한 mechanism만 manifest에 표시한다.
권한·헌법 보호는 ablation 대상이 아니다. Without Risk Shaping에서도 기본 권한 검사는 유지한다.
계측 결과가 없는 ablation은 NOT_RUN으로 남긴다. 이 문서 작성 시 benchmark는 실행하지 않았다.
