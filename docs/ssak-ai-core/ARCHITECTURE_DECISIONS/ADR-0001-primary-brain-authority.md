---
title: "Primary Brain 권한과 순수 COMMIT"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Primary Brain 권한과 순수 COMMIT

상태: 구현 기준 제안. 헌법 변경이 아니며 런타임 반영은 미완료.

## Context / Problem

기존 CognitiveLoop/quality gate와 새로운 COMMIT이 혼동될 수 있다.

## Decision

Primary가 의미를 통합하고 COMMIT은 외부 호출 없는 readiness 함수로 둔다.

## Alternatives

기존 quality grader 재사용 / 새 semantic judge 추가

## Why / Trade-offs

기존 검증 도구를 evidence producer로는 유지할 수 있으나 COMMIT을 의미 심판으로 만들지 않는다.

## Constitution Compatibility

C2/C4/C14/C20

## Expected Impact

책임 경계가 명확해지고 기존 기능의 점진 전환이 가능하다. 성능 효과는 측정 전 미확정이다.

## Validation

T06: 모델 호출 0, 사전 정의 predicate와 receipt만 검사

## Rollback

신규 cognitive adapter off, 기존 동작 보존
