"""T01a — typed cognitive model/계보 계약 시험.

검증 항목: 전 entity roundtrip 무손실, unknown enum·naive time·cross-project ref·잘못된 type 거부,
Observation/Interpretation 분리, provider/UI 비의존.
"""

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from antigravity_k.engine.cognitive import models as cognitive_models
from antigravity_k.engine.cognitive.models import (
    PAYLOAD_TYPES,
    ActionPayload,
    AlternativePayload,
    ArchitectureDecisionPayload,
    AssumptionPayload,
    AuthorityGrant,
    AuthorityProfilePayload,
    BehaviorChangeTracePayload,
    BrainJudgmentPayload,
    CanonicalInvariantError,
    CheckStatus,
    CognitiveRequestPayload,
    ConfidenceProfile,
    ConstitutionRulePayload,
    ContextBudget,
    ContextHandleRef,
    ContextItem,
    ContextPackagePayload,
    DecisionAssurance,
    DecisionPayload,
    DisclosureLevel,
    EntityPayloadModel,
    EventPayload,
    EvidenceKind,
    EvidencePayload,
    ExecutionReceiptPayload,
    ExperiencePayload,
    GoalPayload,
    GovernanceDecisionPayload,
    GovernanceFeedback,
    HypothesisPayload,
    IntegrityStatus,
    InterpretationPayload,
    LoopState,
    MetricResult,
    ObservationPayload,
    ObservationStatus,
    OutcomePayload,
    OutcomeStatus,
    PatternPayload,
    PolicyActivationPayload,
    PolicyPayload,
    PrinciplePayload,
    Producer,
    ProducerKind,
    ProjectPayload,
    Provenance,
    ReadinessCheck,
    ReadinessCheckResult,
    ReadinessVerdict,
    ReassessmentPayload,
    Record,
    RiskProfile,
    StrategyPayload,
    UnknownPayload,
    UnsupportedSchemaError,
    ValidationReportPayload,
    from_wire,
    to_wire,
)
from antigravity_k.engine.cognitive.references import (
    REL_EVIDENCE,
    REL_GROUND,
    REL_SHARED_SCOPE,
    REL_SUPERSEDES,
    EntityType,
    Reference,
    ReferenceValidationError,
    ResolvedTarget,
    assert_no_supersedes_cycle,
    new_id,
    validate_references,
)

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
PRODUCER = Producer(kind=ProducerKind.BODY, actor_id="body:test")
IDS = {entity_type: new_id(entity_type) for entity_type in EntityType}
PROJECT_ID = IDS[EntityType.PROJECT]
OTHER_PROJECT_ID = new_id(EntityType.PROJECT)


def _provenance() -> Provenance:
    return Provenance(
        source_uri="tests/cognitive/test_models.py",
        source_version="1",
        content_digest="sha256:" + "0" * 64,
        observed_at=NOW,
        ingested_at=NOW,
    )


def _assurance() -> DecisionAssurance:
    return DecisionAssurance(
        verdict=ReadinessVerdict.READY,
        check_results=tuple(
            ReadinessCheckResult(check=check, status=CheckStatus.PASS, reason="fixture") for check in ReadinessCheck
        ),
        decision_revision=1,
        state_revision=1,
    )


def _confidence() -> ConfidenceProfile:
    return ConfidenceProfile(
        evidence_strength=0.5, independence=0.5, replication=0.5, contradiction=0.1, context_coverage=0.5
    )


def _payload_for(entity_type: EntityType) -> EntityPayloadModel:
    """30종 entity의 최소 유효 payload."""

    match entity_type:
        case EntityType.PROJECT:
            return ProjectPayload(
                name="Ssak-Ai",
                premise="Persistent Adaptive Cognitive System",
                protected_constraints=(IDS[EntityType.CONSTITUTION_RULE],),
            )
        case EntityType.GOAL:
            return GoalPayload(statement="P01 계약 구현", success_criteria=("T01a 통과",))
        case EntityType.EVIDENCE:
            return EvidencePayload(
                kind=EvidenceKind.OBSERVATION,
                claim="pytest 127 passed",
                provenance=_provenance(),
                time=NOW,
                digest="sha256:" + "1" * 64,
                independence_group="pytest-run",
            )
        case EntityType.BRAIN_JUDGMENT:
            return BrainJudgmentPayload(
                current_judgment="계약 우선 구현이 타당하다",
                grounds=(IDS[EntityType.EVIDENCE],),
                confidence=0.6,
                confidence_reason="단일 fixture 근거",
                brain_version="primary/test",
                context_digest="sha256:" + "2" * 64,
            )
        case EntityType.ASSUMPTION:
            return AssumptionPayload(statement="venv가 존재한다", validity_scope="로컬 워크스테이션")
        case EntityType.UNKNOWN:
            return UnknownPayload(
                question="migration 범위는?",
                category="CONTEXT",
                materiality="MATERIAL",
                materiality_reason="action 범위가 달라진다",
                potential_action_change=True,
            )
        case EntityType.ALTERNATIVE:
            return AlternativePayload(proposed_action="adapter 유지", expected_outcome="회귀 없음")
        case EntityType.COGNITIVE_REQUEST:
            return CognitiveRequestPayload(
                request_type="TOOL",
                purpose="현재 상태 확인",
                target="tool:read",
                expected_value="ground 확보",
                expected_decision_impact="action 축소",
                args_digest="sha256:" + "3" * 64,
            )
        case EntityType.GOVERNANCE_DECISION:
            return GovernanceDecisionPayload(
                disposition="APPROVE_WITH_LIMITS",
                reason="읽기만 허용",
                limits=("read-only",),
                feedback=GovernanceFeedback(original_request_digest="sha256:" + "4" * 64, why_changed="범위 제한"),
            )
        case EntityType.DECISION:
            return DecisionPayload(
                selected_action="계약 모듈 작성",
                why_selected="의존 없는 선행 카드",
                closure="closed_for_action",
                expected_outcome="T01a 통과",
                reopen_triggers=("NEW_MATERIAL_EVIDENCE",),
                readiness=_assurance(),
                unknowns_assessed=True,
            )
        case EntityType.ACTION:
            return ActionPayload(
                tool="read_file",
                args_digest="sha256:" + "5" * 64,
                scope="tests/cognitive",
                risk_profile=RiskProfile(),
                idempotency_key="action:1",
            )
        case EntityType.OBSERVATION:
            return ObservationPayload(
                raw_measurement_or_handle="127 passed",
                observed_at=NOW,
                method="pytest -q",
                source="local venv",
                status=ObservationStatus.COMPLETE,
            )
        case EntityType.OUTCOME:
            return OutcomePayload(expected="T01a 통과", observed="통과", delta="없음", status=OutcomeStatus.MATCH)
        case EntityType.EXPERIENCE:
            return ExperiencePayload(trigger="P01 구현", future_attention=("adapter 회귀",))
        case EntityType.PATTERN:
            return PatternPayload(
                statement="계약 먼저 구현하면 회귀가 줄어든다", scope="engine/cognitive", independence_count=2
            )
        case EntityType.HYPOTHESIS:
            return HypothesisPayload(
                claim="typed reference가 ID 손실을 막는다",
                falsification_criteria=("roundtrip 손실 발생",),
                evaluation_plan="roundtrip 시험",
            )
        case EntityType.STRATEGY:
            return StrategyPayload(operational_rule="쓰기 전에 resolver 검증", applicability={"goal_match": "MATCH"})
        case EntityType.PRINCIPLE:
            return PrinciplePayload(
                statement="저장 전에 계보를 고정한다",
                scope="canonical store",
                confidence_profile=_confidence(),
                applicability={},
            )
        case EntityType.POLICY:
            return PolicyPayload(
                target="CONTEXT_DEPTH",
                rule="얕은 context에서 config evidence handle을 한 단계 더 연다",
                parameters={"extra_depth": 1},
                version="v1",
            )
        case EntityType.AUTHORITY_PROFILE:
            return AuthorityProfilePayload(
                grants=(
                    AuthorityGrant(
                        subject="body:test",
                        dimension="TOOL_READ",
                        resource_scope="tests/cognitive",
                        allowed_operations=("read",),
                        granted_by="human:mr.k",
                        issued_at=NOW,
                        revision=1,
                    ),
                ),
                revision=1,
            )
        case EntityType.CONSTITUTION_RULE:
            return ConstitutionRulePayload(
                principle_number=1,
                verbatim_text="THE BRAIN IS REPLACEABLE.",
                source_digest="sha256:" + "6" * 64,
                version="1.0",
            )
        case EntityType.ARCHITECTURE_DECISION:
            return ArchitectureDecisionPayload(
                context="P01", problem="ID 계보 부재", decision="canonical envelope 도입"
            )
        case EntityType.CONTEXT_PACKAGE:
            return ContextPackagePayload(
                goal_id=IDS[EntityType.GOAL],
                state_revision=1,
                l0_constraints=(
                    ContextItem(
                        record_id=IDS[EntityType.CONSTITUTION_RULE],
                        reason_selected="protected constraint",
                        token_estimate=10,
                        disclosure_level=DisclosureLevel.L0_SIGNAL,
                    ),
                ),
                handles=(
                    ContextHandleRef(
                        handle_id="H1",
                        project_id=PROJECT_ID,
                        owner_scope="project",
                        record_id=IDS[EntityType.EXPERIENCE],
                        content_digest="sha256:" + "7" * 64,
                        disclosure_level=DisclosureLevel.L1_SUMMARY,
                    ),
                ),
                budget=ContextBudget(token_budget=100, tokens_used=10, l0_reserved_tokens=10),
            )
        case EntityType.INTERPRETATION:
            return InterpretationPayload(
                experience_id=IDS[EntityType.EXPERIENCE],
                revision=1,
                author=PRODUCER,
                meaning="초기 해석",
                confidence_profile=_confidence(),
                applicability_profile={},
            )
        case EntityType.REASSESSMENT:
            return ReassessmentPayload(
                target_record_id=IDS[EntityType.DECISION],
                trigger="NEW_MATERIAL_EVIDENCE",
                changed_understanding="범위를 좁힌다",
                smallest_scope="P01만",
            )
        case EntityType.VALIDATION_REPORT:
            return ValidationReportPayload(
                candidate_id=IDS[EntityType.PATTERN],
                split_ids=("held-out-1",),
                method="paired trial",
                metrics=(MetricResult(name="retry", value=0.0, unit="count"),),
                passed=True,
                independent_episode_count=2,
            )
        case EntityType.POLICY_ACTIVATION:
            return PolicyActivationPayload(
                policy_id=IDS[EntityType.POLICY],
                version="v1",
                validation_report_id=IDS[EntityType.VALIDATION_REPORT],
                reason="검증 통과",
            )
        case EntityType.BEHAVIOR_CHANGE_TRACE:
            return BehaviorChangeTracePayload(
                policy_version="v1", task_id="task-1", shadow_selection=("ctx:shallow",), actual_selection=("ctx:deep",)
            )
        case EntityType.EVENT:
            return EventPayload(sequence=1, episode_id="episode-1", state=LoopState.THINK, state_revision=1)
        case EntityType.EXECUTION_RECEIPT:
            return ExecutionReceiptPayload(
                action_id=IDS[EntityType.ACTION],
                idempotency_key="action:1",
                dispatch_attempt=1,
                started_at=NOW,
                status="DISPATCHED",
            )
    raise AssertionError(f"payload fixture 누락: {entity_type}")


def _references_for(entity_type: EntityType) -> tuple[Reference, ...]:
    match entity_type:
        case EntityType.PROJECT:
            return (
                Reference(
                    relation="constitution_rule",
                    target_id=IDS[EntityType.CONSTITUTION_RULE],
                    expected_type=EntityType.CONSTITUTION_RULE,
                ),
            )
        case EntityType.BRAIN_JUDGMENT:
            return (
                Reference(relation=REL_GROUND, target_id=IDS[EntityType.EVIDENCE], expected_type=EntityType.EVIDENCE),
            )
        case _:
            return ()


def _record_for(entity_type: EntityType) -> Record:
    return Record.create(
        entity_type=entity_type,
        project_id=PROJECT_ID,
        producer=PRODUCER,
        payload=_payload_for(entity_type),
        references=_references_for(entity_type),
        record_id=IDS[entity_type],
        created_at=NOW,
    )


@pytest.mark.parametrize("entity_type", list(EntityType))
def test_every_entity_roundtrips_without_loss(entity_type: EntityType) -> None:
    record = _record_for(entity_type)

    wire = to_wire(record)
    assert list(wire) == [
        "schema_version",
        "id",
        "entity_type",
        "project_id",
        "created_at",
        "producer",
        "references",
        "payload",
    ]
    assert from_wire(wire) == record
    assert to_wire(from_wire(wire)) == wire
    assert isinstance(record.payload, PAYLOAD_TYPES[entity_type])
    assert json.loads(json.dumps(wire)) == wire


def test_payload_union_covers_all_entity_types() -> None:
    assert len(PAYLOAD_TYPES) == len(EntityType) == 30
    schema_enum = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/ssak-ai-core/contracts/record-envelope.schema.json").read_text(
            encoding="utf-8"
        )
    )["properties"]["entity_type"]["enum"]
    assert set(schema_enum) == {entity_type.value for entity_type in EntityType}


def test_created_at_is_normalized_to_utc() -> None:
    kst = timezone(timedelta(hours=9))
    record = _record_for(EntityType.GOAL).model_copy(update={})
    record = Record.create(
        entity_type=EntityType.GOAL,
        project_id=PROJECT_ID,
        producer=PRODUCER,
        payload=_payload_for(EntityType.GOAL),
        created_at=datetime(2026, 9, 22, 12, 0, tzinfo=kst),
    )
    assert record.created_at == datetime(2026, 9, 22, 3, 0, tzinfo=UTC)
    assert to_wire(record)["created_at"].startswith("2026-09-22T03:00:00")


def test_naive_time_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ObservationPayload(
            raw_measurement_or_handle="x",
            observed_at=datetime(2026, 9, 22, 3, 0),
            method="m",
            source="s",
            status=ObservationStatus.COMPLETE,
        )
    with pytest.raises(ValidationError, match="timezone"):
        Record.create(
            entity_type=EntityType.GOAL,
            project_id=PROJECT_ID,
            producer=PRODUCER,
            payload=_payload_for(EntityType.GOAL),
            created_at=datetime(2026, 9, 22, 3, 0),
        )


def test_naive_provenance_time_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Provenance(
            source_uri="x",
            content_digest="sha256:" + "0" * 64,
            observed_at=datetime(2026, 9, 22, 3, 0),
            ingested_at=NOW,
        )


def test_unknown_enum_value_rejected() -> None:
    wire = to_wire(_record_for(EntityType.EVIDENCE))
    payload = dict(wire["payload"])
    payload["kind"] = "PROBABLY_TRUE"
    wire["payload"] = payload
    with pytest.raises(ValidationError):
        from_wire(wire)


def test_undefined_payload_field_rejected() -> None:
    wire = to_wire(_record_for(EntityType.PROJECT))
    payload = dict(wire["payload"])
    payload["secret_note"] = "미정의 필드"
    wire["payload"] = payload
    with pytest.raises(ValidationError):
        from_wire(wire)


def test_payload_entity_mismatch_rejected() -> None:
    goal = _payload_for(EntityType.GOAL)
    with pytest.raises(ValidationError):
        Record(
            id=IDS[EntityType.ACTION],
            entity_type=EntityType.ACTION,
            project_id=PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=goal,
        )


def test_id_namespace_must_match_entity_type() -> None:
    with pytest.raises(ValidationError, match="namespace mismatch"):
        Record(
            id=new_id(EntityType.GOAL),
            entity_type=EntityType.EVIDENCE,
            project_id=PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=_payload_for(EntityType.EVIDENCE),
        )


def test_non_canonical_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Record(
            id="evidence-1",
            entity_type=EntityType.EVIDENCE,
            project_id=PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=_payload_for(EntityType.EVIDENCE),
        )


def test_project_record_project_id_must_equal_self() -> None:
    with pytest.raises(ValidationError, match="자기 ID"):
        Record(
            id=IDS[EntityType.PROJECT],
            entity_type=EntityType.PROJECT,
            project_id=OTHER_PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=_payload_for(EntityType.PROJECT),
            references=_references_for(EntityType.PROJECT),
        )


def test_project_protected_constraint_needs_rule_reference() -> None:
    with pytest.raises(ValidationError, match="ConstitutionRule"):
        Record(
            id=IDS[EntityType.PROJECT],
            entity_type=EntityType.PROJECT,
            project_id=IDS[EntityType.PROJECT],
            created_at=NOW,
            producer=PRODUCER,
            payload=_payload_for(EntityType.PROJECT),
        )


def test_observation_rejects_interpretation_field() -> None:
    wire = to_wire(_record_for(EntityType.OBSERVATION))
    payload = dict(wire["payload"])
    payload["meaning"] = "좋은 결과였다"
    wire["payload"] = payload
    with pytest.raises(ValidationError):
        from_wire(wire)


def test_brain_judgment_requires_evidence_ground_reference() -> None:
    judgment = _payload_for(EntityType.BRAIN_JUDGMENT)
    assert isinstance(judgment, BrainJudgmentPayload)
    with pytest.raises(ValidationError, match="Evidence reference"):
        Record(
            id=IDS[EntityType.BRAIN_JUDGMENT],
            entity_type=EntityType.BRAIN_JUDGMENT,
            project_id=PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=judgment,
        )
    with pytest.raises(ValidationError, match="ground"):
        Record(
            id=IDS[EntityType.BRAIN_JUDGMENT],
            entity_type=EntityType.BRAIN_JUDGMENT,
            project_id=PROJECT_ID,
            created_at=NOW,
            producer=PRODUCER,
            payload=BrainJudgmentPayload(
                current_judgment="근거 없는 결론",
                grounds=(),
                confidence=1.0,
                brain_version="primary/test",
                context_digest="sha256:" + "2" * 64,
            ),
        )


def test_decision_assurance_requires_all_nine_checks() -> None:
    partial = tuple(
        ReadinessCheckResult(check=check, status=CheckStatus.PASS, reason="fixture")
        for check in ReadinessCheck
        if check is not ReadinessCheck.ROLLBACK_SUFFICIENT
    )
    with pytest.raises(ValidationError, match="missing readiness checks"):
        DecisionAssurance(verdict=ReadinessVerdict.READY, check_results=partial, decision_revision=1, state_revision=1)


def test_not_ready_verdict_requires_non_pass_check() -> None:
    with pytest.raises(ValidationError, match="NOT_READY"):
        DecisionAssurance(
            verdict=ReadinessVerdict.NOT_READY,
            check_results=tuple(
                ReadinessCheckResult(check=check, status=CheckStatus.PASS, reason="fixture") for check in ReadinessCheck
            ),
            decision_revision=1,
            state_revision=1,
        )


def test_experience_integrity_consistency() -> None:
    with pytest.raises(ValidationError, match="missing_references"):
        ExperiencePayload(trigger="t", integrity=IntegrityStatus.INCOMPLETE)
    with pytest.raises(ValidationError, match="missing_references"):
        ExperiencePayload(trigger="t", integrity=IntegrityStatus.COMPLETE, missing_references=("goal:missing",))


def test_context_package_integrity_consistency() -> None:
    base = {
        "goal_id": IDS[EntityType.GOAL],
        "state_revision": 1,
        "budget": ContextBudget(token_budget=10, tokens_used=0, l0_reserved_tokens=0),
    }
    with pytest.raises(ValidationError, match="missing_ids"):
        ContextPackagePayload(**base, integrity=IntegrityStatus.INCOMPLETE)
    with pytest.raises(ValidationError, match="L0"):
        ContextPackagePayload(**{**base, "budget": ContextBudget(token_budget=5, tokens_used=0, l0_reserved_tokens=6)})


def test_policy_target_allowlist_rejects_constitution() -> None:
    with pytest.raises(ValidationError):
        PolicyPayload(target="CONSTITUTION", rule="헌법을 바꾼다", version="v1")


def test_policy_parameter_key_format_enforced() -> None:
    with pytest.raises(ValidationError, match="parameter key"):
        PolicyPayload(
            target="CONTEXT_DEPTH",
            rule="r",
            parameters={"Depth Delta": 1},
            version="v1",
        )


def test_constitution_rule_principle_number_range() -> None:
    with pytest.raises(ValidationError):
        ConstitutionRulePayload(principle_number=25, verbatim_text="x", source_digest="d", version="1.0")


class _Resolver:
    def __init__(self, targets: dict[str, ResolvedTarget]) -> None:
        self._targets = targets

    def resolve(self, target_id: str) -> ResolvedTarget | None:
        return self._targets.get(target_id)


def _resolver_for(record: Record, target: ResolvedTarget) -> _Resolver:
    reference = record.references[0]
    return _Resolver({reference.target_id: target})


def test_reference_validation_reasons() -> None:
    record = _record_for(EntityType.BRAIN_JUDGMENT)
    reference = record.references[0]

    with pytest.raises(ReferenceValidationError, match="UNRESOLVED"):
        validate_references(record, _Resolver({}))

    with pytest.raises(ReferenceValidationError, match="TYPE_MISMATCH"):
        validate_references(
            record, _Resolver({reference.target_id: ResolvedTarget(entity_type=EntityType.GOAL, project_id=PROJECT_ID)})
        )

    with pytest.raises(ReferenceValidationError, match="CROSS_PROJECT"):
        validate_references(
            record,
            _Resolver(
                {reference.target_id: ResolvedTarget(entity_type=EntityType.EVIDENCE, project_id=OTHER_PROJECT_ID)}
            ),
        )

    validate_references(
        record,
        _Resolver({reference.target_id: ResolvedTarget(entity_type=EntityType.EVIDENCE, project_id=PROJECT_ID)}),
    )


def test_revision_mismatch_and_self_reference_rejected() -> None:
    reference = Reference(
        relation=REL_GROUND,
        target_id=IDS[EntityType.EVIDENCE],
        expected_type=EntityType.EVIDENCE,
        target_revision=2,
    )
    judgment = _payload_for(EntityType.BRAIN_JUDGMENT)
    record = Record.create(
        entity_type=EntityType.BRAIN_JUDGMENT,
        project_id=PROJECT_ID,
        producer=PRODUCER,
        payload=judgment,
        references=(reference,),
        created_at=NOW,
    )
    with pytest.raises(ReferenceValidationError, match="REVISION_MISMATCH"):
        validate_references(
            record,
            _Resolver(
                {
                    reference.target_id: ResolvedTarget(
                        entity_type=EntityType.EVIDENCE, project_id=PROJECT_ID, revision=1
                    )
                }
            ),
        )

    ground = Reference(relation=REL_GROUND, target_id=IDS[EntityType.EVIDENCE], expected_type=EntityType.EVIDENCE)
    self_reference = Reference(relation=REL_EVIDENCE, target_id=record.id, expected_type=EntityType.BRAIN_JUDGMENT)
    self_record = Record.create(
        entity_type=EntityType.BRAIN_JUDGMENT,
        project_id=PROJECT_ID,
        producer=PRODUCER,
        payload=judgment,
        references=(ground, self_reference),
        record_id=record.id,
        created_at=NOW,
    )
    with pytest.raises(ReferenceValidationError, match="SELF_REFERENCE"):
        validate_references(
            self_record,
            _Resolver(
                {IDS[EntityType.EVIDENCE]: ResolvedTarget(entity_type=EntityType.EVIDENCE, project_id=PROJECT_ID)}
            ),
        )


def test_shared_scope_relation_allows_cross_project_reference() -> None:
    local_evidence = IDS[EntityType.EVIDENCE]
    foreign_evidence = new_id(EntityType.EVIDENCE)
    record = Record.create(
        entity_type=EntityType.BRAIN_JUDGMENT,
        project_id=PROJECT_ID,
        producer=PRODUCER,
        payload=_payload_for(EntityType.BRAIN_JUDGMENT),
        references=(
            Reference(relation=REL_GROUND, target_id=local_evidence, expected_type=EntityType.EVIDENCE),
            Reference(relation=REL_SHARED_SCOPE, target_id=foreign_evidence, expected_type=EntityType.EVIDENCE),
        ),
        created_at=NOW,
    )
    validate_references(
        record,
        _Resolver(
            {
                local_evidence: ResolvedTarget(entity_type=EntityType.EVIDENCE, project_id=PROJECT_ID),
                foreign_evidence: ResolvedTarget(entity_type=EntityType.EVIDENCE, project_id=OTHER_PROJECT_ID),
            }
        ),
    )


def test_supersedes_cycle_rejected() -> None:
    first = IDS[EntityType.DECISION]
    second = new_id(EntityType.DECISION)

    def load(record_id: str) -> Sequence[Reference]:
        if record_id == first:
            return (Reference(relation=REL_SUPERSEDES, target_id=second, expected_type=EntityType.DECISION),)
        if record_id == second:
            return (Reference(relation=REL_SUPERSEDES, target_id=first, expected_type=EntityType.DECISION),)
        return ()

    with pytest.raises(ReferenceValidationError, match="SUPERSEDES_CYCLE"):
        assert_no_supersedes_cycle(first, load)
    assert_no_supersedes_cycle(new_id(EntityType.DECISION), load)


def test_unsupported_schema_major_quarantined() -> None:
    wire = to_wire(_record_for(EntityType.GOAL))
    wire["schema_version"] = "2.0"
    with pytest.raises(UnsupportedSchemaError, match="UNSUPPORTED_SCHEMA"):
        from_wire(wire)

    del wire["schema_version"]
    with pytest.raises(UnsupportedSchemaError):
        from_wire(wire)


#: provider/UI/도구 계층. cognitive core와 adapter가 여기에 결합하면 Brain 교체성이 깨진다.
FORBIDDEN_FIRST_PARTY_PREFIXES = (
    "antigravity_k.api",
    "antigravity_k.agents",
    "antigravity_k.cli",
    "antigravity_k.dashboard",
    "antigravity_k.desktop",
    "antigravity_k.knowledge",
    "antigravity_k.tools",
    "antigravity_k.ui",
    "antigravity_k.vscode",
)
CORE_MODULES = ("models.py", "references.py")
CORE_ALLOWED_THIRD_PARTY = {"pydantic"}
INFRA_ALLOWED_THIRD_PARTY = {"pydantic", "filelock", "yaml"}
ALLOWED_FIRST_PARTY_PREFIX = "antigravity_k.engine.cognitive"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            modules.append(node.module)
    return modules


def test_cognitive_core_imports_no_provider_or_ui() -> None:
    package_dir = Path(cognitive_models.__file__).parent
    violations: list[str] = []
    for path in sorted(package_dir.glob("*.py")):
        allowed_third_party = CORE_ALLOWED_THIRD_PARTY if path.name in CORE_MODULES else INFRA_ALLOWED_THIRD_PARTY
        for module in _imported_modules(path):
            root = module.split(".")[0]
            if root in sys.stdlib_module_names or root in allowed_third_party:
                continue
            if module == ALLOWED_FIRST_PARTY_PREFIX or module.startswith(ALLOWED_FIRST_PARTY_PREFIX + "."):
                continue
            violations.append(f"{path.name}: {module}")
    assert violations == []


def test_cognitive_namespace_never_imports_provider_or_ui_layers() -> None:
    package_dir = Path(cognitive_models.__file__).parent
    violations: list[str] = []
    for path in sorted(package_dir.glob("*.py")):
        for module in _imported_modules(path):
            if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_FIRST_PARTY_PREFIXES):
                violations.append(f"{path.name}: {module}")
    assert violations == []


def test_canonical_invariant_error_is_value_error() -> None:
    assert issubclass(CanonicalInvariantError, ValueError)
