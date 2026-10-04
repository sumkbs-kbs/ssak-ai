---
title: Skills Publish authenticated API regression fix
date: 2026-10-04
tags: [qa, skills, publish, authentication]
---

Base HEAD supplied by the parent: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
This report covers the five files listed in `skills-publish-auth-hashes.txt`.

Changes:

- Local skill loading and both publication forms call the existing authenticated `apiRequestPath` client through `publishSkillsApi.ts`.
- Zod parses local and publication payloads, including nullable optional publication fields and HTTP 200 application failures.
- Local failures render a visible alert with PIN guidance when applicable and a named retry control. A failed refresh retains the last confirmed skill list.
- A monotonic request revision advances on every local request dispatch. Only the newest request can change skills, failure state, count metadata, or loading flags. Cleanup invalidates in-flight requests when the tab unmounts.
- Publication failures remain visible and allow an explicit retry. Existing dry-run settings, history, endpoints, and request body fields remain intact.
- The legacy component decreased from 685 to 665 lines, including the six-line race fix. The new boundary is 68 lines. No surrounding legacy styling refactor was attempted.

Regression proof:

- `skills-publish-auth-red.log`: eight regression tests failed before implementation. Missing bearer headers, absent alerts/PIN guidance, refresh failure, and unparsed malformed payloads reproduced the defects.
- `skills-publish-auth-race-red.log`: three controlled overlap tests failed with revision guards disabled. An old 503 response replaced newer success with an alert; an old successful poll removed a newer failure and replaced cached data; an old completion handler enabled refresh while the newest request remained pending. All responses are deferred HTTP fakes and the clock is explicitly advanced; no sleeps are used.
- `skills-publish-auth-green.log`: four files, 53 tests passed. Counts: three overlap tests, nine authenticated PublishTab tests, 13 existing PublishTab tests, 28 existing history tests. The same controlled overlap tests pass with revision guards restored.
- `skills-publish-auth-typecheck.log`: final TypeScript command exited 0. Earlier unrelated concurrent MCP catalog type mismatch was resolved by the parent before the final run.
- `skills-publish-auth-lint.log`: focused lint command exited 0.

Commands, all run from `dashboard/` using installed dependencies:

```sh
node node_modules/vitest/vitest.mjs run src/pages/skills/__tests__/PublishTab.requests.test.tsx src/pages/skills/__tests__/PublishTab.auth.test.tsx src/pages/skills/__tests__/PublishTab.test.tsx src/pages/skills/__tests__/publishHistory.test.ts
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/eslint/bin/eslint.js src/pages/skills/PublishTab.tsx src/pages/skills/publishSkillsApi.ts src/pages/skills/__tests__/PublishTab.auth.test.tsx src/pages/skills/__tests__/PublishTab.requests.test.tsx src/pages/skills/__tests__/PublishTab.test.tsx
```

Tests use HTTP-level fakes and fabricated bearer credentials. No actual publication, package installation, removal, OAuth, or external action was performed. No browser or parent server process was controlled. Parent/root owns the combined production build and actual browser QA; this report does not claim browser validation.

An advisory child review reported no actionable defects, but its tooling could not run and its exact source inspection was not independently artifact-verified. It is not counted as gate coverage. The parent will independently review the combined current files.

Discovery used the knowledge graph first. One nonpersistent fast index succeeded after the project was missing; later graph availability was unstable, so known-file reads supplied the remaining narrow route and client contracts. No Git mutation was performed.
