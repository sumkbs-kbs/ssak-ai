"""Deterministic cleanup for recurring local-model language contamination."""

from __future__ import annotations

from collections.abc import Iterator

from antigravity_k.engine.chat_stream_events import FinalChunk, ProgressChunk

_TECHNICAL_TERMS: tuple[tuple[str, str], ...] = (
    ("复杂度", "복잡도"),
    ("複雜度", "복잡도"),
    ("复杂", "복잡"),
    ("複雜", "복잡"),
    ("方法", "방법"),
    ("结果", "결과"),
    ("結果", "결과"),
)


def normalize_foreign_technical_terms(text: str) -> str:
    """Replace known CJK technical false friends with Korean equivalents."""
    normalized = text
    for source, target in _TECHNICAL_TERMS:
        normalized = normalized.replace(source, target)
    return normalized


def normalize_streaming_chunks(chunks: Iterator[str]) -> Iterator[str]:
    """Normalize terms without allowing a source term to split across chunks."""
    buffer = ""
    for chunk in chunks:
        if isinstance(chunk, ProgressChunk):
            yield chunk
            continue
        if isinstance(chunk, FinalChunk):
            if buffer:
                yield normalize_foreign_technical_terms(buffer)
                buffer = ""
            yield chunk
            continue
        buffer += chunk
        safe_end = len(buffer)
        for source, _target in _TECHNICAL_TERMS:
            for length in range(1, len(source)):
                if buffer.endswith(source[:length]):
                    safe_end = min(safe_end, len(buffer) - length)
        if safe_end <= 0:
            continue
        yield normalize_foreign_technical_terms(buffer[:safe_end])
        buffer = buffer[safe_end:]
    if buffer:
        yield normalize_foreign_technical_terms(buffer)
