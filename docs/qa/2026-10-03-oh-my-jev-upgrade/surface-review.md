---
title: Decision evaluation API and CLI surface review
date: 2026-10-03
tags: [code-review, api, cli, decision-evaluation]
reviewer_role: code-quality-reviewer
reviewed_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest: docs/qa/2026-10-03-oh-my-jev-upgrade/source.sha256
source_manifest_sha256: 0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa
source_manifest_verified: true
reviewed_file_sha256:
  src/antigravity_k/api/routes/decision_evaluation_api.py: bbedf21f9601a419e64d386e40bdca482ab1ce7fc3ef0e94ceede4e7088449db
  tests/test_decision_evaluation_surfaces.py: c4836b0c0c82381ce1319ae424512e1caa5500ccd1126410c52d22a0580dad3b
verdict: CLEAR
recommendation: APPROVE
---

## Scope and provenance

Retake reviewed the frozen surface scope after the final OpenAPI-contract
adjustment. The updated source manifest covers the two changed files,
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
- The API route uses typed request and response models. Its explicit `422`
  response model, `DecisionEvaluationInputError`, documents exactly the body
  emitted by the route-local `RequestValidationError` handler: one required
  string `detail` with the generic message. Serializing that model with
  `model_dump()` preserves the existing body and status, cannot turn malformed
  input into a 500, and cannot echo submitted input. `@override` is checker-only.
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

Inspected `worker-b-openapi-green.txt`: the scoped surface suite reports
`21 passed`, including the public OpenAPI/error-body regression. The prior
20-test surface pass and 50-test engine pass remain corroborative evidence.
Inspected `worker-a-green.txt`: the engine suite reports `50 passed`.
`worker-b-ruff.txt`, `worker-b-typecheck.txt`, and `worker-b-no-excuse.txt`
report passing lint, zero type diagnostics, and no no-excuse violations. These
artifacts are corroborative rather than substitutes for source inspection.

The OpenAPI final-regression artifact reports 160 related tests passing. It emits
the pre-existing Starlette/httpx deprecation and 11 unrelated duplicate-operation
ID warnings while generating the application-wide OpenAPI document; none name the
new endpoint. The new regression sends an invalid authenticated request through
the production app, parses the observed generic body, then reads `/openapi.json`
and confirms the declared 422 schema has a required string `detail`. This is a
public-contract test rather than a brittle implementation-only assertion.

The unrelated CLI backend-discovery fixture remains reported as environment- or
network-dependent in `root-final-regression.log`; it is outside this change and
does not invalidate the focused engine/surface evidence.

## Skill-perspective check

Ran the `omo:remove-ai-slops` and `omo:programming` skill perspectives before
judging maintainability and test relevance. The retake does not add deletion-only
tests, tautological tests, brittle prompt assertions, untyped escape hatches,
needless production parsing/normalization, or speculative production abstraction.
The small `_isolate_home` helper removes repeated setup without obscuring the
isolation boundary. The OpenAPI test checks an externally consumable schema
against the observed HTTP response, so it is not implementation-mirroring.
Boundary validation is required by the public contract, and the tests assert
observable CLI/HTTP behavior through the real registered applications.

## Limitations

This review did not rerun the root-owned live HTTP and subprocess CLI QA, did not
inspect raw application logs or credentials, and did not run an unrelated full
suite. The source manifest was verified at review time; subsequent workspace
edits require a new manifest verification.
