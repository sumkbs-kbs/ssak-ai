# Citation source links and table preservation

Parent-supplied base/candidate HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. Evidence covers the current shared working tree. No Git operations were performed.

Root observed the Search ON R2-12 retry after PID 33856 as two bullet pipe rows with `[citation:23316a30b478]`, without a clickable public source link. This worker did not inspect the live model/search response, private task data, logs or auth. The association between that actual ID and its public URL remains pending root/receipt-worker metadata and the next live retest.

## Proven source seams and fix

Ordinary chat emits canonical text as `agk_final_content`; its handler stores only text. ChatMarkdown renders standard Markdown and has no citation ID-to-URL map. `_supported_claim_fallback` returns bullet claims retaining machine citation IDs but no public URL.

A controlled actual production stream reproduced the exact table symptom: a supported Markdown table became two `- | ... | [citation:id]` rows. Citation evaluation treated its uncited column labels as unsupported factual claims, triggering deterministic claim filtering and losing table scaffolding. Evaluation now excludes table headers/delimiters while still checking every data row, including an unsupported-row negative case.

ToolLoop now adds visible ordinary Markdown source links before canonical finalization, using only known IDs and canonical URLs supplied by the current citation records. Missing/invalid URLs remain unresolved; no ID-to-URL reverse guessing is used. Canonical FinalChunk equals persisted task output. Machine citation IDs remain available for evaluation.

Independent read-only review identified a second provenance defect: the source parser chose the first URL anywhere in the citation block, permitting a snippet URL to override the authoritative source URL. A production-shaped fixture reproduced it. Extraction now uses only the explicit `🔗` metadata line after removing untrusted blocks; both an ordinary snippet URL and a spoofed `🔗` inside a snippet are ignored.

Generated source-footer scaffolding is excluded from claim scoring only for known source URLs with matching hostname labels. Forged factual labels and unrelated URL footers remain unsupported claims.

The explicit-search contract implementation was frozen. Its success-output expectation and four existing citation assertions were updated to require the exact supported claim plus the exact known public source link. No frontend, API schema, bridge, Job UI, quality scorer or context behavior was edited.

## Verification

- `citation-source-links-red.txt`: 4 failed / 2 passed; known URL omitted and supported table converted to bullet pipe rows through actual production stream.
- `citation-source-links-provenance-red.txt`: source parser selected a snippet URL; unverified footer labels bypassed claim scoring. Both defects then corrected.
- `citation-source-links-green.txt`: 8 focused cases passed.
- `citation-source-links-regression.txt`: 243 tests passed across new citation tests, search contract, ToolLoop, web search quality, AgentRuntime and request preservation. One existing unawaited MCPToolLoader coroutine warning remains in the AgentRuntime fixture.
- `citation-source-links-types.txt`: 0 errors / 0 warnings / 0 notes for all five changed source/test files.
- Ruff check and format check passed.
- Independent narrow AST-only review confirmed authoritative source metadata selection, known URL/hostname footer checks, canonical flow, and unsupported data-row handling; no remaining finding in this scope.

All production/test imports ran after synthetic Path.home/expanduser, cwd, AGK/config/data/task/vault and environment isolation. HOME/CODEX_HOME values were preserved. Python socket connect was blocked. TaskStateStore databases and evidence were temporary synthetic fixtures. No real provider/model/network requests, private home/SQLite/log/auth reads or Git operations were performed.

Live R2-12 retest remains root-owned and unverified here. The table fix preserves otherwise valid tables; it does not invent a table header for arbitrary malformed model output.

## Final SHA-256

- `src/antigravity_k/engine/tool_loop.py`: `eb018c1d080534d5e9e6b4deb60f8d9c953eace064f2ec9a303e55ee1b6eea17`
- `src/antigravity_k/tools/search_quality_evaluator.py`: `947ee7aee053ef53678605a9730ed7ef9a53ba42e82169281f208eedca4cd911`
- `tests/test_citation_source_links.py`: `d763a161586cd0dd2b6fbdc8e95c865111962dc33f8a78cc410d4d789158d663`
- `tests/test_search_request_contract.py`: `9ae7d0fc5d1a270193f59151c214e6dfcc18e945959d6818f0673fe827db2e67`
- `tests/test_tool_loop.py`: `97d5716803b1d34218149a683a3c0891788882af5a687ea50c1ac73b1cbcefc9`
