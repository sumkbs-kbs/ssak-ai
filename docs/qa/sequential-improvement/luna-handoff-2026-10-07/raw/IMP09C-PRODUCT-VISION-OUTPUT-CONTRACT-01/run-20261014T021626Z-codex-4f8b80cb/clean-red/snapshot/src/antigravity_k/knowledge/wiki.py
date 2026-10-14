"""Ssak-Ai: LLM Wiki — 세컨드 브레인 (Second Brain).

======================================================
로컬 LLM의 지식을 확장하는 영속적 지식 관리 시스템.

핵심 기능:
    1. Markdown / Obsidian 볼트 자동 파싱 & 벡터화
    2. 위키 CRUD API (등록/검색/갱신/삭제)
    3. 대화 중 자동 지식 참조 (RAG 연동)
    4. 웹 검색 결과 자동 저장
    5. 지식 그래프 메타데이터 관리

아키텍처:
    ┌─────────┐     ┌──────────┐     ┌──────────┐
    │ LLM 채팅 │ ──▶ │ Wiki API │ ──▶ │ SQLite   │
    └─────────┘     └──────────┘     │ + FTS5   │
         ▲               │           └──────────┘
         │               ▼
    ┌─────────┐     ┌──────────┐
    │ 웹 검색  │ ──▶ │ 벡터 DB  │
    └─────────┘     │(ChromaDB)│
                    └──────────┘

사용법:
    from antigravity_k.knowledge.wiki import LLMWiki

    wiki = LLMWiki()
    wiki.add_entry("FastAPI 3.0", "2025년 출시된 FastAPI 3.0의 주요 변경사항...")
    results = wiki.search("FastAPI 비동기 패턴")
"""

import json
import logging
import os
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast, final

from antigravity_k.knowledge.obsidian_links import (
    expand_linked_entry_ids,
    parse_obsidian_note,
    plan_obsidian_vault,
)
from antigravity_k.knowledge.wiki_graph import (
    GraphRewardEvent,
    KGBinaryValidator,
    advance_reward_tick,
    advance_reward_ticks,
    delete_graph_rows,
    graph_deletion_events,
    prepare_graph_deletion,
)

logger = logging.getLogger("llm_wiki")

from antigravity_k.config import config

# ─── 데이터 디렉토리 ──────────────────────────────────────────────
DATA_DIR = config.paths.data_dir
WIKI_DB_PATH = DATA_DIR / "wiki.db"
WIKI_DIR = config.paths.wiki_dir


# ─── 데이터 모델 ──────────────────────────────────────────────────


@dataclass
class WikiEntry:
    """위키 항목."""

    id: int | None = None
    title: str = ""
    content: str = ""
    category: str = "general"  # general, code, domain, web, note
    tags: list[str] = field(default_factory=list)
    source: str = ""  # manual, web_search, obsidian, chat
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    relevance_score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        d = cast(dict[str, object], asdict(self))
        d["tags"] = json.dumps(self.tags, ensure_ascii=False)
        return d


@dataclass
class SearchHit:
    """검색 결과."""

    entry: WikiEntry
    score: float = 0.0
    matched_field: str = ""  # title, content, tags


# ─── LLM Wiki 코어 ───────────────────────────────────────────────


@final
class LLMWiki:
    """세컨드 브레인 — 로컬 LLM을 위한 영속적 지식 관리.

    SQLite FTS5 (Full-Text Search)를 사용하여
    외부 벡터 DB 없이도 빠른 키워드 + 의미 검색을 지원합니다.
    ChromaDB 통합은 선택적입니다.

    Args:
        db_path: SQLite DB 경로

    """

    def __init__(self, db_path: Path | None = None):
        """Initialize the LLMWiki.

        Args:
            db_path (Path | None): Path | None db path.

        """
        p = db_path or WIKI_DB_PATH
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            test_file = p.parent / f".agk_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            self.db_path = p
        except OSError:
            fallback_dir = Path.home() / ".antigravity-k" / "data"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = fallback_dir / p.name

        try:
            WIKI_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._init_db()

    def _init_db(self) -> None:
        """DB 스키마 초기화."""
        conn = self._connect()
        _ = conn.executescript(
            """
            -- 메인 위키 테이블

            CREATE TABLE IF NOT EXISTS wiki_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                category    TEXT DEFAULT 'general',
                tags        TEXT DEFAULT '[]',
                source      TEXT DEFAULT 'manual',
                source_url  TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            -- FTS5 전문 검색 인덱스
            CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
                title,
                content,
                tags,
                content=wiki_entries,
                content_rowid=id,
                tokenize='unicode61'
            );

            -- FTS 트리거 (자동 동기화)
            CREATE TRIGGER IF NOT EXISTS wiki_ai AFTER INSERT ON wiki_entries BEGIN
                INSERT INTO wiki_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS wiki_ad AFTER DELETE ON wiki_entries BEGIN
                INSERT INTO wiki_fts(wiki_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS wiki_au AFTER UPDATE ON wiki_entries BEGIN
                INSERT INTO wiki_fts(wiki_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
                INSERT INTO wiki_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END;

            -- 지식 그래프 (항목 간 관계)
            CREATE TABLE IF NOT EXISTS wiki_links (
                from_id INTEGER NOT NULL,
                to_id   INTEGER NOT NULL,
                relation TEXT DEFAULT 'related',
                created_at TEXT NOT NULL,
                PRIMARY KEY (from_id, to_id),
                FOREIGN KEY (from_id) REFERENCES wiki_entries(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id) REFERENCES wiki_entries(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_wiki_links_to_from ON wiki_links(to_id, from_id);
            CREATE INDEX IF NOT EXISTS idx_wiki_entries_source_url ON wiki_entries(source, source_url);

            CREATE TABLE IF NOT EXISTS wiki_graph_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                tick INTEGER NOT NULL CHECK (tick >= 0)
            );
            INSERT OR IGNORE INTO wiki_graph_state (id, tick) VALUES (1, 0);

            CREATE TABLE IF NOT EXISTS wiki_node_rewards (
                entry_id INTEGER PRIMARY KEY,
                score REAL NOT NULL CHECK (score > 0 AND score <= 10),
                FOREIGN KEY (entry_id) REFERENCES wiki_entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS wiki_link_rewards (
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                score REAL NOT NULL CHECK (score > 0 AND score <= 10),
                PRIMARY KEY (from_id, to_id),
                FOREIGN KEY (from_id, to_id) REFERENCES wiki_links(from_id, to_id) ON DELETE CASCADE
            );

            -- 접근 이력
            CREATE TABLE IF NOT EXISTS wiki_access_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id   INTEGER NOT NULL,
                query      TEXT,
                accessed_at TEXT NOT NULL,
                context    TEXT DEFAULT ''
            );
        """,
        )
        conn.close()
        validation = KGBinaryValidator(self.db_path).validate()
        if validation["OK"] is not True:
            raise RuntimeError(f"Wiki KG validation failed: {validation['errors']}")
        logger.info("Wiki DB 초기화 완료: %s", self.db_path)

    def validate_knowledge_graph(self) -> dict[str, object]:
        """Validate graph invariants using a read-only SQLite connection."""
        return dict(KGBinaryValidator(self.db_path).validate())

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        _ = conn.execute("PRAGMA journal_mode=WAL")
        _ = conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ─── CRUD ────────────────────────────────────────────────────

    def add_entry(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: list[str] | None = None,
        source: str = "manual",
        source_url: str = "",
    ) -> int:
        """위키에 새 항목을 추가합니다.

        Args:
            title: 제목
            content: 내용 (Markdown 지원)
            category: 카테고리 (general/code/domain/web/note)
            tags: 태그 목록
            source: 출처 (manual/web_search/obsidian/chat)
            source_url: 출처 URL

        Returns:
            생성된 항목 ID

        """
        if re.fullmatch(r"[\w-]{1,64}", category) is None:
            raise ValueError("Wiki category must be a safe path component")
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """INSERT INTO wiki_entries

                   (title, content, category, tags, source, source_url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, content, category, tags_json, source, source_url, now, now),
            )
            entry_id = cursor.lastrowid or 0
            if entry_id:
                advance_reward_tick(conn, node_id=entry_id)
            conn.commit()
        except BaseException:
            conn.rollback()
            conn.close()
            raise
        conn.close()

        # Markdown 파일로도 저장 (Obsidian 호환)
        self._save_markdown(entry_id, title, content, category, tags or [])

        logger.info("위키 항목 추가: [%s] %s", entry_id, title)
        return entry_id

    def update_entry(self, entry_id: int, **kwargs: object) -> bool:
        """기존 항목을 업데이트합니다.

        사용법:
            wiki.update_entry(1, content="새로운 내용", tags=["python", "async"])
        """
        allowed = {"title", "content", "category", "tags", "source_url"}
        updates: dict[str, object] = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return False
        if (
            isinstance(updates.get("category"), str)
            and re.fullmatch(r"[\w-]{1,64}", cast(str, updates["category"])) is None
        ):
            raise ValueError("Wiki category must be a safe path component")

        if "tags" in updates and isinstance(updates["tags"], list):
            updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)

        updates["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values: list[object] = list(updates.values()) + [entry_id]

        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                # set_clause contains only keys from the local `allowed` set.
                f"UPDATE wiki_entries SET {set_clause} WHERE id = ?",  # nosec B608
                values,
            )
            if cursor.rowcount > 0:
                advance_reward_tick(conn, node_id=entry_id)
            conn.commit()
            updated = cursor.rowcount > 0
        except BaseException:
            conn.rollback()
            conn.close()
            raise
        conn.close()

        logger.info("위키 항목 업데이트: [%s]", entry_id)
        return updated

    def sync_vault_entry(
        self,
        title: str,
        content: str,
        category: str,
        tags: list[str],
        source_url: str,
    ) -> int:
        """정확한 소스 경로로 Vault 소유 위키 행을 생성하거나 갱신합니다."""
        if re.fullmatch(r"[\w-]{1,64}", category) is None:
            raise ValueError("Vault wiki category must be a safe path component")
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        tags_json = json.dumps(tags, ensure_ascii=False)
        connection = self._connect()
        changed = False
        obsolete_mirror: tuple[str, str] | None = None
        source_was_obsidian = False
        try:
            _ = connection.execute("BEGIN IMMEDIATE")
            matches = cast(
                list[sqlite3.Row],
                connection.execute(
                    "SELECT id, title, content, category, tags, source FROM wiki_entries "
                    "WHERE source IN ('vault', 'obsidian') AND source_url = ? ORDER BY id LIMIT 2",
                    (source_url,),
                ).fetchall(),
            )
            if len(matches) > 1:
                raise RuntimeError(f"Duplicate Vault wiki source path: {source_url}")
            source_was_obsidian = bool(matches) and str(matches[0]["source"] or "") == "obsidian"
            if source_was_obsidian:
                _ = connection.execute(
                    "UPDATE wiki_entries SET source = 'vault' WHERE id = ?",
                    (int(matches[0]["id"]),),
                )

            if not matches:
                cursor = connection.execute(
                    """INSERT INTO wiki_entries
                       (title, content, category, tags, source, source_url, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'vault', ?, ?, ?)""",
                    (title, content, category, tags_json, source_url, now, now),
                )
                entry_id = int(cursor.lastrowid or 0)
                if entry_id <= 0:
                    raise RuntimeError("Vault wiki insert did not return an entry ID")
                changed = True
            else:
                row = matches[0]
                entry_id = int(row["id"])
                changed = (
                    str(row["title"]) != title
                    or str(row["content"]) != content
                    or str(row["category"] or "") != category
                    or str(row["tags"] or "[]") != tags_json
                    or str(row["source"] or "") != "vault"
                )
                if source_was_obsidian or changed:
                    previous_mirror = (str(row["category"] or "general"), str(row["title"] or ""))
                    if previous_mirror != (category, title):
                        obsolete_mirror = previous_mirror
                    if changed:
                        _ = connection.execute(
                            "UPDATE wiki_entries SET title = ?, content = ?, category = ?, tags = ?, source = 'vault', "
                            "updated_at = ? WHERE id = ?",
                            (title, content, category, tags_json, now, entry_id),
                        )

            if changed or source_was_obsidian:
                advance_reward_tick(connection, node_id=entry_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

        mirror_keys = {(category, title)}
        if obsolete_mirror is not None:
            mirror_keys.add(obsolete_mirror)
        mirror_connection = self._connect()
        try:
            mirror_rows: list[tuple[tuple[str, str], sqlite3.Row | None]] = []
            for mirror_key in sorted(mirror_keys):
                mirror_row = cast(
                    sqlite3.Row | None,
                    mirror_connection.execute(
                        "SELECT * FROM wiki_entries WHERE category = ? AND title = ? "
                        "ORDER BY updated_at DESC, id DESC LIMIT 1",
                        mirror_key,
                    ).fetchone(),
                )
                mirror_rows.append((mirror_key, mirror_row))
        finally:
            mirror_connection.close()

        for (mirror_category, mirror_title), mirror_row in mirror_rows:
            if re.fullmatch(r"[\w-]{1,64}", mirror_category) is None:
                logger.warning("Skipping an unsafe Wiki Markdown mirror category: %r", mirror_category)
                continue
            if mirror_row is None:
                safe_title = re.sub(r'[<>:"/\\|?*]', "_", mirror_title)[:80]
                (WIKI_DIR / mirror_category / f"{safe_title}.md").unlink(missing_ok=True)
                continue
            mirror = self._row_to_entry(mirror_row)
            self._save_markdown(mirror.id, mirror.title, mirror.content, mirror.category, mirror.tags)
        return entry_id

    def delete_entry(self, entry_id: int) -> bool:
        """항목, 접근 이력 및 연결 관계를 한 트랜잭션으로 제거합니다."""
        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute("SELECT 1 FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone()
            if exists is None:
                conn.rollback()
                return False
            prepare_graph_deletion(conn, (entry_id,))
            delete_graph_rows(conn, (entry_id,))
            cursor = conn.execute("DELETE FROM wiki_entries WHERE id = ?", (entry_id,))
            _ = conn.execute("DELETE FROM wiki_access_log WHERE entry_id = ?", (entry_id,))
            conn.commit()
            return cursor.rowcount > 0
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_vault_sources(self, source_urls: tuple[str, ...]) -> int:
        from antigravity_k.knowledge.wiki_privacy import delete_vault_sources

        return delete_vault_sources(self._connect, WIKI_DIR, source_urls)

    def get_entry(self, entry_id: int) -> WikiEntry | None:
        """ID로 항목을 조회합니다."""
        conn = self._connect()
        _ = conn.execute("BEGIN")
        row = cast(
            sqlite3.Row | None,
            conn.execute("SELECT * FROM wiki_entries WHERE id = ?", (entry_id,)).fetchone(),
        )
        conn.close()

        if not row:
            return None

        return self._row_to_entry(row)

    # ─── 검색 ────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        category: str | None = None,
        limit: int = 10,
        *,
        link_direction: Literal["outbound", "backlinks", "both"] = "both",
        expand_links: bool = True,
    ) -> list[SearchHit]:
        """위키를 전문 검색합니다.

        FTS5 기반 검색 + 접근 빈도 가중치.

        Args:
            query: 검색 쿼리
            category: 카테고리 필터
            limit: 최대 결과 수

        Returns:
            관련도 순으로 정렬된 검색 결과

        """
        if limit <= 0:
            return []
        if link_direction not in {"outbound", "backlinks", "both"}:
            raise ValueError("link_direction must be outbound, backlinks, or both")
        if not query.strip():
            return []
        # FTS5 검색
        fts_query = self._prepare_fts_query(query)
        if not fts_query:
            return []
        conn = self._connect()
        _ = conn.execute("BEGIN")

        if category is not None:
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    """SELECT e.*, bm25(wiki_fts) as score

                   FROM wiki_fts f
                   JOIN wiki_entries e ON f.rowid = e.id
                   WHERE wiki_fts MATCH ?
                     AND e.category = ?
                   ORDER BY score, e.id
                   LIMIT ?""",
                    (fts_query, category, limit),
                ).fetchall(),
            )
        else:
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    """SELECT e.*, bm25(wiki_fts) as score

                   FROM wiki_fts f
                   JOIN wiki_entries e ON f.rowid = e.id
                   WHERE wiki_fts MATCH ?
                   ORDER BY score, e.id
                   LIMIT ?""",
                    (fts_query, limit),
                ).fetchall(),
            )

        direct_results: list[SearchHit] = []
        for row in rows:
            entry = self._row_to_entry(row)
            direct_results.append(
                SearchHit(
                    entry=entry,
                    score=abs(cast(float, row["score"])),
                    matched_field="fts",
                ),
            )

        results = direct_results
        if expand_links and direct_results:
            seed_ids = [hit.entry.id for hit in direct_results if hit.entry.id is not None]
            if seed_ids and len(seed_ids) < limit:
                relation_pairs_set: set[tuple[int, int]] = set()
                category_clause = (
                    " AND source_entry.category = ? AND target_entry.category = ?" if category is not None else ""
                )
                for offset in range(0, len(seed_ids), 400):
                    seed_chunk = seed_ids[offset : offset + 400]
                    placeholders = ",".join("?" for _ in seed_chunk)
                    if link_direction == "outbound":
                        direction_clause = f"link.from_id IN ({placeholders})"
                        relation_params: tuple[object, ...] = tuple(seed_chunk)
                    elif link_direction == "backlinks":
                        direction_clause = f"link.to_id IN ({placeholders})"
                        relation_params = tuple(seed_chunk)
                    else:
                        direction_clause = f"(link.from_id IN ({placeholders}) OR link.to_id IN ({placeholders}))"
                        relation_params = (*seed_chunk, *seed_chunk)
                    if category is not None:
                        relation_params = (*relation_params, category, category)
                    link_rows = cast(
                        list[sqlite3.Row],
                        conn.execute(
                            f"""SELECT link.from_id, link.to_id FROM wiki_links AS link
                                JOIN wiki_entries AS source_entry ON source_entry.id = link.from_id
                                JOIN wiki_entries AS target_entry ON target_entry.id = link.to_id
                                WHERE {direction_clause} AND link.relation = 'obsidian'{category_clause}
                                ORDER BY link.from_id, link.to_id""",
                            relation_params,
                        ).fetchall(),
                    )
                    relation_pairs_set.update((int(row[0]), int(row[1])) for row in link_rows)
                relation_pairs = sorted(relation_pairs_set)
                eligible_ids = set(seed_ids)
                eligible_ids.update(endpoint for pair in relation_pairs for endpoint in pair)
                ordered_ids = expand_linked_entry_ids(
                    seed_ids,
                    relation_pairs,
                    eligible_ids=eligible_ids,
                    limit=limit,
                    direction=link_direction,
                )
                direct_ids = set(seed_ids)
                neighbor_ids = [entry_id for entry_id in ordered_ids if entry_id not in direct_ids]
                if neighbor_ids:
                    expanded_by_id: dict[int, sqlite3.Row] = {}
                    for offset in range(0, len(neighbor_ids), 400):
                        chunk = neighbor_ids[offset : offset + 400]
                        placeholders = ",".join("?" for _ in chunk)
                        expanded_rows = cast(
                            list[sqlite3.Row],
                            conn.execute(
                                f"SELECT * FROM wiki_entries WHERE id IN ({placeholders})",  # nosec B608
                                tuple(chunk),
                            ).fetchall(),
                        )
                        expanded_by_id.update({int(row["id"]): row for row in expanded_rows})
                    for entry_id in neighbor_ids:
                        expanded_row = expanded_by_id.get(entry_id)
                        if expanded_row is None:
                            continue
                        results.append(
                            SearchHit(
                                entry=self._row_to_entry(expanded_row),
                                score=0.0,
                                matched_field="wiki_link",
                            ),
                        )

        # 접근 이력 기록
        for hit in results:
            if hit.entry.id is not None:
                self._log_access(conn, hit.entry.id, query)

        conn.commit()
        conn.close()

        logger.info("위키 검색: '%s' → %s개 결과", query, len(results))
        return results

    def search_for_llm(self, query: str, max_chars: int = 2000) -> str:
        """LLM 컨텍스트에 주입할 수 있도록 검색 결과를 포맷합니다.

        api_forwarder.py에서 자동으로 호출됩니다.
        """
        if max_chars <= 0:
            return ""
        hits = self.search(query, limit=5)
        if not hits:
            return ""

        header = "[📚 세컨드 브레인 — 관련 지식]\n\n"
        if len(header) > max_chars:
            return ""
        context = header
        has_block = False

        for hit in hits:
            entry = hit.entry
            block = f"### {entry.title}\n{entry.content[:500]}\n_(카테고리: {entry.category}, 출처: {entry.source})_\n"
            if hit.matched_field == "wiki_link":
                block = block.replace("_(카테고리:", "_(연결 문서, 카테고리:")
            separator = "\n" if has_block else ""
            if len(context) + len(separator) + len(block) > max_chars:
                break
            context += separator + block
            has_block = True

        return context if has_block else ""

    # ─── Obsidian / Markdown 파싱 ────────────────────────────────

    def import_obsidian_vault(self, vault_path: str) -> int:
        """Obsidian 볼트를 일괄 임포트합니다.

        Args:
            vault_path: Obsidian 볼트 디렉토리 경로

        Returns:
            임포트된 항목 수

        """
        vault = Path(vault_path).expanduser().resolve(strict=True)
        vault_plan = plan_obsidian_vault(vault)
        if vault_plan.read_errors:
            raise OSError(f"Obsidian vault scan incomplete: {vault_plan.read_errors}")

        documents: dict[str, tuple[str, str, tuple[str, ...], str]] = {}
        for relative_path, raw in vault_plan.documents:
            body, category, tags = parse_obsidian_note(raw)
            documents[relative_path] = (Path(relative_path).stem, body, tags, category)

        def source_relative_path(source_url: str) -> str | None:
            raw_path = Path(source_url).expanduser()
            candidates = [raw_path] if raw_path.is_absolute() else [vault / raw_path, Path(os.path.abspath(raw_path))]
            for candidate in candidates:
                try:
                    lexical = Path(os.path.abspath(candidate)).relative_to(vault)
                except (OSError, RuntimeError, ValueError):
                    lexical = None
                if lexical is not None and lexical.parts and all(part not in ("", ".", "..") for part in lexical.parts):
                    return lexical.as_posix()
                try:
                    resolved = candidate.resolve(strict=False).relative_to(vault)
                except (OSError, RuntimeError, ValueError):
                    continue
                if resolved.parts and all(part not in ("", ".", "..") for part in resolved.parts):
                    return resolved.as_posix()
            return None

        skipped = set(vault_plan.skipped_paths)

        def source_was_skipped(source_url: str) -> bool:
            relative = source_relative_path(source_url)
            if relative is None:
                return False
            return any(relative == path or relative.startswith(path.rstrip("/") + "/") for path in skipped)

        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        conn = self._connect()
        path_to_id: dict[str, int] = {}
        reward_events: list[GraphRewardEvent] = []
        obsolete_mirror_keys: set[tuple[str, str]] = set()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            existing_rows = cast(
                list[sqlite3.Row],
                conn.execute("SELECT * FROM wiki_entries WHERE source IN ('vault', 'obsidian')").fetchall(),
            )
            existing_by_path: dict[str, sqlite3.Row] = {}
            for row in existing_rows:
                source_url = str(row["source_url"] or "")
                relative = source_relative_path(source_url)
                if relative is None:
                    continue
                canonical = str(vault / relative)
                if canonical in existing_by_path:
                    raise RuntimeError(f"Duplicate Obsidian entry source path: {canonical}")
                existing_by_path[canonical] = row

            desired_urls = {str(vault / relative_path) for relative_path in documents}
            for relative_path in sorted(documents, key=lambda value: (value.casefold(), value)):
                title, body, tags, category = documents[relative_path]
                source_url = str(vault / relative_path)
                tags_json = json.dumps(tags, ensure_ascii=False)
                existing = existing_by_path.get(source_url)
                if existing is None:
                    cursor = conn.execute(
                        """INSERT INTO wiki_entries
                           (title, content, category, tags, source, source_url, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'obsidian', ?, ?, ?)""",
                        (title, body, category, tags_json, source_url, now, now),
                    )
                    entry_id = int(cursor.lastrowid or 0)
                    reward_events.append(("node", entry_id))
                else:
                    entry_id = int(existing["id"])
                    changed = (
                        str(existing["title"]) != title
                        or str(existing["content"]) != body
                        or str(existing["category"]) != category
                        or str(existing["tags"]) != tags_json
                        or str(existing["source"]) != "obsidian"
                    )
                    if changed:
                        old_mirror_key = (str(existing["category"] or "general"), str(existing["title"] or ""))
                        if old_mirror_key != (category, title):
                            obsolete_mirror_keys.add(old_mirror_key)
                        _ = conn.execute(
                            """UPDATE wiki_entries SET title = ?, content = ?, category = ?, tags = ?, source = 'obsidian',
                               updated_at = ? WHERE id = ?""",
                            (title, body, category, tags_json, now, entry_id),
                        )
                        reward_events.append(("node", entry_id))
                path_to_id[relative_path] = entry_id

            desired_pairs = {
                (path_to_id[relation.source_path], path_to_id[relation.target_path])
                for relation in vault_plan.link_plan.relations
                if relation.source_path in path_to_id
                and relation.target_path in path_to_id
                and path_to_id[relation.source_path] != path_to_id[relation.target_path]
            }
            protected_ids = {
                int(row["id"]) for source_url, row in existing_by_path.items() if source_was_skipped(source_url)
            }
            owned_ids = tuple(sorted({int(row["id"]) for row in existing_by_path.values()} | set(path_to_id.values())))
            old_relations: dict[tuple[int, int], str] = {}
            for offset in range(0, len(owned_ids), 400):
                chunk = owned_ids[offset : offset + 400]
                placeholders = ",".join("?" for _ in chunk)
                old_rows = cast(
                    list[sqlite3.Row],
                    conn.execute(
                        f"""SELECT from_id, to_id, relation FROM wiki_links
                            WHERE from_id IN ({placeholders}) AND relation = 'obsidian'""",  # nosec B608
                        chunk,
                    ).fetchall(),
                )
                old_relations.update(
                    {(int(row["from_id"]), int(row["to_id"])): str(row["relation"] or "related") for row in old_rows},
                )

            for pair, _old_relation in sorted(old_relations.items()):
                if pair not in desired_pairs and not ({pair[0], pair[1]} & protected_ids):
                    reward_events.append(("decay", None))
                    _ = conn.execute("DELETE FROM wiki_links WHERE from_id = ? AND to_id = ?", pair)
            for pair in sorted(desired_pairs):
                cursor = conn.execute(
                    "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', ?) "
                    "ON CONFLICT(from_id, to_id) DO NOTHING",
                    (pair[0], pair[1], now),
                )
                if cursor.rowcount > 0:
                    reward_events.append(("link", pair))

            stale_urls = {
                source_url for source_url in set(existing_by_path) - desired_urls if not source_was_skipped(source_url)
            }
            stale_ids = tuple(sorted(int(existing_by_path[url]["id"]) for url in stale_urls))
            if stale_ids:
                for source_url in stale_urls:
                    stale_row = existing_by_path[source_url]
                    obsolete_mirror_keys.add(
                        (str(stale_row["category"] or "general"), str(stale_row["title"] or "")),
                    )
                reward_events.extend(graph_deletion_events(conn, stale_ids))
                delete_graph_rows(conn, stale_ids)
                for offset in range(0, len(stale_ids), 400):
                    chunk = stale_ids[offset : offset + 400]
                    placeholders = ",".join("?" for _ in chunk)
                    _ = conn.execute(
                        f"DELETE FROM wiki_entries WHERE id IN ({placeholders})",  # nosec B608
                        chunk,
                    )
                    _ = conn.execute(
                        f"DELETE FROM wiki_access_log WHERE entry_id IN ({placeholders})",  # nosec B608
                        chunk,
                    )
            desired_mirror_keys = {(category, title) for title, _body, _tags, category in documents.values()}
            mirrors_to_remove: list[tuple[str, str]] = []
            for mirror_key in sorted(obsolete_mirror_keys - desired_mirror_keys):
                remaining_mirror = conn.execute(
                    "SELECT 1 FROM wiki_entries WHERE category = ? AND title = ? LIMIT 1",
                    mirror_key,
                ).fetchone()
                if remaining_mirror is None:
                    mirrors_to_remove.append(mirror_key)
            if reward_events:
                advance_reward_ticks(conn, tuple(reward_events))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

        for category, title in mirrors_to_remove:
            if re.fullmatch(r"[\w-]{1,64}", category) is None:
                logger.warning("Skipping removal of an unsafe Wiki Markdown mirror category: %r", category)
                continue
            safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:80]
            try:
                (WIKI_DIR / category / f"{safe_title}.md").unlink(missing_ok=True)
            except OSError:
                logger.exception("Wiki Markdown mirror removal failed after the database transaction committed")
        try:
            for relative_path, (title, body, tags, category) in documents.items():
                self._save_markdown(path_to_id[relative_path], title, body, category, list(tags))
        except OSError:
            logger.exception("Wiki Markdown mirror write failed after the database transaction committed")
        logger.info("Obsidian 임포트 완료: %s개 항목", len(documents))
        return len(documents)

    # ─── 웹 검색 결과 저장 ────────────────────────────────────────

    def save_web_search(
        self,
        query: str,
        results: list[dict[str, object]],
        auto_tag: bool = True,
    ) -> int:
        """웹 검색 결과를 위키에 저장합니다.

        Args:
            query: 검색 쿼리
            results: 검색 결과 리스트 [{"title":..., "snippet":..., "url":...}]
            auto_tag: 자동 태깅 여부

        Returns:
            저장된 항목 ID

        """
        # 검색 결과를 하나의 위키 항목으로 통합
        content_parts = [
            f"## 웹 검색: {query}\n",
            f"_검색 일시: {datetime.now(UTC).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M')}_\n",
        ]

        for i, r in enumerate(results[:8], 1):
            content_parts.append(
                f"### {i}. {r.get('title', '')}\n{r.get('snippet', '')}\n🔗 [{r.get('url', '')}]({r.get('url', '')})\n",
            )

        content = "\n".join(content_parts)
        tags = ["web-search", query.split()[0]] if auto_tag else ["web-search"]

        return self.add_entry(
            title=f"웹검색: {query}",
            content=content,
            category="web",
            tags=tags,
            source="web_search",
        )

    # ─── 통계 ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, object]:
        """위키 통계를 반환합니다."""
        conn = self._connect()
        _ = conn.execute("BEGIN")
        total_row = cast(sqlite3.Row | None, conn.execute("SELECT COUNT(*) FROM wiki_entries").fetchone())

        total = cast(int, total_row[0]) if total_row is not None else 0

        by_category: dict[str, int] = {}
        for row in cast(
            list[sqlite3.Row],
            conn.execute(
                "SELECT category, COUNT(*) as cnt FROM wiki_entries GROUP BY category",
            ).fetchall(),
        ):
            by_category[cast(str, row["category"])] = cast(int, row["cnt"])

        by_source: dict[str, int] = {}
        for row in cast(
            list[sqlite3.Row],
            conn.execute("SELECT source, COUNT(*) as cnt FROM wiki_entries GROUP BY source").fetchall(),
        ):
            by_source[cast(str, row["source"])] = cast(int, row["cnt"])

        recent: list[dict[str, object]] = []
        for row in cast(
            list[sqlite3.Row],
            conn.execute(
                "SELECT id, title, updated_at FROM wiki_entries ORDER BY updated_at DESC LIMIT 5",
            ).fetchall(),
        ):
            recent.append(
                {
                    "id": cast(int, row["id"]),
                    "title": cast(str, row["title"]),
                    "updated_at": cast(str, row["updated_at"]),
                },
            )

        most_accessed: list[dict[str, object]] = []
        for row in cast(
            list[sqlite3.Row],
            conn.execute(
                "SELECT id, title, access_count FROM wiki_entries ORDER BY access_count DESC LIMIT 5",
            ).fetchall(),
        ):
            most_accessed.append(
                {"id": cast(int, row["id"]), "title": cast(str, row["title"]), "count": cast(int, row["access_count"])},
            )

        conn.close()

        return {
            "total_entries": total,
            "by_category": by_category,
            "by_source": by_source,
            "recent_entries": recent,
            "most_accessed": most_accessed,
        }

    def clear_all(self) -> int:
        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            entries = cast(list[sqlite3.Row], conn.execute("SELECT id, category, title FROM wiki_entries").fetchall())
            ids = tuple(int(row["id"]) for row in entries)
            prepare_graph_deletion(conn, ids)
            _ = conn.execute("DELETE FROM wiki_access_log")
            delete_graph_rows(conn, ids)
            _ = conn.execute("DELETE FROM wiki_links")
            _ = conn.execute("DELETE FROM wiki_entries")
            _ = conn.execute("DELETE FROM wiki_node_rewards")
            _ = conn.execute("DELETE FROM wiki_link_rewards")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

        for entry in entries:
            category = cast(str, entry["category"])
            if re.fullmatch(r"[\w-]{1,64}", category) is None:
                logger.warning("Skipping removal of an unsafe Wiki Markdown mirror category: %r", category)
                continue
            mirror_path = self._safe_mirror_path(category, cast(str, entry["title"]))
            mirror_path.unlink(missing_ok=True)
        return len(entries)

    def export_all(self) -> list[dict[str, object]]:
        conn = self._connect()
        rows = [
            dict(row)
            for row in cast(
                list[sqlite3.Row], conn.execute("SELECT * FROM wiki_entries ORDER BY created_at").fetchall()
            )
        ]
        conn.close()
        return rows

    def redact_all(self) -> int:
        from antigravity_k.engine.secret_scanner import redact_full

        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            rows = cast(list[sqlite3.Row], conn.execute("SELECT * FROM wiki_entries").fetchall())
        except BaseException:
            conn.rollback()
            conn.close()
            raise
        changed = 0
        changed_ids: list[int] = []
        try:
            for row in rows:
                old_title = cast(str, row["title"])
                values = {
                    "title": redact_full(cast(str, row["title"])),
                    "content": redact_full(cast(str, row["content"])),
                    "tags": redact_full(cast(str, row["tags"] or "")),
                    "source_url": redact_full(cast(str, row["source_url"] or "")),
                }
                if any(values[key] != (cast(str, row[key]) or "") for key in values):
                    _ = conn.execute(
                        "UPDATE wiki_entries SET title = ?, content = ?, tags = ?, source_url = ?, updated_at = ? WHERE id = ?",
                        (
                            values["title"],
                            values["content"],
                            values["tags"],
                            values["source_url"],
                            datetime.now(UTC).replace(tzinfo=None).isoformat(),
                            cast(int, row["id"]),
                        ),
                    )
                    try:
                        parsed_tags = cast(object, json.loads(values["tags"] or "[]"))
                        tags = [str(tag) for tag in cast(list[object], parsed_tags)]
                    except json.JSONDecodeError:
                        tags = []
                    category = cast(str, row["category"])
                    self._save_markdown(cast(int, row["id"]), values["title"], values["content"], category, tags)
                    old_file = self._safe_mirror_path(category, old_title)
                    new_file = self._safe_mirror_path(category, values["title"])
                    if old_file != new_file:
                        old_file.unlink(missing_ok=True)
                    changed += 1
                    changed_ids.append(cast(int, row["id"]))
            for entry_id in changed_ids:
                advance_reward_tick(conn, node_id=entry_id)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        return changed

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        from datetime import timedelta

        cutoff = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=max_age_days)).isoformat()
        conn = self._connect()
        try:
            _ = conn.execute("BEGIN IMMEDIATE")
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    "SELECT id, category, title FROM wiki_entries WHERE created_at < ?",
                    (cutoff,),
                ).fetchall(),
            )
            deleted_ids = tuple(int(row["id"]) for row in rows)
            prepare_graph_deletion(conn, deleted_ids)
            delete_graph_rows(conn, deleted_ids)
            for offset in range(0, len(deleted_ids), 400):
                chunk = deleted_ids[offset : offset + 400]
                placeholders = ",".join("?" for _ in chunk)
                _ = conn.execute(
                    f"DELETE FROM wiki_entries WHERE id IN ({placeholders})",  # nosec B608
                    chunk,
                )
                _ = conn.execute(
                    f"DELETE FROM wiki_access_log WHERE entry_id IN ({placeholders})",  # nosec B608
                    chunk,
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        for row in rows:
            category = cast(str, row["category"])
            if re.fullmatch(r"[\w-]{1,64}", category) is None:
                logger.warning("Skipping removal of an unsafe Wiki Markdown mirror category: %r", category)
                continue
            self._safe_mirror_path(category, cast(str, row["title"])).unlink(missing_ok=True)
        return len(rows)

    # ─── 내부 유틸 ───────────────────────────────────────────────

    def _safe_mirror_path(self, category: str, title: str) -> Path:
        if re.fullmatch(r"[\w-]{1,64}", category) is None:
            raise ValueError("Wiki Markdown category must be a safe path component")
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:80]
        return WIKI_DIR / category / f"{safe_title}.md"

    def _row_to_entry(self, row: sqlite3.Row) -> WikiEntry:
        raw_tags = cast(str, row["tags"] or "[]")
        parsed_tags = cast(object, json.loads(raw_tags))
        tags = [str(tag) for tag in cast(list[object], parsed_tags)]
        return WikiEntry(
            id=cast(int, row["id"]),
            title=cast(str, row["title"]),
            content=cast(str, row["content"]),
            category=cast(str, row["category"]),
            tags=tags,
            source=cast(str, row["source"]),
            source_url=cast(str, row["source_url"]),
            created_at=cast(str, row["created_at"]),
            updated_at=cast(str, row["updated_at"]),
            access_count=cast(int, row["access_count"]),
        )

    def _prepare_fts_query(self, query: str) -> str:
        """FTS5 쿼리 문법으로 변환."""
        # 특수문자 제거 + 단어별 OR 검색
        words = re.findall(r"[\w가-힣]+", query)
        if not words:
            return ""
        return " OR ".join(words)

    def _log_access(self, conn: sqlite3.Connection, entry_id: int, query: str) -> None:
        """접근 이력 기록."""
        _ = conn.execute(
            "UPDATE wiki_entries SET access_count = access_count + 1 WHERE id = ?",
            (entry_id,),
        )
        _ = conn.execute(
            "INSERT INTO wiki_access_log (entry_id, query, accessed_at) VALUES (?, ?, ?)",
            (entry_id, query, datetime.now(UTC).replace(tzinfo=None).isoformat()),
        )

    def _save_markdown(
        self,
        entry_id: int | None,
        title: str,
        content: str,
        category: str,
        tags: list[str],
    ) -> None:
        """위키 항목을 Markdown 파일로도 저장 (Obsidian 호환)."""
        if re.fullmatch(r"[\w-]{1,64}", category) is None:
            raise ValueError("Wiki Markdown category must be a safe path component")
        md_file = self._safe_mirror_path(category, title)
        md_file.parent.mkdir(parents=True, exist_ok=True)

        frontmatter = (
            f"---\n"
            f"id: {entry_id}\n"
            f"category: {category}\n"
            f"tags: {json.dumps(tags, ensure_ascii=False)}\n"
            f"created: {datetime.now(UTC).replace(tzinfo=None).isoformat()}\n"
            f"---\n\n"
        )
        _ = md_file.write_text(frontmatter + content, encoding="utf-8")


# ─── CLI 테스트 ──────────────────────────────────────────────────

if __name__ == "__main__":
    wiki = LLMWiki()

    # 테스트 항목 추가
    _ = wiki.add_entry(
        "FastAPI 비동기 패턴",
        "FastAPI는 Starlette 기반의 ASGI 프레임워크로...",
        category="code",
        tags=["python", "fastapi", "async"],
    )

    # 검색
    hits = wiki.search("fastapi")
    for hit in hits:
        print(f"[{hit.score:.2f}] {hit.entry.title}")

    # 통계
    print(json.dumps(wiki.get_stats(), indent=2, ensure_ascii=False))
