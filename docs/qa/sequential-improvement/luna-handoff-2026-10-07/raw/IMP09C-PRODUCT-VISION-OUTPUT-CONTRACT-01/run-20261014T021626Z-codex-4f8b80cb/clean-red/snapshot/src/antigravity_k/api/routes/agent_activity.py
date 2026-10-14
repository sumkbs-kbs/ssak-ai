"""Agent Activity API — 에이전트 활동 상태 + 감사 로그 조회 엔드포인트.

====================================================================
Sidabari의 패널 활동 추적 + SQLite 감사 로그를 대시보드에 제공합니다.
"""

import logging
import time
from typing import Annotated, TypeAlias, cast

from fastapi import APIRouter, Query
from pydantic import JsonValue

logger = logging.getLogger("antigravity_k.api.routes.agent_activity")

router = APIRouter(prefix="/api/agent")
RouteResponse: TypeAlias = dict[str, JsonValue]
LimitParam = Annotated[int, Query(le=500)]
OptionalTextParam = Annotated[str | None, Query()]
OptionalMinutesParam = Annotated[int | None, Query()]


def _error_response(error: str, **extra: JsonValue) -> RouteResponse:
    response: RouteResponse = {"ok": False, "error": error}
    response.update(extra)
    return response


@router.get("/activity")
async def get_agent_activity() -> RouteResponse:
    """모든 에이전트의 현재 활동 상태를 조회합니다.

    Returns:
        패널별 activity 상태 (thinking/idle) + 현재 도구 정보

    """
    try:
        from antigravity_k.engine.panel_activity_tracker import (
            get_panel_activity_tracker,
        )

        tracker = get_panel_activity_tracker()
        activities = tracker.get_all_activities()
        thinking_panels = tracker.get_thinking_panels()

        return {
            "ok": True,
            "activities": cast(JsonValue, activities),
            "thinking_count": len(thinking_panels),
            "thinking_panels": cast(JsonValue, thinking_panels),
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.exception("Activity query failed")
        return _error_response(str(e), activities={})


@router.get("/audit/recent")
async def get_recent_audit_events(
    limit: LimitParam = 50,
    kind: OptionalTextParam = None,
    panel_id: OptionalTextParam = None,
    since_minutes: OptionalMinutesParam = None,
) -> RouteResponse:
    """최근 감사 이벤트를 조회합니다.

    Args:
        limit: 최대 반환 수 (기본 50, 최대 500)
        kind: 이벤트 종류 필터
        panel_id: 패널 ID 필터
        since_minutes: 최근 N분 이내 이벤트만

    """
    try:
        from antigravity_k.engine.audit_db import get_audit_db

        db = get_audit_db()
        if not db.initialized:
            return _error_response("AuditDb not initialized", events=[])

        since_ms = None
        if since_minutes:
            since_ms = int((time.time() - since_minutes * 60) * 1000)

        events = db.query_recent(
            limit=limit,
            kind=kind,
            panel_id=panel_id,
            since_ms=since_ms,
        )

        return {
            "ok": True,
            "events": cast(JsonValue, events),
            "count": len(events),
            "total": db.count_events(since_ms=since_ms),
        }
    except Exception as e:
        logger.exception("Audit query failed")
        return _error_response(str(e), events=[])


@router.get("/audit/tool-stats")
async def get_tool_stats(
    since_minutes: OptionalMinutesParam = 60,
) -> RouteResponse:
    """도구별 호출 통계를 조회합니다.

    Args:
        since_minutes: 최근 N분 이내 통계 (기본 60분)

    """
    try:
        from antigravity_k.engine.audit_db import get_audit_db

        db = get_audit_db()
        if not db.initialized:
            return _error_response("AuditDb not initialized", stats=[])

        since_ms = None
        if since_minutes:
            since_ms = int((time.time() - since_minutes * 60) * 1000)

        stats = db.query_tool_stats(since_ms=since_ms)

        return {
            "ok": True,
            "stats": cast(JsonValue, stats),
            "period_minutes": since_minutes,
        }
    except Exception as e:
        logger.exception("Tool stats query failed")
        return _error_response(str(e), stats=[])


@router.get("/deny-rules/status")
async def get_deny_rules_status(directory: OptionalTextParam = None) -> RouteResponse:
    """현재 deny 패턴 설치 상태를 확인합니다."""
    try:
        from antigravity_k.engine.claude_deny_patterns import (
            get_deny_rules_status,
        )

        if not directory:
            import os

            directory = os.getcwd()

        status = get_deny_rules_status(directory)
        if status:
            status_payload = cast(dict[str, JsonValue], status.to_dict())
            return {"ok": True, "installed": True, **status_payload}
        else:
            return {"ok": True, "installed": False}
    except Exception as e:
        logger.exception("Deny rules status check failed")
        return _error_response(str(e))


@router.post("/deny-rules/install")
async def install_deny_rules(directory: str | None = None) -> RouteResponse:
    """Deny 패턴을 설치합니다."""
    try:
        from antigravity_k.engine.claude_deny_patterns import (
            install_deny_rules as _install,
        )

        if not directory:
            import os

            directory = os.getcwd()

        report = _install(directory)
        report_payload = cast(dict[str, JsonValue], report.to_dict())
        return {"ok": True, **report_payload}
    except Exception as e:
        logger.exception("Deny rules installation failed")
        return _error_response(str(e))
