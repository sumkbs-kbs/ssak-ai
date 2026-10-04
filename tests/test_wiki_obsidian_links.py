from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from antigravity_k.engine.vault import VaultEngine
from antigravity_k.knowledge import wiki as wiki_module
from antigravity_k.knowledge import wiki_graph as wiki_graph_module
from antigravity_k.knowledge.wiki import LLMWiki
from antigravity_k.knowledge.wiki_graph import KGBinaryValidator, advance_reward_tick


@pytest.fixture
def isolated_wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LLMWiki:
    mirror_dir = tmp_path / "wiki-mirrors"
    monkeypatch.setattr(wiki_module, "WIKI_DIR", mirror_dir)
    return LLMWiki(db_path=tmp_path / "wiki.db")


def _scalar(wiki: LLMWiki, statement: str, parameters: tuple[object, ...] = ()) -> object:
    connection = wiki._connect()
    try:
        return connection.execute(statement, parameters).fetchone()[0]
    finally:
        connection.close()


def _db_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validator_returns_ok_and_is_read_only(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    _ = wiki.add_entry("Seed", "validator sample", source="manual")
    before_hash = _db_sha256(wiki.db_path)

    result = KGBinaryValidator(wiki.db_path).validate()

    assert result["OK"] is True
    assert result["errors"] == ()
    assert result["integrity_check"] == "ok"
    assert result["foreign_key_violations"] == 0
    assert result["entry_count"] == 1
    assert _db_sha256(wiki.db_path) == before_hash
    assert wiki.validate_knowledge_graph()["OK"] is True


def test_validator_rejects_orphaned_link_even_when_legacy_foreign_keys_were_off(
    isolated_wiki: LLMWiki,
) -> None:
    wiki = isolated_wiki
    connection = sqlite3.connect(wiki.db_path)
    try:
        _ = connection.execute("PRAGMA foreign_keys=OFF")
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (999, 1000, 'obsidian', 'now')",
        )
        connection.commit()
    finally:
        connection.close()

    result = KGBinaryValidator(wiki.db_path).validate()

    assert result["OK"] is False
    assert result["foreign_key_violations"] > 0
    assert "orphan_link_endpoints" in result["errors"]


def test_successful_node_and_link_writes_apply_decay_then_pair_reward(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    vault = Path(wiki.db_path.parent / "vault")
    vault.mkdir()
    (vault / "First.md").write_text("[[Second]]", encoding="utf-8")
    (vault / "Second.md").write_text("beta", encoding="utf-8")

    assert wiki.import_obsidian_vault(str(vault)) == 2

    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == 3
    source_id = int(next(row["id"] for row in wiki.export_all() if row["title"] == "First"))
    target_id = int(next(row["id"] for row in wiki.export_all() if row["title"] == "Second"))
    assert (
        _scalar(wiki, "SELECT score FROM wiki_link_rewards WHERE from_id = ? AND to_id = ?", (source_id, target_id))
        == 1.0
    )
    assert _scalar(wiki, "SELECT score FROM wiki_node_rewards WHERE entry_id = ?", (source_id,)) == pytest.approx(
        0.95**2
    )
    assert _scalar(wiki, "SELECT score FROM wiki_node_rewards WHERE entry_id = ?", (target_id,)) == pytest.approx(0.95)
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_import_is_idempotent_resolves_aliases_and_search_expands_one_hop(
    isolated_wiki: LLMWiki, tmp_path: Path
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    source = vault / "Source.md"
    target = vault / "Target.md"
    source.write_text(
        "---\ncategory: research\ntags: [one, two]\n---\nNeedle begins here.\n\nSee [[Blueprint#Start|plan]].",
        encoding="utf-8",
    )
    target.write_text("---\naliases: [Blueprint]\ncategory: reference\n---\nRelated only detail.", encoding="utf-8")

    assert wiki.import_obsidian_vault(str(vault)) == 2
    entries = {str(row["source_url"]): row for row in wiki.export_all()}
    source_id = int(entries[str(source)]["id"])
    target_id = int(entries[str(target)]["id"])
    first_tick = _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1")
    first_count = int(_scalar(wiki, "SELECT COUNT(*) FROM wiki_links"))

    assert first_count == 1
    assert wiki.import_obsidian_vault(str(vault)) == 2
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == first_tick
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == first_count

    hits = wiki.search("Needle", limit=3)
    assert [hit.entry.id for hit in hits] == [source_id, target_id]
    assert [hit.matched_field for hit in hits] == ["fts", "wiki_link"]
    filtered_hits = wiki.search("Needle", category="research", limit=3)
    assert [hit.entry.id for hit in filtered_hits] == [source_id]
    assert [hit.entry.id for hit in wiki.search("Needle", limit=3, expand_links=False)] == [source_id]
    assert [hit.entry.id for hit in wiki.search("Needle", limit=1)] == [source_id]
    assert wiki.search("Needle", limit=3, link_direction="outbound")[1].entry.id == target_id
    assert [hit.entry.id for hit in wiki.search("Needle", category="reference", limit=3)] == []
    assert [hit.entry.id for hit in wiki.search("Needle", category="research", limit=3)] == [source_id]
    backlinks = wiki.search("Related", limit=3, link_direction="backlinks")
    assert [hit.entry.id for hit in backlinks] == [target_id, source_id]
    context = wiki.search_for_llm("Needle", max_chars=500)
    assert "### Source" in context
    assert "### Target" in context
    assert "연결 문서" in context
    assert len(wiki.search_for_llm("Needle", max_chars=120)) <= 120
    assert wiki.search_for_llm("Needle", max_chars=0) == ""
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_access_log WHERE query = 'Needle'") > 0


def test_reimport_updates_note_removes_stale_relation_and_stale_entry(isolated_wiki: LLMWiki, tmp_path: Path) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    source = vault / "Source.md"
    target = vault / "Target.md"
    source.write_text("[[Target]]", encoding="utf-8")
    target.write_text("Target body", encoding="utf-8")
    _ = wiki.import_obsidian_vault(str(vault))
    original = {str(row["source_url"]): row for row in wiki.export_all()}
    source_id = int(original[str(source)]["id"])
    target_id = int(original[str(target)]["id"])

    source.write_text("Updated source without a link", encoding="utf-8")
    target.unlink()
    assert wiki.import_obsidian_vault(str(vault)) == 1

    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert wiki.get_entry(target_id) is None
    updated = wiki.get_entry(source_id)
    assert updated is not None and "Updated" in updated.content
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_import_does_not_persist_heading_only_self_links(isolated_wiki: LLMWiki, tmp_path: Path) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("[[#Local heading]]", encoding="utf-8")

    assert wiki.import_obsidian_vault(str(vault)) == 1
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_reimport_tracks_moved_note_and_refreshes_relation_endpoint(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    source = vault / "Source.md"
    target = vault / "Target.md"
    source.write_text("[[Target]]", encoding="utf-8")
    target.write_text("Target body", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 2
    initial = {str(row["source_url"]): row for row in wiki.export_all()}
    source_id = int(initial[str(source)]["id"])
    old_target_id = int(initial[str(target)]["id"])

    moved_dir = vault / "Reference"
    moved_dir.mkdir()
    moved_target = moved_dir / "Target.md"
    target.rename(moved_target)
    source.write_text("[[Reference/Target]]", encoding="utf-8")

    assert wiki.import_obsidian_vault(str(vault)) == 2
    updated = {str(row["source_url"]): row for row in wiki.export_all()}
    new_target_id = int(updated[str(moved_target)]["id"])
    assert new_target_id != old_target_id
    assert wiki.get_entry(old_target_id) is None
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 1
    assert (
        _scalar(
            wiki,
            "SELECT COUNT(*) FROM wiki_links WHERE from_id = ? AND to_id = ? AND relation = 'obsidian'",
            (source_id, new_target_id),
        )
        == 1
    )
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_reimport_preserves_entries_under_skipped_symlinked_directory(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    nested = vault / "linked"
    nested.mkdir(parents=True)
    first = nested / "First.md"
    second = nested / "Second.md"
    first.write_text("[[Second]]", encoding="utf-8")
    second.write_text("Second body", encoding="utf-8")
    _ = wiki.import_obsidian_vault(str(vault))
    records = {str(row["source_url"]): row for row in wiki.export_all()}
    first_id = int(records[str(first)]["id"])
    second_id = int(records[str(second)]["id"])

    connection = wiki._connect()
    try:
        _ = connection.execute(
            "UPDATE wiki_entries SET source_url = ? WHERE id = ?",
            (str(first.relative_to(vault)), first_id),
        )
        connection.commit()
    finally:
        connection.close()

    detached = tmp_path / "detached"
    nested.rename(detached)
    nested.symlink_to(detached, target_is_directory=True)
    (vault / "Current.md").write_text("Current note", encoding="utf-8")
    tick_before = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))

    assert wiki.import_obsidian_vault(str(vault)) == 1
    assert wiki.get_entry(first_id) is not None
    assert wiki.get_entry(second_id) is not None
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 1
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_before + 1
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_import_removes_obsolete_markdown_mirror_after_note_metadata_change(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Note.md"
    note.write_text("Original body", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 1
    original_mirror = wiki_module.WIKI_DIR / "note" / "Note.md"
    assert original_mirror.exists()

    note.write_text("---\ncategory: research\n---\nUpdated body", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 1

    assert not original_mirror.exists()
    assert (wiki_module.WIKI_DIR / "research" / "Note.md").exists()
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_vault_privacy_delete_removes_graph_and_applies_reward_ticks(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    source = vault / "Source.md"
    target = vault / "Target.md"
    source.write_text("[[Target]]", encoding="utf-8")
    target.write_text("private content", encoding="utf-8")
    _ = wiki.import_obsidian_vault(str(vault))
    records = {str(row["source_url"]): row for row in wiki.export_all()}
    source_id = int(records[str(source)]["id"])
    target_id = int(records[str(target)]["id"])
    tick_before = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))

    assert wiki.delete_vault_sources((str(target),)) == 1
    assert wiki.get_entry(target_id) is None
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links WHERE from_id = ? OR to_id = ?", (source_id, target_id)) == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_before + 2
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_retention_removes_graph_endpoints_and_rewards_transactionally(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    source = vault / "Source.md"
    target = vault / "Target.md"
    source.write_text("[[Target]]", encoding="utf-8")
    target.write_text("expired target", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 2
    records = {str(row["source_url"]): row for row in wiki.export_all()}
    target_id = int(records[str(target)]["id"])
    connection = wiki._connect()
    try:
        _ = connection.execute(
            "UPDATE wiki_entries SET created_at = '2000-01-01T00:00:00' WHERE id = ?",
            (target_id,),
        )
        connection.commit()
    finally:
        connection.close()
    tick_before = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))

    assert wiki.apply_retention(1) == 1

    assert wiki.get_entry(target_id) is None
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_before + 2
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_link_search_empty_query_does_not_expand_the_graph(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    source = wiki.add_entry("Seed", "source body", source="manual")
    target = wiki.add_entry("Linked", "target body", source="manual")
    connection = wiki._connect()
    try:
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', 'now')",
            (source, target),
        )
        connection.commit()
    finally:
        connection.close()

    assert wiki.search("", limit=5) == []
    assert wiki.search("   ", limit=5) == []
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_access_log") == 0


def test_search_expansion_follows_each_linked_relation_kind_only(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    source = wiki.add_entry("Seed", "unique needle", source="manual")
    target = wiki.add_entry("Linked", "neighbor", source="manual")
    manual_neighbor = wiki.add_entry("Manual relation", "manual neighbor", source="manual")
    _ = wiki.add_entry("Unrelated", "unrelated", source="manual")
    connection = wiki._connect()
    try:
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', 'now')",
            (source, target),
        )
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'related', 'now')",
            (source, manual_neighbor),
        )
        from antigravity_k.knowledge.wiki_graph import advance_reward_tick

        advance_reward_tick(connection, link_pair=(source, target))
        advance_reward_tick(connection, link_pair=(source, manual_neighbor))
        connection.commit()
    finally:
        connection.close()

    results = wiki.search("needle", limit=5)

    assert [hit.entry.id for hit in results] == [source, target]
    assert [hit.matched_field for hit in results] == ["fts", "wiki_link"]


def test_vault_entry_sync_uses_exact_source_and_is_idempotent(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    first_url = "/vault/one/Shared.md"
    second_url = "/vault/two/Shared.md"

    first_id = wiki.sync_vault_entry("Shared", "first contents", "vault", ["one"], first_url)
    _ = wiki.sync_vault_entry("Shared", "second contents", "vault", ["two"], second_url)
    tick_after_insert = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))
    updated_id = wiki.sync_vault_entry("Renamed", "updated contents", "vault", ["new"], first_url)
    tick_after_update = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))
    unchanged_id = wiki.sync_vault_entry("Renamed", "updated contents", "vault", ["new"], first_url)

    entries = {str(entry["source_url"]): entry for entry in wiki.export_all()}
    assert first_id == updated_id == unchanged_id
    assert entries[first_url]["title"] == "Renamed"
    assert entries[first_url]["content"] == "updated contents"
    assert entries[second_url]["content"] == "second contents"
    assert tick_after_update == tick_after_insert + 1
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_after_update
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_vault_sync_uses_path_identity_and_updates_only_changed_sources(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki = isolated_wiki
    monkeypatch.setattr(wiki_module, "LLMWiki", lambda: wiki)
    vault = VaultEngine(str(tmp_path / "vault"), sync_rag=False)

    vault._sync_to_wiki("one/Shared.md", {"title": "Shared", "type": "vault"}, "first contents")
    vault._sync_to_wiki("two/Shared.md", {"title": "Shared", "type": "vault"}, "second contents")
    tick_after_insert = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))
    vault._sync_to_wiki("one/Shared.md", {"title": "Renamed", "type": "vault"}, "updated contents")
    tick_after_update = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))
    vault._sync_to_wiki("one/Shared.md", {"title": "Renamed", "type": "vault"}, "updated contents")

    entries = {str(entry["source_url"]): entry for entry in wiki.export_all()}
    first_url = str(vault.vault_path / "one/Shared.md")
    second_url = str(vault.vault_path / "two/Shared.md")
    assert len(entries) == 2
    assert entries[first_url]["title"] == "Renamed"
    assert entries[first_url]["content"] == "updated contents"
    assert entries[second_url]["title"] == "Shared"
    assert entries[second_url]["content"] == "second contents"
    assert tick_after_update == tick_after_insert + 1
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_after_update
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_restart_keeps_persisted_links_rewards_and_search_results(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Source.md").write_text("[[Target]]", encoding="utf-8")
    (vault / "Target.md").write_text("target body", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 2
    source_id = int(next(row["id"] for row in wiki.export_all() if row["title"] == "Source"))
    target_id = int(next(row["id"] for row in wiki.export_all() if row["title"] == "Target"))
    tick_before = _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1")
    reopened = LLMWiki(db_path=wiki.db_path)
    monkeypatch.setattr(wiki_module, "WIKI_DIR", tmp_path / "wiki-mirrors")

    hits = reopened.search("target", limit=3, link_direction="backlinks")
    assert [hit.entry.id for hit in hits] == [target_id, source_id]
    assert _scalar(reopened, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_before
    assert KGBinaryValidator(reopened.db_path).validate()["OK"] is True


def test_graph_relation_reward_respects_decay_and_pair_cap(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    first = wiki.add_entry("First", "one", source="manual")
    second = wiki.add_entry("Second", "two", source="manual")
    connection = wiki._connect()
    try:
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'related', 'now')",
            (first, second),
        )
        for _tick in range(40):
            advance_reward_tick(connection, link_pair=(first, second))
        connection.commit()
    finally:
        connection.close()

    assert _scalar(wiki, "SELECT score FROM wiki_link_rewards WHERE from_id = ? AND to_id = ?", (first, second)) == 10.0
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_clear_all_removes_graph_data_and_is_idempotent(isolated_wiki: LLMWiki, tmp_path: Path) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "First.md").write_text("[[Second]]", encoding="utf-8")
    (vault / "Second.md").write_text("second", encoding="utf-8")
    assert wiki.import_obsidian_vault(str(vault)) == 2
    tick_before = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))

    assert wiki.clear_all() == 2
    tick_after = _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1")
    assert tick_after == tick_before + 3
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_entries") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_node_rewards") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert wiki.clear_all() == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_after
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_failed_incomplete_scan_does_not_mutate_wiki_db(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Bad.md").write_bytes(b"bad:\xff")
    before_tick = _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1")

    with pytest.raises(OSError, match="scan incomplete"):
        wiki.import_obsidian_vault(str(vault))

    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_entries") == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == before_tick


def test_obsidian_source_path_is_reused_by_vault_sync(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    source_url = "/vault/one/Shared.md"
    target_url = "/vault/one/Target.md"
    source_id = wiki.add_entry("Old title", "old body", source="obsidian", source_url=source_url)
    target_id = wiki.add_entry("Target", "target body", source="obsidian", source_url=target_url)
    connection = wiki._connect()
    try:
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', 'now')",
            (source_id, target_id),
        )
        advance_reward_tick(connection, link_pair=(source_id, target_id))
        connection.commit()
    finally:
        connection.close()

    synced_id = wiki.sync_vault_entry("Shared", "updated body", "vault", [], source_url)
    entries = {str(entry["source_url"]): entry for entry in wiki.export_all()}

    assert synced_id == source_id
    assert len(entries) == 2
    assert entries[source_url]["source"] == "vault"
    assert entries[source_url]["title"] == "Shared"
    assert entries[source_url]["content"] == "updated body"
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links WHERE from_id = ? AND to_id = ?", (source_id, target_id)) == 1
    assert (
        _scalar(
            wiki,
            "SELECT COUNT(*) FROM wiki_link_rewards WHERE from_id = ? AND to_id = ?",
            (source_id, target_id),
        )
        == 1
    )
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_endpoint_delete_cascades_relation_and_reward_with_graph_ticks(isolated_wiki: LLMWiki) -> None:
    wiki = isolated_wiki
    first = wiki.add_entry("First", "first", source="manual")
    second = wiki.add_entry("Second", "second", source="manual")
    connection = wiki._connect()
    try:
        now = "2026-09-26T00:00:00"
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', ?)",
            (first, second, now),
        )
        advance_reward_tick(connection, link_pair=(first, second))
        connection.commit()
    finally:
        connection.close()
    tick_before = int(_scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1"))

    assert wiki.delete_entry(first) is True

    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == tick_before + 2
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_deletes_graph_orphans_when_legacy_foreign_keys_are_disabled(
    isolated_wiki: LLMWiki,
) -> None:
    wiki = isolated_wiki
    first = wiki.add_entry("First", "first", source="manual")
    second = wiki.add_entry("Second", "second", source="manual")
    connection = sqlite3.connect(wiki.db_path)
    try:
        _ = connection.execute("PRAGMA foreign_keys=OFF")
        _ = connection.execute(
            "INSERT INTO wiki_links (from_id, to_id, relation, created_at) VALUES (?, ?, 'obsidian', 'now')",
            (first, second),
        )
        connection.commit()
    finally:
        connection.close()

    assert wiki.delete_entry(first) is True

    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_node_rewards WHERE entry_id = ?", (first,)) == 0
    assert KGBinaryValidator(wiki.db_path).validate()["OK"] is True


def test_import_transaction_rolls_back_all_entries_links_and_rewards(
    isolated_wiki: LLMWiki,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki = isolated_wiki
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text("[[B]]", encoding="utf-8")
    (vault / "B.md").write_text("Body", encoding="utf-8")

    def fail_reward_batch(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise RuntimeError("simulated graph reward failure")

    monkeypatch.setattr(wiki_module, "advance_reward_ticks", fail_reward_batch)
    monkeypatch.setattr(wiki_graph_module, "advance_reward_ticks", fail_reward_batch)
    with pytest.raises(RuntimeError, match="simulated graph reward failure"):
        wiki.import_obsidian_vault(str(vault))

    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_entries") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_links") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_node_rewards") == 0
    assert _scalar(wiki, "SELECT COUNT(*) FROM wiki_link_rewards") == 0
    assert _scalar(wiki, "SELECT tick FROM wiki_graph_state WHERE id = 1") == 0
