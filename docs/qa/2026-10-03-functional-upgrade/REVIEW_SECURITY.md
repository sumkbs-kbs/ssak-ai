---
title: Functional upgrade security review
tags: [qa, security, frontend, functional-upgrade]
date: 2026-10-03
---

# Security review

- **recommendation:** APPROVE
- **lane result:** PASS
- **blockers:** none
- **exact HEAD:** `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- **source_hash:** `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`
- **task.diff SHA-256:** `10a17e0aa578ca10cffe67fb2362360b383c05393493700318a5fc9544c1d90a`
- **baseline archive SHA-256:** `be88253900d5cf0d543add74b712532b2955fad405da174e5712d7f9b8455689`

## Original intent

Apply the bounded frontend functional upgrade described in `docs/frontend/CODEX_FUNCTIONAL_REVIEW_2026-10-03.md` and `docs/frontend/CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md`: bind asynchronous chat work to its conversation/project/run owner, render progressive output through the existing safe Markdown surface, keep queued inputs and attachment bytes with their owning turn, consume the existing server conversation-fork contract without mutating the source, and make task submit/fork response-loss retry reuse the exact captured request and idempotency key only inside the original identity and credential scope. The patch must not change backend authority, authentication policy, approval policy, dependencies, or the Constitution.

## Desired outcome

Late callbacks cannot write into a different conversation or newer run; queued base64 attachment data remains transient; progressive model text receives the same sanitization as completed text; conversation forks preserve the source and obey server CAS; task retries neither duplicate server work nor replay across project/session/credential changes; credentials and attachment bytes are not added to durable storage or logs; and errors do not expose captured authorization material.

## User outcome review

PASS for the scoped security outcome. The 24-path patch adds client-side ownership and freshness checks around asynchronous writes while leaving server authentication and authorization authoritative. The retry operation captures its bearer header only in React hook memory, compares both the exact current header and a SHA-256 fingerprint before replay, and sends the captured header only to the original request. The fingerprint is a stale-owner detector, not a permission mechanism. No changed production path serializes the operation, credential, fingerprint, or queued attachment bytes to local/session storage or logs.

Progressive chunks update the existing assistant message and therefore flow through `ChatMessage`/`ChatMarkdown`. `ChatMarkdown` already applies `rehype-sanitize` after raw Markdown handling; this patch does not add an alternate HTML rendering path. The existing Mermaid `innerHTML` boundary predates the scoped baseline and is not changed by this patch.

The loopback QA fixture is test-only and mounts production task components against an ephemeral fake service. Its lack of production authentication does not alter or bypass the production client/backend authentication path.

## Security findings

### Critical

None.

### High

None.

### Medium

None that violates a stated success criterion.

### Low / notes

1. `TaskOperationScope` retains both the full authorization header and its SHA-256 fingerprint in memory until the failed operation is cleared or the component unmounts. This is deliberate so an ambiguous response can replay byte-for-byte with the same headers and key. The reviewed code does not persist or log either value. This is not a blocker under the stated memory-only criterion.
2. `isTaskOperationRetryable` treats non-HTTP failures, including response parsing failures, as ambiguous and retryable. The same key makes replay idempotent, and scope is rechecked before replay. This is broader than network-response loss but does not violate an identified security criterion.
3. Conversation fork failures expose `Error.message` in a user toast. Reviewed request libraries do not include request headers in those messages, and the captured bearer header is not interpolated into any error. No secret exposure was reproduced.

## Criterion review

| Criterion | Result | Evidence |
| --- | --- | --- |
| SEC-01 progressive untrusted Markdown retains the existing sanitization boundary | PASS | `dashboard/src/components/Chat/ChatPage.tsx`; `dashboard/src/components/Chat/ChatMarkdown.tsx` (`rehypeRaw` followed by `rehypeSanitize`) |
| SEC-02 queued attachment bytes remain memory-only and bound to their turn | PASS | `dashboard/src/components/Chat/chatRunOwnership.ts`; queue held in `ChatPage.tsx` refs/state; scoped search found no storage/log serialization |
| SEC-03 retry key/request/header identity cannot cross project, revision, session, epoch, or credential owner | PASS | `dashboard/src/features/task-execution/taskOperation.ts`; `taskExecutionApi.ts`; `useTaskExecutionEvents.ts`; focused retry tests |
| SEC-04 owner fingerprint does not become authorization | PASS | fingerprint is only compared locally; `Authorization` remains the request credential and backend remains authoritative |
| SEC-05 fork preserves source and uses server CAS without a client authority bypass | PASS | `dashboard/src/hooks/useConversationFork.ts`; `dashboard/src/api/client.ts`; `chatStore.ts`; fork request omits the forbidden `project_revision` JSON field |
| SEC-06 stale async callbacks cannot mutate a different session/project/run | PASS | run gate plus active session/project/epoch checks in `ChatPage.tsx`; fork invalidation checks in `useConversationFork.ts` |
| SEC-07 new errors do not log or display secrets | PASS | no changed production logging of operations, headers, tokens, fingerprints, or attachment bytes; UI error paths use response/error messages only |
| SEC-08 no backend/auth/approval/dependency policy expansion | PASS | 24-path manifest is dashboard frontend/design/test scope; `dashboard/package.json` is unchanged relative to the baseline |

## Direct slop and programming pass

The diff, production code, and tests were reviewed directly under the `remove-ai-slops` and `programming` criteria. No deletion-only test, test that merely proves requested text/code removal, natural-language prompt pin, tautological expected value, output-derived expected value, speculative production abstraction, or security-relevant catch-and-swallow was found in the scoped patch. Assertions on `Authorization`, project identity fields, retry identity, queue ownership, CAS adoption, and visible failure notices exercise machine-consumed or user-observable contracts. The Korean `toContain` assertion checks an actionable UI notice rather than prompt prose.

Some new helpers exist once (`operationKey`, `authorizationHeader`, `ownerFingerprint`, `captureScope`), but each isolates credential/identity capture at the trust boundary and is used to construct both submit and fork operations; they do not create a security-significant unnecessary parsing or normalization layer. Existing large modules and pre-existing console diagnostics were not made blockers because no stated criterion requires broad refactoring and the scoped changes do not route secrets through them.

No separate code-review report containing its own explicit `remove-ai-slops`/`programming` coverage was present in this evidence directory at review time. This is an evidence NOTE rather than a blocker: the direct pass above covers the required criterion, and no stated security success criterion requires that separate report as an artifact.

## Reproduced evidence

- Rebuilt the dashboard-vs-baseline comparison in memory: exactly 24 changed paths, equal to `changed-files.json`; rebuilt bytes equal `task.diff`.
- Recomputed all 308 manifest file hashes: 0 missing and 0 mismatched.
- Recomputed aggregate `source_hash`: `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`.
- Confirmed checkout HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Re-ran 6 security-relevant Vitest files: 72 tests passed, 0 failed.
- `git diff --check` over all 24 changed paths exited 0.
- Supplied whole-dashboard evidence reports 109 files / 1,088 tests passed, TypeScript exited 0, and the production build completed. Those broad logs were inspected but are secondary to the reproduced focused run.

## Checked artifacts

- `docs/frontend/CODEX_FUNCTIONAL_REVIEW_2026-10-03.md`
- `docs/frontend/CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md`
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-03-functional-upgrade/baseline/dashboard-before.tar`
- `docs/qa/2026-10-03-functional-upgrade/changed-files.json`
- `docs/qa/2026-10-03-functional-upgrade/task.diff`
- `docs/qa/2026-10-03-functional-upgrade/source-manifest.json`
- `docs/qa/2026-10-03-functional-upgrade/CHAT_IMPLEMENTATION.md`
- `docs/qa/2026-10-03-functional-upgrade/FORK_IMPLEMENTATION.md`
- `docs/qa/2026-10-03-functional-upgrade/CHAT_PAGE_FORK_INTEGRATION.md`
- `docs/qa/2026-10-03-functional-upgrade/TASK_IMPLEMENTATION.md`
- `docs/qa/2026-10-03-functional-upgrade/QA_PREPARE.md`
- `docs/qa/2026-10-03-functional-upgrade/dashboard-tests.log`
- `docs/qa/2026-10-03-functional-upgrade/dashboard-typecheck.log`
- `docs/qa/2026-10-03-functional-upgrade/dashboard-build.log`
- all 24 paths in `changed-files.json`, with detailed review concentrated on the production security boundaries and their tests

## Exact evidence gaps

- No completed manual QA matrix or browser verdict artifact was present at review time; `QA_PREPARE.md` explicitly records preparation rather than a product verdict. This does not block this code-level security lane because no security criterion depends on a manual visual result.
- No dedicated static security scanner result was supplied. The scoped patch is frontend TypeScript with no dependency change; direct boundary review, graph-first discovery, exact diff reconstruction, focused tests, typecheck/build evidence, and secret/persistence searches support this security recommendation.
- The full 1,088-test suite, TypeScript check, and production build were not re-run in this lane; their supplied logs were inspected. The security-relevant 72-test subset was independently reproduced against the exact manifest source.

## Recommendation

**APPROVE.** There is no critical or high security regression in the scoped patch and no evidenced failure of a stated success criterion.
