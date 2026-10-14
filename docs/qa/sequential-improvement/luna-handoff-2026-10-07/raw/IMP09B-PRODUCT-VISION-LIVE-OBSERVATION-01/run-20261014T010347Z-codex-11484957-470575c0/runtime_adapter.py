from __future__ import annotations

import importlib
import os
import secrets
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import IO, Any, Never, Protocol, cast
from urllib.parse import urlsplit

h = importlib.import_module("run_harness")


class Clock(Protocol):
    def monotonic(self) -> float: ...


class HttpResponse(Protocol):
    @property
    def status(self) -> int: ...
    @property
    def headers(self) -> Mapping[str, str]: ...

    def set_timeout(self, timeout: float) -> None: ...
    def read(self, amount: int = -1) -> bytes: ...
    def readline(self, amount: int = -1) -> bytes: ...
    def close(self) -> None: ...


class HttpOpener(Protocol):
    def open(self, request: urllib.request.Request, *, timeout: float) -> HttpResponse: ...


class ProcessHandle(Protocol):
    pid: int

    def wait(self, *, timeout: float) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


class PrivateIPC(Protocol):
    @property
    def child_env(self) -> Mapping[str, str]: ...
    @property
    def pass_fds(self) -> tuple[int, ...]: ...

    def send(self, value: Mapping[str, object], *, timeout: float) -> None: ...
    def receive(self, *, timeout: float) -> dict[str, Any]: ...
    def close(self) -> None: ...


class JournalPort(Protocol):
    path: Path

    def counts(self) -> dict[str, dict[str, int]]: ...

    def replay(self) -> list[dict[str, object]]: ...
    def reserve(self, slot: str, logical_id: str, request_bytes: bytes) -> bool: ...
    def enter_wire(self, slot: str, logical_id: str, request_bytes: bytes) -> bool: ...
    def record_response(
        self, slot: str, logical_id: str, request_bytes: bytes, response_bytes: bytes, status: int | None
    ) -> None: ...


class StatePort(Protocol):
    dispatches: int
    provider_wires: int
    product_response_bytes: bytes
    provider_request_bytes: bytes
    provider_response_bytes: bytes


class Listener(Protocol):
    port: int
    fd: int

    def close(self) -> None: ...


@dataclass(frozen=True)
class WorkerSpec:
    run: Path
    root: Path
    state: Path
    binding_sha: str
    journal: Path
    deadline: float
    readiness_deadline: float
    parent_pid: int
    challenge: str
    mode: str
    authorization: Mapping[str, object]


@dataclass(frozen=True)
class Resources:
    clock: Clock
    http: HttpOpener
    modules: Callable[[str], Any]
    listener: Callable[[], Listener]
    ipc: Callable[[], PrivateIPC]
    process: Callable[[WorkerSpec, Listener, PrivateIPC, Mapping[str, str]], ProcessHandle]
    mock: bool = False


def remaining(clock: Clock, deadline: float, cap: float | None = None) -> float:
    value = deadline - clock.monotonic()
    if cap is not None:
        value = min(value, cap)
    if value <= 0:
        raise TimeoutError("runtime deadline exhausted before boundary")
    return value


def origin_key(url: str) -> str:
    return h.canonical_provider_origin(url)


class ExchangeDeadlineExceeded(TimeoutError):
    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        super().__init__(f"HTTP exchange absolute deadline exhausted: {deadline}")


class ExchangeTimerUnavailable(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"HTTP exchange timer unavailable: {reason}")


@contextmanager
def exchange_deadline(resources: Resources, deadline: float) -> Iterator[None]:
    """Own SIGALRM only during parent I/O; release it before supervisor cleanup."""
    if resources.mock:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise ExchangeTimerUnavailable("main thread required")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ExchangeTimerUnavailable("ITIMER_REAL already owned")
    duration = remaining(resources.clock, deadline)
    previous = signal.getsignal(signal.SIGALRM)
    if previous is None:
        raise ExchangeTimerUnavailable("unknown SIGALRM handler cannot be restored")

    def expired(signum: int, frame: FrameType | None) -> Never:
        raise ExchangeDeadlineExceeded(deadline)

    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, duration)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def provider_url_key(url: str) -> str:
    """Compare provider origins while preserving (but not normalizing) the actual request URL."""
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        raise ValueError("provider URL contains query or fragment")
    return origin_key(f"{parsed.scheme}://{parsed.netloc}")


def safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(k).lower(): str(v)
        for k, v in headers.items()
        if str(k).lower() in {"content-type", "content-length", "date"}
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class SocketResponse:
    def __init__(self, response: Any, *, body_owner: Any | None = None):
        self.response = response
        self.body_owner = response if body_owner is None else body_owner
        self.status = int(getattr(response, "status", getattr(response, "code", 0)))
        self.headers = response.headers

    def _walk_response_owners(self) -> list[Any]:
        pending = [self.response, self.body_owner]
        seen: set[int] = set()
        owners: list[Any] = []
        while pending:
            owner = pending.pop()
            if id(owner) in seen:
                continue
            seen.add(id(owner))
            owners.append(owner)
            for name in ("fp", "response", "raw"):
                nested = getattr(owner, name, None)
                if nested is not None:
                    pending.append(nested)
        return owners

    def set_timeout(self, timeout: float) -> None:
        if timeout <= 0:
            raise TimeoutError("HTTP response deadline exhausted before socket read")
        owners = self._walk_response_owners()
        for owner in owners:
            raw_socket = getattr(getattr(owner, "raw", None), "_sock", None)
            if raw_socket is not None:
                raw_socket.settimeout(timeout)
                return
        # EOF has no blocking read left; an open body without a socket is not bounded.
        if any(getattr(owner, "isclosed", lambda: False)() for owner in owners):
            return
        raise RuntimeError("HTTP response has no bounded socket read boundary")

    def read(self, amount: int = -1) -> bytes:
        if amount > 0 and callable(getattr(self.body_owner, "read1", None)):
            chunk: bytes = self.body_owner.read1(amount)
            return chunk
        return cast(bytes, self.body_owner.read(amount))

    def readline(self, amount: int = -1) -> bytes:
        return cast(bytes, self.body_owner.readline(amount))

    def close(self) -> None:
        self.body_owner.close()


class DelegatedHTTPError(urllib.error.HTTPError):
    """HTTPError retaining urllib metadata while bounding all body operations."""

    response: Any

    @property
    def status(self) -> int:
        return self.code

    def __init__(self, error: urllib.error.HTTPError, delegate: Any, response: Any):
        super().__init__(error.url, error.code, error.reason, error.headers, cast(IO[bytes], cast(object, response)))
        self.response = response
        self._delegate = delegate

    def set_timeout(self, timeout: float) -> None:
        self._delegate.set_timeout(timeout)

    def read(self, n: int = -1) -> bytes:
        return cast(bytes, self._delegate.read(n))

    def readline(self, limit: int = -1) -> bytes:
        return cast(bytes, self._delegate.readline(limit))

    def close(self) -> None:
        self._delegate.close()


class StdlibHTTP:
    def __init__(self) -> None:
        self.opener: Any | None = None

    def open(self, request: urllib.request.Request, *, timeout: float) -> HttpResponse:
        if self.opener is None:
            self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            response = SocketResponse(self.opener.open(request, timeout=timeout))
            return response
        except urllib.error.HTTPError as exc:
            # Keep urllib's HTTPResponse in HTTPError.fp; delegate bounded body operations separately.
            response = exc.fp
            if response is None:
                raise
            delegate = SocketResponse(response, body_owner=response)
            raise DelegatedHTTPError(exc, delegate, response) from exc


class OwnedListener:
    def __init__(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(8)
            self.port = int(self.socket.getsockname()[1])
            self.fd = self.socket.fileno()
        except BaseException:
            self.socket.close()
            raise

    def close(self) -> None:
        self.socket.close()


class PipeIPC:
    """Two bounded private pipes; no secret appears in process argv or public captures."""

    def __init__(self) -> None:
        self.child_read, self.parent_write = os.pipe()
        self.parent_read, self.child_write = os.pipe()
        self.child_env = {"RB_CONTROL_FD": str(self.child_read), "RB_RECEIPT_FD": str(self.child_write)}
        self.pass_fds = (self.child_read, self.child_write)
        self.pending = bytearray()

    def send(self, value: Mapping[str, object], *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        data = h.canonical_json(dict(value)) + b"\n"
        if len(data) > 65536:
            raise ValueError("private IPC frame too large")
        offset = 0
        while offset < len(data):
            duration = remaining(time, deadline)
            if not select.select([], [self.parent_write], [], duration)[1]:
                raise TimeoutError("private IPC write timeout")
            offset += os.write(self.parent_write, data[offset : offset + 4096])

    def receive(self, *, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while b"\n" not in self.pending:
            duration = remaining(time, deadline)
            if not select.select([self.parent_read], [], [], duration)[0]:
                raise TimeoutError("private IPC read timeout")
            chunk = os.read(self.parent_read, 4096)
            if not chunk:
                raise EOFError("worker IPC closed before receipt")
            self.pending.extend(chunk)
            if len(self.pending) > 65536:
                raise ValueError("private IPC receipt too large")
        raw, _, rest = self.pending.partition(b"\n")
        self.pending = bytearray(rest)
        value = h.strict_json_loads(bytes(raw))
        if not isinstance(value, dict):
            raise ValueError("private IPC receipt is not object")
        return value

    def close(self) -> None:
        errors: list[OSError] = []
        for fd in (self.child_read, self.parent_write, self.parent_read, self.child_write):
            try:
                os.close(fd)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise errors[0]


def spawn_owned(spec: WorkerSpec, listener: Listener, ipc: PrivateIPC, env: Mapping[str, str]) -> ProcessHandle:
    child_env = dict(env)
    child_env.update(ipc.child_env)
    child_env["RB_LISTENER_FD"] = str(listener.fd)
    # Secrets and authority descriptor are sent only through inherited private IPC.
    proc = subprocess.Popen(
        [sys.executable, "-B", str(spec.run / "runtime_adapter.py"), "--worker"],
        cwd=spec.state,
        env=child_env,
        pass_fds=(*ipc.pass_fds, listener.fd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc


def concrete_resources() -> Resources:
    return Resources(time, StdlibHTTP(), importlib.import_module, OwnedListener, PipeIPC, spawn_owned)


def serialize_spec(spec: WorkerSpec) -> dict[str, object]:
    return {
        "run": str(spec.run),
        "root": str(spec.root),
        "state": str(spec.state),
        "binding_sha": spec.binding_sha,
        "journal": str(spec.journal),
        "deadline": spec.deadline,
        "readiness_deadline": spec.readiness_deadline,
        "parent_pid": spec.parent_pid,
        "challenge": spec.challenge,
        "mode": spec.mode,
        "authorization": dict(spec.authorization),
    }


def check_worker_spec(spec: WorkerSpec, proof: Mapping[str, object], *, mock: bool, parent_pid: int) -> None:
    # Executed before the module loader, listener, or child environment is touched.
    if not proof or proof.get("challenge") != spec.challenge or not spec.challenge or spec.parent_pid != parent_pid:
        raise PermissionError("unowned child reentry denied before imports")
    if mock != (spec.mode == "OFFLINE_MOCK"):
        raise PermissionError("worker mode/resource mismatch")
    _, binding_raw, _ = h.validate_execution_binding(spec.run, spec.root)
    if h.sha256(binding_raw) != spec.binding_sha:
        raise ValueError("worker source/binding drift")
    if (
        spec.run.resolve() not in spec.state.resolve().parents
        or spec.run.resolve() not in spec.journal.resolve().parents
    ):
        raise ValueError("worker state/journal outside owned run")
    if spec.authorization.get("status") != "VERIFIED_RUNTIME_AUTHORIZATION":
        raise PermissionError("worker lacks verified supervisor authority")
    if not mock:
        verified = h.verify_runtime_authorization(
            spec.run, spec.root, spec.authorization.get("descriptor"), mode="LIVE"
        )
        if verified is None:
            raise PermissionError("child independent authority check failed")


def worker_bootstrap(
    spec: WorkerSpec,
    proof: Mapping[str, object],
    resources: Resources,
    *,
    parent_pid: int,
    observer: Callable[[Any, Any], None],
    child_environment: Callable[[Mapping[str, str]], None],
) -> dict[str, Any]:
    """Same concrete bootstrap for the real child and offline injected module loader."""
    check_worker_spec(spec, proof, mock=resources.mock, parent_pid=parent_pid)
    remaining(resources.clock, spec.readiness_deadline)
    env = h.isolate_worker_environment(spec.state, spec.root)
    config_copy = spec.state / "config/owned-config.yaml"
    if not config_copy.exists():
        h.write_once(config_copy, (spec.root / "config.yaml").read_bytes())
    env["AGK_CONFIG_FILE"] = str(config_copy)
    env["AGK_SEC_DEV_NO_PIN_ALLOW"] = "false"
    child_environment(env)
    loader = resources.modules
    config = loader("antigravity_k.config").config
    config.security.pin_hash_file = str(spec.state / "auth/pin-hash.json")
    config.security.token_secret_file = str(spec.state / "auth/token-secret")
    config.security.access_pin = secrets.token_urlsafe(24)
    config.server.host = "127.0.0.1"
    for name in ("auth",):
        (spec.state / name).chmod(0o700)
    auth = loader("antigravity_k.api.auth_routes")
    auth.init_auth_state()
    policy = loader("antigravity_k.api.auth_policy")
    policy.init_shared_auth_policy(config.security.pin_hash_file)
    token = auth.get_token_service().issue_token(subject=h.FUTURE_TASK_ID)
    egress = loader("antigravity_k.tools.egress_policy")
    providers = loader("antigravity_k.engine.provider_adapters.inference_providers")
    observer(egress, providers)
    dependencies = loader("antigravity_k.api.dependencies")
    # Ordinary getter builds the real registry/usage tracker/model manager. No fake manager is installed.
    manager = dependencies.get_model_manager()
    profile = manager._registry.get_model(h.MODEL_REPO)
    if profile is None or profile.provider != "ollama" or profile.repo != h.MODEL_REPO:
        raise ValueError("ordinary manager profile mismatch")
    base, api_key = providers.OllamaProvider()._resolve_endpoint(type("ProfileContext", (), {"profile": profile})())
    origin = str(base).removesuffix("/v1").rstrip("/")
    if provider_url_key(origin) != provider_url_key(h.PROVIDER_ORIGIN_EXPECTATION) or api_key not in {"", "ollama"}:
        raise ValueError("provider profile differs from frozen unauthenticated loopback origin")
    project_module = loader("antigravity_k.engine.project_registry")
    request_binding, _ = h.read_request_binding(spec.run)
    project_module._global_registry = project_module.ProjectRegistry(
        storage_path=spec.run / str(request_binding["project_registry_path"])
    )
    app = loader("antigravity_k.api.server").app
    for path in (Path(config.security.pin_hash_file), Path(config.security.token_secret_file)):
        if not path.is_file() or spec.state.resolve() not in path.resolve().parents:
            raise ValueError("auth initialization did not produce owned security state")
        path.chmod(0o600)
    return {
        "app": app,
        "token": token,
        "origin": origin,
        "source": "OFFLINE_MOCK" if resources.mock else "RUNTIME_OBSERVATION",
    }


class RecordingResponse:
    """Delegate without pre-reading. Persist only bytes actually consumed by the provider."""

    def __init__(
        self,
        response: HttpResponse,
        *,
        resources: Resources,
        deadline: float,
        path: Path,
        finish: Callable[[bytes, int, Mapping[str, str]], None],
    ):
        self.response = response
        self.resources = resources
        self.deadline = deadline
        self.status = response.status
        self.code = self.status
        self.headers = response.headers
        self.path = path
        self.finish_callback = finish
        self.raw = bytearray()
        self.finished = False
        self.stream = path.open("xb")
        h.write_once(
            path.with_suffix(".headers.json"),
            h.canonical_json({"status": self.status, "safe_headers": safe_headers(self.headers)}),
        )

    def _consume(self, method: str, amount: int) -> bytes:
        self.response.set_timeout(remaining(self.resources.clock, self.deadline))
        data = cast(bytes, getattr(self.response, method)(amount))
        if data:
            self.raw.extend(data)
            self.stream.write(data)
            self.stream.flush()
            os.fsync(self.stream.fileno())
        if not data or (method == "read" and amount < 0):
            self._finish()
        remaining(self.resources.clock, self.deadline)
        return data

    def read(self, amount: int = -1) -> bytes:
        return self._consume("read", amount)

    def readline(self, amount: int = -1) -> bytes:
        return self._consume("readline", amount)

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        if not self.stream.closed:
            self.stream.flush()
            os.fsync(self.stream.fileno())
            self.stream.close()
        self.finish_callback(bytes(self.raw), self.status, self.headers)

    def close(self) -> None:
        try:
            self._finish()
        finally:
            self.response.close()

    def __enter__(self) -> RecordingResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.close()
        return False

    def __iter__(self) -> RecordingResponse:
        return self

    def __next__(self) -> bytes:
        value = self.readline()
        if not value:
            raise StopIteration
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.response, name)


class WorkerObserver:
    def __init__(self, spec: WorkerSpec, resources: Resources):
        self.spec = spec
        self.resources = resources
        self.journal = h.OneShotJournal(spec.journal)
        self.product_id: str | None = None
        self.request_sha: str | None = None
        self.phase = "bootstrap"
        self.guard: Any | None = None
        self.captures = spec.state / "captures"
        self.captures.mkdir(parents=True, exist_ok=True)
        self.references: list[object] = []

    def arm(self, product_id: str, request_sha: str) -> None:
        context = h.request_gate(self.spec.run, self.spec.root)
        if context["request_sha256"] != request_sha:
            raise ValueError("IPC request SHA drift")
        events = self.journal.replay()
        if not any(
            e.get("event") == "logical_reserved"
            and e.get("logical_id") == product_id
            and e.get("request_sha256") == request_sha
            for e in events
        ):
            raise PermissionError("worker product gate lacks matching parent wire authorization")
        self.product_id, self.request_sha, self.phase = product_id, request_sha, "product"
        self.guard = h.ProviderWireGuard(
            self.spec.run, self.spec.root, self.journal, product_id, self.spec.deadline, self.resources.clock.monotonic
        )

    def install(self, egress: Any, providers: Any) -> None:
        # Guard urllib's terminal sink. Existing safe_urlopen retry re-enters this guard
        # and is denied before another sink. Redirects/proxies are disabled in the opener.
        urllib.request.urlopen = self.urlopen
        providers.safe_urlopen = egress.safe_urlopen

    def urlopen(self, target: Any, *args: Any, **kwargs: Any) -> Any:
        request = target if isinstance(target, urllib.request.Request) else urllib.request.Request(str(target))
        url, method = request.full_url, request.get_method()
        body = request.data or b""
        if not isinstance(body, bytes):
            raise ValueError("provider body must be immutable bytes before wire")
        parsed = urlsplit(url)
        if provider_url_key(url) != provider_url_key(h.PROVIDER_ORIGIN_EXPECTATION):
            raise ValueError("unknown provider origin before sink")
        if args:
            raise ValueError("positional urllib sink arguments forbidden")
        requested_timeout = kwargs.get("timeout")
        timeout = remaining(
            self.resources.clock,
            self.spec.deadline,
            float(requested_timeout) if requested_timeout is not None else None,
        )
        if any(target is old for old in self.references):
            self.journal.reserve("retry_wire", "retry:" + secrets.token_hex(8), body)
            raise RuntimeError("safe_urlopen retry denied before second terminal sink")
        self.references.append(target)
        slot: str
        logical_id: str
        if self.phase == "product" and parsed.path == "/api/chat":
            if self.guard is None:
                raise PermissionError("provider guard not armed")
            slot, logical_id = self.guard.enter(body, url=url)
        elif self.phase == "product" and parsed.path == "/api/show" and method == "POST":
            payload = h.strict_json_loads(body)
            if payload != {"model": h.MODEL_REPO} and payload != {"model": h.MODEL_ALIAS}:
                raise ValueError("internal capability model drift")
            h.request_gate(self.spec.run, self.spec.root)
            slot, logical_id = "product_internal_capability_show", "capability:" + secrets.token_hex(8)
            if not self.journal.reserve(slot, logical_id, body) or not self.journal.enter_wire(slot, logical_id, body):
                raise RuntimeError("capability budget exhausted")
        else:
            raise ValueError("unknown provider path or unarmed worker before sink")
        stem = logical_id.replace(":", "-")
        h.write_once(self.captures / (stem + "-request.bin"), body)
        h.write_once(
            self.captures / (stem + "-request.json"),
            h.canonical_json(
                {
                    "url": url,
                    "canonical_origin": h.canonical_provider_origin(url),
                    "origin_policy": h.PROVIDER_ORIGIN_POLICY,
                    "method": method,
                    "slot": slot,
                    "logical_id": logical_id,
                    "request_sha256": h.sha256(body),
                    "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
                    "transmission_state": "MAY_HAVE_TRANSMITTED",
                }
            ),
        )

        def finish(raw: bytes, status: int, headers: Mapping[str, str]) -> None:
            self.journal.record_response(slot, logical_id, body, raw, status)

        try:
            response = self.resources.http.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            recorded_error_body = RecordingResponse(
                cast(HttpResponse, cast(object, exc)),
                resources=self.resources,
                deadline=self.spec.deadline,
                path=self.captures / (stem + "-response.bin"),
                finish=finish,
            )
            raise DelegatedHTTPError(exc, recorded_error_body, exc.fp) from exc
        return RecordingResponse(
            response,
            resources=self.resources,
            deadline=self.spec.deadline,
            path=self.captures / (stem + "-response.bin"),
            finish=finish,
        )


class ConcreteRuntimeAdapter:
    terminal_wire_owner = True

    def __init__(self, run: Path, root: Path, journal: JournalPort, resources: Resources):
        # Constructor and import have no resource side effects.
        self.run, self.root, self.journal, self.resources = run, root, journal, resources
        self.state = run / "runtime-state"
        self.proc: ProcessHandle | None = None
        self.listener_handle: Listener | None = None
        self.ipc_handle: PrivateIPC | None = None
        self.token = ""
        self.origin = h.PROVIDER_ORIGIN_EXPECTATION
        self.events: list[dict[str, object]] = []
        self.cleanup_calls = 0

    def event(self, name: str, **values: object) -> None:
        record = {"event": name, "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION", **values}
        self.events.append(record)
        h.append_jsonl_fsync(self.run / "runtime-observations.jsonl", record)

    def bootstrap(self, context: Mapping[str, object]) -> Mapping[str, object]:
        h.request_gate(self.run, self.root)
        if self.journal.counts()["logical_reserved"].get("product_authenticated_chat_post", 0):
            raise RuntimeError("retained task-wide product reservation prevents new resources")
        deadline = float(cast(float, context["deadline_monotonic"]))
        ready_deadline = float(cast(float, context["readiness_deadline_monotonic"]))
        remaining(self.resources.clock, ready_deadline)
        env = h.isolate_worker_environment(self.state, self.root)
        env["AGK_SEC_DEV_NO_PIN_ALLOW"] = "false"
        spec = WorkerSpec(
            self.run,
            self.root,
            self.state,
            str(context["execution_binding_sha256"]),
            self.journal.path,
            deadline,
            ready_deadline,
            os.getpid(),
            secrets.token_hex(32),
            "OFFLINE_MOCK" if self.resources.mock else "LIVE",
            cast(Mapping[str, object], context["authorization"]),
        )
        self.listener_handle = self.resources.listener()
        self.ipc_handle = self.resources.ipc()
        self.proc = self.resources.process(spec, self.listener_handle, self.ipc_handle, env)
        self.ipc_handle.send(
            {"event": "BOOT", "spec": serialize_spec(spec), "challenge": spec.challenge},
            timeout=remaining(self.resources.clock, ready_deadline),
        )
        started = self.ipc_handle.receive(timeout=remaining(self.resources.clock, ready_deadline))
        if (
            started.get("event") != "WORKER_STARTED"
            or started.get("pid") != self.proc.pid
            or started.get("binding_sha") != spec.binding_sha
            or started.get("ready") is not True
        ):
            raise ValueError("worker-start receipt is not owned or ready")
        token = started.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("private bearer receipt missing")
        self.token = token
        self.origin = str(started.get("origin"))
        if provider_url_key(self.origin) != provider_url_key(h.PROVIDER_ORIGIN_EXPECTATION):
            raise ValueError("worker provider origin differs from frozen contract")
        self.event(
            "worker-start",
            pid=self.proc.pid,
            port=self.listener_handle.port,
            binding_sha=spec.binding_sha,
            ready_signal=True,
            http_ready=False,
        )
        return {
            "worker_owned": True,
            "auth_state_owned": True,
            "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
        }

    def _exchange(
        self, request: urllib.request.Request, deadline: float, stem: str
    ) -> tuple[int, Mapping[str, str], bytes]:
        captures = self.state / "parent-captures"
        captures.mkdir(parents=True, exist_ok=True)
        response: HttpResponse | None = None
        error: urllib.error.HTTPError | None = None
        raw = bytearray()
        path = captures / (stem + "-response.bin")
        try:
            with exchange_deadline(self.resources, deadline):
                duration = remaining(self.resources.clock, deadline)
                self.event("http-open", method=request.get_method(), url=request.full_url, timeout=duration)
                try:
                    response = self.resources.http.open(request, timeout=duration)
                except urllib.error.HTTPError as exc:
                    error = exc
                    response = cast(HttpResponse, cast(object, exc))
                with path.open("xb") as stream:
                    h.write_once(
                        captures / (stem + "-headers.json"),
                        h.canonical_json({"status": response.status, "safe_headers": safe_headers(response.headers)}),
                    )
                    while True:
                        duration = remaining(self.resources.clock, deadline)
                        response.set_timeout(duration)
                        self.event("http-read", stem=stem, timeout=duration)
                        chunk = response.read(4096)
                        if chunk:
                            raw.extend(chunk)
                            stream.write(chunk)
                            stream.flush()
                            os.fsync(stream.fileno())
                        remaining(self.resources.clock, deadline)
                        if not chunk:
                            break
                status = error.code if error is not None else response.status
                return status, safe_headers(response.headers), bytes(raw)
        finally:
            if response is not None:
                response.close()

    def readiness(self, context: Mapping[str, object]) -> Mapping[str, object]:
        if self.listener_handle is None:
            raise RuntimeError("listener unavailable")
        deadline = min(
            float(cast(float, context["deadline_monotonic"])),
            float(cast(float, context["readiness_deadline_monotonic"])),
        )
        url = f"http://127.0.0.1:{self.listener_handle.port}/api/system/cache-stats"
        a, _, _ = self._exchange(urllib.request.Request(url), deadline, "anonymous-ready")
        b, _, body = self._exchange(
            urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token}), deadline, "bearer-ready"
        )
        value = h.strict_json_loads(body)
        ready = (
            b == 200 and isinstance(value, dict) and value.get("ok") is True and isinstance(value.get("stats"), dict)
        )
        self.event("readiness", anonymous_status=a, bearer_status=b, ready=ready, get_calls=2)
        return {
            "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
            "unauthenticated_status": a,
            "bearer_status": b,
            "ready": ready,
        }

    def _metadata(self, slot: str, path: str, deadline: float, *, body: bytes | None = None) -> Any:
        method = "POST" if body is not None else "GET"
        binding = h.canonical_json({"url": self.origin + path, "method": method, "body_sha256": h.sha256(body or b"")})
        logical = "metadata:" + slot
        remaining(self.resources.clock, deadline)
        h.request_gate(self.run, self.root)
        if not self.journal.reserve(slot, logical, binding) or not self.journal.enter_wire(slot, logical, binding):
            raise RuntimeError("metadata budget exhausted")
        status, headers, raw = self._exchange(
            urllib.request.Request(
                self.origin + path, data=body, method=method, headers={"Content-Type": "application/json"}
            ),
            deadline,
            slot,
        )
        self.journal.record_response(slot, logical, binding, raw, status)
        self.event(
            "metadata", slot=slot, status=status, request_sha256=h.sha256(binding), response_sha256=h.sha256(raw)
        )
        if status != 200 or headers.get("content-type", "").split(";", 1)[0] != "application/json":
            raise ValueError("metadata HTTP status/content-type invalid")
        return h.strict_json_loads(raw)

    def metadata(self, context: Mapping[str, object]) -> Mapping[str, object]:
        deadline = float(cast(float, context["deadline_monotonic"]))
        version = self._metadata("ollama_get_version_preflight", "/api/version", deadline)
        tags = self._metadata("ollama_get_tags_preflight", "/api/tags", deadline)
        ps = self._metadata("ollama_get_ps_preflight", "/api/ps", deadline)
        show = self._metadata(
            "ollama_post_show_preflight", "/api/show", deadline, body=h.canonical_json({"model": h.MODEL_REPO})
        )
        models = tags.get("models") if isinstance(tags, dict) else None
        matches = (
            [m for m in models if isinstance(m, dict) and m.get("name") == h.MODEL_REPO]
            if isinstance(models, list)
            else []
        )
        caps = show.get("capabilities") if isinstance(show, dict) else None
        digest = matches[0].get("digest") if len(matches) == 1 else None
        if (
            not isinstance(version, dict)
            or not isinstance(version.get("version"), str)
            or digest != h.APPROVED_MODEL_DIGEST
            or not isinstance(caps, list)
            or "vision" not in caps
            or not isinstance(ps, dict)
            or not isinstance(ps.get("models"), list)
        ):
            raise ValueError("provider repo/digest/vision/version/loaded-state metadata mismatch")
        return {
            "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
            "complete": True,
            "version": version,
            "tags": tags,
            "show": show,
            "capabilities": caps,
            "model_repo": h.MODEL_REPO,
            "model_digest": digest,
            "ollama_origin": self.origin,
            "model_loaded": any(m.get("name") == h.MODEL_REPO for m in ps["models"] if isinstance(m, dict)),
        }

    def reconcile(self, context: Mapping[str, object]) -> dict[str, object]:
        state = cast(StatePort, context["supervisor_state"])
        product_id = str(context["product_logical_id"])
        provider_id = "provider:" + product_id.split(":", 1)[1]
        events = [e for e in self.journal.replay() if e.get("logical_id") == provider_id]
        wires = [e for e in events if e.get("event") == "wire_entered"]
        state.provider_wires = len(wires)
        stem = provider_id.replace(":", "-")
        request_path = self.state / "captures" / (stem + "-request.bin")
        response_path = self.state / "captures" / (stem + "-response.bin")
        if request_path.exists():
            state.provider_request_bytes = request_path.read_bytes()
        if response_path.exists():
            state.provider_response_bytes = response_path.read_bytes()
        observed = next((e for e in events if e.get("event") == "response_observed"), {})
        if wires and h.sha256(state.provider_request_bytes) != wires[0].get("request_sha256"):
            raise ValueError("worker wire request capture/journal mismatch")
        if observed and h.sha256(state.provider_response_bytes) != observed.get("response_sha256"):
            raise ValueError("worker response capture/journal mismatch")
        headers_path = response_path.with_suffix(".headers.json")
        headers = h.strict_json_loads(headers_path.read_bytes()) if headers_path.exists() else {}
        safe = headers.get("safe_headers", {}) if isinstance(headers, dict) else {}
        self.event(
            "parent-reconcile",
            provider_logical_id=provider_id,
            provider_wire_attempts=len(wires),
            response_observed=bool(observed),
            new_reservations=0,
            new_sends=0,
        )
        return {
            "provider_logical_id": provider_id,
            "upstream_status": observed.get("status"),
            "upstream_content_type": safe.get("content-type", ""),
        }

    def dispatch_product(
        self, context: Mapping[str, object], provider_wire: Callable[..., Mapping[str, object]]
    ) -> Mapping[str, object]:
        _ = provider_wire  # The child uses the extracted identical guard; parent never sends provider inference.
        if self.listener_handle is None or self.ipc_handle is None:
            raise RuntimeError("owned worker resources missing")
        deadline = float(cast(float, context["deadline_monotonic"]))
        raw = cast(bytes, context["product_request_bytes"])
        product_id = str(context["product_logical_id"])
        current = h.request_gate(self.run, self.root)
        if (
            current["request_sha256"] != h.sha256(raw)
            or current["execution_binding_sha256"] != context["execution_binding_sha256"]
        ):
            raise ValueError("product drift immediately before terminal transport")
        remaining(self.resources.clock, deadline)
        state = cast(StatePort, context["supervisor_state"])
        self.ipc_handle.send(
            {"event": "ARM_PRODUCT", "product_id": product_id, "request_sha": h.sha256(raw)},
            timeout=remaining(self.resources.clock, deadline),
        )
        armed = self.ipc_handle.receive(timeout=remaining(self.resources.clock, deadline))
        if armed.get("event") != "PRODUCT_ARMED" or armed.get("product_id") != product_id:
            raise PermissionError("worker observer did not arm matching logical ID")
        current = h.request_gate(self.run, self.root)
        remaining(self.resources.clock, deadline)
        if current["execution_binding_sha256"] != context["execution_binding_sha256"] or current[
            "request_sha256"
        ] != h.sha256(raw):
            raise ValueError("source/request drift after IPC immediately before terminal wire")
        if not self.journal.enter_wire("product_authenticated_chat_post", product_id, raw):
            raise RuntimeError("product terminal wire denied")
        state.dispatches += 1
        url = f"http://127.0.0.1:{self.listener_handle.port}/v1/chat/completions"
        try:
            status, headers, body = self._exchange(
                urllib.request.Request(
                    url,
                    data=raw,
                    method="POST",
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token},
                ),
                deadline,
                "product",
            )
            state.product_response_bytes = body
        finally:
            partial = self.state / "parent-captures/product-response.bin"
            if partial.exists():
                state.product_response_bytes = partial.read_bytes()
            lineage = self.reconcile(context)
        self.event("product-response", logical_id=product_id, status=status, response_sha256=h.sha256(body))
        return {
            "raw_body": body,
            "status": status,
            "content_type": headers.get("content-type", ""),
            "product_logical_id": product_id,
            **lineage,
            "source_sha256_before_wire": cast(Mapping[str, object], current["source"])["actual"],
            "request_sha256_before_wire": h.sha256(raw),
            "provider_contract_pass": state.provider_wires == 1,
        }

    def postflight(self, context: Mapping[str, object]) -> Mapping[str, object]:
        value = self._metadata("ollama_get_ps_postflight", "/api/ps", float(cast(float, context["deadline_monotonic"])))
        return {
            "status": "OBSERVED",
            "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
            "ps": value,
        }

    def cleanup(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self.cleanup_calls += 1
        deadline = min(
            float(cast(float, context["cleanup_deadline_monotonic"])),
            self.resources.clock.monotonic() + float(cast(float, context["cleanup_timeout_seconds"])),
        )
        exit_code: int | None = None
        errors: list[str] = []
        shutdown_report: object = "NOT_OBSERVED"
        proc = self.proc
        if proc is not None:
            try:
                if self.ipc_handle is not None:
                    self.ipc_handle.send({"event": "SHUTDOWN"}, timeout=remaining(self.resources.clock, deadline, 0.5))
                    shutdown_report = self.ipc_handle.receive(
                        timeout=remaining(self.resources.clock, deadline, 0.5)
                    ).get("event", "NOT_OBSERVED")
            except (OSError, EOFError, ValueError, TimeoutError) as exc:
                errors.append("shutdown:" + type(exc).__name__)
            for operation, cap in (("wait", 1.0), ("terminate", None), ("wait", 1.0), ("kill", None), ("wait", None)):
                if exit_code is not None:
                    break
                try:
                    duration = remaining(self.resources.clock, deadline, cap)
                    self.event("process-" + operation, pid=proc.pid, timeout=duration)
                    if operation == "wait":
                        exit_code = proc.wait(timeout=duration)
                    elif operation == "terminate":
                        proc.terminate()
                    else:
                        proc.kill()
                except (subprocess.TimeoutExpired, TimeoutError):
                    continue
                except (OSError, RuntimeError) as exc:
                    errors.append(operation + ":" + type(exc).__name__)
                    break
        released = True
        for resource in (self.ipc_handle, self.listener_handle):
            if resource is not None:
                try:
                    resource.close()
                except (OSError, RuntimeError) as exc:
                    released = False
                    errors.append("release:" + type(exc).__name__)
        self.token = ""
        observed = type(exit_code) is int
        result: dict[str, object] = {
            "source": "OFFLINE_MOCK" if self.resources.mock else "RUNTIME_OBSERVATION",
            "owned_cleanup": observed and released and not errors,
            "worker_started": proc is not None,
            "exit_observation": "OBSERVED" if observed else "NOT_OBSERVED",
            "exit_code": exit_code,
            "reaped": observed,
            "released_handles": released,
            "worker_shutdown_report": shutdown_report,
            "os_exit_observation": "NOT_OBSERVED"
            if self.resources.mock
            else "OBSERVED"
            if observed
            else "NOT_OBSERVED",
            "supervisor_exit_observation": "NOT_OBSERVED",
            "errors": errors,
        }
        self.event("cleanup", receipt=result)
        return result


def concrete_adapter_factory(
    run: Path, root: Path, journal: JournalPort, resources: Resources | None = None
) -> ConcreteRuntimeAdapter:
    return ConcreteRuntimeAdapter(run, root, journal, resources or concrete_resources())


def worker_entrypoint(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    required = ("RB_CONTROL_FD", "RB_RECEIPT_FD", "RB_LISTENER_FD")
    if args != ["--worker"] or any(name not in os.environ for name in required):
        return 3
    if os.getppid() <= 1:
        return 3
    ipc = PipeIPC.__new__(PipeIPC)
    ipc.parent_read = int(os.environ.pop("RB_CONTROL_FD"))
    ipc.parent_write = int(os.environ.pop("RB_RECEIPT_FD"))
    ipc.pending = bytearray()
    listener_fd = int(os.environ.pop("RB_LISTENER_FD"))
    boot = ipc.receive(timeout=1.0)
    data = boot.get("spec")
    if boot.get("event") != "BOOT" or not isinstance(data, dict):
        return 3
    spec = WorkerSpec(
        Path(data["run"]),
        Path(data["root"]),
        Path(data["state"]),
        data["binding_sha"],
        Path(data["journal"]),
        float(data["deadline"]),
        float(data["readiness_deadline"]),
        int(data["parent_pid"]),
        data["challenge"],
        data["mode"],
        data["authorization"],
    )
    resources = concrete_resources()
    check_worker_spec(spec, boot, mock=False, parent_pid=os.getppid())
    observer = WorkerObserver(spec, resources)

    def child_env(env: Mapping[str, str]) -> None:
        os.environ.clear()
        os.environ.update(env)
        os.chdir(spec.state)

    runtime = worker_bootstrap(
        spec, boot, resources, parent_pid=os.getppid(), observer=observer.install, child_environment=child_env
    )
    uvicorn = resources.modules("uvicorn")
    listener = socket.socket(fileno=listener_fd)
    server = uvicorn.Server(
        uvicorn.Config(
            runtime["app"],
            host="127.0.0.1",
            port=listener.getsockname()[1],
            workers=1,
            reload=False,
            lifespan="off",
            access_log=False,
            log_level="critical",
            timeout_graceful_shutdown=1,
        )
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=False)
    thread.start()
    while not server.started:
        remaining(resources.clock, spec.readiness_deadline)
        if not thread.is_alive():
            raise RuntimeError("worker exited before ready signal")
        thread.join(timeout=min(0.01, remaining(resources.clock, spec.readiness_deadline)))
    ipc.send(
        {
            "event": "WORKER_STARTED",
            "pid": os.getpid(),
            "ready": True,
            "binding_sha": spec.binding_sha,
            "token": runtime["token"],
            "origin": runtime["origin"],
        },
        timeout=remaining(resources.clock, spec.readiness_deadline),
    )
    runtime["token"] = ""
    try:
        while True:
            message = ipc.receive(timeout=remaining(resources.clock, spec.deadline))
            if message.get("event") == "ARM_PRODUCT":
                observer.arm(message["product_id"], message["request_sha"])
                ipc.send(
                    {"event": "PRODUCT_ARMED", "product_id": message["product_id"]},
                    timeout=remaining(resources.clock, spec.deadline),
                )
            elif message.get("event") == "SHUTDOWN":
                break
            else:
                raise PermissionError("unknown private worker command")
    finally:
        server.should_exit = True
        cleanup_deadline = min(
            spec.deadline + h.GRACEFUL_CLEANUP_SECONDS, time.monotonic() + h.GRACEFUL_CLEANUP_SECONDS
        )
        thread.join(timeout=remaining(resources.clock, cleanup_deadline))
        listener.close()
        if not thread.is_alive():
            ipc.send({"event": "WORKER_DONE"}, timeout=remaining(resources.clock, cleanup_deadline))
    return 0 if not thread.is_alive() else 4


if __name__ == "__main__":
    raise SystemExit(worker_entrypoint())
