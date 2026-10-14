"""Graph-memory-first relevant-file selection for bounded context acquisition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, override

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SearchValue = str | float | int | Sequence[str]
SearchRecord = Mapping[str, SearchValue]


class SelectionSource(StrEnum):
    CODEBASE_MEMORY = "codebase_memory"
    CODE_TREE_FALLBACK = "code_tree_fallback"
    NONE = "none"


class RelevantFile(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    score: float = 0.0
    functions: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    line_count: int | None = Field(default=None, ge=0)


@dataclass(frozen=True, slots=True)
class FileSelection:
    source: SelectionSource
    files: tuple[RelevantFile, ...]


@dataclass(frozen=True, slots=True)
class CodebaseMemoryUnavailableError(Exception):
    provider: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.provider} unavailable: {self.reason}"


class CodebaseMemorySearch(Protocol):
    def search_files(self, query: str, max_files: int) -> Sequence[SearchRecord]: ...


class CodeTreeSearch(Protocol):
    def build_tree(self) -> str: ...

    def search(self, query: str, max_files: int) -> Sequence[SearchRecord]: ...


def select_relevant_files(
    project_root: str | Path,
    query: str,
    *,
    memory_search: CodebaseMemorySearch | None,
    fallback_search: CodeTreeSearch | None,
    max_files: int = 8,
) -> FileSelection:
    """Select safe in-project files from graph memory before consulting the code tree."""
    root = Path(project_root).resolve()
    memory_files = _memory_files(memory_search, query, max_files, root)
    if memory_files:
        return FileSelection(source=SelectionSource.CODEBASE_MEMORY, files=memory_files)
    if fallback_search is None:
        return FileSelection(source=SelectionSource.NONE, files=())

    _ = fallback_search.build_tree()
    fallback_files = _parse_safe_files(fallback_search.search(query, max_files), root, max_files)
    source = SelectionSource.CODE_TREE_FALLBACK if fallback_files else SelectionSource.NONE
    return FileSelection(source=source, files=fallback_files)


def _memory_files(
    search: CodebaseMemorySearch | None,
    query: str,
    max_files: int,
    root: Path,
) -> tuple[RelevantFile, ...]:
    if search is None:
        return ()
    try:
        records = search.search_files(query, max_files)
    except CodebaseMemoryUnavailableError:
        return ()
    return _parse_safe_files(records, root, max_files)


def _parse_safe_files(
    records: Sequence[SearchRecord],
    root: Path,
    max_files: int,
) -> tuple[RelevantFile, ...]:
    selected: list[RelevantFile] = []
    seen: set[str] = set()
    for record in records:
        try:
            candidate = RelevantFile.model_validate(record)
        except ValidationError:
            continue
        relative_path = _safe_relative_path(root, candidate.file)
        if relative_path is None or relative_path in seen:
            continue
        seen.add(relative_path)
        selected.append(candidate.model_copy(update={"file": relative_path}))
        if len(selected) >= max_files:
            break
    return tuple(selected)


def _safe_relative_path(root: Path, candidate_path: str) -> str | None:
    candidate = Path(candidate_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    return relative.as_posix()
