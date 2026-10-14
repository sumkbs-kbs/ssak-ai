"""Security & Shields API — 보호 레벨 제어, 시크릿 스캔, 심층 헬스체크."""

import json
import logging
import os
from collections.abc import Mapping
from typing import ClassVar, Literal, cast

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, JsonValue, StrictInt, StrictStr, TypeAdapter, ValidationError

from antigravity_k.config import config
from antigravity_k.engine.runtime_recovery import deep_health_check
from antigravity_k.engine.secret_scanner import redact, redact_full, scan_for_secrets, strip_credentials
from antigravity_k.engine.shields import ShieldsManager
from antigravity_k.engine.toolset_manager import ToolsetManager
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.security")

_toolset_manager: ToolsetManager | None = None


class _StripConfigRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    config: JsonValue = {}


class _SecurityScanRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    text: StrictStr = ""
    redact_mode: Literal["partial", "full"] = "partial"


class _ShieldsDownRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    reason: StrictStr | None = None
    timeout_seconds: StrictInt | None = None
    target_toolset: StrictStr = "full"


_YAML_CONFIG_ADAPTER = TypeAdapter(dict[str, JsonValue])
_TOOLSET_CONFIG_ADAPTER = TypeAdapter(dict[str, dict[str, JsonValue]])


async def _parse_strip_config_body(request: Request) -> _StripConfigRequest:
    try:
        return _StripConfigRequest.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


async def _parse_security_scan_body(request: Request) -> _SecurityScanRequest:
    try:
        return _SecurityScanRequest.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


async def _parse_shields_down_body(request: Request) -> _ShieldsDownRequest:
    try:
        return _ShieldsDownRequest.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


def _permission_gate() -> PermissionGate:
    return PermissionGate(project_root=str(config.paths.project_root), mode="auto-pilot")


def _load_yaml_config(config_file: str) -> dict[str, JsonValue]:
    with open(config_file, encoding="utf-8") as f:
        raw_config = cast(JsonValue, yaml.safe_load(f))
    return _YAML_CONFIG_ADAPTER.validate_python(raw_config)


def _require_allowed(tool_name: str, args: Mapping[str, JsonValue], risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for {tool_name}: {decision.permission.value}",
        )


def _get_memory_manager():
    from antigravity_k.api.dependencies import get_memory_manager

    return get_memory_manager()


def _get_model_manager():
    from antigravity_k.api.dependencies import get_model_manager

    return get_model_manager()


def _get_session_manager():
    from antigravity_k.api.dependencies import get_session_manager

    return get_session_manager()


def _get_toolset_manager() -> ToolsetManager:
    global _toolset_manager
    if _toolset_manager is None:
        try:
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "config.yaml",
            )
            if os.path.exists(config_file):
                cfg = _load_yaml_config(config_file)
                toolsets = _TOOLSET_CONFIG_ADAPTER.validate_python(cfg.get("toolsets", {}))
                _toolset_manager = ToolsetManager.from_config(toolsets)
            else:
                _toolset_manager = ToolsetManager()
        except Exception:
            logger.exception("Unhandled exception")
            _toolset_manager = ToolsetManager()
    return _toolset_manager


_shields_manager: ShieldsManager | None = None


def _get_shields_manager() -> ShieldsManager:
    global _shields_manager
    if _shields_manager is None:
        try:
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "config.yaml",
            )
            shields_config = {}
            if os.path.exists(config_file):
                cfg = _load_yaml_config(config_file)
                shields_config = _YAML_CONFIG_ADAPTER.validate_python(cfg.get("shields", {}))
            _shields_manager = ShieldsManager.from_config(
                shields_config,
                toolset_manager=_get_toolset_manager(),
            )
        except Exception:
            logger.exception("Unhandled exception")
            _shields_manager = ShieldsManager(
                toolset_manager=_get_toolset_manager(),
            )
    return _shields_manager


@router.post("/api/shields/down")
async def shields_down(request: Request):
    """Shields를 내립니다 (시간 제한 권한 완화).

    Body:
        reason: 변경 사유 (선택)
        timeout_seconds: 타임아웃 초 (선택, 기본 300)
        target_toolset: 완화 시 toolset (선택, 기본 "full")
    """
    body = await _parse_shields_down_body(request)
    _require_allowed(
        "shields_down",
        {
            "reason": body.reason,
            "timeout_seconds": body.timeout_seconds,
            "target_toolset": body.target_toolset,
        },
        "critical",
    )
    shields = _get_shields_manager()
    _ = shields.shields_down(
        reason=body.reason,
        timeout_seconds=body.timeout_seconds,
        target_toolset=body.target_toolset,
    )
    return shields.status()


@router.post("/api/shields/up")
async def shields_up():
    """Shields를 올립니다 (보호 복원)."""
    _require_allowed("shields_up", {}, "high")
    shields = _get_shields_manager()
    _ = shields.shields_up(restored_by="api_operator")
    return shields.status()


@router.post("/api/security/scan")
async def scan_text_for_secrets(request: Request):
    """텍스트에서 시크릿을 스캔합니다.

    Body:
        text: 스캔할 텍스트
        redact_mode: "partial" (기본) | "full"
    """
    payload = await _parse_security_scan_body(request)

    matches = scan_for_secrets(payload.text)
    redacted_text = redact(payload.text) if payload.redact_mode == "partial" else redact_full(payload.text)

    return {
        "secrets_found": len(matches),
        "matches": [{"pattern": m.pattern, "redacted": m.redacted} for m in matches],
        "redacted_text": redacted_text,
    }


@router.post("/api/security/strip-config")
async def strip_config_credentials(request: Request):
    """설정 딕셔너리에서 민감 필드를 제거합니다.

    Body:
        config: 필터링할 설정 딕셔너리
    """
    payload = await _parse_strip_config_body(request)
    return {"sanitized": strip_credentials(payload.config)}


@router.get("/api/health/deep")
async def get_deep_health():
    """전체 시스템 깊은 Health Check를 수행합니다.

    인퍼런스, 메모리, 가드레일, shields 등 모든 컴포넌트를 점검합니다.
    """
    from dataclasses import asdict

    health = deep_health_check(
        model_manager=_get_model_manager(),
        session_manager=_get_session_manager(),
        memory_manager=_get_memory_manager(),
        toolset_manager=_get_toolset_manager(),
        shields_manager=_get_shields_manager(),
    )
    return {
        "status": health.status.value,
        "components": [asdict(c) for c in health.components],
    }
