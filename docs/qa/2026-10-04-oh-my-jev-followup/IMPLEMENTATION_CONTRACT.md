---
title: Decision evaluation uncertainty and tag diagnostics contract
date: 2026-10-04
tags: [implementation, decision, statistics, compatibility]
---

## Additive public behavior

Preserve the existing API path, CLI command, authentication, error body, existing
metric denominators, strict/lenient sum policy, lexical argmax tie handling and
tie-group selective coverage. score_source remains provided_probabilities and
calibration_status remains unverified. Keep schema_version=1 for additive fields.
Existing reports missing the new fields must still parse with safe defaults.

Prediction and error cases accept optional tags: an immutable tuple of at most
16 existing bounded nonblank DecisionKey strings, default empty, no duplicates.
Unknown fields, invalid tags and duplicates fail at the existing input boundary.
Absent/empty tags preserve the prior canonical parsed-input SHA256; nonempty tags
are included in that fingerprint. Tags never change aggregate scoring.

Add metrics.accuracy_interval: nullable typed Wilson proportion interval, fixed
method=wilson, confidence_level=0.95, z=1.96, n/successes/lower/upper. Use the exact
strict-valid labelled scored set, not all predictions. n=0 returns null. n>0:
denominator=1+z*z/n; center=(successes/n+z*z/(2*n))/denominator;
radius=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator;
lower=max(0,center-radius), upper=min(1,center+radius). Handle numerical endpoint
roundoff; intervals always contain the observed proportion. Do not apply this
formula to ECE/Brier/NLL or empirically selected coverage/risk.

Add report.tag_diagnostics with total_tags, omitted_tags, fixed tag_limit=25 and
groups. Each group has tag plus the same typed summary fields as the aggregate:
counts, metrics including accuracy_interval, ece_bins, selective_coverage and
underdetermined. Reuse one common summary calculation, so error/unlabelled/invalid
sum exclusions and ties cannot diverge. Rank tags by total tagged case count
descending then tag lexical order; report at most 25. Include low-count/universal
tags with their counts rather than pretending to certify quality or hiding small
groups. Group members are unique cases; a multi-tag case belongs to each group.
Expose omitted count rather than silently discarding excess groups. Counts from
overlapping tag groups must not be added as independent global samples.

## Ownership and acceptance

Engine owner: engine/decision_evaluation_models.py, engine/decision_evaluation.py,
optional engine/decision_evaluation_statistics.py, tests/test_decision_diagnostics.py.
Surface owner: tests/test_decision_diagnostic_surfaces.py; existing surface test
fixtures may be reused. No API/CLI production change is expected: typed request
and response models already connect the same calculator through both surfaces.
Coordinate any additional file change with Root before editing.

Write meaningful red tests against current production symbols first, then minimal
implementation. Cover one-correct/one-wrong/empty/mixed scored cases, bounds and
legacy digest, tag invalid/duplicate/count limits, shared metric exclusion rules,
multi-tag overlap, deterministic top25/truncation, low-count/error-only groups.
Surface tests cover typed API and real CLI JSON, validation safe422/exit2, unchanged
missing-credential401, and OpenAPI fields. Isolate home/storage BEFORE project
imports; synthetic cases/tokens only, no provider calls/user stores or model loads.

Root uses the real CLI on synthetic JSON and independently checks known interval
values and denominator counts. Actual browser/site access is still saved-policy
blocked; do not use alternate browser/CDP/host alias/HTTP to bypass that block.
In-memory test clients are isolated contract tests, not a substitute observation
of the user's blocked site. No new dependency installation or Git mutation.
