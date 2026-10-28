"""Agent Stream API — SSE 스트리밍과 활성 세션 조회."""

import asyncio
import json
import logging
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from antigravity_k.api.dependencies import get_agent_runtime
from antigravity_k.api.routes.session_state import (
    active_response_snapshot,
    begin_active_response,
    ensure_active_response_available,
)
from antigravity_k.api.routes.session_state import (
    reset_active_session as reset_active_session,
)

router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.agent_stream")


@router.get("/api/agent/active")
async def get_active_agent(request: Request = cast(Request, None)):
    """Return the currently active agent session if any."""
    session = active_response_snapshot(request)
    assert session is not None
    if session.is_active:
        return {
            "active": True,
            "q": session.q,
            "history": list(session.history),
        }
    return {"active": False}


@router.get("/api/stream_agent")
async def stream_agent(
    request: Request = cast(Request, None),
    q: Annotated[str | None, Query(description="User prompt to the agent")] = None,
    reconnect: bool = False,
):
    """Server-Sent Events (SSE) endpoint to stream agent thoughts and outputs.

    Supports reconnection to an ongoing session.
    """
    from starlette.concurrency import iterate_in_threadpool

    initial = active_response_snapshot(request) if reconnect else None
    execution_context = None
    if not reconnect and q:
        if request is not None:
            from antigravity_k.api.project_binding import SESSION_ID_HEADER, resolve_project_execution_context

            actor = getattr(request.state, "auth_subject", None)
            actor = actor.strip() if isinstance(actor, str) and actor.strip() else "anonymous"
            execution_context = resolve_project_execution_context(
                project_id=request.query_params.get("project_id"),
                session_id=request.query_params.get("session_id"),
                header_session_id=request.headers.get(SESSION_ID_HEADER),
                actor_subject=actor,
                bind=True,
            )
        ensure_active_response_available(execution_context)

    async def event_generator():
        if reconnect:
            assert initial is not None
            snapshot = initial
            last_idx = 0
            while snapshot is not None and snapshot.is_active:
                for chunk in snapshot.history[last_idx:]:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                last_idx = len(snapshot.history)
                await asyncio.sleep(0.5)
                snapshot = active_response_snapshot(request, generation=initial.generation)
            if snapshot is not None:
                for chunk in snapshot.history[last_idx:]:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
            if snapshot is not None and snapshot.error:
                yield f"data: {json.dumps({'error': snapshot.error})}\n\n"
            elif snapshot is not None and snapshot.done:
                yield f"data: {json.dumps({'done': True})}\n\n"
            return

        if not q:
            yield f"data: {json.dumps({'error': 'Missing query'})}\n\n"
            return

        try:
            active_session = begin_active_response(execution_context, q)
        except HTTPException as exc:
            yield f"data: {json.dumps({'error': exc.detail})}\n\n"
            return

        try:
            # Instantiate orchestrator
            runtime = get_agent_runtime()
            active_session.orchestrator = runtime.orchestrator

            messages = [{"role": "user", "content": q}]
            target_model = runtime.resolve_model()
            tracked_stream = runtime.start_stream(messages, target_model=target_model)
            if tracked_stream.task_id:
                yield f"data: {json.dumps({'task_id': tracked_stream.task_id})}\n\n"

            # We don't want the task to cancel if the client disconnects,
            # so we run it completely and buffer. Wait, actually SSE generator
            # might still be cancelled. But with iterate_in_threadpool it usually
            # finishes the thread.
            async for chunk in iterate_in_threadpool(
                tracked_stream.chunks,
            ):
                if chunk:
                    active_session.history.append(chunk)
                    payload = json.dumps({"text": chunk})
                    yield f"data: {payload}\n\n"

            active_session.done = True
            # P11 opt-in: 대화 스트림이 끝난 뒤 shadow episode로 core 상태를 관찰한다.
            # surface가 없거나 OFF면 no-op이고, 실패해도 legacy 응답은 이미 완료됐다.
            _ = runtime.observe_interaction(
                episode_id=f"stream:{tracked_stream.task_id or 'ephemeral'}",
                context_ref="legacy:agent-stream",
                goal_ref="legacy:agent-stream",
                expected_outcome=q[:200],
            )
            yield f"data: {json.dumps({'done': True})}\n\n"
        except asyncio.CancelledError:
            # Client disconnected, but the thread might still run.
            logger.info("SSE client disconnected, but task might continue in thread.")
            raise
        except Exception as e:
            logger.error("SSE Error: %s", e, exc_info=True)
            active_session.error = str(e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Delay clearing so reconnects right after finish can see it's done
            active_session.is_active = False

    return StreamingResponse(event_generator(), media_type="text/event-stream")
