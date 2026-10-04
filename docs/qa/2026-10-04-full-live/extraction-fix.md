# Authenticated extraction failure regression

Date: 2026-10-04. Scope: extraction page and its API boundary only.

The live failure reported by the root agent was a 401 from metrics and extraction requests after the dashboard had been unlocked. The page used bare fetch calls, omitted the stored bearer credential and active project/session headers, and only logged failures. Null metrics therefore remained visibly loading.

## Change

- `dashboard/src/pages/DataExtractionPage.tsx` delegates all three operations to the existing authenticated API mechanism, shows semantic alerts with named retry actions, exposes request progress with `aria-busy`, and ends loading on every completed failure.
- `dashboard/src/pages/dex/extractionApi.ts` uses existing `apiRequestPath`, parses success/application-failure envelopes with Zod, and preserves extra extraction fields. The real server serializes unavailable numeric fields as null; these normalize to undefined at the existing optional-number UI boundary, preserving its rendering behavior.
- `dashboard/src/pages/DataExtractionPage.test.tsx` exercises the page through a wire-level fetch seam using a nonempty synthetic token, project, revision and session. The API client and credential/project helpers are real. Requests missing bearer/project identity receive 401 from the wire fixture.
- A failed replacement search keeps the previous extraction readable and cached. A/B progress or failure hides a preceding completion label. Metrics with no data show an empty status, distinct from request loading and an error.
- New failure presentation uses existing design tokens and native alert/button semantics. Existing result panels and their styles remain the rendering path.

## Verification

| Evidence | Result |
| --- | --- |
| `extraction-red.txt` | Before implementation: 10 failed. Auth assertions found missing Authorization on all three endpoints; controlled denial and application failure assertions found no alert. |
| `extraction-null-red.txt` | Before null normalization: 1 failed, 14 passed. A valid partial server result was rejected rather than rendered. |
| `extraction-tests.txt` | Final focused Vitest run: 15 passed, exit 0. |
| `extraction-typecheck.txt` | Installed `tsc -b --pretty false`: exit 0, no diagnostics. |
| `extraction-lint.txt` | Installed ESLint on the three changed TS/TSX files: exit 0, no diagnostics. |
| `extraction-no-excuse.txt` | Skill audit unavailable, exit 2: its script requires TypeScript unstable API subpaths absent from the installed compiler. No dependency installation was performed. |
| `extraction-source-hashes.txt` | SHA-256 values for the final three source/test files. |

Commands used installed binaries directly from `dashboard/`:

```sh
node node_modules/vitest/vitest.mjs run src/pages/DataExtractionPage.test.tsx
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/eslint/bin/eslint.js src/pages/DataExtractionPage.tsx src/pages/DataExtractionPage.test.tsx src/pages/dex/extractionApi.ts
```

The 15 scenarios cover request method/path/body, bearer/project/revision/session headers, server 401 and PIN-required event, each operation's explicit retry, HTTP 200 application failures, retained previous extraction, valid partial/null values, retained extra server fields, and empty metrics. Expected outcomes assert structure/state and fixture data rather than fixed user-facing error prose.

The initial `pnpm exec` dependency-status check attempted an install and aborted before completing because there was no TTY. All recorded verification runs use already installed binaries. No dependencies, Git operations, actual credentials, browser sessions, or model calls were used by this worker.

## Live verification handoff

The root agent owns the shared production build and actual authenticated browser revisit. No browser or production-build pass is claimed here. After that build, revisit `/data-extraction`: metrics should resolve; a harmless synthetic search should carry auth/project/session headers; a controlled failed operation should expose a readable alert and retry with loading ended. Search may legitimately return no extracted fields; the successful existing result view should remain distinguishable from authentication or application failure.

Server contract observation: all `/api/*` extraction routes are protected by bearer authentication. The handlers return HTTP 200 `ok:false` on internal application failures. They currently do not consume project identity headers themselves; transmitting the active project metadata does not claim server-side extraction isolation.
