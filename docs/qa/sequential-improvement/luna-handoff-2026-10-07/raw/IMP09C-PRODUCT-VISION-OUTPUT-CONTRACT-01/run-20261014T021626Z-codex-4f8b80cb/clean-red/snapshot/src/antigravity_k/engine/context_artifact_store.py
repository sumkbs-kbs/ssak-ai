"""Durable, content-addressed storage for context-sized tool artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antigravity_k.engine.context_artifact_retention import ArtifactRetentionPolicy


@final
@dataclass(frozen=True, slots=True)
class ContextArtifact:
    """Metadata describing a persisted large context payload."""

    ref_id: str
    sha256: str
    source: str
    total_chars: int
    chunk_count: int
    chunk_chars: int


@final
@dataclass(frozen=True, slots=True)
class ContextArtifactChunk:
    """One bounded artifact chunk with its source line range."""

    ref_id: str
    index: int
    chunk_count: int
    start_line: int
    end_line: int
    content: str


@final
@dataclass(frozen=True, slots=True)
class ContextArtifactChunkRange:
    """Payload-free metadata for an artifact chunk."""

    index: int
    start_line: int
    end_line: int
    chars: int


@final
@dataclass(frozen=True, slots=True)
class ContextArtifactManifest:
    """Typed metadata for a stored artifact."""

    ref_id: str
    sha256: str
    source: str
    total_chars: int
    chunk_count: int
    chunk_chars: int
    ranges: tuple[ContextArtifactChunkRange, ...]


@final
class InvalidChunkSizeError(ValueError):
    """Raised when an artifact chunk size cannot produce bounded chunks."""

    def __init__(self, chunk_chars: int):
        self.chunk_chars: int = chunk_chars
        super().__init__(f"chunk_chars must be positive, got {chunk_chars}")


class _StoredChunk(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str


class _StoredArtifact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    version: Literal[1] = 1
    ref_id: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    source: str = ""
    total_chars: int = Field(ge=0)
    chunk_chars: int = Field(ge=1)
    chunks: tuple[_StoredChunk, ...] = Field(min_length=1)


class ContextArtifactStore:
    """Persist large outputs in independently retrievable character chunks."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_artifacts: int = 256,
        max_total_bytes: int = 256 * 1024 * 1024,
    ):
        self.root: Path = Path(root)
        self._retention_policy: ArtifactRetentionPolicy = ArtifactRetentionPolicy(
            max_artifacts=max_artifacts,
            max_total_bytes=max_total_bytes,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def store(
        self,
        content: str,
        *,
        source: str = "",
        chunk_chars: int = 6_000,
    ) -> ContextArtifact:
        """Store content and return a stable reference for later retrieval."""
        if chunk_chars < 1:
            raise InvalidChunkSizeError(chunk_chars)

        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        ref_id = f"artifact-{digest[:24]}"
        path = self.root / f"{ref_id}.json"
        existing = self._load(ref_id)
        if existing is not None:
            self._retention_policy.prune(self.root, path)
            return self._metadata(existing)

        payload = _StoredArtifact(
            ref_id=ref_id,
            sha256=digest,
            source=source,
            total_chars=len(content),
            chunk_chars=chunk_chars,
            chunks=self._chunk_content(content, chunk_chars),
        )
        _ = path.write_text(payload.model_dump_json(), encoding="utf-8")
        path.chmod(0o600)
        self._retention_policy.prune(self.root, path)
        return self._metadata(payload)

    def read(self, ref_id: str, *, chunk_index: int | None = None) -> str | None:
        """Read an entire artifact or one zero-based chunk by reference ID."""
        payload = self._load(ref_id)
        if payload is None:
            return None
        if chunk_index is None:
            return "".join(chunk.content for chunk in payload.chunks)
        chunk = self._chunk(payload, chunk_index)
        return chunk.content if chunk is not None else None

    def read_chunk(self, ref_id: str, chunk_index: int) -> ContextArtifactChunk | None:
        """Read one bounded chunk and return navigation metadata with it."""
        payload = self._load(ref_id)
        if payload is None:
            return None
        chunk = self._chunk(payload, chunk_index)
        if chunk is None:
            return None
        return ContextArtifactChunk(
            ref_id=payload.ref_id,
            index=chunk.index,
            chunk_count=len(payload.chunks),
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
        )

    def manifest(self, ref_id: str) -> ContextArtifactManifest | None:
        """Return artifact metadata and chunk line ranges without payload text."""
        payload = self._load(ref_id)
        if payload is None:
            return None
        return ContextArtifactManifest(
            ref_id=payload.ref_id,
            sha256=payload.sha256,
            source=payload.source,
            total_chars=payload.total_chars,
            chunk_count=len(payload.chunks),
            chunk_chars=payload.chunk_chars,
            ranges=tuple(
                ContextArtifactChunkRange(
                    index=chunk.index,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    chars=len(chunk.content),
                )
                for chunk in payload.chunks
            ),
        )

    def _load(self, ref_id: str) -> _StoredArtifact | None:
        if not ref_id or Path(ref_id).name != ref_id:
            return None
        try:
            return _StoredArtifact.model_validate_json(
                (self.root / f"{ref_id}.json").read_text(encoding="utf-8"),
            )
        except (OSError, ValidationError):
            return None

    @staticmethod
    def _metadata(payload: _StoredArtifact) -> ContextArtifact:
        return ContextArtifact(
            ref_id=payload.ref_id,
            sha256=payload.sha256,
            source=payload.source,
            total_chars=payload.total_chars,
            chunk_count=len(payload.chunks),
            chunk_chars=payload.chunk_chars,
        )

    @staticmethod
    def _chunk(payload: _StoredArtifact, chunk_index: int) -> _StoredChunk | None:
        if chunk_index < 0 or chunk_index >= len(payload.chunks):
            return None
        return payload.chunks[chunk_index]

    @staticmethod
    def _chunk_content(content: str, chunk_chars: int) -> tuple[_StoredChunk, ...]:
        if not content:
            return (_StoredChunk(index=0, start_line=1, end_line=1, content=""),)
        chunks: list[_StoredChunk] = []
        for index, start in enumerate(range(0, len(content), chunk_chars)):
            chunk = content[start : start + chunk_chars]
            start_line = content.count("\n", 0, start) + 1
            chunks.append(
                _StoredChunk(
                    index=index,
                    start_line=start_line,
                    end_line=start_line + chunk.count("\n"),
                    content=chunk,
                ),
            )
        return tuple(chunks)
