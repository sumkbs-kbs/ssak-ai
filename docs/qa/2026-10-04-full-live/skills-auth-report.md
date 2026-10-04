---
title: Skills Browser authentication and truthful state repair
date: 2026-10-04
tags: [qa, skills, frontend, authentication]
---

# Skills Browser repair

Candidate base commit: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` supplied by root. This is a shared working-tree patch; coverage binds to `skills-auth-hashes.txt`, not to the base commit alone. No Git mutation was performed.

Root observed unlocked `/skills` returning 401 at 16:17:11 and 16:17:36 UTC, then displaying All Skills/Marketplace/MCP as zero. Source confirmed that `SkillsPage` used bare `fetch`, omitted the shared authenticated project identity, and swallowed request failures. Its legacy test explicitly expected the false empty state after a failed response; that assertion was replaced by the correct visible-failure contract.

## Implemented behavior

- Catalog, installed skills, MCP, npm search, install and remove use existing `apiRequestPath`. This supplies the existing bearer/project/revision/session headers and 401 PIN recovery event. The shared API client and server routes are unchanged.
- Zod parses success envelopes and required response arrays. HTTP 200 `ok:false` and malformed data become visible failures, with safe error text and retry controls. Unknown counts remain `미확인`; a valid empty response becomes zero.
- Prior successful catalog data remains readable beside a failed refresh. Per-tab request revisions prevent older success/error/finally settlements from replacing the latest request. Superseded recommendation operations cannot leave a permanent loading indicator.
- Marketplace automatic recommendations remain available through authenticated search (`q=skill&limit=10`). Their data/loading/error state is separate from the installed catalog and explicit Search npm results. A valid nonempty installed list clears obsolete recommendation state.
- Search example buttons pass the selected query directly rather than relying on a delayed callback closing over an old input value.
- Existing panel/button/token styles are reused. Catalog loading uses a status landmark; failures use an alert and named retry button. Root owns the central DESIGN.md update and final browser/visual verification.

## Regression evidence

All commands use installed dependencies from `dashboard`; no installation, real npm lookup, model call, publishing, skill installation/removal, OAuth or backend request was performed. Fetch is replaced only at the HTTP wire boundary with synthetic `Response` objects; the production shared API identity and parser execute.

| Evidence | Result | Artifact |
|---|---|---|
| Initial authenticated catalog regression before production repair | 12 failed / 1 passed, missing credentials and invisible error | `skills-auth-red.log` |
| Search example before direct-query fix | 1 failed / 13 passed, selected query produced no result | `skills-auth-search-example-red.log` |
| Catalog old response settlement before revision guard | 7 failed, stale data/error and recommendation state | `skills-auth-ordering-red.log` |
| Superseded recommendation spinner before dispatch reset | 1 failed / 7 passed | `skills-auth-recommendation-spinner-red.log` |
| Final catalog/page/API/request-ordering regression | 36 passed / 3 files, exit 0 | `skills-auth-catalog-final-tests.log` |
| Combined catalog and Publish regression after all race fixes | 89 passed / 7 files, exit 0 | `skills-auth-final-tests.log` |
| Full dashboard TypeScript project check | exit 0, empty diagnostic output | `skills-auth-final-typecheck.log` |
| Focused ESLint for the seven owned TS/TSX files | exit 0, empty diagnostic output | `skills-auth-final-lint.log` |

Exact final catalog test command:

```sh
node node_modules/vitest/vitest.mjs run src/pages/SkillsPage.test.tsx src/pages/skills/skillsApi.test.ts src/pages/skills/useSkillsCatalog.test.ts
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/eslint/bin/eslint.js src/pages/SkillsPage.tsx src/pages/SkillsPage.test.tsx src/pages/skills/skillsApi.ts src/pages/skills/skillsApi.test.ts src/pages/skills/useSkillsCatalog.ts src/pages/skills/useSkillsCatalog.test.ts src/pages/skills/SearchTab.tsx
```

The edit hook and a direct LSP diagnostics request timed out waiting 3000ms; this is unavailable LSP coverage, not clean LSP evidence. The skill no-excuse checker could not resolve TypeScript under the existing Node invocation (exit 2; `skills-auth-no-excuse.log`). Installed `tsc` and ESLint checks above passed; no new tooling was installed.

Pure LOC, documented in `skills-auth-loc.txt`: page 91, API boundary 64, hook 128, SearchTab 59, page tests 158, API tests 34, ordering tests 74. The source owns distinct responsibilities: presentation, external parsing/authenticated requests, and request-owned catalog lifecycle. No type assertion, `any`, suppression or new logging framework was added. The exhaustive tab switch is checked with `satisfies never`.

## Publish lane and handoff

The independent PublishTab lane fixes the same missing-auth boundary for local skill discovery and publish actions. Its five files, 53 passing tests and existing baseline size are recorded in `skills-publish-auth-report.md` and `skills-publish-auth-hashes.txt`. Its advisory child review had unavailable tools and is explicitly excluded from gate coverage. A separate source-inspecting reviewer identified request ordering issues; these were repaired and covered by controlled deferred-response regressions. The final source review is CLEAR / APPROVE with no blockers in `skills-auth-code-review.md`, bound to the base commit plus current source hashes.

Root must build the complete frontend, then personally revisit `/skills`: read All Skills, Marketplace recommendations, MCP and Publish local catalog; inspect loading/error/count truthfulness and console auth errors. No real installation/removal/publication is required or claimed. Real-browser screenshots, breakpoint checks and final whole-app coverage remain root-owned; synthetic wire tests do not substitute for them.

## Execution checklist

- [x] Graph-first discovery and current source read.
- [x] Source-confirmed auth root cause and failing behavioral regressions.
- [x] Authenticated typed boundary, visible error/retry and unknown/empty distinction.
- [x] Preserve Marketplace recommendation functionality with independent state.
- [x] Reproduce and repair stale query, stale response and perpetual recommendation loading.
- [x] Focused regression/type/lint checks and source hashes.
- [x] Combined Publish lane regression and final independent source review on current hashes.
- [ ] Root production build/live browser and breakpoint verification, explicitly handed off rather than claimed by this implementation lane.

The final unchecked handoff is not a claim of full feature completion.

Durable review receipt: lane `skills-auth-code-review`, supplied base SHA `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, verdict **CLEAR / APPROVE**, report `skills-auth-code-review.md`, and the exact source-manifest digests stamped in that report. This covers the twelve current source/test files named by the two manifests; it does not cover other shared working-tree edits or substitute for root live QA.
