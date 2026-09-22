---
title: "Context 재구성과 기존 projection 재사용"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Context 재구성과 기존 projection 재사용

상태: 구현 기준 제안. 헌법 변경이 아니며 런타임 반영은 미완료.

## Context / Problem

ContextShaper와 PersistentAgency projection이 이미 있다.

## Decision

새 ContextPackage builder가 기존 projection과 검색을 사용하고 최종 budget shaping을 수행한다.

## Alternatives

전체 history 요약 / 별도 memory stack 신설

## Why / Trade-offs

기존 코드 재사용과 L0/L1/L2/L3 경계 추적을 함께 얻는다.

## Constitution Compatibility

C1/C19/C21

## Expected Impact

책임 경계가 명확해지고 기존 기능의 점진 전환이 가능하다. 성능 효과는 측정 전 미확정이다.

## Validation

T03/T04: 제약 보존·handle 권한·Brain 교체

## Rollback

builder flag off, 원본 및 adapter 보존
