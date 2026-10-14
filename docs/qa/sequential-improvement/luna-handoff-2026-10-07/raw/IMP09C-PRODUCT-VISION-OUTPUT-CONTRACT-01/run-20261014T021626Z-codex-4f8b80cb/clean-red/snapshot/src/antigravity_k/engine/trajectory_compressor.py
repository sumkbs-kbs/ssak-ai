"""Trajectory Compressor module."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from antigravity_k.engine.tool_evidence_compactor import compact_structured_tool_response

logger = logging.getLogger(__name__)

Message = dict[str, object]


@dataclass
class CompressionResult:
    """Result of compressing an agent trajectory (ratio, summary, retained steps)."""

    compressed_messages: list[Message]
    user_message: str = ""


class TrajectoryCompressor:
    """Compress long chat trajectories into a compact system summary."""

    def __init__(
        self,
        summarize_fn: Callable[[str], str] | None = None,
        max_messages: int = 40,
        max_chars: int = 80_000,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize the TrajectoryCompressor.

        Args:
            summarize_fn (Callable[[str], str] | None): Callable[[str], str] | None summarize fn.
            max_messages (int): int max messages.
            max_chars (int): int max chars (영어 중심 대비 폴백 기준).
            max_tokens (int | None): 토큰 기반 트리거 상한. chars*4 가정은 한국어를
                ~5배 과대 허용하므로 단일 추정기(CJK 인식) 기준을 함께 적용한다.

        """
        self.summarize_fn: Callable[[str], str] | None = summarize_fn
        self.max_messages: int = max_messages
        self.max_chars: int = max_chars
        self.max_tokens: int | None = max_tokens

    def should_compress(self, messages: list[Message]) -> bool:
        """Determine whether to compress.

        Args:
            messages (list[dict]): list[dict] messages.

        Returns:
            bool: The bool result.

        """
        if len(messages) > self.max_messages:
            return True
        total_chars = sum(len(str(message.get("content", ""))) for message in messages)
        if total_chars > self.max_chars:
            return True
        if self.max_tokens is not None:
            from antigravity_k.engine.tokenizer import TokenEstimator

            if TokenEstimator.estimate_messages(messages, use_cache=False) > self.max_tokens:
                return True
        return False

    def compress(self, messages: list[Message]) -> CompressionResult:
        """Compress.

        Args:
            messages (list[dict]): list[dict] messages.

        Returns:
            CompressionResult: The compressionresult result.

        """
        if not messages:
            return CompressionResult(compressed_messages=[])

        tail_start = max(1, len(messages) - 10)
        head = messages[:1]
        tail = messages[tail_start:]
        middle = messages[1:tail_start]
        summary = self._summarize(middle)

        compressed = list(head)
        if summary:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[Compressed conversation trajectory]\n{summary}",
                },
            )
        compressed.extend(tail)
        return CompressionResult(
            compressed_messages=compressed,
            user_message=("🧭 대화 이력이 길어 핵심 궤적을 압축했습니다." if middle else ""),
        )

    def _summarize(self, messages: list[Message]) -> str:
        if not messages:
            return ""

        raw = "\n".join(f"{message.get('role', 'unknown')}: {message.get('content', '')}" for message in messages)
        preserved_evidence = [
            compacted
            for message in messages
            if (compacted := compact_structured_tool_response(str(message.get("content", "")))) is not None
        ][-5:]
        if self.summarize_fn:
            try:
                summary = self.summarize_fn(raw)
                return "\n".join([summary, *preserved_evidence])
            except Exception:
                logger.exception("Unhandled exception")
        return "\n".join([raw[:4000], *preserved_evidence])
