"""Zero-Waste Context Density Maximizer — Ruthless token compression.

First Principle: Delete and Simplify.
Every wasted decorative token (greetings, polite fillers, repetitive markdown banners)
dilutes the 27B model's KV-cache and degrades multi-turn instruction following.

This module strips zero-entropy noise and packs the prompt with pure code-density.
"""

import re
from dataclasses import dataclass
from typing import Final

_FILLER_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(
        r"(?i)^(?:hello|hi|sure|certainly|of course|i would be happy to help|알겠습니다|확인했습니다|도와드리겠습니다)[,!.]?\s*",
        re.MULTILINE,
    ),
    re.compile(r"(?i)\b(?:as an ai language model|as an ai assistant|ai 모델로서)\b", re.IGNORECASE),
    re.compile(r"<!--.*?-->", re.DOTALL),  # Remove internal html comments
    re.compile(r"\n{3,}", re.MULTILINE),  # Compress excessive newlines
]


@dataclass(frozen=True)
class CompressedPrompt:
    """Outcome of token density maximization."""

    original_length: int
    compressed_length: int
    saved_chars: int
    text: str


class ZeroWasteCompressor:
    """Strips conversational boilerplate and maximizes code entropy in prompts."""

    @staticmethod
    def compress(prompt_text: str) -> CompressedPrompt:
        """Strip filler patterns and compress context while preserving all technical substance.

        Args:
            prompt_text: Raw system or user prompt.

        Returns:
            CompressedPrompt containing trimmed, high-density prompt text.
        """
        orig_len = len(prompt_text)
        cleaned = prompt_text

        for pattern in _FILLER_PATTERNS:
            cleaned = pattern.sub("", cleaned)

        # Remove redundant whitespace at line ends
        lines = [line.rstrip() for line in cleaned.splitlines() if line.strip() != ""]
        cleaned_text = "\n".join(lines)

        return CompressedPrompt(
            original_length=orig_len,
            compressed_length=len(cleaned_text),
            saved_chars=orig_len - len(cleaned_text),
            text=cleaned_text,
        )
