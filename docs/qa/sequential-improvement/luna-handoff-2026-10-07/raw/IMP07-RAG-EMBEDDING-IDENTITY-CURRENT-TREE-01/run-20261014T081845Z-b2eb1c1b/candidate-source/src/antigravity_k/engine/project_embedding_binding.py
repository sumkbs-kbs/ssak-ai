"""Explicit configured embedding identity for a project vector collection."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import asdict, dataclass, field

from antigravity_k.engine.embeddings import EmbeddingEngine
from antigravity_k.engine.provider_adapters.embedding_providers import OllamaEmbeddingProvider

IDENTITY_METADATA_KEY = "ssak_embedding_identity"
DIMENSIONS_METADATA_KEY = "ssak_embedding_observed_dimensions"


class ProjectEmbeddingBindingError(ValueError):
    """The requested embedding identity or vectors cannot safely use this index."""


@dataclass(frozen=True, slots=True)
class ConfiguredEmbeddingIdentity:
    version: int
    provider: str
    profile_name: str
    wire_model: str
    endpoint: str
    configured_dimensions: int
    document_prefix: str
    query_prefix: str
    weight_revision: None = None
    weight_revision_status: str = "UNVERIFIED"

    def serialized(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ProjectEmbeddingBinding:
    engine: EmbeddingEngine
    model_name: str
    document_prefix: str = ""
    query_prefix: str = ""
    identity: ConfiguredEmbeddingIdentity = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", self._configured_identity())

    def _configured_identity(self) -> ConfiguredEmbeddingIdentity:
        registry = self.engine.registry
        profile = registry.get_model(self.model_name) if registry is not None else None
        if profile is None or profile.provider.casefold() != "ollama":
            raise ProjectEmbeddingBindingError("A registered Ollama embedding profile is required.")
        if "embedding" not in {role.strip().casefold() for role in profile.supported_roles}:
            raise ProjectEmbeddingBindingError("The configured profile does not support embeddings.")
        if type(profile.dimensions) is not int or profile.dimensions < 0:
            raise ProjectEmbeddingBindingError("Configured embedding dimensions must be a non-negative integer.")
        return ConfiguredEmbeddingIdentity(
            version=1,
            provider="ollama",
            profile_name=profile.name,
            wire_model=profile.repo or profile.name,
            endpoint=OllamaEmbeddingProvider.resolve_base_url(profile, registry),
            configured_dimensions=profile.dimensions,
            document_prefix=self.document_prefix,
            query_prefix=self.query_prefix,
        )

    def revalidate(self) -> None:
        if self._configured_identity() != self.identity:
            raise ProjectEmbeddingBindingError(
                "The configured embedding identity changed; reopen with the original binding."
            )

    def embed(self, texts: list[str], *, query: bool = False, observed_dimensions: int = 0) -> list[list[float]]:
        self.revalidate()
        prefix = self.query_prefix if query else self.document_prefix
        raw = self.engine.embed([prefix + text for text in texts], self.model_name, allow_fallback=False)
        self.revalidate()
        return self.validate_vectors(raw, len(texts), observed_dimensions)

    def validate_vectors(self, raw: object, count: int, observed_dimensions: int) -> list[list[float]]:
        if not isinstance(raw, list) or len(raw) != count:
            raise ProjectEmbeddingBindingError("Embedding vector count does not match the input.")
        vectors: list[list[float]] = []
        expected = self.identity.configured_dimensions or observed_dimensions
        for row in raw:
            if not isinstance(row, list) or not row:
                raise ProjectEmbeddingBindingError("Embedding vectors must be non-empty numeric rows.")
            if expected and len(row) != expected:
                raise ProjectEmbeddingBindingError("Embedding dimensions do not match the collection.")
            expected = len(row)
            if observed_dimensions and expected != observed_dimensions:
                raise ProjectEmbeddingBindingError("Embedding dimensions changed for this collection.")
            vector: list[float] = []
            for value in row:
                if type(value) not in (int, float):
                    raise ProjectEmbeddingBindingError("Embedding values must be numeric and not boolean.")
                try:
                    number = float(value)
                except (OverflowError, ValueError) as exc:
                    raise ProjectEmbeddingBindingError("Embedding value is out of range.") from exc
                if not math.isfinite(number) or abs(number) > 3.4028234663852886e38:
                    raise ProjectEmbeddingBindingError("Embedding value is not a finite Chroma float32 value.")
                vector.append(struct.unpack("f", struct.pack("f", number))[0])
            norm = math.hypot(*vector)
            if not math.isfinite(norm) or norm <= 0:
                raise ProjectEmbeddingBindingError("Embedding vector norm must be positive and finite.")
            vectors.append(vector)
        return vectors
