"""Kanban API — 태스크 보드 CRUD, 워크스페이스 필터, 실시간 브로드캐스트."""

import asyncio
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from antigravity_k.api.routes.session_state import close_unauthorized_ws
from antigravity_k.config import config
from antigravity_k.engine.event_bus import global_event_bus

router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.kanban")

# ─── 상태 ────────────────────────────────────────────────────────

JsonObject = dict[str, object]

kanban_tasks: list[JsonObject] = []
task_counter = 100
kanban_clients: set[WebSocket] = set()


def _as_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default if value is None else str(value)


def _as_map(value: object) -> JsonObject:
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value).items()
        return {str(key): item for key, item in items}
    return {}


def _append_task(payload: dict[str, list[JsonObject]], key: str, task: JsonObject) -> None:
    bucket = payload.get(key)
    if bucket is not None:
        bucket.append(task)


def _default_project_path() -> str:
    try:
        return str(Path(config.paths.project_root).resolve())
    except Exception:
        logger.exception("Unhandled exception")
        return str(Path.cwd().resolve())


def _normalize_project_path(project_path: str | None = None) -> str:
    raw = str(project_path or "").strip()
    if not raw or raw == "/":
        return _default_project_path()
    return str(Path(raw).expanduser().resolve())


def _project_name(project_path: str) -> str:
    path = Path(project_path)
    return path.name or str(path)


def _task_matches_workspace(task: JsonObject, workspace: str | None) -> bool:
    if not workspace:
        return True
    expected = _normalize_project_path(workspace)
    actual = _normalize_project_path(_as_text(task.get("project_path"), ""))
    return actual == expected


def _serialize_kanban_payload(
    tasks: list[JsonObject] | None = None,
) -> dict[str, list[JsonObject]]:
    selected = list(tasks if tasks is not None else kanban_tasks)
    payload = {
        "tasks": selected,
        "todo": [],
        "in_progress": [],
        "completed": [],
        "cancelled": [],
        # Backward-compatible aliases for older Kanban consumers.
        "BACKLOG": [],
        "IN_PROGRESS": [],
        "REVIEW": [],
        "DONE": [],
    }
    for task in selected:
        status = _as_text(task.get("status"), "todo")
        _append_task(payload, status, task)
        if status == "todo":
            _append_task(payload, "BACKLOG", task)
        elif status == "in_progress":
            _append_task(payload, "IN_PROGRESS", task)
        elif status == "completed":
            _append_task(payload, "DONE", task)
        elif status == "cancelled":
            _append_task(payload, "DONE", task)
    return payload


async def broadcast_kanban() -> None:
    """Broadcast Kanban."""
    # Helper to broadcast the flat task list plus grouped status views.
    message = json.dumps(_serialize_kanban_payload())
    for client in list(kanban_clients):
        try:
            await client.send_text(message)
        except Exception:
            logger.exception("Unhandled exception")
            kanban_clients.discard(client)


def _on_agent_turn_started(**kwargs: object) -> None:
    global task_counter
    task_type = _as_text(kwargs.get("task_type"), "Task")
    role = _as_text(kwargs.get("role"), "WORKER")

    # Check if a similar task is already in progress
    for task in kanban_tasks:
        if task["role"] == role and task["status"] == "in_progress":
            return  # Update existing if needed, or skip

    kanban_tasks.append(
        {
            "id": f"T{task_counter}",
            "title": f"[{role}] {task_type}",
            "description": "Agent is working on the task...",
            "status": "in_progress",
            "type": "Agent",
            "role": role,
            "priority": "normal",
            "project_path": _default_project_path(),
            "project_name": _project_name(_default_project_path()),
        },
    )
    task_counter += 1


def _on_agent_turn_ended(**kwargs: object) -> None:
    role = _as_text(kwargs.get("role"), "WORKER")
    for task in reversed(kanban_tasks):
        if task["role"] == role and task["status"] == "in_progress":
            task["status"] = "completed"
            task["description"] = "Task completed successfully."
            break


def _on_quality_check_failed(**kwargs: object) -> None:
    """진행 중인 작업 카드에 QualityGate 실패 정보를 표시합니다."""
    grade = _as_text(kwargs.get("grade"), "?")
    issues = _as_text(kwargs.get("feedback"), "") or "품질 게이트 미달"
    for task in reversed(kanban_tasks):
        if task["status"] == "in_progress":
            task["quality_failed"] = True
            task["quality_grade"] = grade
            detail = f"[품질 실패 {grade}] {issues}"
            task["description"] = f"{_as_text(task.get('description'), '')}\n{detail}".strip()
            break


def _on_anti_patterns_detected(**kwargs: object) -> None:
    """진행 중인 작업 카드에 반복 실패(안티패턴) 감지 정보를 표시합니다."""
    raw_patterns = kwargs.get("patterns")
    pattern_text = (
        "; ".join(_as_text(p) for p in raw_patterns) if isinstance(raw_patterns, list) else _as_text(raw_patterns)
    )
    for task in reversed(kanban_tasks):
        if task["status"] == "in_progress":
            task["anti_patterns"] = True
            detail = f"[안티패턴 감지] {pattern_text or '반복 실패 패턴'}"
            task["description"] = f"{_as_text(task.get('description'), '')}\n{detail}".strip()
            break


global_event_bus.subscribe("AgentTurnStarted", _on_agent_turn_started)
global_event_bus.subscribe("AgentTurnEnded", _on_agent_turn_ended)
global_event_bus.subscribe("QualityCheckFailed", _on_quality_check_failed)
global_event_bus.subscribe("AntiPatternsDetected", _on_anti_patterns_detected)


class StatusUpdate(BaseModel):
    """Statusupdate.

    Bases: BaseModel
    """

    status: str


@router.post("/api/kanban/tasks")
async def create_kanban_task(request: Request):
    """Create kanban task.

    Args:
        request (Request): Request request.

    """
    global task_counter
    data = _as_map(cast(object, await request.json()))
    project_path = _normalize_project_path(
        _as_text(
            data.get("project_path") or data.get("workspace_path") or data.get("workspace"),
            "",
        ),
    )
    task = {
        "id": f"T{task_counter}",
        "title": data.get("description", "Untitled Task"),
        "description": data.get("description", "Untitled Task"),
        "role": data.get("assignee", "auto"),
        "status": "todo",
        "tokens": 0,
        "type": data.get("type", "Task"),
        "priority": data.get("priority", "normal"),
        "project_path": project_path,
        "project_name": _project_name(project_path),
    }
    task_counter += 1
    kanban_tasks.append(task)
    await broadcast_kanban()
    return task


@router.get("/api/kanban/tasks")
async def get_kanban_tasks(workspace: str | None = None):
    """Retrieve kanban tasks.

    Args:
        workspace (str | None): str | None workspace.

    """
    tasks = [t for t in kanban_tasks if _task_matches_workspace(t, workspace)]
    return {
        "data": tasks,
        "workspace": _normalize_project_path(workspace) if workspace else None,
    }


@router.post("/api/kanban/tasks/{task_id}/cancel")
async def cancel_kanban_task_endpoint(task_id: str):
    """Cancel Kanban Task Endpoint.

    Args:
        task_id (str): str task id.

    """
    # 실제 백그라운드 엔진 취소 호출 (mocking for non-existing real tasks)
    try:
        from antigravity_k.engine.task_runner import get_task_runner

        runner = get_task_runner()
        _ = runner.cancel_task(task_id)
    except Exception:
        logger.exception("Engine cancel failed or skipped")

    for task in kanban_tasks:
        if str(task["id"]) == str(task_id):
            task["status"] = "cancelled"
            task["title"] = f"[중단됨] {task.get('title', '')}"
            await broadcast_kanban()
            return {"ok": True, "message": "Task cancelled", "task": task}

    raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/api/kanban/tasks/{task_id}")
async def delete_kanban_task_endpoint(task_id: str):
    """Remove kanban task endpoint.

    Args:
        task_id (str): str task id.

    """
    for idx, task in enumerate(list(kanban_tasks)):
        if str(task["id"]) == str(task_id):
            removed = kanban_tasks.pop(idx)
            await broadcast_kanban()
            return {"ok": True, "message": "Task removed", "task": removed}

    raise HTTPException(status_code=404, detail="Task not found")


@router.put("/api/kanban/tasks/{task_id}/status")
async def update_kanban_task_status(task_id: str, update: StatusUpdate):
    """Update kanban task status.

    Args:
        task_id (str): str task id.
        update (StatusUpdate): StatusUpdate update.

    """
    for task in kanban_tasks:
        if task["id"] == task_id:
            task["status"] = update.status
            await broadcast_kanban()
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@router.websocket("/ws/kanban")
async def websocket_kanban(websocket: WebSocket):
    """Websocket Kanban.

    Args:
        websocket (WebSocket): WebSocket websocket.

    """
    if await close_unauthorized_ws(websocket):
        return
    kanban_clients.add(websocket)
    try:
        await websocket.send_text(json.dumps(_serialize_kanban_payload()))

        while True:
            _ = await websocket.receive_text()
    except (WebSocketDisconnect, asyncio.CancelledError):
        kanban_clients.discard(websocket)
    except Exception:
        logger.exception("Unhandled exception")
        kanban_clients.discard(websocket)
