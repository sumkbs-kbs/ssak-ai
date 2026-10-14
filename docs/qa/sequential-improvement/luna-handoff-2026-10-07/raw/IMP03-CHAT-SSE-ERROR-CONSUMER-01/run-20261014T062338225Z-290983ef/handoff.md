# IMP03-CHAT-SSE-ERROR-CONSUMER-01

Scoped offline parser and consumer fix. The current producer in `src/antigravity_k/api/routes/chat.py` sends a typed provider error envelope and returns without `[DONE]`. Previously the dashboard ignored that envelope, completed at EOF, and ChatPage dispatched the next queued turn. The RED component test directly observed two chat requests instead of one.

The change adds a private Zod schema and private Error subclass in `dashboard/src/api/client.ts`. Recognized protocol and transport envelopes now throw into the existing `onError` boundary. Partial deltas remain delivered; `onDone`, later final content, and queue dispatch do not run after the error. Existing ChatPage failure handling retains the queued message. No ChatPage production change, APIs, stores, dependencies, or UI styling changed.

Only three assigned files changed. `preimage/` holds their exact incoming dirty-tree bytes. `task-only.patch` is relative to those bytes, not HEAD. `patch-reconstruction.json` records application of that patch to separate preimage copies and equality with the tested/current source. Existing unrelated edits are preserved. No staging, commit, push, live model/provider, browser, or full application validation was performed.

## Invocations and observables

All invocation working directories, start/end timestamps, exit statuses, and complete argv are in each phase's `receipts.json`. Run commands from the repository root:

```sh
node docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP03-CHAT-SSE-ERROR-CONSUMER-01/run-20261014T062338225Z-290983ef/capture.mjs red
node docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP03-CHAT-SSE-ERROR-CONSUMER-01/run-20261014T062338225Z-290983ef/capture.mjs green
node docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP03-CHAT-SSE-ERROR-CONSUMER-01/run-20261014T062338225Z-290983ef/capture.mjs checks
```

These are the recorded historical invocations, not an instruction to overwrite them. For a new validation use a new owned directory and preserve RED source separately. Both test phases invoke `pnpm exec vitest run src/api/client.test.ts src/api/client.streamChannels.test.ts src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx --reporter=verbose --reporter=json --outputFile.json=<phase>/vitest.json` from `dashboard/`.

| Scenario / exact case prefix | Binary observable | Captured artifacts |
| --- | --- | --- |
| `reports %s/%s once after partial content without completing at EOF` (six recognized type/code pairs) | partial chunk preserved; Error instance exactly once with type/code/message; onDone=0; fetch=1 | `red/vitest.json`, `green/vitest.json`, phase `tests.stdout` and source snapshots |
| `stops on a typed stream error with split framing` | one-character chunks still produce partial then error only | same parser artifacts |
| `stops on a typed stream error with unterminated framing` | EOF flush produces error, never completion | same parser artifacts |
| `stops on a typed stream error with trailing-success framing` | later authoritative final and DONE do not reach handlers | same parser artifacts |
| `keeps legitimate content when an unrelated or malformed error field is %j` (seven inputs) | ordinary error string/content and malformed envelopes retain content + done | same parser artifacts |
| `preserves the queued turn and partial answer when the real parser receives a typed stream error` | actual parser + rendered ChatPage: request count=1, queued turn remains, partial answer remains, failure displayed, only first user message recorded | `red/tests.stderr` captures count=2 failure; `green/vitest.json` and `green/source/dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx` capture passing assertions |
| Existing final/status, DONE, unterminated content, split UTF-8, abort and typed revision-conflict scenarios | original assertions remain passing | `green/vitest.json` lists every full case name/status |
| `pnpm exec tsc --noEmit --pretty false` | exit=0 | `checks/receipts.json`, `checks/typecheck.stdout`, `checks/typecheck.stderr` |
| `pnpm exec eslint src/api/client.ts src/api/client.streamChannels.test.ts src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx` | exit=0 | `checks/receipts.json`, `checks/lint.stdout`, `checks/lint.stderr` |
| `git diff --check -- <three owned files>` | exit=0 | `counts-and-checks.json` |

RED: 59 tests, 49 passed and 10 failed (nine parser failures plus the real consumer queue failure). GREEN: 59 passed, 0 failed, 0 skipped. Counts are phase-specific, never summed. No relevant check was skipped. The editor LSP hook could not initialize its TypeScript installation; the installed project `pnpm exec tsc` completed successfully, so no editor-LSP claim is made.

All dashboard source/test and relevant configuration inputs are hashed before/after each validation phase; phase receipts require unchanged inputs. `artifact-manifest.json` binds the evidence files, and `counts-and-checks.json` derives counts/cases directly from the Vitest reports. Empty stderr files are expected on successful static checks; the nonempty receipts record their actual status.

## Boundary and next owner

This is fixture-backed parser and jsdom consumer evidence. Fetch is replaced with an in-memory stream; no live SSE endpoint, browser rendering, external network, provider quality, release readiness, or full-app PASS is established. Root owns independent review and publication using the exact patch/bindings. Malformed or unknown error shapes retain the existing ignore/normal-content behavior; only the two current producer types and their six existing codes are recognized. Generic EOF behavior and abort-as-completion are unchanged.
