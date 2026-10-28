"""Native provider adapters for embedding generation."""

from __future__ import annotations

import math
import os
from typing import cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx
from httpx import Client as HttpxClient

from antigravity_k.engine.model_registry import ModelProfile, ModelRegistry


class OllamaEmbeddingUnavailableError(RuntimeError):
    """Ollama embedding request could not produce an HTTP 200 response."""


class OllamaEmbeddingProtocolError(RuntimeError):
    """Ollama returned a response that violates the embedding contract."""


REQUEST_LIMIT_ENV = "AGK_EMBEDDING_REQUEST_LIMIT"


class OllamaEmbeddingProvider:
    """One-shot synchronous adapter for Ollama's native ``/api/embed`` endpoint.

    ``AGK_EMBEDDING_REQUEST_LIMIT`` (optional, test/scoped runs) caps the number of
    ``/api/embed`` requests this process may send; the cap is checked before sending.
    """

    requests_sent: int = 0

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

    @staticmethod
    def _authentication_headers(profile: ModelProfile, registry: ModelRegistry | None) -> dict[str, str]:
        key_env = profile.api_key_env.strip()
        if not key_env and not profile.api_base.strip() and registry is not None:
            configured_key = registry.get_provider_config("ollama").get("api_key_env")
            key_env = configured_key.strip() if isinstance(configured_key, str) else ""
        # An endpoint override must not inherit another endpoint's provider key.
        # Unconfigured legacy requests also keep omitting implicit global keys.
        api_key = os.environ.get(key_env, "") if key_env else ""
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def embed(
        self,
        profile: ModelProfile,
        registry: ModelRegistry | None,
        text: str | list[str],
        wire_model: str,
    ) -> list[list[float]]:
        inputs = [text] if isinstance(text, str) else list(text)
        url = self.resolve_base_url(profile, registry) + "/api/embed"
        limit = os.environ.get(REQUEST_LIMIT_ENV, "").strip()
        if limit and OllamaEmbeddingProvider.requests_sent >= int(limit):
            raise OllamaEmbeddingUnavailableError("Embedding request limit reached; no request sent")
        import antigravity_k.engine.call_ledger as call_ledger
        import antigravity_k.engine.llm_input_audit as llm_input_audit
        from antigravity_k.engine import model_allowlist

        # r34: embedding sends bypass llm_call_budget.charge(); gate the wire model here too.
        if not model_allowlist.embed_model_allowed(wire_model):
            raise OllamaEmbeddingUnavailableError("embedding model not allowlisted; no request sent")

        try:
            ledger_n = call_ledger.reserve("embed")
        except call_ledger.CallLedgerError as exc:
            raise OllamaEmbeddingUnavailableError(f"{exc}; no request sent") from exc
        OllamaEmbeddingProvider.requests_sent += 1
        llm_input_audit.audit_embed(inputs=len(inputs), ledger_cumulative=ledger_n, model=wire_model)
        payload = {"model": wire_model, "input": inputs, "truncate": False}
        try:
            with HttpxClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                call_ledger.mark("embed", ledger_n, "dispatched")
                response = client.post(url, json=payload, headers=self._authentication_headers(profile, registry))
        except (httpx.RequestError, httpx.InvalidURL) as exc:
            call_ledger.mark(
                "embed",
                ledger_n,
                "failed" if isinstance(exc, (httpx.ConnectError, httpx.InvalidURL)) else "aborted_unknown",
            )
            raise OllamaEmbeddingUnavailableError("Ollama embedding request failed") from exc
        call_ledger.mark("embed", ledger_n, "succeeded" if response.status_code == 200 else "failed")

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
