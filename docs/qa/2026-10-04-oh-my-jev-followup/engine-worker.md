---
title: Decision diagnostics engine implementation evidence
date: 2026-10-04
tags: [qa, decision, wilson, tag-diagnostics, compatibility]
phase: complete
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
---

## Implemented contract

Added frozen typed `AccuracyInterval`, `DecisionEvaluationSummary`,
`DecisionTagGroup`, and `TagDiagnostics` models. Prediction and error cases accept
at most 16 unique bounded `DecisionKey` tags. The common `_summarize_decisions`
calculates both aggregate and tag results using the existing exclusions, lexical
argmax, sum tolerances and confidence tie groups. Tag groups rank by all-case
frequency then lexical tag order, with the first 25 emitted and omission counts.

Wilson uses fixed z=1.96 and confidence_level=0.95 on the same scored rows as
accuracy. An empty scored sample returns null. Endpoint bounds are clamped to
include the observed proportion, covering floating-point endpoint cases 0/11
and 6/6. No intervals were added to calibration losses or selected risk/coverage.

Only canonical fingerprint serialization omits empty case tags. Nonempty tags
remain in the fingerprint. Public input serialization uses existing Pydantic
APIs compatible with the declared 2.10 minimum; no serializer override or new
dependency was added. Existing report parsers default missing interval to null
and tag diagnostics to an empty report. Schema version remains 1,
score_source remains provided_probabilities and calibration_status unverified.

## Red and green

Red was run before production changes using current production symbols and
dictionary observations, avoiding missing-import/setup failures:

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_decision_diagnostics.py -q
```

Observed: **17 failed, 17 passed**. Failures were missing `accuracy_interval`
fields (`KeyError`) and valid optional tags rejected as `extra_forbidden` at the
existing typed boundary. Expected invalid-tag cases already rejected input.

After implementation, tests were changed to typed attribute observations and
extended for roundoff endpoints and per-group ties/metric isolation. Final:

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_decision_diagnostics.py tests/test_decision_evaluation.py -q
```

Observed: **87 passed in 0.56s**. This includes 37 new diagnostics cases and 50
existing evaluation cases. The only edit to the existing test file is its
provenance expected canonical dump, which now omits empty tags specifically.
The fixed pre-tags canonical fixture independently guards the old fingerprint.

## Static checks

```sh
.venv/bin/python -m basedpyright src/antigravity_k/engine/decision_evaluation_models.py src/antigravity_k/engine/decision_evaluation.py tests/test_decision_diagnostics.py tests/test_decision_evaluation.py
.venv/bin/python -m ruff check src/antigravity_k/engine/decision_evaluation_models.py src/antigravity_k/engine/decision_evaluation.py tests/test_decision_diagnostics.py tests/test_decision_evaluation.py
.venv/bin/python /Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/4.19.4/skills/programming/scripts/python/check-no-excuse-rules.py src/antigravity_k/engine/decision_evaluation_models.py src/antigravity_k/engine/decision_evaluation.py tests/test_decision_diagnostics.py
```

Observed: basedpyright **0 errors, 0 warnings, 0 notes**; configured ruff **all
checks passed**; programming audit **no violations in 3 files**. Module launchers
use the current interpreter instead of the environment's stale CLI shebang.

An extra read-only `ruff --select ALL` audit initially found 88 style findings,
mostly documentation, existing Pydantic error construction, formatting and
pytest assertions/import conventions outside repository configuration. The two
new test style findings (boolean fixture signature and tuple concatenation) were
fixed. With those explicit convention exceptions, the additional audit passes:

```sh
.venv/bin/python -m ruff check --select ALL --ignore D,EM101,TC003,COM812,PLC0415,S101,PLR2004 src/antigravity_k/engine/decision_evaluation_models.py src/antigravity_k/engine/decision_evaluation.py tests/test_decision_diagnostics.py
```

Repository-configured lint and unfiltered typing are the task's quality gates.

## Source identity

These hashes bind this evidence to working-tree source; the shared tree has
uncommitted changes and no Git mutation was performed by this worker.

| File | SHA256 | Pure LOC |
| --- | --- | ---: |
| src/antigravity_k/engine/decision_evaluation_models.py | d3e8180e2f0102d663cdc4cd89e58c9a9e8a7cc7e427cba99eac272d1ac74e97 | 113 |
| src/antigravity_k/engine/decision_evaluation.py | d6d895c81f4b897168c4d1267934799588736f7d2cdb519ffb50fee743d2c774 | 232 |
| tests/test_decision_diagnostics.py | 3192588b371c7e92d19fc0e5081269b42ebb7ac3887279396d2a1f54696bc40e | 190 |
| tests/test_decision_evaluation.py | 50c2963815e78baec4a6fbf46be6536c5400fb8d99ce9d080a70a8e99a0cf3a9 | 248 |

The explicit pre-tags known-case canonical string hashes to
`e36466c6484aedcb738888e6c5c8d88ca177309da11094862a262879d4bdcc78`.
Both absent and empty tags must return this digest. The separate nonempty-tag
case asserts that tags are included and the digest differs.

## Scope and limits

Tests isolate home before project collection through the existing QA launcher.
Inputs are synthetic and no model/provider call, user credential/store access,
external source copy, installation, browser/HTTP access or Git mutation was used.
This worker implemented the engine and unit contract tests. API/CLI tests belong
to Worker B, while Root owns the real CLI manual run and integration review.
Unit green alone is not a claim that the user's blocked site was observed.
