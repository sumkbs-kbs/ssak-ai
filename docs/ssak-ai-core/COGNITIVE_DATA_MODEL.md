---
title: "Cognitive Data Model v1"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Cognitive Data Model v1

## 공통 envelope

모든 canonical record: `schema_version="1.0", id, entity_type, project_id, created_at, producer, references[], payload`.
ID는 namespace가 붙은 UUID, UTC RFC3339 시간 사용. project의 project_id는 자기 ID다.
reference는 `{relation, target_id, expected_type, target_revision?}`. `producer`는 human/brain/body/tool과 actor ID를 포함한다.
현재값을 바꾸는 update 대신 새 ID + supersedes reference를 사용한다. projection의 head pointer만 expected_revision CAS로 갱신한다.
불명 값은 UNKNOWN 또는 명시적 null_reason으로 나타낸다. null, empty list, UNKNOWN을 같은 값으로 취급하지 않는다.

## Entity별 필수 payload 및 연결

| Entity | 필수 payload | 주요 reference |
|---|---|---|
| Project | name, premise, human_partner_ref, protected_constraints | ConstitutionRule |
| Goal | statement, success_criteria, constraints, status | Project, parent Goal? |
| Evidence | kind, claim, provenance, time, digest, independence_group | source record? |
| BrainJudgment | current_judgment, grounds, assumptions, unknowns, alternatives, requests, confidence, confidence_reason, brain_version, context_digest | Goal, Evidence, previous Judgment? |
| Assumption | statement, validity_scope, status | Judgment, supporting Evidence |
| Unknown | question, category, materiality_reason, investigation_status | Goal, Judgment |
| Alternative | proposed_action, expected_outcome, tradeoffs, selection_reason | Judgment, Evidence |
| CognitiveRequest | type, purpose, target, expected_value, expected_decision_impact, args_digest, budget | Judgment |
| GovernanceDecision | disposition, changes, reason, limits, alternatives, feedback | Request, AuthorityProfile, Policy |
| Decision | selected_action, why_selected, why_not_selected, closure, expected_outcome, reopen_triggers, readiness | Goal, Judgment, Grounds, Unknowns, Alternatives, AuthorityProfile |
| Action | tool, args_digest, scope, risk_profile, idempotency_key, execution_status, receipt | Decision, GovernanceDecision |
| Observation | raw_measurement_or_handle, observed_at, method, source, status | Action, Evidence |
| Outcome | expected, observed, delta, status | Action, Observation |
| Experience | trigger, historical_refs, remaining_unknowns, future_attention | Goal, Judgment, Governance, Decision, Action, Outcome, Evidence |
| Pattern | statement, scope, counterexamples, independence_count | Experience[] |
| Hypothesis | claim, falsification_criteria, evaluation_plan | Pattern, Evidence |
| Strategy | operational_rule, applicability, exceptions, lifecycle | Hypothesis, validation Evidence |
| Principle | statement, scope, confidence_profile, applicability, lifecycle | Strategy, broader validation Evidence |
| Policy | target, rule, parameters, version, lifecycle, compatibility, rollback_version | Strategy/Principle, validation report |
| AuthorityProfile | independent grants, human ceiling ref, revision | Human-input Evidence |
| ConstitutionRule | principle_number, verbatim_text, source_digest, version | source Evidence |
| ArchitectureDecision | context, problem, decision, alternatives, tradeoffs, compatibility, validation, rollback | ConstitutionRule, Evidence |

추가 entity: ContextPackage, Interpretation, Reassessment, ValidationReport, PolicyActivation, BehaviorChangeTrace, Event, ExecutionReceipt.
이는 새 철학이 아니라 기존 요구의 이력·검증을 표현하는 record다.

## 타입별 불변 조건

- BrainJudgment의 ground는 Evidence ID를 참조한다. 자유문만 있는 justification은 거부한다.
- Observation에 meaning/current_interpretation을 혼합하지 않는다. 해석은 Interpretation에 기록한다.
- Experience의 일부 참조가 없으면 status=INCOMPLETE와 missing_references를 기록하고 성공 학습 입력으로 취급하지 않는다.
- Policy는 임의 Python/shell이 아니라 allowlist된 운영 설정이다. 헌법과 authority grant를 쓸 수 없다.
- ConfidenceProfile: evidence_strength/independence/replication/contradiction/context_coverage.
- ApplicabilityProfile: goal/context/constraint/environment/action match, exceptions, drift. 각각 MATCH/PARTIAL/MISMATCH/UNKNOWN.
- DecisionAssurance는 readiness check 결과 집합이다. 앞의 두 profile에서 단일 scalar를 합성하지 않는다.

## Lineage와 참조 정합성

Project→Goal→Decision→Action→Outcome→Experience→Pattern→Strategy→Principle→Policy를 복원할 수 있어야 한다.
모든 episode에 Principle 생성을 요구하지 않는다. 아직 생성되지 않은 것은 데이터 유실이 아니다.
쓰기 시 target 존재, expected_type, 동일 project 또는 명시적 shared-scope를 검증한다.
supersedes chain의 순환은 거부한다. Evidence 상호 참조 전체에 DAG를 강제하지 않는다.
검색 결과에 record ID와 revision을 반환하고 같은 문장의 중복 chunk를 독립 experience로 세지 않는다.

## 저장과 transaction 경계

v1은 episode transaction 단위 staging manifest를 사용한다. lock 아래 ID 충돌과 기대 revision을 확인하고 temp→flush→atomic rename을 거친다. Git commit 성공 후 committed manifest를 공개한다.
여러 파일 rename을 atomic transaction이라고 부르지 않는다. reader는 committed manifest에 열거된 record만 읽는다.
쓰기 완료/commit 미완료 crash는 recovery가 같은 transaction ID로 대조해 중복 publish를 막는다.
VaultEngine.write_note는 현재 같은 이름의 파일을 교체할 수 있으므로 그것만으로 append-only가 보장되지 않는다.
새 store는 create-only API와 ID uniqueness를 제공하고, Vault adapter 안에서 기존 lock과 Git을 재사용하는 설계를 검증한다.
고빈도 token stream을 매번 Git commit하지 않는다. cognitive record는 episode/decision 경계에서 저장하고 기존 실행 ledger와 연결한다.

## Schema evolution

v1 reader는 알 수 없는 major를 UNSUPPORTED_SCHEMA로 격리한다. minor 추가는 schema에 명시하며 미인식 payload를 실행하지 않는다.
backfill은 원본을 덮어쓰지 않고 source digest+mapping manifest+converted record를 별도 root에 만든다.
아래 JSON Schema는 공통 envelope와 참조 형식만의 구현 시작용 계약이다. entity 고유 검증·참조 해결·append-only·권한을 보장하지 않는다.
[record-envelope.schema.json](contracts/record-envelope.schema.json)을 P01에서 typed entity union으로 확장한다.
