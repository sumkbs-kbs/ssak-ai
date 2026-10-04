---
title: Decision evaluation API and CLI surface review
date: 2026-10-03
tags: [code-review, api, cli, decision-evaluation]
reviewer_role: code-quality-reviewer
reviewed_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest: docs/qa/2026-10-03-oh-my-jev-upgrade/source.sha256
source_manifest_sha256: e7fd09ddfc15b9bb0771cfc061144dd6cd7cb1d16d7360d1aa6f699327866f2c
source_manifest_verified: true
reviewed_file_sha256:
  src/antigravity_k/api/routes/decision_evaluation_api.py: b7e47c157041c1a0c276651386c5dd595940c3c460bdc1294ff851aab12fd1ed
  tests/test_decision_evaluation_surfaces.py: 95916a5826d414d5548adbac910dedcc35d4f7cba1a9790cf80a330d3b32c1a6
verdict: CLEAR
recommendation: APPROVE
---

## Scope and provenance

Retake reviewed the frozen surface scope after the type-only refinement. The
updated source manifest covers the two changed files,
`src/antigravity_k/api/routes/decision_evaluation_api.py` and
`tests/test_decision_evaluation_surfaces.py`, as well as the dependent engine,
CLI, registration, and engine-test files. `sha256sum -c` passed for every entry.
The repository HEAD was the required `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

The codebase-memory graph tools required by repository guidance were not exposed
in this review environment. I used bounded direct reads and `rg` only to inspect
the registration path and the pre-existing auth middleware.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Surface assessment

- The CLI reads at most `2 MiB + 1` bytes before validation, accepts the inclusive
  2 MiB boundary, emits only the typed JSON report to stdout on success, and maps
  file, UTF-8, JSON, and schema failures to one generic stderr message and exit
  code 2. It does not print a validation payload, path, or traceback.
- `cli.py` adds only the import and `decision-eval` registration. The routes
  aggregator adds only the import and inclusion of the new router.
- The API route uses the typed request and typed response model. The added
  `@override` only verifies that `get_route_handler` remains an `APIRoute`
  override; it makes no runtime-policy change. Its route-local
  `RequestValidationError` handler emits the generic 422 body and cannot turn
  malformed input into a 500 or echo submitted input.
- The route is under `/api/benchmarks/decisions/evaluate`; it is not in the
  pre-existing public exact-path allowlist. The pre-existing protected-path
  middleware invokes `authenticate_request`, whose current implementation accepts
  a verified bearer token (with explicit development loopback policy outside this
  change). No auth middleware, allowlist, provider, model policy, credential, or
  promotion behavior was changed.
- The production-app tests exercise registration, a missing-credential 401, and a
  real ephemeral bearer token issued through `TokenService`. They also cover
  malformed JSON, nonfinite values, invalid coercions, duplicate option keys, and
  duplicate case IDs as generic non-echoing 422 responses. CLI tests exercise the
  registered command, typed output, safe errors, unreadable paths, and both byte
  boundaries.

## Test and evidence review

Inspected `worker-b-green.txt`: the scoped surface suite reports `20 passed`.
Inspected `worker-a-green.txt`: the engine suite reports `50 passed`.
`worker-b-ruff.txt`, `worker-b-typecheck.txt`, and `worker-b-no-excuse.txt`
report passing lint, zero type diagnostics, and no no-excuse violations. These
artifacts are corroborative rather than substitutes for source inspection.

For this retake, `root-approved-regression.log` records 159 related tests passing
with one pre-existing Starlette/httpx deprecation warning. The updated surface
test annotation uses `httpx.Client`, the interface implemented by Starlette's
`TestClient`; `_isolate_home`, explicit ignored write returns, `usefixtures`, and
the explicit string concatenation are checker-facing refinements with no changed
test scenario or production behavior.

The unrelated CLI backend-discovery fixture remains reported as environment- or
network-dependent in `root-final-regression.log`; it is outside this change and
does not invalidate the focused engine/surface evidence.

## Skill-perspective check

Ran the `omo:remove-ai-slops` and `omo:programming` skill perspectives before
judging maintainability and test relevance. The retake does not add deletion-only
tests, tautological tests, brittle prompt assertions, implementation-mirroring
tests, untyped escape hatches, needless parsing/normalization, or speculative
production abstraction. The small `_isolate_home` helper removes repeated setup
without obscuring the isolation boundary. Boundary validation is required by the
public contract, and the tests assert observable CLI/HTTP behavior through the
real registered applications.

## Limitations

This review did not rerun the root-owned live HTTP and subprocess CLI QA, did not
inspect raw application logs or credentials, and did not run an unrelated full
suite. The source manifest was verified at review time; subsequent workspace
edits require a new manifest verification.
