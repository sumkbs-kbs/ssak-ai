"""Pure parsing and resolution helpers for Obsidian-style internal links.

This module deliberately has no database or knowledge-graph side effects.
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

_FRONTMATTER_DELIMITER = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class ObsidianLink:
    """One parsed Obsidian wikilink."""

    target: str
    heading: str | None = None
    alias: str | None = None
    embedded: bool = False


@dataclass(frozen=True, slots=True, order=True)
class ObsidianRelation:
    """A resolved, directed source-note to target-note relation."""

    source_path: str
    target_path: str
    relation: str = "obsidian"


@dataclass(frozen=True, slots=True)
class UnresolvedObsidianLink:
    """A wikilink that could not be safely resolved to exactly one note."""

    source_path: str
    link: ObsidianLink


@dataclass(frozen=True, slots=True)
class ObsidianLinkPlan:
    """Deterministic result of planning links without touching a database."""

    relations: tuple[ObsidianRelation, ...]
    unresolved: tuple[UnresolvedObsidianLink, ...]
    ignored_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObsidianVaultPlan:
    """Read-only inventory and link plan for one Obsidian vault."""

    link_plan: ObsidianLinkPlan
    scanned_paths: tuple[str, ...]
    skipped_paths: tuple[str, ...]
    read_errors: tuple[str, ...]
    documents: tuple[tuple[str, str], ...] = ()


def parse_obsidian_note(markdown: str) -> tuple[str, str, tuple[str, ...]]:
    """Return body, category, and string tags from safe YAML frontmatter."""
    metadata, body = _parse_yaml_frontmatter(markdown)
    category_value = metadata.get("category", "note")
    requested_category = category_value.strip() if isinstance(category_value, str) else ""
    category = requested_category if re.fullmatch(r"[\w-]{1,64}", requested_category) else "note"
    raw_tags = metadata.get("tags", ())
    tags: tuple[str, ...]
    if isinstance(raw_tags, str):
        tags = (raw_tags.strip(),) if raw_tags.strip() else ()
    elif isinstance(raw_tags, Sequence) and not isinstance(raw_tags, (bytes, bytearray)):
        tags = tuple(value.strip() for value in raw_tags if isinstance(value, str) and value.strip())
    else:
        tags = ()
    return body, category, tags


def expand_linked_entry_ids(
    seed_ids: Sequence[int],
    relations: Iterable[tuple[int, int]],
    *,
    eligible_ids: Collection[int],
    limit: int,
    direction: Literal["outbound", "backlinks", "both"] = "both",
) -> tuple[int, ...]:
    """Return seed IDs followed by deterministic one-hop relation neighbors.

    Seeds preserve their search-rank order and always take priority. Only IDs
    in ``eligible_ids`` are returned, so callers can enforce row-existence and
    category constraints before expansion. ``limit`` caps the complete result
    including seeds. Neighbors are ranked by seed order, then outbound before
    inbound for ``both``, then ID; they are deduplicated and never recursively
    expanded. No database or graph access occurs in this helper.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return ()

    eligible = set(eligible_ids)
    seeds: list[int] = []
    seen_seeds: set[int] = set()
    for seed_id in seed_ids:
        if seed_id in eligible and seed_id not in seen_seeds:
            seeds.append(seed_id)
            seen_seeds.add(seed_id)
            if len(seeds) == limit:
                return tuple(seeds)

    seed_rank = {entry_id: index for index, entry_id in enumerate(seeds)}
    neighbor_rank: dict[int, tuple[int, int, int]] = {}
    for source_id, target_id in relations:
        if source_id == target_id:
            continue
        if direction in ("outbound", "both") and source_id in seed_rank and target_id in eligible:
            _add_neighbor_rank(neighbor_rank, target_id, (seed_rank[source_id], 0, target_id))
        if direction in ("backlinks", "both") and target_id in seed_rank and source_id in eligible:
            _add_neighbor_rank(neighbor_rank, source_id, (seed_rank[target_id], 1, source_id))

    for seed_id in seen_seeds:
        neighbor_rank.pop(seed_id, None)
    remaining = limit - len(seeds)
    ordered_neighbors = sorted(neighbor_rank, key=neighbor_rank.__getitem__)[:remaining]
    return (*seeds, *ordered_neighbors)


def plan_obsidian_vault(vault_root: Path) -> ObsidianVaultPlan:
    """Read Markdown files and plan Obsidian relations without writing.

    Hidden paths and all symlinks are skipped. Files must resolve inside the
    vault and be valid UTF-8 Markdown. Walk/read failures are reported instead
    of silently producing a plan that could be mistaken for a complete import.
    No wiki database or generated Markdown mirror is opened or modified.
    """
    try:
        root = vault_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Obsidian vault root is not accessible: {vault_root}") from exc
    if not root.is_dir():
        raise ValueError(f"Obsidian vault root is not a directory: {vault_root}")

    documents: dict[str, str] = {}
    skipped_paths: set[str] = set()
    read_errors: set[str] = set()

    def record_walk_error(error: OSError) -> None:
        raw_path = Path(error.filename) if error.filename is not None else root
        read_errors.add(_report_path(root, raw_path))

    for directory, directory_names, filenames in os.walk(
        root,
        topdown=True,
        onerror=record_walk_error,
        followlinks=False,
    ):
        current = Path(directory)
        retained_directories: list[str] = []
        for name in sorted(directory_names, key=lambda item: (item.casefold(), item)):
            candidate = current / name
            if name.startswith(".") or candidate.is_symlink():
                skipped_paths.add(_report_path(root, candidate, resolve=False))
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in sorted(filenames, key=lambda item: (item.casefold(), item)):
            candidate = current / name
            if candidate.suffix.casefold() != ".md":
                continue
            if name.startswith(".") or candidate.is_symlink():
                skipped_paths.add(_report_path(root, candidate, resolve=False))
                continue
            try:
                resolved = candidate.resolve(strict=True)
                relative = resolved.relative_to(root)
                if not resolved.is_file():
                    skipped_paths.add(relative.as_posix())
                    continue
                markdown = resolved.read_text(encoding="utf-8")
            except (OSError, RuntimeError, UnicodeError, ValueError):
                read_errors.add(_report_path(root, candidate, resolve=False))
                continue
            documents[relative.as_posix()] = markdown

    plan = build_obsidian_link_plan(documents, vault_root=root)

    def path_order(value: str) -> tuple[str, str]:
        return value.casefold(), value

    return ObsidianVaultPlan(
        link_plan=plan,
        scanned_paths=tuple(sorted(documents, key=path_order)),
        skipped_paths=tuple(sorted(skipped_paths, key=path_order)),
        read_errors=tuple(sorted(read_errors, key=path_order)),
        documents=tuple((path, documents[path]) for path in sorted(documents, key=path_order)),
    )


def _report_path(root: Path, value: Path, *, resolve: bool = True) -> str:
    try:
        report_value = value.resolve(strict=False) if resolve else value.absolute()
        return report_value.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return str(value)


def _add_neighbor_rank(
    neighbor_rank: dict[int, tuple[int, int, int]],
    entry_id: int,
    rank: tuple[int, int, int],
) -> None:
    previous = neighbor_rank.get(entry_id)
    if previous is None or rank < previous:
        neighbor_rank[entry_id] = rank


def parse_obsidian_links(markdown: str) -> tuple[ObsidianLink, ...]:
    """Extract wikilinks outside fenced and inline code spans.

    Supported forms include ``[[note]]``, ``[[folder/note#heading|alias]]``
    and embedded links such as ``![[image-or-note]]``. This function parses
    syntax only: it does not decide whether a target exists in a vault.
    """
    visible = _mask_fenced_code(markdown)
    visible = _mask_inline_code(markdown, visible)
    links: list[ObsidianLink] = []
    cursor = 0

    while cursor < len(visible) - 1:
        opening = visible.find("[[", cursor)
        if opening < 0:
            break
        if _is_escaped(markdown, opening):
            cursor = opening + 2
            continue

        closing = _find_link_end(visible, markdown, opening + 2)
        if closing < 0:
            break

        raw = markdown[opening + 2 : closing]
        if "[[" not in raw:
            link = _parse_link_body(raw, embedded=_is_embed(markdown, opening))
            if link is not None:
                links.append(link)
        cursor = closing + 2

    return tuple(links)


def build_obsidian_link_plan(
    documents: Mapping[str, str] | Mapping[Path, str],
    *,
    vault_root: Path,
) -> ObsidianLinkPlan:
    """Build a stable directed-link plan from an in-memory Markdown inventory.

    This is a pure content-planning operation: it reads no file contents,
    writes no files, opens no database, and mutates no graph. Non-Markdown or unsafe
    source paths are reported in ``ignored_sources``. Every valid note is
    indexed before any wikilink is resolved, so forward references and
    aliases declared in files later in caller order resolve identically.
    Repeated source-target links collapse to one directed relation.
    """
    try:
        root = vault_root.expanduser().resolve()
    except (OSError, RuntimeError):
        return ObsidianLinkPlan(relations=(), unresolved=(), ignored_sources=(str(vault_root),))

    candidates: dict[str, list[tuple[str, str]]] = {}
    ignored_sources: list[str] = []
    for raw_path, markdown in documents.items():
        relative = _vault_relative_path(root, raw_path)
        if relative is None or relative.suffix.casefold() != ".md" or not isinstance(markdown, str):
            ignored_sources.append(str(raw_path))
            continue
        candidates.setdefault(relative.as_posix(), []).append((str(raw_path), markdown))

    source_documents: dict[str, str] = {}
    for relative_path, records in candidates.items():
        if len(records) != 1:
            ignored_sources.extend(raw_path for raw_path, _markdown in records)
            continue
        source_documents[relative_path] = records[0][1]

    def path_order(value: str) -> tuple[str, str]:
        return value.casefold(), value

    markdown_paths = tuple(sorted(source_documents, key=path_order))
    aliases: dict[str, tuple[str, ...]] = {
        relative_path: extract_frontmatter_aliases(markdown) for relative_path, markdown in source_documents.items()
    }

    relations: set[ObsidianRelation] = set()
    unresolved: list[UnresolvedObsidianLink] = []
    for source_path in sorted(source_documents, key=path_order):
        markdown = source_documents[source_path]
        for link in parse_obsidian_links(markdown):
            if not link.target and link.heading:
                # Heading-only wikilinks are valid within a note but do not
                # represent a document-to-document graph edge.
                continue
            target_path = resolve_obsidian_target(
                link,
                vault_root=root,
                source_path=source_path,
                markdown_paths=markdown_paths,
                aliases=aliases,
            )
            if target_path is None:
                unresolved.append(UnresolvedObsidianLink(source_path=source_path, link=link))
                continue
            relations.add(
                ObsidianRelation(
                    source_path=source_path,
                    target_path=target_path,
                ),
            )

    return ObsidianLinkPlan(
        relations=tuple(sorted(relations)),
        unresolved=tuple(unresolved),
        ignored_sources=tuple(sorted(set(ignored_sources), key=path_order)),
    )


def extract_frontmatter_aliases(markdown: str) -> tuple[str, ...]:
    """Read Obsidian ``aliases``/``alias`` strings from YAML frontmatter.

    Invalid YAML, non-mapping frontmatter, and non-string alias values are
    ignored. Returned values preserve source order and are deduplicated using
    Unicode case-folding.
    """
    frontmatter, _body = _parse_yaml_frontmatter(markdown)
    aliases: list[str] = []
    seen: set[str] = set()
    for key in ("aliases", "alias"):
        raw_values = frontmatter.get(key)
        if isinstance(raw_values, str):
            values: Sequence[object] = (raw_values,)
        elif isinstance(raw_values, Sequence) and not isinstance(raw_values, (bytes, bytearray)):
            values = raw_values
        else:
            continue

        for raw_value in values:
            if not isinstance(raw_value, str):
                continue
            value = raw_value.strip()
            folded = value.casefold()
            if value and folded not in seen:
                seen.add(folded)
                aliases.append(value)
    return tuple(aliases)


def _parse_yaml_frontmatter(markdown: str) -> tuple[Mapping[object, object], str]:
    text = markdown.removeprefix("\ufeff")
    delimiters = _FRONTMATTER_DELIMITER.finditer(text)
    opening = next(delimiters, None)
    if opening is None or opening.start() != 0:
        return {}, text
    closing = next(delimiters, None)
    if closing is None:
        return {}, text

    try:
        parsed = yaml.safe_load(text[opening.end() : closing.start()])
    except yaml.YAMLError:
        return {}, text
    if not isinstance(parsed, Mapping):
        return {}, text

    body = text[closing.end() :].lstrip("\r\n").strip()
    return parsed, body


def resolve_obsidian_target(
    link: ObsidianLink,
    *,
    vault_root: Path,
    source_path: str | Path,
    markdown_paths: Sequence[str | Path],
    aliases: Mapping[str, Sequence[str] | str] | None = None,
) -> str | None:
    """Resolve a wikilink to one vault-relative Markdown path.

    ``source_path``, ``markdown_paths``, and alias-map keys may be relative to
    ``vault_root`` or absolute paths inside it. Explicit paths are resolved
    relative to the vault root, except ``./`` and ``../`` paths, which are
    relative to the source note. Bare note names and aliases prefer a unique
    match in the source note's directory; otherwise they resolve only when
    globally unique. Ambiguous, missing, absolute, and out-of-vault targets
    return ``None`` rather than guessing.

    A heading-only link (for example ``[[#Details]]``) resolves to its source
    note; callers can omit self-relations if their graph does not model them.
    """
    try:
        root = vault_root.expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    source_relative = _vault_relative_path(root, source_path)
    if source_relative is None or source_relative.suffix.casefold() != ".md":
        return None

    notes = _collect_markdown_paths(root, markdown_paths)
    source_matches = [path for path in notes if _path_key(path) == _path_key(source_relative)]
    if len(source_matches) != 1:
        return None
    source_relative = source_matches[0]

    target = link.target.strip()
    if not target:
        return source_relative.as_posix() if link.heading else None
    if "\\" in target or "\x00" in target:
        return None

    target_path = Path(target)
    if target_path.is_absolute():
        return None

    has_explicit_path = "/" in target
    if has_explicit_path:
        if target.startswith(("./", "../")):
            candidate = _vault_relative_path(root, source_relative.parent / target_path)
        else:
            candidate = _vault_relative_path(root, target_path)
        if candidate is None:
            return None
        if candidate.suffix == "":
            candidate = candidate.with_suffix(".md")
        if candidate.suffix.casefold() != ".md":
            return None
        return _match_explicit_path(candidate, notes)

    title = _without_markdown_suffix(target).casefold()
    title_matches = [path for path in notes if path.stem.casefold() == title]
    match = _prefer_local_unique(title_matches, source_relative.parent)
    if match is not None:
        return match.as_posix()
    if title_matches:
        return None

    alias_matches = _find_alias_matches(root, notes, aliases or {}, target.casefold())
    match = _prefer_local_unique(alias_matches, source_relative.parent)
    return match.as_posix() if match is not None else None


def _parse_link_body(raw: str, *, embedded: bool) -> ObsidianLink | None:
    target_and_heading, separator, alias_text = raw.partition("|")
    target_and_heading = target_and_heading.strip()
    if not target_and_heading:
        return None

    target, heading_separator, heading = target_and_heading.partition("#")
    target = target.strip()
    heading_value = heading.strip() if heading_separator else None
    alias = alias_text.strip() if separator else None
    if not target and heading_value is None:
        return None
    return ObsidianLink(
        target=target,
        heading=heading_value,
        alias=alias,
        embedded=embedded,
    )


def _mask_fenced_code(markdown: str) -> str:
    """Replace fenced code contents with spaces while preserving offsets."""
    masked = list(markdown)
    fence_char: str | None = None
    fence_length = 0
    offset = 0

    for line in markdown.splitlines(keepends=True):
        line_body = line.rstrip("\r\n")
        if fence_char is None:
            match = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line_body)
            if match is not None:
                marker = match.group(1)
                info = line_body[match.end() :]
                if marker[0] != "`" or "`" not in info:
                    fence_char = marker[0]
                    fence_length = len(marker)
                    _mask_range(masked, offset, offset + len(line_body))
        else:
            _mask_range(masked, offset, offset + len(line_body))
            closing = re.match(rf"^[ \t]{{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$", line_body)
            if closing is not None:
                fence_char = None
                fence_length = 0
        offset += len(line)

    return "".join(masked)


def _mask_inline_code(markdown: str, visible: str) -> str:
    """Mask CommonMark-style backtick spans, including multiline spans."""
    masked = list(visible)
    cursor = 0
    while cursor < len(markdown):
        if visible[cursor] != "`" or _is_escaped(markdown, cursor):
            cursor += 1
            continue

        run_end = cursor + 1
        while run_end < len(markdown) and markdown[run_end] == "`" and visible[run_end] == "`":
            run_end += 1
        delimiter_length = run_end - cursor
        closing = _find_backtick_closer(markdown, visible, run_end, delimiter_length)
        if closing < 0:
            cursor = run_end
            continue

        closing_end = closing + delimiter_length
        _mask_range(masked, cursor, closing_end)
        cursor = closing_end

    return "".join(masked)


def _find_backtick_closer(markdown: str, visible: str, cursor: int, delimiter_length: int) -> int:
    while cursor < len(markdown):
        candidate = visible.find("`", cursor)
        if candidate < 0:
            return -1
        run_end = candidate + 1
        while run_end < len(markdown) and markdown[run_end] == "`" and visible[run_end] == "`":
            run_end += 1
        if run_end - candidate == delimiter_length:
            return candidate
        cursor = run_end
    return -1


def _find_link_end(visible: str, markdown: str, cursor: int) -> int:
    while cursor < len(visible) - 1:
        closing = visible.find("]]", cursor)
        if closing < 0:
            return -1
        if not _is_escaped(markdown, closing):
            return closing
        cursor = closing + 2
    return -1


def _is_embed(markdown: str, opening: int) -> bool:
    return opening > 0 and markdown[opening - 1] == "!" and not _is_escaped(markdown, opening - 1)


def _is_escaped(text: str, offset: int) -> bool:
    backslashes = 0
    cursor = offset - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _vault_relative_path(root: Path, value: str | Path) -> Path | None:
    raw_path = Path(value).expanduser()
    if raw_path.is_absolute():
        candidate = raw_path
    else:
        candidate = root / raw_path
    try:
        relative = candidate.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        return None
    return relative


def _collect_markdown_paths(root: Path, values: Sequence[str | Path]) -> tuple[Path, ...]:
    notes: dict[str, Path] = {}
    for value in values:
        relative = _vault_relative_path(root, value)
        if relative is None or relative.suffix.casefold() != ".md":
            continue
        notes.setdefault(relative.as_posix(), relative)
    return tuple(notes[key] for key in sorted(notes, key=str.casefold))


def _match_explicit_path(candidate: Path, notes: Sequence[Path]) -> str | None:
    key = _path_key(candidate)
    matches = [path for path in notes if _path_key(path) == key]
    return matches[0].as_posix() if len(matches) == 1 else None


def _prefer_local_unique(matches: Sequence[Path], source_directory: Path) -> Path | None:
    local = [path for path in matches if path.parent == source_directory]
    if len(local) == 1:
        return local[0]
    if local or len(matches) != 1:
        return None
    return matches[0]


def _find_alias_matches(
    root: Path,
    notes: Sequence[Path],
    aliases: Mapping[str, Sequence[str] | str],
    sought_alias: str,
) -> list[Path]:
    matches: list[Path] = []
    seen: set[str] = set()
    for alias_path, raw_aliases in aliases.items():
        relative = _vault_relative_path(root, alias_path)
        if relative is None or relative.suffix.casefold() != ".md":
            continue
        candidates = [path for path in notes if _path_key(path) == _path_key(relative)]
        if len(candidates) != 1:
            continue
        note = candidates[0]
        note_identity = note.as_posix()
        if note_identity in seen:
            continue
        if isinstance(raw_aliases, str):
            values: Sequence[str] = (raw_aliases,)
        else:
            values = raw_aliases
        if any(value.strip().casefold() == sought_alias for value in values if isinstance(value, str)):
            matches.append(note)
            seen.add(note_identity)
    return matches


def _path_key(path: Path) -> str:
    return path.as_posix().casefold()


def _without_markdown_suffix(target: str) -> str:
    return target[:-3] if target.casefold().endswith(".md") else target


def _mask_range(masked: list[str], start: int, end: int) -> None:
    for index in range(start, min(end, len(masked))):
        if masked[index] not in "\r\n":
            masked[index] = " "
