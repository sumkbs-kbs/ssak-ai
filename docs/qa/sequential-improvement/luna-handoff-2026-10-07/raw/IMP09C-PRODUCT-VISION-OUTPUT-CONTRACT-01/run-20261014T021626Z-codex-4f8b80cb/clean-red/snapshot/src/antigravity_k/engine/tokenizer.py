"""Ssak-Ai: 토큰 추정기 (TokenEstimator).

=============================================
시스템 전체에서 단 하나의 토큰 추정 공식만 사용하도록 통일합니다.

이전 문제:
  - context_compressor.py: max(단어*1.3, len//4) — 한국어를 ~4-5배 과소평가
  - tokenizer.py (구버전): bytes//3 + CJK글자수 — 한국어를 ~1.5-2배 과대평가
  - tool_loop.py / chat.py: len(text)//4 — 한국어 ~4-6배 과소평가
  → 세 추정치가 서로 달라 (동일 한국어 샘플에서 최대 6.2배 편차)
    컨텍스트 예산/압축 트리거/비용 집계가 경로마다 어긋났다.

설계 원칙:
  - 한국어/영어 혼합 텍스트에 대한 단일 캘리브레이션 공식 (Qwen 계열 실측 근사)
  - 메시지 리스트 단위 추정 지원
  - 성능을 위한 캐싱 (메시지별 _tokens 필드)
"""

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import ClassVar

# 한글, 한자, 일본어(히라가나/가타카나) 정규식
CJK_PATTERN = re.compile(r"[\uac00-\ud7a3\u4e00-\u9fff\u3040-\u30ff]")


class TokenEstimator:
    """토큰 수 추정 — 시스템 전체에서 이 클래스만 사용할 것.

    추정 공식 (Qwen BPE/SentencePiece 실측 근사):
      - CJK 문자(한글/한자/가나): 글자당 ~1.2 토큰
      - 그 외(라틴/숫자/기호/공백): 글자당 ~0.25 토큰 (≈ 4글자/토큰)

    근거:
      - 한국어 서브워드 토큰화는 통상 글자당 1.0~1.5 토큰
      - 영어는 ~4글자/토큰; 과소 추정은 컨텍스트 초과(Ollama 좌측 잘림)로
        이어지므로 약간 보수적으로 잡는다
    """

    CJK_TOKENS_PER_CHAR: ClassVar[float] = 1.2
    OTHER_TOKENS_PER_CHAR: ClassVar[float] = 0.25

    @staticmethod
    def estimate_text(text: str) -> int:
        """단일 텍스트의 토큰 수를 추정합니다."""
        if not text:
            return 0
        cjk_count = len(CJK_PATTERN.findall(text))
        other_count = len(text) - cjk_count
        estimated = cjk_count * TokenEstimator.CJK_TOKENS_PER_CHAR + other_count * TokenEstimator.OTHER_TOKENS_PER_CHAR
        # 짧은 응답도 실제로는 1토큰 이상 소비하므로 하한을 둔다
        return max(1, int(estimated + 0.5))

    @staticmethod
    def estimate_messages(messages: Sequence[Mapping[str, object]], use_cache: bool = True) -> int:
        """메시지 리스트의 총 토큰 수를 추정합니다.

        Args:
            messages: [{"role": "...", "content": "..."}] 리스트
            use_cache: True이면 메시지별 _tokens 필드에 캐시 (반복 호출 시 성능 향상)

        """
        total = 0
        for msg in messages:
            if use_cache and "_tokens" in msg:
                _t = msg["_tokens"]
                if isinstance(_t, (int, float)):
                    total += int(_t)
            else:
                raw_content = msg.get("content", "")
                content = raw_content if isinstance(raw_content, str) else str(raw_content)
                tokens = TokenEstimator.estimate_text(content)
                if use_cache and isinstance(msg, MutableMapping):
                    msg["_tokens"] = tokens
                total += tokens
        return total

    @staticmethod
    def estimate_messages_by_role(messages: list[dict[str, str]]) -> dict[str, int]:
        """역할별 토큰 사용량을 분석합니다."""
        by_role: dict[str, int] = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            tokens = TokenEstimator.estimate_text(msg.get("content", ""))
            by_role[role] = by_role.get(role, 0) + tokens
        return by_role
