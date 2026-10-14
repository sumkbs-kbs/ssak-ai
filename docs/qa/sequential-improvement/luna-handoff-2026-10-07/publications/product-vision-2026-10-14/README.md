---
title: Product Vision evidence publication
date: 2026-10-14
tags: [qa, publication, partial]
---

This publication preserves the reviewed offline closeout and four actual live cases. The final live case reached HTTP 200 through the authenticated product route and Ollama with byte-identical assistant content. Counts were correct, but markdown fences violated strict JSON acceptance: FAIL_SEMANTIC, overall IMP09 PARTIAL.

Only owned QA files are included. The existing unrelated staged changes remain outside this commit. Generated authentication secrets, derived runtime databases, locks, cache files and local fixture symlinks remain local and are listed as omissions in publication-manifest.json. Original sealed local manifests retain their original hashes; their complete runtime inventories are intentionally larger than the published Git inventory.

The publication manifest records the precise public paths, sizes and SHA-256. It supplements the local evidence manifests without rewriting them.

The first commit attempt was refused after formatting and newline hooks rewrote 557 immutable evidence files. Those hook-only edits were restored byte-for-byte from the already verified staged originals. The pre-commit configuration now excludes raw QA evidence from Python formatting/lint, JSON validation of deliberate malformed fixtures, whitespace/newline rewriting and source-size limits. Current source, publication helpers and normal documentation remain checked; private-key and conflict checks still inspect the evidence. Focused source checks and sealed artifact validators remain the verification for raw snapshots.
