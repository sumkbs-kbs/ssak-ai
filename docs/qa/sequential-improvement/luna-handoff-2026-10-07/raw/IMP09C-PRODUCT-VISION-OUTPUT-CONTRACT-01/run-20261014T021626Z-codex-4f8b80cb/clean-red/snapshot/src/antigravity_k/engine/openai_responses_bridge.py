"""OpenAI Responses API 브리지 — Codex 0.150+ 전용 프로토콜 경계 변환.

============================================================
배경: Codex CLI 0.150부터 ``wire_api = "chat"``가 제거되고 Responses API가
필수가 됐다 (openai/codex#7782). 로컬 모델로 Codex를 연결하려면
``POST {base_url}/responses``를 텍스트 프로토콜로 변환해야 한다.

Responses API의 tool 형식은 Chat Completions와 다르다:
- 요청 tools: ``{"type": "function", "name", "description", "parameters"}`` (평평함)
- 히스토리: ``function_call`` (call_id/name/arguments) / ``function_call_output`` items
- 응답: ``output`` 배열에 ``message``/``function_call`` items + SSE 이벤트 스트림

변환 파이프라인은 openai_tool_bridge / anthropic_tool_bridge 프리미티브를 재사용한다
(단일 파서 원칙 — 새 파서 금지).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from antigravity_k.engine.anthropic_tool_bridge import (
    ToolUseBlock,
    build_tool_choice_directive,
    serialize_tools_for_prompt,
    strip_tool_call_syntax,
)

logger = logging.getLogger("antigravity_k.api.openai_responses_bridge")


# ─── 1. 요청 변환 ──────────────────────────────────────────────────────


def validate_responses_tools(raw_tools: object) -> tuple[list[dict[str, Any]], str | None]:
    """Responses tools 배열 검증 + 브리지 형식 변환. (tools, error_message)."""
    if raw_tools is None:
        return [], None
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)):
        return [], "tools: must be an array"
    tools: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_tools):
        if not isinstance(raw, Mapping):
            return [], f"tools[{index}]: must be an object"
        if raw.get("type") not in (None, "function"):
            # function이 아닌 내장 툴(web_search 등)은 카탈로그에서 생략
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            return [], f"tools[{index}].name: must be a non-empty string"
        tool: dict[str, Any] = {"name": name}
        if isinstance(raw.get("description"), str):
            tool["description"] = raw["description"]
        if isinstance(raw.get("parameters"), Mapping):
            tool["input_schema"] = raw["parameters"]
        tools.append(tool)
    return tools, None


def _flatten_content(content: object) -> str:
    """message item content (문자열 | parts 배열) → 단일 텍스트."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, Mapping):
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(part, str):
            parts.append(part)
    return "\n".join(part for part in parts if part)


def _parse_arguments(raw: object) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        except json.JSONDecodeError:
            logger.debug("function_call.arguments 파싱 실패 — 빈 인자로 대체")
    return {}


def _flatten_call_output(raw: object) -> str:
    """function_call_output.output → 텍스트 (JSON 래퍼 {\"output\": ...} 언래핑)."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, Mapping):
                    output = parsed.get("output")
                    if isinstance(output, str):
                        return output
            except json.JSONDecodeError:
                pass
        return raw
    if isinstance(raw, Mapping):
        output = raw.get("output")
        if isinstance(output, str):
            return output
    return json.dumps(raw, ensure_ascii=False)


def responses_input_to_internal(
    raw_input: object,
    instructions: object = None,
) -> tuple[str, list[dict[str, str]]]:
    """Responses ``input`` + ``instructions`` → (system_text, 내부 messages).

    - string input → user 메시지 1개
    - ``function_call`` item → 모델이 자기 출력으로 인식하는 json 코드펜스
    - ``function_call_output`` item → Function result 블록
    - ``reasoning`` 등 비메시지 item → 스킵
    """
    system_text = instructions if isinstance(instructions, str) else ""
    internal: list[dict[str, str]] = []

    if isinstance(raw_input, str):
        if raw_input:
            internal.append({"role": "user", "content": raw_input})
        return system_text, internal
    if not isinstance(raw_input, Sequence) or isinstance(raw_input, (str, bytes)):
        return system_text, internal

    for item in raw_input:
        if not isinstance(item, Mapping):
            if isinstance(item, str):
                internal.append({"role": "user", "content": item})
            continue
        item_type = item.get("type")
        if item_type == "message" or item_type is None:
            role = item.get("role")
            if role not in ("user", "assistant"):
                if role == "system" or role == "developer":
                    text = _flatten_content(item.get("content"))
                    system_text = f"{system_text}\n{text}".strip() if system_text else text
                continue
            text = _flatten_content(item.get("content"))
            if text:
                internal.append({"role": role, "content": text})
        elif item_type == "function_call":
            payload = {
                "name": item.get("name") if isinstance(item.get("name"), str) else "",
                "arguments": _parse_arguments(item.get("arguments")),
            }
            fence = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
            internal.append({"role": "assistant", "content": fence})
        elif item_type == "function_call_output":
            call_id = item.get("call_id")
            content = _flatten_call_output(item.get("output"))
            header = f"Function result for tool_use_id={call_id}"
            internal.append({"role": "user", "content": f"{header}:\n{content}"})
        # reasoning, local_shell_call 등은 스킵
    return system_text, internal


# ─── 2. 프롬프트 조립 (다른 브리지와 동일 직렬화) ──────────────────────


def build_tool_prompt(
    system_text: str,
    tools: Sequence[Mapping[str, Any]],
    tool_choice: object,
    messages: Sequence[Mapping[str, str]],
) -> str:
    lines: list[str] = []
    if system_text:
        lines.append(f"System: {system_text}")
    catalog = serialize_tools_for_prompt(tools)
    if catalog:
        lines.append(catalog)
    directive = build_tool_choice_directive(tool_choice)
    if directive:
        lines.append(directive)
    for msg in messages:
        prefix = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{prefix}: {msg.get('content', '')}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


# ─── 3. 응답 변환 ──────────────────────────────────────────────────────


def _count_tokens_estimate(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 3)


def _message_item(text: str) -> dict[str, Any]:
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _function_call_item(block: ToolUseBlock) -> dict[str, Any]:
    return {
        "id": f"fc_{uuid.uuid4().hex[:24]}",
        "type": "function_call",
        "status": "completed",
        "call_id": block.tool_use_id,
        "name": block.name,
        "arguments": block.input_json,
    }


def build_responses_output(text: str, blocks: Sequence[ToolUseBlock]) -> list[dict[str, Any]]:
    """완성 텍스트 + tool_use 블록 → Responses ``output`` items."""
    items: list[dict[str, Any]] = []
    content = strip_tool_call_syntax(text) if blocks and text.strip() else text
    if content and content.strip():
        items.append(_message_item(content))
    items.extend(_function_call_item(block) for block in blocks)
    return items


def build_responses_response(
    model: str,
    text: str,
    blocks: Sequence[ToolUseBlock],
) -> dict[str, Any]:
    """비스트리밍 Responses API 응답."""
    output = build_responses_output(text, blocks)
    input_tokens = _count_tokens_estimate(text)
    output_tokens = _count_tokens_estimate(text)
    return {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "output_text": strip_tool_call_syntax(text) if blocks else text,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


# ─── 4. SSE 이벤트 스트림 ──────────────────────────────────────────────


def _sse(event_type: str, payload: Mapping[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def responses_stream_events(
    model: str,
    text: str,
    blocks: Sequence[ToolUseBlock],
) -> list[str]:
    """완성 텍스트를 Responses API SSE 이벤트 프레임으로 직렬화.

    순서: response.created → item added → (text delta | arguments delta) →
    item done → response.completed. buffer-then-emit (판정이 완성 텍스트 기반).
    """
    response_id = f"resp_{uuid.uuid4().hex[:24]}"
    frames: list[str] = []
    created: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "in_progress",
        "model": model,
        "output": [],
    }
    frames.append(_sse("response.created", {"type": "response.created", "response": created}))
    frames.append(
        _sse(
            "response.in_progress",
            {"type": "response.in_progress", "response": {**created, "status": "in_progress"}},
        )
    )

    output = build_responses_output(text, blocks)
    for output_index, item in enumerate(output):
        frames.append(
            _sse(
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": output_index,
                    "item": {**item, "status": "in_progress"},
                },
            )
        )
        if item["type"] == "message":
            for content_index, part in enumerate(item["content"]):
                frames.append(
                    _sse(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": item["id"],
                            "output_index": output_index,
                            "content_index": content_index,
                            "delta": part["text"],
                        },
                    )
                )
                frames.append(
                    _sse(
                        "response.output_text.done",
                        {
                            "type": "response.output_text.done",
                            "item_id": item["id"],
                            "output_index": output_index,
                            "content_index": content_index,
                            "text": part["text"],
                        },
                    )
                )
        elif item["type"] == "function_call":
            frames.append(
                _sse(
                    "response.function_call_arguments.delta",
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": item["id"],
                        "output_index": output_index,
                        "delta": item["arguments"],
                    },
                )
            )
            frames.append(
                _sse(
                    "response.function_call_arguments.done",
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": item["id"],
                        "output_index": output_index,
                        "arguments": item["arguments"],
                    },
                )
            )
        frames.append(
            _sse(
                "response.output_item.done",
                {"type": "response.output_item.done", "output_index": output_index, "item": item},
            )
        )

    input_tokens = _count_tokens_estimate(text)
    output_tokens = _count_tokens_estimate(text)
    completed = {
        **created,
        "status": "completed",
        "output": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }
    frames.append(_sse("response.completed", {"type": "response.completed", "response": completed}))
    return frames
