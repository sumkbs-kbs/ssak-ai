"""인지 표면 상태 API 시험 — read-only 계약과 라우터 등록 검증(P11)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from antigravity_k.api.routes import api_router
from antigravity_k.api.routes.cognitive_surface_api import (
    get_surface_adapter,
    get_surface_measurement,
    reset_surface_measurement_cache,
    router,
)
from antigravity_k.engine.cognitive_surface import (
    CognitiveCoreSettings,
    CognitiveSurfaceAdapter,
    SurfaceMode,
    SurfaceSource,
)


def _client(settings: CognitiveCoreSettings | None = None) -> TestClient:
    """라우트와 같은 경로(config → settings)로 만든 adapter를 주입한다."""

    app = FastAPI()
    app.include_router(router)
    resolved = settings if settings is not None else CognitiveCoreSettings.from_config({})
    adapter = CognitiveSurfaceAdapter(resolved)
    app.dependency_overrides[get_surface_adapter] = lambda: adapter
    return TestClient(app)


def test_status_reports_legacy_when_core_is_off() -> None:
    client = _client()
    response = client.get("/api/cognitive/surface/status")
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    assert payload["enabled"] is False
    assert payload["mode"] == "off"
    assert payload["source"] == "legacy"
    assert payload["legacy_module"] == "antigravity_k.engine.cognitive_loop"
    assert payload["core_module"] == "antigravity_k.engine.cognitive.runtime"
    assert payload["notes"], "OFF 사유가 노출되어야 한다"
    assert "legacy" in payload["notes"][0]
    # read-only: 실행·dispatch 흔적이 없다.
    assert payload["dispatched_actions"] == 0
    assert payload["refused_actions"] == 0
    assert payload["last_episode_id"] is None


def test_status_reports_shadow_mode() -> None:
    client = _client(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW, project_id="project:x"))
    payload: dict[str, Any] = client.get("/api/cognitive/surface/status").json()
    assert payload["mode"] == "shadow"
    assert payload["source"] == "core_shadow"
    assert payload["activation"] is None


def test_active_settings_without_approval_still_report_shadow_side() -> None:
    client = _client(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.ACTIVE, project_id="project:x"))
    payload: dict[str, Any] = client.get("/api/cognitive/surface/status").json()
    assert payload["mode"] == "active"
    assert payload["source"] == "core_shadow"
    assert payload["activation"] is None
    assert SurfaceSource.CORE_ACTIVE.value not in {payload["source"]}


def test_reach_endpoint_reports_measurement() -> None:
    reset_surface_measurement_cache()
    client = _client()
    response = client.get("/api/cognitive/surface/reach")
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    assert payload["legacy_module"] == "antigravity_k.engine.cognitive_loop"
    assert payload["core_module"] == "antigravity_k.engine.cognitive.runtime"
    labels = {item["module"] for item in payload["entrypoints"]}
    assert "antigravity_k.api.routes.chat" in labels
    assert payload["legacy_count"] >= 5
    assert payload["legacy_count"] == sum(1 for item in payload["entrypoints"] if item["reaches_legacy"])
    assert payload["core_count"] == sum(1 for item in payload["entrypoints"] if item["reaches_core"])


def test_reach_measurement_is_cached_until_refresh() -> None:
    reset_surface_measurement_cache()
    assert get_surface_measurement() is get_surface_measurement()
    client = _client()
    first = client.get("/api/cognitive/surface/reach").json()
    second = client.get("/api/cognitive/surface/reach").json()
    assert first == second
    refreshed = client.get("/api/cognitive/surface/reach", params={"refresh": "true"}).json()
    assert refreshed["core_module"] == first["core_module"]


def test_reach_recomputes_only_when_refreshed(monkeypatch: pytest.MonkeyPatch) -> None:
    import antigravity_k.api.routes.cognitive_surface_api as module

    calls: list[int] = []
    real = module.measure_surface_reach

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "measure_surface_reach", counting)
    reset_surface_measurement_cache()
    module.get_surface_measurement()
    module.get_surface_measurement()
    assert len(calls) == 1
    module.get_surface_measurement(refresh=True)
    assert len(calls) == 2
    reset_surface_measurement_cache()


def _sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if line]
        if not lines:
            continue
        name = next((line.removeprefix("event: ") for line in lines if line.startswith("event: ")), "message")
        payload = next((line.removeprefix("data: ") for line in lines if line.startswith("data: ")), "{}")
        events.append((name, json.loads(payload)))
    return events


def test_stream_sends_one_snapshot_then_done() -> None:
    client = _client()
    with client.stream("GET", "/api/cognitive/surface/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = _sse_events(body)
    assert [name for name, _ in events] == ["surface_status", "done"]
    status = events[0][1]["status"]
    assert status["source"] == SurfaceSource.LEGACY.value
    assert status["mode"] == "off"
    assert status["dispatched_actions"] == 0
    assert status["last_episode_id"] is None
    assert events[1][1] == {"done": True}


def test_stream_limit_is_bounded_and_terminates() -> None:
    client = _client()
    body = client.get("/api/cognitive/surface/stream", params={"limit": 3}).text
    events = _sse_events(body)
    assert [name for name, _ in events] == ["surface_status"] * 3 + ["done"]
    assert [payload["index"] for _, payload in events[:-1]] == [1, 2, 3]
    assert client.get("/api/cognitive/surface/stream", params={"limit": 0}).status_code == 422
    assert client.get("/api/cognitive/surface/stream", params={"limit": 11}).status_code == 422


def test_stream_does_not_change_surface_state() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings.from_config({}))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_surface_adapter] = lambda: adapter
    client = TestClient(app)
    first = _sse_events(client.get("/api/cognitive/surface/stream").text)[0][1]["status"]
    second = _sse_events(client.get("/api/cognitive/surface/stream").text)[0][1]["status"]
    assert first == second
    # 스트림은 episode를 돌리지 않는다.
    assert adapter.status().last_episode_id is None
    assert adapter.status().dispatched_actions == 0


def test_stream_reports_shadow_source_when_enabled() -> None:
    client = _client(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW))
    events = _sse_events(client.get("/api/cognitive/surface/stream").text)
    status = events[0][1]["status"]
    assert status["source"] == SurfaceSource.CORE_SHADOW.value
    assert status["mode"] == "shadow"
    assert status["activation"] is None


def test_surface_routes_are_registered_read_only() -> None:
    paths = {route.path: route for route in api_router.routes}
    for path in (
        "/api/cognitive/surface/status",
        "/api/cognitive/surface/reach",
        "/api/cognitive/surface/stream",
    ):
        assert path in paths, f"{path}가 api_router에 등록되지 않았다"
        assert paths[path].methods == {"GET"}, f"{path}는 read-only 여야 한다"
