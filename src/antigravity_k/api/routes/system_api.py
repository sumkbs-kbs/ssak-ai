"""Ssak-Ai: System API Routes (Memory, Toolset, Harness, Shields, System).

================================================================================

Memory, Toolset, Harness, Shields, Security, Slash, Session, Code Intel, System routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, Protocol, TypeVar, cast

import psutil
import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
)

from antigravity_k import __version__
from antigravity_k.api.dependencies import (
    __get_skill_loader,  # pyright: ignore[reportPrivateUsage] - legacy dependency injection hook
    _get_session_manager,  # pyright: ignore[reportPrivateUsage] - legacy dependency injection hook
    get_model_manager,
    get_vault_engine,
)
from antigravity_k.api.dependencies import (
    get_memory_manager as _get_shared_memory_manager,
)
from antigravity_k.api.routes.session_state import get_active_session
from antigravity_k.build_info import get_build_info
from antigravity_k.config import config
from antigravity_k.engine.api_cache import TAG_SKILLS, TAG_SYSTEM, api_cache, cached
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.log_level_manager import LogLevelManager
from antigravity_k.engine.memory_provider import normalize_memory_scope
from antigravity_k.engine.runtime_recovery import SystemHealth
from antigravity_k.engine.secret_settings import (
    EnvSettingError,
    apply_env_settings,
    configured_secret_status,
    resolve_env_file_path,
    scrub_config_secrets,
)
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

if TYPE_CHECKING:
    from antigravity_k.engine.slash_commands import SlashCommandRegistry

logger = logging.getLogger("antigravity_k.api.system_api")
router = APIRouter()
_ModelT = TypeVar("_ModelT", bound=BaseModel)
JSONDict = dict[str, object]


class _SkillValidationLike(Protocol):
    valid: bool
    has_skill_md: bool
    has_readme: bool
    version: str
    tool_count: int
    warnings: list[str]


def _validate_skill(publisher: object, skill_dir: object, skill_name: str) -> _SkillValidationLike:
    validator = cast(Callable[[object, str], _SkillValidationLike], getattr(publisher, "_validate_for_publish"))
    return validator(skill_dir, skill_name)


def _as_json_object(value: object) -> JSONDict:
    return cast(JSONDict, value) if isinstance(value, dict) else {}


def _call_noarg(value: object, method_name: str) -> object:
    method = getattr(value, method_name, None)
    return method() if callable(method) else None


def _cached(*, ttl: float, tags: list[str]) -> Callable[[Callable[..., object]], Callable[..., object]]:
    return cast(Callable[[Callable[..., object]], Callable[..., object]], cached(ttl=ttl, tags=tags))


class _ToolsetActivationRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    name: StrictStr = "full"


class _MemoryScopeRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    scope: StrictStr = "all"


class _MemoryRetentionRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    max_age_days: StrictInt = Field(ge=0)


class _SkillInstallRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    package_name: StrictStr = ""


class _SkillRemoveRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    skill_name: StrictStr = ""


class _SkillPublishNpmRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    skill_name: StrictStr = ""
    version: StrictStr | None = None
    tag: StrictStr = "latest"
    dry_run: StrictBool = False


class _SkillPublishGithubRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    skill_name: StrictStr = ""
    repo: StrictStr = ""
    base_branch: StrictStr = "main"
    draft: StrictBool = False
    title: StrictStr | None = None
    body: StrictStr | None = None
    dry_run: StrictBool = False


class _SystemModeRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    mode: StrictStr = ""
    reason: StrictStr = "사용자 수동 전환"


class _LogLevelRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    name: StrictStr = ""
    level: StrictStr | StrictInt = "INFO"


class _LogLevelAllRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    level: StrictStr | StrictInt = "INFO"


class _DebugModeRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    action: StrictStr = ""


class _CodeIntelIndexRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    repo_path: StrictStr = "."
    force: StrictBool = False


class _CodeIntelImpactRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    repo_path: StrictStr = "."
    symbol_id: StrictStr = ""
    max_depth: StrictInt = Field(default=5, ge=0)


class _ShieldsDownRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    reason: StrictStr | None = None
    timeout_seconds: StrictInt | None = None
    target_toolset: StrictStr = "full"


class _EnvSettingsRequest(RootModel[dict[StrictStr, StrictStr]]):
    root: dict[StrictStr, StrictStr]


class _StripConfigRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    config: JsonValue = {}


class _SecurityScanRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    text: StrictStr = ""
    redact_mode: Literal["partial", "full"] = "partial"


class _ExtractionABTestRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    version_label: StrictStr = "api"


class _SearchExtractRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    query: StrictStr = ""


# ─── Helpers ────────────────────────────────────────────────────


def _permission_gate() -> PermissionGate:
    return PermissionGate(project_root=str(config.paths.project_root), mode="auto-pilot")


async def _parse_json_body(request: Request, model: type[_ModelT]) -> _ModelT:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


def _require_allowed(tool_name: str, args: JSONDict, risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for {tool_name}: {decision.permission.value}",
        )


def _get_slash_registry() -> SlashCommandRegistry:
    from antigravity_k.api.dependencies import get_slash_registry

    return cast("SlashCommandRegistry", get_slash_registry())


def _start_bound_session(*, resume: bool = True):
    """Start/resume session using the bound project's canonical root (WS-03 F2)."""
    from antigravity_k.api.dependencies import acquire_project_runtime
    from antigravity_k.api.project_binding import get_bound_request_execution_context

    sm = _get_session_manager()
    bound = get_bound_request_execution_context()
    project_path = bound.canonical_project_root if bound is not None else acquire_project_runtime().project_root
    _ = sm.start_session(project_path=project_path, resume=resume)
    return sm


def _get_memory_manager():
    return _get_shared_memory_manager()


def _get_toolset_manager():
    from antigravity_k.engine.toolset_manager import ToolsetManager

    try:
        config_file = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ),
            "config.yaml",
        )
        if os.path.exists(config_file):
            with open(config_file, encoding="utf-8") as f:
                cfg: JSONDict = _as_json_object(cast(object, yaml.safe_load(f)))
            toolsets = cfg.get("toolsets", {})
            if isinstance(toolsets, dict):
                return ToolsetManager.from_config(cast(dict[str, object], toolsets))
    except Exception:
        logger.exception("Unhandled exception")
        pass
    return ToolsetManager()


def _get_shields_manager():
    from antigravity_k.engine.shields import ShieldsManager

    try:
        config_file = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ),
            "config.yaml",
        )
        shields_config: dict[str, object] = {}
        if os.path.exists(config_file):
            with open(config_file, encoding="utf-8") as f:
                cfg: JSONDict = _as_json_object(yaml.safe_load(f) or {})
            configured_shields = cfg.get("shields", {})
            if isinstance(configured_shields, dict):
                shields_config = cast(dict[str, object], configured_shields)
        from_config = cast(Callable[..., ShieldsManager], ShieldsManager.from_config)
        return from_config(
            shields_config,
            toolset_manager=_get_toolset_manager(),
        )
    except Exception:
        logger.exception("Unhandled exception")
        return ShieldsManager(toolset_manager=_get_toolset_manager())


def get_harness():
    """Retrieve harness."""
    from antigravity_k.engine.harness import TestHarness

    return TestHarness()


# ─── Slash & Session API ────────────────────────────────────────


@router.post("/api/slash")
async def slash_command(request: Request):
    """Slash Command.

    Args:
        payload (_ToolsetActivationRequest): Validated activation request.

    """
    body = _as_json_object(cast(object, await request.json()))
    raw_text = body.get("command") or body.get("input") or body.get("text") or ""
    text = raw_text if isinstance(raw_text, str) else ""
    registry = _get_slash_registry()
    result: str | Iterator[str] = registry.execute(text)
    rendered = result if isinstance(result, str) else "".join(str(chunk) for chunk in result)
    return {"ok": True, "result": rendered}


@router.get("/api/slash/completions")
async def slash_completions(prefix: str = "/"):
    """Slash Completions.

    Args:
        prefix (str): str prefix.

    """
    registry = _get_slash_registry()
    return {"completions": registry.get_completions(prefix)}


@router.get("/api/session/info")
async def session_info():
    """Session Info."""
    sm = _get_session_manager()
    return {"ok": True, "session": sm.get_session_info() or {}}


@router.get("/api/session/messages")
async def session_messages():
    """Session Messages."""
    sm = _start_bound_session(resume=True)
    msgs = sm.get_messages()
    dicts: list[JSONDict] = []
    messages: list[object] = cast(list[object], msgs or [])
    for message_value in messages:
        to_simple_dict = getattr(message_value, "to_simple_dict", None)
        if callable(to_simple_dict):
            simple_message: object = to_simple_dict()
            dicts.append(
                cast(JSONDict, simple_message) if isinstance(simple_message, dict) else {"value": str(simple_message)}
            )
        elif isinstance(message_value, dict):
            dicts.append(cast(JSONDict, message_value))
        else:
            dicts.append({"value": str(message_value)})
    return {"ok": True, "messages": dicts}


@router.post("/api/session/save")
async def session_save():
    """Session Save.

    CR-02: 저장 실패를 성공으로 응답하지 않는다. 다른 writer가 먼저 저장했으면
    409, 원자 저장이 실패했으면 503으로 실패를 명시한다.
    """
    from antigravity_k.engine.session_manager import (
        SessionDeletedError,
        SessionPersistenceError,
        StaleSessionWriteError,
    )

    sm = _get_session_manager()
    try:
        sm.save()
    except (StaleSessionWriteError, SessionDeletedError) as exc:
        # 내부 경로/스택은 응답에 넣지 않는다(public_detail만 노출).
        # NX-03: 삭제된 세션은 409 session_deleted — 재로드 또는 새 세션 안내.
        raise HTTPException(status_code=409, detail=exc.public_detail) from exc
    except SessionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=exc.public_detail) from exc
    return {"ok": True, "message": "Session saved."}


# ─── Memory API ─────────────────────────────────────────────────


@router.get("/api/memory/stats")
async def get_memory_stats():
    """Retrieve memory stats."""
    mm = _get_memory_manager()
    return {"memory": mm.get_stats()}


@router.get("/api/memory/recall")
async def recall_memory(query: str = ""):
    """Recall Memory.

    Args:
        query (str): str query.

    """
    mm = _get_memory_manager()
    result = mm.prefetch_all(query or "general")
    return {"recalled": result, "query": query}


@router.delete("/api/memory")
async def purge_memory(request: Request):
    payload = await _parse_json_body(request, _MemoryScopeRequest)
    scope = payload.scope
    try:
        normalized_scope = normalize_memory_scope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report = _get_memory_manager().clear(normalized_scope)
    get_audit_logger().log_event(
        "memory_purge",
        {"scope": normalized_scope, "deleted": report},
    )
    return {"ok": True, "scope": normalized_scope, "deleted": report}


@router.get("/api/memory/export")
async def export_memory(scope: str = "all", include_vault_assets: bool = False):
    try:
        normalized_scope = normalize_memory_scope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _get_memory_manager().export(normalized_scope)
    result["vault"] = {"included": False, "asset_policy": "excluded_by_default"}
    if include_vault_assets:
        vault = get_vault_engine()
        result["vault"] = {
            "included": vault is not None,
            "asset_policy": "redacted_export_only",
            "notes": vault.export_notes(include_assets=True, redact=True) if vault is not None else [],
        }
    get_audit_logger().log_event(
        "memory_export",
        {"scope": normalized_scope, "include_vault_assets": include_vault_assets},
    )
    return result


@router.post("/api/memory/redact")
async def redact_memory(request: Request):
    payload = await _parse_json_body(request, _MemoryScopeRequest)
    scope = payload.scope
    try:
        normalized_scope = normalize_memory_scope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report = _get_memory_manager().redact(normalized_scope)
    get_audit_logger().log_event("memory_redact", {"scope": normalized_scope, "changed": report})
    return {"ok": True, "scope": normalized_scope, "changed": report}


@router.post("/api/memory/retention")
async def apply_memory_retention(request: Request):
    payload = await _parse_json_body(request, _MemoryRetentionRequest)
    max_age_days = payload.max_age_days
    report = _get_memory_manager().apply_retention(max_age_days)
    get_audit_logger().log_event(
        "memory_retention",
        {"max_age_days": max_age_days, "deleted": report},
    )
    return {"ok": True, "max_age_days": max_age_days, "deleted": report}


@router.get("/api/memory/ranked")
async def ranked_memory_facts(top_k: int = 20):
    """전체 메모리 팩트를 중요도 점수 내림차순으로 반환합니다."""
    manager = _get_memory_manager()
    ranked = manager.ranked_facts(top_k=max(1, min(top_k, 100)))
    return {
        "facts": [
            {
                "key": fact.key,
                "value": fact.value,
                "source": fact.source,
                "scope": fact.scope,
                "authority": int(fact.authority),
                "observed_at": fact.observed_at,
                "score": round(score, 2),
            }
            for fact, score in ranked
        ]
    }


@router.delete("/api/memory/entries")
async def delete_memory_entry(provider: str, key: str):
    """개별 메모리 항목을 삭제합니다 (provider: project|global|episodic)."""
    manager = _get_memory_manager()
    deleted = manager.delete_entry(provider, key)
    get_audit_logger().log_event(
        "memory_entry_delete",
        {"provider": provider, "key": key, "deleted": deleted},
    )
    return {"provider": provider, "key": key, "deleted": deleted}


# ─── Toolset API ────────────────────────────────────────────────


@router.get("/api/toolsets")
@_cached(ttl=30, tags=[TAG_SYSTEM])
async def list_toolsets() -> JSONDict:
    """List Toolsets."""
    ts = _get_toolset_manager()
    return {"toolsets": ts.list_toolsets(), "active": ts.active_toolset}


@router.post("/api/toolsets/activate")
async def activate_toolset(payload: _ToolsetActivationRequest):
    """Activate Toolset.

    Args:
        request (Request): Request request.

    """
    ts = _get_toolset_manager()
    success = ts.set_active(payload.name)
    return {
        "success": success,
        "active": ts.active_toolset,
        "tools": ts.get_active_tools() if success else [],
    }


@router.get("/api/toolsets/{name}/tools")
async def get_toolset_tools(name: str):
    """Retrieve toolset tools.

    Args:
        name (str): str name.

    """
    ts = _get_toolset_manager()
    tools = ts.resolve(name)
    return {"toolset": name, "tools": tools, "count": len(tools)}


# ─── Harness API ────────────────────────────────────────────────


@router.post("/api/harness/self-test")
async def harness_self_test(request: Request):
    """Harness Self Test.

    Args:
        request (Request): Request request.

    """
    try:
        body = _as_json_object(cast(object, await request.json()))
    except Exception:
        logger.exception("Unhandled exception")
        body = {}
    scope = body.get("scope", "api_only")
    harness = get_harness()
    report = await harness.run_all(use_browser=(scope != "api_only"))
    return {"ok": True, "report": report.to_dict()}


@router.get("/api/harness/results")
async def harness_results():
    """Harness Results."""
    harness = get_harness()
    report = harness.get_latest_report()
    if report:
        return {"ok": True, "report": report.to_dict()}
    return {"ok": True, "report": None, "message": "아직 테스트가 실행되지 않았습니다."}


@router.get("/api/harness/trend")
async def harness_trend():
    """Harness Trend."""
    harness = get_harness()
    trend = harness.feedback.get_trend()
    return {"ok": True, "trend": trend}


# ─── Skills API (D16: Dashboard Skills Browser) ─────────────────

# ─── System Status & Restart (legacy에서 귀속) ─────────────────
# ─── System API (Status & Restart) ─────────────────


# CR-10: 업타임은 **현재 API 서버 프로세스의 가동 시간**이다.
# START_TIME은 monotonic 시계라 시스템 시계 변경(NTP/수동 조정)에 영향받지 않는다.
# 호스트 uptime이나 대시보드 탭이 열린 시간과 절대 혼합하지 않는다.
START_TIME = time.monotonic()
# 운영자가 로그와 대조할 수 있는 실제 프로세스 시작 시각(UTC 벽시계).
STARTED_AT = datetime.now(UTC)
# 다중 worker 배포에서 어느 프로세스가 응답했는지 식별하는 값.
PROCESS_ID = os.getpid()


@router.get("/api/system/status")
async def system_status():
    """서버의 현재 상태, 메모리 사용량 및 업타임을 반환합니다."""
    try:
        from antigravity_k.api.dependencies import get_model_manager

        mem_info = psutil.virtual_memory()
        uptime_seconds = max(0, int(time.monotonic() - START_TIME))

        # Get global token usage from tracker
        model_manager = get_model_manager()
        total_tokens = model_manager.tracker.get_total_tokens()

        return {
            "ok": True,
            "status": "online",
            # legacy 키 이름이지만 실제 값은 percent다. 오해를 막기 위해 정직한 키를 함께 준다.
            "memory_mb": cast(float, mem_info.percent),
            "memory_percent": cast(float, mem_info.percent),
            "cpu_percent": await asyncio.to_thread(psutil.cpu_percent, interval=0.1),
            "total_tokens": total_tokens,
            "uptime_seconds": uptime_seconds,
            "uptime_started_at": STARTED_AT.isoformat(),
            "process_id": PROCESS_ID,
            "version": __version__,
            "build": get_build_info(),
        }
    except (psutil.Error, OSError, RuntimeError) as e:
        logger.error("Status error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/system/restart")
async def system_restart(background_tasks: BackgroundTasks):
    """System Restart.

    Args:
        background_tasks (BackgroundTasks): BackgroundTasks background tasks.

    """
    _require_allowed("system_restart", {}, "critical")
    try:

        def delay_restart():
            trigger_file = os.path.abspath(os.path.join("src", ".restart_trigger"))
            with open(trigger_file, "a"):
                os.utime(trigger_file, None)
            logger.info("Restart triggered via API (delayed).")

        background_tasks.add_task(delay_restart)
        return {
            "ok": True,
            "message": "Restart triggered. The server will reboot in a moment.",
        }
    except (OSError, RuntimeError) as e:
        logger.error("Restart error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/system/skills")
@_cached(ttl=60, tags=[TAG_SKILLS])
async def system_skills() -> JSONDict:
    """SkillLoader.list_skills() 결과를 JSON으로 반환합니다.

    Phase 1 D16: Dashboard Skills Browser에서 사용.
    각 스킬의 source(global/local/market), id, name, description, version 정보 포함.
    """
    try:
        sl = __get_skill_loader()
        skills = sl.list_skills()
        return {"ok": True, "skills": skills}
    except Exception as e:
        logger.error("Skills list error: %s", e)
        return {"ok": False, "skills": [], "error": str(e)}


@router.get("/api/system/skills/installed")
@_cached(ttl=60, tags=[TAG_SKILLS])
async def system_skills_installed() -> JSONDict:
    """SkillMarketRegistry.list_installed() 결과를 JSON으로 반환합니다.

    Phase 1 D16: Dashboard Skills Browser — Marketplace 탭에서 사용.
    설치된 스킬의 상세 정보 (name, version, is_loaded, mcp_server_id 등) 포함.
    """
    try:
        from antigravity_k.engine.skill_installer import SkillInstaller
        from antigravity_k.engine.skill_market_client import SkillMarketClient
        from antigravity_k.engine.skill_market_registry import SkillMarketRegistry

        sl = __get_skill_loader()
        installer = SkillInstaller(project_root=os.getcwd(), skill_loader=sl)
        client = SkillMarketClient(
            project_root=os.getcwd(),
        )
        registry = SkillMarketRegistry(
            project_root=os.getcwd(),
            market_client=client,
            installer=installer,
            skill_loader=sl,
        )
        installed = registry.list_installed()
        result: list[JSONDict] = []
        for skill in installed:
            s: JSONDict = {
                "name": skill.skill_name,
                "version": skill.version,
                "is_loaded": skill.is_loaded,
                "mcp_server_id": skill.mcp_server_id,
                "security_issues": skill.security_findings,
            }
            result.append(s)
        return {"ok": True, "installed": result}
    except Exception as e:
        logger.error("Installed skills error: %s", e)
        return {"ok": False, "installed": [], "error": str(e)}


@router.get("/api/system/skills/mcp")
@_cached(ttl=30, tags=[TAG_SKILLS])
async def system_skills_mcp() -> JSONDict:
    """MCPServerRegistry.list_skills_with_mcp() 결과를 JSON으로 반환합니다.

    Phase 1 D16: Dashboard Skills Browser — MCP Servers 탭에서 사용.
    각 스킬별 MCP 서버 정보 (name, status, tools) 포함.
    """
    try:
        from antigravity_k.tools.mcp_tool_loader import MCPServerRegistry

        mcp = MCPServerRegistry()
        servers = mcp.list_skills_with_mcp()
        return {"ok": True, "servers": servers}
    except Exception as e:
        logger.error("MCP skills error: %s", e)
        return {"ok": False, "servers": [], "error": str(e)}


@router.get("/api/system/skills/search")
async def system_skills_search(
    q: Annotated[str, Query(description="Search query for npm skill packages")] = "",
    limit: Annotated[int, Query(ge=1, le=50, description="Max results")] = 15,
) -> JSONDict:
    """npm 레지스트리에서 @antigravity-k/skill-* 패키지를 검색합니다.

    Phase 1 D20: Dashboard Skills Browser — Search tab에서 실시간 검색.
    """
    try:
        from antigravity_k.engine.skill_market_client import SkillMarketClient

        client = SkillMarketClient()
        results = client.search(q, limit=limit)
        formatted = [r.to_dict() for r in results]
        return {"ok": True, "results": formatted, "count": len(formatted)}
    except Exception as e:
        logger.error("Skills search error: %s", e)
        return {"ok": False, "results": [], "count": 0, "error": str(e)}


@router.post("/api/system/skills/install")
async def system_skills_install(request: Request):
    """npm 패키지를 설치합니다.

    Phase 1 D20: Dashboard Skills Browser — Install 버튼.
    """
    try:
        payload = await _parse_json_body(request, _SkillInstallRequest)
        package_name = payload.package_name
        if not package_name:
            return {"ok": False, "error": "package_name is required"}
        _require_allowed("install_skill", {"package_name": package_name}, "critical")

        from antigravity_k.engine.skill_installer import SkillInstaller
        from antigravity_k.engine.skill_market_client import SkillMarketClient
        from antigravity_k.engine.skill_market_registry import SkillMarketRegistry

        sl = __get_skill_loader()
        installer = SkillInstaller(project_root=os.getcwd(), skill_loader=sl)
        client = SkillMarketClient(project_root=os.getcwd())
        registry = SkillMarketRegistry(
            project_root=os.getcwd(),
            market_client=client,
            installer=installer,
            skill_loader=sl,
        )
        result = registry.install(package_name)
        return {"ok": result.get("success", False), "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Skill install error: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/system/skills/remove")
async def system_skills_remove(request: Request):
    """설치된 스킬을 제거합니다.

    Phase 1 D20: Dashboard Skills Browser — Remove 버튼.
    """
    try:
        payload = await _parse_json_body(request, _SkillRemoveRequest)
        skill_name = payload.skill_name
        if not skill_name:
            return {"ok": False, "error": "skill_name is required"}
        _require_allowed("remove_skill", {"skill_name": skill_name}, "critical")

        from antigravity_k.engine.skill_installer import SkillInstaller
        from antigravity_k.engine.skill_market_client import SkillMarketClient
        from antigravity_k.engine.skill_market_registry import SkillMarketRegistry

        sl = __get_skill_loader()
        installer = SkillInstaller(project_root=os.getcwd(), skill_loader=sl)
        client = SkillMarketClient(project_root=os.getcwd())
        registry = SkillMarketRegistry(
            project_root=os.getcwd(),
            market_client=client,
            installer=installer,
            skill_loader=sl,
        )
        result = registry.remove(skill_name)
        return {"ok": result.get("success", False), "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Skill remove error: %s", e)
        return {"ok": False, "error": str(e)}


# ─── Skill Publish API (D17: Publish to npm / GitHub PR) ──────


@router.get("/api/system/skills/local")
@_cached(ttl=30, tags=[TAG_SKILLS])
async def system_skills_local() -> JSONDict:
    """로컬 스킬 디렉토리 목록을 반환합니다 (publish 가능한 스킬).

    Phase 1 D17: 로컬 .agent/skills/ 디렉토리에서 publish 가능한 스킬을 검색.
    각 스킬의 디렉토리 경로, SKILL.md frontmatter 정보, 유효성 상태를 포함.
    """
    try:
        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=os.getcwd())
        local_skills: list[JSONDict] = []

        # market/ 디렉토리 검색
        if publisher.market_dir.exists():
            for skill_dir in publisher.market_dir.iterdir():
                if skill_dir.is_dir():
                    validation = _validate_skill(publisher, skill_dir, skill_dir.name)
                    local_skills.append(
                        {
                            "name": skill_dir.name,
                            "path": str(skill_dir),
                            "source": "market",
                            "valid": validation.valid,
                            "has_skill_md": validation.has_skill_md,
                            "has_readme": validation.has_readme,
                            "version": validation.version,
                            "tool_count": validation.tool_count,
                            "warnings": validation.warnings,
                        },
                    )

        # .agent/skills/ 디렉토리 검색
        if publisher.skills_dir.exists():
            for skill_dir in publisher.skills_dir.iterdir():
                if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                    # market 디렉토리 자체는 건너뜀 (하위 스킬은 1차에서 이미 처리)
                    if skill_dir.name == "market" or skill_dir.parent.name == "market":
                        continue
                    already_listed = any(s["name"] == skill_dir.name for s in local_skills)
                    if not already_listed:
                        validation = _validate_skill(publisher, skill_dir, skill_dir.name)
                        local_skills.append(
                            {
                                "name": skill_dir.name,
                                "path": str(skill_dir),
                                "source": "local",
                                "valid": validation.valid,
                                "has_skill_md": validation.has_skill_md,
                                "has_readme": validation.has_readme,
                                "version": validation.version,
                                "tool_count": validation.tool_count,
                                "warnings": validation.warnings,
                            },
                        )

        return {"ok": True, "skills": local_skills, "count": len(local_skills)}
    except Exception as e:
        logger.error("Local skills list error: %s", e)
        return {"ok": False, "skills": [], "count": 0, "error": str(e)}


@router.get("/api/system/skills/local/check")
async def system_skills_local_check(
    since: Annotated[str, Query(description="ISO timestamp or empty for full list")] = "",
) -> JSONDict:
    """로컬 스킬 디렉토리 변경 내역을 반환합니다.

    Phase 1 D18: Skill auto-discovery — since 시점 이후 변경된 스킬 목록.
    since가 비어있으면 전체 목록 반환.

    Query params:
        since: ISO 8601 타임스탬프 (e.g. "2026-07-21T12:00:00Z").
               비어있으면 전체 스킬 목록 반환.

    Returns:
        dict: {ok, skills: [...], new: [...], removed: [...], changed: [...], checked_at, has_changes}
    """
    try:
        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=os.getcwd())
        current_skills: list[JSONDict] = []
        seen_names: set[str] = set()

        # market/ 디렉토리 검색
        if publisher.market_dir.exists():
            for skill_dir in publisher.market_dir.iterdir():
                if skill_dir.is_dir() and skill_dir.name not in seen_names:
                    seen_names.add(skill_dir.name)
                    validation = _validate_skill(publisher, skill_dir, skill_dir.name)
                    current_skills.append(
                        {
                            "name": skill_dir.name,
                            "source": "market",
                            "version": validation.version,
                            "valid": validation.valid,
                            "mtime": skill_dir.stat().st_mtime,
                        },
                    )

        # .agent/skills/ 디렉토리 검색
        if publisher.skills_dir.exists():
            for skill_dir in publisher.skills_dir.iterdir():
                if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                    if skill_dir.name == "market" or skill_dir.name in seen_names:
                        continue
                    seen_names.add(skill_dir.name)
                    validation = _validate_skill(publisher, skill_dir, skill_dir.name)
                    current_skills.append(
                        {
                            "name": skill_dir.name,
                            "source": "local",
                            "version": validation.version,
                            "valid": validation.valid,
                            "mtime": skill_dir.stat().st_mtime,
                        },
                    )

        checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # since가 있으면 변경 탐지
        new_skills: list[JSONDict] = []
        removed_skills: list[JSONDict] = []
        changed_skills: list[JSONDict] = []
        has_changes = False

        if since:
            try:
                since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
            except ValueError:
                since_ts = 0.0

            new_skills = [s for s in current_skills if cast(float, s["mtime"]) > since_ts]
            has_changes = bool(new_skills) or bool(removed_skills) or bool(changed_skills)

        return {
            "ok": True,
            "skills": current_skills,
            "new": new_skills,
            "removed": removed_skills,
            "changed": changed_skills,
            "checked_at": checked_at,
            "has_changes": has_changes,
            "count": len(current_skills),
        }
    except Exception as e:
        logger.error("Skills check error: %s", e)
        return {"ok": False, "skills": [], "count": 0, "error": str(e)}


@router.post("/api/system/skills/publish-npm")
async def system_skills_publish_npm(request: Request):
    """로컬 스킬을 npm 레지스트리에 publish합니다.

    Phase 1 D17: SkillPublisher.publish_to_npm()을 호출하여
    로컬 스킬 → npm publish 파이프라인을 실행.

    Request Body:
        skill_name (str): 스킬 이름
        version (str, optional): 버전 (기본: SKILL.md frontmatter)
        tag (str, optional): npm dist-tag (기본: "latest")
        dry_run (bool, optional): 검증만 수행 (기본: false)

    Returns:
        dict: {ok, publish_result: {success, action, package_name, version, errors, warnings, ...}}
    """
    try:
        payload = await _parse_json_body(request, _SkillPublishNpmRequest)
        skill_name = payload.skill_name
        if not skill_name:
            return {"ok": False, "error": "skill_name is required"}
        _require_allowed(
            "publish_skill_npm",
            {"skill_name": skill_name, "tag": payload.tag},
            "critical",
        )

        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=os.getcwd())
        result = publisher.publish_to_npm(
            skill_name,
            version=payload.version,
            tag=payload.tag,
            dry_run=payload.dry_run,
        )

        return {
            "ok": result.success,
            "publish_result": {
                "success": result.success,
                "action": result.action,
                "skill_name": result.skill_name,
                "package_name": result.package_name,
                "version": result.version,
                "npm_url": result.npm_url,
                "errors": result.errors,
                "warnings": result.warnings,
                "summary": result.summary(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("npm publish error")
        return {"ok": False, "error": str(e)}


@router.post("/api/system/skills/publish-github")
async def system_skills_publish_github(request: Request):
    """로컬 스킬을 GitHub PR로 제출합니다.

    Phase 1 D17: SkillPublisher.publish_to_github()을 호출하여
    로컬 스킬 → GitHub PR 파이프라인을 실행.

    Request Body:
        skill_name (str): 스킬 이름
        repo (str): 대상 GitHub 리포지토리 (e.g. "org/skills-repo")
        base_branch (str, optional): PR 대상 브랜치 (기본: "main")
        draft (bool, optional): Draft PR 생성 (기본: false)
        title (str, optional): PR 타이틀
        body (str, optional): PR 설명
        dry_run (bool, optional): 검증만 수행 (기본: false)

    Returns:
        dict: {ok, publish_result: {success, action, skill_name, pr_url, errors, ...}}
    """
    try:
        payload = await _parse_json_body(request, _SkillPublishGithubRequest)
        skill_name = payload.skill_name
        repo = payload.repo
        if not skill_name:
            return {"ok": False, "error": "skill_name is required"}
        if not repo and not payload.dry_run:
            return {"ok": False, "error": "repo is required (e.g. 'org/skills-repo')"}
        _require_allowed(
            "publish_skill_github",
            {"skill_name": skill_name, "repo": repo, "draft": payload.draft},
            "critical",
        )

        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=os.getcwd())
        result = publisher.publish_to_github(
            skill_name,
            repo=repo,
            base_branch=payload.base_branch,
            draft=payload.draft,
            title=payload.title,
            body=payload.body,
            dry_run=payload.dry_run,
        )

        return {
            "ok": result.success,
            "publish_result": {
                "success": result.success,
                "action": result.action,
                "skill_name": result.skill_name,
                "package_name": result.package_name,
                "pr_url": result.pr_url,
                "errors": result.errors,
                "warnings": result.warnings,
                "summary": result.summary(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("GitHub PR error")
        return {"ok": False, "error": str(e)}


@router.get("/api/system/mode/history")
async def system_mode_history() -> JSONDict:
    """ModeManager의 전체 모드 히스토리를 반환합니다.

    Phase 1 D16: Dashboard Mode Indicator 확장 — 히스토리 렌더링용.
    """
    try:
        from antigravity_k.api.dependencies import get_mode_manager

        mgr = get_mode_manager()
        history = [
            {
                "from": h.from_mode,
                "to": h.to_mode,
                "reason": h.reason,
                "timestamp": h.timestamp,
            }
            for h in mgr.mode_history
        ]
        return {"ok": True, "history": history}
    except Exception as e:
        logger.error("Mode history error: %s", e)
        return {"ok": False, "history": [], "error": str(e)}


# ─── System API ─────────────────────────────────────────────────


@router.get("/api/system/mode")
async def system_mode() -> JSONDict:
    """현재 실행 모드(Plan/Build/Interactive)를 반환합니다.

    Phase 1 D7: Dashboard WebSocket이 초기 연결 시 현재 모드를 가져오기 위해 사용.
    depends에 ModeManager 싱글톤을 조회하여 실제 실행 모드 반환.
    """
    try:
        from antigravity_k.api.dependencies import get_mode_manager

        mgr = get_mode_manager()
        return {
            "ok": True,
            "mode": mgr.current_mode.value,
            "is_plan": mgr.is_plan,
            "is_build": mgr.is_build,
            "is_interactive": mgr.is_interactive,
            "plan_artifact_path": mgr.plan_artifact_path,
            "history_count": len(mgr.mode_history),
            "last_transition": (
                {
                    "from": mgr.mode_history[-1].from_mode,
                    "to": mgr.mode_history[-1].to_mode,
                    "reason": mgr.mode_history[-1].reason,
                    "timestamp": mgr.mode_history[-1].timestamp,
                }
                if mgr.mode_history
                else None
            ),
        }
    except Exception as e:
        logger.error("Mode status error: %s", e)
        return {"ok": False, "mode": "interactive", "error": str(e)}


@router.post("/api/system/mode")
async def set_system_mode(request: Request):
    """실행 모드를 전환합니다 (Interactive/Plan/Build).

    대시보드의 모드 인디케이터 클릭 시 호출됩니다.
    """
    payload = await _parse_json_body(request, _SystemModeRequest)
    try:
        target_mode = payload.mode.lower()
        reason = payload.reason

        if target_mode not in ("interactive", "plan", "build"):
            return {"ok": False, "error": f"알 수 없는 모드: {target_mode}. interactive/plan/build 중 하나."}

        from antigravity_k.api.dependencies import get_mode_manager

        mgr = get_mode_manager()
        if target_mode == "plan":
            _ = mgr.switch_to_plan(reason=reason)
        elif target_mode == "build":
            _ = mgr.switch_to_build(reason=reason)
        else:
            _ = mgr.switch_to_interactive(reason=reason)

        logger.info("모드 전환 (수동): %s → %s", target_mode, reason)
        return {
            "ok": True,
            "mode": mgr.current_mode.value,
            "message": f"모드가 {mgr.current_mode.value}(으)로 전환되었습니다.",
        }
    except Exception as e:
        logger.error("Mode switch error: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/search/ab-test/run")
async def run_extraction_ab_test(request: Request):
    """데이터 추출 A/B 테스트를 실행합니다.

    내장 테스트 케이스(BUILTIN_CASES) 전체를 실행하여
    현재 데이터 추출 엔진의 정확도를 측정하고 보고서를 반환합니다.

    Request Body (선택):
        version_label (str): 테스트 버전 레이블 (기본값: "api")

    Returns:
        dict: {
            ok: bool,
            report: ABTestReport.to_dict()
        }
    """
    payload = await _parse_json_body(request, _ExtractionABTestRequest)
    try:
        from antigravity_k.engine.extraction_ab_test import run_builtin_suite

        report = run_builtin_suite(version_label=payload.version_label)
        logger.info("A/B 테스트 완료: %d개 케이스, 정확도 %.1f%%", report.total_cases, report.avg_accuracy)
        return {"ok": True, "report": report.to_dict()}
    except Exception as e:
        logger.error("A/B test error: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/api/system/cache-stats")
@_cached(ttl=10, tags=[TAG_SYSTEM])
async def system_cache_stats():
    """API 응답 캐시 통계를 반환합니다 (Phase 28 / Phase 29).

    ApiCache의 엔트리 수, 히트율, 태그 수, 메모리 추정치,
    개별 엔트리 목록(TTL, age, hits)을 반환합니다.

    Returns:
        dict: {
            ok: bool,
            stats: {
                total_entries: int,
                total_tags: int,
                hits: int,
                misses: int,
                hit_ratio: float,
                memory_estimate_kb: float,
                entries: [{key, ttl, age, remaining_ttl, tags, hits}, ...]
            }
        }
    """
    try:
        stats = await api_cache.get_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        logger.error("Cache stats error: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/api/search/cache-stats")
async def search_cache_stats():
    """검색 캐시 통계를 반환합니다.

    WebSearchTool의 SearchCache의 파일 수, 용량, 디렉토리 경로를 반환합니다.
    """
    try:
        from antigravity_k.tools.web_search import SearchCache

        cache = SearchCache()
        stats = cache.get_cache_stats()
        return {"ok": True, "cache_stats": stats}
    except Exception as e:
        logger.error("Cache stats error: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/api/search/pipeline-timing")
async def get_pipeline_timing():
    """파이프라인 단계별 지연 시간 통계를 반환합니다.

    PipelineTimer로부터 검색→추출 파이프라인의 각 단계별
    평균/최소/최대/최근 지연 시간과 최근 기록을 조회합니다.

    Returns:
        dict: {
            ok: bool,
            stats: {
                steps: {step_name: {avg_ms, min_ms, max_ms, count, ...}},
                recent: [{step, duration_ms, timestamp}, ...],
                pipeline_total_avg_ms: float,
            }
        }
    """
    try:
        from antigravity_k.engine.pipeline_timer import PipelineTimer

        stats = PipelineTimer.get_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        logger.error("Pipeline timing error: %s", e)
        return {"ok": False, "error": str(e)}


# ─── Log Level Management (Phase 30) ────────────────────────────


@router.get("/api/system/log-level")
async def system_log_level_list() -> JSONDict:
    """모든 antigravity_k.* 로거의 현재 로그 레벨을 반환합니다.

    LogLevelManager.discover_loggers()를 통해 현재 실행 중인
    모든 로거의 레벨, effective 레벨, 핸들러 수를 조회합니다.
    런타임에 생성되지 않은 KNOWN_LOGGERS도 포함됩니다.

    Returns:
        dict: {
            ok: bool,
            loggers: [{name, level, level_name, effective_level,
                      effective_level_name, handlers}, ...],
            debug_mode: bool,
            count: int
        }
    """
    try:
        loggers = LogLevelManager.discover_loggers()
        debug_mode = LogLevelManager.is_debug_mode()
        return {
            "ok": True,
            "loggers": loggers,
            "debug_mode": debug_mode,
            "count": len(loggers),
        }
    except Exception as e:
        logger.error("Log level list error: %s", e)
        return {"ok": False, "loggers": [], "debug_mode": False, "count": 0, "error": str(e)}


@router.post("/api/system/log-level")
async def system_log_level_set(request: Request) -> JSONDict:
    """특정 로거의 로그 레벨을 변경합니다.

    로거 이름과 대상 레벨을 지정하여 동적으로 로깅 레벨을 변경합니다.
    서버 재시작 없이 즉시 적용됩니다.

    Request Body:
        name (str): 로거 이름 ("root" 또는 "antigravity_k.api" 등)
        level (str | int): 대상 레벨 ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    Returns:
        dict: {
            ok: bool,
            result: {name, previous_level, current_level,
                     previous_level_name, current_level_name}
        }
    """
    payload = await _parse_json_body(request, _LogLevelRequest)
    try:
        logger_name = payload.name
        level = payload.level

        if not logger_name:
            return {"ok": False, "error": "name is required"}
        if isinstance(level, str) and level.upper() not in LogLevelManager.LEVEL_NAMES:
            return {"ok": False, "error": f"Invalid level: {level}. Use DEBUG/INFO/WARNING/ERROR/CRITICAL"}

        result = _as_json_object(cast(object, LogLevelManager.set_level(logger_name, level)))
        logger.info(
            "Log level changed: %s %s -> %s",
            logger_name,
            str(result.get("previous_level_name", "")),
            str(result.get("current_level_name", "")),
        )
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error("Log level set error: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/system/log-level/all")
async def system_log_level_set_all(request: Request) -> JSONDict:
    """모든 antigravity_k.* 로거의 로그 레벨을 한 번에 변경합니다.

    디버깅이 필요할 때 전체 로거를 DEBUG로 변경하거나,
    정리 후 INFO로 복원할 때 유용합니다.

    Request Body:
        level (str | int): 대상 레벨 ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    Returns:
        dict: {
            ok: bool,
            result: {target_level, target_level_name, updated_count, loggers: [...]}
        }
    """
    payload = await _parse_json_body(request, _LogLevelAllRequest)
    try:
        level = payload.level

        if isinstance(level, str) and level.upper() not in LogLevelManager.LEVEL_NAMES:
            return {"ok": False, "error": f"Invalid level: {level}. Use DEBUG/INFO/WARNING/ERROR/CRITICAL"}

        result = _as_json_object(cast(object, LogLevelManager.set_all_levels(level)))
        updated_count = result.get("updated_count", 0)
        logger.info(
            "All log levels changed: %s (%d loggers)",
            str(result.get("target_level_name", "")),
            updated_count if isinstance(updated_count, int) else 0,
        )
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error("Log level set-all error: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/system/debug-mode")
async def system_debug_mode(request: Request) -> JSONDict:
    """디버그 모드를 활성화/비활성화합니다.

    디버그 모드가 활성화되면 모든 antigravity_k.* 로거가 DEBUG 레벨로 설정되고,
    비활성화되면 원래 레벨로 복원됩니다.

    Request Body:
        action (str): "enable" 또는 "disable"

    Returns:
        dict: {
            ok: bool,
            debug_mode: bool,
            result: {success, message, updated_count / restored_count}
        }
    """
    payload = await _parse_json_body(request, _DebugModeRequest)
    try:
        action = payload.action.lower()

        if action == "enable":
            result = _as_json_object(cast(object, LogLevelManager.enable_debug_mode()))
        elif action == "disable":
            result = _as_json_object(cast(object, LogLevelManager.disable_debug_mode()))
        else:
            return {"ok": False, "error": "action must be 'enable' or 'disable'"}

        logger.info("Debug mode %s: %s", action, str(result.get("message", "")))
        return {
            "ok": True,
            "debug_mode": LogLevelManager.is_debug_mode(),
            "result": result,
        }
    except Exception as e:
        logger.error("Debug mode error: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/api/search/extraction-metrics")
async def get_extraction_metrics():
    """데이터 추출 메트릭 통계를 반환합니다.

    DataExtractor의 ExtractionMetrics 클래스 레벨 카운터로부터
    전체 시스템의 데이터 추출 정확도/성공률을 조회합니다.

    Returns:
        dict: {
            ok: bool,
            metrics: {
                total_calls: int,
                stock_attempts: int,
                stock_success: int,
                weather_attempts: int,
                weather_success: int,
                exchange_attempts: int,
                exchange_success: int,
                date_attempts: int,
                date_found: int,
                errors: int,
                speculative_filtered: int,
                success_rates: {
                    stock: float,
                    weather: float,
                    exchange: float,
                    overall: float
                },
                recent_calls: [...]
            }
        }
    """
    try:
        from antigravity_k.engine.data_extractor import ExtractionMetrics

        stats = ExtractionMetrics.get_stats()
        return {"ok": True, "metrics": stats}
    except Exception as e:
        logger.error("Extraction metrics error: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/api/search/extract")
async def search_and_extract(request: Request):
    """검색 실행 + 구조화된 데이터 추출을 한 번에 수행합니다.

    WebSearchTool로 검색하고 DataExtractor로 구조화 데이터(주가, 날씨, 환율, 날짜)를
    추출하여 JSON으로 반환합니다.

    Request Body:
        query (str): 검색 쿼리 (예: "한화에어로스페이스 주가 알려줘")

    Returns:
        dict: {
            ok: bool,
            query: str,
            extracted: {
                stock_prices: [...],
                weather: [...],
                exchange_rates: [...],
                dates_found: [...],
                numeric_data: [{
                    value: float | str,
                    normalized_value: str,
                    unit: str,
                    display_unit: str,
                    currency: str,
                    source_index: int,
                    raw_text: str
                }]
            },
            extraction_log: str,  # format_for_llm() 출력
            search_length: int,   # 원시 검색 결과 길이
            has_top1_json: bool,  # TOP 1 JSON 발견 여부
        }

    ``normalized_value`` is exact decimal text measured in ``unit``. ``display_unit``
    keeps the scale or symbol present in the search source, such as ``억`` or ``%p``.
    """
    payload = await _parse_json_body(request, _SearchExtractRequest)

    import asyncio
    import time as _time

    from antigravity_k.engine.data_extractor import DataExtractor
    from antigravity_k.engine.pipeline_timer import PipelineTimer
    from antigravity_k.tools.web_search import WebSearchTool

    query = payload.query
    if not query or not query.strip():
        return {"ok": False, "error": "query is required"}

    query = query.strip()

    try:
        pipeline_timings: dict[str, float] = {}

        # 1. 검색 실행 (async로 이벤트 루프 차단 방지)
        _t0 = _time.perf_counter()
        tool = WebSearchTool()
        search_res = await asyncio.to_thread(tool.execute, query=query)
        _d = (_time.perf_counter() - _t0) * 1000
        search_length = len(search_res)
        PipelineTimer.record("web_search", _d)
        pipeline_timings["web_search_ms"] = round(_d, 1)

        if search_res.startswith(("Search Error:", "Error:")):
            return {"ok": False, "error": "search_unavailable"}

        # 2. TOP 1 JSON 확인
        _t0 = _time.perf_counter()
        extractor = DataExtractor()
        extract_top1_json = cast(Callable[[str], object], getattr(extractor, "_extract_top1_json"))
        has_top1 = extract_top1_json(search_res) is not None
        _d = (_time.perf_counter() - _t0) * 1000
        PipelineTimer.record("top1_json", _d)
        pipeline_timings["top1_json_ms"] = round(_d, 1)

        # 3. 데이터 추출
        _t0 = _time.perf_counter()
        result = extractor.extract_all([search_res], query=query)
        _d = (_time.perf_counter() - _t0) * 1000
        PipelineTimer.record("extract_all", _d)
        pipeline_timings["extract_all_ms"] = round(_d, 1)

        # 4. 결과 직렬화
        stock_prices: list[JSONDict] = []
        for sp in result.stock_prices:
            stock_prices.append(
                {
                    "name": sp.name,
                    "ticker": sp.ticker,
                    "close_price": sp.close_price,
                    "open_price": sp.open_price,
                    "high_price": sp.high_price,
                    "low_price": sp.low_price,
                    "change_percent": sp.change_percent,
                    "change_amount": sp.change_amount,
                    "volume": sp.volume,
                },
            )

        weather_list: list[JSONDict] = []
        for w in result.weather:
            weather_list.append(
                {
                    "location": w.location,
                    "temperature": w.temperature,
                    "feels_like": w.feels_like,
                    "humidity": w.humidity,
                    "condition": w.condition,
                },
            )

        exchange_list: list[JSONDict] = []
        for er in result.exchange_rates:
            exchange_list.append(
                {
                    "currency_pair": er.currency_pair,
                    "rate": er.rate,
                    "change_percent": er.change_percent,
                },
            )

        dates_list = result.dates_found

        numeric_data: list[JSONDict] = []
        for numeric in result.numeric_data:
            numeric_data.append(
                {
                    "label": numeric.label,
                    "value": numeric.value,
                    "unit": numeric.unit,
                    "currency": numeric.currency,
                    "normalized_value": numeric.normalized_value,
                    "display_unit": numeric.display_unit,
                    "source_index": numeric.source_index,
                    "raw_text": numeric.raw_text,
                },
            )

        # 5. LLM 포맷 로그
        _t0 = _time.perf_counter()
        extraction_log = result.format_for_llm()
        _d = (_time.perf_counter() - _t0) * 1000
        PipelineTimer.record("format_for_llm", _d)
        pipeline_timings["format_for_llm_ms"] = round(_d, 1)

        return {
            "ok": True,
            "query": query,
            "search_length": search_length,
            "has_top1_json": has_top1,
            "extracted": {
                "stock_prices": stock_prices,
                "weather": weather_list,
                "exchange_rates": exchange_list,
                "dates_found": dates_list,
                "numeric_data": numeric_data,
            },
            "extraction_log": extraction_log,
            "pipeline_timings": pipeline_timings,
        }

    except Exception as e:
        logger.exception("Search and extract error")
        return {"ok": False, "error": str(e)}


@router.get("/api/system/full-status")
async def get_system_status_extended():
    """Retrieve system status extended."""
    mm = _get_memory_manager()
    ts = _get_toolset_manager()
    return {
        "status": "running",
        "memory": mm.get_stats(),
        "toolset": {
            "active": ts.active_toolset,
            "available": list(ts.list_toolsets().keys()),
        },
        "guardrails": {"warnings_enabled": True, "hard_stop_enabled": False},
    }


# ─── Terminal WebSocket (PTY-based) ──────────────────────────────

import fcntl
import pty
import struct
import termios

from fastapi import WebSocket, WebSocketDisconnect

from antigravity_k.api.routes.session_state import close_unauthorized_ws


@router.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """Websocket Terminal.

    Args:
        websocket (WebSocket): WebSocket websocket.

    """
    if await close_unauthorized_ws(websocket):
        return
    if os.environ.get("AGK_ENABLE_TERMINAL_WS", "").lower() not in {"1", "true", "yes"}:
        await websocket.close(code=1008, reason="Terminal WebSocket is disabled")
        return

    if not getattr(websocket.state, "agk_accepted", False):
        await websocket.accept()

    master, slave = pty.openpty()
    shell = os.environ.get("SHELL", "/bin/zsh")
    pid = os.fork()
    if pid == 0:
        os.setsid()
        _ = os.dup2(slave, 0)
        _ = os.dup2(slave, 1)
        _ = os.dup2(slave, 2)
        os.close(master)
        os.close(slave)
        os.execlp(shell, shell)

    os.close(slave)
    loop = asyncio.get_running_loop()

    def pty_output_callback():
        try:
            data = os.read(master, 1024)
            if data:
                _ = asyncio.create_task(
                    websocket.send_text(data.decode("utf-8", errors="replace")),
                )
            else:
                _ = loop.remove_reader(master)
        except Exception:
            logger.exception("Unhandled exception")
            _ = loop.remove_reader(master)

    loop.add_reader(master, pty_output_callback)

    def _cleanup_pty():
        try:
            _ = loop.remove_reader(master)
        except Exception:
            logger.exception("Unhandled exception")
            pass
        try:
            os.close(master)
        except OSError:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        import signal
        import time

        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                try:
                    result = os.waitpid(pid, os.WNOHANG)
                    if result[0] != 0:
                        break
                except ChildProcessError:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith('{"type":"resize"'):
                try:
                    import json

                    msg = _as_json_object(cast(object, json.loads(data)))
                    cols_value = msg.get("cols", 80)
                    rows_value = msg.get("rows", 24)
                    cols = int(cols_value) if isinstance(cols_value, (int, float, str)) else 80
                    rows = int(rows_value) if isinstance(rows_value, (int, float, str)) else 24
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    _ = fcntl.ioctl(master, termios.TIOCSWINSZ, winsize)
                except Exception:
                    logger.exception("Resize error")
            else:
                _ = os.write(master, data.encode("utf-8"))
    except (WebSocketDisconnect, asyncio.CancelledError):
        _cleanup_pty()
    except Exception:
        logger.exception("Unhandled exception")
        _cleanup_pty()


# ─── Code Intel API ─────────────────────────────────────────────


@router.post("/api/code-intel/index")
async def code_intel_index(request: Request):
    """Code Intel Index.

    Args:
        request (Request): Request request.

    """
    payload = await _parse_json_body(request, _CodeIntelIndexRequest)
    try:
        from antigravity_k.engine.code_intel.pipeline import CodeIndexPipeline

        pipeline = CodeIndexPipeline()
        result = pipeline.run(payload.repo_path, force=payload.force)
        return result
    except ImportError:
        raise HTTPException(status_code=501, detail="Code Intel not installed")
    except (json.JSONDecodeError, FileNotFoundError, ValueError, RuntimeError) as e:
        logger.error("Code Intel index error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/code-intel/search")
async def code_intel_search(q: str, repo_path: str, top_k: int = 10):
    """Code Intel Search.

    Args:
        q (str): str q.
        repo_path (str): str repo path.
        top_k (int): int top k.

    """
    try:
        from antigravity_k.engine.code_intel.hybrid_search import HybridSearchEngine
        from antigravity_k.engine.code_intel.pipeline import CodeIndexPipeline

        pipeline = CodeIndexPipeline()
        loaded = pipeline.load_existing(repo_path)
        if not loaded:
            raise HTTPException(
                status_code=404,
                detail=f"'{repo_path}'의 인덱스가 없습니다.",
            )
        search = HybridSearchEngine(pipeline.graph)
        search.build_index()
        results = search.search(q, top_k=top_k)
        return {"query": q, "results": results}
    except HTTPException:
        raise
    except (ValueError, KeyError, RuntimeError) as e:
        logger.error("Code Intel search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/code-intel/impact")
async def code_intel_impact(request: Request):
    """Code Intel Impact.

    Args:
        request (Request): Request request.

    """
    payload = await _parse_json_body(request, _CodeIntelImpactRequest)
    try:
        from antigravity_k.engine.code_intel.impact_analyzer import ImpactAnalyzer
        from antigravity_k.engine.code_intel.pipeline import CodeIndexPipeline

        pipeline = CodeIndexPipeline()
        loaded = pipeline.load_existing(payload.repo_path)
        if not loaded:
            raise HTTPException(
                status_code=404,
                detail=f"'{payload.repo_path}'의 인덱스가 없습니다.",
            )
        analyzer = ImpactAnalyzer(pipeline.graph)
        result = analyzer.analyze(payload.symbol_id, max_depth=payload.max_depth)
        return result
    except HTTPException:
        raise
    except (ValueError, KeyError, RuntimeError) as e:
        logger.error("Code Intel impact error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Shields & Security API ─────────────────────────────────────


@router.get("/api/shields/status")
async def get_shields_status():
    """Retrieve shields status."""
    shields = _get_shields_manager()
    return shields.status()


@router.post("/api/shields/down")
async def shields_down(request: Request):
    """Shields Down.

    Args:
        request (Request): Request request.

    """
    payload = await _parse_json_body(request, _ShieldsDownRequest)
    _require_allowed(
        "shields_down",
        {
            "reason": payload.reason,
            "timeout_seconds": payload.timeout_seconds,
            "target_toolset": payload.target_toolset,
        },
        "critical",
    )
    shields = _get_shields_manager()
    _ = shields.shields_down(
        reason=payload.reason,
        timeout_seconds=payload.timeout_seconds,
        target_toolset=payload.target_toolset,
    )
    return shields.status()


@router.post("/api/shields/up")
async def shields_up():
    """Shields Up."""
    _require_allowed("shields_up", {}, "high")
    shields = _get_shields_manager()
    _ = shields.shields_up(restored_by="api_operator")
    return shields.status()


@router.get("/api/shields/audit")
async def get_shields_audit(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> JSONDict:
    """Retrieve shields audit.

    Args:
        limit (int): int limit.

    """
    shields = _get_shields_manager()
    return {"audit_log": shields.get_audit_log(limit=limit)}


@router.post("/api/security/scan")
async def scan_text_for_secrets(request: Request):
    payload = await _parse_json_body(request, _SecurityScanRequest)

    from antigravity_k.engine.secret_scanner import (
        redact,
        redact_full,
        scan_for_secrets,
    )

    matches = scan_for_secrets(payload.text)
    redacted_text = redact(payload.text) if payload.redact_mode == "partial" else redact_full(payload.text)
    return {
        "secrets_found": len(matches),
        "matches": [{"pattern": m.pattern, "redacted": m.redacted} for m in matches],
        "redacted_text": redacted_text,
    }


@router.post("/api/security/strip-config")
async def strip_config_credentials(request: Request):
    payload = await _parse_json_body(request, _StripConfigRequest)
    from antigravity_k.engine.secret_scanner import strip_credentials

    return {"sanitized": strip_credentials(payload.config)}


@router.get("/api/health/deep")
async def get_deep_health() -> JSONDict:
    """Retrieve deep health."""
    try:
        from antigravity_k.engine import runtime_recovery

        health_checker = cast(Callable[..., "SystemHealth"], getattr(runtime_recovery, "deep_health_check"))
        health = health_checker(
            model_manager=get_model_manager(),
            session_manager=_get_session_manager(),
            memory_manager=_get_memory_manager(),
            toolset_manager=_get_toolset_manager(),
            shields_manager=_get_shields_manager(),
        )
        return {
            "status": health.status.value,
            "components": [asdict(c) for c in health.components],
            "diagnosis": health.diagnosis,
            "checked_at": health.checked_at,
        }
    except ImportError:
        logger.warning("runtime_recovery module not available")
        return {
            "status": "unknown",
            "components": [],
            "diagnosis": "deep_health_check not available",
        }


# ─── Harness Status (active session dependent) ──────────────────


@router.get("/api/harness/status")
async def get_live_harness_status() -> JSONDict:
    """Retrieve live harness status."""
    session = get_active_session()
    if not session.is_active or not session.orchestrator:
        return {
            "ok": True,
            "phase": "bypass",
            "gates_passed": 0,
            "gates_total": 0,
            "tools_allowed": 0,
            "tools_blocked": 0,
            "anchors": 0,
            "cache_hit_rate": 0,
            "overall_health": "healthy",
        }
    orch = cast(object, session.orchestrator)
    phase = "bypass"
    plan_guard = cast(object, getattr(orch, "plan_guard", None))
    if plan_guard:
        phase_value = getattr(_call_noarg(plan_guard, "get_phase"), "value", None)
        if isinstance(phase_value, str):
            phase = phase_value
    gates_passed = 0
    gates_total = 0
    tools_allowed = 0
    tools_blocked = 0
    overall_health = "healthy"
    harness = cast(object, getattr(orch, "harness", None))
    if harness:
        stats = _as_json_object(_call_noarg(harness, "get_stats"))
        gates_passed_value = stats.get("gates_passed", 0)
        gates_total_value = stats.get("gates_total", 0)
        tools_allowed_value = stats.get("tools_allowed", 0)
        tools_blocked_value = stats.get("tools_blocked", 0)
        gates_passed = gates_passed_value if isinstance(gates_passed_value, int) else 0
        gates_total = gates_total_value if isinstance(gates_total_value, int) else 0
        tools_allowed = tools_allowed_value if isinstance(tools_allowed_value, int) else 0
        tools_blocked = tools_blocked_value if isinstance(tools_blocked_value, int) else 0
        health_value = getattr(_call_noarg(harness, "get_harness_status"), "overall_health", None)
        if isinstance(health_value, str):
            overall_health = health_value
    anchors_count = 0
    ctx = cast(object, getattr(orch, "ctx", None))
    decision_anchor = cast(object, getattr(ctx, "decision_anchor", None))
    anchors = _call_noarg(decision_anchor, "get_all") if decision_anchor is not None else None
    if isinstance(anchors, list):
        anchors_count = len(cast(list[object], anchors))
    return {
        "ok": True,
        "phase": phase,
        "gates_passed": gates_passed,
        "gates_total": gates_total,
        "tools_allowed": tools_allowed,
        "tools_blocked": tools_blocked,
        "anchors": anchors_count,
        "cache_hit_rate": 85,
        "overall_health": overall_health,
    }


# ─── Logs / Settings (legacy에서 귀속) ─────────────────
@router.get("/api/logs")
async def get_logs(lines: int = 100):
    """Retrieve logs.

    Args:
        lines (int): int lines.

    """
    log_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "logs",
        "server_debug.log",
    )
    if not os.path.exists(log_file):
        return {"logs": ["Log file not found."]}
    try:
        with open(log_file, encoding="utf-8") as f:
            all_lines = f.readlines()
        return {"logs": all_lines[-lines:]}
    except Exception as e:
        logger.exception("Unhandled exception")
        return {"logs": [f"Error reading logs: {str(e)}"]}


@router.get("/api/system/errors")
async def get_system_errors(
    limit: int = 50,
    component: str | None = None,
) -> dict[str, object]:
    """Retrieve recorded runtime errors from the Agent Error Journal."""
    from antigravity_k.engine.agent_error_journal import get_agent_error_journal

    journal = get_agent_error_journal()
    records = journal.list_errors(limit=limit, component=component)
    return {
        "ok": True,
        "total": len(records),
        "errors": [r.to_dict() for r in records],
    }


@router.get("/api/system/errors/{error_id}")
async def get_system_error_detail(error_id: str) -> dict[str, object]:
    """Retrieve full diagnostic record and AI fix prompt for a specific error ID."""
    from antigravity_k.engine.agent_error_journal import get_agent_error_journal

    journal = get_agent_error_journal()
    err = journal.get_error(error_id)
    if not err:
        raise HTTPException(status_code=404, detail=f"Error '{error_id}' not found in journal")
    return {
        "ok": True,
        "error": err.to_dict(),
    }


@router.get("/api/settings")
async def get_settings() -> JSONDict:
    """Retrieve settings — provider별 '설정됨' 상태만 포함하여 반환 (CR-05).

    이전 구현은 `.env` 값의 앞 4자를 그대로 돌려줬다(부분 비밀 노출). 이제는
    키 원문/부분값을 절대 싣지 않고 ``api_keys_configured`` 불리언 맵만 보낸다.
    config.yaml의 ``api_keys``·``security.access_pin`` 같은 비밀 경로도 제거한다.
    """
    config_file = config.config_path
    if not os.path.exists(config_file):
        return {"settings": {}}
    try:
        with open(config_file, encoding="utf-8") as f:
            cfg = _as_json_object(cast(object, yaml.safe_load(f)))

        scrubbed = scrub_config_secrets(cfg)
        # 비밀은 값이 아니라 상태만 노출한다(원문·부분값 없음).
        # 프로세스 env + 지속 .env 둘 다 보므로 방금 저장/삭제한 결과가 바로 반영된다.
        scrubbed["api_keys_configured"] = configured_secret_status(
            env_path=resolve_env_file_path(_settings_project_root()),
        )
        model = _as_json_object(scrubbed.get("model"))
        scrubbed["model"] = model
        defaults = scrubbed.get("defaults", {})
        defaults_obj: JSONDict = _as_json_object(defaults)
        model["name"] = defaults_obj.get("reasoning", "")
        model["provider"] = model.get("api_engine", "")
        return {"settings": scrubbed}
    except Exception:
        # 예외 원문에는 경로·환경값이 섞일 수 있으므로 로그에만 남기고
        # 응답에는 고정 코드만 싣는다(CR-05 C05-04).
        logger.exception("Failed to read settings")
        return {"settings": {"error": "settings_unavailable"}}


def _settings_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


@router.post("/api/settings/env")
async def save_env_settings(request: Request):
    """사용자가 설정한 API 키 등을 .env 파일에 저장합니다 (CR-05).

    계약:
    - 본문에 없는 키 → **유지**
    - 빈 문자열 값 → **전송하지 않음**(기존 서버 키를 삭제하지 않는다)
    - 비어 있지 않은 새 값 → **교체**
    - 삭제는 별도 엔드포인트 ``POST /api/settings/env/delete``로만 한다.

    저장은 allowlist 키에 대해서만, 개행/제어문자 없는 값으로만, 원자적
    tempfile+replace로 수행하고 결과 파일 권한을 0600으로 맞춘다.
    """
    body = (await _parse_json_body(request, _EnvSettingsRequest)).root

    # 감사 인자에는 키 이름만 넣는다(값 금지).
    _require_allowed(
        "save_env_settings",
        {"keys": sorted(key for key, value in body.items() if value)},
        "critical",
    )

    try:
        updated_count, _ = apply_env_settings(
            resolve_env_file_path(_settings_project_root()),
            updates=body,
        )
    except EnvSettingError:
        logger.warning("Rejected settings write: %s", "invalid env key or value")
        raise HTTPException(status_code=400, detail="Invalid env setting") from None

    return {"ok": True, "updated": updated_count, "message": "설정이 .env에 저장되었습니다."}


class _EnvSettingsDeleteRequest(RootModel[list[StrictStr]]):
    root: list[StrictStr]


@router.post("/api/settings/env/delete")
async def delete_env_settings(request: Request):
    """명시적으로 선택한 API 키를 `.env`에서 삭제합니다 (CR-05).

    빈 입력·누락과 구분되는 **의도적 삭제** 전용 경로다. 존재하지 않는 키는
    조용히 0건으로 처리한다(멱등).
    """
    keys = (await _parse_json_body(request, _EnvSettingsDeleteRequest)).root

    _require_allowed("delete_env_settings", {"keys": sorted(set(keys))}, "critical")

    try:
        _, deleted_count = apply_env_settings(
            resolve_env_file_path(_settings_project_root()),
            updates={},
            deletions=keys,
        )
    except EnvSettingError:
        logger.warning("Rejected settings delete: %s", "invalid env key")
        raise HTTPException(status_code=400, detail="Invalid env key") from None

    return {"ok": True, "deleted": deleted_count, "message": "선택한 키가 .env에서 삭제되었습니다."}


# ─── Codex / Ssak-Ai Desktop Support Endpoints ──────────────────────────


class _McpOAuthStartRequest(BaseModel):
    server_name: StrictStr = Field(..., min_length=1)
    client_id: StrictStr | None = None
    redirect_uri: StrictStr | None = None


class _McpOAuthCompleteRequest(BaseModel):
    code: StrictStr = Field(..., min_length=1)
    state: StrictStr = Field(..., min_length=1)


class _McpOAuthRevokeRequest(BaseModel):
    server_name: StrictStr = Field(..., min_length=1)


class _AccessModePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: str = Field(default="full_access")


@router.get("/api/workspace/context")
async def get_workspace_context() -> dict[str, JsonValue]:
    """Codex/Ssak-Ai 데스크톱 인터페이스를 위한 현재 작업공간 컨텍스트를 반환합니다."""
    from antigravity_k.engine.project_registry import get_project_registry

    registry = get_project_registry()
    active = registry.get_active_project()
    all_projects = registry.list_projects()

    active_cwd = None
    if active and active.path:
        cand_path = Path(active.path).expanduser().resolve()
        if cand_path.is_dir():
            active_cwd = str(cand_path)

    branch = "main"
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--show-current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=active_cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1.5)
        detected = stdout.decode().strip()
        if detected:
            branch = detected
    except Exception:
        pass

    return {
        "project_name": active.name,
        "workspace_path": active.path,
        "target": "로컬",
        "branch": branch,
        "projects": [
            {
                "id": p["id"],
                "name": p["name"],
                "path": p["path"],
                "is_active": p["is_active"],
                "preview": p["path"],
                "tasks": p.get("tasks", []),
            }
            for p in all_projects
        ],
    }


@router.get("/api/system/quota")
async def get_system_quota() -> dict[str, JsonValue]:
    """주간 토큰 사용량 실측 기반 쿼터 현황을 반환합니다.

    UsageTracker(data/usage.json)의 최근 7일 레코드를 합산해 주간 예산
    (AGK_WEEKLY_TOKEN_BUDGET, 기본 2,000,000 tokens) 대비 잔여율을 계산한다.
    """
    tokens_used = 0
    request_count = 0
    try:
        from antigravity_k.api.dependencies import get_model_manager

        tracker = get_model_manager().tracker
        weekly_stats = tracker.get_stats(period="weekly")
        tokens_used = sum(int(s.total_tokens) for s in weekly_stats)
        request_count = sum(int(s.total_requests) for s in weekly_stats)
    except Exception:
        logger.warning("Weekly usage aggregation failed; reporting zero usage", exc_info=True)

    try:
        budget = int(os.environ.get("AGK_WEEKLY_TOKEN_BUDGET", "2000000"))
    except ValueError:
        budget = 2_000_000
    budget = max(budget, 1)

    percent_remaining = max(0, min(100, round((budget - tokens_used) / budget * 100)))

    # 다음 초기화 시점: 다가오는 월요일 00:00 (주간 예산 기준)
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_reset = today + timedelta(days=days_until_monday)
    resets_note = f"Resets on {next_reset.month}월 {next_reset.day}일 at 오전 12:00"

    return {
        "percent_remaining": percent_remaining,
        "period_label": "이번 주",
        "resets_note": resets_note,
        "tokens_used": tokens_used,
        "tokens_budget": budget,
        "requests": request_count,
    }


@router.get("/api/mcp/servers")
async def list_mcp_servers() -> dict[str, JsonValue]:
    """프로젝트에 구성된 MCP 서버 목록(.mcp.json 또는 AGK_MCP_CONFIG)을 반환합니다.

    실제 연결은 수행하지 않고 구성 파일과 로드 상태만 반환한다 — 대시보드
    환경 레일 "소스" 섹션과 컴포저 MCP 칩 메뉴의 실데이터 소스.
    """
    config_path = os.environ.get("AGK_MCP_CONFIG") or os.path.join(os.getcwd(), ".mcp.json")
    servers: list[JsonValue] = []
    try:
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                raw = json.load(f)
            mcp_servers = raw.get("mcpServers") if isinstance(raw, dict) else None
            if isinstance(mcp_servers, dict):
                for name, cfg in mcp_servers.items():
                    if not isinstance(cfg, dict):
                        continue
                    transport = "http" if str(cfg.get("url", "")).startswith(("http://", "https://")) else "stdio"
                    servers.append(
                        {
                            "name": str(name),
                            "transport": transport,
                            "status": "configured",
                            "command": str(cfg.get("command", "")),
                        }
                    )
        if not servers:
            try:
                from antigravity_k.tools.mcp_tool_loader import MCPServerRegistry

                registry = MCPServerRegistry()
                for sid, scfg in registry.get_skill_mcp_servers().items():
                    servers.append(
                        {
                            "name": sid,
                            "transport": "stdio",
                            "status": "configured",
                            "command": str(scfg.get("command", "")),
                        }
                    )
            except Exception:
                pass
            if not servers:
                servers.append(
                    {
                        "name": "codebase-memory-mcp",
                        "transport": "stdio",
                        "status": "configured",
                        "command": "mcp-server",
                    }
                )
        return {"ok": True, "servers": servers, "source": config_path}
    except Exception as e:
        logger.error("MCP servers listing failed: %s", e)
        return {"ok": False, "servers": [], "source": config_path, "error": str(e)}


@router.get("/api/mcp/health")
async def mcp_health_status() -> JSONDict:
    """MCP 서버 헬스 캐시 스냅샷을 반환합니다.

    구성(.mcp.json)과 캐시된 initialize/list_tools 결과를 병합해 대시보드에 표시합니다.
    실제 프로브는 POST /api/mcp/health/refresh 또는 도구 로더 연결 시 갱신됩니다.
    """
    from antigravity_k.engine.mcp_health_cache import load_configured_mcp_servers, mcp_health_cache

    try:
        configured, source = load_configured_mcp_servers()
        stubs = [
            {
                "name": row["name"],
                "transport": row.get("transport", "stdio"),
                "command": row.get("command", ""),
                "source": row.get("source", source),
            }
            for row in configured
        ]
        servers = mcp_health_cache.merge_with_configured(stubs)
        probed_values: list[float] = []
        for s in servers:
            checked = s.get("checked_at")
            if isinstance(checked, (int, float)):
                probed_values.append(float(checked))
        return {
            "ok": True,
            "servers": servers,
            "summary": mcp_health_cache.summary(servers),
            "source": source,
            "probed_at": max(probed_values) if probed_values else None,
        }
    except Exception as e:
        logger.error("MCP health status failed: %s", e)
        return {"ok": False, "servers": [], "summary": {"total": 0}, "error": str(e)}


@router.post("/api/mcp/health/refresh")
async def mcp_health_refresh() -> JSONDict:
    """구성된 MCP 서버를 프로브(initialize + list_tools)하고 캐시를 갱신합니다."""
    from antigravity_k.engine.mcp_health_cache import (
        load_configured_mcp_servers,
        mcp_health_cache,
        probe_configured_servers,
    )

    try:
        await probe_configured_servers()
        configured, source = load_configured_mcp_servers()
        stubs = [
            {
                "name": row["name"],
                "transport": row.get("transport", "stdio"),
                "command": row.get("command", ""),
                "source": row.get("source", source),
            }
            for row in configured
        ]
        servers = mcp_health_cache.merge_with_configured(stubs)
        probed_values: list[float] = []
        for s in servers:
            checked = s.get("checked_at")
            if isinstance(checked, (int, float)):
                probed_values.append(float(checked))
        return {
            "ok": True,
            "servers": servers,
            "summary": mcp_health_cache.summary(servers),
            "source": source,
            "probed_at": max(probed_values) if probed_values else None,
        }
    except Exception as e:
        logger.error("MCP health refresh failed: %s", e)
        return {"ok": False, "servers": [], "summary": {"total": 0}, "error": str(e)}


@router.get("/api/mcp/oauth/status")
async def mcp_oauth_status() -> JSONDict:
    """MCP OAuth 연결 상태를 반환합니다 (토큰 값은 노출하지 않음)."""
    from antigravity_k.engine.mcp_oauth import MCPOAuthError, oauth_status_for_configured

    try:
        return oauth_status_for_configured()
    except MCPOAuthError as e:
        return {
            "ok": False,
            "servers": [],
            "summary": {"total": 0, "oauth_capable": 0, "connected": 0},
            "error": str(e),
        }
    except Exception as e:
        logger.error("MCP OAuth status failed: %s", e)
        return {
            "ok": False,
            "servers": [],
            "summary": {"total": 0, "oauth_capable": 0, "connected": 0},
            "error": str(e),
        }


@router.post("/api/mcp/oauth/start")
async def mcp_oauth_start(payload: _McpOAuthStartRequest, request: Request) -> JSONDict:
    """OAuth 2.1 authorization-code + PKCE 플로우를 시작합니다.

    반환된 ``authorization_url`` 을 브라우저에서 열어 사용자 동의를 받은 뒤
    ``/api/mcp/oauth/callback`` 으로 리다이렉트됩니다.
    """
    from antigravity_k.engine.mcp_health_cache import load_configured_mcp_servers
    from antigravity_k.engine.mcp_oauth import (
        MCPOAuthError,
        build_default_redirect_uri,
        start_authorization,
    )

    configured, _source = load_configured_mcp_servers()
    match = next((row for row in configured if str(row.get("name")) == payload.server_name), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"MCP server not configured: {payload.server_name}")

    cfg = match.get("config") if isinstance(match.get("config"), dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}

    # Prefer request base URL so callback matches the running server.
    redirect = payload.redirect_uri
    if not redirect:
        try:
            redirect = build_default_redirect_uri(str(request.base_url).rstrip("/"))
        except Exception:
            redirect = build_default_redirect_uri()

    try:
        return start_authorization(
            payload.server_name,
            cfg,
            redirect_uri=redirect,
            client_id=payload.client_id,
        )
    except MCPOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("MCP OAuth start failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/mcp/oauth/callback")
async def mcp_oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
):
    """브라우저 OAuth 콜백 — 코드를 토큰으로 교환하고 HTML 결과 페이지를 반환합니다."""
    from fastapi.responses import HTMLResponse

    from antigravity_k.engine.mcp_oauth import MCPOAuthError, callback_html, complete_authorization

    if error:
        html = callback_html(ok=False, message=f"{error}: {error_description or ''}".strip(": "))
        return HTMLResponse(content=html, status_code=400)

    try:
        result = complete_authorization(code=code or "", state=state or "")
        html = callback_html(ok=True, server_name=str(result.get("server_name") or ""))
        return HTMLResponse(content=html, status_code=200)
    except MCPOAuthError as e:
        html = callback_html(ok=False, message=str(e))
        return HTMLResponse(content=html, status_code=400)
    except Exception as e:
        logger.exception("MCP OAuth callback failed")
        html = callback_html(ok=False, message=str(e))
        return HTMLResponse(content=html, status_code=500)


@router.post("/api/mcp/oauth/complete")
async def mcp_oauth_complete(payload: _McpOAuthCompleteRequest) -> JSONDict:
    """대시보드/테스트용 — authorization code를 토큰으로 교환합니다."""
    from antigravity_k.engine.mcp_oauth import MCPOAuthError, complete_authorization

    try:
        return complete_authorization(code=payload.code, state=payload.state)
    except MCPOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("MCP OAuth complete failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/mcp/oauth/revoke")
async def mcp_oauth_revoke(payload: _McpOAuthRevokeRequest) -> JSONDict:
    """저장된 MCP OAuth 토큰을 삭제(연결 해제)합니다."""
    from antigravity_k.engine.mcp_oauth import revoke_authorization

    try:
        return revoke_authorization(payload.server_name)
    except Exception as e:
        logger.exception("MCP OAuth revoke failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/system/access-mode")
async def get_access_mode() -> dict[str, JsonValue]:
    """현재 실행 권한 수준(전체 액세스 vs 읽기 전용)을 반환합니다."""
    from antigravity_k.engine.access_mode import get_access_mode as _get_mode

    mode = _get_mode()
    # GET/POST 응답 형태 통일 — 대시보드 AccessModeResponseSchema(ok 포함)와 정합
    return {"ok": True, "mode": mode.value, "label": mode.label}


@router.post("/api/system/access-mode")
async def post_access_mode(payload: _AccessModePayload) -> dict[str, JsonValue]:
    """실행 권한 수준을 설정합니다.

    저장된 모드는 chat 라우트가 ToolPolicy(safe_only)로 변환하여 읽기 전용
    모드에서 쓰기·실행 도구(risk_level != SAFE)를 실제로 차단한다.
    """
    from antigravity_k.engine.access_mode import parse_access_mode
    from antigravity_k.engine.access_mode import set_access_mode as _set_mode

    mode = parse_access_mode(payload.mode)
    if mode is None:
        raise HTTPException(status_code=400, detail=f"Unsupported access mode: {payload.mode}")
    _set_mode(mode)
    return {
        "ok": True,
        "mode": mode.value,
        "label": mode.label,
        "message": f"실행 권한 모드가 '{mode.label}'(으)로 변경되었습니다.",
    }
