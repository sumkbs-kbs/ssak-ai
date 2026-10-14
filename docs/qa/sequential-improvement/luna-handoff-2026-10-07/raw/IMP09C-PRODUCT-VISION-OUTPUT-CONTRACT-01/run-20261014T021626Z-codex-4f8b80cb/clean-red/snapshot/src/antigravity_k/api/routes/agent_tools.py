"""Agent Tools module."""

import asyncio
import base64
import hashlib
import inspect
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Protocol, cast

if TYPE_CHECKING:
    from playwright.async_api import Page as _AsyncPage

    from antigravity_k.tools.browser_observation import BrowserObserver, Observation, ObservationPolicy

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from antigravity_k.api.browser_session_state import (
    BrowserSessionLimitError,
    BrowserSessionRegistry,
    BrowserSessionState,
)
from antigravity_k.api.contracts.shell import (
    ShellApprovalRequiredError,
    ShellPolicyDeniedError,
    ShellSandboxUnavailableError,
    ShellTimeoutError,
)
from antigravity_k.config import config
from antigravity_k.engine.access_mode import AccessMode, get_access_mode
from antigravity_k.engine.approval_manager import (
    ApprovalStatus,
    get_approval_manager,
)
from antigravity_k.engine.sandbox import SandboxRunner, _minimal_child_env, _python_runtime_read_paths
from antigravity_k.tools.browser_approval import (
    ALWAYS_ALLOW_FORBIDDEN,
    APPROVAL_BINDING_CHANGED,
    APPROVAL_EXPIRED,
    APPROVAL_REJECTED,
    APPROVAL_REPLAYED,
    APPROVAL_REQUIRED,
    MODEL_CLAIM_REFUSED,
    MODEL_TOKEN_REFUSED,
    SECRET_HANDLE_UNKNOWN,
    SECRET_ORIGIN_MISMATCH,
    SECRET_VALUE_NOT_ALLOWED,
    ApprovalBinding,
    BrowserApprovalError,
    HumanResolution,
    classify_effect,
    detect_user_handoff,
    get_browser_approval_gate,
    get_browser_secret_vault,
    guard_request_claims,
    origin_of,
    payload_fingerprint,
    summarize_effect,
)
from antigravity_k.tools.browser_session_owner import (
    DEFAULT_SCOPE,
    BrowserOwner,
    BrowserSessionRefusedError,
    get_browser_session_owner,
)
from antigravity_k.tools.egress_policy import EgressPolicyError, validate_egress_url, validate_httpx_request_async
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, PermissionDecision, ToolInvocation, ToolSpec

logger = logging.getLogger(__name__)
router = APIRouter()


browser_state = BrowserSessionState()
# 상한은 **소유자 정책**이 정한다(task 16). 레지스트리는 상태 저장소이고, 세션 수의 권위는 소유자다.
# 예전 기본값 32 는 "상한"이라기보다 사실상 무제한이었고, 시간 축도 없었다.
browser_sessions = BrowserSessionRegistry(
    max_sessions=get_browser_session_owner().max_active_sessions,
    default_state=browser_state,
)
# task 17 계약으로 가는 action 이름. `type` 은 `fill` 의 옛 이름이다(없애지 않고 이유를 남긴다).
_BROWSER_CONTRACT_ACTIONS = frozenset(
    {"observe", "goto", "click", "fill", "type", "scroll", "select", "upload", "download"},
)
_CONTRACT_ACTION_ALIASES = {"type": "fill"}
# 운영자가 지정한 QA 대상(보통 루프백)을 API 경로가 두드릴 수 있게 하는 **명시 옵트인**.
_BROWSER_API_ALLOW_LOCAL_ENV = "AGK_BROWSER_API_ALLOW_LOCAL"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

_MAX_CONSOLE_ENTRIES = 500
_BROWSER_SESSION_HEADER = "X-AGK-Browser-Session"
_BROWSER_TASK_HEADER = "X-AGK-Task-Id"
_MAX_BROWSER_SESSION_ID_LENGTH = 128


class _AccessibilityLike(Protocol):
    async def snapshot(self) -> object: ...


class _PageLike(Protocol):
    accessibility: _AccessibilityLike
    url: str

    def aria_snapshot(self) -> Awaitable[object]: ...

    async def screenshot(self) -> bytes: ...

    async def goto(self, url: str, *, wait_until: str) -> object: ...

    async def click(self, selector: str) -> object: ...

    async def fill(self, selector: str, text: str) -> object: ...

    def on(self, event: str, handler: Callable[[object], object]) -> object: ...


class _RouteLike(Protocol):
    async def abort(self, *, error_code: str) -> object: ...

    async def continue_(self) -> object: ...


class _RequestLike(Protocol):
    url: str


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _append_console_entry(entries: list[dict[str, str]], entry: dict[str, str]) -> None:
    entries.append(entry)
    if len(entries) > _MAX_CONSOLE_ENTRIES:
        del entries[:-_MAX_CONSOLE_ENTRIES]


def _browser_session_id(request: Request | None) -> str:
    if request is None:
        return "default"
    raw_session_id = request.headers.get(_BROWSER_SESSION_HEADER, "").strip()
    if len(raw_session_id) > _MAX_BROWSER_SESSION_ID_LENGTH:
        raise HTTPException(status_code=400, detail="Browser session identifier is too long")
    auth_subject = getattr(request.state, "auth_subject", "anonymous")
    if not isinstance(auth_subject, str) or not auth_subject:
        auth_subject = "anonymous"
    if not raw_session_id:
        raw_session_id = "default"
    session_key = f"{auth_subject}:{raw_session_id}"
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def _browser_owner(request: Request | None) -> BrowserOwner:
    """요청 → 세션 소유자(subject·scope·task). 인증 없는 요청은 `anonymous` 이고,
    그 주체와 기본 scope 는 persistent profile 을 열 수 없다(정책은 소유자 모듈에 있다)."""
    if request is None:
        return BrowserOwner()
    raw_scope = request.headers.get(_BROWSER_SESSION_HEADER, "").strip()
    if len(raw_scope) > _MAX_BROWSER_SESSION_ID_LENGTH:
        raise HTTPException(status_code=400, detail="Browser session identifier is too long")
    subject = getattr(request.state, "auth_subject", "anonymous")
    if not isinstance(subject, str) or not subject:
        subject = "anonymous"
    task_id = request.headers.get(_BROWSER_TASK_HEADER, "").strip()
    return BrowserOwner(subject=subject, scope=raw_scope or DEFAULT_SCOPE, task_id=task_id)


def _browser_state_for(request: Request | None) -> tuple[str, BrowserSessionState]:
    session_id = _browser_session_id(request)
    # 상한을 소유자 정책과 계속 맞춘다(운영 중 env 로 정책이 바뀌면 여기도 따라간다).
    browser_sessions.max_sessions = get_browser_session_owner().max_active_sessions
    try:
        return session_id, browser_sessions.get(session_id)
    except BrowserSessionLimitError as exc:
        raise HTTPException(status_code=429, detail="Too many active browser sessions") from exc


def _api_session_closer(state: BrowserSessionState) -> Callable[[], object]:
    """소유자가 회수할 때 부르는 닫기. Playwright 자원은 async 라 **돌고 있는 루프에 예약**한다
    (회수는 `begin()` 안에서 동기로 일어난다). 루프가 없으면(종료 중 등) 로그만 남긴다 —
    그 한계는 `E/task-16/result.md` 에 적었다.
    """

    def _close() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[Browser] no running loop; async browser session close deferred to shutdown")
            return
        _ = loop.create_task(_close_api_session_async(state))

    return _close


async def _close_api_session_async(state: BrowserSessionState) -> None:
    """브라우저·플레이라이트를 순서대로 닫는다(실패해도 다른 자원은 계속 닫는다)."""
    try:
        if state.browser:
            await state.browser.close()
    except Exception:
        logger.exception("Unhandled exception")
    finally:
        state.browser = None
        state.context = None
        state.page = None
    try:
        if state.playwright:
            await state.playwright.stop()
    except Exception:
        logger.exception("Unhandled exception")
    finally:
        state.playwright = None


def _browser_error_status(error: Exception) -> int:
    message = str(error).lower()
    if "executable doesn't exist" in message or "please run the following command" in message:
        return 503
    return 500


def _observation_status(code: str) -> int:
    """관찰/행동 계약 위반을 HTTP 로 옮긴다(코드는 본문에 그대로 남는다)."""
    from antigravity_k.tools.browser_observation import (
        DOWNLOAD_TOO_LARGE,
        POLICY_DENIED,
        SESSION_MISMATCH,
        STALE_SNAPSHOT,
    )

    if code in {POLICY_DENIED, SESSION_MISMATCH}:
        return 403
    if code == STALE_SNAPSHOT:
        return 409
    if code == DOWNLOAD_TOO_LARGE:
        return 413
    return 400


def _browser_observation_policy(session_id: str, *, with_sandbox: bool) -> "ObservationPolicy":
    """task 샌드박스 경로를 정한다 — 다운로드/업로드는 **세션 전용 디렉터리** 밖으로 나가지 못한다."""
    from antigravity_k.tools.browser_observation import ObservationPolicy

    root = Path(config.paths.data_dir) / "browser" / session_id
    download_dir = root / "downloads"
    upload_root = root / "uploads"
    if with_sandbox:
        for directory in (download_dir, upload_root):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # pragma: no cover - 권한/디스크 문제
                logger.warning("browser sandbox directory unavailable: %s", exc)
    # 로컬 주소는 **운영자가 명시할 때만** 허용한다(기본은 닫힘 — 에이전트가 스스로 고른
    # 주소를 로컬로 열어 주면 egress 정책이 무의미해진다).
    allow_local = str(os.environ.get(_BROWSER_API_ALLOW_LOCAL_ENV, "")).strip().lower() in _TRUTHY
    return ObservationPolicy(
        download_dir=download_dir,
        upload_root=upload_root,
        allow_local=allow_local,
    )


def _browser_observer(request: Request, state: BrowserSessionState, *, with_sandbox: bool) -> "BrowserObserver":
    """요청 → 관찰자. 세션 소유자가 준 페이지에만 붙고, 정책은 요청마다 다시 세운다(샌드박스 경로)."""
    from antigravity_k.tools.browser_observation import observer_for_owner

    session_id, _ = _browser_state_for(request)
    observer = observer_for_owner(_browser_owner(request))
    observer.configure_policy(_browser_observation_policy(session_id, with_sandbox=with_sandbox))
    observer.register_page(state.page)
    return observer


async def _accessibility_tree(page: object) -> str | None:
    page_obj = cast(_PageLike, page)
    if hasattr(page_obj, "aria_snapshot"):
        result = page_obj.aria_snapshot()
        if not inspect.isawaitable(result):
            return None
        snapshot = await result
        return snapshot if isinstance(snapshot, str) and snapshot else None

    accessibility = getattr(page_obj, "accessibility", None)
    if accessibility is None:
        return None
    snapshot_value = await cast(_AccessibilityLike, accessibility).snapshot()
    snapshot = _as_mapping(snapshot_value)
    return _flatten_a11y_tree(snapshot) if snapshot else None


async def _guard_browser_route(route: object, request: object) -> None:
    route_obj = cast(_RouteLike, route)
    request_obj = cast(_RequestLike, request)
    scheme = request_obj.url.split(":", 1)[0].lower()
    if scheme not in {"http", "https"}:
        _ = await route_obj.abort(error_code="blockedbyclient")
        return
    # 운영자가 로컬 QA 대상을 명시했으면 **차단 계층도 같은 문을 연다** — 한쪽만 열면
    # "정책은 통과했는데 네트워크가 막는" 모순이 생긴다(그 모순을 시험에서 만났다).
    allow_local = str(os.environ.get(_BROWSER_API_ALLOW_LOCAL_ENV, "")).strip().lower() in _TRUTHY
    try:
        _ = validate_egress_url(request_obj.url, allow_local=allow_local)
    except EgressPolicyError:
        _ = await route_obj.abort(error_code="blockedbyclient")
        return
    _ = await route_obj.continue_()


# ─── CR-04: 실행 경계 — 권한 모드와 요청 root 스냅샷 ────────────────────
#
# 이전 구현은 `mode="auto-pilot"`을 상수로 고정해, 사용자가 대시보드에서 선택한
# 실행 권한 모드(전체 액세스 / 읽기 전용)를 무시하고 high-risk 도구(셸 실행)를
# 항상 자동 승인했다. 이제는 현재 요청의 기존 권한 모드에서 모드를 도출한다:
#  - FULL_ACCESS(사용자가 명시적으로 허용)  → auto-pilot: high-risk 도구 자동 승인
#  - READ_ONLY(읽기 전용)                   → balanced: high-risk 도구는 ASK(prompt)
# 별도 승인 workflow가 없는 동기 API이므로 ASK는 실행 없이 403을 반환한다
# (allow로 승격하지 않는다). DENY도 실행 0회다.
_PERMISSION_MODE_BY_ACCESS_MODE: dict[AccessMode, str] = {
    AccessMode.FULL_ACCESS: "auto-pilot",
    AccessMode.READ_ONLY: "balanced",
}
_SHELL_TOOL_NAME = "run_bash_command"


def _permission_mode() -> str:
    """현재 요청의 기존 권한 모드 → PermissionGate 모드."""
    return _PERMISSION_MODE_BY_ACCESS_MODE.get(get_access_mode(), "balanced")


def _shell_request_root(req: "ShellRunRequest", request: Request) -> str:
    """셸 실행 root를 요청 시작 시점에 1회 확정한다(재조회·재바인딩 없음).

    우선순위:
    1. 이미 바인딩된 ARC-01 요청 실행 컨텍스트(chat/task가 실행한 경우)
    2. 클라이언트가 명시한 ``project_id``(ARC-01 resolution)
    3. ``X-AGK-Session-Id``로 명시된 session active-project binding
    4. 그 외 구형 클라이언트는 서버 기본 root(기존 동작)

    """
    from antigravity_k.api.project_binding import (
        SESSION_ID_HEADER,
        get_request_project_root,
        get_session_active_project,
        resolve_project_execution_context,
    )
    from antigravity_k.engine.project_registry import get_project_registry

    bound = get_request_project_root()
    if bound:
        return os.path.realpath(bound)

    project_id = (req.project_id or "").strip()
    if not project_id:
        header_session = request.headers.get(SESSION_ID_HEADER)
        binding = get_session_active_project(header_session) if header_session else None
        if binding is None:
            return os.path.realpath(str(config.paths.project_root))
        project_id = binding.project_id

    context = resolve_project_execution_context(
        payload=None,
        project_id=project_id,
        registry=get_project_registry(),
        bind=False,
    )
    return os.path.realpath(context.canonical_project_root)


def _permission_gate(root: str | None = None) -> PermissionGate:
    return PermissionGate(project_root=root or str(config.paths.project_root), mode=_permission_mode())


def _decide_shell_permission(*, root: str, command: str, cwd: str) -> PermissionDecision:
    """셸 실행 전 권한 결정 — 검사 경로와 실행 경로를 같은 root로 고정한다."""
    return _permission_gate(root).decide(
        ToolInvocation(
            ToolSpec(name=_SHELL_TOOL_NAME, risk_level="high", category="api"),
            {"command": command, "cwd": cwd},
        ),
    )


def _enforce_shell_permission(*, root: str, command: str, cwd: str) -> None:
    """ASK/DENY는 실행 0회로 끝낸다. 승인 workflow 없이 allow로 승격하지 않는다."""
    # 실행 모드(Plan/Build/Interactive)가 도구를 막으면 권한 gate 이전에 거부한다.
    from antigravity_k.api.dependencies import get_mode_manager

    execution_mode = get_mode_manager().current_mode
    if not execution_mode.tool_is_allowed(_SHELL_TOOL_NAME):
        raise ShellPolicyDeniedError(
            detail=execution_mode.get_block_reason(_SHELL_TOOL_NAME),
            context={"tool": _SHELL_TOOL_NAME, "execution_mode": execution_mode.value},
        )

    decision = _decide_shell_permission(root=root, command=command, cwd=cwd)
    access_mode = get_access_mode().value
    if decision.permission is Permission.PROMPT:
        raise ShellApprovalRequiredError(
            detail=(
                "Shell execution requires explicit approval in the current permission mode "
                "(ASK); no approval workflow is attached to this endpoint"
            ),
            context={"tool": _SHELL_TOOL_NAME, "access_mode": access_mode, "permission_mode": _permission_mode()},
        )
    if decision.permission is not Permission.ALLOW:
        raise ShellPolicyDeniedError(
            detail="Shell execution was denied by policy (DENY)",
            context={"tool": _SHELL_TOOL_NAME, "access_mode": access_mode, "reason": decision.reason},
        )


def _require_allowed(tool_name: str, args: dict[str, object], risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for {tool_name}: {decision.permission.value}",
        )


def _resolve_project_cwd(cwd: str | None, *, root: str | None = None) -> str:
    project_root = Path(root or config.paths.project_root).resolve()
    candidate = (project_root if not cwd else Path(cwd).expanduser()).resolve()
    try:
        _ = candidate.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Working directory must remain inside the project root") from exc
    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail="Working directory does not exist")
    return str(candidate)


def _resolve_project_path(path: str) -> str:
    project_root = Path(config.paths.project_root).resolve()
    raw_path = Path(path).expanduser()
    candidate = (raw_path if raw_path.is_absolute() else project_root / raw_path).resolve()
    try:
        _ = candidate.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="File path must remain inside the project root") from exc
    return str(candidate)


class FileReadRequest(BaseModel):
    """Filereadrequest.

    Bases: BaseModel
    """

    path: str


class FileWriteRequest(BaseModel):
    """Filewriterequest.

    Bases: BaseModel
    """

    path: str
    content: str
    overwrite: bool = False


class ShellRunRequest(BaseModel):
    """Shellrunrequest.

    Bases: BaseModel
    """

    command: str
    cwd: str | None = None
    timeout: int = 30
    # CR-04: ARC-01 프로젝트를 명시한 요청은 그 프로젝트 root에서만 실행한다.
    project_id: str | None = None


@router.post("/api/agent/tools/fs/read")
def read_file(req: FileReadRequest):
    """지정된 파일의 내용을 읽어옵니다."""
    path = _resolve_project_path(req.path)
    _require_allowed("read_file", {"path": path}, "safe")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(path, encoding="utf-8") as f:
            return {"ok": True, "content": f.read()}
    except (OSError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/agent/tools/fs/write")
def write_file(req: FileWriteRequest):
    """파일을 생성하거나 덮어씁니다."""
    path = _resolve_project_path(req.path)
    _require_allowed("write_file", {"path": path}, "medium")
    if os.path.exists(path) and not req.overwrite:
        raise HTTPException(status_code=400, detail="File exists, use overwrite=True")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            _ = f.write(req.content)
        return {"ok": True, "path": path}
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/agent/tools/shell/run")
def run_shell(req: ShellRunRequest, request: Request):
    """터미널 명령을 OS 샌드박스에서 실행합니다 (CR-04 실행·승인 경계).

    실행 권한 모드(전체 액세스/읽기 전용)와 요청 root는 요청 시작 시점에 확정한다.
    - ASK → 실행 없이 403 ``shell_approval_required``
    - DENY → 실행 0회, 403 ``shell_policy_denied``
    - ALLOW → CR-03 제한 읽기 + 최소 env의 sandbox 실행(폴백 없음)
    """
    root = _shell_request_root(req, request)
    cwd = _resolve_project_cwd(req.cwd, root=root)
    _enforce_shell_permission(root=root, command=req.command, cwd=cwd)
    timeout = max(1, min(req.timeout, int(config.security.max_execution_time)))
    try:
        runner = SandboxRunner(
            project_root=root,
            enabled=bool(config.security.sandbox_enabled),
            network=str(config.security.sandbox_network),
            timeout=timeout,
            max_output_bytes=int(config.security.max_output_bytes),
            max_memory_mb=int(config.security.max_memory_mb),
            max_processes=int(config.security.max_processes),
            # CR-03 경계 재사용: 민감 트리 deny + 작업 디렉토리/런타임만 재허용.
            restrict_reads=True,
            # 설정으로 꺼졌거나 backend가 없으면 raw host 실행으로 대체하지 않는다.
            require_sandbox=True,
            read_allow_paths=[cwd, *_python_runtime_read_paths()],
        )
        result = runner.execute(
            req.command,
            timeout=timeout,
            # 부모 os.environ(모델 provider 키·서버 PIN/token secret) 상속 금지.
            env=_minimal_child_env(cwd),
            cwd=cwd,
        )
        if result.timed_out:
            raise ShellTimeoutError(
                detail=f"Shell command exceeded the {timeout}s execution time limit",
                context={"tool": _SHELL_TOOL_NAME, "timeout_seconds": timeout},
            )
        if result.error:
            # 내부 오류 문자열(경로·환경)은 응답에 넣지 않고 로그에만 남긴다.
            logger.warning("sandboxed shell failed to start: %s", result.error)
            raise ShellSandboxUnavailableError(
                detail=(
                    "OS sandbox could not run this command; raw host execution is disabled. "
                    "Check security.sandbox_enabled and the sandbox backend."
                ),
                context={"tool": _SHELL_TOOL_NAME},
            )
        return {
            "ok": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.return_code,
            "sandboxed": result.sandboxed,
            "output_truncated": result.output_truncated,
            "timed_out": result.timed_out,
        }
    except (ShellApprovalRequiredError, ShellPolicyDeniedError, ShellSandboxUnavailableError, ShellTimeoutError):
        raise
    except (OSError, ValueError) as e:
        # 실행 환경 전체(경로·env)를 노출하지 않는다.
        logger.warning("shell execution failed: %s", e)
        raise HTTPException(status_code=500, detail="Shell execution failed") from e


class BrowserActionRequest(BaseModel):
    """Browseractionrequest.

    Bases: BaseModel
    """

    action: str  # "launch", "goto", "click", "type", "snapshot", "close", "observe", "act"
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    # 관찰/행동 계약(task 17): ref 는 직전 관찰이 발급한 opaque 핸들이다.
    ref: str | None = None
    value: str | None = None
    path: str | None = None
    delta: int = 800
    screenshot: bool = False
    # 승인 계약(task 18): 토큰은 **서버가** 발급한 것만 통하고, 비밀은 handle 로만 가리킨다.
    approval_token: str | None = None
    secret_ref: str | None = None


async def _browser_observe(request: Request, state: BrowserSessionState, *, screenshot: bool) -> "Observation":
    from antigravity_k.tools.browser_observation import BrowserObservationError

    observer = _browser_observer(request, state, with_sandbox=False)
    try:
        return await observer.observe(screenshot=screenshot)
    except BrowserObservationError as exc:
        raise HTTPException(status_code=_observation_status(exc.code), detail=exc.to_dict()) from exc


# ── 브라우저 효과의 위험도·승인(task 18) ─────────────────────────────────────
# 승인 요청을 등록할 도구 이름. `browser_action` 을 쓰지 **않는다** — 일반 도구 승인에서 한 번
# "항상 허용" 을 받으면 그것이 브라우저 효과를 통째로 자동 승인해 버리기 때문이다. 이 이름이
# "항상 허용" 목록에 들어 있으면 실행하지 않고 거절한다(무조건 자동 승인 금지).
_BROWSER_EFFECT_TOOL = "browser_effect"

_APPROVAL_HTTP_STATUS = {
    APPROVAL_REQUIRED: 428,
    MODEL_TOKEN_REFUSED: 403,
    MODEL_CLAIM_REFUSED: 400,
    APPROVAL_REJECTED: 403,
    ALWAYS_ALLOW_FORBIDDEN: 403,
    APPROVAL_REPLAYED: 409,
    APPROVAL_EXPIRED: 410,
    APPROVAL_BINDING_CHANGED: 409,
    SECRET_VALUE_NOT_ALLOWED: 400,
    SECRET_HANDLE_UNKNOWN: 403,
    SECRET_ORIGIN_MISMATCH: 403,
}


def _approval_status(code: str) -> int:
    return _APPROVAL_HTTP_STATUS.get(code, 403)


def _payload_value(req: BrowserActionRequest, *, secret_field: bool, action: str) -> tuple[str | None, str]:
    """승인 지문에 쓸 값. 비밀 필드는 **handle 만** 넘긴다(평문은 어느 필드로 와도 거절한다)."""
    carried = req.value or req.text
    if secret_field and carried:
        raise HTTPException(
            status_code=400,
            detail=BrowserApprovalError(
                SECRET_VALUE_NOT_ALLOWED,
                "a secret field is filled from a stored handle (secret_ref), never from a value the model carries",
            ).to_dict(),
        )
    if req.secret_ref:
        return req.secret_ref, "secret_handle"
    if action == "select":
        return req.value, "text"
    return req.text, "text"


# ref 가 있어야만 성립하는 행동. ref 가 현재 관찰의 것이 아니면 **승인을 묻지 않는다** —
# 계약이 STALE_SNAPSHOT/UNKNOWN_REF 로 거절하는 것이 맞는 답이고, 엉뚱한 승인 창을 띄우면
# 사용자가 무엇을 승인하는지 알 수 없다.
_REF_ACTIONS: frozenset[str] = frozenset({"click", "fill", "select", "upload", "download"})


async def _screen_browser_effect(
    req: BrowserActionRequest,
    request: Request,
    observer: "BrowserObserver",
    action: str,
) -> dict[str, object]:
    """행동 직전 **서버가** 효과를 분류하고, 필요하면 사람의 승인을 요구하거나 소비한다.

    반환값은 판정 재료(분류 결과·바인딩)·소비 사실이다. 승인이 필요 없으면 분류만 돌려준다 —
    자동으로 지나가는 효과가 무엇인지 응답에 드러내기 위해서다.
    """
    fact = observer.element_fact(req.ref)
    if fact is None:
        if action in _REF_ACTIONS:
            return {
                "effect": {
                    "effect": "unknown",
                    "requires_approval": False,
                    "reason": "this ref is not part of the current observation: the action contract decides",
                }
            }
        fact = observer.page_fact()
    secret_field = bool(fact.get("secret"))
    payload_value, value_kind = _payload_value(req, secret_field=secret_field, action=action)
    target_url = str(req.url or "") if action == "goto" else str(fact.get("url") or "")
    page_url = str(fact.get("url") or "")
    decision = classify_effect(
        action,
        role=str(fact.get("role") or ""),
        name=str(fact.get("name") or ""),
        tag=str(fact.get("tag") or ""),
        url=target_url,
        text=req.text,
        value=payload_value,
        path=req.path,
        secret=secret_field or bool(req.secret_ref),
        disabled=bool(fact.get("disabled")),
        eager=bool(fact.get("eager")),
    )
    result: dict[str, object] = {"effect": decision.to_dict()}
    binding = ApprovalBinding(
        owner_key=_browser_owner(request).key,
        session_tag=observer.session_tag,
        origin=origin_of(target_url) if action == "goto" else origin_of(page_url),
        action=action,
        ref=str(req.ref or ""),
        payload_hash=payload_fingerprint(
            action=action,
            url=req.url,
            text=req.text,
            value=payload_value,
            path=req.path,
            delta=req.delta,
            value_kind=value_kind,
        ),
        generation=int(cast("int", fact.get("generation") or 0)) or observer.generation,
        effect=decision.effect.value,
    )
    result["binding"] = binding.to_dict()
    if not decision.requires_approval:
        return result

    gate = get_browser_approval_gate()
    if req.approval_token:
        try:
            ticket = gate.authorize(req.approval_token, binding)
        except BrowserApprovalError as exc:
            raise HTTPException(status_code=_approval_status(exc.code), detail=exc.to_dict()) from exc
        result["approval"] = {"consumed": True, "ticket_id": ticket.ticket_id, "action": action}
        return result

    vault = get_browser_secret_vault()
    summary = summarize_effect(
        decision,
        action=action,
        origin=binding.origin,
        name=str(fact.get("name") or ""),
        role=str(fact.get("role") or ""),
        text=req.text,
        value=req.value,
        value_kind=value_kind,
        secret_name=vault.name_of(req.secret_ref or ""),
    )
    manager_request = get_approval_manager().request_approval(
        tool_name=_BROWSER_EFFECT_TOOL,
        tool_args={
            "origin": binding.origin,
            "action": action,
            "effect": decision.effect.value,
            "risk": decision.risk,
            "binding": binding.fingerprint[:16],
        },
        risk_level=decision.risk,
        description=summary,
    )
    if manager_request.status is not ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=403,
            detail=BrowserApprovalError(
                ALWAYS_ALLOW_FORBIDDEN,
                "this effect needs its own approval: 'always allow' is not accepted for browser effects",
                details={"status": manager_request.status.value},
            ).to_dict(),
        )
    requirement = gate.register(binding, decision, summary=summary, request_id=manager_request.request_id)
    raise HTTPException(
        status_code=428,
        detail={
            "error_code": APPROVAL_REQUIRED,
            "status": "approval_required",
            "requirement": requirement.to_dict(),
            "grant_url": f"/api/agent/tools/browser/approval/{requirement.request_id}/grant",
        },
    )


async def _handoff_or_none(state: BrowserSessionState) -> dict[str, object] | None:
    """MFA·CAPTCHA 면 사람 차례다 — 행동을 수행하지 않고 그 사실을 그대로 알린다."""
    if state.page is None:
        return None
    signal = await detect_user_handoff(state.page)
    if signal is None:
        return None
    return {**signal.to_dict(), "error_code": "HANDOFF_REQUIRED"}


async def _browser_contract_action(
    req: BrowserActionRequest,
    request: Request,
    state: BrowserSessionState,
) -> dict[str, object]:
    """task 17 의 관찰/행동 계약 경로. selector·임의 JS 는 여기 없다(계약에 문이 없다)."""
    from antigravity_k.tools.browser_observation import (
        ALLOWED_ACTIONS,
        FORBIDDEN_ACTIONS,
        BrowserObservationError,
    )

    if req.action in FORBIDDEN_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action {req.action!r} is not exposed by the browser contract",
        )
    action = _CONTRACT_ACTION_ALIASES.get(req.action, req.action)
    if action == "observe":
        observation = await _browser_observe(request, state, screenshot=req.screenshot)
        payload: dict[str, object] = {
            "ok": True,
            "observation": observation.to_dict(),
            "summary": observation.to_summary(),
        }
        # 관찰은 막지 않는다(사람이 화면을 봐야 한다) — 다만 **사람 차례**라는 사실을 같이 알린다.
        handoff = await _handoff_or_none(state)
        if handoff is not None:
            payload["handoff"] = handoff
        return payload
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    observer = _browser_observer(request, state, with_sandbox=True)
    # 사람이 해야 하는 단계면 여기서 멈춘다(자동 재시도·자동 승인 없음).
    handoff = await _handoff_or_none(state)
    if handoff is not None and action not in {"goto", "scroll"}:
        raise HTTPException(status_code=409, detail=handoff)
    screening = await _screen_browser_effect(req, request, observer, action)

    # 비밀은 **여기서만** 값이 된다. 승인된 뒤에 꺼내므로, 승인되지 않은 호출은 보관소를 건드리지도
    # 않는다. 해석은 서버가 하고 모델에게는 handle 조차 응답으로 돌아가지 않는다.
    act_text = req.text
    if action == "fill" and req.secret_ref:
        vault = get_browser_secret_vault()
        fact = observer.element_fact(req.ref) or observer.page_fact()
        try:
            act_text, _grant = vault.resolve(
                req.secret_ref,
                owner_key=_browser_owner(request).key,
                origin=origin_of(str(fact.get("url") or "")),
            )
        except BrowserApprovalError as exc:
            raise HTTPException(status_code=_approval_status(exc.code), detail=exc.to_dict()) from exc

    try:
        result = await observer.act(
            action,
            ref=req.ref,
            url=req.url,
            text=act_text,
            value=req.value,
            path=req.path,
            delta=req.delta,
        )
    except BrowserObservationError as exc:
        raise HTTPException(status_code=_observation_status(exc.code), detail=exc.to_dict()) from exc
    result_payload = result.to_dict()
    return {
        "ok": True,
        "result": result_payload,
        "summary": f"{result_payload['action']}: {result_payload['detail']}",
        **screening,
    }


async def _reject_model_claims(request: Request) -> None:
    """본문에 "안전하다/승인됐다"는 주장이 있으면 거절한다(task 18).

    위험도는 **서버가** 요소의 의미로 판정하고 사람이 승인한다. 호출자가 `risk`/`approved` 같은
    필드로 그 판정을 낮출 수 있으면 판정이 의미를 잃는다 — 그래서 "무시" 가 아니라 **거절**이다
    (`ignore` 는 조용한 통과를 만들고, 통과는 승인 UI 에 아무것도 남기지 않는다).
    """
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001 - 본문이 없거나 JSON 이 아니면 주장할 것도 없다
        return
    if not isinstance(raw, Mapping):
        return
    try:
        guard_request_claims(cast("Mapping[str, object]", raw))
    except BrowserApprovalError as exc:
        raise HTTPException(status_code=_approval_status(exc.code), detail=exc.to_dict()) from exc


@router.post("/api/agent/tools/browser/action")
async def browser_action(req: BrowserActionRequest, request: Request):
    """Playwright 기반 브라우저 자동화 엔진 API."""
    await _reject_model_claims(request)
    risk_level = "safe" if req.action in {"snapshot", "console_errors", "observe"} else "medium"
    if req.action == "goto":
        risk_level = "high"
    _require_allowed(
        "browser_action",
        {"action": req.action, "url": req.url, "selector": req.selector, "ref": req.ref},
        risk_level,
    )
    session_id, state = _browser_state_for(request)
    try:
        from playwright.async_api import Error, async_playwright
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Browser automation is unavailable; install the dev dependency group to enable Playwright.",
        ) from exc
    try:
        if req.action == "launch":
            owner = _browser_owner(request)
            session_owner = get_browser_session_owner()
            try:
                reservation = session_owner.begin(owner, purpose="api browser action")
            except BrowserSessionLimitError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except BrowserSessionRefusedError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            if reservation.is_reuse and state.page is None:
                reuse = reservation.reuse
                assert reuse is not None
                state.page = cast("_AsyncPage", reuse.page)
                return {"ok": True, "message": "Reusing the owner's existing browser session"}
            if not state.playwright:
                state.playwright = await async_playwright().start()
            assert state.playwright is not None
            if not state.browser:
                state.browser = await state.playwright.chromium.launch(
                    headless=True,
                )
                browser = state.browser
                assert browser is not None
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                )
                state.context = context
                _ = await context.route("**/*", _guard_browser_route)
                # 개인 Chrome·CDP 가 이미 열어 둔 페이지는 **채택하지 않는다**(관찰만).
                _ = session_owner.remember_foreign_pages(list(getattr(context, "pages", []) or []))
                page = await context.new_page()
                state.page = page
                # Console error/log auto-collection
                state.console_errors = []
                state.console_logs = []
                page.on(
                    "console",
                    lambda msg: (
                        _append_console_entry(state.console_errors, {"type": msg.type, "text": msg.text})
                        if msg.type in ("error", "warning")
                        else _append_console_entry(state.console_logs, {"type": msg.type, "text": msg.text})
                    ),
                )
            # 예약을 실제 세션으로 확정한다 — 안 하면 자리만 차지한 예약이 남는다(그리고 소유자는
            # 이 세션을 모른다). close 콜백을 넘겨서 유휴/deadline 회수도 같은 경로로 닫히게 한다.
            if state.page is not None:
                _ = session_owner.commit(reservation, page=state.page, close=_api_session_closer(state))
            return {"ok": True, "message": "Browser launched with console capture"}

        elif req.action == "close":
            if state.browser:
                await state.browser.close()
                state.browser = None
                state.context = None
                state.page = None
            if state.playwright:
                await state.playwright.stop()
                state.playwright = None
            # 소유자 원장에서도 뺀다 — 안 빼면 다음 launch 가 "이미 너 세션이 있다"고 잘못 답한다.
            _ = get_browser_session_owner().release(_browser_owner(request))
            if session_id != "default":
                _ = browser_sessions.discard(session_id)
            return {"ok": True, "message": "Browser closed"}

        # For remaining actions, ensure page exists
        if not state.page:
            raise HTTPException(
                status_code=400,
                detail="Browser is not launched. Call 'launch' first.",
            )

        if req.action == "snapshot":
            # 스냅숏도 **관찰**이다(task 17) — 그래야 비밀 필드 마스킹을 같은 코드가 지킨다.
            # 예전 구현은 마스킹 없는 스크린샷을 그대로 돌려줬다.
            observation = await _browser_observe(request, state, screenshot=True)
            snapshot_payload: dict[str, object] = {
                "ok": True,
                "screenshot_base64": observation.screenshot,
                "accessibility_tree": observation.accessibility,
                "refs": [item.to_dict() for item in observation.refs],
                "snapshot_id": observation.snapshot_id,
                "generation": observation.generation,
                "screenshot_masked": observation.screenshot_masked,
                "masked_regions": observation.masked_regions,
                "console_errors": state.console_errors[-20:],
                "console_logs_count": len(state.console_logs),
                "url": observation.url,
            }
            handoff = await _handoff_or_none(state)
            if handoff is not None:
                snapshot_payload["handoff"] = handoff
            return snapshot_payload

        if req.action in _BROWSER_CONTRACT_ACTIONS:
            return await _browser_contract_action(req, request, state)

        if req.action == "console_errors":
            return {
                "ok": True,
                "errors": state.console_errors,
                "total": len(state.console_errors),
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    except HTTPException:
        raise
    except (Error, OSError, TimeoutError) as e:
        raise HTTPException(status_code=_browser_error_status(e), detail=str(e))


# ─── 브라우저 효과 승인·비밀 handle(task 18) ────────────────────
@router.get("/api/agent/tools/browser/approval/pending")
async def list_browser_approvals() -> dict[str, object]:
    """대기 중인 브라우저 효과 승인. **서버가 발급한** 요청만 나온다(모델이 만든 것은 없다)."""
    gate = get_browser_approval_gate()
    pending = gate.list_pending()
    return {"pending": [item.to_dict() for item in pending], "count": len(pending), "gate": gate.describe()}


@router.post("/api/agent/tools/browser/approval/{request_id}/grant")
async def grant_browser_approval(request_id: str, request: Request) -> dict[str, object]:
    """사람이 승인한 요청에 **서버가** 일회용 토큰을 발급한다.

    토큰은 사람의 해결(ApprovalManager 의 승인 상태)에만 묶여 나온다 — 승인되지 않은 요청에는
    아무것도 발급되지 않고, 한 번 발급된 토큰은 그 행동에 한 번만 쓸 수 있다.
    """
    gate = get_browser_approval_gate()
    requirement = gate.pending(request_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="unknown or already used browser approval request")
    manager_request = get_approval_manager().get_request(request_id)
    if manager_request is None:
        raise HTTPException(status_code=404, detail="unknown browser approval request")
    if manager_request.status is not ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": APPROVAL_REJECTED,
                "status": manager_request.status.value,
                "detail": "the browser effect is not approved yet",
            },
        )
    # 발급은 **지금의 상태**로 한다 — 사람이 보고 누른 사이에 페이지가 바뀌었으면(주소·DOM)
    # 발급 자체가 거절되어 다시 물어보게 된다(승인한 것과 실행될 것이 달라지지 않게).
    current = _live_state_binding(requirement.binding, request)
    resolution = HumanResolution(
        request_id=request_id,
        decision="approve",
        resolved_at=manager_request.resolved_at or time.time(),
    )
    try:
        ticket = gate.issue(current, resolution)
    except BrowserApprovalError as exc:
        raise HTTPException(status_code=_approval_status(exc.code), detail=exc.to_dict()) from exc
    return {"ok": True, "ticket": ticket.to_dict(include_token=True), "summary": requirement.summary}


@router.post("/api/agent/tools/browser/approval/{request_id}/withdraw")
async def withdraw_browser_approval(request_id: str) -> dict[str, object]:
    """사람이 거절했거나 끝난 요청을 대기 목록에서 뺀다.

    거절의 **기록**은 ApprovalManager 가 갖는다(그 경로가 감사 대상이다). 여기서는 발급되지
    않은 승인이 TTL(60초)까지 화면에 남아 사용자에게 되묻는 일만 막는다.
    """
    withdrawn = get_browser_approval_gate().withdraw(request_id)
    return {"ok": True, "request_id": request_id, "withdrawn": withdrawn}


def _live_state_binding(recorded: ApprovalBinding, request: Request) -> ApprovalBinding:
    """승인 기록에서 **동일성 축**은 그대로 두고 상태 축(origin·generation)만 지금 것으로 바꾼다.

    요청자가 다른 사용자면 여기서 거절한다 — 남의 승인 창을 자기 것으로 바꿔 발급받는 길을 막는다.
    """
    owner = _browser_owner(request)
    if owner.key != recorded.owner_key:
        raise HTTPException(
            status_code=403,
            detail=BrowserApprovalError(
                APPROVAL_BINDING_CHANGED,
                "this approval belongs to a different user session",
                details={"changed": ["owner_key"]},
            ).to_dict(),
        )
    state = browser_sessions.get(_browser_session_id(request))
    page_url = str(getattr(state.page, "url", "") or "")
    observer = _browser_observer(request, state, with_sandbox=False)
    return ApprovalBinding(
        owner_key=owner.key,
        session_tag=observer.session_tag,
        origin=recorded.origin if recorded.action == "goto" else origin_of(page_url),
        action=recorded.action,
        ref=recorded.ref,
        payload_hash=recorded.payload_hash,
        generation=observer.generation,
        effect=recorded.effect,
    )


class BrowserSecretStoreRequest(BaseModel):
    """운영자가 비밀을 넣는 요청. 응답에는 handle 만 나가고 **값은 다시 나오지 않는다**."""

    name: str
    value: str
    origins: list[str] = Field(default_factory=list)


@router.post("/api/agent/tools/browser/secrets")
async def store_browser_secret(req: BrowserSecretStoreRequest, request: Request) -> dict[str, object]:
    """비밀을 넣고 opaque handle 을 받는다(로그인은 이 handle 로만 지정된다)."""
    _require_allowed("browser_secret_store", {"name": req.name}, "high")
    vault = get_browser_secret_vault()
    handle = vault.put(
        req.name,
        req.value,
        owner_key=_browser_owner(request).key,
        origins=req.origins,
    )
    return {"ok": True, "handle": handle, "name": req.name, "origins": list(req.origins)}


@router.get("/api/agent/tools/browser/secrets")
async def list_browser_secrets(request: Request) -> dict[str, object]:
    """보관된 비밀의 **이름·handle·origin 핀** 만 준다(값은 어느 경로로도 나오지 않는다)."""
    _require_allowed("browser_secret_store", {"name": "list"}, "safe")
    secrets = get_browser_secret_vault().describe_for_owner(_browser_owner(request).key)
    return {"secrets": secrets, "count": len(secrets)}


@router.delete("/api/agent/tools/browser/secrets/{handle}")
async def discard_browser_secret(handle: str, request: Request) -> dict[str, object]:
    """비밀을 버린다. handle 은 owner 에 묶여 있어 남의 것을 지울 수 없다."""
    _require_allowed("browser_secret_store", {"name": "discard"}, "high")
    vault = get_browser_secret_vault()
    if not vault.owned_by(handle, _browser_owner(request).key):
        raise HTTPException(
            status_code=403,
            detail=BrowserApprovalError(
                SECRET_HANDLE_UNKNOWN, "this secret handle is unknown or belongs to a different user session"
            ).to_dict(),
        )
    _ = vault.discard(handle)
    return {"ok": True, "handle": handle, "discarded": True}


# ─── Accessibility Tree Flattener ─────────────────────────────
def _flatten_a11y_tree(node: Mapping[str, object], depth: int = 0) -> str:
    """Playwright의 Accessibility Tree를 LLM이 이해할 수 있는.

    컴팩트한 텍스트 표현으로 변환합니다.

    예시 출력:
      [button] "Send" focused
        [img] "send icon"
      [textbox] "채팅 입력" value="hello"
    """
    lines: list[str] = []
    role = _as_text(node.get("role"), "unknown")
    name = _as_text(node.get("name"))
    value = _as_text(node.get("value"))
    focused = " focused" if node.get("focused") else ""
    checked = " checked" if node.get("checked") else ""
    disabled = " disabled" if node.get("disabled") else ""

    indent = "  " * depth
    label = f"[{role}]"
    if name:
        label += f' "{name}"'
    if value:
        label += f' value="{value[:50]}"'
    label += focused + checked + disabled

    lines.append(f"{indent}{label}")

    children = node.get("children", [])
    if isinstance(children, list):
        for child in cast(list[object], children):
            if isinstance(child, Mapping):
                lines.extend(_flatten_a11y_tree(cast(Mapping[str, object], child), depth + 1).split("\n"))

    return "\n".join(lines)


# ─── Self-Test Orchestration ──────────────────────────────────
class BrowserSelfTestRequest(BaseModel):
    """Browserselftestrequest.

    Bases: BaseModel
    """

    scope: str = "all"
    base_url: str | None = None
    dashboard_url: str | None = None
    ws_url: str | None = None


_DEFAULT_BROWSER_SELF_TEST_REQUEST = BrowserSelfTestRequest()


@router.post("/api/agent/tools/browser/self-test")
async def browser_self_test(
    request: Request,
    req: Annotated[BrowserSelfTestRequest, Body()] = _DEFAULT_BROWSER_SELF_TEST_REQUEST,
):
    """기존 TestHarness 프레임워크를 활용하여.

    Ssak-Ai가 스스로를 테스트하는 멀티스텝 오케스트레이션 루프.

    실행 흐름:
    1. TestHarness가 API 테스트 실행 (health, models)
    2. Playwright로 UI 테스트 실행 (dashboard, chat, explorer)
    3. Self-Healing Loop 적용 (실패 시 자동 재시도)
    4. 결과를 마크다운 리포트로 반환
    """
    try:
        from antigravity_k.engine.harness import TestHarness

        request_base_url = str(request.base_url).rstrip("/")
        base_url = req.base_url or request_base_url
        harness = TestHarness(
            base_url=base_url,
            dashboard_url=req.dashboard_url or base_url,
            ws_url=req.ws_url,
        )
        use_browser = req.scope not in ("api", "api_only")
        report = await harness.run_all(use_browser=use_browser)
        return {
            "ok": True,
            "report": report.to_dict(),
            "markdown": report.to_markdown(),
            "feedback": ("✅ 모든 테스트 통과" if report.failed == 0 else f"⚠️ {report.failed}개 테스트 실패"),
            "trend": harness.feedback.get_trend(),
        }
    except HTTPException:
        raise
    except (ImportError, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Autonomous QA Full Loop ─────────────────────────────────
class AutonomousQARequest(BaseModel):
    """Autonomousqarequest.

    Bases: BaseModel
    """

    url: str = "http://localhost:5173"
    max_iterations: int = Field(default=3, ge=1, le=10)
    vision_model: str = "qwen3.6:latest"
    coding_model: str = "qwen3.6:latest"


@router.post("/api/agent/tools/browser/autonomous-qa")
async def autonomous_qa_loop(req: AutonomousQARequest):
    """완전 자율 QA 루프: 비전 분석 → 코드 수정 → 자동 적용 → 재테스트 → 검증.

    이 엔드포인트가 호출되면:
    1. Playwright로 대시보드 스크린샷 촬영
    2. qwen3.6:latest가 UI 결함 분석
    3. qwen3.6:latest가 코드 수정 패치 생성
    4. 패치 자동 적용 → 리로드 → 재분석
    5. 결함 해소 확인될 때까지 최대 N회 반복
    6. 반응형 테스트(desktop/tablet/mobile) + 성능 메트릭 수집
    """
    try:
        _ = validate_egress_url(req.url, allow_local=True)
    except EgressPolicyError as exc:
        raise HTTPException(status_code=403, detail="Autonomous QA target must be a valid HTTP(S) URL") from exc
    _require_allowed("autonomous_qa", {"url": req.url}, "critical")
    try:
        from antigravity_k.api.dependencies import get_model_manager
        from antigravity_k.engine.autonomous_qa import AutonomousQAEngine

        engine = AutonomousQAEngine(
            dashboard_url=req.url,
            vision_model=req.vision_model,
            coding_model=req.coding_model,
            max_iterations=req.max_iterations,
            model_manager=get_model_manager(),
        )
        report = await engine.run_full_loop(req.url)
        return {
            "ok": True,
            "report": report.to_dict(),
            "markdown": report.to_markdown(),
        }
    except HTTPException:
        raise
    except (ImportError, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Vision Analysis (멀티모달 LLM 연동) ─────────────────────
class VisionAnalyzeRequest(BaseModel):
    """Visionanalyzerequest.

    Bases: BaseModel
    """

    screenshot_base64: str | None = None
    prompt: str = "이 UI 스크린샷을 분석하세요. 레이아웃 문제, 겹침, 잘림, 정렬 오류가 있으면 모두 지적하고 수정 방법을 제안하세요."  # noqa: E501
    model: str = "qwen3.6:latest"


@router.post("/api/agent/tools/browser/vision-analyze")
async def vision_analyze(req: VisionAnalyzeRequest, request: Request):
    """멀티모달 비전 LLM을 활용한 UI 스크린샷 자동 분석.

    1. screenshot_base64가 없으면 현재 브라우저에서 자동 캡처
    2. 비전 모델(qwen3.6:latest)에 이미지+프롬프트 전달
    3. UI 결함 분석 결과 반환
    """
    import httpx

    try:
        _, state = _browser_state_for(request)
        # 스크린샷 자동 캡처 (없으면)
        screenshot_b64 = req.screenshot_base64
        if not screenshot_b64 and state.page:
            try:
                screenshot_bytes = await state.page.screenshot()
            except ModuleNotFoundError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Browser capture is unavailable; install the dev dependency group to enable Playwright.",
                ) from exc
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        if not screenshot_b64:
            raise HTTPException(
                status_code=400,
                detail="No screenshot available. Launch browser and navigate first, or provide screenshot_base64.",
            )

        from antigravity_k.api.dependencies import get_model_manager

        model_manager = get_model_manager()
        target = req.model
        if target == "qwen3.6:latest":
            target = model_manager.get_target_for_role("vision", default_role="vision")
        try:
            analysis = await asyncio.to_thread(
                model_manager.generate,
                req.prompt,
                target=target,
                raw_messages=[
                    {"role": "user", "content": req.prompt, "images": [screenshot_b64]},
                ],
                max_tokens=2048,
                temperature=0.2,
            )
            if analysis.strip():
                return {"ok": True, "model": target, "analysis": analysis}
        except Exception:
            logger.warning("Managed vision route failed, HTTP fallback", exc_info=True)

        # Ollama 멀티모달 API 호출
        async with httpx.AsyncClient(
            timeout=120.0,
            event_hooks={"request": [validate_httpx_request_async]},
        ) as client:
            response = await client.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": req.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": req.prompt,
                            "images": [screenshot_b64],
                        },
                    ],
                    "stream": False,
                },
            )

            if response.status_code == 200:
                data = _as_mapping(cast(object, response.json()))
                analysis = _as_text(_as_mapping(data.get("message")).get("content"), "분석 결과 없음")
                return {
                    "ok": True,
                    "model": req.model,
                    "analysis": analysis,
                }
            else:
                return {
                    "ok": False,
                    "error": f"Ollama returned {response.status_code}: {response.text}",
                }

    except HTTPException:
        raise
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Response parse error: {e}")


# ─── External Brain (외부 AI 두뇌 간접 연동) ─────────────────
class ExternalBrainRequest(BaseModel):
    """Externalbrainrequest.

    Bases: BaseModel
    """

    prompt: str
    target: str = ""  # "gemini_app", "chatgpt_web", "gemini_web", or "" for auto
    strategy: str = "fallback"  # "fallback", "round-robin", "compare"


@router.get("/api/agent/tools/external-brain/list")
async def external_brain_list():
    """사용 가능한 외부 AI 두뇌 목록을 반환합니다."""
    _require_allowed("external_brain_list", {}, "safe")
    from antigravity_k.engine.external_brain import ExternalBrainRouter

    router_instance = ExternalBrainRouter()
    brains = await router_instance.list_available()
    return {"ok": True, "brains": brains}


@router.post("/api/agent/tools/external-brain/send")
async def external_brain_send(req: ExternalBrainRequest):
    """외부 AI 두뇌에 프롬프트를 전송합니다.

    Ssak-Ai가 설치된 Gemini 앱이나 ChatGPT 웹의 채팅 UI를
    GUI 자동화로 제어하여 API 없이 추론 결과를 획득합니다.

    전략:
    - fallback: 첫 번째 가용 두뇌 사용, 실패 시 다음으로
    - round-robin: 순환 사용
    - compare: 여러 두뇌에 동시 전송하여 결과 비교
    """
    _require_allowed(
        "external_brain_send",
        {"target": req.target, "strategy": req.strategy},
        "critical",
    )
    from antigravity_k.engine.external_brain import ExternalBrainRouter

    router_instance = ExternalBrainRouter()

    response = await router_instance.send(
        prompt=req.prompt,
        strategy=req.strategy,
        target=req.target,
    )

    return {
        "ok": response.success,
        "source": response.source,
        "text": response.text,
        "latency_ms": round(response.latency_ms, 1),
        "error": response.error,
    }


# ─── TDD Loop Engine ─────────────────────────────────────────
class TDDGenerateRequest(BaseModel):
    """Tddgeneraterequest.

    Bases: BaseModel
    """

    prompt: str
    target_file_path: str | None = None
    max_iterations: int = Field(default=3, ge=1, le=10)
    coding_model: str = "qwen3.6:latest"


@router.post("/api/agent/tools/tdd-generate")
async def tdd_generate(req: TDDGenerateRequest):
    """Test-Driven Generation 자율 루프.

    코드와 테스트를 생성하고, 실패 시 에러 로그를 분석하여 코드를 자동 수정합니다.
    """
    target_file_path = _resolve_project_path(req.target_file_path) if req.target_file_path else None
    _require_allowed(
        "tdd_generate",
        {"path": target_file_path, "max_iterations": req.max_iterations},
        "critical",
    )
    try:
        from antigravity_k.api.dependencies import get_model_manager
        from antigravity_k.engine.tdd_engine import OmniTDDEngine

        engine = OmniTDDEngine(
            model_manager=get_model_manager(),
            coding_model=req.coding_model,
            max_iterations=req.max_iterations,
        )
        report = await engine.run_tdd_loop(req.prompt, target_file_path=target_file_path)
        return {
            "ok": report.status == "passed",
            "report": report.to_dict(),
        }
    except HTTPException:
        raise
    except (ImportError, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
