---
title: "Experience 원본과 정책 lifecycle 분리"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Experience 원본과 정책 lifecycle 분리

상태: 구현 기준 제안. 헌법 변경이 아니며 런타임 반영은 미완료.

## Context / Problem

일반 Vault는 replace 가능하고 기존 trajectory는 SQLite다.

## Decision

새 cognitive 원본은 create-only files+Git; 기존 기록은 origin refs로 연결하며 해석/승격은 append 이벤트로 관리한다.

## Alternatives

DB 전면 교체 / 기존 snapshot을 그대로 experience로 간주

## Why / Trade-offs

migration 위험을 줄이지만 transaction publish와 두 저장층의 책임 구분이 필요하다.

## Constitution Compatibility

C7/C8/C9/C18

## Expected Impact

책임 경계가 명확해지고 기존 기능의 점진 전환이 가능하다. 성능 효과는 측정 전 미확정이다.

## Validation

T02/T09/T10/T12: crash·해석 분리·승격·rebuild

## Rollback

기존 DB 불변, 새 policy 비활성, 신규 원본은 보존
