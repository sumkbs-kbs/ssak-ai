---
title: Backend budget, output contract and profile review
date: 2026-10-04
tags: [qa, code-review, output-contract, context-budget, read-only]
---

Verdict: **PASS** for the frozen scope below. **Blocking files/lines: none.**

This review covers `quality_gate.py`, `context_budget.py`, `user_model.py`, their
three focused regression modules, and the existing `test_final_prompt_budget.py`
baseline. Unchanged provider, tool-loop, registry and chat-route source was read
only to verify the affected boundaries. The reviewer made no production/test
edits, project imports, private-home accesses, provider/network/model calls or
Git mutations. This report is the reviewer's only retained file.

## Resolved review findings

The first quality candidate incorrectly interpreted a function mentioned in a
JSON explanation or numeric-result question as a request for source code.
Independent AST-only execution reproduced C/0.3 with retry for valid
`{"purpose":"increment"}` and `9`. The intermediate candidate still rejected
"Show the number returned by this function", "Write a summary of this function",
and "Provide the purpose of this function". It also incorrectly rejected `9.5`
under a generic number-only comparison when an integer was only an input topic.
An explicit source request phrased "Give me a Python function" incorrectly
accepted `9`; initial source-request controls containing `Code only` did not
exercise this predicate independently.

The frozen correction at `quality_gate.py:271` binds generation verbs to direct
source objects, and `quality_gate.py:303` binds integer restriction to the actual
integer-only directive. The new test controls remove the `Code only`/`코드만`
shortcut where they must distinguish program source from a program's output.
Description/result cases use default execution for reasoning and coding routes;
complex-route cases explicitly use build mode.

Independent execution of the final source's AST in a fresh Python process passed
**24 cases, zero mismatches**. Function descriptions/results, the descriptive
verb variants, and mixed integer/decimal comparisons returned A without retry.
Explicit integer-only decimal failures and explicit source requests without the
code-only shortcut still returned C with retry. Valid code-only source passed.
Malformed JSON, missing explicitly requested tables, internal tags within valid
JSON, unsafe commands within valid JSON, and invalid Python syntax still retried.
A short shape-valid answer reached the supplied semantic verifier exactly once;
its rejection returned C with retry. This driver loaded only this source AST and
standard-library modules, with no project import or filesystem writes.

## Budget and profile assessment

`context_budget.py:61` preserves exact-name precedence and falls back to the
registered repo identity. Calibration budgets for both registered identifiers
are combined conservatively at `context_budget.py:91`. The hard final-input
ceiling at `context_budget.py:253` reserves completion inside the shared provider
window: **28,672 estimated input tokens + 4,096 reserve = 32,768**. The provider's
unchanged `_context_window` uses the existing shared helper; the legacy streaming
request also uses `MAX_CONTEXT_TOKEN_LIMIT`. No second reserve deduction was
introduced into that provider helper.

The source-derived fixture is above the former 8,000-token fallback and fits the
corrected ceiling without compression. The new tests retain an explicit 8,000
operator halt, lower empirical ceilings through either alias, and rejection of
mandatory input that would consume completion reserve. The unchanged final
enforcer checks serialized size and the reserve-inclusive ledger, and still
raises typed errors rather than dropping mandatory prompt components.
`test_final_prompt_budget.py` matches the worker's captured baseline hash; its
existing working-tree differences from HEAD predate this batch.

`user_model.py:238` checks the existing request predicate before directory
creation, timestamp mutation, GBrain synchronization and JSON writes. Session
learning remains in memory. Denied direct saves, fifth-observation writes,
preservation of existing bytes, and later permitted saves are covered by the
focused tests. The final subprocess setup patches `Path.home()` before imports,
asserts the temporary GBrain store, and preserves inherited home environment
variables. Static caller review confirms the real streaming path binds policy
before `contextvars.copy_context()` and executes each generator step under that
context (`chat.py:1232`, `chat.py:1239`, `chat.py:1249`); the profile guard is not
removed by that thread-pool boundary. No full HTTP/runtime test was performed by
this reviewer.

## Evidence and limits

Worker evidence reports final quality **61 focused / 111 regression passes**,
budget **25 leaf passes**, and profile **5 focused / 2 existing preference
passes**, with focused static/type checks passing. The reviewer inspected their
assertion seams and reports, performed the independent quality driver above,
and verified all **19** entries in `budget-sha256.json` against current bytes.
The reviewer did not rerun project-importing pytest suites or read private/raw
application logs.

The reports correctly distinguish a constructed source-only prompt fixture from
the unavailable complete live post-read ledger. R2-05's original file read
succeeded before the post-read prompt halted at the erroneous 8,000 input limit;
the root owns the successful app retry. Pure post-loop evidence shows two
needless revisions of an already shape-valid `9` in the old gate. It does not
establish that those revisions caused the particular live R2-06 table response:
the initial provider draft and request-level rewrite receipts were not captured.
Shape checks do not prove a number or JSON value factually correct. The unchanged
planning check can still reject complex tasks in default execution mode; this
review does not claim that separate policy behavior was fixed.

Graph-first discovery was attempted: the listed Ssak-Ai project initially had
zero nodes, symbol search reported it absent, and one fast refresh with
`persistence=false` returned indexed but subsequent searches/status still found
no project. The OMO graph was also unavailable. Bounded known-file reads and
symbol searches were used after those insufficient results; no second index or
project-local graph was created.

## Frozen fingerprints

Actual HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

| File | SHA-256 |
| --- | --- |
| `src/antigravity_k/engine/quality_gate.py` | `1d905c500a60a7f2f722b8d9118e73c8910ee73e766082e8336669e4de2bfd55` |
| `src/antigravity_k/engine/context_budget.py` | `9eea0d25f007f1cb803f90ac0f437d74b72742822972da7b295020e8aa945621` |
| `src/antigravity_k/engine/user_model.py` | `ecfb1629dc4ad9e586c2c32ba7c1b2ada60c12960b824d1488ee74e6a43110ee` |
| `tests/test_quality_output_contract.py` | `2df7fdad881dde21a937d187c7cfcd26661411cedc1d2bf54252d8a5d236891a` |
| `tests/test_qwen_repo_prompt_budget.py` | `a61c338523b00bdce4cbf763658e34bb5bb0a908838b957b0523e6d64717e29f` |
| `tests/test_final_prompt_budget.py` | `3855164d5248864e5f79c18e623fcd6ab5e856488739265b36aba32bd6f5978f` |
| `tests/test_user_model_request_policy.py` | `6f4ab1cdd55f1a568545c9ef5e881b4097144ff2ab2167b8f5a48ed821b6157a` |
| `docs/qa/2026-10-04-full-live/quality-verification.md` | `430656f5cc74f87b4da682dab67a6210c8ed618100faab356ac562223d32f3ea` |
| `docs/qa/2026-10-04-full-live/budget-report.md` | `584e6e1a3e618670391e78a3eb603684512c84d56e2f9033f9058aaeff743582` |
| `docs/qa/2026-10-04-full-live/profile-findings.md` | `33cdc9ae2a51cf5e7c26375a03b6bc1ba7043a39e7a14b67fed33710b68b5786` |

The programming Python and debugging Python/partial-runtime-evidence references
were read. Existing legacy type/style structure was not used to demand an
unrelated refactor. The PASS is scoped to these frozen files and evidence limits.

Late skeptical evidence verification: **PASS** at the full HEAD above. The peer
matched all ten frozen file hashes and confirmed test-count consistency,
root-only live attribution, the fixture/live-ledger distinction, and the stated
static-only async-context limit. No material gap was found.
