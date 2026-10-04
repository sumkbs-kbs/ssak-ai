---
title: Isolated production HTTP and CLI manual protocol
date: 2026-10-04
tags: [qa, manual, production-routes, isolation]
status: ready-for-root-execution
---

This protocol calls the real production FastAPI application through a real loopback
uvicorn socket and `/usr/bin/curl`, with its actual authentication middleware. It
invokes the actual Typer CLI in fresh child processes. The 118 HTTP cases and nine
CLI cases are representative route and boundary checks, not a claim that every
function, inventory feature, hardware path, or installation has been verified.

The CLI cases inspect help/version/recipes, cognitive-off status, known/invalid
decision evaluation, isolated task/memory lists, and the Codex bridge dry plan.
The bridge case prints only connection instructions and checks a guarded token
environment reference, the actual selected base URL, and absence of a fake token;
it does not execute Codex or read any credential.

Run these exact commands from any directory with the existing repository runtime:

```sh
/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/manual_api_driver.py check --output /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-118.json > /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-118.jsonl
/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/manual_cli_driver.py > /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-cli-final.jsonl
```

Loopback binding requires the host's approved local-socket execution permission.
Do not run the shebang through dependency resolution: no package installation is
needed or authorized. The interpreter is Python 3.13 in the existing `.venv`.

`check` owns its child server. It allocates an ephemeral port, waits for readiness,
executes each real curl request, compares selected response fields against explicit
expectations, exits nonzero for any discrepancy, and terminates the child in a
`finally` block. A shutdown timeout triggers a kill and removal of only that child's
validated temporary root. The output concludes with case counts and confirmation
that the temporary authentication header was removed. Parent-root result files are
the personal execution receipts; harness-author results are separate evidence.

For an additional direct curl inspection, `serve` prints one JSON record containing
only its URL and temporary paths, then stays running until interrupted:

```sh
/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/manual_api_driver.py serve
```

Use the returned URL and header path without reading or printing the header:

```sh
/usr/bin/curl --silent --show-error --noproxy '*' --header @<returned-header-file> <returned-url>/api/auth/verify --request POST
/usr/bin/curl --silent --show-error --noproxy '*' --header @<returned-header-file> '<returned-url>/v1/notes/search?q=QA_SEED_TEXT'
```

These two optional commands are templates because the server chooses a fresh port
and temporary root. The `check` command above performs the full exact protocol.
Stop a standalone `serve` with Ctrl+C or SIGTERM so its context managers clean up.

Before every product import, the fixture patches `Path.home`, changes cwd to its
own project, inserts the repository source path explicitly, and replaces inherited
application settings with temporary config, auth, task DB, job DB, usage, vault,
model, GBrain-compatible home, data, log, vector, HF and cache paths. `HOME` and
`CODEX_HOME` retain their original values. `dotenv.load_dotenv` is disabled before
product imports so source-relative discovery cannot read a real `.env`.
`AGK_CONVERSATION_STORE_DIR` is explicit, and `os.path.expanduser` redirects `~`
and `~/...` to the owned root for legacy session/episodic-memory defaults.

Every note uses YAML frontmatter and the actual VaultEngine with Git autocommits
inside a temporary repository. Git author/config paths are synthetic. The bearer
comes from the real TokenService and is written to `request-header` with mode
0600; no JWT, PIN, bearer header, browser approval token, or nonce is selected for
the printed observations. The only header file is inside the owned temporary root.

The real app runs with lifespan off. This avoids startup dispatch, scheduler work,
network discovery and real model loading; it does not verify full production startup.
Server-side outbound socket connections fail closed, including real local model
ports. No real home/profile/config, private memory, logs, or credentials are used.

Internal route dependencies bind real VaultEngine, MemoryManager, ProjectMemoryProvider,
ConversationStore, SessionManager, TaskStateStore, BackgroundTaskRunner,
AgentRuntime, ScheduledJobService/Store, ApprovalManager and BrowserApprovalGate
instances to the owned temporary stores. No fake route is mounted. Three external
boundaries are labeled in each observation: deterministic WebSearchTool output,
a synthetic VoiceService transcriber, and a model port that raises typed unavailability.

The fixture's disabled search, agency, MCP and cognitive states describe this
isolated configuration, not the user's live configuration. Toolset cases inspect
the real readonly catalog without changing access policy. Tasks read/cancel an
isolated paused task without LLM work. Jobs create/pause/resume/delete definitions
scheduled in 2100 with delivery none; every run count remains zero. Conversation
compaction uses the real deterministic local summary, preserves originals, and
checks revision conflicts and independent fork state.

Memory zero-budget and separate-project recall are asserted directly against real
engines and printed as `engine_fixture_checks`; they are explicitly not HTTP cases.
Privacy cases redact synthetic vault text, read the redaction, restore the returned
Git snapshot, and verify one old synthetic project fact is removed by retention.
The project-memory redact case is a valid no-op on already nonsecret content.

Search fixtures distinguish numeric success, recognized partial stock data with
absent fields remaining null, actual producer-style `Search Error:` unavailability,
and a successful empty result. Exact decimal strings retain the integer
9007199254740993, Korean trillion/billion scaling, percentage points and basis points.
No provider reachability or live financial-data accuracy is claimed.

Browser approval cases verify pending/denied refusal, owner binding mismatch,
forbidden permanent grants, one-time ticket issuance, duplicate issuance rejection,
withdrawal, and model self-approval refusal. The API uses opaque request IDs and
one-shot approval tokens; it has no literal nonce input. Tokens are never printed
or used to perform a browser action. Actual page execution, token consumption and
replay after page execution remain outside this protocol.

Hardware/external paths remain unverified: real STT/TTS, vision, training, embeddings,
model loading/generation, live search, OAuth/accounts, remote pairing/relay,
external-brain communication, publishing, native signing/update/install and other
platforms. Real chat/browser UI execution belongs to root's separate live surface
receipts. This protocol also does not exercise terminal commands, package/skill
installation, settings mutations, scheduler triggers, destructive user data, live
Kanban dispatch, agent audit history, filesystem edits outside the fixture, or
all tool implementations. Unsupported/disabled capability is not converted into
a fake successful feature execution.

The initial 114-case root and author receipts remain separate from the final 118-case protocol.

Initial failure evidence is retained separately: parent `root-api-results.json/jsonl`
recorded 43/45 before catalog corrections; `harness-api-initial.json` recorded
109/112 including negative compaction returning HTTP 500. Catalog corrections
followed production contracts: the readonly tool list is sorted; stock extraction
requires stock intent and a recognized source shape; execution context requires
the current conversation revision; memory export uses `providers` at the root.
Product fixes are owned by other workers and remain distinct from harness edits.
The added append negative revision, invalid role and fork negative revision cases
require 422 and verify the source snapshot is unchanged. Their baseline 500 failures
are retained in conversation-validation-baseline-live.json.
The ninth CLI case was initially 8/9 in harness-cli-bridge-red.jsonl before the guarded
connection-plan fix; its final author receipt is 9/9.

`harness-source-manifest.json` records SHA256 and pure LOC for the ten driver
modules. Each stays below 250 pure LOC. Ruff, the no-excuse checker, and the dedicated
basedpyright error gate validate only these modules; live receipts establish runtime
behavior. No earlier QA document or test result counts as a current manual pass.

The ordered scenario table below is generated from the executable case catalog.

| Case | HTTP | Expected semantics | Scope |
| --- | --- | --- | --- |
| health | GET /health, 200 | status equals ok | real production route + real isolated stores |
| ready | GET /api/ready, 200 | traffic equals accept; status equals degraded | real production route + real isolated stores |
| auth-required | GET /api/recipes, 401 | detail equals Invalid or missing credentials; ok equals False | real production route + real isolated stores |
| auth-protected | GET /api/recipes, 200 | ok equals True; recipes.0.name equals chat-sft | real production route + real isolated stores |
| toolsets | GET /api/toolsets, 200 | active equals full; toolsets contains read_file | real production route + real isolated stores |
| readonly-toolset | GET /api/toolsets/safe/tools, 200 | tools equals ['git_diff', 'git_log', 'git_status', 'glob_search', 'grep_search', 'list_directory', 'read_file', 'web_search']; count equals 8 | real production route + real isolated stores |
| policy | GET /api/system/access-mode, 200 | ok equals True; mode equals full_access | real production route + real isolated stores |
| cognitive-off | GET /api/cognitive/surface/status, 200 | actual_active equals False; mode equals off; source equals legacy | real production route + real isolated stores |
| cognitive-finite | GET /api/cognitive/surface/stream?limit=1&interval_ms=0, 200 | $ contains event: surface_status; $ contains event: done | real production route + real isolated stores |
| cognitive-limit | GET /api/cognitive/surface/stream?limit=11, 422 | error equals validation_error | real production route + real isolated stores |
| memory-stats | GET /api/memory/stats, 200 | memory.total_providers equals 1; memory.provider_names equals ['project'] | real production route + real isolated stores |
| memory-recall | GET /api/memory/recall?query=qa_marker, 200 | recalled contains QA_SCOPED_MEMORY | real production route + real isolated stores |
| memory-provenance | GET /api/memory/ranked?top_k=1, 200 | facts.0.key equals project:fact:qa_marker; facts.0.value equals QA_SCOPED_MEMORY; facts.0.scope equals project | real production route + real isolated stores |
| vault-tree | GET /api/vault/tree, 200 | tree.0.path equals seed.md | real production route + real isolated stores |
| vault-read | GET /api/vault/read?path=seed.md, 200 | metadata.title equals QA seed; content contains QA_SEED_TEXT | real production route + real isolated stores |
| vault-write | POST /api/vault/write, 200 | ok equals True; path equals http.md | real production route + real isolated stores |
| vault-read-write | GET /api/vault/read?path=http.md, 200 | content contains QA_HTTP_WRITE; metadata.title equals HTTP QA | real production route + real isolated stores |
| vault-search | GET /v1/notes/search?q=QA_SEED_TEXT, 200 | keyword_results contains seed.md | real production route + real isolated stores |
| vault-bounds | GET /api/vault/read?path=../fixture.txt, 400 | error equals http_400 | real production route + real isolated stores |
| filesystem-read | GET /api/fs/read?file=fixture.txt, 200 | ok equals True; content equals QA workspace fixture  | real production route + real isolated stores |
| filesystem-bounds | GET /api/fs/read?file=../../outside.txt, 403 | error equals http_403 | real production route + real isolated stores |
| git-status | GET /api/git/status?path=vault, 200 | ok equals True; files equals [] | real production route + real isolated stores |
| git-committed-write | POST /api/git/log, 200 | ok equals True; commits.0.message equals Wiki edit: http.md | real production route + real isolated stores |
| git-diff | POST /api/git/diff, 200 | ok equals True; diff equals  | real production route + real isolated stores |
| task-status | GET /api/tasks/qa-paused/status, 200 | data.task_id equals qa-paused; data.status equals paused | real production route + real isolated stores |
| task-missing | GET /api/tasks/qa-missing/status, 404 | error equals http_404 | real production route + real isolated stores |
| task-limit | GET /api/tasks?limit=0, 422 | error equals validation_error | real production route + real isolated stores |
| task-cancel | POST /api/tasks/qa-paused/cancel, 200 | status equals cancelled | real production route + real isolated stores |
| agency-disabled | GET /api/agency/status, 200 | enabled equals False; scheduler.should_wake equals False; objective_task_ids equals [] | real production route + real isolated stores |
| jobs-fixture | GET /api/jobs, 200 | 0.job_id equals job_qa_lifecycle; 0.status equals active | real production route + real isolated stores |
| jobs-health | GET /api/jobs/health, 200 | active_jobs equals 1; open_runs equals 0; healthy equals True | real production route + real isolated stores |
| search-disabled | GET /api/search/status, 200 | availability equals disabled | real production route + real isolated stores |
| extract-numeric | POST /api/search/extract, 200 | ok equals True; extracted.numeric_data contains row {'normalized_value': '9007199254740993', 'unit': 'KRW'}; extracted.numeric_data contains row {'normalized_value': '1234500000000', 'unit': 'KRW'}; extracted.numeric_data contains row {'normalized_value': '3.5', 'unit': 'percentage_point', 'display_unit': '%p'}; extracted.numeric_data contains row {'normalized_value': '25', 'unit': 'basis_point', 'display_unit': 'bp'} | real route/extractor; deterministic external search provider fixture |
| extract-null | POST /api/search/extract, 200 | has_top1_json equals True; extracted.stock_prices.0.name equals 삼성전자; extracted.stock_prices.0.close_price equals 943000; extracted.stock_prices.0.open_price equals None | real route/extractor; deterministic external search provider fixture |
| extract-unavailable | POST /api/search/extract, 200 | ok equals False; error equals search_unavailable | real route/extractor; deterministic external search provider fixture |
| extract-empty | POST /api/search/extract, 200 | ok equals True; extracted.numeric_data equals []; extracted.stock_prices equals []; has_top1_json equals False | real route/extractor; deterministic external search provider fixture |
| extract-invalid | POST /api/search/extract, 400 | error equals http_400 | real production route + real isolated stores |
| voice-malformed | POST /api/voice/transcribe, 422 | error equals http_422; detail contains WAV | real production route + real isolated stores |
| voice-unsupported | POST /api/voice/transcribe, 422 | error equals http_422; detail equals unsupported WAV encoding: format code 2 | real production route + real isolated stores |
| voice-overlarge | POST /api/voice/transcribe, 413 | error equals http_413; detail equals Audio body exceeds 25 MiB | real production route + real isolated stores |
| voice-blank-speak | POST /api/voice/speak, 422 | error equals validation_error | real production route + real isolated stores |
| recipe-capabilities | GET /api/recipes/capabilities, 200 | ok equals True; capabilities.1.backend equals unsloth; capabilities.1.executable equals False; capabilities.0.unsupported_keys equals ['gradient_accumulation_steps', 'max_seq_length', 'num_train_epochs'] | real production route + real isolated stores |
| decision-known | POST /api/benchmarks/decisions/evaluate, 200 | counts.scored equals 1; metrics.accuracy equals 1.0; metrics.brier within 1e-12 0.08; score_source equals provided_probabilities | real production route + real isolated stores |
| decision-invalid | POST /api/benchmarks/decisions/evaluate, 422 | detail equals Invalid decision evaluation input | real production route + real isolated stores |
| mcp-empty-health | GET /api/mcp/health, 200 | ok equals True; servers equals []; summary.total equals 0 | real production route + real isolated stores |
| integration-capabilities | GET /v1/integrations/unsloth/capabilities, 200 | write_tools_enabled equals False; capabilities contains unavailable | real production route + real isolated stores |
| session-hydrated-info | GET /api/session/info, 200 | ok equals True; session.turn_count equals 1; session.message_count equals 2 | real production routes + real isolated stores; no model execution |
| session-save | POST /api/session/save, 200 | ok equals True | real production routes + real isolated stores; no model execution |
| conversation-disk-hydration | GET /v1/conversations/qa-conversation-source?project_id=default, 200 | snapshot.revision equals 4; snapshot.message_count equals 4; messages.0.id equals qa-user-1; messages.0.content equals QA_ORIGINAL_FIRST; messages.3.content equals QA_ORIGINAL_FINAL | real production routes + real isolated stores; no model execution |
| conversation-append-invalid-revision | POST /v1/conversations/append, 422 | error equals validation_error | real production routes + real isolated stores; no model execution |
| conversation-append-invalid-role | POST /v1/conversations/append, 422 | error equals validation_error | real production routes + real isolated stores; no model execution |
| conversation-fork-invalid-revision | POST /v1/conversations/fork, 422 | error equals validation_error | real production routes + real isolated stores; no model execution |
| conversation-invalid-input-preserves-source | GET /v1/conversations/qa-conversation-source?project_id=default, 200 | snapshot.revision equals 4; snapshot.message_count equals 4; messages.0.content equals QA_ORIGINAL_FIRST; messages.3.content equals QA_ORIGINAL_FINAL | real production routes + real isolated stores; no model execution |
| conversation-stale-append | POST /v1/conversations/append, 409 | error equals stale_conversation_revision; expected_revision equals 3; current_revision equals 4 | real production routes + real isolated stores; no model execution |
| conversation-append | POST /v1/conversations/append, 200 | revision equals 5; message_count equals 5 | real production routes + real isolated stores; no model execution |
| conversation-fork | POST /v1/conversations/fork, 200 | conversation_id equals qa-conversation-fork; revision equals 0; message_count equals 5 | real production routes + real isolated stores; no model execution |
| conversation-fork-hydration | GET /v1/conversations/qa-conversation-fork?project_id=default, 200 | snapshot.revision equals 0; snapshot.message_count equals 5; messages.0.provenance equals fork; messages.4.content equals QA_HTTP_TURN | real production routes + real isolated stores; no model execution |
| conversation-fork-independent-append | POST /v1/conversations/append, 200 | conversation_id equals qa-conversation-fork; revision equals 1; message_count equals 6 | real production routes + real isolated stores; no model execution |
| conversation-source-after-fork-write | GET /v1/conversations/qa-conversation-source?project_id=default, 200 | snapshot.revision equals 5; snapshot.message_count equals 5; messages.4.content equals QA_HTTP_TURN | real production routes + real isolated stores; no model execution |
| conversation-compact-invalid | POST /v1/conversations/compact, 422 | error equals validation_error | real production routes + real isolated stores; no model execution |
| conversation-local-compact | POST /v1/conversations/compact, 200 | revision equals 6; message_count equals 3; retained_message_ids.0 equals msg_summary; retained_message_ids.1 equals qa-assistant-2 | real production routes + real isolated stores; no model execution |
| conversation-refresh-compacted-view | GET /v1/conversations/qa-conversation-source?project_id=default, 200 | snapshot.revision equals 6; snapshot.message_count equals 3; messages.0.id equals msg_summary; messages.0.role equals system; messages.0.provenance equals summary; messages.1.content equals QA_ORIGINAL_FINAL; messages.2.content equals QA_HTTP_TURN | real production routes + real isolated stores; no model execution |
| conversation-originals-preserved | GET /v1/conversations/qa-conversation-source/history?project_id=default, 200 | revision equals 6; total equals 5; history_incomplete equals False; messages.0.content equals QA_ORIGINAL_FIRST; messages.4.content equals QA_HTTP_TURN | real production routes + real isolated stores; no model execution |
| conversation-originals-page | GET /v1/conversations/qa-conversation-source/history?project_id=default&offset=3&limit=1, 200 | offset equals 3; limit equals 1; total equals 5; messages.0.id equals qa-assistant-2; messages.0.content equals QA_ORIGINAL_FINAL | real production routes + real isolated stores; no model execution |
| conversation-originals-export | GET /v1/conversations/qa-conversation-source/export?project_id=default, 200 | schema_id equals agk.conv-export.v1; revision equals 6; message_count equals 5; deleted equals False; messages.0.content equals QA_ORIGINAL_FIRST | real production routes + real isolated stores; no model execution |
| conversation-fork-refresh | GET /v1/conversations/qa-conversation-fork?project_id=default, 200 | snapshot.revision equals 1; snapshot.message_count equals 6; messages.5.content equals QA_FORK_ONLY_TURN | real production routes + real isolated stores; no model execution |
| job-fixture-definition | GET /api/jobs/job_qa_lifecycle, 200 | job_id equals job_qa_lifecycle; name equals QA seeded lifecycle job; status equals active; schedule.kind equals once; next_run_at equals 2100-01-01T00:00:00Z; last_run_at equals None | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-create | POST /api/jobs, 201 | name equals QA HTTP created job; status equals active; model equals qa-unavailable-model; schedule.kind equals once; next_run_at equals 2100-01-01T00:00:00Z; delivery.kind equals none | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-created-definitions | GET /api/jobs, 200 | $ contains row {'name': 'QA HTTP created job', 'status': 'active'}; $ contains row {'job_id': 'job_qa_lifecycle', 'status': 'active'} | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-health-after-create | GET /api/jobs/health, 200 | active_jobs equals 2; paused_jobs equals 0; open_runs equals 0 | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-pause | POST /api/jobs/job_qa_lifecycle/pause, 200 | job_id equals job_qa_lifecycle; status equals paused; last_run_at equals None | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-read-paused | GET /api/jobs/job_qa_lifecycle, 200 | status equals paused; name equals QA seeded lifecycle job | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-resume | POST /api/jobs/job_qa_lifecycle/resume, 200 | job_id equals job_qa_lifecycle; status equals active; next_run_at equals 2100-01-01T00:00:00Z | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-no-runs | GET /api/jobs/job_qa_lifecycle/runs, 200 | $ equals [] | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-delete | DELETE /api/jobs/job_qa_lifecycle, 204 | empty response; following GET confirms deletion | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-read-deleted | GET /api/jobs/job_qa_lifecycle, 404 | error equals http_404; detail equals Scheduled job not found | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-final-health | GET /api/jobs/health, 200 | active_jobs equals 1; paused_jobs equals 0; open_runs equals 0 | real scheduled-job service/store in temporary DB; no trigger or delivery |
| job-invalid-create | POST /api/jobs, 422 | error equals validation_error | real scheduled-job service/store in temporary DB; no trigger or delivery |
| auth-verify | POST /api/auth/verify, 200 | valid equals True; subject equals synthetic-qa | real production route + real isolated stores |
| auth-verify-missing | POST /api/auth/verify, 401 | detail equals Invalid or missing credentials | real production route + real isolated stores |
| auth-policy-status | GET /api/auth/status, 200 | protected equals True; dev_no_pin_allow equals False | real production route + real isolated stores |
| settings-isolated-config | GET /api/settings, 200 | settings.qa_marker equals QA_SETTINGS_ONLY | real production route + real isolated stores |
| workspace-pointer | GET /api/fs/workspace, 200 | ok equals True; workspace equals {project_root} | real production route + real isolated stores |
| workspace-bound-context | POST /api/execution-context/resolve, 200 | ok equals True; bound_project_root equals {project_root}; execution_context.canonical_project_root equals {project_root}; execution_context.project_id equals default; execution_context.actor_subject equals synthetic-qa | real production route + real isolated stores |
| workspace-context-invalid | POST /api/execution-context/resolve, 404 | error equals project_not_found | real production route + real isolated stores |
| voice-valid-pcm | POST /api/voice/transcribe, 200 | transcript equals QA_SYNTHETIC_TRANSCRIPT | real WAV validation + real VoiceService; external transcriber fixture, no hardware verification |
| messages-invalid | POST /v1/messages, 400 | error.type equals invalid_request_error; error.message equals model: Field required | real production compatibility route; external model port raises synthetic unavailability |
| responses-invalid | POST /v1/responses, 400 | detail equals Model is required | real production compatibility route; external model port raises synthetic unavailability |
| messages-model-unavailable | POST /v1/messages, 529 | error.type equals api_error; error.message equals Model generation failed: synthetic model provider unavailable | real production compatibility route; external model port raises synthetic unavailability |
| responses-model-unavailable | POST /v1/responses, 529 | detail equals Model generation failed: synthetic model provider unavailable | real production compatibility route; external model port raises synthetic unavailability |
| vault-redact-invalid-confirmation | POST /api/memory/vault/redact, 422 | error equals validation_error | real production privacy route + real isolated Git vault; synthetic content only |
| vault-redact | POST /api/memory/vault/redact, 200 | action equals redact; changed_files equals 1; replacement_count equals 1; paths equals ['zz-privacy.md']; history_retained_for_rollback equals True | real production privacy route + real isolated Git vault; synthetic content only |
| vault-redacted-read | GET /api/vault/read?path=zz-privacy.md, 200 | content contains <REDACTED> | real production privacy route + real isolated Git vault; synthetic content only |
| vault-restore | POST /api/memory/vault/restore, 200 | restored equals True; paths equals ['zz-privacy.md']; snapshot_commit equals {vault_snapshot} | real production privacy route + real isolated Git vault; synthetic content only |
| vault-restored-read | GET /api/vault/read?path=zz-privacy.md, 200 | content contains QA_PRIVATE_VALUE | real production privacy route + real isolated Git vault; synthetic content only |
| memory-redact-project | POST /api/memory/redact, 200 | ok equals True; scope equals project; changed.project equals 0 | real production route + real isolated stores |
| memory-retention | POST /api/memory/retention, 200 | ok equals True; max_age_days equals 1; deleted.project equals 1 | real production route + real isolated stores |
| memory-retained-current | GET /api/memory/recall?query=qa_marker, 200 | recalled contains QA_SCOPED_MEMORY | real production route + real isolated stores |
| memory-expired-absent | GET /api/memory/export?scope=project, 200 | providers.project.0.key equals qa_marker; vault.included equals False | real production route + real isolated stores |
| browser-approval-pending | GET /api/agent/tools/browser/approval/pending, 200 | count equals 4; gate.pending equals 4; gate.tickets equals 0 | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-policy | GET /api/approval/{browser_pending_id}, 200 | tool_name equals browser_effect; status equals pending; always_allow_allowed equals False | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-unknown-id | POST /api/agent/tools/browser/approval/qa-unknown/grant, 404 | error equals http_404 | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-unresolved | POST /api/agent/tools/browser/approval/{browser_pending_id}/grant, 409 | detail.error_code equals APPROVAL_REJECTED; detail.status equals pending | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-always-forbidden | POST /api/approval/{browser_pending_id}/resolve, 403 | detail.error_code equals always_allow_forbidden | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-deny | POST /api/approval/{browser_denied_id}/resolve, 200 | ok equals True; status equals denied | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-denied-grant | POST /api/agent/tools/browser/approval/{browser_denied_id}/grant, 409 | detail.error_code equals APPROVAL_REJECTED; detail.status equals denied | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-denied-withdraw | POST /api/agent/tools/browser/approval/{browser_denied_id}/withdraw, 200 | ok equals True; withdrawn equals True | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-owner-approve | POST /api/approval/{browser_owner_mismatch_id}/resolve, 200 | ok equals True; status equals approved | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-owner-mismatch | POST /api/agent/tools/browser/approval/{browser_owner_mismatch_id}/grant, 403 | detail.error_code equals APPROVAL_BINDING_CHANGED; detail.context.changed equals ['owner_key'] | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-once-approve | POST /api/approval/{browser_issued_id}/resolve, 200 | ok equals True; status equals approved | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-once-grant | POST /api/agent/tools/browser/approval/{browser_issued_id}/grant, 200 | ok equals True; ticket.binding.action equals goto; ticket.binding.effect equals transmit; ticket.consumed equals False | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-duplicate-grant | POST /api/agent/tools/browser/approval/{browser_issued_id}/grant, 404 | error equals http_404 | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-model-self-approval | POST /api/agent/tools/browser/action, 400 | detail.error_code equals MODEL_CLAIM_REFUSED | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-pending-withdraw | POST /api/agent/tools/browser/approval/{browser_pending_id}/withdraw, 200 | ok equals True; withdrawn equals True | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-owner-withdraw | POST /api/agent/tools/browser/approval/{browser_owner_mismatch_id}/withdraw, 200 | ok equals True; withdrawn equals True | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-withdraw-once | POST /api/agent/tools/browser/approval/{browser_denied_id}/withdraw, 200 | ok equals True; withdrawn equals False | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-completed-queue | GET /api/agent/tools/browser/approval/pending, 200 | count equals 0; gate.pending equals 0; gate.tickets equals 1; gate.consumed equals 0 | real approval HTTP route + real isolated manager/gate; no browser action |
| browser-approval-no-permanent-grants | GET /api/approval/always-allowed, 200 | grants equals []; count equals 0 | real approval HTTP route + real isolated manager/gate; no browser action |
