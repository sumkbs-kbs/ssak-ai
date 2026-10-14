"""Base Adapter module."""

from abc import ABC, abstractmethod


class BaseProviderAdapter(ABC):
    """Ssak-Ai 코어(Anthropic 규격)와 타사 모델 API 간의.

    요청/응답을 투명하게 번역해주는 어댑터의 기본 인터페이스입니다.
    (Inspired by free-claude-code)
    """

    @abstractmethod
    def translate_request(self, anthropic_payload: dict[str, object]) -> dict[str, object]:
        """Anthropic Messages API 형식의 페이로드를 받아.

        대상 Provider의 형식(예: OpenAI Chat Completions)으로 변환합니다.
        """
        pass

    @abstractmethod
    def translate_response(self, provider_response: dict[str, object]) -> dict[str, object]:
        """대상 Provider의 응답 형식을 받아.

        Anthropic Messages API 형식으로 재변환하여 코어로 반환합니다.
        """
        pass

    @abstractmethod
    def translate_stream(self, provider_chunk: dict[str, object]) -> dict[str, object]:
        """Streaming 모드일 때 SSE Chunk를 변환합니다."""
        pass
