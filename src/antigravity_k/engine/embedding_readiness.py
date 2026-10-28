"""Read-only readiness check for the local Ollama embedding model."""

from __future__ import annotations

from typing import Literal, TypedDict, cast

import httpx

from antigravity_k.engine.model_registry import ModelProfile, ModelRegistry
from antigravity_k.engine.provider_adapters.embedding_providers import (
    OllamaEmbeddingProtocolError,
    OllamaEmbeddingProvider,
    OllamaEmbeddingUnavailableError,
)

EmbeddingState = Literal[
    "ollama_unreachable",
    "model_missing",
    "embedding_failed",
    "dimension_mismatch",
    "model_present_unprobed",
    "ready",
]


class EmbeddingReadiness(TypedDict):
    state: EmbeddingState
    rag_ready: bool
    model: str
    message: str


def _result(state: EmbeddingState, model: str, message: str) -> EmbeddingReadiness:
    return {"state": state, "rag_ready": state == "ready", "model": model, "message": message}


def check_embedding_readiness(
    profile: ModelProfile,
    registry: ModelRegistry | None,
    *,
    probe: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> EmbeddingReadiness:
    """Classify Ollama/embedding readiness. Never downloads, installs or starts anything.

    Only ``GET /api/tags`` is used unless ``probe`` is True, which adds one real ``/api/embed`` call.
    RAG is reported ready only after a real embedding call succeeds.
    """
    wire_model = profile.repo or profile.name
    try:
        base = OllamaEmbeddingProvider.resolve_base_url(profile, registry)
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = client.get(base + "/api/tags")
        if response.status_code != 200:
            raise OllamaEmbeddingUnavailableError(f"HTTP {response.status_code}")
        body = cast(object, response.json())
    except (OllamaEmbeddingUnavailableError, httpx.HTTPError, ValueError):
        return _result(
            "ollama_unreachable", wire_model, "Ollama에 연결할 수 없습니다. Ollama 실행 여부와 주소 설정을 확인하세요."
        )
    models = cast(dict[str, object], body).get("models") if isinstance(body, dict) else None
    names: set[str] = set()
    for row in models if isinstance(models, list) else []:
        if isinstance(row, dict):
            for key in ("name", "model"):
                value = cast(dict[str, object], row).get(key)
                if isinstance(value, str):
                    names.add(value)
    if wire_model not in names:
        return _result(
            "model_missing",
            wire_model,
            f"임베딩 모델 '{wire_model}'이 Ollama에 없습니다. 직접 `ollama pull {wire_model}` 후 다시 확인하세요.",
        )
    if not probe:
        return _result(
            "model_present_unprobed", wire_model, "모델은 설치되어 있으나 임베딩 호출은 아직 검증되지 않았습니다."
        )
    try:
        _ = OllamaEmbeddingProvider(transport=transport).embed(profile, registry, "readiness probe", wire_model)
    except OllamaEmbeddingProtocolError as exc:
        if "dimension" in str(exc):
            return _result("dimension_mismatch", wire_model, f"임베딩 차원이 설정과 다릅니다: {exc}")
        return _result("embedding_failed", wire_model, f"임베딩 응답이 올바르지 않습니다: {exc}")
    except OllamaEmbeddingUnavailableError as exc:
        return _result("embedding_failed", wire_model, f"임베딩 호출 실패: {exc}")
    return _result("ready", wire_model, "임베딩이 정상 동작합니다.")
