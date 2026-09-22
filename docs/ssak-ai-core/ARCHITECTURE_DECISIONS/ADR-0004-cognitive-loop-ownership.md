---
title: "기존 CognitiveLoop와 신규 cognitive runtime의 ownership"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# 기존 CognitiveLoop와 신규 cognitive episode runtime의 ownership

상태: 구현 기준 확정(P08). 헌법 변경이 아니며 기존 runtime 파일은 수정하지 않는다.

## Context / Problem

P08 카드는 "기존 CognitiveLoop와의 ownership를 ADR로 확정한다"를 선행 조건으로 요구한다.
현재 tree에서 발견한 사실(2026-09-22, source head 79582ccd):

- `src/antigravity_k/engine/cognitive_loop.py` (534줄)에 `CognitiveLoop`이 존재한다.
  성격은 **Plan → Execute → Verify → Reflect → Adapt**이며 `verify_tool_result`, `reflect`,
  `auto_extract_memory`, 반복 실패 시 외부 Brain 위임 같은 prompt/검증 중심 기능을 담는다.
- 사용처는 `engine/orchestrator/agent.py`, `engine/tool_loop.py`, `engine/engine_context.py`,
  `api/routes/events.py` 등 **production 대화 경로**다.
- 신규 `src/antigravity_k/engine/cognitive/runtime.py`는 원문 §5의 cognitive 상태 전이
  (PREPARE→THINK→GOVERN/EXECUTE/FEEDBACK→TARGETED_RETHINK→COMMIT→ACTION→OBSERVE→EXPERIENCE)와
  canonical record 소유를 목표로 한다.

두 runtime을 같은 이름의 "인지 루프"로 취급하면 상태 의미·소유권·기록 주체가 섞인다. 이 중복은
헌법 원칙 4(Responsibility Boundary)와 원칙 23(Runtime Maturity) 위반 위험이 있다.

## Decision

1. **경계 분리.** legacy `CognitiveLoop`는 production 대화 경로의 분해·검증·성찰 엔진으로 그대로 둔다.
   canonical cognitive episode 계약(PREPARE~EXPERIENCE, readiness, receipt, Experience 선별)의
   소유자는 `engine/cognitive/runtime.py`다.
2. **opt-in.** 신규 runtime은 port(think/rethink/dispatch)가 주입될 때만 동작한다. 주입이 없으면
   아무 것도 dispatch하지 않는다. 기본 상태는 off이며 legacy 동작을 바꾸지 않는다.
3. **canonical 소유는 Body store.** episode 전이·Experience·receipt·decision은 canonical record로만
   남기고, legacy의 in-memory/EventBus 관찰값을 canonical state로 승격하지 않는다.
4. **이중 write 금지.** 한 요청을 신규 runtime과 legacy가 동시에 dispatch하지 않는다. 연결 시점에
   task 단위 flag로 한쪽만 활성화한다.
5. **migration은 사람 결정.** legacy history를 canonical store로 옮기거나 두 loop를 합치는 작업은
   destructive migration에 준해 P12의 human decision 절차로 분리한다.
6. `engine/agent_runtime.py`·`engine/orchestrator/*`·`config` 수정은 통합 담당 한 명이 반영한다.
   P08은 module + 실제 ToolExecutor 표면까지이며, 사용자 경로 연결은 P11 이월로 기록한다.

## Alternatives

- (a) legacy `CognitiveLoop`를 확장해 canonical 계약을 넣는다 → production 경로 회귀 위험과
  prompt/검증 관심사 혼합이 커진다. 헌법 원칙 4와 충돌한다.
- (b) legacy를 즉시 대체한다 → 사용자 표면 QA 없이 production 동작을 바꾸게 되어 원칙 23에 어긋난다.
- (c) 신규 runtime을 영구히 별도 실험 코드로 둔다 → 원칙 9(Experience Must Change Future Behavior)
  경로가 실제 행동에 닿지 못한다. P11 통합을 이월 조건으로 명시해 (c)를 피한다.

## Why / Trade-offs

경계를 분리하면 회귀 위험과 소유권 혼합을 줄이고 단계적 전환이 가능하다. 대신 두 runtime이
공존하는 동안 계측·문서가 이중으로 필요하고, legacy 관찰값과 canonical 기록의 관계를 명시적으로
관리해야 한다(성능 효과는 측정 전 미확정). 또한 연결 전까지 growth 평가(P10)는 fixture 수준에 머문다.

## Constitution Compatibility

원칙 4(Responsibility Boundary), 원칙 7(Historical Preservation), 원칙 8(Experience Ownership),
원칙 23(Runtime Maturity), 원칙 24(Ultimate Relationship). 헌법 문구 변경은 없다.

## Expected Impact

- 신규 cognitive 경로가 기존 사용자 경로를 깨지 않고 추가된다.
- canonical state/experience가 provider session에 종속되지 않는다(원칙 1·2와 정합).
- 이중 write 위험은 task 단위 flag와 P11 인수 항목으로 관리한다.

## Validation

T08/T09(최소 루프·Experience 선별, evidence/T08_T09_episode.md), T07(receipt 경계),
T11(사용자 표면 opt-in과 feature off 회귀, 이월), T14(feature off 회귀·manual QA, 이월).

## Rollback

주입된 port를 제거하면(`actions=None`, 구동 flag off) legacy 경로만 남는다. 새 canonical 기록은
삭제하지 않고 보존한다. destructive migration은 실행하지 않는다.
