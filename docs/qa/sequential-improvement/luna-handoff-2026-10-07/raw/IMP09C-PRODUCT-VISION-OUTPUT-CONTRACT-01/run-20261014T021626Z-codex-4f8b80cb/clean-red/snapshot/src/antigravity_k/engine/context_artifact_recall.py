"""Bounded lexical recall for persisted context artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import ClassVar, Final, final

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.engine.context_artifact_store import ContextArtifactStore

_ARTIFACT_REF_PATTERN: Final[re.Pattern[str]] = re.compile(r"artifact-[a-f0-9]{24}")
_DEFAULT_MAX_REFS: Final[int] = 8
_DEFAULT_MAX_CHUNKS_PER_REF: Final[int] = 32
_DEFAULT_MAX_MATCHES: Final[int] = 3
_DEFAULT_MAX_CHARS: Final[int] = 2_400
_DEFAULT_EXCERPT_CHARS: Final[int] = 900


class ContextArtifactRecallEntry(BaseModel):
    """One relevant, bounded excerpt recalled from a stored artifact."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ref_id: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = Field(min_length=1)


@final
class ContextArtifactRecall:
    """Recall task-relevant excerpts without requiring a model tool call."""

    def __init__(
        self,
        store: ContextArtifactStore,
        *,
        max_refs: int = _DEFAULT_MAX_REFS,
        max_chunks_per_ref: int = _DEFAULT_MAX_CHUNKS_PER_REF,
        max_matches: int = _DEFAULT_MAX_MATCHES,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ) -> None:
        if min(max_refs, max_chunks_per_ref, max_matches, max_chars) < 1:
            raise ValueError("recall limits must be positive")
        self._store = store
        self._max_refs = max_refs
        self._max_chunks_per_ref = max_chunks_per_ref
        self._max_matches = max_matches
        self._max_chars = max_chars

    def recall(
        self,
        messages: Sequence[Mapping[str, str]],
        focus_terms: Sequence[str],
    ) -> str | None:
        """Return a bounded prompt block for relevant artifact excerpts."""
        terms = self._normalized_terms(focus_terms)
        if not terms:
            return None
        refs = self._artifact_refs(messages)
        candidates: list[tuple[int, str, int, ContextArtifactRecallEntry]] = []
        for ref_id in refs:
            manifest = self._store.manifest(ref_id)
            if manifest is None:
                continue
            for chunk_index in range(min(manifest.chunk_count, self._max_chunks_per_ref)):
                chunk = self._store.read_chunk(ref_id, chunk_index)
                if chunk is None:
                    continue
                score = self._score(chunk.content, terms)
                if score < 1:
                    continue
                candidates.append(
                    (
                        score,
                        ref_id,
                        chunk_index,
                        ContextArtifactRecallEntry(
                            ref_id=ref_id,
                            chunk_index=chunk.index,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            content=self._excerpt(chunk.content, terms),
                        ),
                    ),
                )
        if not candidates:
            return None
        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1], candidate[2]))
        return self._format(candidates[: self._max_matches])

    @staticmethod
    def _normalized_terms(focus_terms: Sequence[str]) -> tuple[str, ...]:
        terms: list[str] = []
        seen: set[str] = set()
        for term in focus_terms:
            normalized = term.strip().casefold()
            if len(normalized) < 3 or normalized in seen:
                continue
            terms.append(normalized)
            seen.add(normalized)
        return tuple(terms)

    def _artifact_refs(self, messages: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
        refs: list[str] = []
        seen: set[str] = set()
        for message in messages:
            content = message.get("content", "")
            ref_ids: list[str] = _ARTIFACT_REF_PATTERN.findall(content)
            for ref_id in ref_ids:
                if ref_id not in seen:
                    refs.append(ref_id)
                    seen.add(ref_id)
                    if len(refs) >= self._max_refs:
                        return tuple(refs)
        return tuple(refs)

    @staticmethod
    def _score(content: str, terms: Sequence[str]) -> int:
        lowered = content.casefold()
        return sum(lowered.count(term) for term in terms)

    @staticmethod
    def _excerpt(content: str, terms: Sequence[str]) -> str:
        lowered = content.casefold()
        match_index = min(
            (index for term in terms if (index := lowered.find(term)) >= 0),
            default=0,
        )
        start = max(0, match_index - 250)
        return content[start : start + _DEFAULT_EXCERPT_CHARS]

    def _format(
        self,
        candidates: Sequence[tuple[int, str, int, ContextArtifactRecallEntry]],
    ) -> str | None:
        parts = ["[CONTEXT_ARTIFACT_RECALL]"]
        for _, _, _, entry in candidates:
            part = f"[UNTRUSTED_TOOL_RESULT]\n{entry.model_dump_json()}\n[/UNTRUSTED_TOOL_RESULT]"
            if sum(len(item) + 1 for item in (*parts, part, "[/CONTEXT_ARTIFACT_RECALL]")) > self._max_chars:
                break
            parts.append(part)
        if len(parts) == 1:
            return None
        parts.append("[/CONTEXT_ARTIFACT_RECALL]")
        return "\n".join(parts)
