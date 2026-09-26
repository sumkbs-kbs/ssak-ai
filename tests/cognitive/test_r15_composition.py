"""R15 residual: trusted ACTIVE composition / defaults / entry owners.

Closes failure-model residuals that suite greens alone do not prove:
- HTTP body cannot inject composition (service/authority/project root)
- Unconfigured ACTIVE returns 503 (not false success)
- Production bootstrap attach path never installs ACTIVE
- observe_interaction never silently runs ACTIVE
- Entry matrix labels stay present in measure_surface_reach
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import antigravity_k.config as config_mod
from antigravity_k.api import dependencies as deps
from antigravity_k.api.routes import cognitive_active_api as api
from antigravity_k.api.routes.cognitive_surface_api import router
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.auth import TokenService
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive_surface import (
    CognitiveCoreSettings,
    CognitiveSurfaceAdapter,
    SurfaceMode,
    SurfaceNotReadyError,
    measure_surface_reach,
)
from tests.cognitive.test_surface import ACTIVE_PROJECT_ID, StubDispatchPort, StubThink, active_settings

BASE = "/api/cognitive/surface/active"


def test_r15_unconfigured_active_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R15 residual: missing CognitiveActiveService is 503, never 200/false success."""

    tokens = TokenService(tmp_path / "jwt-secret", epoch_provider=lambda: 1)
    monkeypatch.setattr(api, "get_token_service", lambda: tokens)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + tokens.issue_token("owner")}
    r = client.post(
        BASE + "/execute",
        headers=headers,
        json={"request_id": "x", "action_digest": "sha256:" + "a" * 64, "reason": "no service"},
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()
    g = client.get(BASE + "/requests/request-1", headers=headers)
    assert g.status_code == 503


def test_r15_body_cannot_inject_composition_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R15-A2 residual: request JSON cannot supply authority/project_root/service/approver."""

    tokens = TokenService(tmp_path / "jwt-secret", epoch_provider=lambda: 1)
    monkeypatch.setattr(api, "get_token_service", lambda: tokens)
    app = FastAPI()
    app.include_router(router)
    app.state.cognitive_active_service = api.CognitiveActiveService(
        prepared={},
        build_adapter=lambda authorize: CognitiveSurfaceAdapter(active_settings(), think=StubThink()),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + tokens.issue_token("owner")}
    base = {
        "request_id": "request-1",
        "action_digest": "sha256:" + "b" * 64,
        "reason": "inject probe",
    }
    for poison in (
        {"approver": "human:owner"},
        {"project_id": ACTIVE_PROJECT_ID},
        {"project_root": str(tmp_path)},
        {"authority": {"allowed": True}},
        {"readiness": {"fresh": True}},
        {"arguments": {"file_path": "evil.txt"}},
        {"tool": "write_file"},
        {"service": "injected"},
    ):
        r = client.post(BASE + "/execute", headers=headers, json={**base, **poison})
        assert r.status_code == 422, poison


def test_r15_boot_attach_never_installs_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production `_attach_cognitive_surface` only wires SHADOW; ACTIVE config is skipped."""

    runtime = MagicMock()
    runtime.attach_cognitive_surface = MagicMock()
    mm = MagicMock()

    monkeypatch.setattr(
        config_mod,
        "config",
        SimpleNamespace(_raw={"cognitive_core": {"enabled": True, "mode": "active", "project_id": ACTIVE_PROJECT_ID}}),
    )
    deps._attach_cognitive_surface(runtime, mm)
    runtime.attach_cognitive_surface.assert_not_called()

    monkeypatch.setattr(
        config_mod,
        "config",
        SimpleNamespace(_raw={"cognitive_core": {"enabled": True, "mode": "shadow"}}),
    )
    deps._attach_cognitive_surface(runtime, mm)
    runtime.attach_cognitive_surface.assert_called_once()


def test_r15_observe_interaction_never_runs_active() -> None:
    """Legacy observe path must ignore ACTIVE adapters (no silent dispatch)."""

    class CountingAdapter:
        settings = SimpleNamespace(effective_mode=SurfaceMode.ACTIVE)
        calls = 0

        def run_shadow(self, request):  # noqa: ANN001
            self.calls += 1
            raise AssertionError("ACTIVE must not use run_shadow from observe")

        def run_active(self, request):  # noqa: ANN001
            self.calls += 1
            raise AssertionError("observe_interaction must never call run_active")

    orch = MagicMock()
    orch.get_model_for_role = MagicMock(return_value="m")
    adapter = CountingAdapter()
    runtime = AgentRuntime(orchestrator=orch, cognitive_surface=adapter)  # type: ignore[arg-type]
    out = runtime.observe_interaction(
        episode_id="episode:r15",
        context_ref="context:r15",
        goal_ref="goal:r15",
    )
    assert out is None
    assert adapter.calls == 0


def test_r15_default_config_is_off() -> None:
    assert CognitiveCoreSettings.from_config({}).effective_mode is SurfaceMode.OFF
    assert (
        CognitiveCoreSettings.from_config({"cognitive_core": {"enabled": False, "mode": "active"}}).effective_mode
        is SurfaceMode.OFF
    )


def test_r15_entry_matrix_labels_present() -> None:
    """Static reach labels used by ENTRY_MATRIX.md must remain measurable."""

    measurement = measure_surface_reach(source_root=Path("src"))
    labels = {item.label for item in measurement.entrypoints}
    required = {
        "CLI",
        "API server",
        "API chat",
        "API agent SSE",
        "background/durable task",
        "agent runtime",
    }
    missing = required - labels
    assert not missing, f"entry matrix labels drifted: {missing}"
    assert any(item.label == "agent runtime" and item.reaches_core for item in measurement.entrypoints)


def test_r15_active_requires_freshness_resolver() -> None:
    """ACTIVE without freshness_resolver must refuse (R08 composition contract)."""

    adapter = CognitiveSurfaceAdapter(
        active_settings(),
        think=StubThink(),
        governance=GovernanceGate(),
        dispatch_port=StubDispatchPort(),
        # omit journal/record_sink/authority/freshness/activation_authorizer
    )
    with pytest.raises(SurfaceNotReadyError) as exc:
        adapter.activate(approver="human:owner", reason="missing freshness")
    msg = str(exc.value).lower()
    assert "freshness" in msg or "durable" in msg or "authority" in msg
