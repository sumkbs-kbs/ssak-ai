"""Explicit configured embedding identity for a project vector collection."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import asdict, dataclass, field

from antigravity_k.engine.embeddings import EmbeddingEngine
from antigravity_k.engine.model_registry import ModelRegistry
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


RAG_EMBEDDING_ENV = "AGK_RAG_EMBEDDING"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


RAG_ALLOWED_ROOT_ENV = "AGK_RAG_ALLOWED_ROOT"


PROJECT_RAG_ENABLED_ENV = "AGK_PROJECT_RAG_ENABLED"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def project_rag_policy() -> tuple[str, str]:
    """Shared project-RAG search policy: ``("legacy"|"disabled"|"enabled", reason)``.

    Unset keeps the dev behavior (legacy fallback). An explicit false value disables project
    RAG. An explicit true value requires the bound path. Unknown values are NOT enabled.
    """
    import os

    raw = os.environ.get(PROJECT_RAG_ENABLED_ENV)
    if raw is None:
        return "legacy", "unset"
    value = raw.strip().casefold()
    if value in _TRUE:
        return "enabled", "explicit"
    if value in _FALSE:
        return "disabled", "explicit_false"
    return "disabled", "invalid_value"


def rag_embedding_binding_requested() -> bool:
    """True when ``AGK_RAG_EMBEDDING=ollama`` explicitly opts into the bound RAG path."""
    import os

    return os.environ.get(RAG_EMBEDDING_ENV, "").strip().casefold() == "ollama"


#: Registry id of the implicit project auto-registered from the process cwd before the user
#: has created or chosen any project (``ProjectRegistry._ensure_default_project``).
IMPLICIT_DEFAULT_PROJECT_ID = "default"


def bound_rag_root_status(project_root: str) -> str:
    """Non-raising classification used to decide setup-pending vs rejection.

    Returns ``"ok"``, ``"no_allowed_root"``, ``"missing"`` or ``"outside_allowed_root"``.
    It applies exactly the checks of :func:`bound_rag_project_root`; it never widens them.
    """
    try:
        _ = bound_rag_project_root(project_root)
    except ProjectEmbeddingBindingError as error:
        text = str(error)
        if "explicit allowed root" in text:
            return "no_allowed_root"
        if "does not exist" in text:
            return "missing"
        return "outside_allowed_root"
    return "ok"


def bound_rag_project_root(project_root: str) -> str:
    """Return the real project root a bound indexer may use, or raise.

    The bound path never falls back: ``AGK_RAG_ALLOWED_ROOT`` must name an existing directory
    and the (symlink-resolved) project root must exist inside it.
    """
    import os
    from pathlib import Path

    allowed = os.environ.get(RAG_ALLOWED_ROOT_ENV, "").strip()
    if not allowed or not project_root:
        raise ProjectEmbeddingBindingError("Bound project RAG requires an explicit allowed root.")
    allowed_real = Path(allowed).resolve()
    root_real = Path(project_root).resolve()
    if not allowed_real.is_dir() or not root_real.is_dir():
        raise ProjectEmbeddingBindingError("Bound project RAG root does not exist.")
    if not root_real.is_relative_to(allowed_real):
        raise ProjectEmbeddingBindingError("Bound project RAG root is outside the allowed root.")
    return str(root_real)


def configured_embedding_binding(
    registry: ModelRegistry | None = None, *, ollama_provider: OllamaEmbeddingProvider | None = None
) -> ProjectEmbeddingBinding | None:
    """Return the configured local-Ollama binding only when explicitly enabled.

    ``AGK_RAG_EMBEDDING=ollama`` opts in. The default embedding profile must be an Ollama
    profile on a loopback endpoint; otherwise this raises instead of silently falling back.
    """
    import os
    from urllib.parse import urlsplit

    if os.environ.get(RAG_EMBEDDING_ENV, "").strip().casefold() != "ollama":
        return None
    reg = registry if registry is not None else ModelRegistry()
    profile = reg.get_default("embedding")
    if profile is None:
        raise ProjectEmbeddingBindingError("No default embedding profile is configured.")
    binding = ProjectEmbeddingBinding(
        engine=EmbeddingEngine(registry=reg, ollama_provider=ollama_provider), model_name=profile.name
    )
    if urlsplit(binding.identity.endpoint).hostname not in _LOOPBACK_HOSTS:
        raise ProjectEmbeddingBindingError("The embedding endpoint must be a loopback address.")
    return binding


def configured_embedding_binding_or_none() -> ProjectEmbeddingBinding | None:
    """r30: same rules as :func:`configured_embedding_binding`; a misconfiguration is logged and
    returns None so the caller's store stays explicitly not-ready (never a substitute embedding)."""
    import logging

    try:
        return configured_embedding_binding()
    except ProjectEmbeddingBindingError as exc:
        logging.getLogger(__name__).warning("embedding binding not ready: %s", exc)
        return None
