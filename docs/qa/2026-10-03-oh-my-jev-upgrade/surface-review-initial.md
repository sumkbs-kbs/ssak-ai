---
title: Decision evaluation API and CLI surface review
date: 2026-10-03
tags: [code-review, api, cli, decision-evaluation]
reviewer_role: code-quality-reviewer
reviewed_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest: docs/qa/2026-10-03-oh-my-jev-upgrade/source.sha256
source_manifest_sha256: 7f09545050bebe8ffdcf521f9af31e59280f814b6f127ab13b76e2c16550777c
source_manifest_verified: true
verdict: CLEAR
recommendation: APPROVE
---

## Scope and provenance

Reviewed the frozen surface scope: `src/antigravity_k/decision_evaluation_cli.py`,
`src/antigravity_k/api/routes/decision_evaluation_api.py`, registration-only edits
to `src/antigravity_k/cli.py` and `src/antigravity_k/api/routes/__init__.py`, and
`tests/test_decision_evaluation_surfaces.py`. `sha256sum -c` passed for every
entry in the source manifest, including the dependent engine and engine-test
files. The repository HEAD was the required
`8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

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
- The API route uses the typed request and typed response model. Its route-local
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

The unrelated CLI backend-discovery fixture remains reported as environment- or
network-dependent in `root-final-regression.log`; it is outside this change and
does not invalidate the focused engine/surface evidence.

## Skill-perspective check

Ran the `omo:remove-ai-slops` and `omo:programming` skill perspectives before
judging maintainability and test relevance. The diff does not add deletion-only
tests, tautological tests, brittle prompt assertions, implementation-mirroring
tests, untyped escape hatches, needless parsing/normalization, or speculative
production abstraction. Boundary validation is required by the public contract,
and the tests assert observable CLI/HTTP behavior through the real registered
applications.

## Limitations

This review did not rerun the root-owned live HTTP and subprocess CLI QA, did not
inspect raw application logs or credentials, and did not run the unrelated full
suite. The source manifest was verified at review time; subsequent workspace
edits require a new manifest verification.
