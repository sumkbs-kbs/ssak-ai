---
title: Final current-pass code review
date: 2026-10-04
tags: [qa, code-review, final, functional-fixes]
status: pass-with-watch
reviewer: full_final_code_review
---

# Final code review

## Verdict

**PASS — no CRITICAL or MAJOR blocker found.**

```json
{
  "codeQualityStatus": "WATCH",
  "recommendation": "APPROVE",
  "blockers": [],
  "reportPath": "docs/qa/2026-10-04-full-live/final-code-review.md"
}
```

This is a bounded review of the current pass, rather than a judgment of the
repository's large pre-existing dirty tree.  It covers the 56 files in
`final-source-manifest.json`, the named functional seams, and their adjacent
call paths.  Actual `HEAD` is
`8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; the manifest SHA-256 is
`c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`.
All 56 manifest file digests match the current bytes.

## Findings

### CRITICAL

None.

### MAJOR

None.

### MEDIUM

1. **Literal natural-language fixtures remain brittle under the strict
   `programming` skill policy.**
   `tests/test_search_request_contract.py:103` and
   `tests/test_quality_output_contract.py:13` exercise large tables of exact
   Korean and English request wording.  These do usefully distinguish routing
   and output-contract behavior, so they are not deletion-only or tautological
   tests.  Still, they will need maintenance for legitimate wording changes and
   cannot establish broad natural-language understanding.  Keep these cases
   limited to representative routing boundaries; new coverage should prefer a
   structured routing decision or a small semantic fixture over expanding
   prose variants.  This is not a release blocker because the features being
   fixed explicitly classify user language and each affected test has positive
   and negative controls.

### LOW

1. **Legacy module size is outside this pass's refactor scope.**
   Several owned files exceed the configured 250 pure-LOC preference, notably
   `src/antigravity_k/engine/tool_loop.py`,
   `src/antigravity_k/api/routes/system_api.py`,
   `dashboard/src/pages/StudioPage.tsx`, and
   `dashboard/src/pages/skills/PublishTab.tsx`.  The inventory and assignment
   identify these as pre-existing large surfaces; the reviewed changes are
   narrow corrections inside them.  A size-driven refactor now would be scope
   expansion and carries more regression risk than it removes.

## Correctness and scope checks

- The Qwen repo/name lookup uses exact-name preference and applies the most
  conservative calibrated ceiling across the registered identities.  The final
  prompt ceiling retains a 4,096-token completion reserve inside the 32,768
  provider window.
- The quality gate distinguishes requests to describe a function or return its
  result from requests to generate program source.  Numeric and JSON output
  constraints remain enforced, including malformed JSON and an explicitly
  required comparison table.
- Conversation append, compact, and fork inputs now enter typed Pydantic
  request boundaries before store mutation.  The focused tests compare the
  persisted bytes before and after 422 responses, which protects the relevant
  no-mutation contract.
- Bridge plans retain token indirection, quote shell-sensitive model and URL
  values, use the current browser origin, and emit the Codex Responses endpoint
  configuration.  The tests execute the rendered shell fragments with only a
  synthetic token and include a shell-metacharacter regression.
- Current selected-project, credential, and selection-generation checks prevent
  delayed palette note reads from replacing a newer note or triggering login
  recovery for a newer credential.
- Skills publishing, skills catalog, and extraction APIs call the shared typed
  authenticated request boundary.  Their Zod schemas turn invalid responses
  into visible failures instead of false empty/success views.
- Model status is derived from the Ollama process snapshot: malformed or
  unavailable process data produces `unknown`, while an empty valid process
  list leaves installed models installed.  Studio labels unavailable export and
  registration actions as unavailable rather than claiming completion.
- Citation URLs come from source metadata, not untrusted result text; markdown
  table headers and verified source-link footers are excluded from claim
  evaluation without allowing unsupported table data or forged source labels.
- Explicit mandatory search requests produce a required-tool contract only when
  the tool is registered and not policy-denied.  Missing execution fails the
  task rather than presenting an unsupported answer as a completed result.

## Evidence reviewed

- `docs/qa/2026-10-04-full-live/root-final-regression.log`: **283 passed** in
  13.48 seconds (one third-party deprecation warning).
- `docs/qa/2026-10-04-full-live/root-final-ui-tests.log`: **16 files / 133
  tests passed**.
- Owner reports and the source inventory were treated as leads, then checked
  against the manifest and current source/test bytes.  I did not rely on an
  owner PASS assertion as proof.

## Skill-perspective check

The required `omo:programming` and `omo:remove-ai-slops` perspectives were
loaded before the test and maintainability assessment.  The check ran.

The production changes do not introduce TypeScript `as any`, `@ts-ignore`, or
`@ts-expect-error`, and the affected frontend boundaries parse unknown API
responses with Zod.  Python changes use concrete request schemas at HTTP
boundaries and do not add needless production data extraction or normalization
outside the requested behavior.  The slop pass found no deletion-only tests,
tautological expected-from-output assertions, or tests whose only purpose is to
prove a requested removal.  The MEDIUM literal-prompt-fixture observation above
is the one strict programming-skill violation; it does not change the approval
recommendation for this bounded fix.

Graph-first discovery could not run because no codebase-memory MCP graph tool
was available in this reviewer session.  I used the supplied immutable manifest,
bounded source reads, and directly adjacent callers as the documented fallback.
