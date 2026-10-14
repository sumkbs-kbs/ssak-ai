from __future__ import annotations

import re

import httpx

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024


class ReaderRejected(ValueError):
    pass


def is_reader_challenge(text: str) -> bool:
    """Require a challenge title and a provider-specific marker, not keywords alone."""
    prefix = text[:4096].casefold()
    html_title = re.search(r"<title\b[^>]*>\s*(.*?)\s*</title\s*>", prefix, re.DOTALL)
    jina_title = re.search(r"^title:\s*(.*?)\s*$", prefix, re.MULTILINE)
    title = html_title.group(1) if html_title else jina_title.group(1) if jina_title else ""
    challenge_title = title.strip().rstrip(". !") in {
        "just a moment",
        "attention required",
        "attention required | cloudflare",
        "security verification",
    }
    if not challenge_title:
        return False
    body = text.casefold()
    return (
        "/cdn-cgi/challenge-platform/" in body
        or "cloudflare ray id" in body
        or bool(re.search(r"^warning:.*(?:requiring captcha|verify you are human)", body, re.MULTILINE))
    )


def _check_media_type(response: httpx.Response) -> None:
    media_type = response.headers.get("content-type", "").partition(";")[0].strip().casefold()
    if media_type and not (media_type.startswith("text/") or media_type == "application/xhtml+xml"):
        raise ReaderRejected("unsupported_content_type")


def _decode_body(response: httpx.Response, body: bytearray) -> str:
    try:
        text = body.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    if is_reader_challenge(text):
        raise ReaderRejected("challenge_page")
    return text


def read_text_response(response: httpx.Response) -> str:
    """Limit decoded bytes even when Content-Length is absent or forged."""
    _check_media_type(response)
    body = bytearray()
    for chunk in response.iter_bytes(chunk_size=_CHUNK_BYTES):
        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
            raise ReaderRejected("response_too_large")
        body.extend(chunk)
    return _decode_body(response, body)


async def read_text_response_async(response: httpx.Response) -> str:
    _check_media_type(response)
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=_CHUNK_BYTES):
        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
            raise ReaderRejected("response_too_large")
        body.extend(chunk)
    return _decode_body(response, body)
