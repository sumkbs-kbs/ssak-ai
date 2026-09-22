"""tests/cognitive 공용 fixture helper. 시험 파일이 아니므로 pytest가 수집하지 않는다."""

from __future__ import annotations

from datetime import UTC, datetime

from antigravity_k.engine.cognitive.models import (
    BrainJudgmentPayload,
    CheckStatus,
    ConfidenceProfile,
    ConstitutionRulePayload,
    DecisionAssurance,
    DecisionPayload,
    EvidencePayload,
    ExperiencePayload,
    GoalPayload,
    InterpretationPayload,
    Producer,
    ProducerKind,
    ProjectPayload,
    Provenance,
    ReadinessCheck,
    ReadinessCheckResult,
    ReadinessVerdict,
    Record,
    UnknownPayload,
)
from antigravity_k.engine.cognitive.references import REL_GROUND, EntityType, Reference

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
PRODUCER = Producer(kind=ProducerKind.BODY, actor_id="body:test")


def confidence() -> ConfidenceProfile:
    return ConfidenceProfile(
        evidence_strength=0.5, independence=0.5, replication=0.5, contradiction=0.1, context_coverage=0.5
    )


def assurance() -> DecisionAssurance:
    return DecisionAssurance(
        verdict=ReadinessVerdict.READY,
        check_results=tuple(
            ReadinessCheckResult(check=check, status=CheckStatus.PASS, reason="fixture") for check in ReadinessCheck
        ),
        decision_revision=1,
        state_revision=1,
    )


def build_evidence(project_id: str, *, claim: str = "pytest 127 passed", kind: str = "OBSERVATION") -> Record:
    return Record.create(
        entity_type=EntityType.EVIDENCE,
        project_id=project_id,
        producer=PRODUCER,
        payload=EvidencePayload(
            kind=kind,
            claim=claim,
            provenance=Provenance(
                source_uri="tests/cognitive/_fixtures.py",
                content_digest="sha256:" + "0" * 64,
                observed_at=NOW,
                ingested_at=NOW,
            ),
            time=NOW,
            digest="sha256:" + "1" * 64,
            independence_group="fixture",
        ),
        created_at=NOW,
    )


def build_goal(project_id: str, *, statement: str = "canonical store 구현") -> Record:
    return Record.create(
        entity_type=EntityType.GOAL,
        project_id=project_id,
        producer=PRODUCER,
        payload=GoalPayload(statement=statement, success_criteria=("T02 통과",), status="ACTIVE"),
        created_at=NOW,
    )


def build_judgment(project_id: str, evidence_id: str) -> Record:
    return Record.create(
        entity_type=EntityType.BRAIN_JUDGMENT,
        project_id=project_id,
        producer=PRODUCER,
        payload=BrainJudgmentPayload(
            current_judgment="store 우선 구현",
            grounds=(evidence_id,),
            confidence=0.6,
            brain_version="primary/fixture",
            context_digest="sha256:" + "2" * 64,
        ),
        references=(Reference(relation=REL_GROUND, target_id=evidence_id, expected_type=EntityType.EVIDENCE),),
        created_at=NOW,
    )


def build_constitution_rule(project_id: str, *, principle_number: int = 1) -> Record:
    return Record.create(
        entity_type=EntityType.CONSTITUTION_RULE,
        project_id=project_id,
        producer=PRODUCER,
        payload=ConstitutionRulePayload(
            principle_number=principle_number,
            verbatim_text="THE BRAIN IS REPLACEABLE.",
            source_digest="sha256:" + "c" * 64,
            version="1.0",
        ),
        created_at=NOW,
    )


def build_project(project_id: str, *, protected_constraints: tuple[str, ...] = ()) -> Record:
    return Record.create(
        entity_type=EntityType.PROJECT,
        project_id=project_id,
        producer=PRODUCER,
        payload=ProjectPayload(
            name="ssak-ai",
            premise="Persistent Adaptive Cognitive System",
            protected_constraints=protected_constraints,
        ),
        references=tuple(
            Reference(relation="constitution_rule", target_id=rule_id, expected_type=EntityType.CONSTITUTION_RULE)
            for rule_id in protected_constraints
        ),
        record_id=project_id,
        created_at=NOW,
    )


def build_open_decision(project_id: str) -> Record:
    return Record.create(
        entity_type=EntityType.DECISION,
        project_id=project_id,
        producer=PRODUCER,
        payload=DecisionPayload(
            selected_action="context builder 구현",
            why_selected="P04 선행 카드",
            closure="open",
            expected_outcome="T03 통과",
            readiness=assurance(),
            unknowns_assessed=True,
        ),
        created_at=NOW,
    )


def build_material_unknown(project_id: str) -> Record:
    return Record.create(
        entity_type=EntityType.UNKNOWN,
        project_id=project_id,
        producer=PRODUCER,
        payload=UnknownPayload(
            question="L2 advisory 범위는 충분한가",
            category="CONTEXT",
            materiality="MATERIAL",
            materiality_reason="action 범위가 달라진다",
            potential_action_change=True,
        ),
        created_at=NOW,
    )


def build_experience(project_id: str) -> Record:
    return Record.create(
        entity_type=EntityType.EXPERIENCE,
        project_id=project_id,
        producer=PRODUCER,
        payload=ExperiencePayload(trigger="T02 시험", future_attention=("digest 변조",)),
        created_at=NOW,
    )


def build_interpretation(project_id: str, experience_id: str) -> Record:
    return Record.create(
        entity_type=EntityType.INTERPRETATION,
        project_id=project_id,
        producer=PRODUCER,
        payload=InterpretationPayload(
            experience_id=experience_id,
            revision=1,
            author=PRODUCER,
            meaning="append-only 확인",
            confidence_profile=confidence(),
            applicability_profile={},
        ),
        created_at=NOW,
    )


def build_decision(project_id: str, *, supersedes: tuple[str, ...] = ()) -> Record:
    return Record.create(
        entity_type=EntityType.DECISION,
        project_id=project_id,
        producer=PRODUCER,
        payload=DecisionPayload(
            selected_action="transaction commit",
            why_selected="create-only 계약",
            closure="closed_for_action",
            expected_outcome="T02 통과",
            readiness=assurance(),
            unknowns_assessed=True,
        ),
        references=tuple(
            Reference(relation="supersedes", target_id=target, expected_type=EntityType.DECISION)
            for target in supersedes
        ),
        created_at=NOW,
    )
