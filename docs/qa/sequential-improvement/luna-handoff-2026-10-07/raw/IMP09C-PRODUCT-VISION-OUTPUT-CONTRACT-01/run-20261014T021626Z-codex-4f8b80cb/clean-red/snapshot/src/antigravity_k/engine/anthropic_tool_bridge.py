"""Anthropic tool-use 브리지 — 로컬 모델을 위한 도구 호출 프로토콜 변환.

============================================================
벤치마킹 출처: unsloth (로컬 모델 + Claude Code/MCP tool calling 연결),
freebuff (에이전트 도구 사용 워크플로).

로컬 27B급 모델은 Anthropic의 tool_use JSON을 네이티브로 생성하지 않고,
텍스트 형식으로 도구 호출을 출력한다. 이 모듈은 양방향 변환을 담당한다:

1. 요청 변환: Anthropic ``tools`` 정의 → 시스템 프롬프트 도구 카탈로그 주입
2. 히스토리 변환: ``tool_use``/``tool_result`` content 블록 → 모델이 이해하는 텍스트
3. 응답 변환: 모델 텍스트의 tool_call 블록 → Anthropic ``tool_use`` content 블록

추출/수리는 기존 `RobustToolParser`를 재사용한다 (단일 파서 원칙 — 새 파서 금지).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from antigravity_k.engine.robust_tool_parser import RobustToolParser

logger = logging.getLogger("antigravity_k.api.anthropic_tool_bridge")

_STOP_REASONS = ("end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal")


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    """모델 출력에서 추출된 도구 호출 — Anthropic tool_use 블록으로 변환된다."""

    tool_use_id: str
    name: str
    input_json: str  # 문자열 JSON (Anthropic input 필드 규약)
    repaired: bool


# ─── 1. 요청 변환: tools 정의 → 프롬프트 ──────────────────────────────


def serialize_tools_for_prompt(tools: Sequence[Mapping[str, Any]]) -> str:
    """Anthropic tools 배열을 모델용 도구 카탈로그 텍스트로 직렬화.

    로컬 모델이 json 코드펜스 형식을 학습할 수 있도록 사용 규약과 예시를 포함한다.

    Note:
        ``<tool_call>`` 리터럴은 카탈로그에 사용하지 않는다. 일부 llama.cpp
        런너(qwen3 GGUF)는 해당 토큰을 *생성*할 때 세그폴트로 죽어 Ollama가
        ``{"error":"EOF"}``를 반환한다(2026-09-04 라이브 검증). 응답 파싱은
        `RobustToolParser`가 ``<tool_call>``과 json 코드펜스를 모두 지원하므로
        카탈로그만 코드펜스 형식으로 안내해도 추출은 동일하게 동작한다.
    """
    if not tools:
        return ""
    lines = [
        "# Tool Use",
        "",
        "To invoke a function, output ONLY a json code fence like:",
        "",
        "```json",
        '{"name": "get_weather", "arguments": {"city": "Seoul"}}',
        "```",
        "",
        "Available functions:",
        "",
    ]
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        description = tool.get("description")
        desc = description if isinstance(description, str) else ""
        lines.append(f"- {name}: {desc}")
        schema = tool.get("input_schema")
        if isinstance(schema, Mapping):
            try:
                lines.append(f"  parameters (JSON Schema): {json.dumps(schema, ensure_ascii=False)}")
            except (TypeError, ValueError):
                logger.debug("tool %s: input_schema 직렬화 실패 — 스킵", name)
    return "\n".join(lines)


def build_tool_choice_directive(tool_choice: object) -> str:
    """Anthropic tool_choice → 모델 지시문."""
    if tool_choice is None:
        return ""
    if isinstance(tool_choice, Mapping):
        kind = tool_choice.get("type")
        if kind == "any":
            return "You MUST use one of the available tools to respond."
        if kind == "tool":
            name = tool_choice.get("name")
            if isinstance(name, str) and name.strip():
                return f'You MUST use the "{name}" tool to respond.'
        if kind == "none":
            return "Do not use any tools. Respond with plain text only."
        return ""
    if tool_choice == "auto":
        return ""
    return ""


# ─── 2. 히스토리 변환: tool_use / tool_result 블록 → 텍스트 ────────────


def flatten_message_content(content: object) -> str:
    """Anthropic content (문자열 또는 블록 배열) → 단일 텍스트.

    tool_use 블록은 모델이 자기 출력으로 인식할 수 있게 json 코드펜스 형식으로
    복원하고, tool_result는 함수 결과 블록으로 직렬화한다.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            if isinstance(block, str):
                parts.append(block)
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif block_type == "tool_use":
            parts.append(_serialize_tool_use_block(block))
        elif block_type == "tool_result":
            parts.append(_serialize_tool_result_block(block))
    return "\n".join(part for part in parts if part)


def _serialize_tool_use_block(block: Mapping[str, Any]) -> str:
    name = block.get("name")
    tool_input = block.get("input")
    payload: dict[str, Any] = {
        "name": name if isinstance(name, str) else "",
        "arguments": tool_input if isinstance(tool_input, Mapping) else {},
    }
    try:
        body = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        body = json.dumps({"name": payload["name"], "arguments": {}}, ensure_ascii=False)
    return f"```json\n{body}\n```"


def _serialize_tool_result_block(block: Mapping[str, Any]) -> str:
    tool_use_id = block.get("tool_use_id")
    content = block.get("content")
    text_parts: list[str] = []
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                text_parts.append(str(item["text"]))
    is_error = block.get("is_error") is True
    header = f"Function result for tool_use_id={tool_use_id}" + (" (error)" if is_error else "")
    return f"{header}:\n{' '.join(text_parts)}"


# ─── 3. 응답 변환: 모델 텍스트 → tool_use 블록 ─────────────────────────


def extract_tool_use_blocks(text: str) -> list[ToolUseBlock]:
    """모델 출력에서 tool_call 블록을 추출해 Anthropic tool_use로 변환.

    RobustToolParser를 재사용해 27B 모델의 흔한 JSON 형식 오류를 수리한다.
    """
    blocks: list[ToolUseBlock] = []
    for parsed in RobustToolParser.extract_tool_calls(text):
        try:
            input_json = json.dumps(parsed.arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            input_json = "{}"
        blocks.append(
            ToolUseBlock(
                tool_use_id=f"toolu_{uuid.uuid4().hex[:16]}",
                name=parsed.name,
                input_json=input_json,
                repaired=parsed.repaired,
            ),
        )
    return blocks


def strip_tool_call_syntax(text: str) -> str:
    """모델 출력에서 도구 호출 마커(태그·코드펜스)를 제거한 나머지 텍스트를 반환.

    코드펜스는 `RobustToolParser`의 백틱 폴백과 동일하게 ``"name"`` 키를 가진
    블록만 제거한다 — 모델이 보여주는 일반 json 설정 블록은 보존된다.
    """
    import re

    text = re.sub(r"<tool_call>\s*.*?\s*</tool_call>", "", text, flags=re.DOTALL)
    return re.sub(
        r'```(?:json)?\s*\{\s*"name"\s*:.*?\}\s*```',
        "",
        text,
        flags=re.DOTALL,
    ).strip()


def resolve_stop_reason(text: str, tool_blocks: Sequence[ToolUseBlock], *, max_tokens_hit: bool) -> str:
    """Anthropic stop_reason 결정.

    - tool_use 블록이 있으면 항상 "tool_use" (에이전트 루프가 계속 돌아야 함)
    - 아니면 기존 end_turn
    """
    if tool_blocks:
        return "tool_use"
    if max_tokens_hit:
        return "max_tokens"
    return "end_turn"


def build_content_blocks(
    text: str,
    tool_blocks: Sequence[ToolUseBlock],
) -> list[dict[str, Any]]:
    """최종 Anthropic content 배열 구성.

    text 블록은 tool_call 태그를 제거한 나머지이며, 그 뒤에 tool_use 블록이 온다.
    text가 비어 있으면(모델이 도구 호출만 한 경우) text 블록은 생략한다.
    """
    blocks: list[dict[str, Any]] = []
    remaining = strip_tool_call_syntax(text)
    if remaining:
        blocks.append({"type": "text", "text": remaining})
    for tool in tool_blocks:
        try:
            parsed_input: dict[str, Any] = json.loads(tool.input_json)
        except (json.JSONDecodeError, TypeError):
            parsed_input = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": tool.tool_use_id,
                "name": tool.name,
                "input": parsed_input,
            },
        )
    return blocks
