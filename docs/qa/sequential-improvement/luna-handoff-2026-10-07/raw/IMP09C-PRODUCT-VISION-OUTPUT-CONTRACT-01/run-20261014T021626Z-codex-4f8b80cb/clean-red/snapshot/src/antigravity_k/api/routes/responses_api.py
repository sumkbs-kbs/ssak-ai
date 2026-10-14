"""OpenAI Responses API 호환 엔드포인트 — Codex CLI 0.150+ 연결용.

Codex는 ``POST {base_url}/responses``만 호출한다 (wire_api="chat" 제거,
openai/codex#7782). 이 엔드포인트는 요청을 openai_responses_bridge로 변환해
로컬 모델 텍스트 프로토콜로 생성하고 Responses API 응답(SSE 포함)으로 돌려준다.
tools 유무와 무관하게 전부 passthrough로 처리한다 — 이 경로의 클라이언트는
에이전트(function calling)가 전제다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from antigravity_k.api.dependencies import get_model_manager
from antigravity_k.engine.anthropic_tool_bridge import extract_tool_use_blocks
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.openai_responses_bridge import (
    build_responses_response,
    build_tool_prompt,
    responses_input_to_internal,
    responses_stream_events,
    validate_responses_tools,
)

logger = logging.getLogger("antigravity_k.api.responses_api")

router = APIRouter()


@router.post("/v1/responses")
async def create_response(
    request: Request,
    manager: Annotated[ModelManager, Depends(get_model_manager)],
) -> object:
    """Responses API passthrough — Codex ↔ 로컬 모델 (Phase 35)."""
    try:
        body = cast("dict[str, Any]", await request.json())
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    tools, tools_error = validate_responses_tools(body.get("tools"))
    if tools_error is not None:
        raise HTTPException(status_code=400, detail=tools_error)

    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise HTTPException(status_code=400, detail="Model is required")

    max_tokens_raw = body.get("max_output_tokens")
    max_tokens = max_tokens_raw if isinstance(max_tokens_raw, int) and max_tokens_raw > 0 else 4096
    temperature_raw = body.get("temperature")
    temperature = temperature_raw if isinstance(temperature_raw, (int, float)) else 0.7
    stream = body.get("stream") is True

    system_text, internal = responses_input_to_internal(body.get("input"), body.get("instructions"))

    from antigravity_k.engine.prompt_injection_guard import PromptInjectionGuard

    guarded = PromptInjectionGuard().augment_user_input(internal)

    tool_choice = body.get("tool_choice")
    prompt = build_tool_prompt(system_text, tools, tool_choice, guarded)

    def _generate() -> str:
        return manager.generate(
            prompt=prompt,
            target=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    try:
        text = await run_in_threadpool(_generate)
    except Exception as exc:  # noqa: BLE001
        logger.exception("responses passthrough generate failed")
        raise HTTPException(status_code=529, detail=f"Model generation failed: {exc}") from exc

    blocks = extract_tool_use_blocks(text)

    if stream:
        frames = responses_stream_events(model, text, blocks)

        async def _sse() -> AsyncIterator[str]:
            for frame in frames:
                yield frame

        return StreamingResponse(_sse(), media_type="text/event-stream")
    return build_responses_response(model, text, blocks)
