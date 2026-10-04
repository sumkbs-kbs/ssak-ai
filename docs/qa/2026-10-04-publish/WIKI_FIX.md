---
title: Vault and Obsidian Wiki Regression Repair
tags: [qa, wiki, vault, obsidian, regression]
date: 2026-10-04
---

# Vault and Obsidian Wiki Regression Repair

## Scope

This repair covers two publish-preflight regressions in the local Wiki library:

1. Two Vault files with the same title were merged because `_sync_to_wiki` selected an entry by title.
2. `delete_vault_sources` skipped entries imported from Obsidian and did not remove their graph rows before deleting the entry.

The change uses the existing `LLMWiki.sync_vault_entry` path-identity API and extends the existing privacy deletion seam to recognize only `vault` and `obsidian` sources. Manual and other sources remain excluded.

## Root-Cause Evidence

| Hypothesis | Observation | Result |
| --- | --- | --- |
| Title is an insufficient Vault identity | `one/Shared.md` and `two/Shared.md` left one entry after the second sync. | Confirmed |
| Imported notes are not classified as Vault-owned | `import_obsidian_vault` stores the target with `source=obsidian`; the deletion query selected only `source=vault`, returning `0`. | Confirmed |
| A matching entry can be removed without graph cleanup | The deletion helper lacked `prepare_graph_deletion` and `delete_graph_rows`; linked entries require those operations before the SQLite entry deletion. | Confirmed from the shared deletion contract in `LLMWiki.delete_entry` and the graph-linked regression scenario. |

## Red Phase

Scenario: run the two original failing regression cases through the isolated pytest launcher.

Invocation:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -B \
  docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q \
  tests/test_wiki_obsidian_links.py::test_vault_privacy_delete_removes_graph_and_applies_reward_ticks \
  tests/test_wiki_obsidian_links.py::test_vault_sync_uses_path_identity_and_updates_only_changed_sources
```

Observed result: `2 failed in 2.16s`. The first case observed delete count `0`; the second observed one entry where two path-distinct entries were expected.

## Fix

- `src/antigravity_k/engine/vault.py`: delegate Vault synchronization to `sync_vault_entry`, whose identity is the source path and which is idempotent for unchanged content.
- `src/antigravity_k/knowledge/wiki_privacy.py`: select exact URLs from `vault` or `obsidian` only, prepare graph reward deletion events, and remove incident graph rows before deleting selected entries.

## Green Phase

Scenario: run all Wiki and Vault privacy regression tests with isolated storage.

Invocation:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -B \
  docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q \
  tests/test_wiki_obsidian_links.py tests/test_wiki_vault_privacy.py
```

Observed result: `24 passed in 0.93s`.

Static checks:

```bash
.venv/bin/ruff check src/antigravity_k/engine/vault.py \
  src/antigravity_k/knowledge/wiki.py \
  src/antigravity_k/knowledge/wiki_privacy.py \
  tests/test_wiki_obsidian_links.py tests/test_wiki_vault_privacy.py
.venv/bin/python -m mypy --ignore-missing-imports --no-strict-optional \
  src/antigravity_k/engine/vault.py src/antigravity_k/knowledge/wiki.py \
  src/antigravity_k/knowledge/wiki_privacy.py
```

Observed results: `All checks passed!`; `Success: no issues found in 3 source files`.

## Library QA

Scenario: a temporary SQLite Wiki and temporary Vault synced two `Shared.md` files from different folders, renamed one, imported an Obsidian target linked by a source note, added a manual entry with the same source URL, then deleted the Obsidian target by its stored resolved path.

Invocation: an inline `.venv/bin/python -B -c` driver using `tempfile.TemporaryDirectory`; no project, user, provider, browser, or localhost storage was used.

Observed result:

```text
shared_entries=2 remaining_entries=4 links_after_delete=0 manual_protected=true
```

This proves the two source paths remain distinct, one update does not overwrite the other, the selected Obsidian entry and its graph link are removed, and the manually authored entry is retained.

## Artifacts

- Durable report: `docs/qa/2026-10-04-publish/WIKI_FIX.md`
- Debugging evidence index: `.omo/evidence/2026-10-04-publish/wiki-regression.md`
- Original pre-fix batch output: `/tmp/ssak-publish-failure-repro-20261004.txt`

No temporary driver or persistent test storage remains.
