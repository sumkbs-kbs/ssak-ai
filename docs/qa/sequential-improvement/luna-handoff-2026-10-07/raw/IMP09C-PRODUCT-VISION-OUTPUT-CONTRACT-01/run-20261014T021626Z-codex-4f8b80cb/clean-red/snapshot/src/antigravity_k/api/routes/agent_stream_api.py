"""Agent Stream API — SSE 스트리밍과 활성 세션 조회."""

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from antigravity_k.api.dependencies import get_agent_runtime
from antigravity_k.api.routes.session_state import get_active_session, reset_active_session

router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.agent_stream")


@router.get("/api/agent/active")
async def get_active_agent():
    """Return the currently active agent session if any."""
    session = get_active_session()
    if session.is_active:
        return {
            "active": True,
            "q": session.q,
            "history": session.history,
        }
    return {"active": False}


@router.get("/api/stream_agent")
async def stream_agent(
    q: Annotated[str | None, Query(description="User prompt to the agent")] = None,
    reconnect: bool = False,
):
    """Server-Sent Events (SSE) endpoint to stream agent thoughts and outputs.

    Supports reconnection to an ongoing session.
    """
    from starlette.concurrency import iterate_in_threadpool

    async def event_generator():
        active_session = get_active_session()
        # If reconnecting to an active session
        if reconnect and active_session.is_active:
            # Yield history first
            for chunk in active_session.history:
                yield f"data: {json.dumps({'text': chunk})}\n\n"

            # Then poll for new chunks until done
            last_idx = len(active_session.history)
            while active_session.is_active:
                if len(active_session.history) > last_idx:
                    for chunk in active_session.history[last_idx:]:
                        yield f"data: {json.dumps({'text': chunk})}\n\n"
                    last_idx = len(active_session.history)
                await asyncio.sleep(0.5)

            if active_session.error:
                yield f"data: {json.dumps({'error': active_session.error})}\n\n"
            elif active_session.done:
                yield f"data: {json.dumps({'done': True})}\n\n"
            return

        if not q:
            yield f"data: {json.dumps({'error': 'Missing query'})}\n\n"
            return

        # Start new session — 바인딩 재할당 대신 동일 객체를 리셋한다
        # (값 복사 임포트 소비자의 stale 바인딩 방지)
        _ = reset_active_session()
        active_session.is_active = True
        active_session.q = q

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
