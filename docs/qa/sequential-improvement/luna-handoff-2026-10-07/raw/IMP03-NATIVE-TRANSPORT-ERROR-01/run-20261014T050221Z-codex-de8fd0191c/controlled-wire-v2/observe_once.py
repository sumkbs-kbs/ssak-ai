from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from dataclasses import asdict, replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OUT = Path(__file__).resolve().parent
OWNED = OUT / "state"
PROVIDER_BODY = b'{"error":"controlled upstream unavailable"}'
OBSERVATIONS: list[dict[str, object]] = []
ATTEMPTS: list[str] = []
CONNECTIONS: list[str] = []
provider_port: int | None = None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, data: bytes) -> None:
    with (OUT / name).open("xb") as stream:
        stream.write(data)


def record(name: str, value: object) -> None:
    write(name, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


class ControlledFailure(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size)
        write("provider-request-body.bin", raw)
        OBSERVATIONS.append({"method": "POST", "path": self.path, "bytes": len(raw), "sha256": digest(raw)})
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(PROVIDER_BODY)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(PROVIDER_BODY)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    assert not (OUT / "acceptance.json").exists(), "This observer may run only once"
    OWNED.mkdir()
    os.chdir(OWNED)
    os.environ["AGK_AUTO_DISCOVER_LOCAL_MODELS"] = "false"
    os.environ["AGK_ALLOWED_ROOTS"] = str(OWNED)
    os.environ["AGK_USAGE_DB"] = str(OWNED / "unused-usage.json")
    os.environ["AGK_USER_MODEL_DB"] = str(OWNED / "brain")
    os.environ["AGK_GLOBAL_USER_MODEL_PATH"] = str(OWNED / "user_model.json")

    def audit(event: str, args: tuple[object, ...]) -> None:
        if event == "urllib.Request":
            url = str(args[0])
            ATTEMPTS.append(url)
            if len(ATTEMPTS) > 1 or provider_port is None or url != f"http://127.0.0.1:{provider_port}/api/chat":
                raise RuntimeError("Controlled observer HTTP dispatch budget exceeded")
        elif event == "socket.connect":
            address = args[1]
            CONNECTIONS.append(repr(address))
            if not isinstance(address, tuple) or address != ("127.0.0.1", provider_port):
                raise RuntimeError("Unexpected physical connection in controlled observer")

    sys.addaudithook(audit)
    import pytest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from antigravity_k.api import dependencies, project_binding
    from antigravity_k.api.routes import chat
    from antigravity_k.config import config
    from antigravity_k.engine.audit_logger import AuditLogger
    from antigravity_k.engine.model_manager import ModelManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.project_registry import ProjectRegistry
    from antigravity_k.engine.protocol_translator import ProtocolTranslator
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.engine.usage_tracker import UsageTracker
    from antigravity_k.engine.user_model import global_gbrain

    source_paths = [
        "src/antigravity_k/api/routes/chat.py",
        "src/antigravity_k/api/routes/messages_api.py",
        "src/antigravity_k/engine/protocol_translator.py",
        "src/antigravity_k/engine/model_manager.py",
        "src/antigravity_k/engine/provider_adapters/inference_providers.py",
        "src/antigravity_k/engine/provider_adapters/transport_errors.py",
        "src/antigravity_k/tools/egress_policy.py",
    ]
    sources = {p: digest((ROOT / p).read_bytes()) for p in source_paths}
    record("acceptance.json", {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "ASGI product request and controlled loopback provider HTTP503, no model inference",
        "product_post_limit": 1,
        "provider_post_limit": 1,
        "expected_product_status": 502,
        "expected_upstream_status": 503,
        "expected_error_type": "provider_transport_error",
        "expected_success_usage": 0,
        "expected_failed_usage": 1,
        "expected_assistant_persistence": 0,
        "expected_inference_calls": 0,
        "source_sha256": sources,
    })
    server = HTTPServer(("127.0.0.1", 0), ControlledFailure)
    global provider_port
    provider_port = server.server_port
    server.timeout = 8
    thread = threading.Thread(target=server.handle_request, daemon=True)
    profile_registry = ModelRegistry()
    profile = profile_registry.get_model("qwen3.8")
    assert profile is not None
    profile_registry._models[profile.name] = replace(profile, api_base=f"http://127.0.0.1:{server.server_port}/v1")
    tracker = UsageTracker(db_path=None)
    manager = ModelManager(profile_registry, tracker=tracker)
    projects = ProjectRegistry(storage_path=OWNED / "projects.json")
    project = projects.add_project("controlled-503", str(OWNED))
    sessions = SessionManager(base_dir=str(OWNED / "sessions"))
    payload = {
        "model": profile.name,
        "project_id": project.id,
        "messages": [{"role": "user", "content": "Return a JSON object."}],
        "response_format": {"type": "json_object"},
        "agent_mode": False,
        "stream": False,
        "max_tokens": 16,
        "temperature": 0,
    }
    record("product-request.json", payload)
    write("provider-response-body.bin", PROVIDER_BODY)
    response = None
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(config.paths, "project_root", OWNED)
            patch.setattr(project_binding, "get_project_registry", lambda: projects)
            patch.setattr(dependencies, "get_session_manager", lambda: sessions)
            patch.setattr(chat, "get_audit_logger", lambda: AuditLogger(log_dir=OWNED / "audit"))
            patch.setattr(global_gbrain, "add_node", lambda **kwargs: None)
            app = FastAPI()
            app.include_router(chat.router)
            app.dependency_overrides[chat.get_model_manager] = lambda: manager
            app.dependency_overrides[chat.get_translator] = ProtocolTranslator
            thread.start()
            with TestClient(app) as client:
                response = client.post("/v1/chat/completions", json=payload)
                write("product-response-body.bin", response.content)
                record("product-response.json", {"status": response.status_code, "headers": dict(response.headers), "json": response.json()})
    finally:
        thread.join(timeout=9)
        server.server_close()
        record("cleanup.json", {"server_thread_alive": thread.is_alive(), "server_closed": True, "urllib_request_attempts": ATTEMPTS, "socket_connections": CONNECTIONS})
    assert response is not None
    records = tracker.get_recent(10)
    session_messages = sessions.get_messages()
    result = {
        "status": response.status_code,
        "body": response.json(),
        "product_asgi_posts": 1,
        "provider_http_posts": len(OBSERVATIONS),
        "provider_requests": OBSERVATIONS,
        "provider_response_status": 503,
        "retry_posts": max(0, len(OBSERVATIONS) - 1),
        "usage": [asdict(row) for row in records],
        "success_usage": sum(row.success for row in records),
        "failure_usage": sum(not row.success for row in records),
        "assistant_records": sum(row.get("role") == "assistant" for row in session_messages),
        "model_inference": 0,
        "real_ollama": 0,
        "product_external_http": 0,
        "source_changed_during_observation": [p for p, sha in sources.items() if digest((ROOT / p).read_bytes()) != sha],
    }
    record("observations.json", result)
    assert result["status"] == 502, result
    assert response.json()["detail"]["type"] == "provider_transport_error", result
    assert len(OBSERVATIONS) == 1 and OBSERVATIONS[0]["path"] == "/api/chat", result
    assert len(ATTEMPTS) == 1 and len(CONNECTIONS) == 1, result
    assert result["success_usage"] == 0 and result["failure_usage"] == 1, result
    assert result["assistant_records"] == 0, result
    assert not result["source_changed_during_observation"], result
    assert not thread.is_alive()
    record("result.json", {"verdict": "PASS_SCOPED_ASGI_REAL_PROVIDER_HTTP503", "limits": "Controlled failure only; no live model/auth/Uvicorn/lifespan claim", "observations": "observations.json"})
    print(json.dumps({"verdict": "PASS_SCOPED_ASGI_REAL_PROVIDER_HTTP503", "status": response.status_code, "provider_posts": len(OBSERVATIONS), "usage_failed": len(records)}))


if __name__ == "__main__":
    main()

