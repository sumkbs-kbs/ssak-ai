---
title: Decision diagnostic compatibility and surface review
date: 2026-10-04
tags: [review, compatibility, decision, api, cli]
reviewer: jev_compatibility_review
verdict: PASS
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
manifest_sha256: 47e26236e414be601803feba31d052835aa9d1f332c1711846ce951585698132
---

## Scope and binding

Independent review of the eight files in `source-manifest.json`, against
`IMPLEMENTATION_CONTRACT.md`. Full HEAD and all eight file hashes matched before
and after this review. Because the tree is dirty, the manifest hash is required
in addition to HEAD to identify the reviewed implementation. No production code,
test, Git state, dependencies or user credentials were changed by this reviewer.

Graph discovery was attempted first. The local project was reported unavailable;
a fast, nonpersistent index reported success, but a subsequent search still
reported the project unavailable. Exact supplied paths were read as fallback.

## Findings

PASS for this scoped compatibility/API/CLI contract. No actionable implementation
defect was found.

- Optional tags use the same bounded, strict, nonblank `DecisionKey` on prediction
  and error cases. An immutable tuple defaults to empty; 16 is inclusive and 17
  fails. Duplicate tags fail at the typed case boundary. Existing discriminator,
  unique case IDs, unknown-field rejection and prediction checks remain intact.
- New readers accept previous reports without `accuracy_interval` or
  `tag_diagnostics`; defaults are a null interval and empty diagnostic groups.
  Schema version, score provenance and unverified calibration status remain
  unchanged. This verifies old-report parsing by the updated reader, not forward
  compatibility of external clients that reject unknown response fields.
- Canonical hashing excludes only empty case tags. Independently reconstructed
  pre-tags JSON verified unchanged fingerprints for empty, prediction-only,
  error-only and mixed requests with both absent and explicit empty tags. A mixed
  request with one nonempty Korean tag retained that metadata in its fingerprint
  while the untagged error row retained its original shape.
- Aggregate and tag summaries use the same calculator, retaining labelled
  strict-valid denominators, lexical argmax ties and whole confidence-group
  selective coverage. The tag limit is deterministic and omitted counts are
  explicit. Multi-tag counts are overlapping views, not extra aggregate samples.
- Existing production API and CLI source hashes are unchanged. Tests exercise
  the registered protected route, generic safe 422, missing-credential 401,
  CLI exit 2 and safe stderr, typed successful reports, and public OpenAPI fields.
  OpenAPI documents nullable interval fields, fixed Wilson metadata, typed
  summaries and optional per-case arrays bounded to 16.

## Observed verification

Executed with the already installed project environment:

```text
.venv/bin/python -B docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_decision_evaluation.py tests/test_decision_evaluation_surfaces.py tests/test_decision_diagnostics.py tests/test_decision_diagnostic_surfaces.py -q
137 passed, 12 warnings in 2.03s
```

An additional stdin driver isolated `Path.home`, configuration and credential
paths before project imports and independently checked 11 compatibility facts:
eight legacy-fingerprint combinations, mixed nonempty-tag inclusion, old-report
defaults, and optional/bounded/unknown-field-forbidden request schema. All passed;
the driver exited 0. It used literal old case shapes and independent canonical
JSON construction rather than the evaluator's new serialization logic.

The test run reports existing Starlette/httpx deprecation and duplicate operation
ID warnings from unrelated registered routes. None identifies this benchmark
route or a failing assertion. They were not modified for this scoped review.

## Limits

API evidence uses an in-memory production TestClient with synthetic protected
authentication and lifespan startup disabled. CLI surface tests use the registered
Typer application. This review did not access the policy-blocked user's browser
site, invoke providers, load models, assess actual model accuracy, validate live
subsystem startup, or certify the whole program. It is a compatibility review
bound to the manifest above, not a whole-program release gate.
