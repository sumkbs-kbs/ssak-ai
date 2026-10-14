"""테스트: Models/Health/Wake/Embeddings + System Status·Restart 계약.
==========================================================
legacy에서 추출·귀속된 엔드포인트의 응답 구조와 권한 게이트를 검증한다.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Protocol, cast, final

import psutil
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from antigravity_k.api.routes import models_api, system_api
from antigravity_k.api.server import app
from antigravity_k.config import config

JsonObject = dict[str, object]


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> object: ...


def _json(response: ResponseLike) -> JsonObject:
    value = response.json()
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object, got {type(value).__name__}")
    return cast(JsonObject, value)


@final
class _Profile:
    name = "qwen3-test"
    role = "reasoning"
    description = "테스트용"

    def routing_metadata(self) -> dict[str, object]:
        return {"tier": 1}


class _Registry:
    def list_models(self) -> list[_Profile]:
        return [_Profile()]


class _Router:
    def status(self) -> dict[str, object]:
        return {"quality_calibration": {"score": 0.9}}


class _Tracker:
    def get_total_tokens(self) -> int:
        return 4242


@final
class _FakeManager:
    def __init__(self, loaded_models: dict[str, object] | None = None):
        self._loaded_models = loaded_models if loaded_models is not None else {}
        self._registry = _Registry()
        self.router = _Router()
        self.tracker = _Tracker()
        self.provider_capability_calls: list[bool] = []

    def status(self) -> dict[str, object]:
        return {"loaded_models": self._loaded_models}

    def discover_local_models(self) -> list[object]:
        return []

    def provider_capabilities(self, refresh: bool = False) -> dict[str, object]:
        self.provider_capability_calls.append(refresh)
        return {"qwen3-test": {"native_tools": True}}


class _FakeRuntime:
    def submit_task(self, **kwargs: object) -> str:
        _ = kwargs
        return "task_777"


class _FakeEmbeddingEngine:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def embed(self, values: list[str], model: str) -> list[list[float]]:
        _ = (values, model)
        if self.error is not None:
            raise self.error
        return [[0.1, 0.2], [0.3, 0.4]]


@pytest.fixture
def client() -> Iterator[TestClient]:
    headers = {"X-Access-Pin": config.security.access_pin}
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update(headers)
        yield test_client


def _fake_manager() -> _FakeManager:
    return _FakeManager()


# ─── Models/Health/Wake (models_api) ─────────────────────────────


class TestModelsApi:
    def test_health_reports_version_and_backend_shape(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = _FakeManager({"m1": {}})
        monkeypatch.setattr(models_api, "get_model_manager", lambda: manager)
        monkeypatch.setattr(models_api, "get_orchestrator", lambda: None)

        body = _json(client.get("/v1/health"))

        assert body["status"] == "ok"
        assert isinstance(body["version"], str)
        assert body["backends"] == {"m1": {}}
        assert body["cov_active"] is False

    def test_wake_submits_background_task(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime = _FakeRuntime()
        monkeypatch.setattr(models_api, "get_agent_runtime", lambda: runtime)

        body = _json(
            client.post(
                "/api/agent/wake",
                json={"event_type": "lint_error", "payload": {"file": "a.py"}},
            )
        )

        assert body["status"] == "woken"
        assert body["task_id"] == "task_777"
        assert "lint_error" in cast(str, body["message"])

    def test_v1_models_openai_shape(self, client: TestClient) -> None:
        manager = _fake_manager()
        from antigravity_k.api.dependencies import get_model_manager

        app.dependency_overrides[get_model_manager] = lambda: manager
        try:
            body = _json(client.get("/v1/models"))
        finally:
            app.dependency_overrides.clear()

        assert body["object"] == "list"
        model = cast(JsonObject, cast(list[object], body["data"])[0])
        assert model["id"] == "qwen3-test"
        assert model["object"] == "model"
        assert model["owned_by"] == "system"
        assert model["provider_capability"] == {"native_tools": True}

    def test_model_operations_refresh_passthrough(self, client: TestClient) -> None:
        manager = _fake_manager()
        from antigravity_k.api.dependencies import get_model_manager

        app.dependency_overrides[get_model_manager] = lambda: manager
        try:
            body = _json(client.get("/v1/models/operations", params={"refresh": True}))
        finally:
            app.dependency_overrides.clear()

        quality = cast(JsonObject, body["quality_calibration"])
        assert quality["score"] == 0.9
        assert manager.provider_capability_calls == [True]

    def test_embeddings_usage_and_error(self, client: TestClient) -> None:
        engine = _FakeEmbeddingEngine()
        from antigravity_k.api.dependencies import get_embedding_engine

        app.dependency_overrides[get_embedding_engine] = lambda: engine

        ok = _json(client.post("/v1/embeddings", json={"input": ["aaaa", "bb"], "model": "e"}))
        usage = cast(JsonObject, ok["usage"])
        embeddings = cast(list[object], ok["data"])
        assert usage["prompt_tokens"] == 1  # 4//4 + 2//4
        assert cast(JsonObject, embeddings[1])["index"] == 1

        engine.error = ValueError("차원 불일치")
        try:
            err = client.post("/v1/embeddings", json={"input": ["x"], "model": "e"})
        finally:
            app.dependency_overrides.clear()
        assert err.status_code == 500


# ─── System status/restart (system_api 귀속분) ───────────────────


class TestSystemStatusRestart:
    def test_status_measures_cpu_off_event_loop(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Callable[..., object], tuple[object, ...], dict[str, object]]] = []

        async def fake_to_thread(func: Callable[..., object], *args: object, **kwargs: object) -> object:
            calls.append((func, args, kwargs))
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(percent=41.5))
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=0: 12.0)
        monkeypatch.setattr(system_api, "get_model_manager", lambda: _fake_manager())

        body = _json(client.get("/api/system/status"))

        assert body["cpu_percent"] == 12.0
        assert calls and calls[0][0] is psutil.cpu_percent

    def test_status_reports_uptime_and_tokens(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_virtual_memory() -> SimpleNamespace:
            return SimpleNamespace(percent=41.5)

        def fake_cpu_percent(interval: float = 0.0) -> float:
            _ = interval
            return 12.0

        monkeypatch.setattr(psutil, "virtual_memory", fake_virtual_memory)
        monkeypatch.setattr(psutil, "cpu_percent", fake_cpu_percent)

        import antigravity_k.api.dependencies as deps

        manager = _fake_manager()
        monkeypatch.setattr(deps, "get_model_manager", lambda: manager)

        body = _json(client.get("/api/system/status"))

        assert body["ok"] is True and body["status"] == "online"
        assert body["total_tokens"] == 4242
        assert cast(int, body["uptime_seconds"]) >= 0

    def test_restart_requires_critical_permission(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        denied = HTTPException(status_code=403, detail="denied")

        def deny(*args: object, **kwargs: object) -> None:
            _ = (args, kwargs)
            raise denied

        monkeypatch.setattr(system_api, "_require_allowed", deny)

        response = client.post("/api/system/restart")

        assert response.status_code == 403

    def test_restart_schedules_trigger_file(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.chdir(tmp_path)

        def allow(*args: object, **kwargs: object) -> None:
            _ = (args, kwargs)

        monkeypatch.setattr(system_api, "_require_allowed", allow)

        body = _json(client.post("/api/system/restart"))

        assert body["ok"] is True
        assert "reboot" in cast(str, body["message"])
