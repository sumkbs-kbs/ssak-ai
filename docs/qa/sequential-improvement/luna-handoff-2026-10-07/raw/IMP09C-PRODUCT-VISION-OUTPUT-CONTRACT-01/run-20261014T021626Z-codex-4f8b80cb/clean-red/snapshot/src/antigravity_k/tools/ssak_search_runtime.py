"""번들 검색 MCP child의 수명주기를 **호스트가 하나만** 소유한다 (task 12).

왜 별도 소유자가 필요한가 — 세 가지가 실측으로 확인된 제약이다.

1. **stdin/stdout 은 한 소유자만** 읽고 써야 한다. JSON-RPC 는 줄 단위 상호 배타 프로토콜이라
   두 곳에서 같은 child 의 stdout 을 읽으면 응답이 서로에게 섞여 사라진다.
2. anyio 스트림과 cancel scope 는 **만든 task 에 묶인다**(task 9 실측: 다른 task 에서 teardown 하면
   SDK 가 `RuntimeError('Attempted to exit cancel scope in a different task …')` 를 낸다).
3. child 를 죽이는 것은 **우리가 만든 그 프로세스**여야 한다. 이름·pgid 로 죽이면 사용자 프로세스를
   죽일 수 있다.

그래서 이 모듈은 전용 스레드 + 전용 이벤트 루프를 만들고, **그 루프의 단일 task** 안에서
stdio context 진입 · 호출 · teardown 을 전부 수행한다. supervisor 는 두 번째 `Popen` 을 만들지
않는다(child 는 MCP SDK 의 stdio context 가 소유하고, 우리는 그 context 의 수명만 관리한다).

상태기계(계획의 Acceptance):

    disabled → stopped → starting → ready → degraded → starting … → failed(회로 열림) → stopping → stopped

- `starting`: 연결 시도 중(episode 안에서 backoff 후 재시도)
- `ready`: 세션이 살아 있고 호출을 받는다
- `degraded`: 준비됐던 세션이 **죽었다**(exit 관찰). 재시작은 허용되지만 툴 호출은 재시도하지 않는다
- `failed`: 한 episode 의 시도(기본 3회)를 모두 소진 → **회로 열림**. cooldown 동안 즉시 거절하고,
  cooldown 이 지나면 trial 1회를 허용한다
- `disabled`: 설정이 꺼져 있어 child 를 만들지 않는다(호출은 typed 오류)

재시도 규칙: **비멱등 작업은 자동 재시도하지 않는다**. 이 런타임은 툴 호출을 스스로 재시도하지
않고, 호출자가 `retry_on_transport=True` 로 요청해도 `idempotent=False` 면
`NON_IDEMPOTENT_NOT_RETRIED` 로 거절한다(전송이 끊긴 뒤 재요청은 상대가 이미 적용했을 수 있다).
시작(connection)은 멱등이므로 backoff 재시도 대상이다.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import logging
import os
import stat
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Final, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .mcp_tool_result import MCPToolOutcome, build_outcome, error_outcome

logger = logging.getLogger(__name__)

TRANSPORT: Final[str] = "stdio"

# child 에게 넘길 환경 변수의 **허용 목록**이다(전체 env 를 넘기지 않는다 — 호스트 환경에는
# API 키·토큰·세션 비밀이 들어 있고, 검색 child 는 그것들을 알 필요가 없다).
DEFAULT_ENV_ALLOWLIST: Final[tuple[str, ...]] = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR")

# 시작 실패 시 재시도 **사이**의 대기(초). 마지막 값은 회로가 열린 뒤의 cooldown 으로도 쓰인다.
DEFAULT_BACKOFF_SECONDS: Final[tuple[float, ...]] = (1.0, 2.0, 4.0)
DEFAULT_MAX_START_ATTEMPTS: Final[int] = 3


class SearchRuntimeState(str, Enum):
    """검색 child 런타임의 상태."""

    DISABLED = "disabled"
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"

    @property
    def serves_tools(self) -> bool:
        """이 상태에서 툴 호출을 받을 수 있는가."""
        return self is SearchRuntimeState.READY

    @property
    def terminal(self) -> bool:
        """이 상태에서는 더 이상 child 를 만들지 않는가."""
        return self in (SearchRuntimeState.DISABLED, SearchRuntimeState.STOPPED, SearchRuntimeState.FAILED)


@dataclass(frozen=True)
class ArtifactVerdict:
    """번들 artifact 검증 결과(실패하면 child 를 만들지 않는다 — fail-closed)."""

    ok: bool
    detail: str
    sha256: str | None = None
    platform: str | None = None
    arch: str | None = None


def _describe(exc: object) -> str:
    """예외를 사람이 읽는 한 줄로. `Connection closed` 처럼 str 이 빈 경우가 실재한다."""
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundled_artifact(
    artifact_path: str | os.PathLike[str] | None,
    manifest_path: str | os.PathLike[str] | None = None,
    *,
    require_manifest: bool = True,
) -> ArtifactVerdict:
    """번들 artifact 가 매니페스트가 기술한 그 bytes 인지 확인한다.

    이 검사가 말하는 것은 "이 파일이 매니페스트가 기술한 그 파일이다"까지다 — hash 는 무결성이고
    publisher 의 증명이 아니다(그 경로는 배포 서명 = task 15). 매니페스트가 없는데
    `require_manifest=True` 면 **시작하지 않는다**(fail-closed): 어느 bytes 를 실행하는지 모르는 채
    실행하는 것이 이 task 가 없애려는 실패 모드다.
    """
    if artifact_path is None:
        return ArtifactVerdict(False, "no artifact path configured")
    artifact = Path(artifact_path)
    if not artifact.exists():
        return ArtifactVerdict(False, f"artifact not found: {artifact}")
    if not artifact.is_file():
        return ArtifactVerdict(False, f"artifact is not a regular file: {artifact}")
    if not artifact.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        return ArtifactVerdict(False, f"artifact is not executable: {artifact}")

    actual = _sha256_file(artifact)
    # 빈 문자열은 "주지 않음"이다 — `Path("")` 는 `.` 이라 매니페스트로 읽히면 디렉터리를 연다
    # (task 13 이 이 느슨한 비교를 실제로 밟았다).
    if manifest_path is None or not str(manifest_path).strip():
        detail = "no manifest given, so the bytes cannot be pinned"
        if require_manifest:
            return ArtifactVerdict(False, f"{detail} — refusing to run an unpinned artifact", sha256=actual)
        return ArtifactVerdict(True, f"{detail} (explicitly opted out)", sha256=actual)

    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        return ArtifactVerdict(False, f"artifact manifest not found: {manifest_file}")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ArtifactVerdict(False, f"artifact manifest is unreadable: {exc}")
    if not isinstance(manifest, Mapping):
        return ArtifactVerdict(False, "artifact manifest is not an object")
    artifact_section = cast(Mapping[str, object], manifest).get("artifact")
    if not isinstance(artifact_section, Mapping):
        return ArtifactVerdict(False, "artifact manifest has no artifact section")
    section = cast(Mapping[str, object], artifact_section)
    expected = section.get("sha256")
    if not isinstance(expected, str) or not expected:
        return ArtifactVerdict(False, "artifact manifest records no sha256 to compare against")
    if actual != expected:
        return ArtifactVerdict(
            False,
            f"artifact sha256 {actual[:16]}… does not match the manifest {expected[:16]}… — refusing to run different bytes",
            sha256=actual,
        )
    platform = section.get("platform")
    arch = section.get("arch")
    return ArtifactVerdict(
        True,
        f"artifact matches the manifest ({actual[:16]}…)",
        sha256=actual,
        platform=str(platform) if platform else None,
        arch=str(arch) if arch else None,
    )


@dataclass
class SearchRuntimeConfig:
    """런타임 설정. 기본값은 "번들 artifact 하나를 조용히 실행"이다."""

    artifact_path: str | None = None
    manifest_path: str | None = None
    require_manifest: bool = True
    enabled: bool = True
    server_name: str = "ssak_search"
    # 테스트/대체 child 를 위한 명시적 오버라이드. 비어 있으면 artifact 를 직접 실행한다.
    command: str | None = None
    args: tuple[str, ...] = ()
    env_allowlist: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST
    extra_env: Mapping[str, str] = field(default_factory=dict)
    backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS
    max_start_attempts: int = DEFAULT_MAX_START_ATTEMPTS
    call_timeout_seconds: float = 30.0
    ready_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 15.0
    monitor_interval_seconds: float = 0.5
    # 세션이 이 시간 이상 살아 있었으면 "건강했다"고 보고 시도 예산을 되돌린다. 그보다 빨리
    # 죽는 child 는 crash loop 이므로 예산을 소모하고, 예산이 바닥나면 회로를 연다(무한 재spawn 금지).
    health_reset_seconds: float = 60.0

    @property
    def circuit_cooldown_seconds(self) -> float:
        """회로가 열린 뒤 trial 1회를 허용하기까지의 대기(마지막 backoff 값을 쓴다)."""
        return self.backoff_seconds[-1] if self.backoff_seconds else 0.0

    @property
    def launch_command(self) -> str | None:
        """실제로 실행할 명령(artifact 또는 명시적 오버라이드)."""
        return self.command or self.artifact_path

    @property
    def pid_hint(self) -> str:
        """자식 PID 를 셀 때 cmdline 에서 찾을 토큰(대상 스크립트/바이너리 이름)."""
        if self.args:
            return Path(self.args[0]).name
        return Path(self.launch_command).name if self.launch_command else ""


@dataclass
class _CallRequest:
    """호출 하나. future 는 어느 스레드에서든 완료시킬 수 있다."""

    name: str
    arguments: Mapping[str, object]
    timeout: float
    retry_on_transport: bool
    idempotent: bool
    future: concurrent.futures.Future[MCPToolOutcome]
    enqueued_at: float = field(default_factory=time.monotonic)


@dataclass
class _ListRequest:
    """도구 목록 요청(등록 단계에서 한 번 쓴다)."""

    future: concurrent.futures.Future[list[dict[str, object]]]
    timeout: float = 15.0


class _Sentinel:
    """큐로 들어오는 제어 메시지(child 가 죽었거나 호스트가 멈추라는 신호)."""

    __slots__ = ("kind",)

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def __repr__(self) -> str:  # pragma: no cover — 진단용
        return f"<{self.kind}>"


SESSION_LOST: Final[_Sentinel] = _Sentinel("session_lost")
HOST_SHUTDOWN: Final[_Sentinel] = _Sentinel("shutdown")


class SsakSearchRuntime:
    """번들 검색 child 하나를 소유하는 관리형 런타임.

    호스트는 ``ensure_ready()`` · ``call_tool()`` · ``probe()`` · ``shutdown()`` 만 쓴다.
    모든 비동기 작업은 이 객체가 만든 **전용 스레드의 전용 루프** 안에서 일어난다.
    """

    def __init__(
        self,
        config: SearchRuntimeConfig | None = None,
        *,
        verdict: ArtifactVerdict | None = None,
        connector: Callable[[StdioServerParameters], Any] | None = None,
        child_pid_probe: Callable[[], list[int]] | None = None,
    ) -> None:
        self.config = config or SearchRuntimeConfig()
        self._connector = connector or stdio_client
        self._child_pid_probe = child_pid_probe or self._probe_child_pids

        self._state = SearchRuntimeState.STOPPED if self.config.enabled else SearchRuntimeState.DISABLED
        self._verdict = verdict
        self._verdict_checked = False

        self._state_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._ready_event = threading.Event()

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._queue: asyncio.Queue[Any] | None = None
        self._shutdown_requested = threading.Event()

        # 아래 셋은 supervisor 루프(task)에서만 만져진다.
        self._stack: contextlib.AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._session_lost: str | None = None

        self._attempts_in_episode = 0
        self._spawn_attempts = 0
        self._retry_waits: list[float] = []
        self._circuit_open = False
        self._circuit_opened_at = 0.0
        self._last_error: str | None = None
        self._last_teardown: str | None = None
        self._last_exit: dict[str, object] | None = None
        self._started_at: float | None = None
        self._ready_at: float | None = None
        self._last_shutdown_clean: bool | None = None

    # ── 상태 조회 ────────────────────────────────────────────────────────────
    @property
    def state(self) -> SearchRuntimeState:
        with self._state_lock:
            return self._state

    @property
    def circuit_open(self) -> bool:
        with self._state_lock:
            return self._circuit_open

    def status(self) -> dict[str, object]:
        """운영/증거용 스냅숏. `child_pids` 는 우리 프로세스 트리에서 **관측한** 값이다."""
        with self._state_lock:
            state = self._state
            attempts = self._attempts_in_episode
            circuit = self._circuit_open
            spawns = self._spawn_attempts
            waits = list(self._retry_waits)
            last_error = self._last_error
            last_teardown = self._last_teardown
            last_exit = dict(self._last_exit) if self._last_exit else None
            started_at = self._started_at
            ready_at = self._ready_at
            clean = self._last_shutdown_clean
        return {
            "server_name": self.config.server_name,
            "state": state.value,
            "circuit_open": circuit,
            "start_attempts_in_episode": attempts,
            "max_start_attempts": self.config.max_start_attempts,
            "spawn_attempts": spawns,
            "retry_waits_seconds": waits,
            "last_error": last_error,
            "last_teardown": last_teardown,
            "last_exit": last_exit,
            "started_at": started_at,
            "ready_at": ready_at,
            "artifact": self._verdict.detail if self._verdict else None,
            "child_pids": self.child_pids(),
            "shutdown_clean": clean,
            "kill_policy": "only the process tree the MCP SDK spawned is terminated; this runtime never kills by name or pgid",
        }

    def child_pids(self) -> list[int]:
        """우리 프로세스의 자식 중 이 런타임의 child 로 보이는 PID(관측 전용)."""
        try:
            return self._child_pid_probe()
        except Exception:  # noqa: BLE001 — 관측 실패가 런타임 상태를 바꾸면 안 된다
            logger.debug("child pid probe failed", exc_info=True)
            return []

    def _probe_child_pids(self) -> list[int]:
        import psutil

        hint = self.config.pid_hint
        if not hint:
            return []
        found: list[int] = []
        # 우리 자손만 본다. 이름이 아니라 **이 런타임이 실행한 그 파일**을 가리키는 토큰으로
        # 거르는 이유는 task 9 의 교훈이다: psutil.children() 만 쓰면 다른 시험의 child 까지 세어
        # "child 0" 이라는 주장이 거짓이 된다.
        for child in psutil.Process().children(recursive=True):
            try:
                cmdline = child.cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied):  # pragma: no cover — 경쟁 조건
                continue
            if any(hint in token for token in cmdline):
                found.append(child.pid)
        return sorted(found)

    # ── 수명주기 ─────────────────────────────────────────────────────────────
    def start(self) -> bool:
        """supervisor 스레드를 (한 번만) 띄운다. child 는 아직 만들지 않는다."""
        if not self.config.enabled:
            with self._state_lock:
                self._state = SearchRuntimeState.DISABLED
            return False
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._shutdown_requested.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name=f"ssak-search-runtime-{self.config.server_name}",
                daemon=True,
            )
            self._thread.start()
        return self._loop_ready.wait(timeout=5.0)

    def ensure_ready(self, timeout: float | None = None) -> bool:
        """child 를 사용 가능하게 만든다(동시에 10번 불러도 child 는 1개)."""
        if not self.config.enabled:
            return False
        if self.state is SearchRuntimeState.READY:
            return True
        verdict = self._check_artifact_once()
        if verdict is not None and not verdict.ok:
            # fail-closed: 어느 bytes 를 실행하는지 모르면 child 를 만들지 않는다.
            with self._state_lock:
                self._state = SearchRuntimeState.FAILED
                self._last_error = verdict.detail
            return False
        if not self.start():
            return False
        deadline = time.monotonic() + (timeout if timeout is not None else self.config.ready_timeout_seconds)
        while time.monotonic() < deadline:
            state = self.state
            if state is SearchRuntimeState.READY:
                return True
            if state in (SearchRuntimeState.FAILED, SearchRuntimeState.DISABLED):
                return False
            if self._circuit_open and not self._cooldown_elapsed():
                return False  # 회로 열림 — 즉시 거절하고 새 child 를 만들지 않는다
            _ = self._ready_event.wait(timeout=min(0.05, max(deadline - time.monotonic(), 0.0)))
        return self.state is SearchRuntimeState.READY

    def _cooldown_elapsed(self) -> bool:
        with self._state_lock:
            return (time.monotonic() - self._circuit_opened_at) >= self.config.circuit_cooldown_seconds

    def reset_circuit(self) -> None:
        """회로를 수동으로 닫는다(운영자/테스트의 명시적 행동)."""
        with self._state_lock:
            self._circuit_open = False
            self._attempts_in_episode = 0
            if self._state is SearchRuntimeState.FAILED:
                self._state = SearchRuntimeState.STOPPED
        _wake(self._loop)

    def _check_artifact_once(self) -> ArtifactVerdict | None:
        """artifact 를 한 번만 검증한다(명시적 오버라이드는 검증하지 않는다)."""
        if self.config.command and not self.config.require_manifest:
            return None
        with self._state_lock:
            if self._verdict_checked:
                return self._verdict
            self._verdict_checked = True
        if self._verdict is None:
            self._verdict = verify_bundled_artifact(
                self.config.artifact_path,
                self.config.manifest_path,
                require_manifest=self.config.require_manifest,
            )
        if not self._verdict.ok:
            logger.error("search artifact rejected (fail-closed): %s", self._verdict.detail)
        return self._verdict

    def probe(self, timeout: float = 5.0) -> MCPToolOutcome:
        """세션에 ping 을 보낸다(child 생존 확인 = exit 관찰의 실시간 경로)."""
        loop = self._loop
        if self.state is not SearchRuntimeState.READY or loop is None or loop.is_closed():
            return error_outcome(
                f"search runtime is not ready (state={self.state.value})",
                server_name=self.config.server_name,
                transport=TRANSPORT,
                error_code="RUNTIME_NOT_READY",
            )
        future: concurrent.futures.Future[MCPToolOutcome] = concurrent.futures.Future()
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._submit_probe, future)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return error_outcome(
                f"search child ping timed out after {timeout}s",
                server_name=self.config.server_name,
                transport=TRANSPORT,
                error_code="TIMEOUT",
            )

    def list_tools(self, timeout: float = 15.0) -> list[dict[str, object]]:
        """child 가 광고하는 도구 목록(등록용). 실패하면 빈 목록 + `last_error` 기록."""
        if not self.ensure_ready(timeout=timeout):
            return []
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None or loop.is_closed():  # pragma: no cover
            return []
        request = _ListRequest(future=concurrent.futures.Future(), timeout=timeout)
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._enqueue_list, request)
        try:
            return request.future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            with self._state_lock:
                self._last_error = f"list_tools timed out after {timeout}s"
            return []

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object] | None = None,
        *,
        timeout: float | None = None,
        retry_on_transport: bool = False,
        idempotent: bool = True,
    ) -> MCPToolOutcome:
        """child 의 툴을 호출한다. 이 런타임은 **툴 호출을 스스로 재시도하지 않는다**."""
        if not self.config.enabled:
            return error_outcome(
                "ssak search runtime is disabled by configuration",
                server_name=self.config.server_name,
                tool_name=name,
                transport=TRANSPORT,
                error_code="RUNTIME_DISABLED",
            )
        if retry_on_transport and not idempotent:
            # 비멱등 작업: 전송이 끊긴 뒤 재요청하면 상대가 이미 적용했을 수 있다 — 명시적으로 거절.
            return error_outcome(
                f"refusing to retry non-idempotent tool '{name}' across a transport failure",
                server_name=self.config.server_name,
                tool_name=name,
                transport=TRANSPORT,
                error_code="NON_IDEMPOTENT_NOT_RETRIED",
            )
        call_timeout = timeout if timeout is not None else self.config.call_timeout_seconds
        if not self.ensure_ready(timeout=call_timeout):
            code = "CIRCUIT_OPEN" if self.circuit_open else "RUNTIME_NOT_READY"
            with self._state_lock:
                last_error = self._last_error
            return error_outcome(
                f"search child is unavailable (state={self.state.value}): {last_error or 'not ready'}",
                server_name=self.config.server_name,
                tool_name=name,
                transport=TRANSPORT,
                error_code=code,
            )
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None or loop.is_closed():  # pragma: no cover — ready 였다면 있다
            return error_outcome(
                "search runtime has no live event loop",
                server_name=self.config.server_name,
                tool_name=name,
                transport=TRANSPORT,
                error_code="RUNTIME_NOT_READY",
            )
        request = _CallRequest(
            name=name,
            arguments=dict(arguments or {}),
            timeout=call_timeout,
            retry_on_transport=retry_on_transport,
            idempotent=idempotent,
            future=concurrent.futures.Future(),
        )
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._enqueue, request)
        try:
            return request.future.result(timeout=call_timeout)
        except concurrent.futures.TimeoutError:
            return error_outcome(
                f"search tool '{name}' timed out after {call_timeout}s",
                server_name=self.config.server_name,
                tool_name=name,
                transport=TRANSPORT,
                error_code="TIMEOUT",
            )

    def shutdown(self, timeout: float | None = None) -> dict[str, object]:
        """child 를 정리한다. 반환 스냅숏의 `child_pids` 가 "child 0" 의 증거다."""
        wait = timeout if timeout is not None else self.config.shutdown_timeout_seconds
        self._shutdown_requested.set()
        thread = self._thread
        loop = self._loop
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._request_host_shutdown)
        if thread is not None and thread.is_alive():
            thread.join(timeout=wait)
        self._thread = None
        self._loop = None
        self._queue = None
        with self._state_lock:
            if self._state not in (SearchRuntimeState.DISABLED, SearchRuntimeState.FAILED):
                self._state = SearchRuntimeState.STOPPED
            self._last_shutdown_clean = not self.child_pids()
            clean = self._last_shutdown_clean
        self._ready_event.clear()
        status = self.status()
        status["shutdown_clean"] = clean
        return status

    # ── 전용 루프 (supervisor) ───────────────────────────────────────────────
    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._queue = asyncio.Queue()
        asyncio.set_event_loop(loop)
        self._loop_ready.set()
        try:
            loop.run_until_complete(self._serve())
        except asyncio.CancelledError:
            # MCP SDK 의 stdio cancel scope 는 child 사망/정리 시 이 task 의 대기를 취소한다.
            # 그건 고장이 아니라 SDK 가 소유한 scope 의 정리 경로다 — 크래시로 보고하지 않는다.
            logger.debug("ssak search supervisor cancelled (SDK stdio scope teardown)")
        except Exception:  # noqa: BLE001 — supervisor 는 호스트로 예외를 올리지 않는다
            logger.exception("ssak search supervisor crashed")
            with self._state_lock:
                self._state = SearchRuntimeState.FAILED
                self._last_error = "supervisor crashed"
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            self._loop_ready.clear()
            self._ready_event.clear()

    def _submit_probe(self, future: concurrent.futures.Future[MCPToolOutcome]) -> None:
        loop = self._loop
        if loop is None:  # pragma: no cover
            future.set_result(
                error_outcome(
                    "runtime loop is gone",
                    server_name=self.config.server_name,
                    transport=TRANSPORT,
                    error_code="RUNTIME_NOT_READY",
                )
            )
            return
        _ = loop.create_task(self._probe_once(future))

    async def _probe_once(self, future: concurrent.futures.Future[MCPToolOutcome]) -> None:
        session = self._session
        if session is None:
            future.set_result(
                error_outcome(
                    "no live session to ping",
                    server_name=self.config.server_name,
                    transport=TRANSPORT,
                    error_code="RUNTIME_NOT_READY",
                )
            )
            return
        try:
            await session.send_ping()
        except Exception as exc:  # noqa: BLE001 — 죽은 child 는 여기서 관측된다
            self._mark_session_lost(f"ping failed: {_describe(exc)}")
            future.set_result(
                error_outcome(
                    f"search child is gone: {exc}",
                    server_name=self.config.server_name,
                    transport=TRANSPORT,
                    error_code="CHILD_EXITED",
                )
            )
            return
        future.set_result(
            build_outcome(
                {"content": [{"type": "text", "text": "pong"}]},
                server_name=self.config.server_name,
                transport=TRANSPORT,
            )
        )

    def _enqueue_list(self, request: _ListRequest) -> None:
        queue = self._queue
        if queue is None:  # pragma: no cover
            request.future.set_result([])
            return
        queue.put_nowait(request)

    def _enqueue(self, request: _CallRequest) -> None:
        queue = self._queue
        if queue is None:  # pragma: no cover
            request.future.set_result(
                error_outcome(
                    "runtime queue is gone",
                    server_name=self.config.server_name,
                    tool_name=request.name,
                    transport=TRANSPORT,
                    error_code="RUNTIME_NOT_READY",
                )
            )
            return
        queue.put_nowait(request)

    def _request_host_shutdown(self) -> None:
        queue = self._queue
        if queue is not None:
            queue.put_nowait(HOST_SHUTDOWN)

    async def _serve(self) -> None:
        """전용 루프의 **단일 task** — 세션 진입·호출·teardown 이 전부 여기서 일어난다."""
        try:
            while not self._shutdown_requested.is_set():
                if self._session is None:
                    if not await self._start_session_with_retries():
                        if not await self._wait_for_trial_or_shutdown():
                            break
                        continue
                outcome = await self._serve_calls()
                if outcome == "shutdown":
                    break
                # 세션을 잃었다: 죽은 세션을 같은 task 에서 정리하고 episode 를 새로 시작한다.
                await self._teardown_guarded()
        finally:
            await self._teardown_guarded()
            self._fail_pending("runtime stopped")

    # ── 세션 시작(backoff·회로) ──────────────────────────────────────────────
    async def _start_session_with_retries(self) -> bool:
        """episode 예산 안에서 시작을 시도한다. 예산은 **세션 상실도 소모**한다."""
        attempts = max(1, self.config.max_start_attempts)
        with self._state_lock:
            self._state = SearchRuntimeState.STARTING
        while True:
            with self._state_lock:
                if self._attempts_in_episode >= attempts:
                    break
                self._attempts_in_episode += 1
                attempt = self._attempts_in_episode
            ok, problem = await self._connect()
            if ok:
                now = time.monotonic()
                with self._state_lock:
                    self._state = SearchRuntimeState.READY
                    self._circuit_open = False
                    self._last_error = None
                    self._started_at = now
                    self._ready_at = now
                self._ready_event.set()
                logger.info("ssak search child ready (attempt %d, spawns=%d)", attempt, self._spawn_attempts)
                return True
            with self._state_lock:
                self._last_error = problem
            logger.warning("ssak search child start attempt %d/%d failed: %s", attempt, attempts, problem)
            if self._shutdown_requested.is_set():
                return False
            if self._attempts_in_episode < attempts:
                wait = 0.0
                if self.config.backoff_seconds:
                    index = min(self._attempts_in_episode - 1, len(self.config.backoff_seconds) - 1)
                    wait = self.config.backoff_seconds[index]
                with self._state_lock:
                    self._retry_waits.append(wait)
                if not await self._sleep_or_shutdown(wait):
                    return False
        with self._state_lock:
            self._circuit_open = True
            self._circuit_opened_at = time.monotonic()
            self._state = SearchRuntimeState.FAILED
        logger.error(
            "ssak search child start gave up after %d attempts — circuit open for %.1fs: %s",
            attempts,
            self.config.circuit_cooldown_seconds,
            self._last_error,
        )
        return False

    async def _sleep_or_shutdown(self, seconds: float) -> bool:
        """backoff 대기. 호스트가 멈추라고 하면 즉시 깨어난다."""
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            if self._shutdown_requested.is_set():
                return False
            await asyncio.sleep(min(0.05, max(end - time.monotonic(), 0.0)))
        return not self._shutdown_requested.is_set()

    async def _wait_for_trial_or_shutdown(self) -> bool:
        """회로가 열린 뒤: cooldown 이 지나면 trial 1회를 허용하고, 아니면 대기한다."""
        while not self._shutdown_requested.is_set():
            if self._cooldown_elapsed():
                with self._state_lock:
                    self._circuit_open = False
                    # trial 은 **새 episode** 다 — 예산을 되돌리지 않으면 시도 없이 곧바로 회로가 다시 열린다.
                    self._attempts_in_episode = 0
                    self._retry_waits = []
                    self._state = SearchRuntimeState.STOPPED
                logger.info("ssak search circuit cooldown elapsed — allowing one trial start")
                return True
            await asyncio.sleep(0.05)
        return False

    async def _connect(self) -> tuple[bool, str]:
        """MCP SDK stdio context 에 진입한다 — child 는 SDK 가 소유한다(우리는 Popen 을 만들지 않는다)."""
        command = self.config.launch_command
        if not command:
            return False, "no search artifact configured"
        params = StdioServerParameters(
            command=command,
            args=list(self.config.args),
            env=self._child_env(),
            # cwd 를 넘기지 않는다 → child 는 호스트의 cwd 를 그대로 물려받는다(불변).
            cwd=None,
        )
        stack = contextlib.AsyncExitStack()
        self._spawn_attempts += 1
        try:
            read, write = await stack.enter_async_context(self._connector(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            _ = await session.initialize()
        except Exception as exc:  # noqa: BLE001 — 시작 실패는 상태로 남기고 재시도한다
            with contextlib.suppress(Exception):
                await stack.aclose()
            return False, _describe(exc)
        self._stack = stack
        self._session = session
        self._session_lost = None
        return True, ""

    def _child_env(self) -> dict[str, str]:
        """최소 allowlist 만 넘긴다(호스트의 비밀 환경을 child 에게 주지 않는다).

        주의(정직): MCP SDK 의 stdio transport 는 우리가 넘긴 env 를 ``get_default_environment()``
        위에 **덮어쓰는** 형태로 합친다 — 즉 우리 allowlist 는 "호스트 환경에서 무엇을 전달하는가"를
        제한하고, SDK 는 자기 기본 목록(PATH/HOME/USER/SHELL/LOGNAME 등)을 별도로 더한다.
        둘 다 비밀 값을 담지 않는다(호스트의 API 키·토큰은 양쪽 어디에도 없다). 이 합성 결과를
        시험이 child 쪽에서 직접 확인한다.
        """
        env = {name: os.environ[name] for name in self.config.env_allowlist if name in os.environ}
        env.update({str(key): str(value) for key, value in self.config.extra_env.items()})
        return env

    # ── 호출 서비스(단일 소유자) ────────────────────────────────────────────
    async def _serve_calls(self) -> str:
        queue = self._queue
        if queue is None:  # pragma: no cover
            return "shutdown"
        ping = asyncio.create_task(self._ping_loop())
        try:
            while True:
                try:
                    item = await queue.get()
                except asyncio.CancelledError:
                    # 위와 같은 이유로 SDK scope 취소가 여기 도달한다 — 우리 계약에서는 "세션 상실"이다.
                    self._mark_session_lost("stdio scope cancelled (the child exited)")
                    return "session_lost"
                if item is HOST_SHUTDOWN:
                    return "shutdown"
                if item is SESSION_LOST:
                    return "session_lost"
                if isinstance(item, _ListRequest):
                    await self._dispatch_list(item)
                    continue
                await self._dispatch(cast(_CallRequest, item))
                if self._session_lost is not None:
                    return "session_lost"
                if self._shutdown_requested.is_set():
                    return "shutdown"
        finally:
            _ = ping.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping

    async def _ping_loop(self) -> None:
        """exit 관찰: 준비된 세션이 조용히 죽는 것을 bounded 시간 안에 발견한다.

        호출이 진행 중일 때는 ping 하지 않는다 — 느린 정상 호출을 죽음으로 오판하지 않기 위해서다.
        호출 중에는 그 호출 자체의 실패가 관찰 수단이다.
        """
        interval = max(0.05, self.config.monitor_interval_seconds)
        while True:
            await asyncio.sleep(interval)
            session = self._session
            if session is None:
                return
            try:
                await session.send_ping()
            except Exception as exc:  # noqa: BLE001 — 죽은 child
                self._mark_session_lost(f"child exited (ping failed: {_describe(exc)})")
                queue = self._queue
                if queue is not None:
                    queue.put_nowait(SESSION_LOST)
                return

    async def _dispatch_list(self, request: _ListRequest) -> None:
        session = self._session
        if session is None:
            request.future.set_result([])
            return
        try:
            listing = await asyncio.wait_for(session.list_tools(), timeout=max(0.1, request.timeout))
        except Exception as exc:  # noqa: BLE001 — 등록 실패는 빈 목록 + 기록
            logger.warning("ssak search list_tools failed: %s", exc)
            self._mark_session_lost(f"list_tools failed: {exc}")
            request.future.set_result([])
            return
        tools: list[dict[str, object]] = []
        for tool in getattr(listing, "tools", []):
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            tools.append(
                {
                    "name": str(getattr(tool, "name", "")),
                    "description": str(getattr(tool, "description", "") or ""),
                    "inputSchema": schema,
                }
            )
        request.future.set_result(tools)

    async def _dispatch(self, request: _CallRequest) -> None:
        session = self._session
        if session is None:
            request.future.set_result(
                error_outcome(
                    "search child session is gone",
                    server_name=self.config.server_name,
                    tool_name=request.name,
                    transport=TRANSPORT,
                    error_code="CHILD_EXITED",
                )
            )
            return
        try:
            result = await asyncio.wait_for(
                session.call_tool(request.name, arguments=dict(request.arguments)),
                timeout=max(0.1, request.timeout),
            )
        except asyncio.TimeoutError:
            # 호출 타임아웃은 세션을 죽이지 않는다(느린 검색일 수 있다) — 결과만 실패로 남긴다.
            with self._state_lock:
                self._last_error = f"tool '{request.name}' timed out after {request.timeout}s"
            request.future.set_result(
                error_outcome(
                    f"search tool '{request.name}' timed out after {request.timeout}s",
                    server_name=self.config.server_name,
                    tool_name=request.name,
                    transport=TRANSPORT,
                    error_code="TIMEOUT",
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 — 전송 실패를 typed 결과로 보존한다
            logger.warning("search tool '%s' call failed: %s", request.name, exc)
            self._mark_session_lost(f"call failed: {exc}")
            request.future.set_result(
                error_outcome(
                    f"search tool '{request.name}' failed on the bundle: {exc}",
                    server_name=self.config.server_name,
                    tool_name=request.name,
                    transport=TRANSPORT,
                    error_code="TRANSPORT_LOST",
                )
            )
            return
        # 성공한 호출은 child 가 일하고 있다는 증거다 — episode 예산을 되돌린다.
        with self._state_lock:
            self._attempts_in_episode = 0
        request.future.set_result(
            build_outcome(result, server_name=self.config.server_name, tool_name=request.name, transport=TRANSPORT)
        )

    def _mark_session_lost(self, reason: str) -> None:
        """세션 상실을 관찰했다. 상실도 한 번의 시도로 계산한다 — 무한 재spawn 을 막는다."""
        attempts_limit = max(1, self.config.max_start_attempts)
        with self._state_lock:
            if self._session_lost is not None:
                # 같은 죽음을 두 경로가 본다(ping 실패 / SDK scope 취소). **첫 관측만** 센다:
                # 아니면 한 번의 죽음이 예산을 두 번 먹고, 이유가 덜 유용한 쪽으로 덮인다.
                return
            self._session_lost = reason
            self._last_exit = {"reason": reason, "at": time.time()}
            healthy_for = (time.monotonic() - self._ready_at) if self._ready_at is not None else 0.0
            if healthy_for >= self.config.health_reset_seconds:
                # 오래 살다가 죽은 child 는 새 episode 로 본다(첫 상실이 바로 회로를 열면 안 된다).
                self._attempts_in_episode = 0
            self._attempts_in_episode += 1
            exhausted = self._attempts_in_episode >= attempts_limit
            if exhausted:
                self._circuit_open = True
                self._circuit_opened_at = time.monotonic()
                self._state = SearchRuntimeState.FAILED
                self._last_error = f"child keeps exiting: {reason}"
            elif self._state is SearchRuntimeState.READY:
                # 준비됐던 세션이 죽었다: 재시작은 허용하지만 툴 호출은 재시도하지 않는다.
                self._state = SearchRuntimeState.DEGRADED
            current = self._state.value
            attempts = self._attempts_in_episode
        logger.warning(
            "ssak search child session lost: %s (state=%s, attempts=%d/%d)",
            reason,
            current,
            attempts,
            attempts_limit,
        )

    def _fail_pending(self, reason: str) -> None:
        queue = self._queue
        if queue is None:  # pragma: no cover
            return
        while not queue.empty():
            item = queue.get_nowait()
            if isinstance(item, _CallRequest) and not item.future.done():
                item.future.set_result(
                    error_outcome(
                        f"search tool '{item.name}' was not run: {reason}",
                        server_name=self.config.server_name,
                        tool_name=item.name,
                        transport=TRANSPORT,
                        error_code="RUNTIME_STOPPED",
                    )
                )

    async def _teardown_guarded(self) -> None:
        """teardown 을 **같은 task 에서** 끝까지 시도한다.

        별도 task 로 미루면 안 된다: SDK 의 stdio context 는 cancel scope 를 만들고, 그 scope 는
        진입한 task 에 묶여 있다 — 다른 task 에서 나가려 하면 SDK 가
        `RuntimeError('Attempted to exit cancel scope in a different task …')` 를 낸다(task 9 실측).
        그래서 취소를 만나도 여기서 다시 시도한다(child 를 남기는 쪽이 더 나쁜 결과다).
        """
        for _ in range(3):
            try:
                await self._teardown_session()
                return
            except asyncio.CancelledError:
                if self._stack is None:
                    return
                continue
            except Exception:  # noqa: BLE001 — 정리 실패는 기록하고 진행
                logger.warning("ssak search teardown failed", exc_info=True)
                return

    async def _teardown_session(self) -> None:
        """세션 정리 — **이 task** 안에서 한다(다른 task 면 SDK 가 cancel scope 로 거부한다)."""
        stack = self._stack
        self._session = None
        if stack is None:
            return
        with self._state_lock:
            if self._state is not SearchRuntimeState.FAILED:
                self._state = SearchRuntimeState.STOPPING
        try:
            # SDK 가 MCP stdio shutdown sequence(입력 닫기 → 대기 → SIGTERM)를 **그 트리에만** 수행한다.
            await stack.aclose()
        except Exception as exc:  # noqa: BLE001 — 이미 죽은 child 의 정리는 실패가 아니라 정보다
            # 주의: 여기서 `_last_error` 를 덮어쓰면 "회로가 왜 열렸는가"가 정리 잡음으로 가려진다.
            # 정리 결과는 별도 필드에 남기고 상태는 진행한다.
            described = _describe(exc)
            with self._state_lock:
                self._last_teardown = described
            logger.info("ssak search session teardown reported: %s", described)
        # aclose 가 취소로 중단되면 스택을 남겨 _teardown_guarded 가 다시 시도하게 한다.
        self._stack = None
        with self._state_lock:
            if self._state is not SearchRuntimeState.FAILED:
                self._state = SearchRuntimeState.STOPPED
        self._ready_event.clear()


def _wake(loop: asyncio.AbstractEventLoop | None) -> None:
    if loop is not None and not loop.is_closed():
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(lambda: None)


# ── 호스트 하나에 하나 있는 런타임 ────────────────────────────────────────────
# "한 host instance 가 한 검색 child 를 관리한다"를 강제하는 지점이다. 두 곳에서 각자 런타임을
# 만들면 child 가 둘이 되고 stdout 을 나눠 읽게 된다.
# 소문자 이름인 이유: 재대입되는 상태(상수 아님)이므로 basedpyright 의 상수 재정의 규칙을 피한다.
_host_runtime: SsakSearchRuntime | None = None
_HOST_RUNTIME_LOCK = threading.Lock()


def get_ssak_search_runtime(config: SearchRuntimeConfig | None = None) -> SsakSearchRuntime:
    """이 프로세스의 검색 런타임(지연 생성 싱글턴)."""
    global _host_runtime
    with _HOST_RUNTIME_LOCK:
        if _host_runtime is None:
            _host_runtime = SsakSearchRuntime(config or runtime_config_from_env())
        return _host_runtime


def resolve_ssak_search_runtime(
    config: SearchRuntimeConfig,
    *,
    replace_when_idle: bool = False,
) -> SsakSearchRuntime:
    """설정과 어긋나는 싱글턴을 **child 가 없을 때만** 교체해 돌려준다.

    왜 필요한가: 싱글턴은 처음 만들어질 때의 설정을 붙들므로, 설정 화면에서 artifact 경로를
    바꿔도 살아 있는 싱글턴은 옛 경로를 계속 쓴다. 그렇다고 **child 를 거둬내고 교체하면**
    진행 중인 검색이 죽는다(그리고 task 15 가 "실행 중 child binary 직접 교체 금지"를 요구한다).
    그래서:

    - `replace_when_idle=True` 이고 관측된 child 가 0 이면 → 기존 싱글턴을 정리하고 새로 만든다.
    - child 가 살아 있으면 → 손대지 않고 그대로 돌려준다(`restart_required` 는 별도 판정).
    - `replace_when_idle=False`(기본) → `get_ssak_search_runtime` 과 같은 동작(동일성 보장).

    기본값이 False 인 이유: task 12 의 "한 host instance = 한 런타임" 동일성 계약을 깨지 않기
    위해, 교체는 **명시적으로 요청한 경로**(상태 확인·재시도·연결 확인)에서만 일어나야 한다.
    """
    if not replace_when_idle:
        return get_ssak_search_runtime(config)
    global _host_runtime
    with _HOST_RUNTIME_LOCK:
        current = _host_runtime
    if current is not None and _runtime_config_matches(current.config, config):
        return current
    if current is not None and current.child_pids():
        # 살아 있는 child 를 거둬내지 않는다 — 교체 대신 그대로 쓴다.
        logger.warning("ssak search runtime is serving a live child; not replacing it for new settings")
        return current
    with _HOST_RUNTIME_LOCK:
        if _host_runtime is current:
            _host_runtime = None
    if current is not None:
        with contextlib.suppress(Exception):  # noqa: BLE001 — 교체가 실패해도 새 런타임은 만든다
            current.shutdown(timeout=10.0)
    return get_ssak_search_runtime(config)


def _runtime_config_matches(left: SearchRuntimeConfig, right: SearchRuntimeConfig) -> bool:
    """두 설정이 **같은 child 를 가리키는가**(경로·활성 여부·server 이름).

    backoff/타임아웃 같은 튜닝 값은 교체 사유가 아니다 — 교체는 "다른 것을 실행하려 한다"일 때만 한다.
    """
    return (
        left.enabled == right.enabled
        and left.server_name == right.server_name
        and _same_path(left.artifact_path, right.artifact_path)
        and _same_path(left.manifest_path, right.manifest_path)
    )


def _same_path(left: str | None, right: str | None) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        # 빈 문자열과 None 은 같은 뜻이다 — 여기서 갈라지면 매 호출마다 교체가 일어난다.
        return not left_text and not right_text
    try:
        return Path(left_text).expanduser().resolve() == Path(right_text).expanduser().resolve()
    except OSError:  # pragma: no cover — 해석 불가 경로는 문자열 비교로 물러선다
        return left_text == right_text


def runtime_config_from_env(env: Mapping[str, str] | None = None) -> SearchRuntimeConfig:
    """환경 변수에서 설정을 읽는다(task 13 이 config 스키마를 확장하기 전의 최소 표면).

    - ``AGK_SEARCH_ENABLED``(기본 true) · ``AGK_SEARCH_ARTIFACT``(기본 없음)
    - ``AGK_SEARCH_MANIFEST``(기본 없음 — 없으면 fail-closed 이므로 함께 지정해야 한다)
    """
    source = env if env is not None else os.environ
    enabled_raw = str(source.get("AGK_SEARCH_ENABLED", "true")).strip().lower()
    return SearchRuntimeConfig(
        artifact_path=source.get("AGK_SEARCH_ARTIFACT") or None,
        manifest_path=source.get("AGK_SEARCH_MANIFEST") or None,
        enabled=enabled_raw not in {"0", "false", "no", "off"},
    )


def shutdown_ssak_search_runtime(timeout: float | None = None) -> dict[str, object] | None:
    """호스트 종료 훅: child 를 정리하고 결과(``child_pids`` 포함)를 돌려준다.

    아직 런타임을 만든 적이 없으면 아무것도 하지 않는다(종료 경로에서 새 child 를 만들면 안 된다).
    """
    global _host_runtime
    with _HOST_RUNTIME_LOCK:
        runtime = _host_runtime
        _host_runtime = None
    if runtime is None:
        return None
    return runtime.shutdown(timeout=timeout)


__all__ = [
    "ArtifactVerdict",
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_ENV_ALLOWLIST",
    "DEFAULT_MAX_START_ATTEMPTS",
    "SearchRuntimeConfig",
    "SearchRuntimeState",
    "SsakSearchRuntime",
    "get_ssak_search_runtime",
    "resolve_ssak_search_runtime",
    "runtime_config_from_env",
    "shutdown_ssak_search_runtime",
    "verify_bundled_artifact",
]
