"""MCP 도구 호출 결과의 typed 표현.

MCP `CallToolResult` 는 평문 텍스트만이 아니라 `isError`·`structuredContent`·image/
resource 블록을 함께 싣는다. 종전 `MCPTool.execute` 는 텍스트 블록만 이어붙이고 나머지를
버렸기 때문에, 호스트는 실패를 **문자열 모양으로 추측**해야 했고 서버가 `isError=true` 로
보고한 오류가 "성공"으로 기록됐다(연속 오류 카운터·실패 이벤트·이력 모두 성공).

`MCPToolOutcome` 은 `str` 하위 클래스다. 텍스트 표현(모델이 보는 값)은 그대로 문자열이라
기존 소비자(도구 루프·이벤트 버스·로그·감사)와 호환되고, 기계 판독 필드는 속성으로 붙는다.
그래야 호스트가 텍스트 추측 대신 `is_error` 를 직접 소비할 수 있다.

손실 없음 원칙:
- 텍스트 블록은 **원문 그대로**, 순서대로 이어붙인다.
- `structuredContent` 는 원문 JSON 으로 본문 뒤에 실어 모델도 볼 수 있게 한다.
- 비텍스트 블록(image/resource/resource_link)은 본문에 descriptor 를 남기고, 원본 필드는
  `blocks` 에 그대로 보존한다(base64 이미지 페이로드를 모델 컨텍스트에 밀어 넣지 않기 위한
  의도적 분리 — 데이터는 버리지 않는다).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import cast, final

logger = logging.getLogger(__name__)

STRUCTURED_HEADER = "[structuredContent]"


def _dump(value: object) -> object:
    """pydantic/모델 객체를 JSON 직렬화 가능한 형태로 낮춘다."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(exclude_none=True)
        except TypeError:
            return model_dump()
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _dump(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in cast(Sequence[object], value)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _field(block: object, name: str) -> object:
    """블록에서 필드를 꺼낸다(dict 블록과 pydantic 블록 모두 지원)."""
    if isinstance(block, Mapping):
        return cast(Mapping[object, object], block).get(name)
    return getattr(block, name, None)


def _json(payload: object) -> str:
    return json.dumps(_dump(payload), ensure_ascii=False, sort_keys=True)


def _short(value: str, limit: int = 120) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def render_block(block: object) -> tuple[str, dict[str, object]]:
    """블록 하나를 (모델이 보는 text, 보존용 descriptor) 로 변환한다."""
    kind = _field(block, "type")
    kind_name = kind if isinstance(kind, str) else ""

    if kind_name == "text":
        raw = _field(block, "text")
        text = raw if isinstance(raw, str) else str(raw)
        return text, {"type": "text", "text": text, "text_length": len(text)}

    if kind_name == "image":
        data = _field(block, "data")
        data_text = data if isinstance(data, str) else str(data)
        mime = _field(block, "mimeType")
        mime_text = mime if isinstance(mime, str) and mime else "unknown"
        descriptor: dict[str, object] = {"type": "image", "mimeType": mime_text, "data": data_text}
        return (
            f"[image: {mime_text} — base64 {len(data_text)} chars, payload kept in result.blocks]",
            descriptor,
        )

    if kind_name == "resource":
        resource = _field(block, "resource") or {}
        uri = _field(resource, "uri")
        mime = _field(resource, "mimeType")
        inner_text = _field(resource, "text")
        mime_text = mime if isinstance(mime, str) and mime else "unknown"
        descriptor = {
            "type": "resource",
            "uri": uri if isinstance(uri, str) else str(uri),
            "mimeType": mime_text,
        }
        if isinstance(inner_text, str):
            # 임베디드 리소스의 텍스트는 그대로 모델에게 보여준다(손실 없음).
            descriptor["text"] = inner_text
            header = f"[resource: {descriptor['uri']} ({mime_text})]"
            return f"{header}\n{inner_text}", descriptor
        blob = _field(resource, "blob")
        blob_text = blob if isinstance(blob, str) else ""
        descriptor["blob"] = blob_text
        return (
            f"[resource: {descriptor['uri']} ({mime_text}) — binary payload "
            f"{len(blob_text)} base64 chars, payload kept in result.blocks]",
            descriptor,
        )

    if kind_name == "resource_link":
        # 주의: SDK 는 uri 를 AnyUrl 로 준다 — str 판정으로 거르면 링크가 통째로 사라진다.
        uri = _field(block, "uri")
        uri_text = uri if isinstance(uri, str) else (str(uri) if uri is not None else "")
        name = _field(block, "name")
        name_text = name if isinstance(name, str) else ""
        mime = _field(block, "mimeType")
        mime_text = mime if isinstance(mime, str) and mime else "unknown"
        return (
            f"[resource link: {name_text} {uri_text} ({mime_text})]",
            {
                "type": "resource_link",
                "uri": uri_text,
                "name": name_text,
                "mimeType": mime_text,
            },
        )

    # 알 수 없는 블록 타입은 표현을 버리지 않고 그대로 남긴다(다른 MCP 서버 호환).
    return str(block), {"type": kind_name or "unknown", "repr": _short(str(block), 500)}


def render_content(content: object) -> tuple[str, tuple[dict[str, object], ...]]:
    """content 블록 목록을 (text, blocks) 로 변환한다."""
    if content is None:
        return "", ()
    if isinstance(content, (str, bytes)):
        text = content.decode("utf-8", "replace") if isinstance(content, bytes) else content
        return text, ({"type": "text", "text": text, "text_length": len(text)},)
    if not isinstance(content, Sequence):
        return str(content), ({"type": "unknown", "repr": _short(str(content), 500)},)
    blocks = cast(Sequence[object], content)
    lines: list[str] = []
    descriptors: list[dict[str, object]] = []
    for block in blocks:
        line, descriptor = render_block(block)
        lines.append(line)
        descriptors.append(descriptor)
    return "\n".join(lines), tuple(descriptors)


def extract_error_code(text: str) -> str | None:
    """텍스트가 기계 판독 오류 봉투면 코드를 꺼낸다.

    예: ``{"error": {"code": "INVALID_TOOL_ARGS", ...}}`` → ``INVALID_TOOL_ARGS``
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    mapping = cast(Mapping[str, object], payload)
    error = mapping.get("error")
    code: object = None
    if isinstance(error, Mapping):
        code = cast(Mapping[str, object], error).get("code")
    else:
        code = mapping.get("code")
    return code if isinstance(code, str) and code else None


def detect_partial(structured: Mapping[str, object] | None, text: str) -> bool:
    """부분 성공 표시를 찾는다.

    MCP 와이어에는 `partial` 필드가 없다(호스트 계약 `ssak-web` 에만 있다). 그래서
    `structuredContent` 를 우선 보고, 없으면 텍스트 봉투를 파싱해 `partial: true` /
    `status: "partial"` 을 찾는다. 서버가 이 필드를 실제로 싣기 시작하면 그대로 통하게
    되는 임시 다리이며, 없으면 False 다.
    """
    candidates: list[object] = []
    if structured is not None:
        candidates.append(structured)
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            candidates.append(json.loads(stripped))
        except (json.JSONDecodeError, ValueError):
            pass
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        mapping = cast(Mapping[str, object], candidate)
        if mapping.get("partial") is True:
            return True
        if mapping.get("status") == "partial":
            return True
    return False


@final
class MCPToolOutcome(str):
    """MCP 도구 호출 결과 — 문자열 본문 + 기계 판독 필드.

    문자열처럼 쓰이는 모든 곳(`str(result)`, 로그, 이벤트 payload, 감사 기록)은 본문을
    그대로 얻고, 판정이 필요한 곳은 `is_error` 같은 속성을 직접 읽는다.
    """

    # 기본값을 클래스 몸통에 둔다 — 값은 __new__ 에서 채우고, 정적 검사기에는
    # "초기화되지 않은 인스턴스 변수"로 보이지 않게 한다.
    text: str = ""
    is_error: bool = False
    error_code: str | None = None
    structured_content: Mapping[str, object] | None = None
    blocks: tuple[dict[str, object], ...] = ()
    partial: bool = False
    server_name: str = ""
    tool_name: str = ""
    transport: str = ""

    def __new__(
        cls,
        text: str,
        *,
        is_error: bool = False,
        error_code: str | None = None,
        structured_content: Mapping[str, object] | None = None,
        blocks: Sequence[dict[str, object]] = (),
        partial: bool = False,
        server_name: str = "",
        tool_name: str = "",
        transport: str = "",
    ) -> MCPToolOutcome:
        outcome = super().__new__(cls, text)
        outcome.text = text
        outcome.is_error = is_error
        outcome.error_code = error_code
        outcome.structured_content = structured_content
        outcome.blocks = tuple(blocks)
        outcome.partial = partial
        outcome.server_name = server_name
        outcome.tool_name = tool_name
        outcome.transport = transport
        return outcome

    def metadata(self) -> dict[str, object]:
        """감사·이벤트용 요약(본문 전체와 base64 페이로드는 제외)."""
        return {
            "server": self.server_name,
            "tool": self.tool_name,
            "transport": self.transport,
            "is_error": self.is_error,
            "error_code": self.error_code,
            "partial": self.partial,
            "structured": self.structured_content is not None,
            "blocks": [block.get("type") for block in self.blocks],
            "text_length": len(self.text),
        }


def error_outcome(
    message: str,
    *,
    server_name: str = "",
    tool_name: str = "",
    transport: str = "",
    error_code: str | None = None,
) -> MCPToolOutcome:
    """서버에 도달하기 전/도달하지 못한 실패를 typed 결과로 만든다.

    오류 본문은 ``Error:`` 로 시작한다 — typed 플래그를 읽지 않는 레거시 소비자도
    실패를 실패로 보게 하는 이중 안전장치다(`result_indicates_failure` 가 인식하는 형태).
    """
    text = f"Error: {message}"
    return MCPToolOutcome(
        text,
        is_error=True,
        error_code=error_code,
        server_name=server_name,
        tool_name=tool_name,
        transport=transport,
    )


def build_outcome(
    result: object,
    *,
    server_name: str = "",
    tool_name: str = "",
    transport: str = "",
) -> MCPToolOutcome:
    """`ClientSession.call_tool` 의 `CallToolResult` 를 typed 결과로 변환한다."""
    raw_content = getattr(result, "content", None)
    if raw_content is None and isinstance(result, Mapping):
        raw_content = cast(Mapping[str, object], result).get("content")
    body, blocks = render_content(raw_content)

    raw_structured = getattr(result, "structuredContent", None)
    if raw_structured is None and isinstance(result, Mapping):
        raw_structured = cast(Mapping[str, object], result).get("structuredContent")
    structured: Mapping[str, object] | None = None
    if raw_structured:
        if isinstance(raw_structured, Mapping):
            structured = cast(Mapping[str, object], raw_structured)
        else:
            # 스펙상 structuredContent 는 객체다. 아니면 typed 필드에는 담지 않고
            # 본문(JSON)으로만 보존한다 — 데이터 자체는 잃지 않는다.
            logger.warning("MCP structuredContent 가 객체가 아니다: %s", type(raw_structured).__name__)

    raw_error = getattr(result, "isError", None)
    if raw_error is None and isinstance(result, Mapping):
        raw_error = cast(Mapping[str, object], result).get("isError")
    is_error = bool(raw_error)

    parts: list[str] = []
    if body:
        parts.append(body)
    if structured is not None:
        parts.append(f"{STRUCTURED_HEADER}\n{_json(structured)}")
    if not parts:
        # content 가 비어 있는 응답도 정보를 버리지 않는다(종전에는 결과 객체 자체를
        # 돌려줘 str 소비자에게 pydantic repr 이 새어 나갔다).
        parts.append(_json(result))
    text = "\n".join(parts)

    error_code = extract_error_code(body) if is_error else None
    partial = detect_partial(structured, body)

    if is_error:
        code_note = f" ({error_code})" if error_code else ""
        text = f"Error: MCP tool '{tool_name}' on server '{server_name}' reported an error{code_note}.\n{text}"

    return MCPToolOutcome(
        text,
        is_error=is_error,
        error_code=error_code,
        structured_content=structured,
        blocks=blocks,
        partial=partial,
        server_name=server_name,
        tool_name=tool_name,
        transport=transport,
    )
