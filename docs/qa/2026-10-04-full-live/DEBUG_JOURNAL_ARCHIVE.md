---
title: Full live debugging journal archive
date: 2026-10-04
tags: [qa, runtime, journal, archive]
---

---
title: Full feature live verification temporary diagnostic journal
date: 2026-10-04
tags: [temporary, debugging]
---

Environment: existing Python3.13 .venv / FastAPI; app PID64370, localhost8000,
no reload watcher/debugger. Shared dirty tree at full HEAD
8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382 is preserved. No Git mutations.
Read debugging/runtime python, methodology00-setup,02-investigate,08-qa;
programming skill and Python README; codebase-memory skill.
Current graph has248nodes and no chat symbols; bounded fallback discovery permitted.
No .git/info/exclude mutation. Remove only this owned journal after durable audit.

## Hypothesis framework for any observed failure

1. App routing/prompt/tool/result boundary loses user intent or misrepresents state:
   distinguish by actual input, tool receipt and final output on the same request.
2. Model limitation: identical preserved prompt reaches current provider but answer is
   wrong; compare isolated controlled question and real pipeline, avoid answer hardcoding.
3. Environment/stale build/unconnected backend: distinguish health, current code candidate,
   selected model and truthful missing dependency/connection status.

No failure round yet. Refine per concrete defect before editing.

## Artifacts and ownership

- This temporary journal: promote findings then remove only this file.
- Permanent QA docs/qa/2026-10-04-full-live/ and new execution plan: retain evidence.
- Browser new synthetic QA conversation: retain as user-visible evidence, no deletion.
- Potential synthetic fixture home/server/auth header: journal exact path/session before
  creating; stop only owned process and remove only owned credential on completion.
- No raw app logs, live credentials, real user memory export or debugger instrumentation.

## Initial live observation

R2-01 actual browser request, new conversation, READ_ONLY, search/codeOFF:
17*23 as JSON only → {"result": 391}. PASS for this question.
R2-02 unknown fictional release date submitted; awaiting actual final response.

## Quality gate false-retry seam (quality worker)

- Runtime: existing `.venv` Python 3.13; use `uv run --no-sync --offline` with
  `UV_CACHE_DIR=/private/tmp/ssak-quality-uv-cache` to avoid the blocked user cache.
- No model/app calls, Git operations, provider/network calls, or source instrumentation.
- References: programming/Python README, debugging Python runtime, setup,
  investigation and fix methodology; graph-first discovery found no current
  `quality_gate.py` in the available index, so bounded source fallback was used.
- H1: length and lexical overlap cause false retry; compare short numeric/JSON
  replies with the same grade checks after those two multipliers are removed.
- H2: a comparison table is imposed without a table request; compare explicit
  table requests with numeric-only comparisons.
- H3: post-loop runs revisions even when unchanged output cannot improve score;
  capture rewrite count with the real gate and in-memory generation adapter.
- Retained artifacts: `tests/test_quality_output_contract.py`, owned quality gate
  changes, and `docs/qa/2026-10-04-full-live/quality-*` evidence.
- Temporary artifact: `/private/tmp/ssak-quality-uv-cache`; remove after checks.

## Concrete findings and owners

R2-02 returned 확인 불가. R2-03 returned 확인. R2-04 returned
{"project":"노을-자작나무","budget":580000,"release":"2026-11-19"}.
Route navigation back to chat restored all4completedturns.

Extraction root browser: unlocked8000/data-extraction, synthetic query,
console Metrics load failed/status401 and Search failed/status401, permanent
metricsloading UI. H1 missingheader confirmed by source; H2 expiredallauth refuted
by workingchat+health; H3 servermodel error refuted by401beforedispatch.
Worker extraction_auth_fix owns DataExtractionPage/tests/dex/extractionApi.

Studio root browser: no trainingjob, progress0/loss2.450, step5skips displaycheckmarks;
GGUFexportclick shows success claiming newweights and selectablemodel.
H1 UI-only success confirmed handler; H2 artifactbackend refuted absent API;
H3 earliercompletedjob refuted freshstep0and purestatehandler.
Worker studio_truthful_fix owns StudioPage/tests/studio-onlyhelper.

Profile worker syntheticreal-leaf runtime: fifth READ_ONLY observation,
request_allows_side_effects=False but profilefile/graph=True and reward_tick1.
H1missingdurableguardconfirmed; H2downstreamguard/H3contextlostrefuted.
Worker readonly_profile_boundary owns user_model+focusedtest; /private/tmp auto-cleaned
TemporaryDirectory source-only leaf isolation avoids actualhome/model/embedding.

Quality pure runtime reproduced by independentinvestigator: numeric-only comparison
correct9 scoresC0.45/should_retryTrue due wordoverlap/table guesses. Worker
quality_short_contract_fix owns gate+focusedcontracttests; do notattribute real
latency tothiswithout bound live call counts. All retained RED/GREEN/logs are in
docs/qa/2026-10-04-full-live/, no rawcredentials or temporary instrumentation.

## Core prompt budget (budget worker)

Scope: context_budget.py plus focused final/context budget regressions. No tool_loop,
quality, user model, UI, capability policy, Constitution, provider calls, Git, live
home imports, credentials, app logs or user memory reads/writes.

Hypotheses:
1. Protected system/tool schema prefix is irreducible above8000. Measure production
   tool prompt with static current built-in schemas and exact R2-05 synthetic request.
2. Model repo alias fails declared-window lookup: qwen3.8:latest returns declared=None
   while canonical qwen3.8 returns262144. Toggle only lookup to test causality.
3. Large history or overselected tool docs drive excess. Compare protected-only and
   four small synthetic turns; preserve complete guard/schema bytes and user request.

Artifacts journaled before creation:
- Retain docs/qa/2026-10-04-full-live/budget-* diagnostic evidence, baseline snapshots,
  source-only reproducer and synthetic prompt fixture; no personal/credential content.
- Temporary /private/tmp/ssak-budget-* isolated pytest/cache paths; owned only cleanup.
- Potential source fix context_budget.py; restore only owned baseline bytes if rejected.
- Focused regressions tests/test_final_prompt_budget.py; preserve preexisting bytes.

## Post-read and format findings

R2-05 final FAIL is after read_file, not before it. Authorized scoped SQLite
mode=ro metadata for synthetic direct_9300b11f775d found one real read receipt;
the source-composed posttool fixture estimates8640tokens. Declared canonical
qwen3.8 window262144 but repoaliasqwen3.8:latest falls back8000. Actual passive
Ollama/api/ps context_length32768 confirms28672input+4096completion reserve.
Budget worker owns only context_budget.py+test_final_prompt_budget.py.

R2-06 numeric-only comparison returned an unwanted7/9/9table. R2-07 quoted
instruction treated as data returned12. Do not infer initial provider draft or
live rewrite count without bound receipts. Quality worker's real postloop
synthetic driver proves the redundant-retry seam independently.

## Additional surface findings and owners

ModelHub browser labels6installedOllama models running; actual passive /api/ps
lists onlyqwen3.8:latest. No model load/unload performed. model_runtime_status_fix
owns diagnosis and narrow modelstatus boundary after graph-first discovery.

Real isolated productionHTTP harness exposed notes/search500 when
VaultEngine(sync_rag=False) lacks vector_store. vault_keyword_search_fix owns
route keywordsearch and regression; QA driver keeps expected200 hit unchanged.
bridge_palette_fix owns Start/commandRegistry/WikiPage minimal safe navigation.

Retain manual_api_driver.py/manual_cli_driver.py/manual_api_fixture.py/
manual_api_cases.py and API_SCENARIOS.md under this QA directory. Driver must
patch Path.home BEFORE all project imports, cwd and explicit AGK task/data/
project/cache paths. Preserve HOME/CODEX_HOME. Root will personally execute
its real HTTP socket and CLI, with synthetic bearer only and owned cleanup.

## Owned live restart

Exact ps confirmedPID64370 `.venv/bin/python .venv/bin/agk serve --host127.0.0.1
--port8000`; TERM sent only tothis ownedprocess. Startcurrentcandidate on same
loopbackport, stdout/stderrredirect `/tmp/ssak-full-live-main-20261004.raw.log`.
That rawfile maycontainJWT websocketquery strings: NEVER read/exportrawlines;
only hardcodedstartup/PID regex maybe emitted. Live server intentionally stays
runningforuserafterverification. No debugger or sourceinstrumentation.

Notes worker planned retained test_vault_keyword_search_api.py and notes-search-
red/green/checks/report; auto-cleanedTemporaryDirectory ssak-notes-search- with
Path.home/cwd/AGKpaths BEFORE imports, preservingHOME/CODEX_HOME. No testserver
or debug instrumentation. H1 optionalvectorstoremissing; H2 realkeywordmatcher
seedhit; H3 exactfixtureVaultrootdistinguishes dependency/scope errors.

API QA additionalplanned retained manual_extra_cases.py/manual_extra_fixture.py
for syntheticconversation/joblifecycles, auth/context/voice/approval boundaries.
Only temporaryownedGitvault/stores aremutated, noactualuserjobs/data.
Root CLIdriver personallyexecuted8/8 exit0; root-cli-results.jsonl retained.
Root sameR2-05 nowreturns exact5fields, sameR2-06returns9. Newboundreceiptpending.

NewestR2-05receipt direct_888c076b6a7f done/read_file1/halt0, retainedsafeJSON.
Rootprofile5realGraphMLcases personallyexecutedexit0(root-profile-check.txt).
FirstrootHTTP45cases43PASS, failures toolsetorderedexpectation and nullsearch
fixturewithoutstockintent; driverownerprovesmisusedfixturebeforecorrection.
Retainoriginalroot-api-results.json/jsonl, do notoverwritefailreceipts.
AdditionalQA modulesplanned manual_boundary_cases/fixture, manual_browser_cases/
fixture. system_boundary_fix ownssettings explicitconfigpath and extraction
availabilityclassification diagnosis; newfocusedtests+system-boundary-* retained,
TemporaryDirectory/Path.homepatch beforeimports, noactualconfigsecretread/debugger.

Compact worker planned retained test_conversation_compact_validation.py and
compact-validation-*; auto-cleanedssak-compact-validation- temporaryhome/cwd/AGK
beforeimports preservingHOME/CODEX_HOME. Existingge0/le10000modelvalidates
manuallyinsideRequesthandler soValidationErrorcurrentlybecomes500; typedFastAPI
bodyboundaryfixplanned, noalgorithm/rangechange. Invalidmustleavefixturestorebyte-
unchanged. Systemworker ssak-boundary-client- temporarysocket/clientcapture uses
driverfixture forsettings+actualproducerSearch Error guard; no rawmainlogs/auth.

Budget worker cleanup scope update: retain new regression module
`tests/test_qwen_repo_prompt_budget.py`; move only worker's appended cases out of
`tests/test_final_prompt_budget.py` to keep new test module under250pureLOC.
The source budget module was already above250pureLOC at baseline; preserve narrow
ownership and document that existing size limitation instead of broad splitting.

### Core prompt budget fix completed

Alias resolution and provider-window completion reserve fixed in context_budget.py. Isolated regression:25 passed, Ruff/basedpyright clean; isolated baseline toggle retains5 expected failures. Exact synthetic live retry direct_888c076b6a7f completed with one persisted read_file call. Evidence and hashes:docs/qa/2026-10-04-full-live/budget-report.md and budget-sha256.json. Successful no-compaction live calls do not persist an exact final ledger. Shared journal retained for root cleanup.

## Final boundary and UI retry artifacts

Bridge owner extends agent_bridges.py/test_agent_bridge_auth_plan.py and its owned
AgentStartPage to guarded signed-token shell references, bearer-compatible Claude
ANTHROPIC_AUTH_TOKEN, and shell-quoted model values. Retain bridge-cli-auth-*;
no credentials read, external client launch, or tunnel launch.

Conversation owner confirms append/fork invalid declared-model inputs also500 and
store bytes unchanged. Conditional typed-boundary fix now authorized in the same
conversation_api.py; retain test_conversation_request_validation.py and
conversation-validation-*. Preserve algorithms, ranges, context/revisions.

Direct search owner owns direct_task_execution.py/test_search_request_contract.py
and search-request-contract-* after graph-first diagnosis. R2-12 natural explicit
web request omitted expected-tools contract; no tool receipt. Conditional tool_loop.py
extension only if real production seam proves a missing required tool is silently
streamed as success. No fake QA-answer hardcoding or search-OFF bypass.

Root will build dashboard with existing local TypeScript/Vite binaries, then run
manual_api_driver.py serve in its existing synthetic before-import isolated home.
Owned ephemeral loopback fixture server/tab uses synthetic-manual-qa-pin; temporary
signed header is consumed by curl only, never printed/read. Retain root-ui-* JPEG
screenshots and metadata under this QA directory; capture synthetic content only.
Temporary isolated server/header/store cleaned by its owner on exit. Real8000
remains for user. Retain root-api-118.*, root-cli-final.jsonl and dashboard-build.log.

Retain root_regression_driver.py/root-regression.log: imports the already-reviewed
isolation helper before pytest, redirects tempfile/TMPDIR into owned root, preserves
HOME/CODEX_HOME and patches outbound sockets closed. Only explicit changed-boundary
tests run, no repo-wide bootstrap/provider/hardware tests. No cache/bytecode retained.
Root model discovery driver runs inside the same isolation (outbound passive local
catalog calls allowed for this separate mode), never loads/unloads/models changes.

## Final cleanup and browser permission guidance

No source edits occurred after the final-source-manifest freeze. Latest main server
PID25430 remains running. Owned fixture server exact command identified as PID30256;
terminate only this process and verify its owned temporary root/request-header are
removed. Original user browser tab remains open; owned QA tab4 was already closed.
Retain all sanitized QA reports, receipts and screenshots as durable evidence.
Archive this root-owned journal to DEBUG_JOURNAL_ARCHIVE.md, verify archive bytes,
then remove only this temporary root journal. Preserve unrelated shared changes.

The saved localhost browser permission still blocks UI verification. Native Codex
UI inspection was also explicitly rejected by Computer Use safety, so no alternate
native automation or preference-file modification was attempted. Fetched official
OpenAI Settings and Browser docs confirm Settings > Browser and Cmd+, on macOS;
removing a blocked website permits a new access prompt. Exact removal control name
is not documented, and must not be invented. User changes that permission directly.

Cleanup observed: PID30256 terminated; owned fixture root and request-header absent. PID25430 remains. Owned QA tab4 closed; original user tab not closed. Runtime manifest rehash69/69 matched. Retain permanent QA evidence only.
