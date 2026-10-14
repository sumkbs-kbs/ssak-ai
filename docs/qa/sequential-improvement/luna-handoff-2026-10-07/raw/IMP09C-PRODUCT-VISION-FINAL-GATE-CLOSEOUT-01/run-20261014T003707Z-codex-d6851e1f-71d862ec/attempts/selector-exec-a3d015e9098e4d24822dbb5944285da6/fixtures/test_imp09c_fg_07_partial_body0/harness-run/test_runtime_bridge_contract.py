from __future__ import annotations

import importlib
import io
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any, cast
from urllib.parse import urlsplit

import pytest

h = importlib.import_module("run_harness")
r = importlib.import_module("runtime_adapter")

RUN = Path(__file__).resolve().parent
ROOT = h.resolve_repository_root()


def seed(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    for name in (*h.IMPLEMENTATION_SOURCE_NAMES, "runtime-bridge-contract.json"):
        source = RUN / name
        if source.is_file():
            shutil.copyfile(source, run / name)
    shutil.copytree(RUN / "fixture", run / "fixture")
    workspace = run / "offline-state/workspace"
    workspace.mkdir(parents=True)
    registry = run / "offline-state/registry/projects.json"
    registry.parent.mkdir(parents=True)
    project = "proj_" + h.sha256(str(run).encode())[:8]
    h.write_once(
        registry,
        h.canonical_json(
            [{"id": project, "name": "runtime-bridge", "path": str(workspace), "is_active": True, "tasks": []}]
        ),
    )
    _, encoded = h.load_image(run)
    raw = h.canonical_json(h.build_request(project, encoded))
    h.write_once(run / "request.json", raw)
    h.write_once(
        run / "request.binding.json",
        h.canonical_json(
            {
                "task_id": h.PREPARATION_TASK_ID,
                "project_id": project,
                "project_registry_path": registry.relative_to(run).as_posix(),
                "project_workspace": workspace.relative_to(run).as_posix(),
                "fixture_b64_sha256": h.B64_SHA256,
                "fixture_png_sha256": h.IMAGE_SHA256,
                "question": h.QUESTION,
                "request_sha256": h.sha256(raw),
            }
        ),
    )
    h.freeze_execution_binding(run, ROOT)


def approval(run: Path) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        **h.runtime_authorization_descriptor(run, ROOT),
        "fixture_only": True,
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


class FakeResponse:
    def __init__(self, raw: bytes, status: int = 200, *, world: Any, partial: bool = False):
        self.status = status
        self.headers = {"Content-Type": "application/json", "Authorization": "DO-NOT-CAPTURE"}
        self.body = io.BytesIO(raw)
        self.world = world
        self.read_timeouts: list[float] = []
        self.partial = partial
        self.reads = 0
        self.closed = False

    def set_timeout(self, timeout: float) -> None:
        assert timeout > 0
        self.read_timeouts.append(timeout)
        self.world.calls.append({"kind": "read-timeout", "timeout": timeout})

    def read(self, amount: int = -1) -> bytes:
        self.reads += 1
        if self.partial and self.reads == 2:
            raise TimeoutError("MOCK partial read timeout")
        if self.partial:
            amount = 7
        return self.body.read(amount)

    def readline(self, amount: int = -1) -> bytes:
        return self.body.readline(amount)

    def close(self) -> None:
        self.closed = True


def mock_http_error(url: str, status: int, response: FakeResponse) -> urllib.error.HTTPError:
    headers = Message()
    for key, value in response.headers.items():
        headers[key] = value
    return urllib.error.HTTPError(url, status, "MOCK", headers, cast(IO[bytes], cast(object, response)))


class FakeIPC:
    child_env: dict[str, str] = {}
    pass_fds: tuple[int, ...] = ()

    def __init__(self, world: Any):
        self.world = world
        self.queue: list[dict[str, Any]] = []
        self.closed = False

    def send(self, value: Any, *, timeout: float) -> None:
        assert timeout > 0
        self.world.calls.append({"kind": "ipc-send", "event": value["event"], "timeout": timeout})
        if value["event"] == "BOOT":
            spec = self.world.spec
            boot = r.worker_bootstrap(
                spec,
                value,
                self.world.resources,
                parent_pid=os.getpid(),
                observer=self.world.observer.install,
                child_environment=self.world.environment,
            )
            self.queue.append(
                {
                    "event": "WORKER_STARTED",
                    "pid": 7001,
                    "ready": self.world.ready_signal,
                    "binding_sha": spec.binding_sha,
                    "token": boot["token"],
                    "origin": boot["origin"],
                }
            )
        elif value["event"] == "ARM_PRODUCT":
            self.world.observer.arm(value["product_id"], value["request_sha"])
            self.queue.append({"event": "PRODUCT_ARMED", "product_id": value["product_id"]})
        elif value["event"] == "SHUTDOWN":
            self.queue.append({"event": "WORKER_DONE"})

    def receive(self, *, timeout: float) -> dict[str, Any]:
        assert timeout > 0
        self.world.calls.append({"kind": "ipc-read", "timeout": timeout})
        if self.world.mode == "ipc-timeout":
            self.world.clock.now += timeout
            raise TimeoutError("MOCK IPC timeout")
        return self.queue.pop(0)

    def close(self) -> None:
        self.closed = True
        if self.world.mode == "cleanup-release":
            raise RuntimeError("MOCK residual IPC handle")


class FakeProcess:
    pid = 7001

    def __init__(self, world: Any):
        self.world = world
        self.waits = 0

    def wait(self, *, timeout: float) -> int:
        assert timeout > 0
        self.waits += 1
        self.world.calls.append({"kind": "process-wait", "pid": self.pid, "timeout": timeout})
        if self.world.mode == "cleanup-exception":
            raise RuntimeError("MOCK wait exception")
        if (
            self.world.mode in {"cleanup-unknown", "cleanup-slow"}
            or self.world.mode == "slow-process"
            and self.waits < 3
        ):
            self.world.clock.now += timeout
            raise subprocess.TimeoutExpired("owned-mock-process", timeout)
        if self.world.mode == "cleanup-late":
            self.world.clock.now += 6
        if self.world.mode == "cleanup-protection":
            self.world.protected_fixture.write_bytes(b"changed during cleanup")
        return 0

    def terminate(self) -> None:
        self.world.calls.append({"kind": "process-terminate", "pid": self.pid})

    def kill(self) -> None:
        self.world.calls.append({"kind": "process-kill", "pid": self.pid})


class FakeListener:
    fd, port = -123, 19123

    def __init__(self, world: Any):
        self.world = world
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.world.calls.append({"kind": "listener-close"})


class World:
    """Lower I/O/module-loader fixtures only. The production adapter is never subclassed."""

    def __init__(self, run: Path, mode: str = "ok"):
        self.run, self.mode = run, mode
        self.clock = FakeClock()
        self.calls: list[dict[str, Any]] = []
        self.imports: list[str] = []
        self.env: dict[str, str] = {}
        self.ready_signal = mode != "false-worker-ready"
        self.product_calls = self.provider_calls = self.process_calls = self.listener_calls = 0
        self.ipc_handle: Any = None
        self.process_handle: Any = None
        self.spec: Any = None
        self.observer: Any = None
        self.protected_fixture = run / "protection-fixture.txt"
        self.protected_fixture.write_bytes(b"protected")
        self.config = SimpleNamespace(security=SimpleNamespace(), server=SimpleNamespace())
        self.token = "MOCK-PRIVATE-TOKEN-NOT-FOR-LIVE"
        self.resources = r.Resources(self.clock, self, self.load, self.listener, self.ipc, self.process, mock=True)
        self.providers = SimpleNamespace(
            OllamaProvider=lambda: SimpleNamespace(
                _resolve_endpoint=lambda loaded: ("http://127.0.0.1:11434/v1", "ollama")
            )
        )
        self.egress = SimpleNamespace(safe_urlopen=self.safe_urlopen)

    def environment(self, env: Any) -> None:
        self.env = dict(env)
        self.calls.append({"kind": "owned-env", "names": sorted(env)})

    def load(self, name: str) -> Any:
        assert self.env and self.spec is not None
        self.imports.append(name)
        self.calls.append({"kind": "module-load", "name": name})
        if name == "antigravity_k.config":
            return SimpleNamespace(config=self.config)
        if name == "antigravity_k.api.auth_routes":

            def init() -> None:
                Path(self.config.security.pin_hash_file).write_text("MOCK-HASH")
                Path(self.config.security.token_secret_file).write_text("MOCK-SECRET")

            return SimpleNamespace(
                init_auth_state=init, get_token_service=lambda: SimpleNamespace(issue_token=lambda subject: self.token)
            )
        if name == "antigravity_k.api.auth_policy":
            return SimpleNamespace(
                init_shared_auth_policy=lambda path: self.calls.append({"kind": "auth-policy", "path": path})
            )
        if name == "antigravity_k.tools.egress_policy":
            return self.egress
        if name == "antigravity_k.engine.provider_adapters.inference_providers":
            return self.providers
        if name == "antigravity_k.api.dependencies":
            profile = SimpleNamespace(provider="ollama", repo=h.MODEL_REPO)
            return SimpleNamespace(
                get_model_manager=lambda: SimpleNamespace(_registry=SimpleNamespace(get_model=lambda model: profile))
            )
        if name == "antigravity_k.engine.project_registry":
            return SimpleNamespace(ProjectRegistry=lambda storage_path: SimpleNamespace(path=storage_path))
        if name == "antigravity_k.api.server":
            return SimpleNamespace(app=SimpleNamespace(mock=True))
        raise AssertionError("unplanned product module load")

    def listener(self) -> FakeListener:
        self.listener_calls += 1
        return FakeListener(self)

    def ipc(self) -> FakeIPC:
        self.ipc_handle = FakeIPC(self)
        return self.ipc_handle

    def process(self, spec: Any, listener: Any, ipc: Any, env: Any) -> FakeProcess:
        self.process_calls += 1
        self.spec = spec
        self.observer = r.WorkerObserver(spec, self.resources)
        self.process_handle = FakeProcess(self)
        self.calls.append({"kind": "process-create", "pid": 7001, "env_names": sorted(env)})
        return self.process_handle

    def safe_urlopen(self, request: Any, *, timeout: float) -> Any:
        # Same retry shape as the current product safe_urlopen, with no real sleep.
        for attempt in range(3):
            try:
                return self.observer.urlopen(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
        raise AssertionError("retry loop exhausted without exception")

    def open(self, request: Any, *, timeout: float) -> FakeResponse:
        assert timeout > 0
        url, method = request.full_url, request.get_method()
        path = urlsplit(url).path
        self.calls.append(
            {
                "kind": "http-sink",
                "url": url,
                "method": method,
                "timeout": timeout,
                "body_sha": h.sha256(request.data or b""),
            }
        )
        if path == "/api/system/cache-stats":
            auth = request.get_header("Authorization")
            status = 200 if auth else 401
            if self.mode == "auth-401":
                status = 401
            if self.mode == "ready-timeout":
                self.clock.now = 15.01
                raise TimeoutError("MOCK readiness timeout")
            raw = h.canonical_json(True if self.mode == "ready-scalar" else {"ok": True, "stats": {}})
            return FakeResponse(raw, status, world=self)
        if path in {"/api/version", "/api/tags", "/api/ps", "/api/show"}:
            digest = "bad-digest" if self.mode == "digest-mismatch" else h.APPROVED_MODEL_DIGEST
            repo = "wrong:latest" if self.mode == "repo-mismatch" else h.MODEL_REPO
            responses = {
                "/api/version": {"version": "MOCK-v1"},
                "/api/tags": {"models": [{"name": repo, "digest": digest}]},
                "/api/ps": {"models": []},
                "/api/show": {"capabilities": [] if self.mode == "vision-mismatch" else ["vision", "completion"]},
            }
            if self.mode == "metadata-error":
                response = FakeResponse(b'{"error":"MOCK"}', 500, world=self)
                raise mock_http_error(url, 500, response)
            if self.mode == "metadata-expired":
                self.clock.now = 121
            if self.mode == "remaining-time":
                self.clock.now += 1
            if (
                path == "/api/show"
                and self.observer.phase == "bootstrap"
                and self.mode in {"source-drift", "request-drift", "binding-drift", "wire-expired"}
            ):
                if self.mode == "wire-expired":
                    self.clock.now = 121
                else:
                    name = {
                        "source-drift": "runtime_adapter.py",
                        "request-drift": "request.json",
                        "binding-drift": "execution-binding.json",
                    }[self.mode]
                    with (self.run / name).open("ab") as stream:
                        stream.write(b" ")
            return FakeResponse(h.canonical_json(responses[path]), world=self)
        if path == "/v1/chat/completions":
            self.product_calls += 1
            raw = request.data
            value = h.strict_json_loads(raw)
            assert isinstance(value, dict)
            _, image = h.load_image(self.run)
            provider = {
                "model": h.MODEL_ALIAS,
                "stream": False,
                "keep_alive": "30m",
                "think": False,
                "options": {
                    "num_ctx": 32768,
                    "num_predict": 128,
                    "temperature": 0,
                    "repeat_penalty": 1.0,
                    "min_p": 0.0,
                },
                "messages": [{"role": "user", "content": h.PROMPT_PREFIX + h.QUESTION, "images": [image]}],
            }
            upstream_request = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat", data=h.canonical_json(provider), method="POST"
            )
            try:
                with self.providers.safe_urlopen(upstream_request, timeout=timeout) as response:
                    upstream_raw = response.read()
                if self.mode == "second-provider":
                    self.observer.urlopen(
                        urllib.request.Request(upstream_request.full_url, data=upstream_request.data), timeout=timeout
                    )
                if self.mode == "unknown-path":
                    self.observer.urlopen(
                        urllib.request.Request("http://127.0.0.1:11434/api/generate", data=b"{}"), timeout=timeout
                    )
                if self.mode == "unknown-origin":
                    self.observer.urlopen(
                        urllib.request.Request("http://example.invalid/api/chat", data=upstream_request.data),
                        timeout=timeout,
                    )
            except (RuntimeError, ValueError, TimeoutError, urllib.error.HTTPError):
                return FakeResponse(b'{"error":"MOCK provider failure"}', 502, world=self)
            upstream = h.strict_json_loads(upstream_raw)
            body = h.canonical_json(
                {"choices": [{"message": {"role": "assistant", "content": upstream["message"]["content"]}}]}
            )
            if self.mode == "late-product":
                self.clock.now = 121
            return FakeResponse(body, world=self, partial=self.mode == "partial-product")
        if path == "/api/chat":
            self.provider_calls += 1
            raw = h.canonical_json(
                {"done": True, "message": {"role": "assistant", "content": '{"red_circles":2,"blue_squares":1}'}}
            )
            if self.mode in {"redirect", "provider-retry"}:
                status = 302 if self.mode == "redirect" else 503
                response = FakeResponse(b'{"error":"MOCK upstream"}', status, world=self)
                raise mock_http_error(url, status, response)
            if self.mode == "late-provider":
                self.clock.now = 121
            return FakeResponse(raw, world=self, partial=self.mode == "partial-provider")
        raise AssertionError("unclassified fake sink")


def execute(run: Path, monkeypatch: Any, mode: str = "ok") -> tuple[World, Any, dict[str, Any]]:
    world = World(run, mode)
    monkeypatch.setattr(h.time, "monotonic", world.clock.monotonic)
    descriptor = approval(run)
    authorization = h.verify_runtime_authorization(run, ROOT, descriptor, mode="OFFLINE_MOCK")
    assert authorization is not None
    journal = h.OneShotJournal(run / "task-wire-journal.jsonl")
    adapter = r.concrete_adapter_factory(run, ROOT, journal, world.resources)
    result = h.supervise_once(run=run, root=ROOT, adapter=adapter, journal=journal, authorization=authorization)
    h.write_once(
        run / "test-observation.json",
        h.canonical_json(
            {
                "source": "OFFLINE_MOCK",
                "mode": mode,
                "product": world.product_calls,
                "provider": world.provider_calls,
                "process": world.process_calls,
                "cleanup": adapter.cleanup_calls,
                "calls": world.calls,
                "imports": world.imports,
                "journal_counts": journal.counts(),
                "result": h.evidence_json(result),
            }
        ),
    )
    return world, adapter, result


@pytest.mark.parametrize(
    "kind", ["absent", "pending", "expired", "revoked", "scope", "candidate", "binding", "fixture-live"]
)
def test_imp09c_rb_01_refuse_before_factory(tmp_path: Path, monkeypatch: Any, kind: str) -> None:
    seed(tmp_path)
    world = World(tmp_path)
    descriptor: Any = approval(tmp_path)
    if kind == "absent":
        descriptor = None
    elif kind == "pending":
        descriptor["status"] = "PENDING"
    elif kind == "expired":
        descriptor["expires_at"] = "2000-01-01T00:00:00+00:00"
    elif kind == "revoked":
        descriptor["revoked"] = True
    elif kind == "scope":
        descriptor["scope"] = h.TASK_ID
    elif kind == "candidate":
        descriptor["candidate_id"] = "foreign"
    elif kind == "binding":
        descriptor["binding_sha256"] = "0" * 64
    before = (tmp_path / "execution-binding.json").read_bytes()
    code = h.runtime_cli(
        ["--live" if kind == "fixture-live" else "--mock-runtime"],
        run=tmp_path,
        root=ROOT,
        authorization_loader=lambda: descriptor,
        resources=world.resources,
    )
    assert code == 3
    assert world.process_calls == world.listener_calls == world.product_calls == world.provider_calls == 0
    assert not (tmp_path / "runtime-state").exists()
    assert (tmp_path / "execution-binding.json").read_bytes() == before


def test_imp09c_rb_02_factory_cli_supervisor(tmp_path: Path, monkeypatch: Any) -> None:
    seed(tmp_path)
    world = World(tmp_path)
    monkeypatch.setattr(h.time, "monotonic", world.clock.monotonic)
    assert (
        h.runtime_cli(
            ["--mock-runtime"],
            run=tmp_path,
            root=ROOT,
            authorization_loader=lambda: approval(tmp_path),
            resources=world.resources,
        )
        == 0
    )
    result = h.strict_json_loads((tmp_path / "runtime-cli-result.json").read_bytes())
    assert result["verdict"] == "FIXTURE_ONLY" and result["pass"] is False
    assert world.product_calls == world.provider_calls == world.process_calls == 1


def test_imp09c_rb_03_worker_bootstrap_order_secrets(tmp_path: Path, monkeypatch: Any) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch)
    assert result["verdict"] == "FIXTURE_ONLY"
    assert world.imports[0:4] == [
        "antigravity_k.config",
        "antigravity_k.api.auth_routes",
        "antigravity_k.api.auth_policy",
        "antigravity_k.tools.egress_policy",
    ]
    assert world.imports.index("antigravity_k.api.dependencies") < world.imports.index("antigravity_k.api.server")
    assert all(
        str(tmp_path) in world.env[key]
        for key in (
            "AGK_USAGE_DB",
            "AGK_AUTH_PIN_HASH_FILE",
            "AGK_AUTH_TOKEN_SECRET_FILE",
            "ANTIGRAVITY_VAULT_PATH",
            "AGK_AUDIT_LOG_DIR",
        )
    )
    assert (adapter.state / "auth/token-secret").stat().st_mode & 0o777 == 0o600
    assert world.token.encode() not in (tmp_path / "runtime-observations.jsonl").read_bytes()
    assert h.runtime_cli(["--worker"], run=tmp_path, root=ROOT) == 3
    count = len(world.imports)
    with pytest.raises(PermissionError):
        r.worker_bootstrap(
            world.spec,
            {},
            world.resources,
            parent_pid=os.getpid(),
            observer=world.observer.install,
            child_environment=world.environment,
        )
    assert len(world.imports) == count


@pytest.mark.parametrize("mode", ["auth-401", "ready-timeout", "ready-scalar", "false-worker-ready"])
def test_imp09c_rb_04_readiness_negatives(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, _, result = execute(tmp_path, monkeypatch, mode)
    assert world.product_calls == world.provider_calls == 0
    assert result["pass"] is False and result["verdict"] != "FIXTURE_ONLY"


@pytest.mark.parametrize(
    "mode", ["digest-mismatch", "repo-mismatch", "vision-mismatch", "metadata-error", "metadata-expired"]
)
def test_imp09c_rb_05_metadata_negatives(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch, mode)
    assert world.product_calls == world.provider_calls == 0
    assert adapter.journal.counts()["logical_reserved"].get("ollama_chat_inference_wire", 0) == 0
    assert result["pass"] is False


def test_imp09c_rb_06_error_response_wrapper(tmp_path: Path, monkeypatch: Any) -> None:
    seed(tmp_path)
    world = World(tmp_path, "provider-retry")
    monkeypatch.setattr(h.time, "monotonic", world.clock.monotonic)
    descriptor = h.verify_runtime_authorization(tmp_path, ROOT, approval(tmp_path), mode="OFFLINE_MOCK")
    spec = r.WorkerSpec(
        tmp_path,
        ROOT,
        tmp_path / "runtime-state",
        h.sha256((tmp_path / "execution-binding.json").read_bytes()),
        tmp_path / "journal.jsonl",
        120,
        15,
        os.getpid(),
        "private-fixture",
        "OFFLINE_MOCK",
        descriptor,
    )
    observer = r.WorkerObserver(spec, world.resources)
    journal = h.OneShotJournal(spec.journal)
    product = (tmp_path / "request.json").read_bytes()
    assert journal.reserve("product_authenticated_chat_post", "product:errors", product)
    observer.arm("product:errors", h.sha256(product))
    _, image = h.load_image(tmp_path)
    payload = {
        "model": h.MODEL_ALIAS,
        "stream": False,
        "keep_alive": "30m",
        "think": False,
        "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0, "repeat_penalty": 1.0, "min_p": 0.0},
        "messages": [{"role": "user", "content": h.PROMPT_PREFIX + h.QUESTION, "images": [image]}],
    }
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=h.canonical_json(payload))
    with pytest.raises(urllib.error.HTTPError) as raised:
        observer.urlopen(request, timeout=1)
    path = spec.state / "captures/provider-errors-response.bin"
    assert path.read_bytes() == b""  # Observer must not consume eagerly.
    assert raised.value.code == 503
    assert raised.value.readline() == b'{"error":"MOCK upstream"}'
    raised.value.close()
    assert path.read_bytes() == b'{"error":"MOCK upstream"}'
    assert journal.counts()["response_observed"]["ollama_chat_inference_wire"] == 1
    with pytest.raises(RuntimeError):
        observer.urlopen(request, timeout=1)
    assert world.provider_calls == 1


def test_imp09c_rb_06_wire_capture_reconcile(tmp_path: Path, monkeypatch: Any) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch)
    assert world.product_calls == world.provider_calls == 1
    assert result["dispatches"] == result["provider_wires"] == 1
    assert result["verdict"] == "FIXTURE_ONLY"
    assert result["gates"]["accounting_lineage"] == "PASS"
    counts = adapter.journal.counts()
    assert (
        counts["wire_entered"]["ollama_chat_inference_wire"]
        == counts["response_observed"]["ollama_chat_inference_wire"]
        == 1
    )
    assert counts["wire_entered"].get("native_inference_wire", 0) == 0
    reconciliation = [e for e in adapter.events if e["event"] == "parent-reconcile"]
    assert reconciliation[0]["new_sends"] == reconciliation[0]["new_reservations"] == 0
    provider_bytes = result["state"].provider_request_bytes
    assert provider_bytes and result["state"].provider_response_bytes
    assert all(
        h.sha256(provider_bytes) == e["request_sha256"]
        for e in adapter.journal.replay()
        if e.get("slot") == "ollama_chat_inference_wire"
    )
    metadata_slots = {
        e["slot"]
        for e in adapter.journal.replay()
        if e["event"] == "wire_entered" and str(e["slot"]).startswith("ollama_get_")
    }
    assert len(metadata_slots) == 4


@pytest.mark.parametrize("mode", ["source-drift", "request-drift", "binding-drift", "wire-expired"])
def test_imp09c_rb_07_pre_wire_drift(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, _, result = execute(tmp_path, monkeypatch, mode)
    assert world.product_calls == world.provider_calls == 0
    assert result["dispatches"] == 0 and result["pass"] is False


@pytest.mark.parametrize("mode", ["redirect", "provider-retry", "second-provider", "unknown-path", "unknown-origin"])
def test_imp09c_rb_08_no_second_sink(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch, mode)
    assert world.provider_calls == world.product_calls == 1
    assert adapter.journal.counts()["wire_entered"]["ollama_chat_inference_wire"] == 1
    # Changing candidate identity cannot replenish the retained journal.
    with pytest.raises(RuntimeError):
        h.ProviderWireGuard(tmp_path, ROOT, adapter.journal, "product:new-candidate", 120, world.clock.monotonic).enter(
            result["state"].provider_request_bytes
        )
    assert world.provider_calls == 1
    assert list((adapter.state / "captures").glob("*-response.bin"))


@pytest.mark.parametrize(
    "mode", ["remaining-time", "partial-product", "partial-provider", "late-product", "late-provider", "ipc-timeout"]
)
def test_imp09c_rb_09_bounded_partial_unknown(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch, mode)
    assert all(c["timeout"] > 0 for c in world.calls if "timeout" in c)
    assert world.product_calls <= 1 and world.provider_calls <= 1
    if mode.startswith("partial-"):
        paths = list(adapter.state.rglob("*-response.bin"))
        assert any(p.stat().st_size == 7 for p in paths)
    if mode == "ipc-timeout":
        assert world.product_calls == world.provider_calls == result["dispatches"] == 0
    if mode != "remaining-time":
        assert result["pass"] is False
    else:
        sinks = [c["timeout"] for c in world.calls if c["kind"] == "http-sink"]
        assert min(sinks) < 120
        assert result["verdict"] == "FIXTURE_ONLY"


@pytest.mark.parametrize("mode", ["ok", "slow-process"])
def test_imp09c_rb_10_owned_shutdown_reap(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    world, adapter, result = execute(tmp_path, monkeypatch, mode)
    cleanup = result["state"].cleanup_receipt
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert cleanup["exit_code"] == 0 and cleanup["reaped"] is True
    assert cleanup["os_exit_observation"] == "NOT_OBSERVED"
    assert cleanup["elapsed_seconds"] < 5
    operations = [c["kind"] for c in world.calls if c["kind"].startswith("process-") and c["kind"] != "process-create"]
    assert operations == (
        ["process-wait"]
        if mode == "ok"
        else ["process-wait", "process-terminate", "process-wait", "process-kill", "process-wait"]
    )
    assert all(c["pid"] == 7001 for c in world.calls if c["kind"].startswith("process-") and "pid" in c)


@pytest.mark.parametrize(
    "mode",
    ["cleanup-release", "cleanup-exception", "cleanup-unknown", "cleanup-slow", "cleanup-late", "cleanup-protection"],
)
def test_imp09c_rb_11_cleanup_final_gate(tmp_path: Path, monkeypatch: Any, mode: str) -> None:
    seed(tmp_path)
    if mode == "cleanup-protection":
        original = h.source_snapshot
        fixture = tmp_path / "protection-fixture.txt"

        def snapshot(root: Path) -> dict[str, object]:
            result = original(root)
            if fixture.exists() and fixture.read_bytes() != b"protected":
                result["ready"] = False
            return result

        monkeypatch.setattr(h, "source_snapshot", snapshot)
    world, adapter, result = execute(tmp_path, monkeypatch, mode)
    assert adapter.cleanup_calls == result["cleanup_calls"] == 1
    assert world.product_calls == world.provider_calls == 1
    assert result["pass"] is False
    if mode == "cleanup-protection":
        assert result["gates"]["protected_before_after"] == "FAIL"
    else:
        assert result["gates"]["cleanup_owned_exit"] != "PASS"
    receipt = h._call_cleanup_once(adapter, {"cleanup_deadline_monotonic": 125}, result["state"])
    assert receipt is result["state"].cleanup_receipt and adapter.cleanup_calls == 1


def test_imp09c_rb_12_delivered_candidate_cli(tmp_path: Path, monkeypatch: Any) -> None:
    # Consume the real delivered candidate, not a freshly generated empty fixture.
    binding, raw, sources = h.validate_execution_binding(RUN, ROOT)
    assert set(sources) == set(h.IMPLEMENTATION_SOURCE_NAMES)
    assert binding["runtime_contract_sha256"] == h.sha256((RUN / "runtime-bridge-contract.json").read_bytes())
    assert binding["authorization"]["status"] == "LIVE_AUTHORIZATION_NOT_ISSUED"
    assert h.runtime_cli(["--live"], run=RUN, root=ROOT) == 3
    manifest = h.write_implementation_source_manifest(RUN, ROOT)
    assert manifest["execution_binding_sha256"] == h.sha256(raw)
    assert (RUN / "execution-binding.json").read_bytes() == raw
    assert not any(name.startswith("antigravity_k.api") for name in __import__("sys").modules)
    delivered_run = RUN / "delivery-probes" / h.EXECUTION_BINDING_ATTEMPT_ID
    seed(delivered_run)
    for name in h.IMPLEMENTATION_SOURCE_NAMES:
        assert (delivered_run / name).read_bytes() == (RUN / name).read_bytes()
    world = World(delivered_run)
    monkeypatch.setattr(h.time, "monotonic", world.clock.monotonic)
    assert (
        h.runtime_cli(
            ["--mock-runtime"],
            run=delivered_run,
            root=ROOT,
            authorization_loader=lambda: approval(delivered_run),
            resources=world.resources,
        )
        == 0
    )
    delivered_result = h.strict_json_loads((delivered_run / "runtime-cli-result.json").read_bytes())
    assert delivered_result["verdict"] == "FIXTURE_ONLY"
    assert (RUN / "execution-binding.json").read_bytes() == raw
    h.write_once(
        delivered_run / "delivered-runtime-observation.json",
        h.canonical_json(
            {
                "source": "OFFLINE_MOCK",
                "mode": "delivered-candidate",
                "product": world.product_calls,
                "provider": world.provider_calls,
                "process": world.process_calls,
                "cleanup": 1,
                "calls": world.calls,
                "imports": world.imports,
                "binding_sha256": h.sha256(raw),
            }
        ),
    )
