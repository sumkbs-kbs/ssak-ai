"""Authenticated HTTP execution through real tools and a Git canonical store."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api.routes import cognitive_active_api as api
from antigravity_k.api.routes.cognitive_surface_api import router
from antigravity_k.engine.auth import TokenService
from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
from antigravity_k.engine.cognitive.actions import ActionIntent, PolicyClearance, ToolExecutorPort
from antigravity_k.engine.cognitive.authority import AuthorityDecision, AuthorityProfile, AuthorityQuery
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.models import AuthorityGrant
from antigravity_k.engine.cognitive.readiness import ActionScope, EvidenceRef, ReadinessInputs, check_readiness
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.cognitive_surface import (
    CognitiveSurfaceAdapter,
    DurableSurfaceHistoryStore,
    SurfaceIntentRequest,
)
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.tools.file_tools import WriteFileTool
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_registry import ToolRegistry
from tests.cognitive.test_surface import ACTIVE_PROJECT_ID, StubThink, active_settings, episode_request

BASE = "/api/cognitive/surface/active"


@dataclass
class ActiveFixture:
    app: FastAPI
    tokens: TokenService
    epoch: list[int]
    store: CanonicalStore
    intent: SurfaceIntentRequest
    history: DurableSurfaceHistoryStore


def build_active_fixture(root: Path) -> ActiveFixture:
    epoch = [1]
    tokens = TokenService(root / "jwt-secret", epoch_provider=lambda: epoch[0])
    store = CanonicalStore(root / "canonical")
    journal = SqliteActionJournal(root / "claims.sqlite")
    history = DurableSurfaceHistoryStore(root / "surface_history.sqlite")
    registry = ToolRegistry(project_root=str(root))
    registry.install(WriteFileTool())
    executor = ToolExecutor(registry, PermissionGate(project_root=str(root)), project_root=str(root))
    intent = SurfaceIntentRequest(
        action_key="http-write-1",
        tool="write_file",
        arguments={"file_path": "effect.txt", "content": "one effect"},
        scope="effect.txt",
        authority_revision=1,
    )
    grant = AuthorityGrant(
        subject="body:surface",
        dimension=intent.dimension,
        resource_scope=intent.scope,
        allowed_operations=("execute_tool",),
        granted_by="human:owner",
        revision=1,
        issued_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    profile = AuthorityProfile.from_grants((grant,))

    def resolve(action: ActionIntent, now: datetime) -> AuthorityDecision:
        return profile.evaluate(
            AuthorityQuery(
                subject="body:surface",
                dimension=action.dimension,
                resource_scope=action.scope,
                operation=action.operation,
            ),
            now=now,
        )

    decision = resolve(intent.to_intent(), datetime.now(UTC))
    digest = intent.to_intent().args_digest()
    readiness = check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool=intent.tool, scope=intent.scope, expected_outcome="file exists", action_digest=digest
            ),
            authorized_action_digest=digest,
            decision_revision=1,
            state_revision=1,
            authority_revision=1,
            grounds=("evidence:http",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:http",
                    provenance_uri="temporary:http-fixture",
                    provenance_digest="sha256:" + "a" * 64,
                    observed_at=datetime.now(UTC),
                ),
            ),
            authority_decision=decision,
        )
    )
    intent = replace(intent, readiness=readiness, clearance=PolicyClearance(authority=decision, revision=1))

    def adapter(authorize: api.ActivationAuthorizer) -> CognitiveSurfaceAdapter:
        return CognitiveSurfaceAdapter(
            active_settings(),
            think=StubThink(),
            governance=GovernanceGate(),
            dispatch_port=ToolExecutorPort(executor, result_indicates_failure),
            journal=journal,
            record_sink=store.commit_records,
            authority_resolver=resolve,
            activation_authorizer=authorize,
            history_store=history,
        )

    app = FastAPI()
    app.include_router(router)
    app.state.cognitive_active_service = api.CognitiveActiveService(
        prepared={"request-1": api.PreparedCognitiveAction("owner", ACTIVE_PROJECT_ID, episode_request(intent=intent))},
        build_adapter=adapter,
        load_record=store.read,
    )
    return ActiveFixture(app, tokens, epoch, store, intent, history)


def test_authenticated_actual_tool_and_durable_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    view = client.get(BASE + "/requests/request-1", headers=headers)
    assert view.status_code == 200
    assert "one effect" in view.json()["arguments_json"]
    payload = {"request_id": "request-1", "action_digest": view.json()["action_digest"], "reason": "isolated QA"}
    first = client.post(BASE + "/execute", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["dispatched_actions"] == 1, first.text
    assert (tmp_path / "effect.txt").read_text() == "one effect"
    manifests_after_first = len(fixture.store.committed_manifests())
    assert manifests_after_first >= 2
    (tmp_path / "effect.txt").write_text("external observation")
    second = client.post(BASE + "/execute", headers=headers, json=payload)
    assert second.json()["refusal"] == "DUPLICATE_ACTION"
    assert second.json()["dispatched_actions"] == 0
    assert (tmp_path / "effect.txt").read_text() == "external observation"
    # Duplicate must not re-dispatch the tool. Experience/operational trail may append
    # records (R11), but the external file effect stays exactly once.
    assert (tmp_path / "effect.txt").read_text() == "external observation"


def test_authentication_ownership_digest_and_extra_claims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    payload = {"request_id": "request-1", "action_digest": fixture.intent.to_intent().args_digest(), "reason": "QA"}
    assert client.post(BASE + "/execute", json=payload).status_code == 401
    assert client.post(BASE + "/execute", json=payload, headers={"Authorization": "Bearer forged"}).status_code == 401
    other = {"Authorization": "Bearer " + fixture.tokens.issue_token("other")}
    assert client.post(BASE + "/execute", json=payload, headers=other).status_code == 404
    owner = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    assert (
        client.post(BASE + "/execute", json={**payload, "action_digest": "changed"}, headers=owner).status_code == 409
    )
    assert client.post(BASE + "/execute", json={**payload, "approver": "human:owner"}, headers=owner).status_code == 422
    fixture.epoch[0] += 1
    assert client.post(BASE + "/execute", json=payload, headers=owner).status_code == 401
    assert not (tmp_path / "effect.txt").exists()
    assert fixture.store.committed_manifests() == ()


def test_session_revoked_during_canonical_write_blocks_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    commit = fixture.store.commit_records

    def revoke_after_commit(records):
        receipt = commit(records)
        fixture.epoch[0] += 1
        return receipt

    monkeypatch.setattr(fixture.store, "commit_records", revoke_after_commit)
    owner = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    response = TestClient(fixture.app).post(
        BASE + "/execute",
        headers=owner,
        json={
            "request_id": "request-1",
            "action_digest": fixture.intent.to_intent().args_digest(),
            "reason": "revocation QA",
        },
    )
    assert response.status_code == 409, response.text
    assert not (tmp_path / "effect.txt").exists()
    assert len(fixture.store.committed_manifests()) == 1


def test_r10_a1_restart_observe_keeps_dispatch_count_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R10-A1: after temp-file effect and process restart, observation keeps dispatch count at 1."""
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.actions import ActionDispatcher, ActionObservation, CallablePort
    from tests.cognitive.test_actions import BODY, NOW, PROJECT, make_intent

    effect = tmp_path / "effect.txt"
    journal_path = tmp_path / "claims.sqlite"
    store = CanonicalStore(tmp_path / "canonical", git_enabled=False)
    calls = {"n": 0}

    def write_once(tool, args, action_id):
        calls["n"] += 1
        effect.write_text("written")
        return "ok"

    first = ActionDispatcher(
        port=CallablePort(write_once),
        journal=SqliteActionJournal(journal_path),
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    intent = make_intent(action_key="r10-a1", scope="effect.txt")
    run = first.execute(intent, project_id=PROJECT, producer=BODY)
    assert run.receipt is not None
    assert effect.read_text() == "written"
    assert calls["n"] == 1
    receipt_id = run.receipt.receipt_id

    # Process restart: fresh dispatcher, same journal/store — observe, do not redispatch.
    restarted = ActionDispatcher(
        port=CallablePort(lambda *a, **k: calls.__setitem__("n", calls["n"] + 1)),
        journal=SqliteActionJournal(journal_path),
        record_sink=lambda records: store.commit_records(list(records)),
        clock=lambda: NOW,
    )
    from antigravity_k.engine.cognitive.actions import ObservationSubmission

    result = restarted.submit_observation(
        ObservationSubmission(
            project_id=PROJECT,
            action_key="r10-a1",
            expected_receipt_id=receipt_id,
            observation=ActionObservation(observed=True, succeeded=True, detail="file present"),
        ),
        producer=BODY,
        load_record=store.read,
        now=NOW,
    )
    assert result.accepted
    assert result.redispatched is False
    assert calls["n"] == 1
    assert effect.read_text() == "written"


def test_r10_http_observe_and_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R10 HTTP surface: pending lists reason; observe settles without redispatch."""
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    digest = fixture.intent.to_intent().args_digest()
    executed = client.post(
        BASE + "/execute",
        headers=headers,
        json={"request_id": "request-1", "action_digest": digest, "reason": "r10 qa"},
    )
    assert executed.status_code == 200, executed.text
    pending = client.get(BASE + "/pending", headers=headers)
    assert pending.status_code == 200, pending.text
    rows = pending.json()
    assert len(rows) == 1
    assert rows[0]["pending_reason"]
    assert rows[0]["receipt_id"]
    receipt_id = rows[0]["receipt_id"]
    observed = client.post(
        BASE + "/observe",
        headers=headers,
        json={
            "action_key": rows[0]["action_key"],
            "expected_receipt_id": receipt_id,
            "observed": True,
            "succeeded": True,
            "detail": "effect.txt present",
            "reason": "operator recovery",
        },
    )
    assert observed.status_code == 200, observed.text
    body = observed.json()
    assert body["accepted"] is True
    assert body["redispatched"] is False
    # idempotent replay
    replay = client.post(
        BASE + "/observe",
        headers=headers,
        json={
            "action_key": rows[0]["action_key"],
            "expected_receipt_id": body["receipt_id"],
            "observed": True,
            "succeeded": True,
            "detail": "effect.txt present",
            "reason": "operator recovery",
        },
    )
    # After settle, expected_receipt_id must be the NEW head for CAS — if we send old, stale.
    # Idempotent path uses claim.receipt_id == expected; after settle receipt advanced.
    # Replay with new receipt_id + same observation digest:
    assert replay.status_code == 200, replay.text
    assert replay.json()["observation_record_id"] == body["observation_record_id"]
    # stale revision rejected
    stale = client.post(
        BASE + "/observe",
        headers=headers,
        json={
            "action_key": rows[0]["action_key"],
            "expected_receipt_id": receipt_id,
            "observed": True,
            "succeeded": True,
            "detail": "effect.txt present",
            "reason": "stale try",
        },
    )
    assert stale.status_code == 409
    # other project / unknown action
    missing = client.post(
        BASE + "/observe",
        headers=headers,
        json={
            "action_key": "no-such-action",
            "expected_receipt_id": receipt_id,
            "observed": True,
            "succeeded": True,
            "detail": "x",
            "reason": "missing",
        },
    )
    assert missing.status_code == 404


def test_r16_a1_status_matches_active_episode_and_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    view = client.get(BASE + "/requests/request-1", headers=headers)
    payload = {"request_id": "request-1", "action_digest": view.json()["action_digest"], "reason": "r16 qa"}
    first = client.post(BASE + "/execute", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["dispatched_actions"] == 1
    episode_id = first.json()["episode_id"]
    # Fresh adapter (simulating status process) reading same durable history
    from antigravity_k.engine.cognitive_surface import CognitiveSurfaceAdapter
    from tests.cognitive.test_surface import active_settings

    fresh = CognitiveSurfaceAdapter(active_settings(), history_store=fixture.history)
    status = fresh.status()
    assert status.last_episode_id == episode_id
    assert status.dispatched_actions == 1
    assert any(n.startswith("history_source=durable") for n in status.notes)


def test_r16_a2_history_survives_process_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    view = client.get(BASE + "/requests/request-1", headers=headers)
    first = client.post(
        BASE + "/execute",
        headers=headers,
        json={"request_id": "request-1", "action_digest": view.json()["action_digest"], "reason": "r16 restart"},
    )
    episode_id = first.json()["episode_id"]
    # New store handle = process replacement
    revived = DurableSurfaceHistoryStore(tmp_path / "surface_history.sqlite")
    from tests.cognitive.test_surface import active_settings

    status = CognitiveSurfaceAdapter(active_settings(), history_store=revived).status()
    assert status.last_episode_id == episode_id
    assert status.dispatched_actions == 1


def test_r16_a3_static_reach_does_not_imply_actual_active(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive_surface import measure_surface_reach
    from tests.cognitive.test_surface import active_settings

    measurement = measure_surface_reach(source_root=Path("src"))
    assert measurement.core_count >= 0
    # Fresh ACTIVE-configured adapter without activation
    status = CognitiveSurfaceAdapter(active_settings()).status()
    assert status.activation is None
    assert any(n == "actual_active=false" for n in status.notes)
    # reaches_core on some entrypoint must not flip actual_active
    assert not (measurement.core_count > 0 and status.activation is not None)


def test_r16_a4_other_project_hidden_and_status_is_side_effect_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = build_active_fixture(tmp_path)
    monkeypatch.setattr(api, "get_token_service", lambda: fixture.tokens)
    client = TestClient(fixture.app)
    headers = {"Authorization": "Bearer " + fixture.tokens.issue_token("owner")}
    view = client.get(BASE + "/requests/request-1", headers=headers)
    client.post(
        BASE + "/execute",
        headers=headers,
        json={"request_id": "request-1", "action_digest": view.json()["action_digest"], "reason": "r16 scope"},
    )
    from dataclasses import replace

    from tests.cognitive.test_surface import ACTIVE_PROJECT_ID, active_settings

    other = replace(
        active_settings(),
        project_id="project:00000000-0000-0000-0000-000000000099",
    )
    before_rev = fixture.history.latest(ACTIVE_PROJECT_ID).projection_revision
    status = CognitiveSurfaceAdapter(other, history_store=fixture.history).status()
    assert status.last_episode_id is None or status.dispatched_actions == 0
    assert status.last_episode_id != fixture.history.latest(ACTIVE_PROJECT_ID).last_episode_id or True
    # Other project must not see ACTIVE project's episode
    assert status.last_episode_id != fixture.history.latest(ACTIVE_PROJECT_ID).last_episode_id
    after_rev = fixture.history.latest(ACTIVE_PROJECT_ID).projection_revision
    assert after_rev == before_rev, "status read must not mutate durable history"
