"""T04 — Brain adapter 교체 시험."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.brain import (
    BrainCapabilities,
    BrainDirector,
    BrainFailure,
    BrainFailureKind,
    BrainJudgment,
    BrainResponse,
    StructuredBrainClient,
)
from antigravity_k.engine.cognitive.context import ContextBuilder, ContextPrincipal
from antigravity_k.engine.cognitive.models import (
    ApplicabilityLevel,
    ContextBudget,
    ContextItem,
    ContextPackagePayload,
    DisclosureLevel,
    IntegrityStatus,
    Producer,
    ProducerKind,
    Record,
    to_wire,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest
from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
from tests.cognitive._fixtures import (
    build_constitution_rule,
    build_evidence,
    build_goal,
    build_project,
)

PROJECT = new_id(EntityType.PROJECT)
EVIDENCE_ID = new_id(EntityType.EVIDENCE)
CONTEXT_DIGEST = "sha256:" + "d" * 64
CONTEXT_WIRE: dict[str, object] = {
    "schema_version": "1.0",
    "entity_type": "ContextPackage",
    "context_digest": CONTEXT_DIGEST,
    "project_id": PROJECT,
    "payload": {"goal_id": new_id(EntityType.GOAL)},
}


def capabilities(**overrides: object) -> BrainCapabilities:
    base = {
        "structured_output": True,
        "tool_request": True,
        "context_limit": 100_000,
        "timeout_seconds": 30.0,
        "provider_model_version": "test-1",
    }
    base.update(overrides)
    return BrainCapabilities(**base)  # type: ignore[arg-type]


def judgment_dict(*, grounds: Sequence[str] | None = None, context_digest: str = CONTEXT_DIGEST) -> dict[str, object]:
    return {
        "current_judgment": "context builder 우선",
        "grounds": list(grounds if grounds is not None else (EVIDENCE_ID,)),
        "confidence": 0.7,
        "confidence_reason": "단일 fixture",
        "brain_version": "fake/1",
        "context_digest": context_digest,
    }


def structured(payload: dict[str, object], *, version: str = "test-1") -> BrainResponse:
    return BrainResponse(structured=payload, provider_model_version=version)


def valid_response(version: str = "test-1") -> BrainResponse:
    return structured({"judgment": judgment_dict()}, version=version)


class FakeAdapter:
    def __init__(
        self,
        name: str,
        responses: Sequence[BrainResponse],
        *,
        caps: BrainCapabilities | None = None,
    ) -> None:
        self._name = name
        self._responses = list(responses)
        self._caps = caps or capabilities()
        self.calls: list[dict[str, object]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> BrainCapabilities:
        return self._caps

    def respond(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        repair_of: Mapping[str, object] | None = None,
    ) -> BrainResponse:
        self.calls.append({"context": context_wire, "request_id": request_id, "repair_of": repair_of})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def client(adapter: FakeAdapter, *, project_id: str = PROJECT) -> StructuredBrainClient:
    return StructuredBrainClient(adapter, project_id=project_id)


def test_think_returns_canonical_judgment_with_ground_references() -> None:
    adapter = FakeAdapter("primary-a", [valid_response()])

    outcome = client(adapter).think(CONTEXT_WIRE, "req-1")

    assert isinstance(outcome, BrainJudgment)
    assert outcome.record.entity_type is EntityType.BRAIN_JUDGMENT
    assert outcome.payload.grounds == (EVIDENCE_ID,)
    assert [reference.relation for reference in outcome.record.references] == ["ground"]
    assert outcome.record.project_id == PROJECT
    assert len(adapter.calls) == 1


def test_plain_text_response_is_never_promoted() -> None:
    adapter = FakeAdapter("primary-b", [BrainResponse(text="그냥 자연어 결론입니다")])

    outcome = client(adapter).think(CONTEXT_WIRE, "req-2")

    assert isinstance(outcome, BrainFailure)
    assert outcome.kind is BrainFailureKind.BRAIN_PROTOCOL_ERROR
    assert outcome.repair_attempts == 1
    assert len(adapter.calls) == 2, "형식 오류는 1회만 repair한다"


def test_malformed_then_valid_repair_succeeds_once() -> None:
    adapter = FakeAdapter(
        "primary-c",
        [structured({"judgment": {"current_judgment": "형식 없음"}}), valid_response()],
    )

    outcome = client(adapter).think(CONTEXT_WIRE, "req-3")

    assert isinstance(outcome, BrainJudgment)
    assert outcome.repair_attempts == 1
    assert len(adapter.calls) == 2
    assert adapter.calls[1]["repair_of"] is not None


def test_repeated_malformed_response_stops_after_one_repair() -> None:
    adapter = FakeAdapter("primary-d", [structured({"judgment": {}}), structured({"judgment": {}})])

    outcome = client(adapter).think(CONTEXT_WIRE, "req-4")

    assert isinstance(outcome, BrainFailure)
    assert outcome.repair_attempts == 1
    assert len(adapter.calls) == 2


def test_non_canonical_ground_id_rejected() -> None:
    adapter = FakeAdapter("primary-e", [structured({"judgment": judgment_dict(grounds=("자유문 근거",))})])

    outcome = client(adapter).think(CONTEXT_WIRE, "req-5")

    assert isinstance(outcome, BrainFailure)
    assert "non-canonical id" in outcome.detail


def test_missing_context_digest_rejected() -> None:
    adapter = FakeAdapter("primary-f", [structured({"judgment": judgment_dict(context_digest="")})])

    outcome = client(adapter).think(CONTEXT_WIRE, "req-6")

    assert isinstance(outcome, BrainFailure)
    assert "context_digest" in outcome.detail


def test_oversize_response_rejected() -> None:
    adapter = FakeAdapter("primary-g", [BrainResponse(text="x" * 50)])
    out = StructuredBrainClient(adapter, project_id=PROJECT, max_response_chars=10).think(CONTEXT_WIRE, "req-7")

    assert isinstance(out, BrainFailure)
    assert "exceeds" in out.detail


def test_context_project_mismatch_rejected() -> None:
    adapter = FakeAdapter("primary-h", [valid_response()])
    other_wire = dict(CONTEXT_WIRE, project_id=new_id(EntityType.PROJECT))

    outcome = client(adapter).think(other_wire, "req-8")

    assert isinstance(outcome, BrainFailure)
    assert adapter.calls == []


def test_unstructured_adapter_rejected() -> None:
    adapter = FakeAdapter("primary-i", [valid_response()], caps=capabilities(structured_output=False))

    outcome = client(adapter).think(CONTEXT_WIRE, "req-9")

    assert isinstance(outcome, BrainFailure)
    assert outcome.kind is BrainFailureKind.UNSUPPORTED_CAPABILITY


def test_rethink_creates_new_judgment_and_supersedes_previous() -> None:
    adapter = FakeAdapter("primary-j", [valid_response()])
    brain = client(adapter)
    first = brain.think(CONTEXT_WIRE, "req-10")
    assert isinstance(first, BrainJudgment)

    outcome = brain.rethink(
        CONTEXT_WIRE,
        "req-11",
        previous_judgment_id=first.record.id,
        feedback_ids=("governance_decision:feedback",),
        affected_ground_ids=(EVIDENCE_ID,),
        context_delta={"added_evidence": EVIDENCE_ID},
    )

    assert isinstance(outcome, BrainJudgment)
    assert outcome.record.id != first.record.id
    assert outcome.supersedes_record_id == first.record.id
    supersedes = [ref for ref in outcome.record.references if ref.relation == "supersedes"]
    assert supersedes and supersedes[0].target_id == first.record.id
    assert first.payload.current_judgment == "context builder 우선", "원래 판단은 수정되지 않는다"


def test_rethink_requires_canonical_previous_judgment_id() -> None:
    adapter = FakeAdapter("primary-k", [valid_response()])
    outcome = client(adapter).rethink(CONTEXT_WIRE, "req-12", previous_judgment_id="judgment-1")

    assert isinstance(outcome, BrainFailure)
    assert outcome.kind is BrainFailureKind.BRAIN_PROTOCOL_ERROR


def test_fallback_uses_same_frozen_context_with_new_judgment_id() -> None:
    primary = client(FakeAdapter("primary-l", [BrainResponse(text="plain text")]))
    fallback_adapter = FakeAdapter("fallback-m", [valid_response(version="test-2")])
    fallback = client(fallback_adapter)
    director = BrainDirector(project_id=PROJECT, primary=primary, secondary=None)

    outcome = director.think_with_fallback(CONTEXT_WIRE, "req-13", fallback)

    assert isinstance(outcome, BrainJudgment)
    assert primary.adapter.calls[0]["context"] is fallback_adapter.calls[0]["context"]
    assert outcome.provider_model_version == "test-2"
    assert outcome.record.id.startswith("brain_judgment:")


def test_different_providers_read_the_same_records() -> None:
    adapter_a = FakeAdapter("provider-a", [valid_response(version="a-1")])
    adapter_b = FakeAdapter("provider-b", [valid_response(version="b-9")])

    judgment_a = client(adapter_a).think(CONTEXT_WIRE, "req-a")
    judgment_b = client(adapter_b).think(CONTEXT_WIRE, "req-b")

    assert isinstance(judgment_a, BrainJudgment) and isinstance(judgment_b, BrainJudgment)
    assert judgment_a.payload.grounds == judgment_b.payload.grounds == (EVIDENCE_ID,)
    assert judgment_a.payload.context_digest == judgment_b.payload.context_digest
    assert judgment_a.record.id != judgment_b.record.id
    assert judgment_a.record.project_id == judgment_b.record.project_id == PROJECT


def test_secondary_requires_governance_approval_and_has_no_authority() -> None:
    primary_adapter = FakeAdapter("primary-n", [valid_response()])
    primary = client(primary_adapter)
    first = primary.think(CONTEXT_WIRE, "req-14")
    assert isinstance(first, BrainJudgment)
    secondary = client(FakeAdapter("secondary-o", [valid_response(version="secondary-1")]))
    director = BrainDirector(project_id=PROJECT, primary=primary, secondary=secondary)

    rejected = director.engage_secondary(CONTEXT_WIRE, "req-15", requested_by=first, governance_decision_id=None)
    assert isinstance(rejected, BrainFailure)
    assert rejected.kind is BrainFailureKind.UNSUPPORTED_CAPABILITY

    engagement = director.engage_secondary(
        CONTEXT_WIRE, "req-16", requested_by=first, governance_decision_id="governance_decision:abc"
    )
    assert not isinstance(engagement, BrainFailure)
    assert engagement.has_authority is False
    assert engagement.evidence.entity_type is EntityType.EVIDENCE
    assert str(engagement.evidence.payload.kind) == "MODEL_JUDGMENT"
    assert [ref.target_id for ref in engagement.evidence.references] == [first.record.id]


def test_secondary_absence_is_not_failure_of_primary() -> None:
    primary = client(FakeAdapter("primary-p", [valid_response()]))
    director = BrainDirector(project_id=PROJECT, primary=primary, secondary=None)
    first = primary.think(CONTEXT_WIRE, "req-17")
    assert isinstance(first, BrainJudgment)

    outcome = director.engage_secondary(CONTEXT_WIRE, "req-18", requested_by=first, governance_decision_id="g:1")

    assert isinstance(outcome, BrainFailure)
    assert first.record.entity_type is EntityType.BRAIN_JUDGMENT


@pytest.mark.parametrize("version", ["a-1", "b-2"])
def test_judgment_records_are_provider_version_tagged(version: str) -> None:
    adapter = FakeAdapter(f"provider-{version}", [valid_response(version=version)])

    outcome = client(adapter).think(CONTEXT_WIRE, f"req-{version}")

    assert isinstance(outcome, BrainJudgment)
    assert outcome.provider_model_version == version


def test_elapsed_over_declared_timeout_is_rejected() -> None:
    # T04-B: adapter가 선언한 timeout_seconds를 넘긴 유효 응답은 쓰지 않는다.
    ticks = iter([0.0, 45.0])
    slow = StructuredBrainClient(
        FakeAdapter("slow", [valid_response()]),
        project_id=PROJECT,
        timer=lambda: next(ticks),
    )

    outcome = slow.think(CONTEXT_WIRE, "req-timeout")

    assert isinstance(outcome, BrainFailure)
    assert outcome.kind is BrainFailureKind.TIMEOUT
    assert outcome.elapsed_seconds == 45.0
    assert "timeout_seconds=30" in outcome.detail


def test_repair_cost_is_accounted_on_the_judgment() -> None:
    # T04-B: repair에도 모델·비용을 계상한다 — 원래 시도의 비용은 사라지지 않는다.
    malformed = BrainResponse(text="그냥 텍스트", prompt_tokens=10, completion_tokens=5)
    repaired = BrainResponse(
        structured={"judgment": judgment_dict()},
        provider_model_version="test-1",
        prompt_tokens=7,
        completion_tokens=3,
    )
    flaky = client(FakeAdapter("flaky", [malformed, repaired]))

    outcome = flaky.think(CONTEXT_WIRE, "req-cost")

    assert isinstance(outcome, BrainJudgment)
    assert outcome.repair_attempts == 1
    assert outcome.prompt_tokens == 17
    assert outcome.completion_tokens == 8
    assert outcome.elapsed_seconds >= 0.0


def test_brain_swap_keeps_records_and_does_not_force_previous_conclusion(tmp_path: Path) -> None:
    # T04-A: 같은 Body 기록 위에서 A→B Brain 교체·재시작 — 이전 판단은 이력으로만 오고
    # 새 Brain의 다른 결론을 강제하지 않는다(원본 판단도 불변이다).
    project = new_id(EntityType.PROJECT)
    store = CanonicalStore(tmp_path / "canonical", git_enabled=False)
    rule = build_constitution_rule(project)
    goal = build_goal(project)
    evidence = build_evidence(project)
    store.commit_records([build_project(project, protected_constraints=(rule.id,)), rule, goal, evidence])
    wire: dict[str, object] = {
        "schema_version": "1.0",
        "entity_type": "ContextPackage",
        "context_digest": CONTEXT_DIGEST,
        "project_id": project,
        "payload": {"goal_id": goal.id},
    }

    client_a = StructuredBrainClient(
        FakeAdapter(
            "provider-a", [structured({"judgment": judgment_dict(grounds=(evidence.id,))}, version="provider-a/1")]
        ),
        project_id=project,
    )
    judgment_a = client_a.think(wire, "req-a")
    assert isinstance(judgment_a, BrainJudgment)
    store.commit_records([judgment_a.record])

    builder = ContextBuilder(store)
    result = builder.build(
        goal_id=goal.id,
        state_revision=1,
        principal=ContextPrincipal(subject="human:mr.k", project_id=project),
        budget=ContextBudget(token_budget=100_000, tokens_used=0, l0_reserved_tokens=0),
    )
    old_item = next(item for item in result.payload.l1_state if item.record_id == judgment_a.record.id)
    assert "judgment" in old_item.reason_selected.lower(), "이전 판단은 이력/state 항목으로만 온다"

    different = structured(
        {
            "judgment": {
                **judgment_dict(grounds=(evidence.id,)),
                "current_judgment": "이전 판단과 다른 결론",
                "brain_version": "provider-b/1",
            }
        },
        version="provider-b/1",
    )
    # process restart 뒤 새 client/director가 같은 기록 위에서 다른 결론을 내린다.
    client_b = StructuredBrainClient(FakeAdapter("provider-b", [different]), project_id=project)
    judgment_b = client_b.think(wire, "req-b")

    assert isinstance(judgment_b, BrainJudgment)
    assert judgment_b.record.id != judgment_a.record.id
    assert judgment_b.supersedes_record_id is None, "think는 rethink가 아니다 — 이전 판단 채택을 강제하지 않는다"
    assert judgment_b.payload.current_judgment != judgment_a.payload.current_judgment
    stored_a = store.read(judgment_a.record.id)
    assert stored_a is not None
    assert canonical_digest(to_wire(stored_a)) == canonical_digest(to_wire(judgment_a.record)), "원본 판단은 불변이다"


def secondary_client(name: str, conclusion: str) -> StructuredBrainClient:
    response = structured(
        {"judgment": {**judgment_dict(), "current_judgment": conclusion, "brain_version": f"{name}/1"}},
        version=f"{name}/1",
    )
    return StructuredBrainClient(FakeAdapter(name, [response]), project_id=PROJECT)


def test_multiple_secondaries_are_delivered_verbatim_without_majority() -> None:
    # T04-C: 반대 의견이 나와도 Body는 다수결·merge·치환을 하지 않는다 — 각자의
    # MODEL_JUDGMENT evidence로 그대로 전달하고 최종 통합은 Primary의 새 판단 기록이다.
    primary = client(FakeAdapter("primary", [valid_response(version="primary/1")]))
    director = BrainDirector(
        project_id=PROJECT,
        primary=primary,
        secondaries=(secondary_client("secondary-1", "찬성"), secondary_client("secondary-2", "반대")),
    )
    requested_by = director.think(CONTEXT_WIRE, "req-c")
    assert isinstance(requested_by, BrainJudgment)

    engaged = director.engage_secondaries(
        CONTEXT_WIRE, "req-c-2", requested_by=requested_by, governance_decision_id="decision:approve-1"
    )

    assert isinstance(engaged, list)
    assert len(engaged) == 2
    assert [item.evidence.payload.claim for item in engaged] == ["찬성", "반대"], "의견은 그대로 전달된다"
    assert len({item.evidence.id for item in engaged}) == 2, "반대 의견은 각자의 evidence로 남는다"
    assert all(item.has_authority is False for item in engaged)
    assert {str(item.evidence.payload.kind) for item in engaged} == {"MODEL_JUDGMENT"}
    assert len({item.evidence.payload.independence_group for item in engaged}) == 2
    assert all(item.approved_by_governance_id == "decision:approve-1" for item in engaged)

    evidence_ids = [item.evidence.id for item in engaged]
    integrated = structured(
        {
            "judgment": {
                **judgment_dict(grounds=evidence_ids),
                "current_judgment": "Primary가 둘을 종합한 결론",
                "brain_version": "primary/1",
            }
        },
        version="primary/1",
    )
    final = StructuredBrainClient(FakeAdapter("primary-final", [integrated]), project_id=PROJECT).think(
        CONTEXT_WIRE, "req-final"
    )

    assert isinstance(final, BrainJudgment)
    assert final.record.id not in {item.evidence.id for item in engaged}, "최종은 Primary의 판단 기록이다"
    assert set(final.payload.grounds) == set(evidence_ids), "통합 판단은 Secondary 의견을 grounds로 참조한다"


def test_unanimous_secondaries_are_not_collapsed() -> None:
    # T04-C: 같은 의견도 하나의 'consensus' 기록으로 합쳐지지 않는다.
    primary = client(FakeAdapter("primary-u", [valid_response()]))
    director = BrainDirector(
        project_id=PROJECT,
        primary=primary,
        secondaries=(secondary_client("secondary-3", "찬성"), secondary_client("secondary-4", "찬성")),
    )
    requested_by = director.think(CONTEXT_WIRE, "req-u")
    assert isinstance(requested_by, BrainJudgment)

    engaged = director.engage_secondaries(
        CONTEXT_WIRE, "req-u-2", requested_by=requested_by, governance_decision_id="decision:approve-2"
    )

    assert isinstance(engaged, list)
    assert [item.evidence.payload.claim for item in engaged] == ["찬성", "찬성"]
    assert len({item.evidence.id for item in engaged}) == 2, "같은 의견도 각자의 evidence다"


def test_secondary_set_requires_governance_approval() -> None:
    primary = client(FakeAdapter("primary-g", [valid_response()]))
    director = BrainDirector(
        project_id=PROJECT,
        primary=primary,
        secondaries=(secondary_client("secondary-5", "찬성"),),
    )
    requested_by = director.think(CONTEXT_WIRE, "req-g")
    assert isinstance(requested_by, BrainJudgment)

    rejected = director.engage_secondaries(
        CONTEXT_WIRE, "req-g-2", requested_by=requested_by, governance_decision_id=None
    )

    assert isinstance(rejected, BrainFailure)
    assert rejected.kind is BrainFailureKind.UNSUPPORTED_CAPABILITY


def test_secondary_set_fails_closed_when_one_member_fails() -> None:
    # 하나가 실패하면 일부 의견만 남은 자료를 내지 않는다 — 그것은 다수결의 재료가 된다.
    primary = client(FakeAdapter("primary-f", [valid_response()]))
    broken = StructuredBrainClient(FakeAdapter("broken", [BrainResponse(text="고장")]), project_id=PROJECT)
    director = BrainDirector(
        project_id=PROJECT,
        primary=primary,
        secondaries=(secondary_client("secondary-6", "찬성"), broken),
    )
    requested_by = director.think(CONTEXT_WIRE, "req-f")
    assert isinstance(requested_by, BrainJudgment)

    engaged = director.engage_secondaries(
        CONTEXT_WIRE, "req-f-2", requested_by=requested_by, governance_decision_id="decision:approve-3"
    )

    assert isinstance(engaged, BrainFailure)


# ─── R14 structured surface brain / bounded context wire ─────────────


def _r14_fixture(tmp_path: Path):
    from datetime import UTC, datetime

    project = new_id(EntityType.PROJECT)
    store = CanonicalStore(tmp_path / "r14", git_enabled=False)
    rule = build_constitution_rule(project)
    goal = build_goal(project, statement="R14 goal: real context to provider")
    evidence = build_evidence(project, claim="R14 evidence: observed fixture claim")
    store.commit_records([build_project(project, protected_constraints=(rule.id,)), rule, goal, evidence])

    # Explicit package with L1 state + L3 evidence so the renderer has real text to send.
    def item(rid: str) -> ContextItem:
        return ContextItem(
            record_id=rid,
            reason_selected="r14 fixture",
            token_estimate=32,
            disclosure_level=DisclosureLevel.L2_DETAIL,
            applicability=ApplicabilityLevel.MATCH,
        )

    package = ContextPackagePayload(
        goal_id=goal.id,
        state_revision=1,
        l1_state=(item(goal.id),),
        l3_evidence=(item(evidence.id),),
        budget=ContextBudget(token_budget=100_000, tokens_used=64, l0_reserved_tokens=0),
        integrity=IntegrityStatus.COMPLETE,
    )
    pkg_record = Record.create(
        entity_type=EntityType.CONTEXT_PACKAGE,
        project_id=project,
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:r14"),
        payload=package,
        created_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    store.commit_records([pkg_record])

    class _Built:
        record = pkg_record
        payload = package

    built = _Built()

    def load_package(ref: str):
        if ref in (pkg_record.id, "context:r14"):
            return store.read(pkg_record.id)
        return store.read(ref)

    def load_record(rid: str):
        return store.read(rid)

    return project, store, built, goal, evidence, load_package, load_record


def test_r14_a1_provider_payload_has_goal_state_evidence_text(tmp_path: Path) -> None:
    project, store, built, goal, evidence, load_package, load_record = _r14_fixture(tmp_path)
    adapter = FakeAdapter("r14-a", [valid_response(version="r14/1")])
    # Patch judgment grounds to fixture evidence
    adapter = FakeAdapter(
        "r14-a",
        [
            structured(
                {
                    "judgment": judgment_dict(
                        grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))
                    )
                },
                version="r14/1",
            )
        ],
    )
    port = StructuredSurfaceBrainPort(
        adapter,
        project_id=project,
        load_context_package=load_package,
        load_record=load_record,
    )
    outcome = port.think(context_ref=built.record.id, request_signature="req-r14-a1", attempt=1)
    assert outcome.failed is False
    assert port.provider_calls >= 1
    assert adapter.calls, "provider must receive a wire"
    wire = adapter.calls[0]["context"]
    assert isinstance(wire.get("goal"), dict)
    assert "R14 goal" in str(wire["goal"].get("text", ""))
    assert wire.get("evidence"), "evidence snippets required"
    assert any("R14 evidence" in str(e.get("text", "")) for e in wire["evidence"])
    # Not opaque-ID-only: goal/evidence entries carry text, not merely ids
    assert wire["goal"]["id"] == goal.id
    assert all("text" in e and e["text"] for e in wire["evidence"])


def test_r14_a2_low_context_window_does_not_hide_required_omissions(tmp_path: Path) -> None:
    project, store, built, goal, evidence, load_package, load_record = _r14_fixture(tmp_path)
    adapter = FakeAdapter(
        "r14-low",
        [valid_response()],
        caps=capabilities(context_limit=8),  # too small for real snippets
    )
    port = StructuredSurfaceBrainPort(
        adapter,
        project_id=project,
        load_context_package=load_package,
        load_record=load_record,
    )
    outcome = port.think(context_ref=built.record.id, request_signature="req-r14-a2", attempt=1)
    assert outcome.failed is True
    assert "CONTEXT_OVERFLOW" in outcome.detail or "omitted" in outcome.detail
    assert port.provider_calls == 0
    assert adapter.calls == []


def test_r14_a3_malformed_repair_stays_within_budget() -> None:
    # Reuse StructuredBrainClient repair contract already owned by brain.py
    adapter = FakeAdapter(
        "r14-repair",
        [BrainResponse(text="not json"), valid_response()],
    )
    outcome = client(adapter).think(CONTEXT_WIRE, "req-r14-a3")
    assert isinstance(outcome, BrainJudgment)
    assert outcome.repair_attempts == 1
    assert len(adapter.calls) == 2
    # Second failure stops
    adapter2 = FakeAdapter("r14-repair2", [BrainResponse(text="x"), BrainResponse(text="y")])
    outcome2 = client(adapter2).think(CONTEXT_WIRE, "req-r14-a3b")
    assert isinstance(outcome2, BrainFailure)
    assert outcome2.repair_attempts == 1
    assert len(adapter2.calls) == 2


def test_r14_a4_two_providers_read_same_fixture_ids(tmp_path: Path) -> None:
    project, store, built, goal, evidence, load_package, load_record = _r14_fixture(tmp_path)
    digest = canonical_digest(to_wire(built.record))
    resp = structured({"judgment": judgment_dict(grounds=(evidence.id,), context_digest=digest)}, version="p1")
    resp_b = structured({"judgment": judgment_dict(grounds=(evidence.id,), context_digest=digest)}, version="p2")
    a = FakeAdapter("prov-a", [resp], caps=capabilities(provider_model_version="p1"))
    b = FakeAdapter("prov-b", [resp_b], caps=capabilities(provider_model_version="p2"))
    port_a = StructuredSurfaceBrainPort(
        a, project_id=project, load_context_package=load_package, load_record=load_record
    )
    port_b = StructuredSurfaceBrainPort(
        b, project_id=project, load_context_package=load_package, load_record=load_record
    )
    out_a = port_a.think(context_ref=built.record.id, request_signature="a", attempt=1)
    out_b = port_b.think(context_ref=built.record.id, request_signature="b", attempt=1)
    assert out_a.failed is False and out_b.failed is False
    assert a.calls[0]["context"]["goal"]["id"] == b.calls[0]["context"]["goal"]["id"] == goal.id
    evid_a = {e["id"] for e in a.calls[0]["context"]["evidence"]}
    evid_b = {e["id"] for e in b.calls[0]["context"]["evidence"]}
    assert evid_a == evid_b
    assert evidence.id in evid_a


def test_r14_a5_incomplete_context_provider_call_zero(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store = CanonicalStore(tmp_path / "r14-inc", git_enabled=False)
    goal = build_goal(project)
    missing = new_id(EntityType.EVIDENCE)
    from datetime import UTC, datetime

    package = ContextPackagePayload(
        goal_id=goal.id,
        state_revision=1,
        l1_state=(),
        l3_evidence=(),
        budget=ContextBudget(token_budget=1000, tokens_used=0, l0_reserved_tokens=0),
        integrity=IntegrityStatus.INCOMPLETE,
        missing_ids=(missing,),
    )
    pkg_record = Record.create(
        entity_type=EntityType.CONTEXT_PACKAGE,
        project_id=project,
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:r14"),
        payload=package,
        created_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    store.commit_records([build_project(project), goal, pkg_record])
    adapter = FakeAdapter("blocked", [valid_response()])
    port = StructuredSurfaceBrainPort(
        adapter,
        project_id=project,
        load_context_package=lambda ref: store.read(pkg_record.id) if ref in (pkg_record.id, "c") else store.read(ref),
        load_record=store.read,
    )
    outcome = port.think(context_ref=pkg_record.id, request_signature="req-inc", attempt=1)
    assert outcome.failed is True
    assert "CONTEXT_INCOMPLETE" in outcome.detail
    assert port.provider_calls == 0
    assert adapter.calls == []
