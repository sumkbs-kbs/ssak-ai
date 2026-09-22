"""T04 — Brain adapter 교체 시험."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

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
from antigravity_k.engine.cognitive.references import EntityType, new_id

PROJECT = new_id(EntityType.PROJECT)
EVIDENCE_ID = new_id(EntityType.EVIDENCE)
CONTEXT_DIGEST = "sha256:" + "d" * 64
CONTEXT_WIRE: dict[str, object] = {
    "schema_version": "1.0",
    "entity_type": "ContextPackage",
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
