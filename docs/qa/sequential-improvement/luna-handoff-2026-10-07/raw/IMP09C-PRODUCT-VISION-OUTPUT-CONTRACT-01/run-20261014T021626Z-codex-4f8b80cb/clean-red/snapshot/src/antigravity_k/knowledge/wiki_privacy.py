from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, TypeAdapter

from antigravity_k.knowledge.wiki_graph import delete_graph_rows, prepare_graph_deletion

ConnectionFactory = Callable[[], sqlite3.Connection]


class RemovedWikiRow(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: int
    title: str
    category: str


class WikiRow(RemovedWikiRow):
    tags: str
    content: str
    created_at: str


REMOVED_ROWS = TypeAdapter(tuple[RemovedWikiRow, ...])
WIKI_ROWS = TypeAdapter(tuple[WikiRow, ...])
SQLITE_CELL: TypeAdapter[str | int] = TypeAdapter(str | int)


def delete_vault_sources(
    connect: ConnectionFactory,
    wiki_dir: Path,
    source_urls: tuple[str, ...],
) -> int:
    if not source_urls:
        return 0

    connection = connect()
    try:
        removed_by_id: dict[int, RemovedWikiRow] = {}
        for source_url in source_urls:
            raw_rows: list[sqlite3.Row] = connection.execute(
                "SELECT id, title, category FROM wiki_entries WHERE source IN ('vault', 'obsidian') AND source_url = ?",
                (source_url,),
            ).fetchall()
            rows = REMOVED_ROWS.validate_python(
                tuple(_row_payload(row, ("id", "title", "category")) for row in raw_rows),
            )
            removed_by_id.update({row.id: row for row in rows})
        removed = tuple(removed_by_id.values())
        if not removed:
            return 0

        removed_ids = tuple(row.id for row in removed)
        prepare_graph_deletion(connection, removed_ids)
        delete_graph_rows(connection, removed_ids)
        for row in removed:
            _ = connection.execute("DELETE FROM wiki_access_log WHERE entry_id = ?", (row.id,))
            _ = connection.execute("DELETE FROM wiki_entries WHERE id = ?", (row.id,))
        connection.commit()
        replacements = _remaining_markdown_entries(connection, removed)
    finally:
        connection.close()

    for row in removed:
        markdown_path = _markdown_path(wiki_dir, row.category, row.title)
        markdown_path.unlink(missing_ok=True)
        replacement = replacements.get((row.category, row.title))
        if replacement is not None:
            _write_markdown(markdown_path, replacement)
    return len(removed)


def _remaining_markdown_entries(
    connection: sqlite3.Connection,
    removed: tuple[RemovedWikiRow, ...],
) -> dict[tuple[str, str], WikiRow]:
    replacements: dict[tuple[str, str], WikiRow] = {}
    for row in removed:
        key = (row.category, row.title)
        if key in replacements:
            continue
        raw_rows: list[sqlite3.Row] = connection.execute(
            "SELECT id, title, category, tags, content, created_at FROM wiki_entries "
            "WHERE category = ? AND title = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            key,
        ).fetchall()
        rows = WIKI_ROWS.validate_python(
            tuple(_row_payload(row, ("id", "title", "category", "tags", "content", "created_at")) for row in raw_rows),
        )
        if rows:
            replacements[key] = rows[0]
    return replacements


def _row_payload(row: sqlite3.Row, fields: tuple[str, ...]) -> dict[str, str | int]:
    return {field: SQLITE_CELL.validate_python(row[field]) for field in fields}


def _markdown_path(wiki_dir: Path, category: str, title: str) -> Path:
    safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:80]
    return wiki_dir / category / f"{safe_title}.md"


def _write_markdown(path: Path, row: WikiRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nid: {row.id}\ncategory: {row.category}\ntags: {row.tags}\ncreated: {row.created_at}\n---\n\n"
    _ = path.write_text(frontmatter + row.content, encoding="utf-8")
