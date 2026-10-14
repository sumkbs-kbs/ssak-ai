from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import uvicorn
import yaml
from starlette.routing import Mount

BASE = Path(__file__).resolve().parent
OWN = Path(sys.argv[1]).resolve()
OLD = Path(sys.argv[2])
sys.path.insert(0, str(OLD))
from startup_probe.contract import SourcePlan, verify_sources
from startup_probe.guard import Guard

plan = SourcePlan.model_validate_json((BASE / "plan.json").read_bytes())
verify_sources(plan)
fixture_port = 0
counter_lock = threading.Lock()
wire = []


class BrowserGuard(Guard):
    def __init__(self, owned):
        super().__init__(owned)
        self.fixture_delegations = []

    def audit(self, event, args):
        if event == "socket.bind":
            if args[1] != ("127.0.0.1", 0) or self.binds >= 2:
                self.deny("Unexpected browser fixture bind")
            self.binds += 1
            return
        if event == "socket.connect":
            if args[1] != ("127.0.0.1", fixture_port):
                self.deny("Nonfixture outbound socket")
            return
        super().audit(event, args)

    def profile(self, frame, event, arg):
        if (
            event == "call"
            and frame.f_code.co_filename.endswith(("model_manager.py", "inference_providers.py"))
            and frame.f_code.co_name in ("generate", "stream_generate", "load_model", "_load_model")
        ):
            target = frame.f_locals.get("target")
            if target is not None and target not in ("controlled-failure", "controlled-failure-wire"):
                self.deny("Unexpected fixture inference target")
            self.fixture_delegations.append(
                {"module": Path(frame.f_code.co_filename).name, "method": frame.f_code.co_name}
            )
            return
        super().profile(frame, event, arg)


guard = BrowserGuard(OWN)
guard.install()


class FailureProvider(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object):
        pass

    def respond(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        with counter_lock:
            wire.append({"method": "GET", "path": self.path, "kind": "metadata"})
        if self.path == "/api/tags":
            self.respond(
                200,
                {
                    "models": [
                        {
                            "name": "controlled-failure-wire",
                            "model": "controlled-failure-wire",
                            "size": 0,
                            "digest": "synthetic-browser-fixture",
                            "details": {"family": "fixture"},
                        }
                    ]
                },
            )
        elif self.path == "/api/ps":
            self.respond(200, {"models": []})
        elif self.path == "/api/version":
            self.respond(200, {"version": "fixture"})
        else:
            self.respond(200, {"data": [{"id": "controlled-failure-wire", "object": "model"}]})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(raw)
        if self.path == "/api/show":
            with counter_lock:
                wire.append({"method": "POST", "path": self.path, "kind": "metadata"})
            self.respond(200, {"capabilities": ["completion", "tools"], "details": {"family": "fixture"}})
            return
        if (
            self.path not in ("/api/chat", "/api/generate", "/v1/chat/completions")
            or payload.get("model") != "controlled-failure-wire"
        ):
            guard.deny("Unexpected provider request")
        with counter_lock:
            calls = sum(row["kind"] == "controlled_failure" for row in wire)
            if calls >= 4:
                guard.deny("Controlled failure request budget exceeded")
            number = len(wire) + 1
            (OWN / ("provider-" + str(number) + ".request.json")).write_bytes(raw)
            wire.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "kind": "controlled_failure",
                    "request_bytes": len(raw),
                    "request_sha256": hashlib.sha256(raw).hexdigest(),
                    "status": 503,
                }
            )
        self.respond(503, {"error": "Controlled provider unavailable for browser QA"})


class ObserveApp:
    def __init__(self, app):
        self.app = app
        self.sequence = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        self.sequence += 1
        number = self.sequence
        path = scope["path"]
        method = scope["method"]
        safe = path in ("/v1/chat/completions", "/api/tasks/submit") or (
            path.startswith("/api/tasks/") and not path.endswith("/events")
        )
        request = bytearray()
        response = bytearray()
        status = None
        content_type = None

        async def observed_receive():
            msg = await receive()
            if safe and len(request) < 1_000_000:
                request.extend(msg.get("body", b""))
            return msg

        async def observed_send(msg):
            nonlocal status, content_type
            if msg["type"] == "http.response.start":
                status = msg["status"]
                content_type = dict(msg.get("headers", [])).get(b"content-type", b"").decode()
            if safe and msg["type"] == "http.response.body" and len(response) < 1_000_000:
                response.extend(msg.get("body", b""))
            await send(msg)

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            record = {
                "n": number,
                "method": method,
                "path": path,
                "status": status,
                "content_type": content_type,
                "request_bytes": len(request),
                "response_bytes": len(response),
            }
            if safe:
                (OWN / ("http-" + str(number) + ".request.bin")).write_bytes(request)
                (OWN / ("http-" + str(number) + ".response.bin")).write_bytes(response)
                record["request_sha256"] = hashlib.sha256(request).hexdigest()
                record["response_sha256"] = hashlib.sha256(response).hexdigest()
            with (OWN / "http-journal.jsonl").open("a") as out:
                out.write(json.dumps(record) + "\n")


provider = ThreadingHTTPServer(("127.0.0.1", 0), FailureProvider)
fixture_port = provider.server_port
provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
provider_thread.start()
endpoint = "http://127.0.0.1:" + str(fixture_port)
configuration = {
    "models": {
        "reasoning": [
            {
                "name": "controlled-failure-wire",
                "repo": "controlled-failure-wire",
                "provider": "ollama",
                "api_base": endpoint + "/v1",
                "roles": ["default", "reasoning", "coding", "planning", "tool", "tools"],
            }
        ]
    },
    "defaults": {"reasoning": "controlled-failure-wire", "coding": "controlled-failure-wire"},
    "agent_models": {"default": "controlled-failure-wire"},
    "providers": {"ollama": {"base_url": endpoint + "/v1"}},
}
(OWN / "config.yaml").write_text(yaml.safe_dump(configuration))
os.environ["AGK_API_BASE"] = endpoint + "/v1"
os.environ["AGK_MODEL_API_BASE"] = endpoint + "/v1"
os.environ["AGK_MODEL_API_ENGINE"] = "ollama"
os.environ["AGK_OLLAMA_API_BASE"] = endpoint
from antigravity_k.engine import local_model_discovery


class OwnedDiscovery(local_model_discovery.LocalModelDiscovery):
    def __init__(self, *args: object, **kwargs: object):
        super().__init__(model_dirs=[OWN / "models_dir"], openai_endpoints=[], disable_network=False)


local_model_discovery.LocalModelDiscovery = OwnedDiscovery
from antigravity_k.api import server
from antigravity_k.engine.project_registry import get_project_registry

registry = get_project_registry()
project = registry.add_project("브라우저 실패 검증", str(OWN / "project_root"))
bundle = BASE.parent / "build-current/bundle"
for route in server.app.routes:
    if isinstance(route, Mount) and route.name == "dashboard":
        route.app = server._DashboardStaticFiles(directory=bundle, html=True)
(OWN / "metadata.json").write_text(
    json.dumps(
        {
            "root_source": str(Path(server.__file__).resolve()),
            "project_id": project.id,
            "project_root": project.path,
            "bundle": str(bundle),
            "provider_fixture_port": fixture_port,
            "dependency_overrides": len(server.app.dependency_overrides),
            "lifespan": "on",
        },
        indent=2,
    )
    + "\n"
)
stop = threading.Event()
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                (OWN / "started.json").write_text(
                    json.dumps(
                        {"pid": os.getpid(), "port": port, "project_id": project.id, "ready_after_lifespan": True}
                    )
                    + "\n"
                )

    product = Server(
        uvicorn.Config(
            ObserveApp(server.app),
            host="127.0.0.1",
            port=port,
            lifespan="on",
            loop="asyncio",
            http="h11",
            access_log=False,
            timeout_graceful_shutdown=8,
        )
    )

    def watcher():
        deadline = time.monotonic() + 420
        while not stop.wait(0.1):
            if (OWN / "stop.requested").exists() or time.monotonic() > deadline:
                product.should_exit = True
                return

    watch = threading.Thread(target=watcher, daemon=True)
    watch.start()
    try:
        product.run(sockets=[listener])
    finally:
        stop.set()
        watch.join(timeout=1)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=2)
        (OWN / "provider-journal.json").write_text(json.dumps(wire, indent=2) + "\n")
        (OWN / "guard-final.json").write_text(
            json.dumps(
                {
                    "violations": guard.violations,
                    "binds": guard.binds,
                    "model_calls": guard.model_calls,
                    "fixture_production_delegations": guard.fixture_delegations,
                    "scheduled_ticks": guard.scheduled_ticks,
                    "provider_thread_stopped": not provider_thread.is_alive(),
                },
                indent=2,
            )
            + "\n"
        )
