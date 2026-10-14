"""첨부(이미지)의 **단일 계약** — 파싱·검증·표면별 변환.

배경 (NX-09-F03)
----------------
화면은 파일을 고르면 `[첨부 파일: name]` **텍스트만** 입력창에 넣고 바이트는 보내지
않았다. 그래서 사용자는 이미지를 붙였다고 믿지만 모델은 파일명만 본다 — 조용한
거짓말이다. 이 모듈이 그 계약을 한 곳에서 소유한다.

계약 (ADR-0005)
---------------
1. **요청 표현**: `attachments: [{name, mime_type, data_base64}]` — 마지막 user 턴에
   붙는다(파일명 텍스트 표식은 이력 참조용으로 그대로 남는다).
2. **내부 정규형**: 메시지의 `content` 는 **항상 문자열**로 유지하고, 이미지는
   `images`(base64 배열) + `image_mimes`(형식 배열)로 나른다. 이 저장소에는
   `content` 를 문자열로 가정하는 코드가 많다(정규식·`.strip()`·SQLite 바인딩·
   스냅샷 스키마) — content 를 파트 배열로 바꾸면 그 자리들이 전부 죽는다
   (실측: 첨부 요청이 `'list' object has no attribute 'strip'` 로 500).
   `autonomous_qa.py` 가 이미 쓰던 관례(`{"content": str, "images": [b64]}`)와 같다.
3. **입력 호환**: OpenAI 호환 표면처럼 `content` 가 파트 배열로 오는 요청도 받는다 —
   `extract_images()` 가 파트를 message-level `images` 로 **끌어올린다**(버리지 않는다).
4. **표면별 변환**: OpenAI 호환은 파트 배열, Ollama 네이티브는 `images`, Anthropic 은
   `source.base64` 블록. 변환할 수 없는 입력은 조용히 버리지 않고 예외다.
5. **저장 표현**: 대화 저장소·스냅샷에는 텍스트만 남는다(base64 를 넣어 저장소를
   부풀리지 않는다). 따라서 이전 턴의 이미지는 그 턴에서만 모델에 간다.

이 모듈은 순수 함수만 둔다(부작용·I/O 없음).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Final, cast

__all__ = [
    "ALLOWED_IMAGE_MIME",
    "MAX_ATTACHMENTS",
    "MAX_ATTACHMENT_BYTES",
    "MAX_TOTAL_ATTACHMENT_BYTES",
    "AttachmentError",
    "ImageAttachment",
    "adapter_messages",
    "attach_to_latest_user_turn",
    "collect_images",
    "extract_images",
    "flatten_content",
    "has_images",
    "marker_text",
    "normalize_message",
    "parse_attachments",
    "prompt_message",
    "summarize",
    "to_anthropic_messages",
    "to_ollama_messages",
    "to_openai_messages",
]

#: 브라우저가 실제로 만들어 내는 형식만 허용한다 — 목록에 없는 형식은 **거부**한다.
ALLOWED_IMAGE_MIME: Final[tuple[str, ...]] = ("image/png", "image/jpeg", "image/webp", "image/gif")

#: 한 턴에 붙일 수 있는 개수.
MAX_ATTACHMENTS: Final[int] = 4
#: 개별 첨부의 디코딩 후 크기 상한.
MAX_ATTACHMENT_BYTES: Final[int] = 5 * 1024 * 1024
#: 한 턴 전체의 디코딩 후 크기 상한(base64 팽창 전 원본 기준).
MAX_TOTAL_ATTACHMENT_BYTES: Final[int] = 12 * 1024 * 1024

_DEFAULT_IMAGE_MIME: Final[str] = "image/png"
_MAX_NAME_LENGTH: Final[int] = 120


class AttachmentError(ValueError):
    """첨부 계약 위반 — 호출자가 400 으로 변환해 **이유를** 알려야 한다."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ImageAttachment:
    """검증을 통과한 첨부 1건(디코딩 후 바이트 길이를 함께 보관)."""

    name: str
    mime_type: str
    data_base64: str
    byte_length: int

    def to_data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.data_base64}"


def marker_text(name: str) -> str:
    """이력에 남는 파일명 표식 — 이번 턴의 실제 전달과 **별개**다."""
    return f"[첨부 파일: {name}]"


def _clean_name(raw: object, index: int) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise AttachmentError("invalid_attachment", f"attachments[{index}].name 이 필요하다")
    # 경로·제어문자를 제거한다 — 표식이 파일 시스템 경로를 흘리거나 로그를 깨지 않게.
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip()
    if not name:
        raise AttachmentError("invalid_attachment", f"attachments[{index}].name 이 비어 있다")
    return name[:_MAX_NAME_LENGTH]


def _decode_base64(raw: object, index: int) -> tuple[str, int]:
    if not isinstance(raw, str) or not raw:
        raise AttachmentError("invalid_attachment", f"attachments[{index}].data_base64 가 필요하다")
    payload = raw
    if payload.startswith("data:"):
        # data URL 을 통째로 보낸 경우도 받아 준다(헤더는 무시하고 바이트만 본다).
        _, _, payload = payload.partition(",")
    compact = "".join(payload.split())
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttachmentError(
            "invalid_attachment_encoding",
            f"attachments[{index}].data_base64 가 base64 가 아니다",
        ) from exc
    if not decoded:
        raise AttachmentError("invalid_attachment", f"attachments[{index}] 가 빈 파일이다")
    return compact, len(decoded)


def parse_attachments(raw: object) -> list[ImageAttachment]:
    """요청의 `attachments` 를 검증해 첨부 목록으로 만든다.

    위반은 **조용히 버리지 않고** `AttachmentError` 로 알린다 — 조용한 대체가 이
    결함(F03)의 본질이었으므로, 거부도 사용자가 볼 수 있어야 한다.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AttachmentError("invalid_attachments", "'attachments' 는 배열이어야 한다")
    items = cast(list[object], raw)
    if len(items) > MAX_ATTACHMENTS:
        raise AttachmentError(
            "too_many_attachments",
            f"첨부는 최대 {MAX_ATTACHMENTS}개까지 가능하다(요청 {len(items)}개)",
        )

    parsed: list[ImageAttachment] = []
    total = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AttachmentError("invalid_attachment", f"attachments[{index}] 는 객체여야 한다")
        item_map = cast(dict[str, object], item)
        name = _clean_name(item_map.get("name"), index)
        mime = item_map.get("mime_type") or item_map.get("mime")
        if not isinstance(mime, str) or not mime.strip():
            raise AttachmentError("invalid_attachment", f"attachments[{index}].mime_type 이 필요하다")
        mime_type = mime.strip().lower()
        if mime_type not in ALLOWED_IMAGE_MIME:
            raise AttachmentError(
                "unsupported_attachment_type",
                f"지원하지 않는 형식이다: {mime_type} (허용: {', '.join(ALLOWED_IMAGE_MIME)})",
            )
        data_base64, byte_length = _decode_base64(item_map.get("data_base64"), index)
        if byte_length > MAX_ATTACHMENT_BYTES:
            raise AttachmentError(
                "attachment_too_large",
                f"첨부가 너무 크다: {name} {byte_length}B (상한 {MAX_ATTACHMENT_BYTES}B)",
            )
        total += byte_length
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise AttachmentError(
                "attachments_too_large",
                f"첨부 합계가 너무 크다: {total}B (상한 {MAX_TOTAL_ATTACHMENT_BYTES}B)",
            )
        parsed.append(
            ImageAttachment(
                name=name,
                mime_type=mime_type,
                data_base64=data_base64,
                byte_length=byte_length,
            )
        )
    return parsed


# ── content / message 정규화 ─────────────────────────────────────────


def _is_image_part(part: object) -> bool:
    return isinstance(part, dict) and cast(dict[str, object], part).get("type") == "image_url"


def _image_url_of(part: object) -> str:
    if not isinstance(part, dict):
        return ""
    image = cast(dict[str, object], part).get("image_url")
    if isinstance(image, dict):
        url = cast(dict[str, object], image).get("url")
        return url if isinstance(url, str) else ""
    return image if isinstance(image, str) else ""


def split_data_url(url: str) -> tuple[str, str]:
    """`data:<mime>;base64,<data>` → (mime, base64). 해석할 수 없으면 빈 값."""
    if not url.startswith("data:"):
        return "", ""
    header, _, payload = url.partition(",")
    meta = header[len("data:") :]
    if ";base64" not in meta:
        return "", ""
    return meta.split(";", 1)[0].strip().lower(), payload


def flatten_content(content: object) -> str:
    """content 를 **텍스트만** 남긴다(파트 배열이면 text 파트를 이어 붙인다)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in cast(list[object], content):
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            part_map = cast(dict[str, object], part)
            if part_map.get("type") != "text":
                continue
            text = part_map.get("text")
            if isinstance(text, str):
                parts.append(text)
        return " ".join(parts)
    return ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]


def extract_images(message: dict[str, object]) -> list[tuple[str, str]]:
    """메시지에서 `(mime, base64)` 이미지 목록을 뽑는다.

    두 표현을 모두 받는다 — 내부 정규형(`images` + `image_mimes`)과 OpenAI 호환
    파트 배열(`content: [{type: image_url}]`). 어느 쪽도 **버리지 않는다**.
    """
    images = _string_list(message.get("images"))
    mimes = _string_list(message.get("image_mimes"))
    extracted: list[tuple[str, str]] = []
    for index, data in enumerate(images):
        mime = mimes[index] if index < len(mimes) else _DEFAULT_IMAGE_MIME
        extracted.append((mime.lower(), data))

    content = message.get("content")
    if isinstance(content, list):
        for part in cast(list[object], content):
            if not _is_image_part(part):
                continue
            mime, payload = split_data_url(_image_url_of(part))
            if payload:
                extracted.append((mime or _DEFAULT_IMAGE_MIME, payload))
    return extracted


def has_images(message: dict[str, object]) -> bool:
    """이 메시지가 이미지를 싣고 있는가(표현 형식과 무관)."""
    return bool(extract_images(message))


def normalize_message(message: dict[str, object]) -> dict[str, object]:
    """메시지를 내부 정규형으로 만든다: `content` 는 문자열, 이미지는 message-level.

    파트 배열로 들어온 이미지를 **끌어올린다** — 예전 `_prepare_stream_messages` 는
    여기서 텍스트만 남기고 이미지를 버렸다(F03 의 실제 형태).
    """
    images = extract_images(message)
    content = message.get("content", "")
    normalized: dict[str, object] = {
        key: value for key, value in message.items() if key not in ("images", "image_mimes")
    }
    if isinstance(content, list) and not images:
        # 이미지가 없는데 파트 배열이라면 **이미 블록 형식**이다(예: Anthropic cache_control).
        # 텍스트로 접으면 그 블록들이 사라진다 — 그대로 둔다.
        normalized["content"] = content
    else:
        normalized["content"] = flatten_content(content)
    if images:
        normalized["images"] = [data for _mime, data in images]
        normalized["image_mimes"] = [mime for mime, _data in images]
    return normalized


def attach_to_latest_user_turn(
    messages: list[dict[str, object]],
    attachments: list[ImageAttachment],
) -> list[dict[str, object]]:
    """가장 마지막 user 턴에 첨부를 실어 **새 목록**을 만든다(원본 불변).

    `content` 는 문자열로 두고 `images`/`image_mimes` 로 나른다 — 텍스트 전용 코드가
    깨지지 않게 하는 것이 이 표현의 목적이다. user 턴이 없으면 하나 덧붙인다.
    """
    if not attachments:
        return [dict(message) for message in messages]
    out: list[dict[str, object]] = [dict(message) for message in messages]
    target = -1
    for index in range(len(out) - 1, -1, -1):
        if out[index].get("role") == "user":
            target = index
            break
    if target < 0:
        out.append({"role": "user", "content": ""})
        target = len(out) - 1

    normalized = normalize_message(out[target])
    existing = extract_images(out[target])
    normalized["images"] = [data for _mime, data in existing] + [a.data_base64 for a in attachments]
    normalized["image_mimes"] = [mime for mime, _data in existing] + [a.mime_type for a in attachments]
    text = cast(str, normalized["content"])
    for attachment in attachments:
        marker = marker_text(attachment.name)
        if marker not in text:
            text = f"{text}\n{marker}" if text else marker
    normalized["content"] = text
    out[target] = normalized
    return out


# ── 표면별 변환 ─────────────────────────────────────────────────────


def to_openai_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """OpenAI 호환 표면 — 이미지를 `content` 파트 배열로 표현한다."""
    out: list[dict[str, object]] = []
    for message in messages:
        images = extract_images(message)
        entry = {key: value for key, value in message.items() if key not in ("images", "image_mimes")}
        content = message.get("content", "")
        text = flatten_content(content)
        if not images:
            # 이미지가 없으면 기존 표현을 유지한다(파트 배열이면 그대로 — 블록을 지우지 않는다).
            out.append({**entry, "content": content if isinstance(content, list) else text})
            continue
        parts: list[dict[str, object]] = []
        if text.strip():
            parts.append({"type": "text", "text": text})
        for mime, payload in images:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{payload}"},
                }
            )
        out.append({**entry, "content": parts})
    return out


def to_ollama_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Ollama 네이티브 표면 — `content`(텍스트) + `images`(base64 배열)."""
    out: list[dict[str, object]] = []
    for message in messages:
        entry = {key: value for key, value in message.items() if key not in ("images", "image_mimes")}
        entry["content"] = flatten_content(message.get("content", ""))
        images = [data for _mime, data in extract_images(message)]
        if images:
            entry["images"] = images
        out.append(entry)
    return out


def to_anthropic_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Anthropic 표면 — 텍스트 블록 + `source.base64` 이미지 블록."""
    out: list[dict[str, object]] = []
    for message in messages:
        images = extract_images(message)
        entry = {key: value for key, value in message.items() if key not in ("images", "image_mimes")}
        content = message.get("content", "")
        text = flatten_content(content)
        if not images:
            # 캐시 마커(`cache_control`) 같은 기존 블록은 **보존**한다.
            out.append({**entry, "content": content if isinstance(content, list) else text})
            continue
        blocks: list[dict[str, object]] = []
        if text.strip():
            blocks.append({"type": "text", "text": text})
        for mime, payload in images:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime or _DEFAULT_IMAGE_MIME,
                        "data": payload,
                    },
                }
            )
        out.append({**entry, "content": blocks})
    return out


def collect_images(messages: object) -> list[tuple[str, str]]:
    """여러 메시지에서 `(mime, base64)` 를 모은다(프롬프트 문자열 경로로 넘길 때 쓴다)."""
    collected: list[tuple[str, str]] = []
    if not isinstance(messages, list):
        return collected
    for message in cast(list[object], messages):
        if isinstance(message, dict):
            collected.extend(extract_images(cast(dict[str, object], message)))
    return collected


def prompt_message(prompt: str, raw_images: object) -> dict[str, object]:
    """프롬프트 문자열 경로용 user 메시지 — 이미지가 있으면 message-level 로 붙인다.

    에이전트 경로의 모델 입력은 "프롬프트 문자열"이다(압축·예산 게이트가 문자열을
    전제한다). 그래서 이미지는 프롬프트를 건드리지 않고 **옆 채널**로만 실린다.
    """
    message: dict[str, object] = {"role": "user", "content": prompt}
    pairs: list[tuple[str, str]] = []
    if isinstance(raw_images, list):
        for item in cast(list[object], raw_images):
            if not isinstance(item, dict):
                continue
            item_map = cast(dict[str, object], item)
            data = item_map.get("data_base64")
            mime = item_map.get("mime_type") or item_map.get("mime")
            if isinstance(data, str) and data:
                pairs.append(
                    (
                        (mime if isinstance(mime, str) and mime else _DEFAULT_IMAGE_MIME).lower(),
                        data,
                    )
                )
    if pairs:
        message["images"] = [data for _mime, data in pairs]
        message["image_mimes"] = [mime for mime, _data in pairs]
    return message


def adapter_messages(
    *,
    surface: str,
    prompt: object,
    raw_messages: object = None,
    system_prompt: str = "",
    images: object = None,
) -> list[dict[str, object]]:
    """provider 어댑터용 메시지 목록 — **표면별 변환까지 여기서 끝낸다**.

    어댑터마다 `raw_messages`/`prompt` 를 각자 풀어 쓰면 이미지를 조용히 버리는 자리가
    계속 생긴다(실측: 관리자 경로를 고쳐도 어댑터가 다시 납작하게 만들었다).
    그래서 어댑터는 이 함수 하나만 부른다.
    """
    source: list[dict[str, object]] = []
    if isinstance(raw_messages, list) and raw_messages:
        source = [cast(dict[str, object], m) for m in cast(list[object], raw_messages) if isinstance(m, dict)]
    elif isinstance(prompt, list):
        source = [cast(dict[str, object], m) for m in cast(list[object], prompt) if isinstance(m, dict)]
    else:
        source = [prompt_message(prompt if isinstance(prompt, str) else "", images)]

    messages: list[dict[str, object]] = [normalize_message(message) for message in source]
    if system_prompt:
        system_message: dict[str, object] = {"role": "system", "content": system_prompt}
        messages = [system_message, *messages]
    if surface == "ollama":
        return to_ollama_messages(messages)
    if surface == "anthropic":
        return to_anthropic_messages(messages)
    return to_openai_messages(messages)


def summarize(attachments: list[ImageAttachment]) -> list[dict[str, object]]:
    """증거·로그용 요약 — **바이트는 절대 넣지 않는다**."""
    return [
        {"name": attachment.name, "mime_type": attachment.mime_type, "bytes": attachment.byte_length}
        for attachment in attachments
    ]
