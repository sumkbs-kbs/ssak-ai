---
title: Quality gate constrained reply false retry verification
date: 2026-10-04
tags: [qa, quality-gate, output-contract, regression]
---

The pure quality-gate and production post-loop seam now preserve concise replies
when no concrete format or verifier failure exists. This verifies gate behavior,
not model factual correctness or the cause of a particular live app response.

## Reproduction and result

The failing-first suite in `quality-red.log` recorded 10 failures and 8 passes.
For the numeric comparison request, the original gate returned C at 0.45 because
of lexical overlap and an unrequested comparison table. The real post-loop
adapter generated the same `9` twice. Short reasoning JSON, uncertainty, and status
replies received C at 0.35 from length and lexical overlap. Malformed JSON passed
without a post-loop revision. The short-reply verifier was not invoked.

`quality-green.log`: initial **29 passed in 0.88s**.
`quality-function-subject-green.log`: final **61 passed in 2.61s**.
`quality-regression.log`: final **111 passed** across the new suite, quality gate,
quality checkers, output quality, engine context quality, and quality/context
approval suites. Assertions cover machine grades, retry decisions, generation
counts, and retained outputs; no revision prompt prose is asserted.

`quality-contract-boundaries-red.log`, `quality-format-scope-red.log`, and
`quality-table-scope-red.log` record additional failing-first boundary cases.
These establish that program output constraints must not be imposed on its source
code, that topic words such as Python/status code must not override explicit reply
formats, and that Korean `발표로` must not be mistaken for a table request.

The independent reviewer then reproduced remaining function-subject and integer-
topic defects. `quality-function-subject-red.log` captured 12 failures for English
and Korean function explanations/results, including reasoning/coding with default
execution mode and complex with explicit build mode. `quality-integer-topic-red.log`
captured two failures for decimal answers when an integer was merely an input
topic. `quality-source-object-red.log` captured verb/object distinctions such as
showing a result, writing a summary, providing a purpose, and giving actual source.
The final 61-case suite passes these boundaries and preserves explicit source
requests without `Code only`/`코드만` shortcuts.

## Implementation

- Removed unconditional character-length and request/output word-overlap penalties.
  Neither establishes semantic completeness or relevance.
- Applied narrow JSON-only and single-number contracts before general code checks.
  JSON is parsed and non-finite constants are rejected. Integer-only wording
  requires an integer literal. Explanatory prose, fences, tables, or multiple
  values fail a matching scalar contract.
- Kept code contracts for explicit source requests whose program emits a
  constrained value. Generation verbs bind to the source object directly rather
  than a function/topic mentioned later in the sentence. Explanation and result
  questions retain JSON/numeric reply formats even when routed as coding.
- Integer-only checks bind to the requested integer-only directive, rather than
  an integer mentioned elsewhere in a generic numeric comparison.
- Required a comparison table only for explicit table wording, with missing
  requested tables still causing retry.
- Allowed short structurally eligible replies to reach `verify_fn`. A rejecting
  verifier still causes retry. Empty output, internal tags, repetition, unsafe
  commands, code syntax, requested code/complexity, planning, and readability
  checks remain in the evaluation flow.

## Runtime evidence and limits

`quality-runtime.jsonl` contains a direct library driver: numeric-only `9` and
valid JSON pass structurally; malformed JSON and a table against numeric-only
wording return C at 0.3 with retry. All driver records explicitly state
`semantic_verification: not_configured`. A wrong number can still satisfy its
shape; this change does not calculate or assert the correct model answer.
The final driver also accepts function-purpose JSON, function-result scalars, and
a decimal under a generic number-only request containing an integer input topic;
it rejects a decimal under an explicit integer-only directive.

Complex-label description cases are tested in explicit build mode. The unchanged
planning check can still reject complex tasks in default execution mode; the
production post-loop method does not forward an execution mode. This work does
not claim to resolve that separate planning-policy behavior.

Post-loop tests use the real gate and real production recovery method with an
in-memory generator. Shape-valid numeric output now produces zero revisions;
unrepairable JSON/tag failures receive two configured attempts; an empty
generator result stops after the first attempt. These receipts do not establish
that a quality rewrite caused the lead agent's observed live table response.
The initial provider draft and request-level rewrite receipts were not captured
for that live response. The lead agent owns the app retest after restart.

No model/provider calls, app actions, installs, or Git commands were used by this
worker. During initial collection, global GBrain attempted a real-home lock and
the sandbox denied it before a write. The final broader command patches
`Path.home()` to a `TemporaryDirectory` before imports; focused post-loop imports
also occur after the isolated-home fixture. No home environment variable is
reassigned. `uv` uses a worker-owned temporary cache with `--no-sync --offline`.

## Static checks and fingerprints

`quality-static.log`: **All checks passed** (Ruff on the two owned code files).
`quality-types.log`: **0 errors, 0 warnings, 0 notes** (focused BasedPyright).
`quality-strict-audit.log` identifies four existing legacy violations: mutable
`QualityScore`, missing dataclass slots, the oversized module, and the verifier's
broad exception boundary. Those surrounding structures were present before this
fix. They were preserved to keep the delegated change limited to the false-retry
defect. The new test file has no strict-audit violation.

Final source SHA-256:
`1d905c500a60a7f2f722b8d9118e73c8910ee73e766082e8336669e4de2bfd55`.

Final test SHA-256:
`2df7fdad881dde21a937d187c7cfcd26661411cedc1d2bf54252d8a5d236891a`.

Hashes and measured nonblank/noncomment line counts are in `quality-hashes.jsonl`.
Only `quality_gate.py`, the new test file, this worker's `quality-*` evidence,
and its shared-journal section were changed. No debug source instrumentation was
created.
