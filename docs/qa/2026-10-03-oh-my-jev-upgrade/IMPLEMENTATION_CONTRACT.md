---
title: Decision probability evaluation implementation contract
date: 2026-10-03
tags: [benchmark, calibration, implementation]
---

## Public contract

New engine files: `engine/decision_evaluation_models.py` (typed input/output),
`engine/decision_evaluation.py` (`evaluate_decisions(request) -> DecisionEvaluationReport`).
No provider calls, configuration writes, model selection, or eligibility changes.

`DecisionEvaluationRequest`: optional bounded `model_id`, `dataset_id`; `risk_budget`
finite numeric 0..1, default 0.05; `cases` max 1000 records (empty allowed).
Cases are a discriminated union on `status`:

- prediction: `case_id`, `status: prediction`, `options` (2..64 unique nonblank string
  keys, each max 128 characters), `probabilities` (same length, finite numeric 0..1;
  reject booleans/coercion), optional `expected_key`, `underdetermined` strict bool
  default false. Underdetermined plus expected_key is rejected. Unknown expected
  keys are accepted for diagnostic counting but excluded from every scored metric.
- error: `case_id`, `status: error`, `error_code` limited to provider_error, timeout,
  invalid_response. No free-form provider error, credentials, prompts or logging.

Every case_id is unique, bounded 128 characters. Extra fields rejected; immutable
parsed models. Sum tolerance: strict 1e-3, lenient 2e-2 (inclusive); never repair or
normalize invalid vectors. Only strict-valid predictions enter scored or ambiguity
metrics. Lenient validity is diagnostic only.

Report includes schema_version=1, supplied model_id/dataset_id, canonical parsed
input SHA256, score_source=provided_probabilities, calibration_status=unverified.
Typed counts: total, predictions, errors, strict_valid, lenient_valid, invalid_sum,
scored, unlabeled, missing_expected_label, underdetermined, tied_predictions.
unlabeled includes underdetermined; missing_expected_label counts strict-valid
records whose truth is outside options. invalid_sum=predictions-strict_valid.

Metrics: accuracy, ece, brier, nll all share the same scored denominator. Empty
denominators return null, never zero quality. Strict/lenient valid rates divide by
predictions; error_rate divides by total. Brier is mean multiclass sum of squared
one-hot errors, without dividing by number of options. NLL clips truth probability
at 1e-15. ECE uses 15 equal-width bins, last includes confidence 1; expose bins with
bounds/count/mean_confidence/accuracy (empty mean/accuracy null).

Argmax ties choose lexical smallest option key, independent of option order, and
are counted. Selective coverage groups identical confidence ties before considering
any cutoff: largest entire confidence prefix with empirical error <= risk_budget.
Return risk_budget, selected_count, confidence_threshold, coverage, empirical_risk.
No scored cases: coverage null; scored but zero accepted: coverage 0, threshold and
risk null. This is descriptive empirical risk, never an approval/safety guarantee.

Underdetermined diagnostics: count, mean_max_probability, high_confidence_rate
(max >=0.9), uniform_deviation (mean abs(max-1/K)); no truth means no accuracy.

## Production surfaces and ownership

Worker A owns only the two engine files and `tests/test_decision_evaluation.py`.
Worker B owns only `api/routes/decision_evaluation_api.py`, router registration in
`api/routes/__init__.py`, `decision_evaluation_cli.py`, tiny root cli.py registration,
and `tests/test_decision_evaluation_surfaces.py`. B imports A's exact public names.
CLI command `decision-eval INPUT.json`: parse with model_validate_json; bounded
2MiB read; plain JSON report stdout; safe generic failure stderr and exit 2 for
input/file failures, no full validation input/error echo or traceback. Help describes
unverified caller-supplied probabilities. API route response_model is typed report;
existing global /api/ auth applies. Do not alter authentication/public allowlist.

The main agent owns this contract, analysis/results/checklist, evidence and direct
CLI/real HTTP QA. Each worker records meaningful RED then GREEN and respects all
shared edits. Isolate Path.home before importing config during tests; never modify
real user data, tokens, PIN, or model settings. No Git mutation or dependency install.
