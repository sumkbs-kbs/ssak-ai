"""Surface lifecycle forwarding and restoration contracts."""

from dataclasses import replace

import pytest

from antigravity_k.engine.cognitive.experience import ExperienceContractError
from antigravity_k.engine.cognitive.models import ExperiencePayload
from antigravity_k.engine.cognitive_surface import CognitiveSurfaceAdapter
from tests.cognitive._fixtures import build_evidence, build_experience
from tests.cognitive.test_surface import ACTIVE_PROJECT_ID, episode_request


def test_restore_filters_non_experience_but_reports_conflicting_history():
    adapter = CognitiveSurfaceAdapter()
    record = build_experience(ACTIVE_PROJECT_ID)
    assert adapter.restore_experience_records((build_evidence(ACTIVE_PROJECT_ID), record)) == 1
    corrupted = record.model_copy(update={"payload": ExperiencePayload(trigger="conflicting historical core")})
    with pytest.raises(ExperienceContractError):
        adapter.restore_experience_records((corrupted,))


def test_surface_passes_explicit_lineage_to_episode_plan():
    request = replace(
        episode_request(),
        decision_ref="decision:known",
        governance_ref="governance:known",
        outcome_ref="outcome:known",
        observation_refs=("observation:known",),
        evidence_refs=("evidence:known",),
    )
    plan = CognitiveSurfaceAdapter()._episode_request(request).plan
    assert plan.decision_ref == request.decision_ref
    assert plan.governance_ref == request.governance_ref
    assert plan.outcome_ref == request.outcome_ref
    assert plan.observation_refs == request.observation_refs
    assert plan.evidence_refs == request.evidence_refs


@pytest.mark.parametrize("observed,succeeded,expected_count", [(True, True, 1), (False, None, 0)])
def test_late_observation_forms_one_canonical_core_on_replay(
    tmp_path, monkeypatch, observed, succeeded, expected_count
):
    from fastapi.testclient import TestClient

    from antigravity_k.api.routes import cognitive_active_api as api
    from antigravity_k.engine.cognitive.models import IntegrityStatus
    from antigravity_k.engine.cognitive.references import REL_ACTION, REL_OBSERVATION, REL_RECEIPT, EntityType
    from tests.cognitive.test_active_api import BASE, build_active_fixture

    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    client.post(
        BASE + "/execute",
        headers=headers,
        json={
            "request_id": "request-1",
            "action_digest": fixture.intent.to_intent().args_digest(),
            "reason": "recovery test",
        },
    )
    pending = client.get(BASE + "/pending", headers=headers).json()[0]
    body = {
        "action_key": pending["action_key"],
        "expected_receipt_id": pending["receipt_id"],
        "observed": observed,
        "succeeded": succeeded,
        "detail": "file exists",
        "reason": "verified",
    }
    first = client.post(BASE + "/observe", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post(BASE + "/observe", headers=headers, json=body)
    assert second.status_code == 200, second.text
    observation_id = first.json()["observation_record_id"]
    cores = [
        record
        for record in fixture.store.list_committed(ACTIVE_PROJECT_ID)
        if record.entity_type == EntityType.EXPERIENCE
        and any(ref.relation == REL_OBSERVATION and ref.target_id == observation_id for ref in record.references)
    ]
    assert len(cores) == expected_count
    if expected_count == 0:
        selections = [
            record.payload.selection
            for record in fixture.store.list_committed(ACTIVE_PROJECT_ID)
            if record.entity_type == EntityType.EVENT
            and record.payload.selection is not None
            and observation_id in record.payload.selection.note
        ]
        assert len(selections) == 1
        assert selections[0].disposition.value == "DEFERRED"
        return
    core = cores[0]
    assert core.payload.integrity == IntegrityStatus.INCOMPLETE
    assert "decision_ref" in core.payload.missing_references
    assert any(ref.relation == REL_ACTION for ref in core.references)
    observation = fixture.store.read(observation_id)
    assert any(
        ref.relation == REL_RECEIPT and ref.target_id == first.json()["receipt_id"] for ref in observation.references
    )
