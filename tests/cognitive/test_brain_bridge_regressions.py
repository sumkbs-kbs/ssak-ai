"""Context and structured runtime handoff regression contracts."""

from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.brain import render_context_for_brain
from antigravity_k.engine.cognitive.models import ContextItem, to_wire
from antigravity_k.engine.cognitive.store import canonical_digest
from tests.cognitive.test_brain import _r14_fixture


def test_all_selected_layers_reach_provider_without_truncation(tmp_path: Path) -> None:
    # Given a selected constraint and history record with a long required goal.
    project, _, built, goal, evidence, _, load = _r14_fixture(tmp_path)
    goal = goal.model_copy(update={"payload": goal.payload.model_copy(update={"statement": "x" * 800})})
    package = built.payload.model_copy(
        update={
            "l0_constraints": (
                ContextItem(
                    record_id=goal.id, reason_selected="required", token_estimate=1, disclosure_level="L2_DETAIL"
                ),
            ),
            "l2_history": (
                ContextItem(
                    record_id=evidence.id, reason_selected="history", token_estimate=1, disclosure_level="L2_DETAIL"
                ),
            ),
        }
    )
    # When the complete selected context is rendered.
    rendered = render_context_for_brain(
        package,
        project_id=project,
        context_digest="digest",
        load_record=lambda rid: goal if rid == goal.id else load(rid),
        context_limit=100_000,
    )
    # Then no selected layer or record content is silently discarded.
    assert rendered.ready_for_provider
    assert rendered.wire["goal"]["text"] == goal.payload.statement
    assert rendered.wire["constraints"][0]["payload"] == to_wire(goal)["payload"]
    assert rendered.wire["history"][0]["id"] == evidence.id
    assert rendered.wire["payload"] == to_wire(package)


def test_long_required_content_exceeds_window_instead_of_being_shortened(tmp_path: Path) -> None:
    # Given required content too large to fit.
    project, _, built, goal, _, _, load = _r14_fixture(tmp_path)
    goal = goal.model_copy(update={"payload": goal.payload.model_copy(update={"statement": "x" * 20_000})})
    # When only a small provider window is available.
    rendered = render_context_for_brain(
        built.payload,
        project_id=project,
        context_digest="digest",
        load_record=lambda rid: goal if rid == goal.id else load(rid),
        context_limit=1000,
    )
    # Then the provider must not receive a silently shortened contract.
    assert not rendered.ready_for_provider


def test_primary_delta_is_transmitted_and_judgment_persisted(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given a Primary-authored material delta.
    project, store, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    response = structured(
        {
            "judgment": {
                **judgment_dict(grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))),
                "delta": {"ground": True, "description": "new ground"},
            }
        }
    )
    adapter = FakeAdapter("primary", [response])
    port = StructuredSurfaceBrainPort(
        adapter,
        project_id=project,
        load_context_package=load_package,
        load_record=load,
        record_sink=store.commit_records,
    )
    # When thinking through the actual structured client.
    result = port.think(context_ref=built.record.id, request_signature="test", attempt=1)
    # Then the materiality claim and durable judgment survive the bridge.
    assert not result.failed
    assert result.delta.ground
    assert result.delta.description == "new ground"
    assert store.read(result.judgment_ref) is not None


def test_rethink_transmits_actual_feedback_to_provider(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive.runtime import RequestFeedback
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given a prior judgment and a denied request feedback.
    project, store, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    adapter = FakeAdapter(
        "primary",
        [
            structured(
                {
                    "judgment": judgment_dict(
                        grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))
                    )
                }
            )
        ],
    )
    port = StructuredSurfaceBrainPort(adapter, project_id=project, load_context_package=load_package, load_record=load)
    prior = port.think(context_ref=built.record.id, request_signature="test", attempt=1)
    feedback = RequestFeedback("request", "signature", "DENY", False, "authority missing")
    # When Primary rethinks.
    result = port.rethink(
        previous_judgment_ref=prior.judgment_ref,
        feedback_refs=("feedback-id",),
        affected_grounds=(evidence.id,),
        round_index=1,
        feedback=(feedback,),
    )
    # Then the provider sees the actual denial and lineage.
    assert not result.failed
    rethink = adapter.calls[-1]["context"]["rethink"]
    assert rethink["previous_judgment_id"] == prior.judgment_ref
    assert rethink["context_delta"]["feedback"][0]["disposition"] == "DENY"
    assert rethink["affected_ground_ids"] == [evidence.id]


@pytest.mark.parametrize("binding", ["exact", "mismatch", "missing"])
def test_canonical_request_is_preserved_in_runtime_outcome(tmp_path: Path, binding: str) -> None:
    from antigravity_k.engine.cognitive.models import CognitiveRequestPayload, Record
    from antigravity_k.engine.cognitive.references import EntityType
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive._fixtures import PRODUCER
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given a request referenced by Primary's structured judgment.
    project, store, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    request = Record.create(
        entity_type=EntityType.COGNITIVE_REQUEST,
        project_id=project,
        producer=PRODUCER,
        payload=CognitiveRequestPayload(
            request_type="MORE_CONTEXT",
            purpose="inspect",
            target=evidence.id,
            expected_value="resolve",
            expected_decision_impact="choose",
            args_digest="sha256:" + "a" * 64,
        ),
    )
    store.commit_records((request,))
    adapter = FakeAdapter(
        "primary",
        [
            structured(
                {
                    "judgment": {
                        **judgment_dict(grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))),
                        "requests": [request.id],
                    }
                }
            )
        ],
    )
    from antigravity_k.engine.cognitive.runtime import CognitiveRequestEnvelope

    def resolve(record: Record) -> CognitiveRequestEnvelope | None:
        if binding == "missing":
            return None
        return CognitiveRequestEnvelope(
            request_id=record.id,
            request_type=request.payload.request_type,
            purpose=request.payload.purpose,
            target=request.payload.target if binding == "exact" else "other",
            expected_decision_impact=request.payload.expected_decision_impact,
        )

    port = StructuredSurfaceBrainPort(
        adapter, project_id=project, load_context_package=load_package, load_record=load, request_resolver=resolve
    )
    # When the structured judgment is adapted.
    result = port.think(context_ref=built.record.id, request_signature="requests", attempt=1)
    # Then runtime receives the unchanged request identity and decision purpose.
    if binding != "exact":
        assert result.failed
        return
    assert not result.failed
    assert len(result.requests) == 1
    assert result.requests[0].request_id == request.id
    assert result.requests[0].expected_decision_impact == request.payload.expected_decision_impact


def test_invalid_material_delta_repairs_once_without_crashing() -> None:
    from antigravity_k.engine.cognitive.brain import BrainFailure
    from tests.cognitive.test_brain import CONTEXT_WIRE, FakeAdapter, client, judgment_dict, structured

    # Given an invalid semantic delta schema from a provider.
    adapter = FakeAdapter("invalid", [structured({"judgment": {**judgment_dict(), "delta": {"ground": "yes"}}})])
    # When validating the provider response.
    result = client(adapter).think(CONTEXT_WIRE, "invalid")
    # Then protocol repair is bounded and reports failure instead of raising.
    assert isinstance(result, BrainFailure)
    assert len(adapter.calls) == 2


def test_unbound_secondary_request_fails_closed(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive.models import CognitiveRequestPayload, Record
    from antigravity_k.engine.cognitive.references import EntityType
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive._fixtures import PRODUCER
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given a canonical Secondary Brain request.
    project, store, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    request = Record.create(
        entity_type=EntityType.COGNITIVE_REQUEST,
        project_id=project,
        producer=PRODUCER,
        payload=CognitiveRequestPayload(
            request_type="SECONDARY_BRAIN",
            purpose="review",
            target=evidence.id,
            expected_value="independent",
            expected_decision_impact="check",
            args_digest="sha256:" + "a" * 64,
        ),
    )
    store.commit_records((request,))
    adapter = FakeAdapter(
        "primary",
        [
            structured(
                {
                    "judgment": {
                        **judgment_dict(grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))),
                        "requests": [request.id],
                    }
                }
            )
        ],
    )
    port = StructuredSurfaceBrainPort(adapter, project_id=project, load_context_package=load_package, load_record=load)
    # When routing the request to governance.
    result = port.think(context_ref=built.record.id, request_signature="secondary", attempt=1)
    # Then no implicit tool-read execution binding substitutes for Secondary authority.
    assert result.failed
    assert result.requests == ()


def test_judgment_digest_must_match_the_context_actually_sent() -> None:
    from antigravity_k.engine.cognitive.brain import BrainFailure
    from tests.cognitive.test_brain import CONTEXT_WIRE, FakeAdapter, client, judgment_dict, structured

    # Given a provider judgment based on a different context.
    adapter = FakeAdapter("stale", [structured({"judgment": judgment_dict(context_digest="sha256:" + "e" * 64)})])
    wire = {**CONTEXT_WIRE, "context_digest": "sha256:" + "d" * 64}
    # When the response is bound to the context sent to the provider.
    result = client(adapter).think(wire, "binding")
    # Then a stale judgment is rejected after the single repair allowance.
    assert isinstance(result, BrainFailure)
    assert len(adapter.calls) == 2
