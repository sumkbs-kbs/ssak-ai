# Web search answer repair

Status: COMPLETE for the assigned QA09 repair. Two consecutive actual original-prompt, Search-ON Qwen UI runs passed on the frozen final source. Final receipt: `final-two-run-manifest.json`; verification: `final-two-run-verification.txt`. Earlier failures below remain historical evidence and are not substituted for these final passes.

## Scope
- `src/antigravity_k/tools/web_search_tool.py`: constrain one explicitly requested authority to an exact-host site query; reject unrelated/spoofed/malformed URLs before provider quota checks; retain retrieved top snippet; allow more than two results from an explicitly requested host; select relevant paragraphs/code from actual retrieved page text; emit two richer authority records within the observed 6k evidence budget.
- `src/antigravity_k/engine/tool_loop.py`: citation seams only. Correction preserves requested table shape, cites each data row, and removes unsupported extras. Deterministic supported-claim filtering preserves table scaffolding and supported rows. Validation thresholds, URL provenance and conflict checks are unchanged. Concurrent required-tool recovery edits preserved.
- `tests/test_web_search_requested_domain.py`: retrieval regressions (including bounded authority fallback).
- `tests/test_citation_source_links.py`: one table-shape regression.
- `src/antigravity_k/engine/citation_table_contract.py` and `tests/test_citation_table_contract.py`: decimal format constraints, bounded recovery and failure persistence regressions.
- `src/antigravity_k/tools/search_quality_evaluator.py`: accept valid short GFM dividers and retain row citation scope while requiring every sentence fragment to pass independently.
- `tests/test_citation_row_scope.py` and three captured JSON fixtures: sentence scope, syntax/output presentation, bounded feedback, and actual-draft recovery regressions.
- Source hashes: `hashes.txt`. Frontend Markdown destination repair belongs to `markdown_source_links`, not this patch.

## Runtime diagnosis
1. Original real query returned GitHub repositories despite docs.python.org authority request. Exact `site:` query returned official documentation (`provider-probe.txt`).
2. First real authority-fixed replay still lost table (`docs/qa/2026-10-04-sequential-audit/search-authority-fixed.raw.md`). Authorized synthetic task checkpoint captured in `replay-checkpoints.json`: top reader content was navigation, no syntax examples.
3. Actual UI-contract API diagnostic with `agent_mode=true`, `web_search=true`, `new_turn`, `conversation_id`, and revision protocol captured `replay-ui-contract-before.sse`; readable draft is `replay-ui-contract-before.md`. Draft contained uncited syntax row and incorrect universal tuple-hashability side claim. Citation guard appropriately rejected it; source-title fallback erased table.
4. Existing tool loop truncates results above 6,000 characters. Final actual tool output (`live-budgeted-passages.txt`) measures **4,987 characters**, includes four complete parsed official records, and contains literal `[1, 2, 3]` and `(1, 2, 3, 4, 5)` from retrieved tutorial content. Binary assertion receipt: `PASS_COMPLETE_OFFICIAL_SYNTAX_EVIDENCE`.

The exploratory `replay-before.sse` fast-search path and `replay-agent-before.sse` disabled-search path are NOT equivalent QA and do not support success claims.

## Exact validation scenarios
| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Requested hostname, spoof/malformed rejection, unrelated quota rescue, snippet retention, content after navigation, same-authority pages | `.venv/bin/python -m pytest tests/test_web_search_requested_domain.py -q` with HEAD source injected in memory | 5 failures on original implementation | `red-final-tests.txt` |
| Supported table survives removal of unsupported side prose | Owner test with original `_supported_claim_fallback` injected in memory | Table-shape assertion fails | `table-red.txt` |
| Focused regression | `.venv/bin/python -m pytest tests/test_web_search_requested_domain.py tests/test_web_search_candidate_augmentation.py tests/test_citation_source_links.py tests/test_web_search.py tests/test_web_search_quality.py -q` | **141 passed** | `focused-regression.txt` |
| Real retrieval | `WebSearchTool().execute(query='Python list vs tuple difference mutable immutable docs.python.org official documentation')` then parse `citation_sources_from_context` | length <6000; 4 sources; list and tuple syntax in same retrieved source | `live-budgeted-passages.txt` |
| Scoped lint | `.venv/bin/ruff check src/antigravity_k/tools/web_search_tool.py src/antigravity_k/engine/tool_loop.py tests/test_web_search_requested_domain.py tests/test_citation_source_links.py` | 0 errors | `lint.txt` |
| Scoped types | same four paths with `.venv/bin/basedpyright` | 0 errors, 45 legacy/protected-test warnings | `types.txt` |

Wider run including `tests/test_search_request_contract.py tests/test_required_tool_recovery.py` initially had 192 passed / 1 failed (`regression.txt`): the existing no-tool fake supplied only one reply and exhausted after new required-tool recovery. Its owner fixed the fake reply sequence while preserving failed-task/receipt assertions. The full identical wider invocation then passed **193 tests** (`regression-final.txt`). No test was skipped or relaxed by this worker.

Programming no-excuse audit of initial retrieval scope reports 12 pre-existing legacy module violations (object annotations, broad exceptions, module size), none in new helpers/tests (`no-excuse.txt`). Not claimed passed; unrelated legacy module refactor excluded.

## Red toggle reproduction
No disk source mutation:
```sh
.venv/bin/python - <<'PY'
import subprocess
import pytest
import antigravity_k.tools.web_search_tool as module
original = subprocess.check_output(['git', 'show', 'HEAD:src/antigravity_k/tools/web_search_tool.py'], text=True)
exec(compile(original, module.__file__, 'exec'), module.__dict__)
raise SystemExit(pytest.main(['tests/test_web_search_requested_domain.py', '-q']))
PY
```
Table original-method toggle uses AST extraction of `_supported_claim_fallback` from HEAD and invokes the same owner regression; new optional draft parameter ignored to emulate original behavior.

## Limits and outstanding criterion
- Final real Qwen3.8/Ollama UI replay is captured by root in `docs/qa/2026-10-04-sequential-audit/search-final.raw.md` and `search-final.ax.txt`. Direct inspection shows table header plus two list/tuple data rows, supported mutable/immutable facts, list/tuple syntax examples and working docs.python.org links. AX links 195/197 point to FAQ/tutorial. Presentation mismatches: two links instead of one; literal `<br>` inside inline-code syntax cells. No renderer semantics were changed to conceal model formatting.
- Authority routing repair targets the active legacy standard path; opt-in bundled provider is unchanged.
- Single recognized explicitly named domain only; no guessed official URLs or manufactured facts.
- Existing 6k tool evidence limit remains unchanged. Actual sample meets budget; unrelated large outputs retain normal truncation behavior.
- Graph lookup returned project not indexed, so bounded local source fallback was used. No active ulw-loop attempt exists; evidence is retained under `.omo/evidence/`.

## Final actual UI scenario
Invocation: the original QA-09 prompt in production UI, Qwen3.8/Ollama, search enabled, actual isolated server. Root drove browser and captured response-copy raw Markdown and AX tree. Binary observable: AX table rows 177/186 identify list/tuple; links 195/197 resolve to docs.python.org FAQ/tutorial; raw final has the retained 2-row table, not source-title fallback. Artifacts above. No claim that the presentation mismatches are fixed. A prompt-only tweak was intentionally not shipped after the successful replay because valid drafts may bypass revision and the tweak would not reliably fix this generic formatting issue.

## Repeated real failure: task direct_5ea8a86dee3c
The actual query changed to `docs.python.org list vs tuple mutable immutable difference syntax example`. Task DB showed `status=done` with only source titles. Captured actual checkpoints: `repeat-failure-checkpoints.json`; complete source payload: `repeat-failure-evidence.txt`. Evidence was not truncated (4896 chars), but snippet stopwords promoted unrelated input()/divmod code and fixed top-four selection discarded the tutorial. This disproves stability of the earlier successful run.

### Current additional changes
- `_query_topic_words` removes domain/request boilerplate. Paragraph relevance uses query terms rather than all snippet words; code prioritization requires at least two query anchors. Red/green: `relevance-red.txt` / `relevance-green.txt`.
- Preview up to eight already retrieved official candidates through existing bounded reader; promote a relevant code-bearing source before selecting four displayed records. Red proof: `source-selection-red.txt`. Latest actual failing query output: `repeat-query-sources-after.txt`, **5026 chars**, tutorial first with actual `[1, 2, 3]` and `(1, 2, 3, 4, 5)` evidence. No Python facts or URLs are hardcoded.
- New `engine/citation_table_contract.py` recognizes explicit decimal row counts (Korean `2행 표`, English `2-row table` / `table with 2 rows`). Citation post-processing may call correction at most twice for that contract. The second attempt receives the evaluator report. Accepted/recovered output must retain row count and enough supported claims; source-title fallback cannot satisfy it. Failure persists through the existing `citation_validation_failed` status path. Existing citation thresholds and negative tool policy are unchanged.
- New `tests/test_citation_table_contract.py`: original source-title false completion and missing second bounded repair reproduce RED (`structural-red.txt`), GREEN (`structural-green.txt`); production task persistence verifies failed status when the table cannot be recovered. Extra unsupported/fenced/wrong-row-count cases included in final regression.
- Current lint/type artifacts: `repeat-lint.txt`, `repeat-types.txt` (0 errors, existing/protected warnings retained). Full current invocation is the prior wider suite plus `tests/test_citation_table_contract.py tests/test_tool_loop.py`, output `repeat-regression-final.txt`.
- Ownership remains citation-only within tool_loop.py; concurrent negative mutation guard and Ollama continuation work are preserved.

## Final candidate awaiting repeated UI verification
This section supersedes the earlier single-run receipt. Root will restart and repeat the exact original UI prompt twice; success remains pending until those artifacts exist.

Generic presentation checks now require the explicitly requested distinct cited-source URL count and reject accidental `<br>` inside inline code when syntax cells are requested (explicit HTML requests exempt). The correction receives evaluator and presentation feedback on both bounded attempts. Source footer generation skips an existing exact verified Markdown destination, avoiding a duplicate link. No Python answer is manufactured. Valid GFM one/two/three-dash dividers are accepted, and mismatched header/divider column counts rejected. The citation evaluator's divider grammar matches those valid short dividers. Red-before artifacts: `presentation-red.txt`; focused after: `presentation-green.txt`.

Invocation: `.venv/bin/python -m pytest tests/test_web_search_requested_domain.py tests/test_web_search_candidate_augmentation.py tests/test_citation_source_links.py tests/test_web_search.py tests/test_web_search_quality.py tests/test_search_request_contract.py tests/test_required_tool_recovery.py tests/test_citation_table_contract.py tests/test_tool_loop.py -q`. Binary observable: **307 passed**, `repeat-regression-final.txt`. Ruff all seven owned files: `repeat-lint.txt`, all passed. Exact source/test SHA256: `hashes.txt`. This does not establish model/runtime stability; root's two exact UI runs are outstanding.

## Second reopen: real UI task direct_95695a403acc
Root's `search-final-replay-1.raw.md` was a rejected draft still shown as a normal final. Authorized DB reads captured `latest-task_history.json` and `latest-task_checkpoints.json`: actual task **failed** with `citation_validation_failed`, so presentation guard was not bypassed. Evidence had no truncation, but code-first selection still chose unrelated endswith/list-comprehension examples and FAQ navigation. This disproved the prior candidate's runtime completion.

Final additional repair:
- Topic terms exclude the explicitly requested authority's brand words; short stemming matches mutability/mutable in relevance scoring only. Ignore navigation headings for substantive prose selection; preserve the most relevant prose plus adjacent example. Authority response uses two richer 1800-character excerpts in place of four thin excerpts. A source receives example priority only if its code block contains at least two query anchors. Actual same-query output is `latest-definition-sources.txt`: **4614 characters**, tutorial first, both mutable/immutable definitions and literal list/tuple code retained in one official source. Definition/code regression red/green: `definition-red.txt`, `definition-green.txt`.
- Direct local Ollama Qwen3.8 diagnostic (`diagnose_correction.py`, `/api/chat`) generated two real improved answers, captured as `correction-live-1.md` / `correction-live-2.md` with full prompts. Both had supported table rows, clean code, one source, but a bare URL footer was judged unsupported prose. The diagnostic harness then had a metadata-only AttributeError accessing fake context.analysis; generation outputs were already saved. This harness exception is retained in `correction-live.log` and corrected in the script; it was not a model/API failure or a UI pass.
- Proven final recovery defect: after failed citation correction, supported-row filtering still read the original rejected draft rather than the improved correction. It now filters the latest revision and re-applies the exact citation/presentation predicates. Failing-before test `revised-fallback-red.txt`, after `revised-fallback-green.txt`. Captured actual model candidates replay through repaired post-processing: `correction-captured-replay.json`, `failed=false`, 2 rows, clean syntax, one canonical tutorial link. This replay establishes formatter behavior, not end-to-end UI stability.
- If bounded recovery exhausts, existing failed task status is preserved and final `last_output` becomes an explicit `citation_validation_failed` explanation instead of the rejected answer. `failed-final-green.txt` verifies production final replacement and persisted failure.

All actual UI success claims remain pending root's two same-prompt runs on this latest source. No source security or citation overlap thresholds were relaxed.

Final candidate regression: **309 passed in 8.25s**, exact command above (`repeat-regression-final.txt`). Ruff passed (`repeat-lint.txt`). Source/test hashes refreshed in `hashes.txt`; current ToolLoop SHA256 begins `80130c9c3bae`, web-search begins `e927efccaa7c`.

## Third reopen: actual task direct_4f3bb4dc8bfc
Root actual latest run (`search-verified-replay-1.*`) ended with explicit failed answer. This confirms rejected-draft replacement works, but does not fulfill the requested table. Synthetic store captured `verified-task_history.json`, `verified-task_checkpoints.json`, `verified-evidence.txt`. Evidence is 4612 characters and includes complete paired definitions plus literal syntax in the tutorial source. Checkpoints retained only failed final and empty intermediate outputs, so original draft/correction text is unavailable. Root's observed stream had two citation IDs and one displayed link.

Proven format-predicate bug: exact-one displayed link was incorrectly equated with exact-one cited source. `displayed-link-red.txt` reproduces multiple verified citation IDs + one visible URL wrongly rejected. Final contract checks displayed HTTP destinations and available verified destinations; canonical footer generation adds only the requested remaining count. Multiple verified citation IDs are permitted, extra/unknown displayed URLs rejected. No grounding thresholds changed. This is a proven contributing predicate bug, not proof of the unrecorded correction failure's sole cause.

Exact latest evidence direct Qwen diagnostic captured `verified-correction-live-{1,2}.md` with prompts and successful formatter result `verified-correction-live-result.json`. This used an earlier preserved draft because the latest draft was not recorded; it is a diagnostic, not UI pass. Its method-only syntax example motivated generic prompt guidance to prefer a complete construction example over a bare method or error operation.

Latest regression invocation unchanged: **310 passed in 8.27s**, `repeat-regression-final.txt`; Ruff passed. Hashes updated: ToolLoop `00f805923946`, contract `f41c9c80df68`, web-search `e927efccaa7c`. Root's next two exact UI runs remain pending. Earlier recorded type counts pertain to their candidate; latest type check follows separately.

## Latest actual UI verification: first run PASS, second pending
Exact original QA09 prompt, search ON, real Qwen/Ollama, latest source `00f805923946` / `f41c9c80df68`. Root artifacts: `docs/qa/2026-10-04-sequential-audit/search-confirmed-1.raw.md`, `.ax.txt`, `.dom.json`, `.jpg` (see actual saved filename for DOM). Independently read raw final: Markdown header +2data rows, supported mutable/immutable distinction, inline syntax examples without literal HTML breaks, one canonical docs.python.org destination. Root reports DOM3tr/1href and Python AST syntax validation; these are not inferred from a synthetic test.

Independently read isolated tasks.db: `direct_51d8bc89bd2d` **done**, error null. Captured `confirmed-1-task_history.json` / `confirmed-1-task_checkpoints.json`; exact done-task source context is `confirmed-1-evidence.txt` (wrapper4892chars; toolmetadata original4610chars, truncatedfalse). The same snapshot also includes the second task while running; it does not prove its outcome. Two-run acceptance remains pending until the second actual result. Latest basedpyright: 0errors/101warnings (`repeat-types.txt`). Independent reviewer approved displayed-link delta with24focusedtests+6boundaries+Ruff.

## Fourth reopen: second actual run had empty search and false completion
`direct_7eff38aa3e9f` was persisted done, but `confirmed-2-evidence.txt` contains actual95-character no-results tool output. Root artifacts `search-confirmed-2.*` show the model explicitly falling back to general knowledge with an extra unsupported universal hashability statement. The prior DB done receipt is therefore NOT a success criterion by itself; second run FAIL supersedes the pending second result.

Exact query probe (`empty-query-provider-probe.json`): initial search0hits; legacy fallback9unrelated hits (Seattle weather); final requested-domain filter0hits. Existing fallback accepted first nonempty unrelated results before filtering authority, preventing later variants/providers from retrieving official evidence. Final narrow fix preserves explicit domain on each of the existing maximum3fallback variants and routes each through existing provider+authority filters before accepting. Exact query after (`empty-query-provider-after.json`):6official results; formatted payload `empty-query-sources-after.txt` has tutorial first with both definitions+literal syntax. No cached/fabricated answer or guessed URL used.

Explicit search+source verification with an actual empty web_search receipt now produces existing failed status/failure final instead of bypassing citation checks. Optional search for a general knowledge question remains allowed. Red/green: `empty-source-red.txt`, `empty-source-green.txt`; optional boundary `optional-search-green.txt` (17targeted tests). Wider same invocation:312passed16.15s before the final optional-only test addition. Ruff passed. Source hashes: ToolLoop `c137195acdbc`, websearch `a8b25510e008`, contract `234648211c3d`. Root will run two same-prompt UI scenarios after its unrelated QA11 test. No LLM diagnostics running, no further source edits planned.

## Independent review correction: trusted execution provenance
Reviewer reproduced a read_file-only request containing the words web_search in file content being misclassified as a performed search. New guard no longer searches tool-result text for execution identity: run_loop passes its actual `used_tools` list into post-processing. Existing TurnToolConstraints denial must also be absent before requiring fresh search verification. Red `receipt-provenance-red.txt`; changed call chain `.venv/bin/python -m pytest tests/test_citation_table_contract.py tests/test_citation_source_links.py tests/test_search_request_contract.py tests/test_required_tool_recovery.py tests/test_tool_loop.py -q` ->178passed (`receipt-provenance-green.txt`). Final parameterized negative boundary19passed (`receipt-provenance-boundary.txt`): read_file provenance and prohibited search both stay unaffected. Ruff passed; hashes refreshed ToolLoop `d77ac9514eb3`, other production sources unchanged from previous candidate. This final narrow regression follows the prior312-test wider run; it is not reported as a new312-test run.

## Fifth reopen: syntax and sparse fallback
Root actual `search-accepted-1.*` (task `direct_6f0b0662898c`) was done but had prose inside Python code spans; this is a failed syntax criterion, not PASS. Actual task/source captured `accepted-1-task_history.json`, `accepted-1-task_checkpoints.json`, `accepted-1-evidence.txt`. Progress copy had already transitioned to the same final, so no original draft is claimed. Second actual `search-accepted-2.*`, task `direct_29cea1b13deb`, failed explicitly; captures `accepted-2-*` show only one Data Model source2477chars.

Final narrow changes:
- Explicit Python syntax requests validate inline table code with stdlib ast.parse (never execute). Invalid code/prose errors are fed into existing bounded correction. No type-specific answers/facts/URLs are embedded. Actual captured invalid final rejected with2syntax errors: `actual-syntax-rejection.json`. AST validates syntax, not runtime behavior or data-type correctness.
- Before model correction, preserve an already supported requested table by the existing deterministic row filter, but only if exact same citation/presentation/syntax predicates pass. This prevents an unrelated footer/extra paragraph from forcing replacement of correct rows. Red `syntax-preservation-red.txt`, green `syntax-preservation-green.txt`.
- Sparse authority fallback collects/deduplicates hits across the existing maximum3variants rather than stopping on one. Explicit-domain variants progressively shorten existing query terms, avoiding legacy concatenated-word variants; original authority is filtered again before accepting results. Red `sparse-fallback-red.txt`;15focused retrieval tests green `sparse-fallback-green.txt`. Exact sparse failing query now9officialhits (`sparse-fallback-after.json`); normal production ranking/formatting gives4633chars containing complete tutorial definitions and syntax (`sparse-fallback-sources-after.txt`). No new provider, unbounded retry, or model-call budget added.

Latest full9-file regression318passed14.45s (`repeat-regression-final.txt`), Ruffpassed. Hashes refreshed: ToolLoop `ef71430ccba5`, web-search `199870844730`, contract `24fdae95ffcc`, evaluator unchanged. Actual two-run UI acceptance still pending on this candidate. All earlier FAIL artifacts are retained.

## Sixth reopen: capture exact live correction predicates
Actual CORE1 (`search-core-1.*`, task `direct_5b1347b31716`) passed root UI criteria and DBdone. CORE2 (`search-core-2.*`, task `direct_baf0dd88430d`) explicitly failed. Captured `core-{1,2}-task_history.json`, checkpoints, and source contexts. CORE2 has4615characters of full tutorial/source evidence, so no claim that empty retrieval caused this failure.

The actual rejected intermediate drafts were not recorded; no further acceptance change was made on speculation. Diagnostic-only ToolLoop patch adds `CitationValidationChecked` events to existing task_execution_events: draft, at most2revisions, final_candidate. Each records bounded output≤16000chars with SHA/truncation flag, target model, evaluator claims, and independent citation/table/presentation/syntax booleans/errors. Existing validation thresholds, table filtering and generation budget are unchanged. Production persistence fixture plus citation/ToolLoop130tests pass (`audit-trace-green.txt`); Ruffpass `audit-trace-lint.txt`. Stable ToolLoop `c6f8979c0d1b`, other hashes unchanged. Root will replay once after unrelated cancellation-owner work and use exact event records to identify the next defect, if any. No final completion claimed.

## Diagnostic actual run: full predicate trace PASS
Task `direct_7d845e7cc4a2` on actual root UI, same QA09/searchON/Qwen, source `c6f8979c0d1b`: DBdone, captured `diagnostic-ui-task_history.json`, checkpoints, source, and `diagnostic-ui-citation-events.json` (4events).

Exact observed chain: draft Korean mutability row overlap0.133 and backticked citation markers failed; revision1 had supported data rows but invalid literal `<br>`/TypeError prose inside code; revision2 had valid `lst = [1, 2, 3]` and `tup = (1, 2, 3)`, supported rows, no syntax errors, and only two footer lines unsupported; final deterministic filter retained both verified rows. Final event citations_valid/table_rows_valid/presentation_valid alltrue, unsupported claims0. This confirms intended bounded repair without another product change. Root UI DOM/link acceptance and a second same-question run remain separate gates. Source remains unchanged. Audit-specific type check0errors87warnings (`audit-trace-types.txt`).

## Exact second diagnostic failure and metadata-only repair
Actual `direct_c7241159777d` failed (`search-diagnostic-2.*`), retained `diagnostic-2-task_history.json`, checkpoints/evidence and `diagnostic-2-citation-events.json`. Both correction candidates had supported table rows and valid Python examples. Their presentation predicate failed solely because standalone backtick-wrapped citation metadata was parsed as Python; headings/footer remained unsupported but were removable by existing row filtering. This cause is directly recorded, not inferred from provider behavior.

Supported-row recovery now unwraps single-backtick spans containing only known citation markers, leaving IDs intact for the same citation evaluator. Unknown markers, double-backtick literals and actual code containing marker text are untouched. No prose or example code is rewritten. Actual captured draft+both revisions replay through this repair produces `failed=false`, two supported rows, valid examples, one canonical source link (`diagnostic-2-recovered-replay.json`). This replay is an exact failed-candidate formatter regression, not a substitute for root UI runs.

Reviewer independently found diagnostic payload expansion: report claims and syntax errors were previously unbounded even though output was16k. Audit-only detail is now limited to8claims,512chars per claim,8IDs of64chars per field,8syntax errors of320chars. Aggregate counts/validation values/full output SHA remain from the original full report; explicit truncation flags and detail totals retained. Validation uses the unchanged full report. Red/green `metadata-audit-red.txt` / `metadata-audit-green.txt`; unknown/code boundaries added.

Latest full suite324passed14.62s (`repeat-regression-final.txt`), Ruffpassed, basedpyright0errors135warnings. Stable hashes ToolLoop `03d0f56e7d33`, contract `772b864d74e1`, websearch `199870844730`, evaluator `a8a219b21b5c`. Root's two exact UI runs remain pending on this candidate. All previous failure captures retained unchanged.

## Reopened: final repeat 1, row-scoped citation and syntax boundaries

Actual task `direct_0285fe10ffbf` on isolated `yc669nua` failed after approximately five minutes. Full task row, all four checkpoints, exact tool evidence, and four bounded citation-stage events are retained as `final-repeat-1-task_history.json`, `final-repeat-1-task_checkpoints.json`, `final-repeat-1-sources.txt`, and `final-repeat-1-citation-events.json`. Root owns `docs/qa/2026-10-04-sequential-audit/search-final-attempt-1.*`. The overlong first correction exceeded the existing diagnostic text cap; its full text is unavailable, and the audit preserves truncation/hash metadata. Timing shows lengthy correction generation; no model timeout is proven by these artifacts.

Exact failure: draft included literal `<br>` inside Python spans. Sentence splitting detached row citations from earlier sentences. Revision 1 emitted overlong self-deliberation. Revision 2 had table shape/presentation accepted previously, but uncited sentence fragments and unbackticked syntax/prose remained. The revised parser carries row citations only within a real GFM data row and still evaluates EVERY sentence independently, then aggregates the row for fallback. Non-table/fenced/mismatched-header prose receives no citation carry; unknown IDs/conflicts retain rejection. This fixes citation scoping without changing overlap thresholds.

The deterministic formatter can split accidental HTML separators into separate code spans only when every unchanged fragment parses as Python, retaining quoted literal separators and all invalid input. Requested syntax cells lacking explicit code examples now fail (both column and property-row layouts). Correction prompts keep the same two-call budget and 4096-token limit, show parsed source records as untrusted text, omit rejected drafts above 4000 characters, and bound feedback examples. No answer facts, URLs, or examples are invented.

Evidence: `row-scope-red.txt` fails the newly scoped table-row case under the prior splitter; `row-scope-green.txt` passes the initial 15 focused boundaries. `row-scope-regression.txt` records 339 passing tests before the prompt-only follow-up; `row-scope-final-regression.txt` records 249 relevant tests including the final prompt boundary. `row-scope-lint.txt` passes; `row-scope-types.txt` reports 0 errors and 78 warnings. Final source SHA256s are in `row-scope-hashes.txt`.

Crucial limitation: `row-scope-replay.txt` shows this exact captured task STILL fails under the unchanged thresholds. Its Korean tuple fragment shares only two anchors; revision 2 has an unsupported extra fragment and invalid unbackticked examples. Only the supported list row is preserved/normalized. This is NOT an actual recovery or completion claim. Two consecutive actual same-prompt passes remain pending and root's recorded failure must remain unchanged.

### Final row-boundary refinements

Root review correctly identified that valid plaintext syntax examples need not use backticks. Whole plaintext syntax cells now parse unchanged after whitespace/citation-metadata removal; malformed explanatory prose is never discarded. Citation identity remains independently checked. `plain-syntax-red.txt` records two failing valid-plaintext scenarios before repair, and `plain-syntax-green.txt` records 45 passing helper tests afterward.

Root also identified `<br>` as possible valid Python comparison syntax. The separator formatter now returns every originally AST-valid span byte-for-byte, including `a<br>b` and an assignment to a comparison. Only initially invalid spans with independently parseable, nonempty fragments can change presentation. Reviewer found unbounded IDs inside feedback; feedback now caps each identifier to 64 characters and eight entries with original counts and a truncation flag. Full evaluator IDs remain untouched. `row-final-boundaries.txt` records 48 passing boundary/helper tests. Latest hashes in `row-scope-hashes.txt` supersede prior intermediate hashes. Two actual consecutive UI passes are still required.

## Actual row-scope attempt 1 — still FAILED

Root's same-prompt/search-on actual task `direct_9f1edc4cebdb` on `yxy1jord` finished `failed/citation_validation_failed`. Receipts: `row-final-1-task_history.json`, `row-final-1-task_checkpoints.json`, `row-final-1-task_execution_events.json`, and `row-final-1-sources.txt`; root UI artifacts `docs/qa/2026-10-04-sequential-audit/search-row-scope-attempt-1.*` remain authoritative for display. Sources contain two retrieved official records (Data model 1800 chars and Tutorial 1799 chars), not an empty search.

All four validation stages rejected correctly: the original draft combined both requested properties into ONE data row; revisions 1 and 2 retained that one-row structure. Revisions also embedded triple-backtick/fenced Python markup with literal breaks inside a cell and backticked TypeError prose. The main row was supported (.536 initial, .621 revised) but cannot meet the requested two data rows; footer/introduction claims were also uncited. The exact candidate cannot be recovered by formatting-only normalization without generating missing structure. Faster correction completion (~50 seconds task total) is not a task acceptance pass. No product changes made during this actual gate.

### Prompt-only repair after one-row actual failure

Root authorized a precise correction-instruction repair. When the existing draft table has the wrong explicit row count, `_citation_revision` now asks to rebuild exactly N data rows plus header/separator instead of preserving the combined row. Correctly shaped drafts retain their layout. Syntax examples are explicitly requested as single-backtick inline code, with no fenced/triple-backtick code in table cells. No validator, threshold, formatter, budget, or source retrieval changed in this follow-up.

`tests/fixtures/citation_one_row_reply.json` preserves the actual original one-row draft, first rejected fenced correction, and actual two-source evidence. `test_captured_one_row_correction_explicitly_rebuilds_requested_shape` exercises production postchecks with that draft and first correction, then a controlled supported two-row candidate. It proves two calls, 4096-token limit, first rejection, and second acceptance; it is a controlled regression, NOT a live-model pass. `table-shape-prompt-red.txt` fails with prior preserve-layout instruction; `table-shape-prompt-green.txt` passes after repair. `table-shape-prompt-regression.txt` reports 58 passed; `table-shape-prompt-lint.txt` is clean. ToolLoop SHA256: `ed585d1ebc6c311a237fea2bd2b52cd12a355538f52039e7dce25d3d15e44470`. Helper/evaluator unchanged at `693d1534...`/`aefbffdf...`. Actual two-pass gate remains pending.

Reviewer refinement: removed two brittle exact-English prompt assertions from the controlled regression. The retained test proves captured invalid-candidate rejection, valid-candidate acceptance, output, and unchanged call/token budget only. The earlier prompt red artifact records a temporary prose-pinning assertion, not a model-behavior failure, and is not claimed as behavioral proof. Conditional shape instructions were inspected directly; real-model benefit still requires root's actual UI replay. Production hashes unchanged.

Final prompt edge: multi-row splitting guidance applies only when requested N > 1; one-row requests keep exact-N reconstruction without contradictory splitting instructions. Captured assembled prompts `correction-1-row-prompt.txt` and `correction-2-row-prompt.txt` support direct review. Final ToolLoop hash is `be293931c0a88a826a494da424507b2e05a3fbc2f547081ed8557038af033266`; other product files unchanged. 58 relevant tests and scoped Ruff pass. Root's already-loaded ed585 replay is an intermediate candidate, not the final be293 gate.

## Intermediate shape replay and verified exception-output repair

Intermediate ed585 task `direct_fc5e46d409fa` on `swv_h1sl` failed despite two supported original data rows (overlap .50/.65). Exact records: `shape-intermediate-1-task_history.json`, `shape-intermediate-1-task_checkpoints.json`, `shape-intermediate-1-task_execution_events.json`, and `shape-intermediate-1-sources.txt`. Root retained `search-shape-attempt-1.*`. The sole presentation blocker in the preserved table was an inline-code exception message after valid Python and an output arrow. Both correction attempts retained it. `runtime-output-presentation-replay.txt` verifies the message is an exact standalone line in the cited Tutorial source and that changing only its code styling makes all existing predicates pass.

Root authorized a minimal presentation repair: only single-backtick, AST-invalid exception output following valid inline Python and an output arrow can become plain text, and only when the entire line exactly occurs in a known source cited by the same row. All original text, code, citations, and the existing acceptance checks remain. Unverified, partial, noncited-source, unknown-ID, unlabeled, prose, code-with-exception-text, double-backtick, and invalid-previous-code cases remain unchanged. This is applied to supported-table fallback and followed by full validation; no additional model calls.

`tests/fixtures/citation_exception_output.json` contains the actual source/draft. The controlled production postcheck regression recovers that exact captured draft with zero correction calls and two supported rows. `exception-output-red.txt` records failure with the formatter disabled; `exception-output-green.txt` records 34 focused passes; `exception-output-regression.txt` records 267 relevant passes; `exception-output-lint.txt` is clean. This proves the captured regression, not two actual live UI passes. Final candidate hashes: ToolLoop `93a2d83861faaecc8c378f1b56598bd716f1e7d8083be1ee890db8b57e10a625`, helper `9940e6de8f3813c13a326f72d4fd5a4b98d422c957d57113dbf9197f1f738ab3`; evaluator unchanged. Await independent review and root's two live runs.

Final exception-output candidate production type check: `exception-output-types.txt` reports 0 errors and 70 warnings across ToolLoop, citation helper, and search-quality evaluator. Warnings are not represented as a clean zero-warning check.

## Exception candidate live attempt 1 — FAILED, error marker variant

Actual final-candidate task `direct_4688a2f7deaf` on `048p0mpj` failed. Retained `exception-final-1-task_history.json`, `exception-final-1-task_checkpoints.json`, `exception-final-1-task_execution_events.json`, and `exception-final-1-sources.txt`; Root owns `search-exception-attempt-1.*`. Original table has two supported rows and valid examples, but the same source-verbatim exception message follows an explicit failure symbol (`❌`) instead of an output arrow. The deliberately arrow-only formatter does not transform it. Corrections then produce malformed/truncated examples and extra links, all rejected. No two-run actual pass is claimed.

Read-only feasibility check: ModelManager's existing `response_format` option is forwarded as `data['format']` while `_do_ollama_generate` uses `/chat/completions`; adopting constrained JSON would require a separately verified provider contract rather than assuming this option works. No model-manager edits or additional model calls were made.

### Explicit failure-marker presentation delta

Root authorized recognizing the observed `❌` as an explicit error-output marker alongside arrows. The only production change is that marker alternation; preceding valid Python, AST-invalid Error/Exception output, exact standalone line, same-row known citation, and all downstream guards remain unchanged. Success/check/question/no-marker cases do not transform. ModelManager and provider contracts remain untouched.

`tests/fixtures/citation_exception_marker.json` preserves the latest actual draft/source. Its production postcheck regression now recovers the captured supported two-row table with zero model calls, preserving every example and exception word. `exception-marker-red.txt` fails this exact marker fixture under prior arrow-only behavior; `exception-marker-green.txt` reports 39 focused passes; `exception-marker-regression.txt` reports 75 related passes; `exception-marker-lint.txt` is clean. Final helper hash `96b90a5da876d6b98825bfb9435445c9585e12707aaeebecbd04b761b4a6cad9`; ToolLoop remains `93a2d838...`, evaluator `aefbffdf...`. Actual final two-run gate remains pending.

Reviewer caught vacuous negative fixtures (`ValueError: bad` parses as a Python annotation). Replaced them with AST-invalid complete exception lines, explicitly checking fixture invalidity in the wrong-marker test. Related negative source/marker cases now use invalid multiword messages; valid-code preservation remains separate. 75 related tests and Ruff pass again. This correction is test-only; production hashes remain frozen.

## Final marker candidate: actual run 1 PASS, run 2 pending

Root independently verified the actual Search-ON original QA09 prompt in a fresh chat: one rendered table with header + two data rows, list mutable/tuple immutable, valid syntax spans, clearly labeled source-verbatim exception output as plaintext, one official rendered href, and no approval/mutation. UI evidence: `docs/qa/2026-10-04-sequential-audit/search-final-live-1.raw.txt`, `.ax.txt`, `.dom.json`, `.jpg`.

Backend task `direct_b1813e34988d` is `done`, error null, used_tools includes web_search. `marker-final-1-task_history.json`, `marker-final-1-task_checkpoints.json`, `marker-final-1-task_execution_events.json`, and `marker-final-1-sources.txt` retain the complete receipts. Draft failed presentation, then deterministic supported-table recovery produced final_candidate with citation/table/presentation predicates all true, without a revision generation stage. This is one actual passing run; second consecutive original-prompt run remains required. Product hashes remain frozen.


## Final completion receipt — two consecutive actual UI passes

Same exact original QA09 prompt, Search ON, real Qwen/Ollama, fresh conversation for each run, unchanged final product source:

| Run | Task | Actual UI evidence | Backend evidence | Result |
|---|---|---|---|---|
| 1 | direct_b1813e34988d | docs/qa/2026-10-04-sequential-audit/search-final-live-1.{raw.txt,ax.txt,dom.json,jpg} | marker-final-1-{task_history,task_checkpoints,task_execution_events}.json; marker-final-1-sources.txt | PASS |
| 2 | direct_ac8806f080e9 | docs/qa/2026-10-04-sequential-audit/search-final-live-2.{raw.txt,ax.txt,dom.json,jpg} | marker-final-2-{task_history,task_checkpoints,task_execution_events}.json; marker-final-2-sources.txt | PASS |

Root's final combined acceptance receipt is `docs/qa/2026-10-04-sequential-audit/search-final-live-verified.json`: raw UI response equals persisted output, each task has one terminal event, global store sequence remains contiguous (1..9 then10..18), used tools are web_search only, all inline Python spans parse, each rendered table has header plus exactly two data rows, and one official source href. Root measured32.58s and27.52s. The earlier `search-final-live-check.json` harness failure incorrectly expected each task's global sequence to restart at1; it remains preserved, and the corrected receipt documents the proper global sequence check.

Both tasks are done/error-null. Both went directly from draft to a final_candidate with citation/table/presentation predicates true; no correction generation stage was necessary. Root verified mutability facts, syntax examples, source link, no approval/mutation, and final display. This is actual UI acceptance, not a DB-only or controlled-fixture claim.

Reproducible retained-receipt verification: `.venv/bin/python .omo/evidence/web-search-answer/verify_final_two_runs.py` -> `final-two-run-verification.txt` contains `PASS_TWO_CONSECUTIVE_ACTUAL_UI_RUNS`. `final-two-run-manifest.json` records exact prompts, task IDs, source hashes, and SHA256s for every retained backend/UI artifact; all are nonempty. Final hashes remain: web_search_tool19987084..., evaluatoraefbffdf..., citation helper96b90a5d..., ToolLoop93a2d838.... No product edits followed the final two runs.

Latest relevant regression:75 tests pass (`exception-marker-regression.txt`), preceded by267 broader citation/tool-contract tests (`exception-output-regression.txt`) before the one-symbol marker extension. Scoped Ruff is clean (`exception-marker-lint.txt`). Production type check before the marker-only extension reports0errors/70warnings (`exception-output-types.txt`). Independent final review is CLEAR/APPROVE with39focused tests+5marker boundaries; report `docs/qa/2026-10-04-sequential-audit/backend-fix-review.md`.

Limits: AST validation establishes syntax and never executes examples; citation scoring remains the existing lexical/cross-language evidence policy. Exception presentation repair is intentionally narrow (known cited standalone source line, valid preceding Python, explicit arrow or failure marker). General model quality outside this prompt and unrelated provider behavior are not claimed solved. All prior failed actual runs and intermediate candidate hashes remain documented. No install, commit, push, user-store mutation, provider-schema change, or model restart was performed by this worker.
