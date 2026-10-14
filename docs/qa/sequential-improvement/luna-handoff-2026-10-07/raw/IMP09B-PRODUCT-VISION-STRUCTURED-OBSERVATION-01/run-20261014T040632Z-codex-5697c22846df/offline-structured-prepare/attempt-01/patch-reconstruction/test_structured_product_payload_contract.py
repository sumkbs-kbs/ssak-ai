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
SAVED_REQUEST: Final = RUN / "request.json"
EXPECTED_SCHEMA: Final = json.loads((RUN / "planned-acceptance.json").read_bytes())["expected_schema"]
MOCK_CONTENT: Final = '{"red_circles":2,"blue_squares":1}'


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
        return json.dumps({"message": {"role": "assistant", "content": MOCK_CONTENT}, "done": True}).encode()


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
        assert response.json()["choices"][0]["message"]["content"] == MOCK_CONTENT
        assert len(captured) == 1
        assert not blocked
        yield captured[0]


def test_structured_product_payload_matches_exact_profile(actual_payload: CapturedRequest) -> None:
    payload = json.loads(actual_payload.raw)
    request = json.loads(SAVED_REQUEST.read_bytes())
    expected = {
        "model": "qwen3.8",
        "stream": False,
        "keep_alive": "30m",
        "think": False,
        "format": EXPECTED_SCHEMA,
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
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "vision_shape_counts", "strict": True, "schema": EXPECTED_SCHEMA},
    }
    assert payload == expected
    assert (
        h.classify_upstream_request(actual_payload.url, actual_payload.method, actual_payload.raw)
        == "ollama_chat_inference_wire"
    )


@pytest.mark.parametrize("variant", ["missing", "drift", "envelope", "tools", "image", "options", "model"])
def test_schema_and_identity_drift_rejected_before_sink(actual_payload: CapturedRequest, variant: str) -> None:
    payload = json.loads(actual_payload.raw)
    mutations = {
        "missing": lambda: payload.pop("format"),
        "drift": lambda: payload["format"].update({"additionalProperties": True}),
        "envelope": lambda: payload.update({"format": json.loads(h.RESPONSE_FORMAT_JSON)}),
        "tools": lambda: payload.update({"tools": []}),
        "image": lambda: payload["messages"][-1].update({"images": ["YmFk"]}),
        "options": lambda: payload["options"].update({"repeat_penalty": 1.0}),
        "model": lambda: payload.update({"model": "unapproved"}),
    }
    mutations[variant]()
    sink_calls = 0
    with pytest.raises(ValueError):
        h.classify_upstream_request(actual_payload.url, actual_payload.method, json.dumps(payload).encode())
        sink_calls += 1
    assert sink_calls == 0


@pytest.mark.parametrize("variant", ["missing", "drift", "native_object", "extra_key"])
def test_product_request_schema_drift_rejected(variant: str) -> None:
    request = json.loads(SAVED_REQUEST.read_bytes())
    mutations = {
        "missing": lambda: request.pop("response_format"),
        "drift": lambda: request["response_format"]["json_schema"]["schema"].update({"additionalProperties": True}),
        "native_object": lambda: request.update({"response_format": EXPECTED_SCHEMA}),
        "extra_key": lambda: request["response_format"].update({"unexpected": True}),
    }
    mutations[variant]()
    image, _ = h.load_image(RUN)
    assert h.accept_product_request(request, image)["pass"] is False


def test_schema_does_not_encode_semantic_answer() -> None:
    from jsonschema import Draft202012Validator

    assert EXPECTED_SCHEMA == {
        "type": "object",
        "properties": {"red_circles": {"type": "integer"}, "blue_squares": {"type": "integer"}},
        "required": ["red_circles", "blue_squares"],
        "additionalProperties": False,
    }
    validator = Draft202012Validator(EXPECTED_SCHEMA)
    assert validator.is_valid({"red_circles": 7, "blue_squares": 9})
    assert not validator.is_valid({"red_circles": True, "blue_squares": 1})


def test_schema_fixture_profile_sources_and_acceptance_are_bound(tmp_path: Path) -> None:
    run = tmp_path / "bound-structured-profile"
    run.mkdir()
    for name in (
        *h.IMPLEMENTATION_SOURCE_NAMES,
        "endpoint-contract.json",
        "runtime-bridge-contract.json",
        "budgets.json",
        "profile-contract.json",
        "response-schema.json",
        "planned-acceptance.json",
        "test_structured_product_payload_contract.py",
    ):
        shutil.copyfile(RUN / name, run / name)
    shutil.copytree(RUN / "fixture", run / "fixture")
    h.prepare_owned_request(ROOT, run, run / "offline-state")
    binding_raw = (run / "execution-binding.json").read_bytes()
    binding = json.loads(binding_raw)
    request_before = (run / "request.json").read_bytes()
    assert binding["response_schema_sha256"] == h.sha256((run / "response-schema.json").read_bytes())
    assert binding["structured_fixture_sha256"] == h.sha256(Path(__file__).read_bytes())
    assert binding["planned_acceptance_sha256"] == h.sha256((run / "planned-acceptance.json").read_bytes())
    assert len(binding["product_source_sha256"]) == 28
    for path, digest in binding["product_source_sha256"].items():
        assert h.sha256((ROOT / path).read_bytes()) == digest
    assert binding["project_workspace"] == "runtime-state/workspace"
    h.request_gate(run, ROOT)
    assert (run / "request.json").read_bytes() == request_before
    assert (run / "execution-binding.json").read_bytes() == binding_raw
    (run / "response-schema.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="INCONCLUSIVE_SOURCE_DRIFT"):
        h.request_gate(run, ROOT)
