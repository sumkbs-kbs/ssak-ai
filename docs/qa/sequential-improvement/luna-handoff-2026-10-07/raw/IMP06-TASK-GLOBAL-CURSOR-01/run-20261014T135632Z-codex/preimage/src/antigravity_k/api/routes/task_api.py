from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Annotated, ClassVar, Final

import anyio
from anyio.to_thread import run_sync
from fastapi import APIRouter, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antigravity_k.api.dependencies import get_agent_runtime
from antigravity_k.api.routes.session_state import close_unauthorized_ws
from antigravity_k.api.task_models import (
    TaskActionResponse,
    TaskBenchmarkRequest,
    TaskEvent,
    TaskEventsResponse,
    TaskForkRequest,
    TaskForkResponse,
    TaskListResponse,
    TaskOutputResponse,
    TaskStatusResponse,
    TaskSteeringInput,
    TaskSteeringResponse,
    TaskStreamEnd,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.benchmark_cases import get_suite
from antigravity_k.engine.benchmark_harness import BenchmarkHarness
from antigravity_k.engine.task_events import ExecutionEventRecord

router = APIRouter()

_TERMINAL_TASK_STATUSES = frozenset({"done", "failed", "cancelled"})
_SSE_EVENT_NAME = re.compile(r"[A-Za-z0-9_.:-]+")
_FORK_OUTPUT_CONTEXT_LIMIT: Final = 12_000
_TaskListLimit = Annotated[int, Query(ge=1, le=200)]
_TaskEventOffset = Annotated[int, Query(ge=0)]
_TaskEventLimit = Annotated[int, Query(ge=1, le=500)]
_LastEventId = Annotated[int | None, Header(alias="Last-Event-ID", ge=0)]


class _TaskForkSource(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    status: str = Field(min_length=1)
    output: str = ""


class _TaskForkMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source_task_id: str
    source_status: str
    source_output: str
    source_last_sequence: int


class _TaskForkContext(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    fork: _TaskForkMetadata


def _runtime() -> AgentRuntime:
    return get_agent_runtime()


def _auth_subject(request: Request) -> str:
    subject = getattr(request.state, "auth_subject", "anonymous")
    if not isinstance(subject, str) or not subject.strip():
        return "anonymous"
    return subject.strip()


def _require_task(runtime: AgentRuntime, task_id: str, owner_subject: str | None = None) -> dict[str, object]:
    task = runtime.get_task_status(task_id, owner_subject=owner_subject)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post(
    "/api/tasks/submit",
    response_model=TaskSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_background_task(request: TaskSubmitRequest, http_request: Request) -> TaskSubmitResponse:
    """Submit a background task with immutable project binding (WS-01)."""
    from antigravity_k.api.error_handler import correlation_id_var
    from antigravity_k.api.project_binding import (
        SESSION_ID_HEADER,
        execution_context_to_task_context,
        resolve_project_execution_context,
    )

    # F-37: 정체성은 `context` 안에 중첩될 수도 있고 **최상위**에 올 수도 있다 — 대시보드는 최상위
    # 형태를 보낸다(`withProjectIdentityPayload`). 공유 리졸버는 그 둘을 이미 같은 것으로 읽으므로
    # (`extract_project_id_from_payload`), 여기서 할 일은 **도착한 자리를 빠뜨리지 않는 것**이다.
    # 중첩이 있으면 그것이 이긴다(더 구체적인 자리이며 기존 동작이다).
    project_id = request.context.get("project_id") or request.project_id
    payload: dict[str, object] = {
        "project_id": project_id,
        "execution_context": request.context.get("execution_context"),
        "session_id": request.context.get("session_id"),
        "conversation_id": request.context.get("conversation_id"),
        "conversation_revision": request.context.get("conversation_revision", 0),
        "model": request.model,
    }
    execution_context = resolve_project_execution_context(
        payload=payload,
        header_session_id=http_request.headers.get(SESSION_ID_HEADER),
        actor_subject=_auth_subject(http_request),
        model_id=request.model or "default",
        correlation_id=correlation_id_var.get(""),
        require_existing_conversation=False,
        bind=True,
    )
    http_request.state.execution_context = execution_context
    context: dict[str, object] = dict(request.context)
    context.update(execution_context_to_task_context(execution_context))
    task_id = _runtime().submit_task(
        prompt=request.prompt,
        context=context,
        target_model=request.model,
        use_worktree=request.use_worktree,
        idempotency_key=request.idempotency_key,
        owner_subject=_auth_subject(http_request),
    )
    return TaskSubmitResponse(task_id=task_id)


@router.post(
    "/api/tasks/{task_id}/fork",
    response_model=TaskForkResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def fork_task(task_id: str, request: TaskForkRequest, http_request: Request) -> TaskForkResponse:
    runtime = _runtime()
    owner_subject = _auth_subject(http_request)
    try:
        source = _TaskForkSource.model_validate(_require_task(runtime, task_id, owner_subject=owner_subject))
    except ValidationError as error:
        raise HTTPException(status_code=409, detail="Task history is not forkable") from error

    events = runtime.list_task_events(task_id, after_sequence=0, limit=1_000, owner_subject=owner_subject)
    last_sequence = events[-1]["sequence"] if events else 0
    fork_context = _TaskForkContext(
        fork=_TaskForkMetadata(
            source_task_id=source.task_id,
            source_status=source.status,
            source_output=source.output[-_FORK_OUTPUT_CONTEXT_LIMIT:],
            source_last_sequence=last_sequence,
        ),
    ).model_dump()
    forked_task_id = runtime.submit_task(
        prompt=request.prompt or source.prompt,
        context=fork_context,
        target_model=request.model,
        use_worktree=request.use_worktree,
        idempotency_key=request.idempotency_key,
        owner_subject=owner_subject,
    )
    return TaskForkResponse(task_id=forked_task_id, source_task_id=source.task_id)


@router.get("/api/tasks/{task_id}/status", response_model=TaskStatusResponse)
def get_task_status(task_id: str, request: Request) -> TaskStatusResponse:
    return TaskStatusResponse.from_runtime(_require_task(_runtime(), task_id, owner_subject=_auth_subject(request)))


@router.get("/api/tasks", response_model=TaskListResponse)
def list_tasks(request: Request, limit: _TaskListLimit = 20) -> TaskListResponse:
    return TaskListResponse.from_runtime(_runtime().list_tasks(limit=limit, owner_subject=_auth_subject(request)))


@router.get("/api/tasks/{task_id}/output", response_model=TaskOutputResponse)
def get_task_output(task_id: str, request: Request) -> TaskOutputResponse:
    output = _runtime().get_task_output(task_id, owner_subject=_auth_subject(request))
    if output is None:
        raise HTTPException(status_code=404, detail="Task output not found")
    return TaskOutputResponse(task_id=task_id, output=output)


@router.post("/api/tasks/{task_id}/cancel", response_model=TaskActionResponse)
def cancel_background_task(task_id: str, request: Request) -> TaskActionResponse:
    """태스크 취소 — 거부는 **이유별로 다른 응답**이다(F-35).

    "활성 아님"(404)과 "다른 살아 있는 프로세스가 실행 중"(409)은 다른 사건이다. 예전에는 둘 다
    404 였고, 그보다 나쁜 경우도 있었다: 소유 여부를 보지 않고 `cancelled` 로 적어 **이력이
    거짓이 됐다**(그 행은 끝났다고 말하는데 실행은 계속된다). 이제 소유 규칙(`can_cancel`)이
    그 거부를 만들고, 여기서는 그 사실을 응답으로 **이름 붙인다**.
    """
    verdict = _runtime().cancel_verdict(task_id, owner_subject=_auth_subject(request))
    if verdict == "owned_elsewhere":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another live process owns this task's execution — cancel it there",
        )
    if verdict != "cancelled":
        raise HTTPException(status_code=404, detail="Task is not active")
    return TaskActionResponse(status="cancelled", task_id=task_id)


@router.post("/api/tasks/{task_id}/resume", response_model=TaskActionResponse)
def resume_task(task_id: str, request: Request) -> TaskActionResponse:
    if not _runtime().resume_task(task_id=task_id, owner_subject=_auth_subject(request)):
        raise HTTPException(status_code=404, detail="Task is not resumable or has no checkpoint")
    return TaskActionResponse(status="resumed", task_id=task_id)


@router.post("/api/tasks/{task_id}/steer", response_model=TaskSteeringResponse, status_code=status.HTTP_202_ACCEPTED)
def steer_task(task_id: str, payload: TaskSteeringInput, request: Request) -> TaskSteeringResponse:
    result = _runtime().steer_task(
        task_id,
        payload.instruction,
        owner_subject=_auth_subject(request),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task is not active")
    return TaskSteeringResponse(
        task_id=result.task_id,
        steering_id=result.steering_id,
        mode=result.mode,
    )


@router.post("/api/tasks/benchmark/{case_id}", response_model=None)
def submit_task_benchmark(case_id: str, request: TaskBenchmarkRequest, http_request: Request) -> dict[str, object]:
    cases = get_suite(case_id)
    if len(cases) != 1 or cases[0].id != case_id:
        raise HTTPException(status_code=404, detail="Benchmark case not found")
    case = cases[0]
    task_id = _runtime().submit_task(
        prompt=case.prompt,
        context=BenchmarkHarness.task_context_for_case(case),
        target_model=request.model,
        idempotency_key=request.idempotency_key,
        owner_subject=_auth_subject(http_request),
    )
    return {
        "status": "submitted",
        "task_id": task_id,
        "benchmark_case": {
            "id": case.id,
            "category": case.category,
            "difficulty": case.difficulty,
            "expected_tools": list(case.expected_tools),
        },
    }


@router.get("/api/tasks/{task_id}/events", response_model=TaskEventsResponse)
def list_task_events(
    task_id: str,
    request: Request,
    after_sequence: _TaskEventOffset = 0,
    limit: _TaskEventLimit = 200,
) -> TaskEventsResponse:
    runtime = _runtime()
    owner_subject = _auth_subject(request)
    _ = _require_task(runtime, task_id, owner_subject=owner_subject)
    records = runtime.list_task_events(
        task_id,
        after_sequence=after_sequence,
        limit=limit + 1,
        owner_subject=owner_subject,
    )
    has_more = len(records) > limit
    events = [TaskEvent.from_record(record) for record in records[:limit]]
    last_sequence = events[-1].sequence if events else after_sequence
    return TaskEventsResponse(
        task_id=task_id,
        events=events,
        last_sequence=last_sequence,
        has_more=has_more,
    )


@router.get("/api/tasks/{task_id}/events/stream")
async def stream_task_events(
    task_id: str,
    request: Request,
    after_sequence: _TaskEventOffset = 0,
    last_event_id: _LastEventId = None,
) -> StreamingResponse:
    runtime = _runtime()
    owner_subject = _auth_subject(request)
    _ = _require_task(runtime, task_id, owner_subject=owner_subject)
    resume_sequence = max(after_sequence, last_event_id or 0)
    return StreamingResponse(
        _event_stream(runtime, task_id, request, resume_sequence, owner_subject),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/api/tasks/{task_id}/events/ws")
async def stream_task_events_websocket(
    websocket: WebSocket,
    task_id: str,
    after_sequence: _TaskEventOffset = 0,
) -> None:
    runtime = _runtime()
    if await close_unauthorized_ws(websocket):
        return
    owner_subject = getattr(websocket.state, "auth_subject", "loopback")
    if not isinstance(owner_subject, str) or not owner_subject:
        owner_subject = "loopback"
    if runtime.get_task_status(task_id, owner_subject=owner_subject) is None:
        await websocket.close(code=1008, reason="Task not found")
        return
    sequence = after_sequence
    try:
        while True:
            records = await _next_task_events(runtime, task_id, sequence, owner_subject)
            for record in records:
                event = TaskEvent.from_record(record)
                sequence = event.sequence
                await websocket.send_json(event.model_dump(mode="json"))
            task_status = await _task_status(runtime, task_id, owner_subject)
            if task_status in _TERMINAL_TASK_STATUSES:
                end = TaskStreamEnd(task_id=task_id, last_sequence=sequence, status=task_status)
                await websocket.send_json(
                    {
                        "type": "stream.end",
                        "task_id": end.task_id,
                        "last_sequence": end.last_sequence,
                        "status": end.status,
                    },
                )
                await websocket.close()
                return
            await anyio.sleep(0.5)
    except WebSocketDisconnect:
        return


async def _event_stream(
    runtime: AgentRuntime,
    task_id: str,
    request: Request,
    after_sequence: int,
    owner_subject: str,
) -> AsyncIterator[str]:
    sequence = after_sequence
    idle_cycles = 0
    while True:
        records = await _next_task_events(runtime, task_id, sequence, owner_subject)
        for record in records:
            event = TaskEvent.from_record(record)
            sequence = event.sequence
            yield _event_frame(event)
        task_status = await _task_status(runtime, task_id, owner_subject)
        if task_status in _TERMINAL_TASK_STATUSES:
            end = TaskStreamEnd(task_id=task_id, last_sequence=sequence, status=task_status)
            yield f"event: stream.end\ndata: {end.model_dump_json()}\n\n"
            return
        if await request.is_disconnected():
            return
        idle_cycles += 1
        if idle_cycles % 30 == 0:
            yield ": keep-alive\n\n"
        await anyio.sleep(0.5)


async def _next_task_events(
    runtime: AgentRuntime,
    task_id: str,
    after_sequence: int,
    owner_subject: str | None = None,
) -> list[ExecutionEventRecord]:
    def load() -> list[ExecutionEventRecord]:
        return runtime.list_task_events(
            task_id,
            after_sequence=after_sequence,
            limit=200,
            owner_subject=owner_subject,
        )

    return await run_sync(load)


async def _task_status(runtime: AgentRuntime, task_id: str, owner_subject: str | None = None) -> str:
    def load() -> dict[str, object] | None:
        return runtime.get_task_status(task_id, owner_subject=owner_subject)

    task = await run_sync(load)
    return str(task.get("status", "unknown")) if task is not None else "unknown"


def _event_frame(event: TaskEvent) -> str:
    event_name = event.event_type if _SSE_EVENT_NAME.fullmatch(event.event_type) else "task.event"
    return f"id: {event.sequence}\nevent: {event_name}\ndata: {event.model_dump_json()}\n\n"


__all__ = ["router"]
