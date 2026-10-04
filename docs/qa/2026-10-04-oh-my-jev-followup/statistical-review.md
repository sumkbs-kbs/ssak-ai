---
title: Independent statistical review of decision uncertainty and tag diagnostics
date: 2026-10-04
tags: [review, statistics, decision, evidence]
verdict: PASS
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest_sha256: 47e26236e414be601803feba31d052835aa9d1f332c1711846ce951585698132
---

## Scope and identity

PASS for the statistical behavior defined in IMPLEMENTATION_CONTRACT.md. No
scoped defect or blocking missing behavioral boundary was found. This is a
statistical scope review, not whole-program, browser, model-quality, or five-lane
certification.

The review binds to full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
and the dirty-tree file hashes in source-manifest.json, whose SHA256 is
`47e26236e414be601803feba31d052835aa9d1f332c1711846ce951585698132`.
All eight manifest file hashes matched before and after the executed checks.

Directly reviewed source identities:

| File | SHA256 |
| --- | --- |
| src/antigravity_k/engine/decision_evaluation_models.py | d3e8180e2f0102d663cdc4cd89e58c9a9e8a7cc7e427cba99eac272d1ac74e97 |
| src/antigravity_k/engine/decision_evaluation.py | d6d895c81f4b897168c4d1267934799588736f7d2cdb519ffb50fee743d2c774 |
| tests/test_decision_diagnostics.py | 3192588b371c7e92d19fc0e5081269b42ebb7ac3887279396d2a1f54696bc40e |
| tests/test_decision_evaluation.py | 50c2963815e78baec4a6fbf46be6536c5400fb8d99ce9d080a70a8e99a0cf3a9 |

Graph-first discovery was attempted. The project was absent in list_projects, so
fast indexing with persistence=false was run and returned indexed. Subsequent
search_graph requests returned project-not-found while also listing the project
as available. The reviewer then read only the exact files specified by the task.
No production source, tests, Git state, user stores, providers, or browser state
were changed. The only authored file is this report.

## Calculation review

The interval helper at decision_evaluation.py:91 uses z=1.96 and the Wilson
score formula. The clamp also contains the observed proportion at numerical
endpoints. The common summary at line107 supplies successes and n from the same
strict-valid labelled scored rows as accuracy, ECE, Brier and NLL. Errors,
invalid sums, unlabelled rows and expected labels absent from options do not
enter that denominator. Empty scored sets produce a null interval.

An independent stdlib Decimal calculation with precision60 solved the score
equation `(n+z²)q²-(2s+z²)q+s²/n=0`. Its two roots were compared against the
production helper for 29 distinct boundary/interior pairs across n in
1,2,3,6,11,100,1000. Maximum absolute endpoint difference was
`2.220446049250313e-16`, below the `5e-16` check tolerance. A separate exhaustive
grid checked all 501500 valid `(successes,n)` pairs for 1<=n<=1000: output n and
successes matched, and `0<=lower<=successes/n<=upper<=1` always held. The helper
returned null for `(0,0)`.

## Grouping review

Tag input is bounded to16 unique nonblank strings per immutable case, with the
existing string length128 bound. Both prediction and error cases share that
boundary. Duplicate request case IDs are already rejected. Thus each case can
appear only once in a given group. The evaluator ranks by total tagged case
count descending, then lexical tag order, publishes at most25 groups, and
explicitly reports omitted groups. Small and universal tags remain visible.

Both aggregate and each tag call `_summarize_decisions`; there is no second
scoring implementation. Strict/lenient validity, errors, missing labels,
ambiguity, lexical argmax ties and whole-confidence-tie selective coverage
therefore use the same rules. The changed digest generation omits empty tags
from the parsed canonical input while retaining nonempty metadata. Tests cover
the fixed prior canonical representation and old report parsing defaults.

## Executed evidence

Command:

```sh
.venv/bin/python -B docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q tests/test_decision_diagnostics.py tests/test_decision_evaluation.py
```

Observed: `87 passed in 0.60s`, exit0. This includes known Wilson values,
sample-size/endpoints, all exclusion classes, confidence ties, overlap, frequency
and lexical truncation, error-only/small groups, tag validation and limits,
immutability, legacy digest and additive report defaults.

A separate public-library driver parsed manual-cases.json through the production
request model and called evaluate_decisions in a temporary home before project
imports. Independent assertions observed:

| Result | Observed |
| --- | --- |
| Global total / scored | 6 / 2 |
| Global successes / interval n | 1 / 2 |
| Interval lower / upper | 0.09452865480086614 / 0.9054713451991339 |
| ECE / Brier / NLL | 0.45 / 0.6500000000000001 / 0.8573992140459633 |
| Selected count / coverage | 1 / 0.5 |
| Ordered tag total/scored/accuracy | en 3/1/0; ko 3/1/1; routing 2/2/0.5; ambiguous 1/0/null |
| Group interval n | en1; ko1; routing2; ambiguous null |
| Sum of group memberships / global cases | 9 / 6 |
| Probability source / calibration status | provided_probabilities / unverified |

The group membership total9 is an overlapping view of six cases, not nine
independent samples. No future-risk guarantee, multiple-comparison correction,
calibration proof, provider quality measurement or execution approval is emitted
by this implementation. RESEARCH.md states these interpretation limits. The
Wilson interval is applied only to accuracy, not ECE/Brier/NLL or empirically
selected risk. No upstream executable code was run.
