---
title: "Master Prompt 요구사항 추적표"
date: 2026-09-22
version: "1.0"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Master Prompt 요구사항 추적표

원문 §0~67을 빠짐없이 주 소유 명세에 대응한다. 이는 **문서 커버리지**이며 runtime 충족 증거는 ACCEPTANCE_CHECKLIST에 별도로 기록한다. FINAL OBJECTIVE는 헌법·아키텍처·P12 최종 인수 전체에 적용한다.

| 원문 | 요구 | 주 소유 명세 |
|---|---|---|
| §0 | 절대적 작업 순서 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §1 | 프로젝트 Identity | [SSAK_AI_CONSTITUTION.md](SSAK_AI_CONSTITUTION.md) |
| §2 | 가장 먼저 생성할 영구 문서 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §3 | SSAK_AI_CONSTITUTION.md — 반드시 실제로 작성할 내용 | [SSAK_AI_CONSTITUTION.md](SSAK_AI_CONSTITUTION.md) |
| §4 | SSAK_AI_ARCHITECTURE_SPEC_V1.md — 실제 작성 내용 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §5 | Cognitive Operating Loop | [COGNITIVE_OPERATING_LOOP.md](COGNITIVE_OPERATING_LOOP.md) |
| §6 | Context Package v1 | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §7 | Context Reconstruction Hierarchy | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §8 | Context Handles | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §9 | Primary Brain Contract | [BRAIN_ENGAGEMENT_PROTOCOL.md](BRAIN_ENGAGEMENT_PROTOCOL.md) |
| §10 | Cognitive Request | [BRAIN_ENGAGEMENT_PROTOCOL.md](BRAIN_ENGAGEMENT_PROTOCOL.md) |
| §11 | Governance Contract | [BRAIN_ENGAGEMENT_PROTOCOL.md](BRAIN_ENGAGEMENT_PROTOCOL.md) |
| §12 | No Silent Governance | [BRAIN_ENGAGEMENT_PROTOCOL.md](BRAIN_ENGAGEMENT_PROTOCOL.md) |
| §13 | Intentional Cognitive Expansion | [COGNITIVE_OPERATING_LOOP.md](COGNITIVE_OPERATING_LOOP.md) |
| §14 | Cognitive Expansion Stop Conditions | [COGNITIVE_OPERATING_LOOP.md](COGNITIVE_OPERATING_LOOP.md) |
| §15 | Secondary Brain Architecture | [COGNITIVE_OPERATING_LOOP.md](COGNITIVE_OPERATING_LOOP.md) |
| §16 | COMMIT Gate | [DECISION_AND_COMMIT.md](DECISION_AND_COMMIT.md) |
| §17 | Decision Closure | [DECISION_AND_COMMIT.md](DECISION_AND_COMMIT.md) |
| §18 | Reopening | [DECISION_AND_COMMIT.md](DECISION_AND_COMMIT.md) |
| §19 | Action Governance | [GOVERNANCE_AND_AUTHORITY.md](GOVERNANCE_AND_AUTHORITY.md) |
| §20 | Authority Profile | [GOVERNANCE_AND_AUTHORITY.md](GOVERNANCE_AND_AUTHORITY.md) |
| §21 | Observation / Experience | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §22 | Experience Record | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §23 | Immutable Historical Core | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §24 | Experience Advisory | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §25 | Progressive Experience Disclosure | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §26 | Experience → Knowledge | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §27 | Knowledge Lifecycle | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §28 | Confidence Profile | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §29 | Applicability Profile | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §30 | Evidence Types | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §31 | Evidence Conflict | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §32 | Unknown | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §33 | Memory Accessibility | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §34 | Failure Taxonomy | [EVIDENCE_AND_UNCERTAINTY.md](EVIDENCE_AND_UNCERTAINTY.md) |
| §35 | Policy Learning Architecture | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §36 | Experience가 개선해야 할 영역 | [EXPERIENCE_AND_LEARNING.md](EXPERIENCE_AND_LEARNING.md) |
| §37 | Self-Improvement | [SELF_IMPROVEMENT_POLICY.md](SELF_IMPROVEMENT_POLICY.md) |
| §38 | Benchmark | [BENCHMARK_AND_ABLATION.md](BENCHMARK_AND_ABLATION.md) |
| §39 | Ablation | [BENCHMARK_AND_ABLATION.md](BENCHMARK_AND_ABLATION.md) |
| §40 | Core Cognitive Data Model | [COGNITIVE_DATA_MODEL.md](COGNITIVE_DATA_MODEL.md) |
| §41 | Lineage | [COGNITIVE_DATA_MODEL.md](COGNITIVE_DATA_MODEL.md) |
| §42 | 처음부터 Graph Database를 요구하지 않는다 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §43 | Canonical Memory vs Retrieval Index | [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md) |
| §44 | FlyCortex / Executive Layer | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §45 | 기존 Repository 분석 | [SSAK_AI_GAP_ANALYSIS_V1.md](SSAK_AI_GAP_ANALYSIS_V1.md) |
| §46 | KEEP / MODIFY / REFACTOR / REMOVE / NEW / DEFER | [SSAK_AI_GAP_ANALYSIS_V1.md](SSAK_AI_GAP_ANALYSIS_V1.md) |
| §47 | Gap Analysis 문서 | [SSAK_AI_GAP_ANALYSIS_V1.md](SSAK_AI_GAP_ANALYSIS_V1.md) |
| §48 | Architecture Compatibility Matrix | [SSAK_AI_GAP_ANALYSIS_V1.md](SSAK_AI_GAP_ANALYSIS_V1.md) |
| §49 | Architecture Decision Records | [ARCHITECTURE_DECISIONS/ADR-0001-primary-brain-authority.md](ARCHITECTURE_DECISIONS/ADR-0001-primary-brain-authority.md) |
| §50 | Architecture Guardrails | [SELF_IMPROVEMENT_POLICY.md](SELF_IMPROVEMENT_POLICY.md) |
| §51 | Documentation Change Policy | [SELF_IMPROVEMENT_POLICY.md](SELF_IMPROVEMENT_POLICY.md) |
| §52 | Constitution Drift Detection | [SELF_IMPROVEMENT_POLICY.md](SELF_IMPROVEMENT_POLICY.md), 답변: [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) §4 |
| §53 | v1 구현 순서 | [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) |
| §54 | 첫 Growth Demonstration을 반드시 만든다 | [BENCHMARK_AND_ABLATION.md](BENCHMARK_AND_ABLATION.md) |
| §55 | Fresh vs Mature SSAK-AI Test | [BENCHMARK_AND_ABLATION.md](BENCHMARK_AND_ABLATION.md) |
| §56 | Core와 Advanced 분리 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §57 | Anti-pattern Checklist | [SELF_IMPROVEMENT_POLICY.md](SELF_IMPROVEMENT_POLICY.md) |
| §58 | 구현 중 질문이 생겼을 때 판단 우선순위 | [SSAK_AI_CONSTITUTION.md](SSAK_AI_CONSTITUTION.md) |
| §59 | Philosophy Conflict 처리 | [SSAK_AI_GAP_ANALYSIS_V1.md](SSAK_AI_GAP_ANALYSIS_V1.md) |
| §60 | Codex가 임의로 결정하면 안 되는 것 | [SSAK_AI_CONSTITUTION.md](SSAK_AI_CONSTITUTION.md) |
| §61 | 작업 중 사용자에게 불필요한 승인 반복 금지 | [GOVERNANCE_AND_AUTHORITY.md](GOVERNANCE_AND_AUTHORITY.md) |
| §62 | 최종 Definition of Done — Cognitive Core v1 | [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md) |
| §63 | 최종 Architecture Review 질문 | [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) (질문별 답·근거·한계), [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md) |
| §64 | 구현 결과 보고 형식 | [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) |
| §65 | 가장 중요한 구현 철학 | [SSAK_AI_ARCHITECTURE_SPEC_V1.md](SSAK_AI_ARCHITECTURE_SPEC_V1.md) |
| §66 | 최종 SSAK-AI Mantra | [SSAK_AI_CONSTITUTION.md](SSAK_AI_CONSTITUTION.md) |
| §67 | 지금부터 실제로 수행할 첫 번째 작업 | [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) |
