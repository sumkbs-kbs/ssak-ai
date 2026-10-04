from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from antigravity_k.knowledge.obsidian_links import (
    ObsidianLink,
    ObsidianLinkPlan,
    ObsidianRelation,
    ObsidianVaultPlan,
    UnresolvedObsidianLink,
    build_obsidian_link_plan,
    expand_linked_entry_ids,
    extract_frontmatter_aliases,
    parse_obsidian_links,
    parse_obsidian_note,
    plan_obsidian_vault,
    resolve_obsidian_target,
)


def test_parses_plain_path_heading_alias_and_embed_links() -> None:
    markdown = (
        "[[Overview]] and [[folder/Design Note#Trade-offs|design choices]]; "
        "![[assets/diagram.png]]; [[#Local heading]]."
    )

    assert parse_obsidian_links(markdown) == (
        ObsidianLink(target="Overview"),
        ObsidianLink(target="folder/Design Note", heading="Trade-offs", alias="design choices"),
        ObsidianLink(target="assets/diagram.png", embedded=True),
        ObsidianLink(target="", heading="Local heading"),
    )


def test_ignores_wikilinks_inside_fenced_and_inline_code() -> None:
    markdown = """Visible [[Actual]].

```python
ref = "[[Fenced]]"
```

~~~markdown
[[Also fenced]]
~~~

Inline `[[Inline]]` and `` `[[Double inline]]` `` stay literal.
"""

    assert parse_obsidian_links(markdown) == (ObsidianLink(target="Actual"),)


def test_ignores_escaped_wikilinks_and_regular_markdown_links() -> None:
    markdown = r"\[[Escaped]] and [label](Target.md) and [[Real]]."

    assert parse_obsidian_links(markdown) == (ObsidianLink(target="Real"),)


def test_malformed_or_nested_wikilinks_do_not_create_partial_links() -> None:
    markdown = "[[unterminated and [[outer [[inner]] tail]]"

    assert parse_obsidian_links(markdown) == ()


def test_preserves_order_and_duplicate_occurrences_for_caller_to_deduplicate() -> None:
    markdown = "[[B]] then [[A]] then [[B|alias]]."

    assert parse_obsidian_links(markdown) == (
        ObsidianLink(target="B"),
        ObsidianLink(target="A"),
        ObsidianLink(target="B", alias="alias"),
    )


def test_extracts_yaml_frontmatter_aliases_safely_and_deduplicates() -> None:
    markdown = (
        "---\n"
        "aliases:\n"
        "  - Design Notes\n"
        '  - "design notes"\n'
        "alias: Blueprint\n"
        "ignored: 7\n"
        "---\n"
        "Body [[Design Notes]].\n"
    )

    assert extract_frontmatter_aliases(markdown) == ("Design Notes", "Blueprint")


def test_parses_note_frontmatter_body_category_tags_and_safe_fallbacks() -> None:
    assert parse_obsidian_note("---\ncategory: research\ntags: [one, two]\n---\n\nBody [[X]].") == (
        "Body [[X]].",
        "research",
        ("one", "two"),
    )
    assert parse_obsidian_note("No frontmatter") == ("No frontmatter", "note", ())
    assert parse_obsidian_note("---\ncategory: [not, scalar]\ntags: [1, null]\n---\nBody") == (
        "Body",
        "note",
        (),
    )


def test_ignores_missing_invalid_or_non_mapping_frontmatter() -> None:
    assert extract_frontmatter_aliases("No frontmatter\naliases: [x]") == ()
    assert extract_frontmatter_aliases("---\naliases: [unterminated\n---\nBody") == ()
    assert extract_frontmatter_aliases("---\n- a\n- b\n---\nBody") == ()
    assert extract_frontmatter_aliases("---\naliases: [1, null, true]\n---\nBody") == ()


def test_resolves_explicit_paths_and_prefers_a_unique_local_title(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = (
        "Projects/Source.md",
        "Projects/Design.md",
        "Archive/Design.md",
    )

    assert (
        resolve_obsidian_target(
            ObsidianLink("Projects/Design.md", heading="Details"),
            vault_root=vault,
            source_path="Projects/Source.md",
            markdown_paths=notes,
        )
        == "Projects/Design.md"
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink("Design"),
            vault_root=vault,
            source_path="Projects/Source.md",
            markdown_paths=notes,
        )
        == "Projects/Design.md"
    )


def test_ambiguous_titles_and_aliases_are_not_guessed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = ("Source.md", "AreaA/Decision.md", "AreaB/Decision.md", "AreaC/Plan.md", "AreaD/Plan.md")
    aliases: Mapping[str, tuple[str, ...]] = {
        "AreaC/Plan.md": ("Roadmap",),
        "AreaD/Plan.md": ("Roadmap",),
    }

    assert (
        resolve_obsidian_target(
            ObsidianLink("Decision"), vault_root=vault, source_path="Source.md", markdown_paths=notes
        )
        is None
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink("Roadmap"),
            vault_root=vault,
            source_path="Source.md",
            markdown_paths=notes,
            aliases=aliases,
        )
        is None
    )


def test_resolves_a_unique_frontmatter_alias_and_local_alias_preference(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = ("Projects/Source.md", "Projects/Design.md", "Archive/Plan.md")
    aliases = {
        "Projects/Design.md": ("Blueprint",),
        "Archive/Plan.md": ("Blueprint",),
    }

    assert (
        resolve_obsidian_target(
            ObsidianLink("Blueprint"),
            vault_root=vault,
            source_path="Projects/Source.md",
            markdown_paths=notes,
            aliases=aliases,
        )
        == "Projects/Design.md"
    )


def test_frontmatter_aliases_flow_from_parser_into_link_resolution(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    source_markdown = "See [[Blueprint#Architecture|the plan]]."
    target_markdown = "---\naliases: [Blueprint]\n---\nDesign note."
    link = parse_obsidian_links(source_markdown)[0]
    aliases = extract_frontmatter_aliases(target_markdown)

    assert (
        resolve_obsidian_target(
            link,
            vault_root=vault,
            source_path="Projects/Source.md",
            markdown_paths=("Projects/Source.md", "Plans/Architecture.md"),
            aliases={"Plans/Architecture.md": aliases},
        )
        == "Plans/Architecture.md"
    )


def test_resolves_source_relative_paths_and_extensionless_markdown_paths(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = ("Projects/Source.md", "Archive/Design.md", "Archive/Other.md")

    assert (
        resolve_obsidian_target(
            ObsidianLink("../Archive/Design"),
            vault_root=vault,
            source_path="Projects/Source.md",
            markdown_paths=notes,
        )
        == "Archive/Design.md"
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink("./Other.md"),
            vault_root=vault,
            source_path="Archive/Design.md",
            markdown_paths=notes,
        )
        == "Archive/Other.md"
    )


def test_accepts_absolute_inventory_paths_inside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    source = vault / "Source.md"
    target = vault / "Target.md"

    assert (
        resolve_obsidian_target(
            ObsidianLink("Target"),
            vault_root=vault,
            source_path=source,
            markdown_paths=(source, target),
        )
        == "Target.md"
    )


def test_heading_only_link_resolves_to_source_note(tmp_path: Path) -> None:
    assert (
        resolve_obsidian_target(
            ObsidianLink("", heading="Details"),
            vault_root=tmp_path / "vault",
            source_path="Folder/Source.md",
            markdown_paths=("Folder/Source.md",),
        )
        == "Folder/Source.md"
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink(""),
            vault_root=tmp_path / "vault",
            source_path="Folder/Source.md",
            markdown_paths=("Folder/Source.md",),
        )
        is None
    )


def test_rejects_missing_absolute_traversal_and_non_markdown_targets(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = ("Source.md", "Target.md", "assets/image.png")
    for target in ("Missing", "../secret.md", str(tmp_path / "outside.md"), r"Folder\\Target.md", "assets/image.png"):
        assert (
            resolve_obsidian_target(
                ObsidianLink(target),
                vault_root=vault,
                source_path="Source.md",
                markdown_paths=notes,
            )
            is None
        )


def test_rejects_source_or_alias_paths_outside_the_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = ("Source.md", "Target.md")

    assert (
        resolve_obsidian_target(
            ObsidianLink("Target"),
            vault_root=vault,
            source_path=tmp_path / "outside.md",
            markdown_paths=notes,
        )
        is None
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink("OutsideAlias"),
            vault_root=vault,
            source_path="Source.md",
            markdown_paths=notes,
            aliases={str(tmp_path / "outside.md"): ("OutsideAlias",)},
        )
        is None
    )


def test_rejects_symlink_paths_that_escape_the_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    (outside / "Secret.md").write_text("not in the vault", encoding="utf-8")
    (vault / "jump.md").symlink_to(outside / "Secret.md")

    assert (
        resolve_obsidian_target(
            ObsidianLink("jump"),
            vault_root=vault,
            source_path="Source.md",
            markdown_paths=("Source.md", "jump.md"),
        )
        is None
    )


def test_builds_a_directed_link_plan_for_forward_references_deterministically(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    documents = {
        "A.md": "[[B]] and [[B|second mention]] and [[Missing]].",
        "Folder/B.md": "---\naliases: [B]\n---\nTarget.",
        "C.md": "[[B#Heading]].",
    }

    expected = ObsidianLinkPlan(
        relations=(
            ObsidianRelation("A.md", "Folder/B.md"),
            ObsidianRelation("C.md", "Folder/B.md"),
        ),
        unresolved=(UnresolvedObsidianLink("A.md", ObsidianLink("Missing")),),
    )
    assert build_obsidian_link_plan(documents, vault_root=vault) == expected
    assert build_obsidian_link_plan(dict(reversed(tuple(documents.items()))), vault_root=vault) == expected


def test_link_plan_records_unsafe_and_duplicate_sources_as_ignored(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    plan = build_obsidian_link_plan(
        {
            "Source.md": "[[Target]].",
            "Target.md": "Target.",
            "../outside.md": "[[Target]].",
            "Images/image.png": "not markdown",
            str(vault / "Source.md"): "different content at same canonical path",
        },
        vault_root=vault,
    )

    assert plan.relations == ()
    assert plan.unresolved == ()
    assert set(plan.ignored_sources) == {
        "../outside.md",
        "Images/image.png",
        "Source.md",
        str(vault / "Source.md"),
    }


def test_link_plan_does_not_create_self_edges_for_heading_only_links() -> None:
    plan = build_obsidian_link_plan(
        {"Source.md": "[[#Details]]"},
        vault_root=Path("/virtual-vault"),
    )

    assert plan.relations == ()
    assert plan.unresolved == ()


def test_link_plan_reports_ambiguous_bare_target_without_choosing_one() -> None:
    plan = build_obsidian_link_plan(
        {
            "Source.md": "[[Decision]].",
            "AreaA/Decision.md": "A.",
            "AreaB/Decision.md": "B.",
        },
        vault_root=Path("/virtual-vault"),
    )

    assert plan.relations == ()
    assert plan.unresolved == (UnresolvedObsidianLink("Source.md", ObsidianLink("Decision")),)


def test_link_search_expansion_preserves_seed_rank_then_orders_one_hop_neighbors() -> None:
    relations = ((1, 3), (2, 4), (5, 2), (1, 3), (3, 6), (2, 2))

    assert expand_linked_entry_ids(
        (2, 1),
        relations,
        eligible_ids={1, 2, 3, 4, 5, 6},
        limit=10,
    ) == (2, 1, 4, 5, 3)


def test_link_search_expansion_supports_direction_filters() -> None:
    relations = ((1, 2), (3, 1), (2, 4))
    eligible = {1, 2, 3, 4}

    assert expand_linked_entry_ids((1,), relations, eligible_ids=eligible, limit=10, direction="outbound") == (1, 2)
    assert expand_linked_entry_ids((1,), relations, eligible_ids=eligible, limit=10, direction="backlinks") == (1, 3)
    assert expand_linked_entry_ids((1,), relations, eligible_ids=eligible, limit=10, direction="both") == (1, 2, 3)


def test_link_search_expansion_caps_total_results_without_evicting_seeds() -> None:
    assert expand_linked_entry_ids(
        (4, 2, 4),
        ((4, 7), (2, 6), (2, 5)),
        eligible_ids={2, 4, 5, 6, 7},
        limit=3,
    ) == (4, 2, 7)
    assert expand_linked_entry_ids((4, 2), ((4, 7),), eligible_ids={2, 4, 7}, limit=2) == (4, 2)
    assert expand_linked_entry_ids((4,), ((4, 7),), eligible_ids={4, 7}, limit=0) == ()


def test_link_search_expansion_never_adds_ineligible_ids_or_expands_recursively() -> None:
    # `eligible_ids` represents existing rows that already passed category filtering.
    assert expand_linked_entry_ids(
        (1,),
        ((1, 2), (2, 3), (4, 1)),
        eligible_ids={1, 2, 4},
        limit=10,
    ) == (1, 2, 4)
    assert expand_linked_entry_ids((), ((1, 2),), eligible_ids={1, 2}, limit=10) == ()


def test_link_search_expansion_rejects_negative_limits() -> None:
    import pytest

    with pytest.raises(ValueError, match="limit must be non-negative"):
        expand_linked_entry_ids((1,), (), eligible_ids={1}, limit=-1)


def test_scans_vault_read_only_and_skips_hidden_and_symlink_paths(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    (vault / "Notes").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    outside.mkdir()
    source_path = vault / "Source.md"
    target_path = vault / "Notes" / "Target.md"
    hidden_path = vault / ".private.md"
    hidden_config = vault / ".obsidian" / "hidden.md"
    outside_note = outside / "External.md"
    source_path.write_text("See [[Target]].", encoding="utf-8")
    target_path.write_text("---\naliases: [Target]\n---\nTarget body.", encoding="utf-8")
    hidden_path.write_text("[[Missing]].", encoding="utf-8")
    hidden_config.write_text("[[Missing]].", encoding="utf-8")
    outside_note.write_text("outside", encoding="utf-8")
    (vault / "external.md").symlink_to(outside_note)
    (vault / "linked-dir").symlink_to(outside, target_is_directory=True)
    before = {path: path.read_bytes() for path in (source_path, target_path, hidden_path, hidden_config)}

    result = plan_obsidian_vault(vault)

    assert result == ObsidianVaultPlan(
        link_plan=ObsidianLinkPlan(
            relations=(ObsidianRelation("Source.md", "Notes/Target.md"),),
            unresolved=(),
        ),
        scanned_paths=("Notes/Target.md", "Source.md"),
        skipped_paths=(".obsidian", ".private.md", "external.md", "linked-dir"),
        read_errors=(),
        documents=(
            ("Notes/Target.md", "---\naliases: [Target]\n---\nTarget body."),
            ("Source.md", "See [[Target]]."),
        ),
    )
    assert {path: path.read_bytes() for path in before} == before


def test_vault_scan_reports_invalid_utf8_and_keeps_other_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Good.md").write_text("Good note.", encoding="utf-8")
    (vault / "Broken.md").write_bytes(b"invalid: \xff")

    result = plan_obsidian_vault(vault)

    assert result.scanned_paths == ("Good.md",)
    assert result.skipped_paths == ()
    assert result.read_errors == ("Broken.md",)
    assert result.link_plan == ObsidianLinkPlan(relations=(), unresolved=())


def test_vault_scan_rejects_missing_roots_and_non_directories(tmp_path: Path) -> None:
    import pytest

    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="not accessible"):
        plan_obsidian_vault(missing)

    file_path = tmp_path / "note.md"
    file_path.write_text("note", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        plan_obsidian_vault(file_path)


def test_path_matching_is_case_insensitive_and_requires_markdown_note(tmp_path: Path) -> None:
    assert (
        resolve_obsidian_target(
            ObsidianLink("folder/design.MD"),
            vault_root=tmp_path / "vault",
            source_path="folder/Source.md",
            markdown_paths=("folder/Source.md", "Folder/Design.md"),
        )
        == "Folder/Design.md"
    )
    assert (
        resolve_obsidian_target(
            ObsidianLink("folder/image.png"),
            vault_root=tmp_path / "vault",
            source_path="folder/Source.md",
            markdown_paths=("folder/Source.md", "folder/image.png"),
        )
        is None
    )
