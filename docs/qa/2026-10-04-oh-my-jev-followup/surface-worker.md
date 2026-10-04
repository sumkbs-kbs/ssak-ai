---
title: Decision diagnostic API and CLI contract regression evidence
date: 2026-10-04
tags: [qa, decision, diagnostics, api, cli, regression]
status: complete
baseline_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
---

Implemented `tests/test_decision_diagnostic_surfaces.py` only for production-facing
regression tests; no API or CLI production changes. The working checkout is dirty:
the HEAD above identifies the baseline and does not identify the tested content.

WORKING: complete. The new suite passes after engine owner A supplied calculation.
Root retains ownership of independent real CLI QA and the final combined gate.

The suite reuses the protected synthetic `api_client` and real Typer `cli_app`
fixtures from `tests/test_decision_evaluation_surfaces.py`. All pytest commands
use the existing `isolated_entry.py` launcher, which patches `Path.home` and sets
temporary auth/storage paths before pytest collection or project imports.
Function fixtures alone would be insufficient because session-autouse fixtures
import production modules before function fixtures run.

## Observed behavior

- API and CLI return typed Wilson intervals for the strict-valid labelled scored
  set. Mixed input scores two cases, with one success: bounds
  `0.09452865480086614` and `0.9054713451991339`. One correct untagged prediction
  returns `n=1`, `successes=1`, lower `0.20654329147389294`, upper `1`.
- Tagged mixed predictions, invalid sums, unlabelled cases and errors retain one
  shared scoring denominator. Universal tag summary fields equal the aggregate,
  and a case belongs independently to each of its tags.
- Empty and error-only scored sets produce a null interval. Low-count groups
  remain present. API accepts 16 unique tags for either case variant; CLI accepts
  the same limit. API output limits 32 distinct groups to 25 and reports 7 omitted.
- Invalid/duplicate/blank/overlong/non-string/excessive tags retain generic safe
  API 422 and CLI exit 2. Missing credentials for a tagged request retain API 401.
- In-memory OpenAPI exposes nullable interval references and typed numeric
  fields, fixed method/confidence/z, bounded tag arrays, tag diagnostic fields and
  the same typed group-summary schemas as the aggregate. Numeric aliases may use
  `$ref`; fixed numeric values use equal minimum/maximum constraints.

## Red evidence

Command:

```text
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_decision_diagnostic_surfaces.py -q --tb=short
```

Initial output: `6 failed, 19 passed, 12 warnings in 2.43s`, exit 1.
At this point A had added public model fields and tag validation but had not yet
implemented calculations. Five failures were meaningful production red: API and
CLI intervals remained `None`, and accepted 16-tag cases reported zero tag groups.
There were no collection/import/setup failures. The sixth failure was the test's
OpenAPI resolver assuming an inline number instead of resolving `Probability`
`$ref`; it is not counted as feature red and was corrected. Concurrent A changes
then supplied the engine calculations. An interim OpenAPI test was also corrected
to assert the final fixed numeric minimum/maximum schema instead of requiring
`const` for confidence/z.

## Green evidence

The same isolated command after calculation, resolver completion and the final
exhaustive-helper cleanup returned:

```text
29 passed, 12 warnings in 1.55s
exit 0
```

Combined fixture/compatibility check before the final helper cleanup:

```text
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_decision_evaluation_surfaces.py tests/test_decision_diagnostic_surfaces.py -q --tb=short
50 passed, 12 warnings in 1.70s
exit 0
```

Static checks:

```text
.venv/bin/ruff check tests/test_decision_diagnostic_surfaces.py
All checks passed!

.venv/bin/python -m basedpyright tests/test_decision_diagnostic_surfaces.py
0 errors, 0 warnings, 0 notes

.venv/bin/python /Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/4.19.4/skills/programming/scripts/python/check-no-excuse-rules.py tests/test_decision_diagnostic_surfaces.py
no violations in 1 file(s)
```

Root's unfiltered type check found an unnecessary `case unreachable` binding
pattern after both Literal variants were already covered. The prior `--level
error` invocation hid that warning. The final helper uses the wildcard default
`case _: assert_never(status)`. Unfiltered basedpyright and the generic no-excuse
checker both pass, and the 29-test suite passes on the content hash below. A newly
added Literal variant without a branch still causes a type error at
`assert_never(status)`. No suppression or checker changes were introduced.

The `.venv/bin/basedpyright` executable has an existing stale interpreter path to
the former `antigravity-k` checkout; the module invocation above used the current
already-installed interpreter without installation or environment repair.

Pure LOC: 217. This is within the 250 ceiling but in the 200–250 warning band;
split the contract test module before substantial future expansion. Its one
responsibility is diagnostic surface contracts. Typed response parsing, exhaustive
fixture variant handling and existing fixture reuse avoid `Any`, casts, ignores,
broad catches or new provider mocks. Added comments are Given/When/Then BDD blocks.
A read-only delegated review suggested asserting nullable OpenAPI shape and exact
group-summary schema equality; both suggestions were incorporated.

## Tested content hashes

SHA256 captured after the passing surface checks:

```text
1c318c18c2670f4ddef3d932db414d84a0c31de78d743d91c9ee2645a971e80c  tests/test_decision_diagnostic_surfaces.py
d3e8180e2f0102d663cdc4cd89e58c9a9e8a7cc7e427cba99eac272d1ac74e97  src/antigravity_k/engine/decision_evaluation_models.py
d6d895c81f4b897168c4d1267934799588736f7d2cdb519ffb50fee743d2c774  src/antigravity_k/engine/decision_evaluation.py
```

Root must bind subsequent A source changes to its final combined regression gate.

## Limits

These are isolated in-memory API contract checks and actual registered Typer
command invocations through `CliRunner`. They do not observe the saved-policy
blocked user site. No listener, alternate browser, CDP, hostname alias or HTTP
access was used to bypass that block. No provider/model was invoked or loaded,
no user credential/configuration file was read, no dependency was installed and
no Git mutation occurred in this worker lane.

The 12 passing-test warnings are existing Starlette/httpx deprecation and
unrelated production OpenAPI duplicate operation IDs. They were reported without
changing their modules. The independent external CLI QA remains Root's evidence.
