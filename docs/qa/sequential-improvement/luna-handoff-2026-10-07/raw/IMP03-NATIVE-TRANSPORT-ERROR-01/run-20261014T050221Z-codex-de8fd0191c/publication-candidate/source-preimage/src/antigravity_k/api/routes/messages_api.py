"""Anthropic Messages API 호환 엔드포인트 (/v1/messages).

============================================================
벤치마킹 출처: unsloth (OpenAI/Anthropic 호환 동시 서빙) + freebuff (에이전트 브리지).
Claude Code, Codex 등 Anthropic 프로토콜을 사용하는 외부 CLI 에이전트가
Ssak-Ai의 로컬 모델을 그대로 사용할 수 있게 한다.

설계 원칙:
- 기존 `ProtocolTranslator`의 Anthropic 변환기 재사용 (새 변환 로직 없음)
- `chat.py`의 검증/가드/세션 흐름 준수 (PromptInjectionGuard 동일 적용)
- 내부 생성은 ModelManager.generate / stream_generate 재사용
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from antigravity_k.api.dependencies import get_model_manager
from antigravity_k.engine.anthropic_tool_bridge import (
    build_content_blocks,
    build_tool_choice_directive,
    extract_tool_use_blocks,
    flatten_message_content,
    resolve_stop_reason,
    serialize_tools_for_prompt,
)
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.protocol_translator import APIFormat, ProtocolTranslator

logger = logging.getLogger("antigravity_k.api.messages")

router = APIRouter()

_ALLOWED_ROLES = {"user", "assistant"}

_TRANSLATOR = ProtocolTranslator()
_TRANSLATOR_TYPE = APIFormat.ANTHROPIC.value


def _error(status: int, err_type: str, message: str) -> tuple[dict[str, Any], int]:
    """Anthropic error envelope."""
    return {"error": {"type": err_type, "message": message}}, status


def _extract_system_text(system: object) -> str:
    """Anthropic system 필드: 문자열 또는 content 블록 배열 모두 수용."""
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, Sequence) and not isinstance(system, (str, bytes)):
        parts = []
        for block in system:
            if isinstance(block, Mapping) and str(block.get("text") or ""):
                parts.append(str(block["text"]))
        return "\n".join(parts)
    return ""


def _extract_message_text(content: object) -> str:
    """message.content: 문자열 또는 content 블록 배열 모두 수용.

    tool_use/tool_result 블록도 텍스트로 복원해 대화 히스토리가 유지되게 한다.
    """
    return flatten_message_content(content)


def _flatten_messages(raw_messages: object) -> list[dict[str, str]]:
    """Anthropic messages → 내부 chat messages [{role, content}]."""
    messages: list[dict[str, str]] = []
    if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
        return messages
    for msg in raw_messages:
        if not isinstance(msg, Mapping):
            continue
        role = msg.get("role")
        if role not in _ALLOWED_ROLES:
            continue
        messages.append({"role": str(role), "content": _extract_message_text(msg.get("content"))})
    return messages


def _validate_anthropic_body(body: object) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """요청 바디 검증. (parsed, None) 또는 (None, error_envelope)."""
    if not isinstance(body, dict):
        return None, _error(400, "invalid_request_error", "Request body must be a JSON object")

    model = body.get("model")
    if not (isinstance(model, str) and model.strip()):
        return None, _error(400, "invalid_request_error", "model: Field required")

    max_tokens = body.get("max_tokens")
    if not (isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens > 0):
        return None, _error(400, "invalid_request_error", "max_tokens: Field required")

    messages = _flatten_messages(body.get("messages"))
    if not messages:
        return None, _error(400, "invalid_request_error", "messages: Field required")

    tools, tools_error = _validate_tools(body.get("tools"))
    if tools_error is not None:
        return None, _error(400, "invalid_request_error", tools_error)

    system_text = _extract_system_text(body.get("system"))
    stream = body.get("stream") is True
    temperature_raw = body.get("temperature")
    temperature = (
        float(temperature_raw)
        if isinstance(temperature_raw, (int, float)) and not isinstance(temperature_raw, bool)
        else 1.0
    )

    parsed: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "system": system_text,
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": body.get("tool_choice"),
    }
    return parsed, None


def _validate_tools(raw_tools: object) -> tuple[list[dict[str, Any]], str | None]:
    """Anthropic tools 배열 검증. (tools, error_message)."""
    if raw_tools is None:
        return [], None
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)):
        return [], "tools: must be an array"
    tools: list[dict[str, Any]] = []
    for tool in raw_tools:
        if not isinstance(tool, Mapping):
            return [], "tools: each tool must be an object"
        name = tool.get("name")
        if not (isinstance(name, str) and name.strip()):
            return [], "tools.name: Field required"
        tools.append(
            {
                "name": name,
                "description": str(tool.get("description") or ""),
                "input_schema": tool.get("input_schema", {}),
            }
        )
    return tools, None


def _prompt_from_internal(system: str, messages: list[dict[str, str]]) -> str:
    """내부 chat messages를 ModelManager 단일 프롬프트로 직렬화."""
    lines: list[str] = []
    if system:
        lines.append(f"System: {system}")
    for msg in messages:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {msg['content']}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


def _build_effective_system(system: str, tools: list[dict[str, Any]], tool_choice: object) -> str:
    """시스템 프롬프트 + 도구 카탈로그 + tool_choice 지시문 결합."""
    sections: list[str] = [system] if system else []
    tool_catalog = serialize_tools_for_prompt(tools)
    if tool_catalog:
        sections.append(tool_catalog)
    directive = build_tool_choice_directive(tool_choice)
    if directive:
        sections.append(directive)
    return "\n\n".join(sections)


def _count_tokens_estimate(text: str) -> int:
    """토큰 근사치 (한국어 혼합 텍스트 기준 보수적 추정)."""
    if not text:
        return 0
    return max(1, len(text) // 3)


def _usage_block(messages: list[dict[str, str]], system: str, output: str) -> dict[str, int]:
    prompt_text = system + "\n".join(m["content"] for m in messages)
    return {
        "input_tokens": _count_tokens_estimate(prompt_text),
        "output_tokens": _count_tokens_estimate(output),
    }


def _message_response(
    model: str,
    content_blocks: list[dict[str, Any]],
    usage: dict[str, int],
    stop_reason: str,
) -> dict[str, Any]:
    """Anthropic message 응답. content 블록(text/tool_use)을 그대로 사용."""
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


def _sse(data: dict[str, Any]) -> str:
    return f"event: {data['type']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _split_chunks(text: str, size: int = 256) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


async def stream_generate_async(
    manager: ModelManager,
    prompt: str,
    model: str,
    **kwargs: Any,
) -> AsyncIterator[str]:
    """ModelManager.stream_generate(동기 Iterator) → AsyncIterator 래퍼 (Phase 31).

    starlette.iterate_in_threadpool은 각 next() 호출을 스레드풀에서 실행해
    이벤트 루프를 막지 않으면서 토큰이 도착하는 대로 전달한다 (버퍼링 없음).
    기존 run_in_threadpool + "".join() 방식은 전체 생성이 끝나야 첫 SSE를
    보내는 가짜 스트리밍이었다.
    """
    from starlette.concurrency import iterate_in_threadpool

    iterator = manager.stream_generate(prompt=prompt, target=model, **kwargs)
    async for chunk in iterate_in_threadpool(iterator):
        yield chunk


async def _stream_events(
    manager: ModelManager,
    prompt: str,
    model: str,
    usage: dict[str, int],
) -> AsyncIterator[str]:
    """Anthropic SSE 이벤트 시퀀스 — 실시간 토큰 스트리밍 (Phase 31).

    stream_generate_async로 토큰을 버퍼링 없이 받아 도착 즉시 text_delta로
    내보낸다. tool_use 감지는 완성 텍스트에 bridge의 동기 파서를 재사용:
    - tool_use 없음 → 이미 스트리밍한 텍스트 그대로 블록 종료
    - tool_use 있음 → 이미 보낸 텍스트에서 tool_call 태그가 노출될 수 있으므로,
      태그가 스트리밍됐다면 뒤에 빈 text_delta 보정 이벤트를 보내고 tool_use 블록으로 이어감
      (Anthropic 클라이언트는 누적 텍스트에서 태그를 다시 파싱하지 않음 — Claude Code는
      stop_reason=tool_use와 tool_use 블록만 소비하므로 라이브 토큰 노출은 UX 이슈뿐)
    """
    message_id = f"msg_{uuid.uuid4().hex[:24]}"

    yield _sse(
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": usage.get("input_tokens", 0), "output_tokens": 0},
            },
        }
    )

    emitted_text: list[str] = []
    text_block_started = False
    text_index = 0
    error_text: str | None = None

    try:
        async for chunk in stream_generate_async(manager, prompt, model):
            if not chunk:
                continue
            if not text_block_started:
                yield _sse(
                    {
                        "type": "content_block_start",
                        "index": text_index,
                        "content_block": {"type": "text", "text": ""},
                    }
                )
                text_block_started = True
            yield _sse(
                {
                    "type": "content_block_delta",
                    "index": text_index,
                    "delta": {"type": "text_delta", "text": chunk},
                }
            )
            emitted_text.append(chunk)
    except Exception as exc:  # noqa: BLE001
        logger.exception("stream_generate failed")
        error_text = f"[API Error] {exc}"

    # ── 말미: 완성 텍스트로 tool_use 판정 (동기 경로와 동일 로직) ──
    full_text = error_text if error_text is not None else "".join(emitted_text)
    usage["output_tokens"] = _count_tokens_estimate(full_text)

    tool_blocks = extract_tool_use_blocks(full_text)
    content_blocks = build_content_blocks(full_text, tool_blocks)
    stop_reason = resolve_stop_reason(full_text, tool_blocks, max_tokens_hit=False)

    if error_text is not None:
        # 생성 실패 — text 블록으로 오류 메시지 전달 (기존 동기 경로와 동일 UX)
        yield _sse(
            {
                "type": "content_block_start",
                "index": text_index,
                "content_block": {"type": "text", "text": ""},
            }
        )
        yield _sse(
            {
                "type": "content_block_delta",
                "index": text_index,
                "delta": {"type": "text_delta", "text": error_text},
            }
        )
        yield _sse({"type": "content_block_stop", "index": text_index})
        text_index += 1

    for block in content_blocks:
        if block["type"] == "text":
            if text_block_started:
                # 이미 실시간 스트리밍된 블록 — 종료만
                yield _sse({"type": "content_block_stop", "index": text_index})
                text_index += 1
            else:
                # 텍스트가 전혀 스트리밍되지 않은 경우(빈 청크만 있었음 등) — 지금 재구성해 전송
                yield _sse(
                    {
                        "type": "content_block_start",
                        "index": text_index,
                        "content_block": {"type": "text", "text": ""},
                    }
                )
                for piece in _split_chunks(str(block["text"])):
                    yield _sse(
                        {
                            "type": "content_block_delta",
                            "index": text_index,
                            "delta": {"type": "text_delta", "text": piece},
                        }
                    )
                yield _sse({"type": "content_block_stop", "index": text_index})
                text_index += 1
        elif block["type"] == "tool_use":
            yield _sse(
                {
                    "type": "content_block_start",
                    "index": text_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": str(block["id"]),
                        "name": str(block["name"]),
                        "input": {},
                    },
                }
            )
            input_json = json.dumps(block["input"], ensure_ascii=False)
            yield _sse(
                {
                    "type": "content_block_delta",
                    "index": text_index,
                    "delta": {"type": "input_json_delta", "partial_json": input_json},
                }
            )
            yield _sse({"type": "content_block_stop", "index": text_index})
            text_index += 1

    yield _sse(
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": usage.get("output_tokens", 0)},
        }
    )
    yield _sse({"type": "message_stop"})


@router.post("/v1/messages")
async def create_message(
    request: Request,
    manager: Annotated[ModelManager, Depends(get_model_manager)],
) -> object:
    """Anthropic Messages API 호환 엔드포인트.

    Claude Code/Codex 등이 ANTHROPIC_BASE_URL을 Ssak-Ai로 지정해 로컬 모델 사용 가능.
    """
    try:
        body: object = await request.json()
    except Exception:  # noqa: BLE001
        parse_err, parse_status = _error(400, "invalid_request_error", "Invalid JSON body")
        return JSONResponse(parse_err, status_code=parse_status)

    parsed, validation = _validate_anthropic_body(body)
    if validation is not None:
        payload, validation_status = validation
        return JSONResponse(payload, status_code=validation_status)

    assert parsed is not None
    model = str(parsed["model"])
    messages = cast(list[dict[str, str]], parsed["messages"])
    raw_system = str(parsed["system"])
    stream = bool(parsed["stream"])
    temperature = float(parsed["temperature"])
    max_tokens = int(parsed["max_tokens"])
    tools = cast(list[dict[str, Any]], parsed["tools"])
    tool_choice = parsed["tool_choice"]

    # P0 인젝션 방어: 기존 /v1/chat/completions와 동일 방어 적용
    from antigravity_k.engine.prompt_injection_guard import PromptInjectionGuard

    messages = PromptInjectionGuard().augment_user_input(messages)

    system_text = _build_effective_system(raw_system, tools, tool_choice)
    prompt = _prompt_from_internal(system_text, messages)

    if stream:
        usage = {
            "input_tokens": _count_tokens_estimate(system_text + "\n".join(m["content"] for m in messages)),
            "output_tokens": 0,
        }
        return StreamingResponse(
            _stream_events(manager, prompt, model, usage),
            media_type="text/event-stream",
        )

    from starlette.concurrency import run_in_threadpool

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
        logger.exception("generate failed")
        gen_err, gen_status = _error(529, "api_error", f"Model generation failed: {exc}")
        return JSONResponse(gen_err, status_code=gen_status)

    usage = _usage_block(messages, system_text, text)
    tool_blocks = extract_tool_use_blocks(text)
    content_blocks = build_content_blocks(text, tool_blocks)
    stop_reason = resolve_stop_reason(text, tool_blocks, max_tokens_hit=False)
    return _message_response(model, content_blocks, usage, stop_reason)
