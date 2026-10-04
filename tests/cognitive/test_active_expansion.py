"""Production composition: canonical context through read receipt and Primary rethink."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from antigravity_k.api import dependencies
from antigravity_k.api.routes import cognitive_active_api as api
from antigravity_k.engine.cognitive.actions import PolicyClearance
from antigravity_k.engine.cognitive.authority import AuthorityProfile, AuthorityQuery
from antigravity_k.engine.cognitive.models import AuthorityDimension, CognitiveRequestPayload, Record, to_wire
from antigravity_k.engine.cognitive.references import EntityType
from antigravity_k.engine.cognitive.store import canonical_digest
from antigravity_k.engine.cognitive_active_composition import CanonicalHeadAnchors
from antigravity_k.engine.cognitive_active_requests import TrustedCognitiveRequestBinding
from antigravity_k.tools.system_tools import ReadFileTool
from tests.cognitive.test_active_api import BASE
from tests.cognitive.test_active_composition import boot
from tests.cognitive.test_brain import FakeAdapter, _r14_fixture, judgment_dict, structured
from tests.cognitive.test_surface import ACTIVE_PROJECT_ID


def expansion_setup(tmp_path, *, binding_digest_matches=True, bound=True):
    fixture, app, config, heads = boot(tmp_path / "active")
    _, context_store, built, goal, evidence, _, _ = _r14_fixture(tmp_path / "context")
    context_records = [
        record.model_copy(update={"project_id": ACTIVE_PROJECT_ID})
        for record in context_store.list_committed()
        if record.entity_type != EntityType.PROJECT
    ]
    fixture.store.commit_records(context_records)
    package = fixture.store.read(built.record.id)
    config.executor.tool_registry.install(ReadFileTool())
    (tmp_path / "active" / "input.txt").write_text("canonical read evidence")
    read_request = replace(
        fixture.intent,
        action_key="cognitive-read-1",
        tool="read_file",
        arguments={"file_path": "input.txt"},
        scope="input.txt",
        dimension=AuthorityDimension.TOOL_READ,
    )
    action = read_request.to_intent()
    grant = (
        heads[2]
        .payload.grants[0]
        .model_copy(update={"dimension": AuthorityDimension.TOOL_READ, "resource_scope": "input.txt"})
    )
    authority_record = Record.create(
        entity_type=EntityType.AUTHORITY_PROFILE,
        project_id=ACTIVE_PROJECT_ID,
        producer=heads[2].producer,
        payload=heads[2].payload.model_copy(update={"grants": (grant,)}),
    )
    profile = AuthorityProfile.from_record(authority_record)
    authority = profile.evaluate(
        AuthorityQuery(
            subject=config.principal,
            dimension=action.dimension,
            resource_scope=action.scope,
            operation=action.operation,
        ),
        now=datetime.now(UTC),
    )
    ready = replace(
        fixture.intent.readiness,
        freshness=replace(fixture.intent.readiness.freshness, action_digest=action.args_digest()),
    )
    action = replace(action, readiness=ready, clearance=PolicyClearance(authority=authority, revision=1))
    decision = Record.create(
        entity_type=EntityType.DECISION,
        project_id=ACTIVE_PROJECT_ID,
        producer=heads[0].producer,
        payload=heads[0].payload.model_copy(
            update={"readiness": heads[0].payload.readiness.model_copy(update={"action_digest": action.args_digest()})}
        ),
    )
    cognitive_request = Record.create(
        entity_type=EntityType.COGNITIVE_REQUEST,
        project_id=ACTIVE_PROJECT_ID,
        producer=heads[0].producer,
        payload=CognitiveRequestPayload(
            request_type="TOOL",
            purpose="read evidence",
            target="input.txt",
            expected_value="file facts",
            expected_decision_impact="verify current state",
            args_digest=action.args_digest() if binding_digest_matches else "sha256:" + "0" * 64,
        ),
    )
    fixture.store.commit_records((authority_record, decision, cognitive_request))
    primary_judgment = judgment_dict(grounds=(evidence.id,), context_digest=canonical_digest(to_wire(package)))
    brain = FakeAdapter(
        "deterministic-protocol-primary",
        [
            structured(
                {
                    "judgment": {
                        **primary_judgment,
                        "requests": [cognitive_request.id],
                        "delta": {"ground": True, "description": "Need canonical read evidence"},
                    }
                }
            ),
            structured({"judgment": {**primary_judgment, "current_judgment": "Read receipt integrated"}}),
        ],
    )
    prepared = {
        key: replace(item, request=replace(item.request, context_ref=package.id, goal_ref=goal.id, simple=False))
        for key, item in config.prepared.items()
    }
    app.state.cognitive_active_configuration = replace(
        config,
        think=None,
        brain_adapter=brain,
        prepared=prepared,
        cognitive_requests={
            cognitive_request.id: TrustedCognitiveRequestBinding(
                action, CanonicalHeadAnchors(decision.id, heads[1].id, authority_record.id)
            )
        }
        if bound
        else {},
    )
    dependencies.bootstrap_cognitive_active(app)
    return fixture, app, brain, cognitive_request, action


def run_request(fixture, app):
    return TestClient(app).post(
        BASE + "/execute",
        headers={"Authorization": "Bearer " + fixture.tokens.issue_token("owner")},
        json={
            "request_id": "request-1",
            "action_digest": fixture.intent.to_intent().args_digest(),
            "reason": "read QA",
        },
    )


def test_structured_request_executes_actual_read_and_rethink_receives_canonical_receipt(tmp_path, monkeypatch):
    fixture, app, brain, request, action = expansion_setup(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    response = run_request(fixture, app)
    assert response.status_code == 200, response.text
    assert len(brain.calls) == 2, response.text
    delta = brain.calls[1]["context"]["rethink"]["context_delta"]
    assert delta["feedback"][0]["request_id"] == request.id
    assert delta["feedback"][0]["executed"] is True, delta
    receipts = delta["receipts"]
    assert len(receipts) == 1
    receipt = fixture.store.read(receipts[0]["id"])
    assert receipt.payload.action_id == action.action_id
    assert "canonical read evidence" in receipt.payload.detail
    assert fixture.store.read(action.action_id) is not None
    from antigravity_k.engine.cognitive.action_recovery_records import receipt_from_record
    from antigravity_k.engine.cognitive.store import CanonicalStore

    reopened = CanonicalStore(fixture.store.root)
    restored = receipt_from_record(reopened.read(receipt.id))
    assert restored.detail == receipt.payload.detail
    assert receipts[0]["payload"]["detail"] == restored.detail
    assert not (tmp_path / "active" / "effect.txt").exists()


@pytest.mark.parametrize("bound,matches", [(False, True), (True, False)])
def test_unbound_or_digest_mismatched_request_never_dispatches(tmp_path, monkeypatch, bound, matches):
    fixture, app, brain, _, action = expansion_setup(tmp_path, bound=bound, binding_digest_matches=matches)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    response = run_request(fixture, app)
    assert response.status_code in (200, 409), response.text
    assert fixture.store.read(action.action_id) is None
    assert len(brain.calls) == 1
    assert not (tmp_path / "active" / "effect.txt").exists()


@pytest.mark.parametrize("delta", [{"risk": True}, {"action": True}, {"risk": True, "action": True}])
def test_rethink_changed_action_or_risk_without_new_plan_cannot_dispatch_final_action(tmp_path, monkeypatch, delta):
    # Given a real read request and a Primary response changing risk/action with no new plan.
    fixture, app, brain, request, action = expansion_setup(tmp_path)
    response = brain._responses[-1]
    brain._responses[-1] = replace(
        response,
        structured={
            "judgment": {
                **response.structured["judgment"],
                "delta": delta,
            }
        },
    )
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    # When HTTP execution completes read evidence and integrates the changed judgment.
    result = run_request(fixture, app)
    # Then the read remains recorded, but the stale final write never executes.
    assert result.status_code == 200, result.text
    assert len(brain.calls) == 2
    assert fixture.store.read(action.action_id) is not None
    assert not (tmp_path / "active" / "effect.txt").exists()
    assert result.json()["action_status"] is None
    assert result.json()["dispatched_actions"] == 0
