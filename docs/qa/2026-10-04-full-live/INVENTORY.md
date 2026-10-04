---
title: SSAK-AI actual feature inventory for full live QA
date: 2026-10-04
tags: [qa, inventory, live-manual, source-backed, isolation]
status: inventory-only
evidence_scope: current source inspection; live verdicts belong to RESULTS and CHECKLIST
---

# Inventory scope and interpretation

This inventory records actual dashboard and CLI entry points observed in the current
working tree. It is not a test result. No earlier test or QA document is counted as a
current pass. Root owns live browser/model execution and the current PLAN, QUESTIONS,
RESULTS and CHECKLIST. This document's author performed source inspection only.

The codebase-memory graph was checked first. It contains 248 nodes from QA documents
and no code Function/Route nodes, so bounded source searches were used as fallback.
Existing user changes were preserved. No source code, Git state, user memory, raw log,
credential or running model was changed or inspected for this inventory.

The unlocked current browser tab is the live UI surface. A newly opened PIN-locked
tab is not an authorization workaround. Do not bypass authentication to make a test pass.

QA boundaries used below:

- **Live-safe:** navigate the current UI, inspect empty/status/configuration presentation,
  or submit root-authorized synthetic chat questions. Avoid opening existing private
  memory, raw logs, audit content or credential values.
- **Synthetic-only:** test writes, deletions, task/job dispatch, approvals, settings,
  retention or Git operations using a separate temporary project/store/browser fixture.
- **Hardware/external:** real training, model runtime loading, STT/TTS, provider accounts,
  OAuth, publishing, remote pairing, shipping/signing and clean-host installation need
  actual capability or credentials. Source presence is not a live pass.
- **Source candidate:** a source observation to verify manually; it is not a reproduced
  live bug until root records the current result.

## Primary source paths

Repository root: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.

| Source | Role |
| --- | --- |
| `dashboard/src/App.tsx` | Main route registration and app shell |
| `dashboard/src/components/Layout/WorkspaceNavigation.tsx` | Primary/more navigation |
| `dashboard/src/components/Chat/ChatPage.tsx` | Chat execution, queues, retry, compact, fork, attachments and tools |
| `dashboard/src/components/UI/CommandPalette.tsx` | Palette interaction and debounced note search |
| `dashboard/src/features/command-palette/commandRegistry.ts` | Palette actions and note API call |
| `dashboard/src/pages/DataExtractionPage.tsx` | Extraction/A-B test fetches and result presentation |
| `dashboard/src/pages/StudioPage.tsx` | Five-step training UI, job calls and export presentation |
| `dashboard/src/pages/AgentStartPage.tsx` | Copyable external-agent bridge commands |
| `dashboard/src/pages/AgentPage.tsx` | Agency, task, browser approval and monitoring panels |
| `dashboard/src/pages/SettingsPage.tsx` | Models, search, budget, PIN/LAN, history, theme, cache, MCP and logger settings |
| `dashboard/src/pages/HistoryPage.tsx` | File snapshots plus scheduled-job tab |
| `dashboard/src/pages/MutationDashboardPage.tsx` | Validated bundled historical mutation snapshot |
| `dashboard/src/api/client.ts` | Shared typed HTTP/SSE API client |
| `src/antigravity_k/api/routes/__init__.py` | Production API router aggregation |
| `src/antigravity_k/api/server.py` | Auth middleware, metrics, readiness and dashboard serving |
| `src/antigravity_k/cli.py` | Actual Typer command registration |
| `src/antigravity_k/engine/slash_commands_base.py` | Actual slash command catalog |
| `src/antigravity_k/engine/slash_commands_workflow.py` | Finance, benchmark, mode and lifecycle handlers |
| `pyproject.toml`, `setup.py` | Console entry point, package data and build hook |

## Actual feature families and QA surfaces

API paths below are read from production route modules under
`src/antigravity_k/api/routes/`, not inferred from README feature claims.

| Family | Actual UI and API surface | Safe scenario and boundary | Source modules |
| --- | --- | --- | --- |
| Core chat / adaptive agent | `/`, `/chat`; POST `/v1/chat/completions`; GET `/v1/chat/completions/reconnect`; POST `/api/agent/ask` | Root synthetic prompt: stream, stop, error/retry and queued message send/edit/remove/reorder. Live-safe within root's authorized chat scope. | `chat.py`, `agent_ask.py`; `ChatPage.tsx` |
| Conversation lifecycle | Chat/sidebar/history; `/v1/conversations/{id}`, `/append`, `/compact`, `/fork`, `/{id}/history`, `/{id}/export`, DELETE `/{id}` | Synthetic conversation only: hydration, fork retains original, revision conflict, compact/refresh. Delete/export stays synthetic-only. | `conversation_api.py`; `chatStore.ts`, `useConversationFork.ts` |
| Attachments / vision | Chat file/photo picker; completion `attachments` payload | Add/remove a generated image or synthetic document; check unsupported adaptive attachment path. Actual vision generation depends on selected model capability. | `ChatPage.tsx`, `ChatComposer.tsx`, `ChatComposerTools.tsx` |
| Tools / policy / access | Chat search/code/MCP chips; GET/POST `/api/system/access-mode`; `/api/toolsets`, `/activate`, `/{name}/tools` | Inspect selection/status live; synthetic execution proves selected allowlist and restricted access. Changing access policy is synthetic-only. | `system_api.py`; `ChatComposerTools.tsx` |
| Agent monitoring | `/agent`; `/api/agent/active`, `/activity`, `/audit/recent`, `/audit/tool-stats`; `/api/stream_agent`, `/v1/ws/events` | Root synthetic run shows tool/plan/error/quality/approval events. Do not inspect existing private audit records. | `agent_activity.py`, `agent_stream_api.py`, `events.py`; `AgentPage.tsx` |
| Durable tasks | `/agent` task panel; `/api/tasks`, `/submit`, `/{id}/fork`, `/status`, `/output`, `/cancel`, `/resume`, `/steer`, `/events`, `/events/stream`, `/events/ws` | Existing synthetic response-loss fixture: submit/fork idempotency, double-click, scope, replay/reconnect. Production task dispatch is synthetic-only. | `task_api.py`; `features/task-execution/` |
| Persistent agency | `/agent`; `/api/agency/status`, `/objectives`, `/{id}`, `/pause`, `/resume` | Inspect unavailable/paused status; queue/priority/pause/resume with isolated objective store only. | `agency_api.py`; `features/persistent-agency/` |
| Legacy Kanban | `/api/kanban/tasks`, `/{id}/cancel`, DELETE `/{id}`, PUT `/{id}/status`, `/ws/kanban` | API-only fixture lifecycle. Do not equate this with the durable task panel. | `kanban_api.py` |
| Scheduled jobs | `/history` scheduled-job tab; `/plugins/job-operations`; `/api/jobs`, `/health`, `/{id}`, `/pause`, `/resume`, `/trigger`, `/runs`, `/runs/{run}/retry` | Empty/health presentation live; creation, trigger and retry use temporary fixture jobs. | `job_api.py`; `features/job-operations/`, `HistoryPage.tsx` |
| Memory / privacy | `/api/memory/stats`, `/recall`, `/ranked`, `/export`, `/redact`, `/retention`, DELETE `/api/memory`, `/entries`; `/api/memory/vault/{redact,purge,restore}` | Temporary providers/store only: budget, deduplication, corrections, scope, retention/redaction/restore. No production recall/export/delete. | `system_api.py`, `vault_privacy.py` |
| Knowledge / vault | `/wiki`; `/api/vault/config`, `/tree`, `/read`, `/write`, `/sync`; `/v1/notes/search`; palette | Temporary Git vault with YAML-frontmatter Markdown: tree/read/search/render/edit/commit. Live-safe empty/search status only. | `vault_api.py`; `WikiPage.tsx`, `wikiStore.ts` |
| Workspace / project | Sidebar/folder picker; `/api/projects`, `/switch`, DELETE `/{id}`; `/api/fs/workspace`; `/api/execution-context/resolve`; `/api/workspace/context` | Temporary project for switch/remove; confirm project/session identity and stale scope rejection. Browse current non-private metadata only. | `filesystem.py`, `system_api.py`; `projectStore.ts` |
| Editor / code intelligence | Chat inspection/editor; `/api/fs/{list,read,write,mkdir,rename,delete,search}`; `/api/code/inline-suggest`; `/api/code-intel/{index,search,impact}` | Synthetic code/text fixture for search/navigation/diff/save/replace; inline generation requires model. File writes and index operations are synthetic-only. | `filesystem.py`, `code_api.py`, `code_intel_api.py`; `components/Editor/` |
| Terminal / output | Global terminal/output panels; `/ws/terminal` | Connection, auth and disabled-state presentation; harmless command only in a temporary workspace. Opening a terminal may start a shell. | `system_api.py`; `TerminalSession.tsx`, `MultiTerminalPanel.tsx` |
| Git | `/git`; `/api/git/{status,log,diff,branches,graph,file-content,stash/list,add,unstage,commit,branch/create,checkout,branch/delete}` | Read temporary repo status/log/diff; every mutation stays in fixture repo. | `git_api.py`; `GitPage.tsx`, `gitApi.ts` |
| Local file history | `/history`; localStorage snapshots, compare, auto-save/limits/clear | Separate synthetic browser state for manual snapshot and A/B diff; do not clear existing browser history. | `HistoryPage.tsx`, `localHistoryStore.ts`, `components/History/` |
| Models | `/models`, chat selector, settings; `/v1/models`, `/api/models/local`, `/load`, `/default`, `/v1/models/operations`, `/v1/embeddings` | List/filter/sort/quality/capability presentation. Selecting/loading/default-changing may start runtime or persist state; hardware/external or synthetic-only. | `models_api.py`; `ModelHubPage.tsx`, `ModelOperationsPanel.tsx` |
| Training / recipes | `/studio`; `/api/recipes`, `/capabilities`; `/api/training-jobs`, `/{id}`, `/cancel`; `/v1/integrations/unsloth/{capabilities,studio,resources,...}` | Browse five steps, recipe presets and invalid fields without launching. Synthetic job for monitor/cancel; real training is hardware/external. | `recipes_api.py`, `training_jobs_api.py`, `unsloth_studio_api.py`, `unsloth_training_api.py`; `StudioPage.tsx` |
| Voice | API-only `/api/voice/{transcribe,commands,speak}`; no dashboard microphone/STT/TTS control found | Existing synthetic WAV/transcriber fixture checks 422/413 and valid PCM/float. `/commands` creates a job, so isolated only; real STT/TTS is capability/hardware dependent. | `voice_api.py`, `engine/voice_audio.py`, `engine/voice_service.py` |
| Search / extraction | Settings/search chip; `/api/search/{status,evidence,settings,probe,retry}`; `/data-extraction` → `/extract`, `/extraction-metrics`, `/ab-test/run`; cache/timing metrics | Read status; deterministic provider for success/unavailable/no-results and stock/weather/exchange extraction. Live search/probe has network effects. | `search_api.py`, `system_api.py`; `DataExtractionPage.tsx`, `SearchIntegrationPanel.tsx` |
| Finance | Extraction stock/exchange/numeric panels; `/api/search/extract`; slash `/finance`, `/comps`, `/dcf` | Synthetic exact decimals, Korean scales, percent vs percentage points and large integers. Actual DCF/comps calculation is not implemented by the slash handler. | `engine/financial_numbers.py`, `engine/data_extractor.py`, `slash_commands_workflow.py` |
| Skills / marketplace / MCP | `/skills`: All/Marketplace/Search npm/Publish/MCP; `/api/system/skills*`; `/api/mcp/{servers,health,health/refresh,oauth/*}`; chat MCP picker | Catalog/status/empty states live; fake MCP for contract/allowlist. Install/remove/publish/OAuth/revoke is external or synthetic-only. | `system_api.py`; `SkillsPage.tsx`, `pages/skills/`, `McpOAuthPanel.tsx` |
| Frontend plugins | `/plugins`, `/plugins/*`; browser plugin registry | Separate browser storage for example plugin enable/disable and registered routes. | `PluginPage.tsx`, `plugin/PluginPanelRoutes.tsx`, `plugin/pluginRegistry.ts` |
| Evaluation / cognitive core | `/mutation` snapshot; POST `/api/benchmarks/decisions/evaluate`; `/api/harness/{status,results,trend,self-test}`; `/api/cognitive/surface/{status,reach,stream,active/*}` | Synthetic decision JSON and finite SSE; mutation source/freshness/filter display. Active execution/observe and self-test run only isolated. | `decision_evaluation_api.py`, `cognitive_surface_api.py`, `cognitive_active_api.py`, `system_api.py`; `MutationDashboardPage.tsx` |
| Approval / browser / agent tools | `/agent` queues; `/api/approval/{pending,always-allowed,{id},resolve,reset-always-allowed}`; `/api/agent/tools/browser/*`, `/fs/read`, `/fs/write`, `/shell/run`, `/external-brain/list`, `/external-brain/send`, `/tdd-generate` | Empty pending state live; synthetic approval/browser/tool fixtures. Do not send external-brain messages or authorize real risky actions. | `approval_api.py`, `agent_tools.py`; `features/browser-approval/` |
| Admin / security | `/settings`; `/api/settings`, `/env`, `/env/delete`; `/api/auth/{login,change-pin,token,verify,logout,ws-ticket,status}`; `/health`, `/v1/health`, `/api/ready`, `/metrics`; `/api/system/*`, `/api/shields/*`, `/api/security/*`, `/api/alerts` | Read status/settings presentation; synthetic auth server for credential/WS/redaction boundaries. Production PIN/settings/log-level/restart mutation excluded. | `system_api.py`, `security_api.py`, `operational_alerts.py`, `api/auth_routes.py`, `api/server.py` |
| Agent compatibility / remote / services / provenance | `/start` copyable commands; `/v1/messages`, `/v1/responses`; `/api/gateway/messages`; `/api/remote/pairing/*`; `/api/workspace/services/*`, `/api/workspaces/links`; `/api/tasks/{id}/provenance*` | Static copy and read/schema checks. Pairing/relay/service launch/gateway/provenance dispatch require isolated fixture; external agents not invoked. | `AgentStartPage.tsx`, `messages_api.py`, `responses_api.py`, `gateway_api.py`, `remote_pairing_api.py`, `workspace_services.py`, `workspace_links.py`, `artifact_api.py` |

## CLI and packaging inventory

Actual `agk` commands: `--version`, `serve`, `dev`, `models`, `model list/set`,
`status`, `run`, `recipes`, `train-recipe`, `fuse-and-serve`, `session`, `start`,
`task list/status/output/resume`, `memory aliases/alias-set/alias-remove/list/remove/retain`,
`doctor`, `key set/list/remove/rotate`, `mode`, `tui`, `ask`, `market`, `autopilot`,
`fast`, `error list/inspect/prompt`, `diagnostics export`, `cognitive status/surface`,
and `decision-eval INPUT.json`.

`run` supports prompt plus `--model`; the current registration does not contain the
README's `run --mode collective`, `rag`, `vault` or `security` command examples.
Normal `doctor` creates directories and a write-test file; it is not read-only.
Model listing probes local discovery. Task/memory/error output can contain existing
private data. Root help/catalog/synthetic evaluation are the safe current CLI slice.

Distribution: `antigravity-k`, Python >=3.12, entry point
`agk = antigravity_k.cli:app`. Package data includes `config.yaml`, `py.typed`,
dashboard assets, prompts, benchmark JSON, release SBOM/notices and the pinned
vendored ssak-search bundle. `setup.py` rebuilds selected package-data paths under
the build output root. `scripts/vendor_ssak_bundle.py --check` verifies pinned
artifacts without materializing changes. `scripts/verify_ssak_bundle.py` supports
offline-start, clean-room and rollback test lanes; they are distinct from a live
desktop distribution pass. DMG signing/notarization/update/clean-host installation
and other-platform claims remain hardware/external checks.

## Exact command-palette note search action

1. Open Cmd+K/Ctrl+K outside the Monaco editor (the global shortcut is suppressed
   while Monaco has focus).
2. Type any nonempty **plain query** in the `검색어 입력` combobox. No prefix or
   selection of `Search Notes` is required.
3. Wait for the 300 ms debounce plus the HTTP result. `handleInput` schedules
   `performSearch(value)`, which calls `searchNoteCommands(value)` and GET
   `/v1/notes/search?q=...`.
4. An arbitrary no-match query initially shows `No results found` from local
   filtering. A successful empty note result keeps it empty. A failed remote
   search eventually shows disabled `Error searching notes` / `Search unavailable`
   when there are no local command matches. A matching local command can mask
   that failure presentation.

The built-in `Search Notes` action itself has `execute: () => undefined`; selecting
it closes the palette and does not trigger a note search. Sources:
`dashboard/src/components/UI/CommandPalette.tsx:77` and
`dashboard/src/features/command-palette/commandRegistry.ts:168`.
Root's observed no-result query is not classified here as either a live 401 or a pass.

## Existing isolation harnesses and safe current-task commands

`docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py` patches `Path.home`
before production imports, supplies temporary synthetic auth, and redirects config,
model/data/log/wiki paths. Modes are CLI, pytest and HTTP; HTTP lifespan is off.
Its pytest mode also uses `subprocess_home.py` to isolate subprocess home.
This is suitable for the commands below, but not blanket whole-app isolation:
it does not explicitly override task DB, cwd or project root, and an explicit
output argument can still write outside the temporary home.

Run from `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`; these commands have not
been executed or marked passed by this inventory author:

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py cli --help
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py cli recipes
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py cli decision-eval docs/qa/2026-10-03-oh-my-jev-upgrade/sample-input.json
.venv/bin/python scripts/vendor_ssak_bundle.py --check
```

Additional reusable harnesses:

- `docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py`: explicitly
  isolates task DB/project paths/cwd and mounts production extraction/voice routers
  with deterministic search and synthetic transcriber on 8047. Its `fixtures`
  command creates synthetic WAVs. This verifies router boundaries, not production auth.
- `docs/qa/2026-10-03-functional-upgrade/fixture/qa-fixture-server.py`: ephemeral
  loopback process-local task fixture mounting production task components;
  `QA_PREPARE.md` lists 24 scenarios and five edge augmentations. It does not write
  production task/vault stores. Build outputs/symlink stay within that fixture directory.
- `tests/conftest.py`: session/auth/benchmark/usage/browser state isolation plus
  login-security and execution-context resets; before-import home isolation still
  matters when collection imports code before fixtures.
- `tests/_cli_subprocess.py`: project-aware interpreter selection for subprocess CLI QA.

## High-value current manual checks and source candidates

The following are startable checks, not reproduced current failures:

1. Authenticated data extraction and palette note search/vault sync. The relevant
   `DataExtractionPage.tsx` bare fetches and `commandRegistry.ts` bare ky calls do not
   add the shared credential headers. Confirm actual current request/UI behavior
   before recording an auth defect; source inspection alone is insufficient.
2. Studio export/capability: the final source reread observed shared changes to
   `StudioPage.tsx`. Export/register controls are now disabled with an explicit
   unavailable notice (`StudioPage.tsx:702`); the former success-toast-only handler
   is absent. Memory telemetry comes from capability system memory, and training
   admission depends on the MLX training capability. Verify these current UI states;
   the earlier fake-export/hardcoded-VRAM observation is not a current defect claim.
3. Agent-start status: `AgentStartPage.tsx` renders copyable bridge instructions and
   a hardcoded Cloudflare Tunnel ready label. Do not count it as a live tunnel check.
4. Finance: `slash_commands_workflow.py:415` returns readiness text for `/finance`,
   `/comps` and `/dcf`; no valuation or skill activation is performed by that handler.
   Exact numeric extraction is implemented; DCF/comps is separate future work.
5. Palette `Self-Test` and `Test-Driven Code Generation` entries currently emit only
   toasts. The actual backend harness/TDD routes are separate surfaces.
6. Streaming/retry/queues/task-fork/conversation-fork across tab and project changes:
   stale results must not mutate the newly selected scope.
7. Keyboard-only dialogs, focus return, IME Enter, clipboard, narrow layout,
   reload/deep links, 404 recovery and unavailable-model/MCP/voice/terminal states.
8. Mutation page provenance and stale labeling: it is a bundled historical snapshot,
   not a current mutation test execution result.

## Existing product and data constraints

Vault notes follow Files-first/Git-first: YAML frontmatter and VaultEngine/explicit
commit handling. This QA document is not a vault note and no Git operation was made.
`docs/adr/0003-ga-product-scope.md`, `docs/ga/GA_SUPPORT_MATRIX.md` and
`docs/ga/GA_DATA_PRIVACY_OPERATIONS.md` limit claims to the documented operator and
data scope. The support matrix currently has zero Supported classifications;
native distribution, multi-user concurrency and hardware/provider staging cannot
be promoted by source presence or old tests. Credentials never belong in evidence;
production memory/export/log content is outside this synthetic inventory scope.
