---
title: Functional upgrade final goal and constraint review
date: 2026-10-03
tags: [qa, goal-review, functional-upgrade, codex]
---

# Final goal and constraint review

## recommendation

**APPROVE / PASS**

## identity and boundary

- Exact HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Exact source hash: `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`
- Baseline archive: `docs/qa/2026-10-03-functional-upgrade/baseline/dashboard-before.tar`, SHA-256 `be88253900d5cf0d543add74b712532b2955fad405da174e5712d7f9b8455689`
- Reviewed patch: `docs/qa/2026-10-03-functional-upgrade/task.diff`, SHA-256 `10a17e0aa578ca10cffe67fb2362360b383c05393493700318a5fc9544c1d90a`
- Scoped paths: the 24 entries in `changed-files.json`. The broad dirty worktree was not treated as this task's diff.
- `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`, so the required report path falls back to this task evidence directory.

I independently recomputed every one of the 308 source-manifest file hashes with zero mismatches and reproduced the aggregate source hash above. The baseline archive hash and current Git HEAD also reproduce exactly.

## originalIntent

Precisely inspect the pinned public OpenAI Codex source and apply the remaining useful functional upgrades to the current SSAK-AI workspace, while preserving SSAK-AI's Constitution, replaceable Brain / stateful Body boundary, evidence and authority model, source-preserving history, minimum-sufficient context, existing UI, and system-font design. Public Codex is correctly described as the Rust CLI/TUI/app-server at `55b6f282a810c3146a1f79c7c2e6e919cc0aa974`; this work does not claim access to or parity with a private Desktop React implementation, and does not misstate JSON-RPC request IDs as idempotency keys.

## desiredOutcome

1. A chat run belongs to one session, project, and run generation. Stop/navigation invalidates it synchronously; late chunks, snapshots, errors, history responses, and finalizers cannot mutate a different conversation or newer run.
2. SSE output appears progressively without stealing a reader's manually moved scroll position. Queued text and attachment bytes remain owned by the queued turn; failed parents pause the queue and retain it for explicit edit or resend.
3. Conversation fork uses the existing server CAS/history contract, preserves the source conversation, adopts canonical fork history as a distinct session, rejects stale completion, and is discoverable through both a native button and the command palette.
4. Task submit/fork creates a fresh key for fresh intent and reuses the exact captured operation/key only for an ambiguous retry in the same project/session/owner scope. Failure retains the draft; confirmed success clears only the matching draft generation and selects the authoritative server task.
5. Typed ask-input, structured MCP/media delivery, durable archive/restore, and first-class review contracts remain explicitly deferred rather than represented as implemented.

## userOutcomeReview

The shipped scoped artifact satisfies the selected functional outcome. The run gate, captured conversation/project identity, transition invalidation, history revision guard, attachment-owned queue records, failure-pause behavior, canonical fork adoption, and captured task operation are present in production code and exercised by adversarial deferred-promise and response-loss tests. The fork and compact bodies omit the invalid `project_revision` JSON field while retaining identity headers. No backend authority, approval policy, Constitution, stylesheet, font, or dependency change appears in the task patch.

The live evidence shows the existing SSAK-AI chat surface at the captured responsive widths with the new named fork action and existing response/UI design intact. The task fixture capture shows the actual production task panel after controlled response loss with the draft retained and the named `같은 작업 다시 시도` action visible. `task-browser-first-state.json` records the completed submit and fork recovery boundary: three total tasks and one submit key plus one fork key, each attempted exactly twice. This is consistent with one committed server task per same-key retry.

## acceptance criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| C1 exact current source and bounded dirty-tree scope | **ACHIEVED** | HEAD, 308/308 manifest hashes, aggregate source hash, baseline tar hash, `task.diff`, and 24-path `changed-files.json` independently reproduced. |
| C2 precise pinned public Codex comparison without Desktop/JSON-RPC overclaim | **ACHIEVED** | `CODEX_FUNCTIONAL_REVIEW_2026-10-03.md`, `CODEX_REFERENCE_2026-10-03.md`, `REVIEW_CONTEXT.md`; upstream pinned at `55b6f282...a974`. |
| C3 session/project/run isolation, including Stop/new-send and stale history | **ACHIEVED** | `ChatPage.tsx`, `chatRunOwnership.ts`, `ChatPageRunOwnership.test.tsx`, `ChatPageHydration.test.tsx`; focused and full suites green. |
| C4 progressive SSE and reading-position preservation | **ACHIEVED** | chunk updates the existing assistant message; near-end tracking and explicit latest-response control in `ChatPage.tsx`; ownership suite covers pre-completion output and scroll behavior. |
| C5 queued text plus attachment ownership; failure pauses automatic continuation | **ACHIEVED** | immutable queued turn copies attachment records; queue editing restores owned bytes; failed SSE/CAS/Adaptive paths retain the queue and stop continuation; focused regressions include attachment preservation. |
| C6 source-preserving canonical conversation fork/button/palette | **ACHIEVED** | `useConversationFork.ts`, `adoptForkedSession`, client wire tests, ChatPage integration, command registry, fork hook and integration suites. |
| C7 immutable same-key task submit/fork retry scoped to project/session/owner | **ACHIEVED** | `taskOperation.ts`, `taskExecutionApi.ts`, `useTaskExecutionEvents.ts`, API-failure and hook tests; fixture state records each recovery key at two attempts with no duplicate task. |
| C8 failed input preservation and confirmed matching-draft clear | **ACHIEVED** | `TaskQueuePanel.tsx` generation match; view/queue regressions cover failed edits, identical-text re-edit, retry success, and fork not clearing submit input. |
| C9 preserve Constitution, Brain/Body authority, history, UI, and fonts | **ACHIEVED** | task diff is dashboard consumer/state/test/design only; no core authority, backend protocol, CSS/font/token, or dependency changes; fork is additive and source preserving. |
| C10 current automated verification | **ACHIEVED** | Independent review: 9 files/85 tests and `tsc -b` exit 0. Manual-QA preparation rerun: 13 files/102 tests and `tsc` exit 0. Supplied full run: 109 files/1,088 tests, typecheck and production build green. `git diff --check` clean. |
| C11 actual screen/behavior evidence | **ACHIEVED for the selected slice; partial breadth** | Responsive chat captures and DOM text; response-loss task captures at 375/768/1280; `task-browser-first-state.json` for completed same-key submit/fork recovery. Parent authenticated scope-switch/auth scenarios were not claimed as live browser coverage and remain directly covered by focused tests. |
| C12 new durable ask-input/MCP media/archive/review contracts | **DEFERRED by scope, not a failure** | Explicitly documented with their required backend, replay, provenance, and authority prerequisites. Full Codex parity was not a criterion. |

## direct programming and remove-ai-slops review

I loaded and directly applied the `omo:programming` TypeScript criteria and `omo:remove-ai-slops` criteria to the production diff and tests. The repository graph tools requested by `AGENTS.md` were unavailable, so I used the permitted exact-source/diff fallback.

- No deletion-only test, requested-removal test, prompt-prose pin, tautology, output-derived expectation, or implementation-mirroring test was found. Tests distinguish real races and observable wire/UI behavior using deferred promises, store transitions, HTTP failure classes, and stable user controls.
- The new ownership, fork, and task-operation modules correspond to genuine asynchronous trust/identity boundaries and multiple consumers. They do not add speculative parsing, normalization, compatibility shims, or dependencies.
- No newly added `any`, TypeScript suppression, non-null assertion, credential logging, attachment persistence, or synthetic success state was found.
- `ChatPage.tsx` and `useTaskExecutionEvents.ts` exceed the skill's preferred 250 pure-LOC threshold. The former was already oversized in the baseline; the latter was already over the threshold and receives a bounded operation seam. Module size is maintenance debt, but no stated functional criterion requires a restructuring, so this is a NOTE rather than a blocker.
- `null as string | null` was called out by the separate code review, but it is present verbatim in the captured pre-task source. It is not introduced by this task and is therefore a nonblocking inherited note.

The separate `REVIEW_CODE.md` explicitly records its own `programming` and `remove-ai-slops` pass, including deletion-only, tautological, implementation-constant, prompt-prose, unnecessary parsing/normalization, and strict-typing coverage. I reproduced that perspective directly rather than relying on the report.

## checked artifact paths

- `docs/frontend/CODEX_FUNCTIONAL_REVIEW_2026-10-03.md`
- `docs/frontend/CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md`
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-03-functional-upgrade/{baseline/dashboard-before.tar,task.diff,changed-files.json,source-manifest.json,bundle-manifest.json}`
- all `*IMPLEMENTATION.md`, `QA_PREPARE.md`, and `DEBUG_JOURNAL.md` in this evidence directory
- all 24 current paths in `changed-files.json`, including full production ownership/fork/retry sources and their related tests
- `dashboard-tests.log`, `dashboard-typecheck.log`, `dashboard-build.log`, `backend-contract-tests-isolated.log`, `fixture-final-build.log`, and `fixture/http-verification.txt`
- `REVIEW_CODE.md`, `REVIEW_CONTEXT.md`, `REVIEW_SECURITY.md`, and `EVIDENCE_LEDGER.md`
- responsive chat/task captures and associated DOM/button metadata
- `task-browser-first-state.json`, `live-bundle.json`, `review-source-integrity.txt`, `review-focused-vitest.txt`, and `review-fixture-readonly.txt`

## exact evidence gaps and notes

- The response-loss fixture provides live browser evidence for visible failure/retry state and final server counts. It does not provide live parent-dashboard project-switch or credential-invalidation interaction. Those cases have direct current-source unit coverage and are described accurately as test evidence.
- The supplied full-suite/typecheck/build logs were inspected and supplemented by independent focused tests/typecheck; this reviewer did not independently rerun the entire 1,088-test suite or rebuild production.
- The initial backend contract run failed on the sandboxed `~/.antigravity` lock. The isolated rerun is the applicable result and reports 26 passed; no backend file is in task scope.
- Static/security scanning is N/A for this frontend-only patch with no dependency change; direct security review and `REVIEW_SECURITY.md` found no blocker.
- The three chat capture names describe requested widths, but the 768 and 1280 JPEGs share the same 757-pixel image width. Their DOM/capture metadata and task fixture screenshots provide the responsive evidence used here; no claim of pixel-perfect Desktop parity is made.

## blockers

None.
