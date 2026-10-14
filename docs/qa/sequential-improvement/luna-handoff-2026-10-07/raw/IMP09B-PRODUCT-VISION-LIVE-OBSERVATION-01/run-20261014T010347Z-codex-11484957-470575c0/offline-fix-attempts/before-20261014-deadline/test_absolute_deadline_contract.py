from __future__ import annotations

import importlib
import io
import signal
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING, Never

import pytest
if TYPE_CHECKING:
    from .runtime_adapter import ConcreteRuntimeAdapter, HttpResponse, Listener, PrivateIPC, WorkerSpec

h = importlib.import_module("run_harness")
r = importlib.import_module("runtime_adapter")


class Response:
    """Accumulate fake read and close observations without opening a socket."""

    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.reads = 0
        self.closed = False
        self.timer_at_close = -1.0

    def set_timeout(self, timeout: float) -> None:
        assert timeout > 0

    def read(self, amount: int = -1) -> bytes:
        self.reads += 1
        if self.reads == 1:
            return b"prefix"
        time.sleep(self.delay)
        return b""

    def readline(self, amount: int = -1) -> bytes:
        return self.read(amount)

    def close(self) -> None:
        self.closed = True
        self.timer_at_close = signal.getitimer(signal.ITIMER_REAL)[0]


class Opener:
    """Record in-memory sink entry and emulate blocking headers or an error body."""

    def __init__(self, response: Response, delay: float = 0.0, error: bool = False) -> None:
        self.response = response
        self.delay = delay
        self.error = error
        self.calls = 0

    def open(self, request: urllib.request.Request, *, timeout: float) -> HttpResponse:
        self.calls += 1
        time.sleep(self.delay)
        if self.error:
            headers = Message()
            headers["Content-Type"] = "application/json"
            original = urllib.error.HTTPError(request.full_url, 400, "fake", headers, io.BytesIO())
            raise r.DelegatedHTTPError(original, self.response, self.response)
        return self.response


def forbidden_listener() -> Never:
    raise AssertionError("listener is outside this offline test")


def forbidden_ipc() -> Never:
    raise AssertionError("IPC is outside this offline test")


def forbidden_process(
    spec: WorkerSpec, listener: Listener, ipc: PrivateIPC, environment: Mapping[str, str]
) -> Never:
    raise AssertionError("process is outside this offline test")


def adapter(tmp_path: Path, opener: Opener, *, mock: bool = False) -> ConcreteRuntimeAdapter:
    resources = r.Resources(time, opener, importlib.import_module, forbidden_listener, forbidden_ipc, forbidden_process, mock)
    return r.ConcreteRuntimeAdapter(tmp_path, tmp_path, h.OneShotJournal(tmp_path / "journal.jsonl"), resources)


@pytest.mark.parametrize("block_headers", [True, False])
def test_exchange_interrupts_absolute_deadline(tmp_path: Path, block_headers: bool) -> None:
    response = Response(delay=0.35 if not block_headers else 0)
    opener = Opener(response, delay=0.35 if block_headers else 0)
    runtime = adapter(tmp_path, opener)
    handler = signal.getsignal(signal.SIGALRM)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        runtime._exchange(urllib.request.Request("http://127.0.0.1/unused"), start + 0.04, "bounded")
    assert time.monotonic() - start < 0.25
    assert opener.calls == 1
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == handler
    if not block_headers:
        assert response.closed
        assert response.timer_at_close == 0.0
        assert (runtime.state / "parent-captures/bounded-response.bin").read_bytes() == b"prefix"


@pytest.mark.parametrize("mock", [True, False])
@pytest.mark.parametrize("error", [True, False])
def test_completed_response_restores_timer_and_error_status(tmp_path: Path, mock: bool, error: bool) -> None:
    response = Response()
    runtime = adapter(tmp_path, Opener(response, error=error), mock=mock)
    handler = signal.getsignal(signal.SIGALRM)
    status, _, body = runtime._exchange(urllib.request.Request("http://127.0.0.1/unused"), time.monotonic() + 1, "done")
    assert (status, body) == (400 if error else 200, b"prefix")
    assert response.closed and response.timer_at_close == 0.0
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_existing_timer_is_preserved_before_sink(tmp_path: Path) -> None:
    opener = Opener(Response())
    runtime = adapter(tmp_path, opener)
    signal.setitimer(signal.ITIMER_REAL, 5.0)
    try:
        with pytest.raises(RuntimeError):
            runtime._exchange(urllib.request.Request("http://127.0.0.1/unused"), time.monotonic() + 1, "conflict")
        assert opener.calls == 0
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 4.0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def test_wrong_thread_refuses_before_sink(tmp_path: Path) -> None:
    opener = Opener(Response())
    runtime = adapter(tmp_path, opener)
    errors: list[RuntimeError] = []

    def exchange() -> None:
        try:
            runtime._exchange(urllib.request.Request("http://127.0.0.1/unused"), time.monotonic() + 1, "thread")
        except RuntimeError as exc:
            errors.append(exc)

    thread = threading.Thread(target=exchange)
    thread.start()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert opener.calls == 0


def test_mock_does_not_install_kernel_timer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_timer(which: int, seconds: float, interval: float = 0.0) -> Never:
        raise AssertionError("mock must not install a kernel timer")

    monkeypatch.setattr(signal, "setitimer", forbidden_timer)
    runtime = adapter(tmp_path, Opener(Response()), mock=True)
    assert runtime._exchange(urllib.request.Request("http://127.0.0.1/unused"), time.monotonic() + 1, "mock")[2] == b"prefix"


class ReadOwner(io.BytesIO):
    """Distinguish bounded prefix reads from compatibility reads."""

    status = 200
    headers: dict[str, str] = {}

    def read1(self, size: int | None = -1) -> bytes:
        return super().read(2 if size is None else min(size, 2))


def test_positive_socket_read_uses_single_buffer_read() -> None:
    owner = ReadOwner(b"abcdef")
    response = r.SocketResponse(owner)
    assert response.read(4096) == b"ab"
    assert response.read() == b"cdef"
