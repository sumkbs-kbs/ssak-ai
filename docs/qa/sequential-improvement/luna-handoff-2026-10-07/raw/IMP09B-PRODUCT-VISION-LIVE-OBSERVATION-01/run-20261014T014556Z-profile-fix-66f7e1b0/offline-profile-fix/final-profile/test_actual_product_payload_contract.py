from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final, Never

import pytest

h = importlib.import_module("run_harness")
RUN: Final = Path(__file__).resolve().parent
ROOT: Final = h.resolve_repository_root()
SAVED_REQUEST: Final = RUN.parent / "run-20261014T013431Z-workspace-fix-8c6d1943/request.json"


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    url: str
    method: str
    raw: bytes


class FakeResponse:
    status = 200

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        return None

    def read(self) -> bytes:
        return b'{"message":{"role":"assistant","content":"offline-fixture-response"},"done":true}'


@pytest.fixture(scope="module")
def actual_payload(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CapturedRequest]:
    capture = Path(os.environ["PROFILE_CAPTURE_ROOT"])
    capture.mkdir(parents=True, exist_ok=True)
    scratch = tmp_path_factory.mktemp("actual-product-profile")
    blocked: list[str] = []
    captured: list[CapturedRequest] = []
    with pytest.MonkeyPatch.context() as patch:

        def deny_socket(*args: str, **kwargs: str) -> Never:
            blocked.append("socket")
            raise AssertionError("offline product fixture attempted a socket")

        for method in ("connect", "connect_ex", "bind", "listen"):
            patch.setattr(socket.socket, method, deny_socket)
        patch.setattr(socket, "create_connection", deny_socket)
        patch.chdir(scratch)
        patch.setenv("AGK_AUTO_DISCOVER_LOCAL_MODELS", "false")
        patch.setenv("AGK_ALLOWED_ROOTS", str(scratch))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from antigravity_k.api import dependencies, project_binding
        from antigravity_k.api.routes import chat
        from antigravity_k.config import config
        from antigravity_k.engine import tracing
        from antigravity_k.engine.audit_logger import AuditLogger
        from antigravity_k.engine.model_manager import ModelManager
        from antigravity_k.engine.model_registry import ModelRegistry
        from antigravity_k.engine.project_registry import ProjectRegistry
        from antigravity_k.engine.protocol_translator import ProtocolTranslator
        from antigravity_k.engine.provider_adapters import inference_providers
        from antigravity_k.engine.session_manager import SessionManager
        from antigravity_k.engine.slash_commands import SlashCommandRegistry
        from antigravity_k.engine.tracing import AgentTracer
        from antigravity_k.engine.usage_tracker import UsageTracker
        from antigravity_k.engine.user_model import global_gbrain

        raw = SAVED_REQUEST.read_bytes()
        body = json.loads(raw)
        (capture / "route-request.bin").write_bytes(raw)
        patch.setattr(config.paths, "project_root", scratch)
        registry_path = scratch / "projects.json"
        registry_path.write_text(
            json.dumps([{"id": body["project_id"], "name": "owned-offline", "path": str(scratch), "is_active": True}])
        )
        project_registry = ProjectRegistry(registry_path)
        patch.setattr(project_binding, "get_project_registry", lambda: project_registry)
        sessions = SessionManager(base_dir=str(scratch / "sessions"))
        patch.setattr(dependencies, "get_session_manager", lambda: sessions)
        audit = AuditLogger(log_dir=scratch / "audit")
        patch.setattr(chat, "get_audit_logger", lambda: audit)
        patch.setattr(global_gbrain, "add_node", lambda **_kwargs: None)
        tracer = AgentTracer()
        patch.setattr(tracing, "get_tracer", lambda persist_dir=None: tracer)
        slash_registry = SlashCommandRegistry()
        patch.setattr(dependencies, "get_slash_registry", lambda **_kwargs: slash_registry)
        registry = ModelRegistry(config_path=str(ROOT / "config.yaml"))
        manager = ModelManager(registry, tracker=UsageTracker(db_path=None))
        translator = ProtocolTranslator()

        def terminal(request: urllib.request.Request, *, timeout: float | None = None) -> FakeResponse:
            assert isinstance(request.data, bytes)
            item = CapturedRequest(request.full_url, request.get_method(), request.data)
            captured.append(item)
            (capture / "provider-request.bin").write_bytes(item.raw)
            (capture / "provider-request.json").write_text(json.dumps(json.loads(item.raw), indent=2))
            return FakeResponse()

        patch.setattr(inference_providers, "safe_urlopen", terminal)
        app = FastAPI()
        app.include_router(chat.router)
        app.dependency_overrides[chat.get_model_manager] = lambda: manager
        app.dependency_overrides[chat.get_translator] = lambda: translator
        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", content=raw, headers={"Content-Type": "application/json"})
        (capture / "route-response.bin").write_bytes(response.content)
        (capture / "counts.json").write_text(
            json.dumps({"asgi_posts": 1, "fake_provider_calls": len(captured), "socket_attempts": len(blocked)})
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "offline-fixture-response"
        assert len(captured) == 1
        assert not blocked
        yield captured[0]


def test_actual_product_payload_matches_exact_profile(actual_payload: CapturedRequest) -> None:
    payload = json.loads(actual_payload.raw)
    request = json.loads(SAVED_REQUEST.read_bytes())
    expected = {
        "model": "qwen3.8",
        "stream": False,
        "keep_alive": "30m",
        "think": False,
        "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0, "min_p": 0.05, "repeat_penalty": 1.3},
        "messages": [
            {"role": "system", "content": h.EXPECTED_UPSTREAM_SYSTEM},
            {
                "role": "user",
                "content": request["messages"][0]["content"][0]["text"],
                "images": [request["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]],
            },
        ],
    }
    assert payload == expected
    assert (
        h.classify_upstream_request(actual_payload.url, actual_payload.method, actual_payload.raw)
        == "ollama_chat_inference_wire"
    )


@pytest.mark.parametrize("field", ["num_ctx", "num_predict", "temperature", "min_p", "repeat_penalty"])
def test_option_drift_still_rejected(actual_payload: CapturedRequest, field: str) -> None:
    payload = json.loads(actual_payload.raw)
    payload["options"][field] = -999
    with pytest.raises(ValueError):
        h.classify_upstream_request(actual_payload.url, actual_payload.method, json.dumps(payload).encode())


@pytest.mark.parametrize("field", ["format", "tools", "unexpected"])
def test_unexpected_top_level_fields_rejected(actual_payload: CapturedRequest, field: str) -> None:
    payload = json.loads(actual_payload.raw)
    payload[field] = "forbidden"
    with pytest.raises(ValueError):
        h.classify_upstream_request(actual_payload.url, actual_payload.method, json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("field", "value"), [("model", "wrong"), ("stream", True), ("think", True), ("keep_alive", "0s")]
)
def test_identity_and_execution_options_rejected(
    actual_payload: CapturedRequest, field: str, value: str | bool
) -> None:
    payload = json.loads(actual_payload.raw)
    payload[field] = value
    with pytest.raises(ValueError):
        h.classify_upstream_request(actual_payload.url, actual_payload.method, json.dumps(payload).encode())


def test_image_drift_rejected(actual_payload: CapturedRequest) -> None:
    payload = json.loads(actual_payload.raw)
    payload["messages"][-1]["images"] = ["YmFk"]
    with pytest.raises(ValueError):
        h.classify_upstream_request(actual_payload.url, actual_payload.method, json.dumps(payload).encode())


def test_profile_contract_and_sources_are_bound(tmp_path: Path) -> None:
    run = tmp_path / "bound-profile"
    run.mkdir()
    for name in (
        *h.IMPLEMENTATION_SOURCE_NAMES,
        "endpoint-contract.json",
        "runtime-bridge-contract.json",
        "budgets.json",
        "profile-contract.json",
    ):
        shutil.copyfile(RUN / name, run / name)
    shutil.copytree(RUN / "fixture", run / "fixture")
    h.prepare_owned_request(ROOT, run, run / "offline-state")
    binding = json.loads((run / "execution-binding.json").read_bytes())
    profile = json.loads((run / "profile-contract.json").read_bytes())
    assert profile["expected_payload"]["options"]["repeat_penalty"] == 1.3
    assert profile["expected_payload"]["options"]["min_p"] == 0.05
    assert binding["profile_contract_sha256"] == h.sha256((run / "profile-contract.json").read_bytes())
    for path, sha in profile["source_sha256"].items():
        assert h.sha256((ROOT / path).read_bytes()) == sha
        assert binding["additional_runtime_source_sha256"][path] == sha
    (run / "profile-contract.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="INCONCLUSIVE_SOURCE_DRIFT"):
        h.request_gate(run, ROOT)
