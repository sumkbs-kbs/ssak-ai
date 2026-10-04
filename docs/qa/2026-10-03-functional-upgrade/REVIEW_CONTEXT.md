---
title: Functional upgrade context-mining review
date: 2026-10-03
tags: [qa, context-review, codex, functional-upgrade]
---

# Context-mining review

## Verdict

**PASS**

The task baseline is internally consistent and the selected implementation scope is traceable to both the Korean source brief and the pinned public Codex source. I found no missed requirement that contradicts or invalidates the three implemented functional upgrades. The implementation diff stays in the dashboard consumer/state layer and does not alter the SSAK-AI Constitution, Brain/Body semantic authority boundary, Files-first/Git-first contracts, append-only history policy, or minimum-sufficient-context policy. The prior Codex visual system is reused; no font, color-token, stylesheet, or layout redesign appears in `task.diff`.

## Baseline identity

- `exactHEAD`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- `source_hash`: `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`
- Recomputed current dashboard source hash: `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309` across 308 files.
- Pinned upstream checkout: `/tmp/openai-codex-research` at `55b6f282a810c3146a1f79c7c2e6e919cc0aa974`.
- Task patch SHA-256: `10a17e0aa578ca10cffe67fb2362360b383c05393493700318a5fc9544c1d90a`.
- The worktree has 540 status entries. Review therefore used the captured pre-task tar, `task.diff`, `changed-files.json`, and source manifest rather than treating the dirty HEAD diff as task scope.

## Original intent and desired outcome

The original Korean brief establishes SSAK-AI as a persistent adaptive cognitive system whose Primary Brain remains the semantic reasoner while the Body owns state, context construction, evidence provenance, tool execution, verification, risk, authority, action governance, and experience persistence. Brains are replaceable; present state has primacy; historical understanding is appended rather than rewritten; context is minimum sufficient and progressively expandable; human authority remains final for constitutional and protected decisions.

For this functional-upgrade pass, the concrete user outcome is a precise comparison between the latest current folder and pinned public OpenAI Codex behavior, followed by useful upgrades that fit those contracts while retaining the prior Codex UI, fonts, and styling. The accepted implementation slice is:

1. conversation/run ownership with progressive assistant output, stable reading position, and queued text-plus-attachment ownership;
2. server-backed conversation fork using existing CAS/history authority and preserving the source conversation;
3. explicit idempotent retry for task submit/fork after ambiguous response loss, scoped to the captured project/session/owner.

## Searched sources

| Source | What was checked |
|---|---|
| `/Users/mr.k/.codex/attachments/79d687aa-9f85-452d-93a0-037147549122/붙여넣은 텍스트.txt` (`94b175...918e`) | Constitutional invariants, Brain replaceability, Primary-Brain semantic authority, Body evidence/authority duties, current-state primacy, append-only understanding, minimum sufficient context, human authority, approval restraint. |
| `docs/frontend/CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md` (`fe4878...aae1`) | Exact P0/P1 scope, acceptance conditions, ownership, dirty-tree baseline rule, exclusions. |
| `docs/frontend/CODEX_FUNCTIONAL_REVIEW_2026-10-03.md` (`05d311...c6d0`) | Upstream/current comparison, selected/kept/deferred/rejected features, request-ID caveat, architecture constraints. |
| `docs/frontend/CODEX_REFERENCE_2026-10-03.md` (`dda04c...ec5`) | Pinned-source inventory and distinction between public Rust CLI/TUI/app-server and an unavailable Desktop React stylesheet implementation. |
| `docs/qa/2026-10-03-functional-upgrade/task.diff` | All 24 task-scoped changed files; production state transitions, tests, command-palette wiring, and absence of visual-token/font changes. |
| `changed-files.json`, `source-manifest.json`, `bundle-manifest.json`, pre-task dashboard tar | Scope integrity, exact source identity, built bundle provenance. |
| `CHAT_IMPLEMENTATION.md`, `FORK_IMPLEMENTATION.md`, `CHAT_PAGE_FORK_INTEGRATION.md`, `TASK_IMPLEMENTATION.md`, `DEBUG_JOURNAL.md`, `QA_PREPARE.md` | Executor claims, red/green narratives, fixture boundary, retained/deferred runtime work. Claims were cross-checked against the task patch and current files rather than accepted as proof by prose. |
| Dashboard test/typecheck/build/backend logs | `109/109` test files and `1088/1088` tests passed; TypeScript log is empty on success; production build completed; isolated backend contract suite reports `26 passed`. |
| `/tmp/openai-codex-research` pinned files | Turn/event identity and delta mapping, thread fork/resume contracts, plan/read-position examples, structured user input, request correlation, compaction/history budgeting, archive/review/revert contracts. Confirmed that JSON-RPC request IDs correlate requests and responses; they are not an idempotency/deduplication guarantee. |

The repository-directed code graph was not available as a callable tool in this review environment. I used the captured task diff and exact-file reads for code cross-references, which is the documented fallback when graph tooling is unavailable or insufficient.

## Requirement coverage

| Requirement | Evidence and conclusion |
|---|---|
| Latest current folder, exact baseline | HEAD and 308-file dashboard hash reproduce the manifest. The review does not reuse the historical 1193-test core PASS or reopen its stale NO-GO findings. |
| Precise public Codex reference | All comparisons pin `55b6f282...a974`; the review correctly limits upstream claims to public Rust CLI/TUI/app-server. |
| Run ownership/progressive output | `ChatPage.tsx` and `chatRunOwnership.ts` bind callbacks to run generation plus session/project/epoch, invalidate synchronously on navigation/Stop, render chunks into one assistant entry, retain user scroll, and keep queued attachments with their turn. |
| Conversation fork | `useConversationFork.ts`, `client.ts`, `chatStore.ts`, ChatPage, and the command registry consume the existing server CAS/history contract, adopt a distinct session, preserve the source, and reject stale adoption. |
| Task idempotent retry | `taskOperation.ts`, `taskExecutionApi.ts`, `useTaskExecutionEvents.ts`, and queue/view wiring preserve an immutable request/key for ambiguous network or 5xx outcomes, reject scope/owner drift, and issue fresh keys for fresh intent. |
| Constitution / Brain / Body / authority | No core or backend protocol file is in task scope. Changes structure client state, provenance, ownership, and action safety; they do not perform semantic reasoning or elevate UI/runtime state over Primary Brain or human authority. |
| Files/Git first and append history | Fork is additive and source-preserving; stale server-created forks are not auto-deleted. Destructive rollback was explicitly rejected. No canonical history is erased to meet a context budget. |
| Minimum sufficient context | Existing canonical compaction/context assembly remains unchanged. The task adds ownership metadata only where needed for safe execution and retry. |
| Prior UI/fonts/styles retained | The patch adds existing native controls/statuses and design documentation. It contains no CSS/font/token modifications. |
| Deferred contracts remain explicit | Typed ask-input, MCP structured/media results, durable archive/restore, and first-class review target/session remain documented as requiring new backend/authority contracts. They are not silently presented as implemented. |

## Direct programming and slop/overfit pass

I directly reviewed production and test additions under the `programming` and `remove-ai-slops` criteria.

- The new tests exercise observable races, request bodies, scope transitions, response loss, one-task idempotency, native control behavior, and source preservation. They are not deletion-only tests, tests that merely assert requested removal, or natural-language prompt snapshots.
- The request-body tests pin a machine-consumed wire schema and the absence of the invalid `project_revision` field; this is a real contract rather than prose or implementation-only formatting.
- The run-ownership and fork tests use deferred promises and navigation/Stop/project transitions to distinguish stale and current operations. They are not tautologies derived from the output under test.
- `chatRunOwnership.ts`, `taskOperation.ts`, and `useConversationFork.ts` correspond to multiple consumers or a durable async boundary. I found no unnecessary parsing/normalization layer introduced only to satisfy tests.
- No new dependency, custom stylesheet, duplicate store, synthetic success state, or semantic decision engine was added.
- `ChatPage.tsx` remains oversized and gained orchestration code. This is maintenance debt, but it predates this task and does not violate a stated functional acceptance criterion; it is a NOTE, not a blocker.
- The module-level queued-turn numeric ID is process-global. It is used as a UI record identity and does not cross a persistence or authority boundary. No criterion fails on this basis.

## Missed requirements

None found within the stated implementation scope.

The upstream review identified additional useful Codex capabilities, but the following are intentionally deferred with explicit contract prerequisites rather than missed: typed ask-input; MCP structured/media result delivery; durable archive/restore; first-class review sessions; arbitrary-turn fork; server turn steering. Implementing any of these in this patch would require backend protocol, replay, provenance, or authority work outside the approved consumer-layer scope.

## Blockers

None.

## Skipped sources and exact evidence gaps

- GitHub CLI remote queries: skipped after the known `401 Bad credentials` condition. Authentication was not modified and no credential material was printed. The pinned anonymous clone supplied the required source evidence.
- Slack and Notion: unavailable and unnecessary for the repository-scoped brief; no plugin or connector installation was attempted.
- Private Codex Desktop React source/style implementation: unavailable in the public checkout. No parity claim depends on it.
- A final manual-QA matrix and final code-review report were not present in this evidence directory at the time of this context-mining pass. Those are downstream gate artifacts and do not change this report's conclusion about requirement selection and source fidelity. They must still be checked by the final gate before product approval.
- Live authenticated parent-dashboard response-loss interaction is not proven by the fixture documents alone. `QA_PREPARE.md` explicitly reserves that verdict for the manual-QA owner.

## Recommendation

Proceed to code-quality, manual-QA, and final gate review using this exact HEAD/source hash. Do not substitute later working-tree state or reuse an older PASS.
