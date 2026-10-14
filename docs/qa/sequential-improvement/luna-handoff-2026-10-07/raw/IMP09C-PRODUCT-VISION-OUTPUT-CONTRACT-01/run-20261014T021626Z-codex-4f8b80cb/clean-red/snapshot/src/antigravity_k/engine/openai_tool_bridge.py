"""OpenAI tool-use 브리지 — Chat Completions ``tools``/``tool_calls`` 경계 변환.

============================================================
벤치마킹 출처: unsloth (로컬 모델 + 코딩 에이전트 툴 호출 연결).

``anthropic_tool_bridge``가 /v1/messages(Anthropic) 경계를 담당하듯, 이 모듈은
/v1/chat/completions(OpenAI) 경계를 담당한다 (Codex 등 OpenAI 프로토콜 에이전트).

역방향/순방향 변환 모두 기존 브리지 프리미티브를 재사용한다 (단일 파서 원칙):
- 요청: OpenAI ``tools`` (function 포맷) → ``serialize_tools_for_prompt`` 입력 형식
- 히스토리: ``assistant.tool_calls`` / ``role:"tool"`` → 모델용 텍스트 (json 코드펜스 /
  Function result 블록 — Anthropic 경계와 동일 직렬화)
- 응답: 모델 텍스트의 tool_call 블록 → OpenAI ``tool_calls`` (arguments는 JSON *문자열*)
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
    extract_tool_use_blocks,
    serialize_tools_for_prompt,
    strip_tool_call_syntax,
)

logger = logging.getLogger("antigravity_k.api.openai_tool_bridge")


# ─── 1. 요청 변환: OpenAI tools → 브리지 카탈로그 형식 ─────────────────


def validate_openai_tools(raw_tools: object) -> tuple[list[dict[str, Any]], str | None]:
    """OpenAI tools 배열 검증 + 브리지 형식 변환. (tools, error_message).

    OpenAI 형식: ``{"type": "function", "function": {"name", "description", "parameters"}}``.
    변환 결과는 anthropic_tool_bridge.serialize_tools_for_prompt 입력 형식
    (``{"name", "description", "input_schema"}``)과 동일하다.
    """
    if raw_tools is None:
        return [], None
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)):
        return [], "tools: must be an array"
    tools: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_tools):
        if not isinstance(raw, Mapping):
            return [], f"tools[{index}]: must be an object"
        fn = raw.get("function")
        if isinstance(fn, Mapping):
            name = fn.get("name")
            description = fn.get("description")
            parameters = fn.get("parameters")
        else:
            # 방어: function 래퍼 없는 직접 형식도 허용
            name = raw.get("name")
            description = raw.get("description")
            parameters = raw.get("parameters")
        if not isinstance(name, str) or not name.strip():
            return [], f"tools[{index}].function.name: must be a non-empty string"
        tool: dict[str, Any] = {"name": name}
        if isinstance(description, str):
            tool["description"] = description
        if isinstance(parameters, Mapping):
            tool["input_schema"] = parameters
        tools.append(tool)
    return tools, None


def convert_tool_choice(raw: object) -> object:
    """OpenAI tool_choice → Anthropic 계열 (build_tool_choice_directive 입력)."""
    if raw is None:
        return None
    if raw == "auto":
        return "auto"
    if raw == "none":
        return {"type": "none"}
    if raw == "required":
        return {"type": "any"}
    if isinstance(raw, Mapping):
        fn = raw.get("function")
        if isinstance(fn, Mapping) and isinstance(fn.get("name"), str):
            return {"type": "tool", "name": fn["name"]}
    return "auto"


# ─── 2. 히스토리 변환: OpenAI messages → 내부 텍스트 ───────────────────


def _flatten_parts(content: object) -> str:
    """OpenAI content (문자열 또는 parts 배열) → 단일 텍스트."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, Mapping) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(part, str):
            parts.append(part)
    return "\n".join(part for part in parts if part)


def _parse_arguments(raw: object) -> dict[str, Any]:
    """OpenAI tool_calls의 arguments(JSON 문자열) → dict. 실패 시 방어적으로 처리."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        except json.JSONDecodeError:
            logger.debug("tool_calls.arguments JSON 파싱 실패 — 빈 인자로 대체")
    return {}


def openai_messages_to_internal(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, str]]]:
    """OpenAI messages → (system_text, 내부 messages).

    - ``assistant.tool_calls`` → 모델이 자기 출력으로 인식하는 json 코드펜스
    - ``role:"tool"`` → Function result 블록 (tool_use_id 라벨 유지 — 파서와 무관하지만
      Anthropic 경계와 동일한 직렬화를 유지해 모델 혼란을 줄임)
    """
    system_text = ""
    internal: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            text = _flatten_parts(message.get("content"))
            system_text = f"{system_text}\n{text}".strip() if system_text else text
            continue
        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            content = message.get("content")
            if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
                content = _flatten_parts(content)
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False) if content is not None else ""
            header = f"Function result for tool_use_id={tool_call_id}"
            internal.append({"role": "user", "content": f"{header}:\n{content}"})
            continue
        # user / assistant
        text = _flatten_parts(message.get("content"))
        tool_calls = message.get("tool_calls")
        if role == "assistant" and isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
            fences: list[str] = []
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    continue
                fn = call.get("function")
                if not isinstance(fn, Mapping):
                    continue
                payload = {
                    "name": fn.get("name") if isinstance(fn.get("name"), str) else "",
                    "arguments": _parse_arguments(fn.get("arguments")),
                }
                fences.append(f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```")
            if fences:
                text = "\n".join(part for part in [text, *fences] if part)
        if role not in ("user", "assistant"):
            continue
        internal.append({"role": role, "content": text})
    return system_text, internal


# ─── 3. 프롬프트 조립 (messages_api와 동일 직렬화) ──────────────────────


def effective_system(system: str, tools: Sequence[Mapping[str, Any]], tool_choice: object) -> str:
    """시스템 프롬프트 + 도구 카탈로그 + tool_choice 지시문."""
    sections: list[str] = [system] if system else []
    catalog = serialize_tools_for_prompt(tools)
    if catalog:
        sections.append(catalog)
    directive = build_tool_choice_directive(tool_choice)
    if directive:
        sections.append(directive)
    return "\n\n".join(sections)


def build_tool_prompt(system_text: str, messages: Sequence[Mapping[str, str]]) -> str:
    """내부 messages를 ModelManager 단일 프롬프트로 직렬화 (messages_api와 동일)."""
    lines: list[str] = []
    if system_text:
        lines.append(f"System: {system_text}")
    for msg in messages:
        prefix = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{prefix}: {msg.get('content', '')}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


# ─── 4. 응답 변환: tool_use 블록 → OpenAI tool_calls ───────────────────


def tool_blocks_to_tool_calls(blocks: Sequence[ToolUseBlock]) -> list[dict[str, Any]]:
    """ToolUseBlock 목록 → OpenAI tool_calls 배열 (arguments는 JSON 문자열)."""
    return [
        {
            "id": block.tool_use_id,
            "type": "function",
            "function": {"name": block.name, "arguments": block.input_json},
        }
        for block in blocks
    ]


def _count_tokens_estimate(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 3)


def build_openai_response(
    model: str,
    text: str,
    blocks: Sequence[ToolUseBlock],
) -> dict[str, Any]:
    """비스트리밍 chat.completion 응답 조립."""
    tool_calls = tool_blocks_to_tool_calls(blocks)
    content = None if blocks else text
    if blocks and text.strip():
        content = strip_tool_call_syntax(text)
    prompt_tokens = _count_tokens_estimate(text)
    completion_tokens = _count_tokens_estimate(text)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                },
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def extract_blocks(text: str) -> list[ToolUseBlock]:
    """모델 텍스트에서 tool_call 블록 추출 (anthropic_tool_bridge 파서 위임)."""
    return extract_tool_use_blocks(text)


# ─── 5. 스트리밍: OpenAI chunk 형식 ────────────────────────────────────


def _chunk(model: str, delta: dict[str, Any], finish_reason: str | None = None) -> str:
    data = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def openai_stream_frames(
    model: str,
    chunks: Sequence[str],
    blocks: Sequence[ToolUseBlock],
) -> list[str]:
    """완성 텍스트를 OpenAI SSE 프레임으로 직렬화.

    텍스트 델타를 먼저 흘리고, tool_calls가 있으면 말미에 tool_calls 델타를 보낸다
    (anthropic 경계의 _stream_events와 동일한 '텍스트 먼저, 판정은 완성 후' 순서).
    """
    frames: list[str] = [_chunk(model, {"role": "assistant"})]
    for chunk in chunks:
        if chunk:
            frames.append(_chunk(model, {"content": chunk}))
    if blocks:
        for index, block in enumerate(blocks):
            frames.append(
                _chunk(
                    model,
                    {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": block.tool_use_id,
                                "type": "function",
                                "function": {"name": block.name, "arguments": ""},
                            }
                        ]
                    },
                )
            )
            frames.append(
                _chunk(
                    model,
                    {"tool_calls": [{"index": index, "function": {"arguments": block.input_json}}]},
                )
            )
    frames.append(_chunk(model, {}, finish_reason="tool_calls" if blocks else "stop"))
    frames.append("data: [DONE]\n\n")
    return frames
