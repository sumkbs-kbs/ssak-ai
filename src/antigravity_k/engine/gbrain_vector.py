"""r30 P1: gbrain vector memory through the approved embedding binding only.

The Chroma collection is opened with ``embedding_function=None`` and every write/query embeds through
the configured :class:`ProjectEmbeddingBinding` (local Ollama nomic-embed-text). Chroma's implicit
default ONNX function is never reached. The collection records the binding identity; a collection
written by another identity (or by the old implicit default) is never reused or modified.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol, cast

from antigravity_k.engine.project_embedding_binding import (
    DIMENSIONS_METADATA_KEY,
    IDENTITY_METADATA_KEY,
    ProjectEmbeddingBinding,
    ProjectEmbeddingBindingError,
)

logger = logging.getLogger(__name__)

#: New name: the pre-r29 ``gbrain_nodes`` collection was created with Chroma's default ONNX
#: embedding function and is left untouched (no silent reuse with a different vector space).
BOUND_COLLECTION_NAME = "gbrain_nodes_bound"

ChromaValue = str | int | float | bool


class _RawCollection(Protocol):
    @property
    def metadata(self) -> Mapping[str, object] | None: ...

    def count(self) -> int: ...

    def upsert(self, **kwargs: object) -> object: ...

    def query(self, **kwargs: object) -> dict[str, object]: ...

    def get(self, **kwargs: object) -> dict[str, object]: ...

    def delete(self, **kwargs: object) -> object: ...

    def modify(self, *, metadata: dict[str, ChromaValue]) -> object: ...


class _RawClient(Protocol):
    def get_or_create_collection(self, **kwargs: object) -> _RawCollection: ...


class BoundGBrainCollection:
    """Chroma collection facade with the gbrain collection surface; embeddings come from the binding."""

    def __init__(self, raw: _RawCollection, binding: ProjectEmbeddingBinding) -> None:
        self._raw = raw
        self._binding = binding

    @classmethod
    def open(cls, client: object, binding: ProjectEmbeddingBinding) -> "BoundGBrainCollection":
        raw = cast(_RawClient, client).get_or_create_collection(
            name=BOUND_COLLECTION_NAME,
            embedding_function=None,
            metadata={IDENTITY_METADATA_KEY: binding.identity.serialized()},
        )
        metadata = dict(raw.metadata or {})
        if metadata.get(IDENTITY_METADATA_KEY) != binding.identity.serialized():
            raise ProjectEmbeddingBindingError("gbrain collection was written by another embedding identity")
        return cls(raw, binding)

    def _observed_dimensions(self) -> int:
        value = dict(self._raw.metadata or {}).get(DIMENSIONS_METADATA_KEY)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def count(self) -> int:
        return self._raw.count()

    def upsert(self, *, ids: list[str], documents: list[str], metadatas: list[dict[str, ChromaValue]]) -> object:
        observed = self._observed_dimensions()
        # Embed first: a failed embedding call writes nothing (caller keeps graph/vector atomic).
        vectors = self._binding.embed(list(documents), observed_dimensions=observed)
        result = self._raw.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
        if not observed and vectors:
            metadata = cast(dict[str, ChromaValue], dict(self._raw.metadata or {}))
            metadata[DIMENSIONS_METADATA_KEY] = len(vectors[0])
            _ = self._raw.modify(metadata=metadata)
        return result

    def query(self, *, query_texts: list[str], n_results: int, where: dict[str, str] | None) -> dict[str, object]:
        vectors = self._binding.embed(list(query_texts), query=True, observed_dimensions=self._observed_dimensions())
        return self._raw.query(query_embeddings=vectors, n_results=n_results, where=where)

    def get(self, *, ids: list[str] | None = None, include: list[str] | None = None) -> dict[str, object]:
        return self._raw.get(ids=ids, include=include or ["documents", "metadatas"])

    def delete(self, *, ids: list[str]) -> object:
        return self._raw.delete(ids=ids)
