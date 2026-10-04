---
title: Hindsight-inspired bounded memory recall evidence
date: 2026-10-03
tags: [qa, memory, recall, budget, provider]
---

# Bounded memory recall

## Candidate sources

- `src/antigravity_k/engine/memory_provider.py`: `a8b7c35beda61162a54f9c7f124c2d638605aa1f601b644802fd21efcc0e6001`
- `src/antigravity_k/engine/memory_recall_budget.py`: `033d7a8d44aacd7554e0ca9a1815179f3e0f9a002d186f8d7bd66b6783688c99`
- `tests/test_memory_recall_budget.py`: `50a4c30d3de8cb9ebd52a575536af4593886a7e19acd1547b2a3ad5fa5e7e2d6`

## Scenarios

| Scenario | Invocation | Binary observable | Captured artifact |
| --- | --- | --- | --- |
| New behavior is unimplemented | `.venv/bin/python -m pytest tests/test_memory_recall_budget.py -q` before adding the module | Collection fails with `ModuleNotFoundError: antigravity_k.engine.memory_recall_budget` | `memory-recall-budget-red.log` |
| Exact cross-provider duplicate suppression | `test_bounded_recall_deduplicates_exact_cross_provider_fragments` | Two equal complete fragments compose to one `shared recall` context | `memory-recall-budget-green.log` |
| Oversized optional fragment backfill | `test_bounded_recall_skips_oversized_fragment_and_backfills_later_fragment` | The 80-character first fragment is omitted; the later 22-character fragment remains and output length is at most 30 | `memory-recall-budget-green.log` |
| Explicit zero and positive budget | `test_bounded_recall_respects_zero_and_positive_character_budgets` | Zero returns an empty context; 12 preserves the complete 12-character fragment | `memory-recall-budget-green.log` |
| Strict conflict prefix budget | `test_bounded_recall_omits_conflict_prefix_that_exceeds_positive_budget` | A conflicting resolver prefix cannot escape a one-character positive budget; the typed result is an empty context | `.omo/evidence/2026-10-03-memory-recall-budget/strict-budget-red.log`, `.omo/evidence/2026-10-03-memory-recall-budget/strict-budget-green.log` |
| Complete fact prefix when it fits | `test_bounded_recall_preserves_complete_conflict_winner_when_prefix_fits` | Current-user identity winner and provenance remain whole under a 500-character budget | `.omo/evidence/2026-10-03-memory-recall-budget/strict-budget-green.log` |
| Default manager legacy boundary | `test_default_manager_deduplicates_and_backfills_after_oversized_fragment` | No-argument manager stays within 12,000 characters, removes exact duplicates, and keeps the later fitting fragment; preserved baseline returned 12,056 characters with two duplicates | `.omo/evidence/2026-10-03-memory-recall-budget/default-manager-baseline.log` |
| Real episodic integration | `test_manager_deduplicates_real_episodic_recall_against_another_provider` | A temp persisted `EpisodicMemoryProvider` and a second provider return one complete episodic header and answer | `memory-recall-budget-green.log` |
| Canonical project fact and header safety | `test_manager_budget_keeps_current_project_fact_winner_without_orphaned_headers` | Oversized optional content is absent; `ui_framework=svelte` resolves to canonical `frontend`, shows the current-user provenance, hides `react`, and leaves no `[Project Memory]` orphan header | `memory-recall-budget-green.log` |

## Regression and static checks

- `.venv/bin/python -m pytest tests/test_memory_recall_budget.py tests/test_memory_conflicts.py tests/test_preference_memory.py tests/test_project_memory.py tests/test_project_memory_aliases.py tests/test_global_memory_provider.py -q` completed with `90 passed in 2.01s`: `.omo/evidence/2026-10-03-memory-recall-budget/final-regression.log`.
- `.venv/bin/ruff check src/antigravity_k/engine/memory_recall_budget.py src/antigravity_k/engine/memory_provider.py tests/test_memory_recall_budget.py` completed with `All checks passed!`: `.omo/evidence/2026-10-03-memory-recall-budget/final-ruff.log`.
- `.venv/bin/python -m basedpyright --level error src/antigravity_k/engine/memory_recall_budget.py src/antigravity_k/engine/memory_provider.py tests/test_memory_recall_budget.py` completed with `0 errors, 0 warnings, 0 notes`: `.omo/evidence/2026-10-03-memory-recall-budget/final-basedpyright.log`.
- `git diff --check -- src/antigravity_k/engine/memory_provider.py src/antigravity_k/engine/memory_recall_budget.py tests/test_memory_recall_budget.py` produced no output.
