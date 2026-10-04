"""Trusted boot and canonical revision integration tests."""

from fastapi import FastAPI

from antigravity_k.api import dependencies


def test_boot_without_trusted_configuration_leaves_active_uninstalled():
    # Given an ordinary app with no explicit project configuration.
    app = FastAPI()
    # When the real production bootstrap runs.
    dependencies.bootstrap_cognitive_active(app)
    # Then ACTIVE remains unavailable.
    assert not hasattr(app.state, "cognitive_active_service")


from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antigravity_k.api.routes import cognitive_active_api as api
from antigravity_k.api.routes.cognitive_surface_api import router
from antigravity_k.engine.cognitive.models import (
    AuthorityProfilePayload,
    DecisionPayload,
    EventPayload,
    LoopState,
    Producer,
    ProducerKind,
    Record,
)
from antigravity_k.engine.cognitive.references import REL_SUPERSEDES, EntityType, Reference
from antigravity_k.engine.cognitive_active_composition import CanonicalHeadAnchors, ProjectActiveConfiguration
from tests.cognitive._fixtures import assurance
from tests.cognitive.test_active_api import BASE, build_active_fixture
from tests.cognitive.test_surface import ACTIVE_PROJECT_ID, StubThink, active_settings


def boot(root: Path, *, authorized_digest: str | None = None):
    fixture = build_active_fixture(root)
    prior_service = fixture.app.state.cognitive_active_service
    adapter = prior_service.build_adapter(lambda *args: True)
    intent = fixture.intent.to_intent()
    grant = adapter.authority_resolver(intent, datetime.now(UTC)).grant
    producer = Producer(kind=ProducerKind.HUMAN, actor_id="human:owner")
    decision = Record.create(
        entity_type=EntityType.DECISION,
        project_id=ACTIVE_PROJECT_ID,
        producer=producer,
        payload=DecisionPayload(
            selected_action="write file",
            why_selected="approved",
            expected_outcome="file",
            unknowns_assessed=True,
            readiness=assurance().model_copy(
                update={
                    "action_digest": authorized_digest or intent.args_digest(),
                    "authority_revision": 1,
                }
            ),
        ),
    )
    state = Record.create(
        entity_type=EntityType.EVENT,
        project_id=ACTIVE_PROJECT_ID,
        producer=producer,
        payload=EventPayload(sequence=1, episode_id="state", state=LoopState.ACTION, state_revision=1),
    )
    authority = Record.create(
        entity_type=EntityType.AUTHORITY_PROFILE,
        project_id=ACTIVE_PROJECT_ID,
        producer=producer,
        payload=AuthorityProfilePayload(grants=(grant,), revision=1),
    )
    fixture.store.commit_records((decision, state, authority))
    config = ProjectActiveConfiguration(
        settings=active_settings(),
        project_root=root,
        runtime_root=root / "runtime",
        owner_subject="owner",
        principal="body:surface",
        store=fixture.store,
        executor=adapter.dispatch_port.executor,
        think=StubThink(),
        anchors=CanonicalHeadAnchors(decision.id, state.id, authority.id),
        prepared=prior_service.prepared,
    )
    app = FastAPI()
    app.include_router(router)
    app.state.cognitive_active_configuration = config
    dependencies.bootstrap_cognitive_active(app)
    return fixture, app, config, (decision, state, authority)


def execute(fixture, app):
    return TestClient(app).post(
        BASE + "/execute",
        headers={"Authorization": "Bearer " + fixture.tokens.issue_token("owner")},
        json={"request_id": "request-1", "action_digest": fixture.intent.to_intent().args_digest(), "reason": "QA"},
    )


def test_trusted_boot_executes_once_and_restart_keeps_durable_claim(tmp_path, monkeypatch):
    # Given the production installer and real committed project heads.
    fixture, app, config, _ = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    # When an authenticated owner executes the server-prepared action.
    first = execute(fixture, app)
    # Then the existing executor produces one effect and a new installation preserves its claim.
    assert first.status_code == 200, first.text
    assert first.json()["dispatched_actions"] == 1, first.text
    assert (tmp_path / "effect.txt").read_text() == "one effect"
    dependencies.bootstrap_cognitive_active(app)
    replay = execute(fixture, app)
    assert replay.json()["refusal"] == "DUPLICATE_ACTION", replay.text


@pytest.mark.parametrize("head_index", [0, 1, 2])
def test_actual_canonical_revision_change_blocks_effect(tmp_path, monkeypatch, head_index):
    # Given a reviewed prepared action and its canonical source heads.
    fixture, app, _, heads = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    old = heads[head_index]
    payload = old.payload
    if head_index == 0:
        payload = payload.model_copy(
            update={"readiness": payload.readiness.model_copy(update={"decision_revision": 2})}
        )
    elif head_index == 1:
        payload = payload.model_copy(update={"state_revision": 2})
    else:
        payload = payload.model_copy(update={"revision": 2})
    updated = Record.create(
        entity_type=old.entity_type,
        project_id=old.project_id,
        producer=old.producer,
        payload=payload,
        references=(Reference(relation=REL_SUPERSEDES, target_id=old.id, expected_type=old.entity_type),),
    )
    fixture.store.commit_records((updated,))
    # When the action is executed after a real canonical record publication.
    response = execute(fixture, app)
    # Then stale approval cannot produce a tool effect.
    assert response.status_code in (200, 409), response.text
    assert not (tmp_path / "effect.txt").exists(), response.text
    if response.status_code == 200:
        assert response.json()["dispatched_actions"] == 0


def test_missing_canonical_head_fails_closed(tmp_path, monkeypatch):
    fixture, app, config, _ = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    app.state.cognitive_active_configuration = replace(
        config, anchors=replace(config.anchors, state_event_id="missing")
    )
    dependencies.bootstrap_cognitive_active(app)
    response = execute(fixture, app)
    assert response.status_code == 409, response.text
    assert not (tmp_path / "effect.txt").exists()


def test_revoked_canonical_grant_blocks_effect(tmp_path, monkeypatch):
    # Given a once-authorized project whose grant has now been revoked canonically.
    fixture, app, _, heads = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    old = heads[2]
    revoked = old.payload.grants[0].model_copy(update={"revoked_at": datetime.now(UTC), "revision": 2})
    updated = Record.create(
        entity_type=old.entity_type,
        project_id=old.project_id,
        producer=old.producer,
        payload=old.payload.model_copy(update={"revision": 2, "grants": (revoked,)}),
        references=(Reference(relation=REL_SUPERSEDES, target_id=old.id, expected_type=old.entity_type),),
    )
    fixture.store.commit_records((updated,))
    # When the owner tries the old prepared request.
    response = execute(fixture, app)
    # Then the live grant denies the effect despite an authenticated session.
    assert response.status_code in (200, 409), response.text
    assert not (tmp_path / "effect.txt").exists()


def test_trusted_root_mismatch_rejected_at_boot(tmp_path):
    fixture, app, config, _ = boot(tmp_path)
    app.state.cognitive_active_configuration = replace(config, project_root=tmp_path / "other")
    with pytest.raises(RuntimeError, match="root"):
        dependencies.bootstrap_cognitive_active(app)


def test_ambiguous_head_rejected_without_effect(tmp_path, monkeypatch):
    fixture, app, _, heads = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    old = heads[1]
    for revision in (2, 3):
        fixture.store.commit_records(
            (
                Record.create(
                    entity_type=old.entity_type,
                    project_id=old.project_id,
                    producer=old.producer,
                    payload=old.payload.model_copy(update={"state_revision": revision}),
                    references=(Reference(relation=REL_SUPERSEDES, target_id=old.id, expected_type=old.entity_type),),
                ),
            )
        )
    response = execute(fixture, app)
    assert response.status_code == 409, response.text
    assert not (tmp_path / "effect.txt").exists()


def test_canonical_policy_head_version_is_loaded_independently(tmp_path):
    from antigravity_k.engine.cognitive.models import PolicyPayload, PolicyTarget
    from antigravity_k.engine.cognitive_active_composition import CanonicalCurrentHeads

    fixture, app, config, heads = boot(tmp_path)
    policy = Record.create(
        entity_type=EntityType.POLICY,
        project_id=ACTIVE_PROJECT_ID,
        producer=heads[0].producer,
        payload=PolicyPayload(target=next(iter(PolicyTarget)), rule="bounded execution", version="v1"),
    )
    fixture.store.commit_records((policy,))
    resolver = CanonicalCurrentHeads(
        fixture.store, ACTIVE_PROJECT_ID, config.principal, replace(config.anchors, policy_id=policy.id)
    )
    changed = Record.create(
        entity_type=EntityType.POLICY,
        project_id=ACTIVE_PROJECT_ID,
        producer=policy.producer,
        payload=policy.payload.model_copy(update={"version": "v2"}),
        references=(Reference(relation=REL_SUPERSEDES, target_id=policy.id, expected_type=EntityType.POLICY),),
    )
    fixture.store.commit_records((changed,))
    current = resolver.freshness(fixture.intent.to_intent(), datetime.now(UTC))
    assert current.policy_version == "v2"
    assert fixture.intent.to_intent().policy_version is None


def test_canonical_authorized_digest_mismatch_blocks_unchanged_revisions(tmp_path, monkeypatch):
    fixture, app, _, _ = boot(tmp_path, authorized_digest="sha256:" + "0" * 64)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    response = execute(fixture, app)
    assert response.status_code == 200, response.text
    assert response.json()["refusal"] == "STALE_READINESS", response.text
    assert not (tmp_path / "effect.txt").exists()


def test_trusted_brain_adapter_boot_persists_canonical_judgment(tmp_path):
    from antigravity_k.engine.cognitive.models import to_wire
    from antigravity_k.engine.cognitive.store import canonical_digest
    from tests.cognitive.test_brain import FakeAdapter, _r14_fixture, judgment_dict, structured

    fixture, app, config, _ = boot(tmp_path / "active")
    project, store, built, _, evidence, _, _ = _r14_fixture(tmp_path / "brain")
    brain = FakeAdapter(
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
    app.state.cognitive_active_configuration = replace(
        config,
        settings=replace(config.settings, project_id=project),
        store=store,
        prepared={},
        think=None,
        brain_adapter=brain,
    )
    dependencies.bootstrap_cognitive_active(app)
    adapter = app.state.cognitive_active_service.build_adapter(lambda *args: True)
    result = adapter.think.think(context_ref=built.record.id, request_signature="boot", attempt=1)
    assert not result.failed
    assert store.read(result.judgment_ref) is not None
    assert adapter.rethink is adapter.think


def test_canonical_not_ready_decision_cannot_authorize_ready_request(tmp_path, monkeypatch):
    from antigravity_k.engine.cognitive.models import CheckStatus, ReadinessVerdict

    original = assurance()
    blocked = original.model_copy(
        update={
            "verdict": ReadinessVerdict.NOT_READY,
            "check_results": (
                original.check_results[0].model_copy(update={"status": CheckStatus.FAIL}),
                *original.check_results[1:],
            ),
        }
    )
    monkeypatch.setattr("tests.cognitive.test_active_composition.assurance", lambda: blocked)
    fixture, app, _, _ = boot(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    response = execute(fixture, app)
    assert response.status_code == 409, response.text
    assert not (tmp_path / "effect.txt").exists()
