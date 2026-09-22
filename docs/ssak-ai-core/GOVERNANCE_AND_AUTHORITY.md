---
title: "Governance and Authority"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Governance and Authority

원문 기본 방침을 그대로 보존한다. 아래 구현 보완은 헌법을 변경하지 않는 v1 Engineering Decision이다.

## 원문 계약

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


# 20. Authority Profile

단일 Autonomy Score 금지.

예:

```text
Reasoning Freedom
Memory Read Authority
Tool Read Authority
Tool Write Authority
Secondary Brain Authority
Code Modification Authority
External Action Authority
Resource Authority
Financial Authority
Constitutional Authority
```

각 권한은 독립적으로 증가·감소 가능하다.

---


# 60. Codex가 임의로 결정하면 안 되는 것

다음은 Human Decision을 요구한다.

```text
Constitution 의미 변경

Human Authority 축소

Protected Authority 해제

Project Premise 변경

Core Philosophy 변경

Irreversible destructive migration

Critical historical data deletion
```

그 외 구현 세부사항은 Constitution과 Architecture Spec 범위에서 주도적으로 진행한다.

---


# 61. 작업 중 사용자에게 불필요한 승인 반복 금지

매 작은 Refactor마다 승인을 요구하지 않는다.

Architecture와 Constitution이 이미 답을 제공한다면 스스로 진행한다.

Human Partner는 Micro-manager가 아니라 최종 Value/Authority Owner다.

---


## 실행 가능한 보완 명세


### 권한 계약

각 capability grant는 `subject, dimension, resource_scope, allowed_operations, constraints, granted_by, issued_at, expires_at, revision, revoked_at?`를 가진다.
AuthorityProfile은 이 grant의 집합이다. 단일 점수는 표시·판정의 근거가 아니다.
판정 순서: protected/human-only boundary → 명시적 deny/revocation → 유효한 grant → limits → 부족한 범위만 승인 요청.
과거 승인 재사용은 같은 principal·scope·operation·유효기간 안에서만 한다. 승인 항목에는 action digest를 묶는다.
learned policy는 human ceiling 아래의 실행 선택을 바꿀 수 있지만 grant를 생성하거나 ceiling을 높일 수 없다.
서브에이전트 위임도 parent 권한의 부분집합이며 만료·취소가 전파된다.

### 위험 재구성

예: 전체 repo 쓰기 → isolated worktree + 좁은 파일 범위 + diff 검사 + rollback checkpoint.
재구성이 tool write를 human-only 외부 publish로 바꾸지는 못한다. reshape 전후 profile과 감소한 risk dimension을 기록한다.
Capability가 없거나 권한이 부족하면 설명 있는 DEFER/DENY를 반환한다. 고위험이라는 이유 하나로 무조건 Human escalation하지 않는다.

### 보호의 실체

문서 hash 검사만으로 헌법 보호가 완료되지 않는다. runtime writer allowlist, 정책 target allowlist, filesystem boundary, CI diff gate를 함께 적용한다.
직접 파일쓰기·shell·plugin·self-evolution·migration 경로 모두 동일한 보호 경계를 지나야 한다.
v1 policy target은 context depth, retrieval limit, expansion budget처럼 정해진 운영 knob로 제한한다.
Constitution, Human authority, project premise, historical deletion은 해당 allowlist에 포함할 수 없다.
현재 이 문서는 목표 계약이다. 현 런타임에서 보호가 완성됐다는 증거는 아직 없다.
