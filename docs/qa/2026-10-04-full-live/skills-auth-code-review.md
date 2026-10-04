---
title: Skills authenticated catalog and publish code review
date: 2026-10-04
tags: [qa, code-review, skills, authentication]
---

# Result

- `codeQualityStatus`: **CLEAR**
- `recommendation`: **APPROVE**
- `blockers`: None

## Scope and evidence inspected

Reviewed the current authenticated Skills catalog and Publish paths, their focused tests, the shared authenticated request client, and the matching Python route contracts. The source hashes at review time match `skills-auth-hashes.txt` and `skills-publish-auth-hashes.txt`; the final combined focused run records **89 passing tests across 7 files** in `skills-auth-final-tests.log`.

The supplied review base is `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. I did not independently verify Git state. The sealed source-manifest digests are:

- `skills-auth-hashes.txt`: `8dd5f9f0011d86c3c53eb9afeb525e50b63742bdc437e1cd6626564efa783c9d`
- `skills-publish-auth-hashes.txt`: `c5193f81ee011885e12840727689678ebf82ceae946597cac16e8fc0c6903069`

The request seam is correctly centralized on `apiRequestPath`: it supplies the stored bearer credential plus project ID, revision, and client session headers. `skillsApi.ts` rejects HTTP-200 `{ ok: false }` envelopes before an empty state can render; Zod parses API data at the boundary. `publishSkillsApi.ts` does the same for local-skill and publication envelopes. Its nullable-or-omitted publication fields agree with the backend routes, which emit different optional fields for npm and GitHub responses.

The page and publish components preserve confirmed data on refresh failure and render an actionable PIN/error state. The per-tab and local-list request revisions prevent older results or errors from overwriting newer state. Marketplace recommendation state is separately owned and is reset when a newer installed-skills request supersedes it, so an obsolete recommendation request cannot leave a spinner or error behind.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Test relevance and maintainability

The tests exercise observable HTTP/UI contracts: authenticated request headers and preserved request bodies, 401 PIN recovery, HTTP-200 application failures, malformed payload rejection, cached-data retention, and controlled out-of-order responses. The ordering tests use deferred responses to distinguish stale completions from current ones; they are neither timing sleeps nor implementation-constant mirrors. No deletion-only, tautological, or prompt/prose tests were found.

`PublishTab.tsx` remains over the preferred module size, but it was a pre-existing 685-physical-LOC legacy component; the auth boundary first reduced it to 659 lines and the final race-safe version is 665. This patch extracts the authenticated request boundary rather than extending unrelated styling or behavior. The new API module and tests are narrowly scoped; no needless extraction, parsing outside the network boundary, untyped escape hatch, or speculative abstraction was introduced.

## Required skill-perspective check

Ran the required perspectives by reading `omo:programming` and its TypeScript reference, plus `omo:remove-ai-slops`.

- **Programming:** no new `any`, unsafe assertion, non-null assertion, ignored type error, bare fetch in the changed Skills API seam, or catch-and-swallow was introduced. Zod is used at the external response boundary and typed error branches remain explicit.
- **Remove AI Slops:** no slop violation found in production or test changes. In particular, the new response-order tests pin user-visible correctness rather than a requested removal or internal constant. The existing localStorage catch blocks in legacy `PublishTab.tsx` are outside this patch's auth/request change and remain intentional I/O fallbacks.

## Validation considered

- `skills-auth-final-tests.log`: 7 files / 89 tests passed.
- `skills-publish-auth-green.log`: 4 files / 53 tests passed, including the controlled local-request race suite.
- `skills-auth-ordering-red.log` and `skills-publish-auth-race-red.log`: the targeted stale-response regressions failed before their respective guards.
- Focused lint and TypeScript commands exited successfully according to their supplied zero-output logs; no claim is made that these empty PTY capture files contain diagnostics.

No browser, backend, model, credential, package, removal, or publication action was performed during this review.
