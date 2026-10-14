"""Native provider adapters for embedding generation."""

from __future__ import annotations

import math
from typing import cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx
from httpx import Client as HttpxClient

from antigravity_k.engine.model_registry import ModelProfile, ModelRegistry


class OllamaEmbeddingUnavailableError(RuntimeError):
    """Ollama embedding request could not produce an HTTP 200 response."""


class OllamaEmbeddingProtocolError(RuntimeError):
    """Ollama returned a response that violates the embedding contract."""


class OllamaEmbeddingProvider:
    """One-shot synchronous adapter for Ollama's native ``/api/embed`` endpoint."""

    timeout_seconds = 55.0
    default_base_url = "http://localhost:11434"

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    @classmethod
    def resolve_base_url(cls, profile: ModelProfile, registry: ModelRegistry | None) -> str:
        base: object = profile.api_base
        if not isinstance(base, str) or not base.strip():
            provider_config = registry.get_provider_config("ollama") if registry else {}
            candidate = provider_config.get("base_url")
            base = candidate if isinstance(candidate, str) and candidate.strip() else cls.default_base_url
        if not isinstance(base, str) or not base.strip():
            raise OllamaEmbeddingUnavailableError("Ollama embedding base URL is unavailable")

        try:
            parsed = urlsplit(base.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError("invalid HTTP base URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("credentials are not supported in the Ollama base URL")
            _ = parsed.port
            path = parsed.path.rstrip("/")
            if path.endswith("/v1"):
                path = path[:-3]
            normalized = SplitResult(parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
            result = urlunsplit(normalized).rstrip("/")
        except (ValueError, UnicodeError) as exc:
            raise OllamaEmbeddingUnavailableError("Ollama embedding base URL is invalid") from exc
        return result

    def embed(
        self,
        profile: ModelProfile,
        registry: ModelRegistry | None,
        text: str | list[str],
        wire_model: str,
    ) -> list[list[float]]:
        inputs = [text] if isinstance(text, str) else list(text)
        url = self.resolve_base_url(profile, registry) + "/api/embed"
        payload = {"model": wire_model, "input": inputs, "truncate": False}
        try:
            with HttpxClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = client.post(url, json=payload)
        except (httpx.RequestError, httpx.InvalidURL) as exc:
            raise OllamaEmbeddingUnavailableError("Ollama embedding request failed") from exc

        if response.status_code != 200:
            raise OllamaEmbeddingUnavailableError(f"Ollama embedding returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise OllamaEmbeddingProtocolError("Ollama embedding response content type is invalid")
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise OllamaEmbeddingProtocolError("Ollama embedding response JSON is invalid") from exc
        if not isinstance(body, dict):
            raise OllamaEmbeddingProtocolError("Ollama embedding response must be a JSON object")
        response_body = cast(dict[str, object], body)
        if response_body.get("model") != wire_model:
            raise OllamaEmbeddingProtocolError("Ollama embedding response model does not match the request")
        rows = response_body.get("embeddings")
        if not isinstance(rows, list):
            raise OllamaEmbeddingProtocolError("Ollama embedding response vectors are invalid")
        if len(rows) != len(inputs):
            raise OllamaEmbeddingProtocolError("Ollama embedding response vector count is invalid")

        dimensions = profile.dimensions
        vectors: list[list[float]] = []
        actual_dimensions: int | None = None
        for row in rows:
            if not isinstance(row, list) or not row:
                raise OllamaEmbeddingProtocolError("Ollama embedding response vector is empty or invalid")
            if actual_dimensions is None:
                actual_dimensions = len(row)
            elif len(row) != actual_dimensions:
                raise OllamaEmbeddingProtocolError("Ollama embedding response dimensions are inconsistent")
            if dimensions > 0 and len(row) != dimensions:
                raise OllamaEmbeddingProtocolError("Ollama embedding response dimension does not match the model")
            vector: list[float] = []
            for value in row:
                if type(value) not in (int, float):
                    raise OllamaEmbeddingProtocolError("Ollama embedding response contains a non-number")
                try:
                    numeric = float(value)
                except (OverflowError, ValueError) as exc:
                    raise OllamaEmbeddingProtocolError("Ollama embedding response number is out of range") from exc
                if not math.isfinite(numeric):
                    raise OllamaEmbeddingProtocolError("Ollama embedding response contains a non-finite number")
                vector.append(numeric)
            norm = math.hypot(*vector)
            if not math.isfinite(norm) or norm <= 0:
                raise OllamaEmbeddingProtocolError("Ollama embedding response vector norm is invalid")
            vectors.append(vector)
        return vectors
