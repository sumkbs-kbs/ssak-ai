from __future__ import annotations

import ast
import importlib.util
import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http.client import HTTPMessage, HTTPResponse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
import yaml

RUN = Path(__file__).resolve().parent
ROOT = next(parent for parent in RUN.parents if parent.name == "Ssak-Ai")
ADAPTER_PATH = RUN / "runtime_adapter.py"
HARNESS_PATH = RUN / "run_harness.py"
PROVIDER_PATH = ROOT / "src/antigravity_k/engine/provider_adapters/inference_providers.py"
CONFIG_PATH = ROOT / "config.yaml"


def load_harness() -> Any:
    spec = importlib.util.spec_from_file_location("run_harness", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["run_harness"] = module
    spec.loader.exec_module(module)
    return module


def load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location("runtime_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["run_harness"] = sys.modules.get("run_harness") or load_harness()
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness() -> Any:
    return load_harness()


@pytest.fixture
def adapter(harness: Any) -> Any:
    return load_adapter()


def origin_key(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        raise ValueError("origin outside frozen HTTP loopback contract")
    if parsed.query or parsed.fragment:
        raise ValueError("origin contains query/fragment")
    if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.port != 11434:
        raise ValueError("origin outside frozen Ollama endpoint")
    return "http", "127.0.0.1", 11434


class FakeSocket:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


class Raw:
    def __init__(self, sock: FakeSocket) -> None:
        self._sock = sock


class Buffered:
    def __init__(self, body: bytes, sock: FakeSocket) -> None:
        self.raw = Raw(sock)
        self._body = io.BytesIO(body)

    def tell(self) -> int:
        return self._body.tell()

    def flush(self) -> None:
        self._body.flush()

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def readline(self, amount: int = -1) -> bytes:
        return self._body.readline(amount)

    def close(self) -> None:
        self._body.close()

    def isclosed(self) -> bool:
        return self._body.closed

    @property
    def closed(self) -> bool:
        return self._body.closed


def genuine_http_response(body: bytes, status: int, sock: FakeSocket, url: str) -> HTTPResponse:
    response = cast(Any, HTTPResponse.__new__(HTTPResponse))
    response.fp = cast(Any, Buffered(body, sock))
    response._closed = False
    response._method = "GET"
    response.status = status
    response.reason = "fixture"
    response.headers = cast(HTTPMessage, Message())
    response.headers["Content-Type"] = "application/json"
    response.version = 11
    response.chunked = False
    response.chunk_left = None
    response.length = len(body)
    response.will_close = False
    response.url = url
    return response


class HttpResponseFixture:
    def __init__(self, body: bytes, status: int, sock: FakeSocket) -> None:
        self.status = status
        self.code = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.fp = Buffered(body, sock)
        self.closed = False
        self._body = body
        self._cursor = 0

    def flush(self) -> None:
        self.fp.flush()

    def read(self, amount: int = -1) -> bytes:
        chunk = self.fp.read(amount)
        self._cursor += len(chunk)
        return chunk

    def readline(self, amount: int = -1) -> bytes:
        chunk = self.fp.readline(amount)
        self._cursor += len(chunk)
        return chunk

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self.closed = True
        self.fp.close()

    def isclosed(self) -> bool:
        return self.closed or self.fp.isclosed() or self._cursor >= len(self._body)


class Opener:
    def __init__(self, replies: list[tuple[int, bytes]]) -> None:
        self.replies = list(replies)
        self.sockets: list[FakeSocket] = []
        self.responses: list[Any] = []
        self.requests: list[tuple[str, bytes]] = []

    def open(self, request: urllib.request.Request, *, timeout: float) -> HttpResponseFixture:
        assert timeout > 0
        status, body = self.replies.pop(0)
        sock = FakeSocket()
        self.sockets.append(sock)
        request_body = cast(bytes, request.data or b"")
        self.requests.append((request.full_url, request_body))
        if status >= 400:
            response = genuine_http_response(body, status, sock, request.full_url)
            self.responses.append(response)
            raise urllib.error.HTTPError(request.full_url, status, "fixture", response.headers, cast(Any, response))
        response = HttpResponseFixture(body, status, sock)
        self.responses.append(response)
        return response


class FakeClock:
    def monotonic(self) -> float:
        return 10.0


def test_imp09c_rc_01_source_bound_resolver_bootstrap_accepts_configured_localhost(adapter: Any, harness: Any) -> None:
    config_bytes = CONFIG_PATH.read_bytes()
    provider_source = PROVIDER_PATH.read_bytes()
    config_data = yaml.safe_load(config_bytes)
    configured_origin = config_data["providers"]["ollama"]["base_url"]
    tree = ast.parse(provider_source.decode("utf-8"), filename=str(PROVIDER_PATH))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OllamaProvider")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_resolve_endpoint")
    method.body = [
        node for node in method.body if not (isinstance(node, ast.ImportFrom) and node.module == "antigravity_k.config")
    ]
    extracted = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(extracted)
    config = SimpleNamespace(model=SimpleNamespace(api_base=configured_origin, api_key=""))
    namespace: dict[str, Any] = {
        "__name__": "source_bound_resolver",
        "os": SimpleNamespace(environ={}),
        "config": config,
    }
    exec(compile(extracted, str(PROVIDER_PATH), "exec"), namespace)
    resolver = namespace["_resolve_endpoint"]
    provider = SimpleNamespace(_registry_provider_base=lambda name: configured_origin if name == "ollama" else "")
    profile = SimpleNamespace(api_base="", name="qwen3.8")
    endpoint, key = resolver(provider, SimpleNamespace(profile=profile))
    assert endpoint == "http://localhost:11434/v1" and key == "ollama"
    assert adapter.provider_url_key(endpoint) == adapter.provider_url_key(configured_origin + "/v1")
    assert harness.sha256(config_bytes) == harness.SOURCE_EXPECTATIONS["config.yaml"]
    assert (
        harness.sha256(provider_source)
        == harness.SOURCE_EXPECTATIONS["src/antigravity_k/engine/provider_adapters/inference_providers.py"]
    )
    assert origin_key(endpoint.removesuffix("/v1")) == origin_key("http://127.0.0.1:11434")
    assert adapter.origin_key("http://localhost:11434") == adapter.origin_key("http://127.0.0.1:11434")
    assert adapter.origin_key("http://localhost:11434/v1") == adapter.origin_key("http://127.0.0.1:11434/v1")

    # Exercise the same concrete worker bootstrap with only owned lower-level modules/resources injected.
    import os
    import sys
    from datetime import UTC, datetime, timedelta

    class ResolverProvider:
        _registry_provider_base = staticmethod(lambda name: configured_origin if name == "ollama" else "")
        _resolve_endpoint = resolver

    state = RUN / "offline-state/rc01-bootstrap/state"
    journal = RUN / "offline-state/rc01-bootstrap/journal.jsonl"
    state.mkdir(parents=True, exist_ok=True)
    (state / "auth").mkdir(parents=True, exist_ok=True)
    registry_path = RUN / "offline-state/registry/projects.json"
    workspace = RUN / "offline-state/workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    request = harness.strict_json_loads((RUN / "request.json").read_bytes())
    registry_path.write_bytes(
        harness.canonical_json(
            [
                {
                    "id": request["project_id"],
                    "name": "imp09c-product-vision",
                    "path": str(workspace.resolve()),
                    "is_active": True,
                    "last_accessed_at": None,
                    "tasks": [],
                }
            ]
        )
    )
    calls: list[str] = []
    child_env: dict[str, str] = {}
    config = SimpleNamespace(
        security=SimpleNamespace(),
        server=SimpleNamespace(),
        model=SimpleNamespace(api_base=configured_origin, api_key=""),
    )
    profile = SimpleNamespace(provider="ollama", repo=harness.MODEL_REPO, api_base="", name="qwen3.8")
    manager = SimpleNamespace(_registry=SimpleNamespace(get_model=lambda name: profile))
    modules: dict[str, Any] = {
        "antigravity_k.config": SimpleNamespace(config=config),
        "antigravity_k.api.auth_routes": SimpleNamespace(
            init_auth_state=lambda: (
                Path(config.security.pin_hash_file).write_text("fixture-pin-hash"),
                Path(config.security.token_secret_file).write_text("fixture-token-secret"),
            ),
            get_token_service=lambda: SimpleNamespace(issue_token=lambda subject: "MOCK_TOKEN"),
        ),
        "antigravity_k.api.auth_policy": SimpleNamespace(
            init_shared_auth_policy=lambda path: calls.append("auth-policy")
        ),
        "antigravity_k.tools.egress_policy": SimpleNamespace(safe_urlopen=lambda *args, **kwargs: None),
        "antigravity_k.engine.provider_adapters.inference_providers": SimpleNamespace(OllamaProvider=ResolverProvider),
        "antigravity_k.api.dependencies": SimpleNamespace(get_model_manager=lambda: manager),
        "antigravity_k.engine.project_registry": SimpleNamespace(
            ProjectRegistry=lambda storage_path: SimpleNamespace(path=storage_path)
        ),
        "antigravity_k.api.server": SimpleNamespace(app=SimpleNamespace(offline_fixture=True)),
    }
    run_binding, frozen_binding, implementation_sources = harness.validate_execution_binding(RUN, ROOT)
    binding_sha = harness.sha256(frozen_binding)
    now = datetime.now(UTC)
    authorization = {
        "status": "VERIFIED_RUNTIME_AUTHORIZATION",
        "scope": harness.TASK_ID,
        "mode": "OFFLINE_MOCK",
        "descriptor": {
            "fixture_only": True,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
        },
    }
    spec = adapter.WorkerSpec(
        RUN,
        ROOT,
        state,
        binding_sha,
        journal,
        120.0,
        15.0,
        os.getpid(),
        "private-fixture-challenge",
        "OFFLINE_MOCK",
        authorization,
    )
    observed: list[str] = []
    runtime = adapter.worker_bootstrap(
        spec,
        {"challenge": spec.challenge},
        adapter.Resources(
            FakeClock(),
            Opener([]),
            lambda name: calls.append(name) or modules[name],
            lambda: None,
            lambda: None,
            lambda *args: None,
            True,
        ),
        parent_pid=os.getpid(),
        observer=lambda egress, provider_module: observed.append("observer-installed"),
        child_environment=lambda env: child_env.update(env),
    )
    assert runtime["origin"] == "http://localhost:11434"
    assert adapter.provider_url_key(runtime["origin"]) == adapter.provider_url_key("http://127.0.0.1:11434")
    assert observed == ["observer-installed"]
    assert child_env["AGK_CONFIG_FILE"] == str(state / "config/owned-config.yaml")
    assert (state / "config/owned-config.yaml").read_bytes() == config_bytes
    _validated_binding, frozen_binding, implementation_sources = harness.validate_execution_binding(RUN, ROOT)
    assert binding_sha == harness.sha256(frozen_binding)
    assert run_binding["candidate_binding_sha256"] == harness.sha256(harness.canonical_json(implementation_sources))
    assert not any(name.startswith("antigravity_k.api") for name in sys.modules)


def provider_body(harness: Any) -> bytes:
    _, image = harness.load_image(RUN)
    return harness.canonical_json(
        {
            "model": harness.MODEL_ALIAS,
            "stream": False,
            "keep_alive": "30m",
            "think": False,
            "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0, "repeat_penalty": 1.0, "min_p": 0.0},
            "messages": [{"role": "user", "content": harness.PROMPT_PREFIX + harness.QUESTION, "images": [image]}],
        }
    )


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_imp09c_rc_02_origin_classifier_journal_and_raw_request(host: str, harness: Any, tmp_path: Path) -> None:
    raw = provider_body(harness)
    url = f"http://{host}:11434/api/chat"
    request = urllib.request.Request(url, data=raw, method="POST")
    slot = harness.classify_upstream_request(request.full_url, request.get_method(), request.data or b"")
    journal = harness.OneShotJournal(tmp_path / f"{host}.jsonl")
    logical_id = f"provider:{host}"
    assert journal.reserve(slot, logical_id, raw)
    assert journal.enter_wire(slot, logical_id, raw)
    response = b'{"done":true}'
    journal.record_response(slot, logical_id, raw, response, 200)
    capture = {
        "url": request.full_url,
        "canonical_origin": harness.canonical_provider_origin(request.full_url),
        "origin_policy": harness.PROVIDER_ORIGIN_POLICY,
        "request_sha256": harness.sha256(request.data or b""),
    }
    assert capture["url"] == url
    assert request.data == raw
    assert capture["canonical_origin"] == "http://127.0.0.1:11434"
    assert capture["origin_policy"] == harness.PROVIDER_ORIGIN_POLICY
    counts = journal.counts()
    assert counts["logical_reserved"][slot] == 1
    assert counts["wire_entered"][slot] == 1
    assert counts["response_observed"][slot] == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost:11434",
        "http://localhost:11435",
        "http://user@localhost:11434",
        "http://localhost:11434?x=1",
        "http://localhost:11434#frag",
        "http://localhost.evil:11434",
        "http://127.0.0.2:11434",
        "http://[::1]:11434",
    ],
)
def test_imp09c_rc_03_forbidden_origins_and_url_variants_fail_closed(adapter: Any, url: str) -> None:
    with pytest.raises(ValueError):
        adapter.origin_key(url)


@pytest.mark.parametrize("anonymous_status", [401, 403, 429])
def test_imp09c_rc_04_http_error_readiness_is_bounded_and_closeable(
    adapter: Any, harness: Any, tmp_path: Path, anonymous_status: int
) -> None:
    opener = Opener([(anonymous_status, b'{"error":"auth"}'), (200, b'{"ok":true,"stats":{}}')])
    http = adapter.StdlibHTTP()
    http.opener = opener
    resources = adapter.Resources(
        FakeClock(), http, lambda name: None, lambda: None, lambda: None, lambda *args: None, True
    )
    concrete = adapter.ConcreteRuntimeAdapter(tmp_path, ROOT, harness.OneShotJournal(tmp_path / "j.jsonl"), resources)
    anonymous = urllib.request.Request("http://127.0.0.1:19123/api/system/cache-stats")
    status_a, _, body_a = concrete._exchange(anonymous, 20, "anonymous-ready")
    bearer = urllib.request.Request(anonymous.full_url, headers={"Authorization": "Bearer MOCK"})
    status_b, _, body_b = concrete._exchange(bearer, 20, "bearer-ready")
    assert (status_a, body_a) == (anonymous_status, b'{"error":"auth"}')
    assert (status_b, body_b) == (200, b'{"ok":true,"stats":{}}')
    assert all(all(value > 0 for value in sock.timeouts) for sock in opener.sockets)
    assert opener.sockets[0].timeouts == [10.0]
    assert opener.sockets[1].timeouts == [10.0, 10.0]
    observed_statuses = [
        int(json.loads(path.read_text(encoding="utf-8"))["status"])
        for path in sorted((concrete.state / "parent-captures").glob("*-headers.json"))
    ]
    assert sorted(observed_statuses) == sorted([anonymous_status, 200])
    assert opener.requests == [(anonymous.full_url, b""), (bearer.full_url, b"")]
    assert len(opener.requests) == 2 and all(response.isclosed() for response in opener.responses)


def test_imp09c_rc_05_genuine_http_error_is_lazy_and_recorded_by_observer(
    adapter: Any, harness: Any, tmp_path: Path
) -> None:
    url = "http://localhost:11434/api/chat"
    original = b'{"error":"upstream unavailable"}\n'
    opener = Opener([(503, original)])
    resources = adapter.Resources(
        FakeClock(), adapter.StdlibHTTP(), lambda name: None, lambda: None, lambda: None, lambda *args: None, True
    )
    resources.http.opener = opener
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    spec = SimpleNamespace(run=RUN, root=ROOT, journal=tmp_path / "journal.jsonl", state=state_dir, deadline=30.0)
    observer = adapter.WorkerObserver(spec, resources)
    journal = harness.OneShotJournal(spec.journal)
    observer.journal = journal
    product = (RUN / "request.json").read_bytes()
    assert journal.reserve("product_authenticated_chat_post", "product:errors", product)
    observer.arm("product:errors", harness.sha256(product))
    payload = {
        "model": harness.MODEL_ALIAS,
        "stream": False,
        "keep_alive": "30m",
        "think": False,
        "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0, "repeat_penalty": 1.0, "min_p": 0.0},
        "messages": [
            {
                "role": "user",
                "content": harness.PROMPT_PREFIX + harness.QUESTION,
                "images": [harness.load_image(RUN)[1]],
            }
        ],
    }
    body = harness.canonical_json(payload)
    request = urllib.request.Request(url, data=body, method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        observer.urlopen(request, timeout=12)
    error = caught.value
    capture = state_dir / "captures/provider-errors-response.bin"
    assert error.code == 503 and error.url == url and error.reason == "fixture"
    assert error.headers is opener.responses[0].headers
    assert error.getcode() == 503 and error.geturl() == url and error.info() is opener.responses[0].headers
    assert capture.read_bytes() == b"" and opener.responses[0].fp.tell() == 0
    assert opener.sockets[0].timeouts == []
    assert error.read(8) == original[:8]
    assert capture.read_bytes() == original[:8] and opener.sockets[0].timeouts[0] == 20.0

    assert error.readline() == original[8:]
    assert capture.read_bytes() == original
    assert opener.sockets[0].timeouts == [20.0, 20.0]
    assert opener.responses[0].isclosed() and opener.responses[0].fp is None

    error.close()
    error.close()
    assert opener.responses[0].isclosed()
    counts = journal.counts()
    assert counts["logical_reserved"].get("ollama_chat_inference_wire") == 1
    assert counts["wire_entered"].get("ollama_chat_inference_wire") == 1
    assert counts["response_observed"].get("ollama_chat_inference_wire") == 1
    assert opener.requests == [(url, body)]


def test_imp09c_rc_06_nested_http_response_owner_timeout_and_delegation(adapter: Any) -> None:
    opener = Opener([(401, b"unauthorized")])
    http = adapter.StdlibHTTP()
    http.opener = opener
    request = urllib.request.Request("http://127.0.0.1:11434/api/version")
    with pytest.raises(urllib.error.HTTPError) as caught:
        http.open(request, timeout=1)
    error = caught.value
    response = opener.responses[0]
    assert isinstance(error, urllib.error.HTTPError)
    assert error.code == 401 and error.url == request.full_url and error.reason == "fixture"
    assert error.headers is response.headers
    assert error.response is response
    assert error.fp is response
    assert error._delegate.response is response
    assert error._delegate.body_owner is response
    assert response.fp.raw._sock is opener.sockets[0]
    assert error.getcode() == 401 and error.geturl() == request.full_url and error.info() is response.headers
    error.set_timeout(0.75)
    assert opener.sockets[0].timeouts == [0.75]
    assert error.read(4) == b"unau"
    assert response.fp.tell() == 4
    assert error.readline() == b"thorized"
    assert response.isclosed() and response.fp is None
    error.close()
    error.close()
    assert response.isclosed()


def test_imp09c_rc_06_success_body_and_open_body_without_socket_are_explicit(adapter: Any) -> None:
    success = Opener([(200, b'{"ok":true}')])
    http = adapter.StdlibHTTP()
    http.opener = success
    response = http.open(urllib.request.Request("http://localhost:11434/api/version"), timeout=3)
    response.set_timeout(1.5)
    assert response.read(6) == b'{"ok":'
    assert response.readline() == b"true}"
    assert response.read() == b""
    response.close()
    assert success.responses[0].isclosed() and success.sockets[0].timeouts == [1.5]

    class OpenWithoutSocket:
        status = 503
        code = 503
        headers = Message()
        fp = SimpleNamespace(raw=None)

        def isclosed(self) -> bool:
            return False

    with pytest.raises(RuntimeError, match="no bounded socket"):
        adapter.SocketResponse(OpenWithoutSocket()).set_timeout(1)


def test_imp09c_rc_07_live_authority_is_not_issued_and_denies_factory(harness: Any) -> None:
    class Factory:
        calls = 0

        def __call__(self) -> object:
            self.calls += 1
            raise AssertionError("factory must remain unreachable")

    factory = Factory()
    allowed, reason = harness.live_mode_guard(requested=True, authorization=None, adapter_factory=factory)
    assert not allowed and "authorization" in reason and factory.calls == 0
    allowed, reason = harness.live_mode_guard(
        requested=True,
        authorization={"status": "VERIFIED_RUNTIME_AUTHORIZATION", "mode": "OFFLINE_MOCK", "scope": harness.TASK_ID},
        adapter_factory=factory,
    )
    assert not allowed and factory.calls == 0
    assert (RUN / "execution-binding.json").is_file()
    binding = harness.validate_execution_binding(RUN, ROOT)[0]
    assert binding["task_id"] == harness.TASK_ID
    origin_contract_raw = (RUN / "runtime-bridge-contract.json").read_bytes()
    origin_contract = harness.strict_json_loads(origin_contract_raw)
    assert isinstance(origin_contract, dict)
    assert origin_contract["preparation_task"] == harness.TASK_ID
    assert origin_contract["live_authorization"] == "NOT_ISSUED"
    assert origin_contract["independent_review"] == "PENDING"
    assert binding["origin_contract_sha256"] == harness.sha256(origin_contract_raw)
    assert binding["endpoint_contract_sha256"] == harness.sha256((RUN / "endpoint-contract.json").read_bytes())
    assert origin_contract["provider_origin_contract"]["configured_base_url"] == "http://localhost:11434"
    cli_factory = Factory()
    cli_status = harness.runtime_cli(["--live"], run=RUN, root=ROOT)
    assert cli_status == 3 and cli_factory.calls == 0
    assert not (RUN / "runtime-cli-result.json").exists()
    assert harness.NEXT_REVIEW == "CODEX_REVIEW_IMP-09-C-PRODUCT-VISION-RUNTIME-COMPATIBILITY-01"
