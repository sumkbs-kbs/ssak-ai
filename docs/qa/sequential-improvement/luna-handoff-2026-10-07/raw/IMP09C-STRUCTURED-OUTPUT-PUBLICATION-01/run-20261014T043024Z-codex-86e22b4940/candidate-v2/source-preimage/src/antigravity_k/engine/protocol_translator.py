"""Ssak-Ai: 프로토콜 변환기.

==============================
9Router의 formats.js 패턴 이식 — OpenAI / Anthropic / 내부 포맷 간 자동 변환.

핵심 기능:
- translate_request(): 외부 API 포맷 → 내부 포맷 변환
- translate_response(): 내부 포맷 → 외부 API 포맷 변환
- detect_format(): 요청 포맷 자동 감지
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from enum import Enum
from typing import TypedDict, TypeGuard, cast

logger = logging.getLogger("antigravity_k.protocol_translator")

Payload = dict[str, object]
Body = Mapping[str, object]


class RequestPayload(TypedDict):
    prompt: str
    messages: list[Payload]
    system: str
    model: str
    max_tokens: int
    temperature: float
    top_p: float
    stream: bool
    stop: list[str]
    stop_sequences: list[str]


class ResponseMessage(TypedDict):
    role: str
    content: str


class ResponseChoice(TypedDict):
    index: int
    message: ResponseMessage
    finish_reason: str


class ResponseUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_tokens: int
    output_tokens: int


class ResponseContentBlock(TypedDict):
    type: str
    text: str


class ResponsePayload(TypedDict):
    id: str
    object: str
    created: int
    model: str
    choices: list[ResponseChoice]
    content: list[ResponseContentBlock]
    type: str
    role: str
    finish_reason: str
    stop_reason: str
    usage: ResponseUsage
    tokens_in: int
    tokens_out: int


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _mapping(value: object) -> Payload:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): item for key, item in mapping.items()}
    return {}


def _mappings(value: object) -> list[Payload]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [_mapping(item) for item in items if _is_mapping(item)]


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _number(value: object, default: float) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _boolean(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [item for item in items if isinstance(item, str)]


class APIFormat(Enum):
    """지원하는 API 포맷."""

    OPENAI = "openai"  # OpenAI Chat Completion API
    ANTHROPIC = "anthropic"  # Anthropic Messages API
    INTERNAL = "internal"  # Ssak-Ai 내부 포맷


class ProtocolTranslator:
    """API 요청/응답 포맷 자동 변환기.

    9Router 패턴: formats.js의 translateBody() 구현을 Python으로 이식.
    OpenAI ↔ Anthropic ↔ 내부 포맷 간 양방향 변환 지원.

    사용 예시:
        translator = ProtocolTranslator()

        # OpenAI 포맷 → 내부 포맷
        internal = translator.translate_request(openai_body, APIFormat.OPENAI)

        # 내부 포맷 → OpenAI 포맷
        openai_resp = translator.translate_response(internal_resp, APIFormat.OPENAI)
    """

    # ─── 요청 변환 ───────────────────────────────────────────────────

    def translate_request(
        self,
        body: Body,
        source: APIFormat,
        target: APIFormat = APIFormat.INTERNAL,
    ) -> RequestPayload:
        """요청 포맷을 변환합니다.

        Args:
            body: 원본 요청 바디
            source: 원본 포맷
            target: 목표 포맷

        Returns:
            변환된 요청 바디

        """
        if source == target:
            return cast(RequestPayload, cast(object, _mapping(body)))

        # 먼저 내부 포맷으로 변환
        if source != APIFormat.INTERNAL:
            internal = self._to_internal_request(body, source)
        else:
            internal = _mapping(body)

        # 목표 포맷으로 변환
        if target != APIFormat.INTERNAL:
            return cast(RequestPayload, cast(object, self._from_internal_request(internal, target)))

        return cast(RequestPayload, cast(object, internal))

    def translate_response(
        self,
        body: Body,
        target: APIFormat,
        source: APIFormat = APIFormat.INTERNAL,
    ) -> ResponsePayload:
        """응답 포맷을 변환합니다.

        Args:
            body: 원본 응답 바디
            target: 목표 포맷
            source: 원본 포맷

        Returns:
            변환된 응답 바디

        """
        if source == target:
            return cast(ResponsePayload, cast(object, _mapping(body)))

        # 먼저 내부 포맷으로 변환
        if source != APIFormat.INTERNAL:
            internal = self._to_internal_response(body, source)
        else:
            internal = _mapping(body)

        # 목표 포맷으로 변환
        if target != APIFormat.INTERNAL:
            return cast(ResponsePayload, cast(object, self._from_internal_response(internal, target)))

        return cast(ResponsePayload, cast(object, internal))

    # ─── 포맷 감지 ───────────────────────────────────────────────────

    @staticmethod
    def detect_format(body: Body) -> APIFormat:
        """요청 바디에서 API 포맷을 자동 감지합니다.

        - "messages" + "model" → OpenAI
        - "messages" + "max_tokens" (no "model") → Anthropic (드문 케이스)
        - "prompt" → 내부 포맷
        """
        if "messages" in body:
            # Anthropic은 anthropic_version 헤더를 사용하지만,
            # 바디 기반으로는 구분이 어려움 → 기본 OpenAI로 처리
            if body.get("anthropic_version"):
                return APIFormat.ANTHROPIC
            return APIFormat.OPENAI
        elif "prompt" in body:
            return APIFormat.INTERNAL
        else:
            return APIFormat.OPENAI  # 기본값

    # ─── 내부 포맷 정의 ──────────────────────────────────────────────
    #
    # Ssak-Ai 내부 포맷:
    # {
    #     "prompt": str,                      # 최종 프롬프트 텍스트
    #     "system": str,                      # 시스템 메시지
    #     "messages": [{"role": str, "content": str}],  # 대화 이력
    #     "model": str,                       # 모델 이름
    #     "max_tokens": int,
    #     "temperature": float,
    #     "top_p": float,
    #     "stream": bool,
    #     "stop": List[str],
    # }

    # ─── OpenAI → 내부 ──────────────────────────────────────────────

    def _openai_to_internal_request(self, body: Body) -> Payload:
        """OpenAI Chat Completion 요청 → 내부 포맷."""
        messages = _mappings(body.get("messages", []))
        system_msg = ""
        chat_messages: list[Payload] = []

        for msg in messages:
            role = _text(msg.get("role", ""))
            raw_content = self._extract_content(msg.get("content", ""))
            content: str = raw_content if isinstance(raw_content, str) else ""
            if role == "system":
                system_msg = content
            else:
                chat_messages.append({"role": role, "content": content})

        return {
            "messages": chat_messages,
            "system": system_msg,
            "model": _text(body.get("model", "")),
            "max_tokens": _integer(body.get("max_tokens", 4096), 4096),
            "temperature": _number(body.get("temperature", 0.7), 0.7),
            "top_p": _number(body.get("top_p", 0.9), 0.9),
            "stream": _boolean(body.get("stream", False)),
            "stop": _strings(body.get("stop", [])),
        }

    # ─── Anthropic → 내부 ───────────────────────────────────────────

    def _anthropic_to_internal_request(self, body: Body) -> Payload:
        """Anthropic Messages API 요청 → 내부 포맷."""
        messages = _mappings(body.get("messages", []))
        system_msg = _text(body.get("system", ""))

        # Anthropic의 system은 최상위 필드
        chat_messages: list[Payload] = []
        for msg in messages:
            role = _text(msg.get("role", ""))
            raw_content = self._extract_content(msg.get("content", ""))
            content: str = raw_content if isinstance(raw_content, str) else ""
            chat_messages.append({"role": role, "content": content})

        return {
            "messages": chat_messages,
            "system": system_msg,
            "model": _text(body.get("model", "")),
            "max_tokens": _integer(body.get("max_tokens", 4096), 4096),
            "temperature": _number(body.get("temperature", 0.7), 0.7),
            "top_p": _number(body.get("top_p", 0.9), 0.9),
            "stream": _boolean(body.get("stream", False)),
            "stop": _strings(body.get("stop_sequences", [])),
        }

    # ─── 내부 → OpenAI ──────────────────────────────────────────────

    def _internal_to_openai_response(self, body: Body) -> Payload:
        """내부 응답 → OpenAI Chat Completion 응답."""
        content = _text(body.get("content", ""))
        model = _text(body.get("model", "antigravity-k"), "antigravity-k")

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": _text(body.get("finish_reason", "stop"), "stop"),
                },
            ],
            "usage": {
                "prompt_tokens": _integer(body.get("tokens_in", 0)),
                "completion_tokens": _integer(body.get("tokens_out", 0)),
                "total_tokens": _integer(body.get("tokens_in", 0)) + _integer(body.get("tokens_out", 0)),
            },
        }

    # ─── 내부 → Anthropic ───────────────────────────────────────────

    def _internal_to_anthropic_response(self, body: Body) -> Payload:
        """내부 응답 → Anthropic Messages API 응답."""
        content = _text(body.get("content", ""))
        model = _text(body.get("model", "antigravity-k"), "antigravity-k")

        return {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": content,
                },
            ],
            "model": model,
            "stop_reason": _text(body.get("finish_reason", "end_turn"), "end_turn"),
            "usage": {
                "input_tokens": _integer(body.get("tokens_in", 0)),
                "output_tokens": _integer(body.get("tokens_out", 0)),
            },
        }

    # ─── 라우팅 메서드 ──────────────────────────────────────────────

    def _to_internal_request(self, body: Body, source: APIFormat) -> Payload:
        """외부 포맷 → 내부 포맷 변환 라우팅."""
        if source == APIFormat.OPENAI:
            return self._openai_to_internal_request(body)
        elif source == APIFormat.ANTHROPIC:
            return self._anthropic_to_internal_request(body)
        else:
            return _mapping(body)

    def _from_internal_request(self, body: Body, target: APIFormat) -> Payload:
        """내부 포맷 → 외부 포맷 변환 라우팅."""
        if target == APIFormat.OPENAI:
            return self._internal_to_openai_request(body)
        elif target == APIFormat.ANTHROPIC:
            return self._internal_to_anthropic_request(body)
        else:
            return _mapping(body)

    def _to_internal_response(self, body: Body, source: APIFormat) -> Payload:
        """외부 응답 → 내부 응답 변환 라우팅."""
        if source == APIFormat.OPENAI:
            return self._openai_to_internal_response(body)
        elif source == APIFormat.ANTHROPIC:
            return self._anthropic_to_internal_response(body)
        else:
            return _mapping(body)

    def _from_internal_response(self, body: Body, target: APIFormat) -> Payload:
        """내부 응답 → 외부 응답 변환 라우팅."""
        if target == APIFormat.OPENAI:
            return self._internal_to_openai_response(body)
        elif target == APIFormat.ANTHROPIC:
            return self._internal_to_anthropic_response(body)
        else:
            return _mapping(body)

    # ─── 추가 변환 헬퍼 ─────────────────────────────────────────────

    def _internal_to_openai_request(self, body: Body) -> Payload:
        """내부 포맷 → OpenAI 요청."""
        messages: list[Payload] = []
        system = _text(body.get("system", ""))
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(_mappings(body.get("messages", [])))

        result: Payload = {
            "model": _text(body.get("model", "")),
            "messages": messages,
            "max_tokens": _integer(body.get("max_tokens", 4096), 4096),
            "temperature": _number(body.get("temperature", 0.7), 0.7),
            "stream": _boolean(body.get("stream", False)),
        }
        stop = _strings(body.get("stop", []))
        if stop:
            result["stop"] = stop
        return result

    def _internal_to_anthropic_request(self, body: Body) -> Payload:
        """내부 포맷 → Anthropic 요청."""
        result: Payload = {
            "model": _text(body.get("model", "")),
            "messages": _mappings(body.get("messages", [])),
            "max_tokens": _integer(body.get("max_tokens", 4096), 4096),
        }
        system = _text(body.get("system", ""))
        if system:
            result["system"] = system
        if "temperature" in body:
            result["temperature"] = _number(body.get("temperature"), 0.7)
        stop = _strings(body.get("stop", []))
        if stop:
            result["stop_sequences"] = stop
        if _boolean(body.get("stream", False)):
            result["stream"] = True
        return result

    def _openai_to_internal_response(self, body: Body) -> Payload:
        """OpenAI 응답 → 내부 포맷."""
        choices = _mappings(body.get("choices", []))
        content = ""
        finish_reason = "stop"
        if choices:
            message = _mapping(choices[0].get("message", {}))
            content = _text(message.get("content", ""))
            finish_reason = _text(choices[0].get("finish_reason", "stop"), "stop")

        usage = _mapping(body.get("usage", {}))
        return {
            "content": content,
            "model": _text(body.get("model", "")),
            "finish_reason": finish_reason,
            "tokens_in": _integer(usage.get("prompt_tokens", 0)),
            "tokens_out": _integer(usage.get("completion_tokens", 0)),
        }

    def _anthropic_to_internal_response(self, body: Body) -> Payload:
        """Anthropic 응답 → 내부 포맷."""
        content_blocks = _mappings(body.get("content", []))
        content = ""
        for block in content_blocks:
            if _text(block.get("type")) == "text":
                content += _text(block.get("text", ""))

        usage = _mapping(body.get("usage", {}))
        return {
            "content": content,
            "model": _text(body.get("model", "")),
            "finish_reason": _text(body.get("stop_reason", "stop"), "stop"),
            "tokens_in": _integer(usage.get("input_tokens", 0)),
            "tokens_out": _integer(usage.get("output_tokens", 0)),
        }

    # ─── 유틸 ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_content(content: object) -> str | list[Payload]:
        """메시지 content 필드 정규화.

        OpenAI는 str 또는 List[dict] (멀티모달) 형식을 지원.
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            content_items = cast(list[object], content)
            items = [_mapping(item) for item in content_items if _is_mapping(item)]
            # Check if there are any non-text items (e.g. image_url)
            has_multimodal = any(_text(item.get("type")) != "text" for item in items)
            if has_multimodal:
                return items  # Preserve the entire list for VLM processing

            # If it's just text blocks, combine them
            parts: list[str] = []
            for item in items:
                if _text(item.get("type")) == "text":
                    parts.append(_text(item.get("text", "")))
            return "\n".join(parts)
        return str(content) if content else ""
