"""Development shims for non-MLX (Windows/Linux) environments.

These dummy objects let ``ModelManager`` represent an Ollama-backed model
without a real local tokenizer. They are referenced by **class name string**
in ``provider_adapters/inference_providers.py`` (via ``type(loaded.model).__name__``),
so the class names ``_OllamaModel`` and ``_OllamaTokenizer`` must remain stable.

Extracted from ``model_manager.py`` to reduce its size.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping, Sequence
from typing import ClassVar, override

logger = logging.getLogger("antigravity_k.model_manager")


class _OllamaModel:
    """Windows에서 Ollama API 연동을 위한 더미 모델 객체."""

    def __init__(self, name: str) -> None:
        self.name: str = name

    @override
    def __repr__(self) -> str:
        return f"OllamaModel({self.name})"


class _OllamaTokenizer:
    """Ollama API 환경에서 토큰 길이 추정용 경량 토크나이저.

    I-2 개선: CJK(한국어/일본어/중국어) 문자를 개별 카운트하여
    서브워드 토크나이저(BPE/SentencePiece) 동작을 근사합니다.
    """

    eos_token_id: int = 100000
    chat_template: str | None = None
    bos_token: str = ""
    eos_token: str = ""

    # CJK Unified Ideographs 및 한글 음절 범위
    _CJK_RANGES: ClassVar[tuple[tuple[int, int], ...]] = (
        (0x4E00, 0x9FFF),  # CJK Unified Ideographs
        (0x3400, 0x4DBF),  # CJK Extension A
        (0xAC00, 0xD7AF),  # Hangul Syllables (한글)
        (0x3040, 0x309F),  # Hiragana
        (0x30A0, 0x30FF),  # Katakana
    )

    def __init__(self, name: str) -> None:
        self.name: str = name

    @staticmethod
    def _is_cjk(char: str) -> bool:
        cp = ord(char)
        return any(lo <= cp <= hi for lo, hi in _OllamaTokenizer._CJK_RANGES)

    def encode(self, text: object, **_: object) -> list[int]:
        """토큰 수 추정: CJK 문자 개별 1.5토큰 + 라틴 단어 1.3토큰."""
        if not isinstance(text, str):
            try:
                text = json.dumps(text, ensure_ascii=False)
            except Exception:
                logger.exception("Unhandled exception")
                text = str(text)

        cjk_count = 0
        latin_parts: list[str] = []
        current_word: list[str] = []
        for ch in text:
            if self._is_cjk(ch):
                cjk_count += 1
                if current_word:
                    latin_parts.append("".join(current_word))
                    current_word = []
            elif ch.isspace():
                if current_word:
                    latin_parts.append("".join(current_word))
                    current_word = []
            else:
                current_word.append(ch)

        if current_word:
            latin_parts.append("".join(current_word))

        # CJK: 한 글자당 ~1.2 서브워드 토큰 (Qwen 계열 실측 근사 —
        # TokenEstimator 단일 캘리브레이션과 동일 계수)
        # Latin: 한 단어당 ~1.3 서브워드 토큰
        estimated = math.ceil(cjk_count * 1.2) + math.ceil(len(latin_parts) * 1.3)
        return list(range(max(1, estimated)))

    def decode(self, _tokens: list[int], **_: object) -> str:
        return "[Decoded by OllamaTokenizer]"

    def get_vocab(self) -> dict[str, int]:
        return {}

    def apply_chat_template(
        self,
        messages: Sequence[Mapping[str, object]],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
    ) -> str:
        # OpenAI API나 로컬 API는 직접 messages 배열을 받을 수 있지만
        # BaseAgent가 프롬프트 구성을 위해 이 함수를 호출하므로 단순 텍스트로 합쳐서 반환
        _ = (tokenize, add_generation_prompt)
        text = ""
        for msg in messages:
            raw_role = msg.get("role", "user")
            role = raw_role if isinstance(raw_role, str) else str(raw_role)
            raw_content = msg.get("content", "")
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
            text += f"{role}: {content}\n"
        return text


OLLAMA_MODEL_CLASS_NAME: str = _OllamaModel.__name__
