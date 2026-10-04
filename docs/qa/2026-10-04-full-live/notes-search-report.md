---
title: Optional RAG notes search regression and runtime evidence
date: 2026-10-04
tags: [qa, vault, keyword-search, optional-rag]
---

Candidate HEAD: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382.

Ownership: `src/antigravity_k/api/routes/vault_api.py::search_notes`, new
`tests/test_vault_keyword_search_api.py`, and this report plus `notes-search-*`
verification logs. Other agents own palette, WikiPage, auth, and the full API driver.

Before creating diagnostic artifacts: each regression child uses an auto-cleaned
`TemporaryDirectory(prefix="ssak-notes-search-")`, patches `Path.home` and cwd,
and sets explicit AGK task/data/project/auth/cache paths before all project imports.
HOME and CODEX_HOME are preserved. No live models, credentials, user vault data,
Git mutations in the shared checkout, or debugger instrumentation are allowed.

Hypotheses:
1. Disabled optional RAG leaves no vector_store, but the HTTP route accesses it
   before keyword search. Distinguish via actual `sync_rag=False` object and HTTP500.
2. The keyword matcher fails to find a real note. Distinguish with an actual
   YAML-frontmatter note written through the real Git-first VaultEngine.
3. A wrong dependency/root is used. Distinguish by returning only the seeded
   relative path from the isolated Vault root; no route or engine stubs.

Discovery: graph-first search initially found no project. Required fast indexing
completed (persistence=false); relevant search returned no symbols at first, then
VectorStore symbols became available. Subsequent snippet lookup again reported
the project missing. Bounded exact-file reads were used only after these results.

Execution plan:
1. Reproduce the route's disabled-RAG failure with real Vault notes (completed).
2. Guard only the optional semantic call and rerun focused contracts (completed).
3. Run related regression/static checks and actual socket HTTP QA (completed).

RED: `python -m pytest tests/test_vault_keyword_search_api.py -q --noconftest`
produced **4 failed, 1 passed in 11.22s**. Four nonempty-query requests returned
`Internal Server Error`; the empty query retained HTTP400. The real direct keyword
search assertion passed before each HTTP request, refuting matcher/root hypotheses.
Raw synthetic failure evidence: `notes-search-red.log`.

Production change: guard only `engine.vector_store.search` with existing
`engine.sync_rag`; return the existing empty semantic list when RAG is disabled.
The real keyword walk, audit, dependency, auth/scope and response keys are unchanged.

Final focused GREEN: **5 passed in 32.01s**, `notes-search-green.log` (same
missing vector-store fixture, case-insensitive text, Unicode text, miss, empty query).
Related existing `tests/test_vault.py::test_search_notes`: **1 passed in 0.75s**,
`notes-search-related.log`, run with the before-import isolation context and no
conftest. The old API fixture injects a vector-store mock into its RAG-off engine,
so it cannot detect the missing-attribute regression addressed here.

Static checks on both owned code files: Ruff check/format and no-excuse audit exit0;
basedpyright **0 errors, 0 warnings, 0 notes**; LSP error diagnostics empty for both.
Logs: `notes-search-lint.log`, `notes-search-format.log`, `notes-search-audit.log`,
`notes-search-typecheck.log`. Pure LOC: route201 (existing module warning band),
new regression100; no broad refactor, casts, Any, ignores, or error swallowing added.
The `_SearchClient` protocol preserves the installed TestClient/HTTP response
contract despite incomplete framework type stubs; it does not substitute runtime
results. New comments are required executable metadata, BDD blocks, and the
before-import state isolation contract.

Manual API QA command:
`.venv/bin/python docs/qa/2026-10-04-full-live/manual_api_driver.py check --output docs/qa/2026-10-04-full-live/notes-search-http.json`

Actual authenticated production request with the real isolated Vault:
`GET /v1/notes/search?q=QA_SEED_TEXT` → HTTP200, `keyword_results=['seed.md']`.
The subprocess server exits and removes its temporary 0600 token header. Synthetic
evidence: `notes-search-http.json` and `notes-search-http.log`. The overall driver
run was43/45; the two other discrepancies (toolset ordering and null-extraction
fixture/catalog shape) were handed to the driver owner, and are not claimed as
passing coverage here. Root will personally rerun the final stabilized catalog.

Independent final read-only review from `notes_search_review`: **CLEAR / APPROVE**,
no blockers, final route/test files plus RED/GREEN and authenticated HTTP receipt.
Reviewer did not execute tests or type checking; those checks were run by this
implementation worker. No reviewer file edits or Git commands. Review is bound to
the full HEAD above and these final source SHA256 values:

| File | SHA256 |
| --- | --- |
| src/antigravity_k/api/routes/vault_api.py | 54bc1e8527adb8dc5e98e6041ca412fab857edc2f37b1ba7a63915f49c92fa7a |
| tests/test_vault_keyword_search_api.py | 7adcf5f9714ea167041cc9edb1f30d9aaeb537f8268656275aebbf26a5260576 |

Scope limits: actual Chroma/embedding semantic retrieval was not invoked; enabled
RAG behavior remains its existing path. The temporary mini-app regression validates
the real router and Vault, while the manual socket driver supplies the production
middleware and authentication proof. No user Vault, private state, live model, shared
Git state, raw application logs, real credentials or debug instrumentation were read or changed.
