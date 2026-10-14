"""Embedding generation (sentence-transformers with hash fallback)."""

import hashlib
import logging
import math
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.provider_adapters.embedding_providers import (
    OllamaEmbeddingProtocolError,
    OllamaEmbeddingProvider,
    OllamaEmbeddingUnavailableError,
)

logger = logging.getLogger("antigravity_k.engine.embeddings")


@runtime_checkable
class _EmbeddingModel(Protocol):
    def encode(self, sentences: list[str], *, convert_to_numpy: bool) -> Sequence[Sequence[float]]: ...


@runtime_checkable
class _EmbeddingFactory(Protocol):
    def __call__(self, model_name: str) -> _EmbeddingModel: ...


class EmbeddingProviderInvalidResponseError(RuntimeError):
    """Selected embedding provider returned an invalid successful response."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__("Embedding provider returned an invalid response.")


class EmbeddingModelUnavailableError(RuntimeError):
    """Requested embedding model could not be loaded without a fallback."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(f"Embedding model '{model_name}' could not be loaded.")


class EmbeddingEngine:
    """Generates vectors through a registered provider or local fallback."""

    fallback_dimensions: Final[int] = 1536

    def __init__(
        self,
        *,
        registry: ModelRegistry | None = None,
        ollama_provider: OllamaEmbeddingProvider | None = None,
    ) -> None:
        """Initialize the embedding engine with optional model/provider routing."""
        self.registry = registry
        self.ollama_provider = ollama_provider
        self.current_model: str | None = None
        self.model: _EmbeddingModel | None = None
        self.tokenizer: None = None

    def initialize(self) -> None:
        """Initialize the engine. Prepares the model for embedding."""
        pass

    def load_model(self, model_name: str) -> None:
        """Load an embedding model via sentence-transformers."""
        # Use a sensible cross-platform default if not provided
        target_model = model_name if model_name else "all-MiniLM-L6-v2"

        if self.current_model == target_model and self.model is not None:
            return

        if target_model.startswith(("test-", "mock-", "dummy-")):
            logger.info("Using local fallback embedding model for test target: %s", target_model)
            self.model = None
            self.current_model = target_model
            return

        logger.info("Loading embedding model: %s", target_model)
        try:
            from sentence_transformers import SentenceTransformer

            factory = SentenceTransformer
            if not isinstance(factory, _EmbeddingFactory):
                msg = "sentence_transformers.SentenceTransformer has an unsupported interface"
                raise ImportError(msg)

            self.model = factory(target_model)
            self.current_model = target_model
            logger.info("Embedding model loaded successfully.")
        except ImportError:
            logger.error(
                "sentence-transformers is not installed. Falling back to dummy embeddings.",
            )
            self.model = None
            self.current_model = target_model
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional embedding provider fallback
            logger.exception(
                "Embedding model '%s' could not be loaded. Falling back to local embeddings.", target_model
            )
            self.model = None
            self.current_model = target_model

    def embed(self, text: str | list[str], model_name: str, *, allow_fallback: bool = True) -> list[list[float]]:
        """Generate embeddings, optionally requiring the requested model to load."""
        profile = self.registry.get_model(model_name) if self.registry is not None else None
        roles = {role.strip().casefold() for role in profile.supported_roles if role.strip()} if profile else set()
        if profile is not None and profile.provider.casefold() == "ollama" and "embedding" in roles:
            wire_model = profile.repo or profile.name
            provider = self.ollama_provider or OllamaEmbeddingProvider()
            try:
                return provider.embed(profile, self.registry, text, wire_model)
            except OllamaEmbeddingUnavailableError as exc:
                raise EmbeddingModelUnavailableError(model_name) from exc
            except OllamaEmbeddingProtocolError as exc:
                raise EmbeddingProviderInvalidResponseError(model_name) from exc

        self.load_model(model_name)
        if self.model is None and not allow_fallback:
            raise EmbeddingModelUnavailableError(model_name)

        if isinstance(text, str):
            text = [text]

        if self.model is not None:
            logger.debug(
                "Generating embeddings for %s items using %s",
                len(text),
                self.current_model,
            )
            embeddings: Sequence[Sequence[float]] = self.model.encode(text, convert_to_numpy=True)
            return [[float(value) for value in row] for row in embeddings]
        else:
            logger.warning("Using local fallback embeddings because model is not loaded.")
            return [self._fallback_embedding(item) for item in text]

    def _fallback_embedding(self, text: str) -> list[float]:
        """Deterministic local embedding used when sentence-transformers is unavailable."""
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        chunks: list[float] = []
        counter = 0
        while len(chunks) < self.fallback_dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            chunks.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        vec = chunks[: self.fallback_dimensions]
        norm = math.sqrt(sum(value * value for value in vec))
        if norm:
            return [value / norm for value in vec]
        return vec


# Singleton instance
embedding_engine = EmbeddingEngine()


def get_embedding_engine() -> EmbeddingEngine:
    """Retrieve embedding engine.

    Returns:
        EmbeddingEngine: The embeddingengine result.

    """
    return embedding_engine
