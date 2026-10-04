---
title: Functional upgrade final runtime audit
date: 2026-10-03
tags: [qa, runtime-audit, final-gate, functional-upgrade]
---

# Final runtime audit — FAIL

## recommendation

**REJECT** pending completion of the required browser interaction matrix and scoped cleanup.

## identity

- `exactHEAD`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- `source_hash`: `c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`
- scoped patch: `docs/qa/2026-10-03-functional-upgrade/task.diff`
- patch SHA-256: `10a17e0aa578ca10cffe67fb2362360b383c05393493700318a5fc9544c1d90a`
- scoped paths: the 24 entries in `changed-files.json`

I reproduced the checkout HEAD and verified all 308 current files against
`source-manifest.json`; mismatches were `0`. The aggregate source hash is therefore
bound to the reviewed source rather than inferred from HEAD alone.

## originalIntent

Apply the bounded frontend functional upgrade selected from the pinned public Codex
comparison: bind chat callbacks to their conversation/project/run owner, render
progressive output without stealing reading position, retain queued text and attachment
ownership, consume the canonical source-preserving conversation-fork contract, and
make ambiguous task submit/fork failures explicitly retryable with the same captured
operation and idempotency key. Preserve the SSAK-AI Constitution, Brain/Body authority,
append-only history, existing visual system, authentication policy, and user stores.

## desiredOutcome

The shipped dashboard should reject late chat/fork/task work after its owner changes,
show progressive output safely, retain dependent queued work after parent failure,
adopt canonical fork history without altering the source, and recover a lost submit or
fork response without duplicating server work or crossing project/session/credential
scope. The required real-browser matrix must demonstrate the named response-loss,
fork, multi-tab, rapid-action, delayed-response, late-selection, crossover, and clean
restart boundaries on the matching source. Test-only processes and the isolated
`Path.home` helper must be removed at closeout.

## userOutcomeReview

The automated/runtime portion is strong. My independent current-tree Vitest run passed
7 files and 51 tests, covering the actual run-ownership component, fork hook and
integration, task operation/API failure logic, event hook, and queue panel. The manual-QA
executor independently passed 13 files and 102 tests plus TypeScript. Supplied logs show
the full dashboard at 109 files / 1,088 tests, production build success, and 26 isolated
backend contract tests passing. The real fixture HTTP transcript records an intentional
empty response after commit followed by a same-key `202` for both submit and fork, with
`created_tasks=3` and both keys at two attempts. The fresh browser capture visibly shows
the submit response-loss state, retained draft, and named `같은 작업 다시 시도` control.

Those observations do not complete the required browser interaction matrix. The current
`REVIEW_QA.md` verdict is explicitly `FAIL` and records no browser action evidence for
fork loss, two-tab/session isolation, rapid submit, delayed response, late fork-source
selection, tab crossover, or clean browser restart. Static screenshots, source reading,
and jsdom tests do not substitute for those stated browser criteria. No product defect
was inferred from the transient viewport capture-pipeline problem reported by the root;
only the finalized QA artifact is used here.

## hypotheses and observed values

| Hypothesis | Distinguishing observation | Result |
|---|---|---|
| H1 run-state ownership permits a stale callback to finalize or mutate a newer run | Independent run-ownership/fork/task Vitest: `7` files, `51` tests, exit `0`; executor focused run: `13` files, `102` tests, exit `0` | Refuted on automated runtime surface |
| H2 transport response loss creates duplicate submit/fork work | Real fixture transcript: first submit/fork receives empty reply after commit; exact repeat returns `202`; final `created_tasks=3`, submit attempts `2`, fork attempts `2` | Refuted on fixture HTTP surface |
| H3 canonical revision/source identity is lost across fork or stale history | Fork/run tests pass canonical-history adoption, source preservation, stale-result rejection, and revision-conflict refresh; API body/header tests pass | Refuted on automated runtime surface |
| H4 owner/project/session identity can drift during task replay | Task hook/API tests pass project switch, asynchronous owner change, captured header, and same-operation replay cases | Refuted on automated runtime surface |
| H5 matching browser interaction evidence covers every required adversarial boundary | `REVIEW_QA.md` marks FU-S04, FU-S08, FU-S09, FU-S11 and FU-E01 through FU-E05 browser coverage missing/failed | Confirmed evidence gap; blocking |

## direct programming and remove-ai-slops pass

I directly applied the `omo:programming` and `omo:remove-ai-slops` criteria to
`task.diff`, the changed production paths, and their tests. I found no deletion-only,
requested-removal, prompt-prose, tautological, output-derived, or purely
implementation-mirroring tests. The tests distinguish observable races, request bodies,
retry identity, scope changes, queue ownership, and canonical adoption. The new helper
modules correspond to real asynchronous ownership/trust boundaries; no unnecessary
parser, normalization layer, dependency, pass-through factory, debug statement, or
credential/attachment persistence was added. Oversized inherited modules remain a
maintenance NOTE because no stated success criterion requires a refactor. The separate
`REVIEW_CODE.md` explicitly records the same skill-perspective and overfit/slop coverage;
its `null as string | null` note was shown by the baseline archive to be inherited.

## blockers

1. **violatedCriterion: C11 / FU-S04, FU-S08, FU-S09, FU-S11, FU-E01–FU-E05**  
   **Observation:** the required matching-source browser interaction matrix is incomplete;
   fork-loss UI, two-tab/session isolation, rapid submit, delayed retry, late source
   selection, tab crossover, and clean browser restart have no accepted final browser
   action evidence.  
   **evidencePointer:** `docs/qa/2026-10-03-functional-upgrade/REVIEW_QA.md` sections
   `surfaceEvidence` and `adversarialCases`.

2. **violatedCriterion: final cleanup / Phase 9 closeout**  
   **Observation:** at audit time PID `54241` was still listening on
   `127.0.0.1:50084`, and `/tmp/ssak-functional-isolation-20261003-root` still contained
   the test-only home/helper. Root confirmed these remained active for ongoing QA, so
   cleanup was not falsely claimed.  
   **evidencePointer:** live `lsof -nP -iTCP:50084 -sTCP:LISTEN` and filesystem existence
   check; cleanup ownership described in `DEBUG_JOURNAL.md` and `QA_PREPARE.md`.

## cleanupState

- Production authentication, user store, system `HOME`, and persisted conversation data:
  no audit mutation performed.
- This reviewer started no browser, server, fixture, debugger, instrumentation, or
  network POST, and installed no dependency.
- Root-owned fixture PID `54241` on port `50084`: **active at audit cutoff**.
- Root-owned test isolation directory
  `/tmp/ssak-functional-isolation-20261003-root`: **present at audit cutoff**.
- Durable evidence under `docs/qa/2026-10-03-functional-upgrade`: retained as required.

## checked artifact paths

- `docs/frontend/CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md`
- `docs/qa/2026-10-03-functional-upgrade/{task.diff,changed-files.json,source-manifest.json,bundle-manifest.json}`
- `DEBUG_JOURNAL.md`, all `*IMPLEMENTATION.md`, `QA_PREPARE.md`
- `dashboard-tests.log`, `dashboard-typecheck.log`, `dashboard-build.log`,
  `backend-contract-tests-isolated.log`, `fixture-final-build.log`
- `fixture/http-verification.txt`, `task-browser-first-state.json`
- `review-source-integrity.txt`, `review-focused-vitest.txt`,
  `review-fixture-readonly.txt`
- `REVIEW_CODE.md`, `REVIEW_CONTEXT.md`, `REVIEW_SECURITY.md`, `REVIEW_GOAL.md`,
  `REVIEW_QA.md`, `EVIDENCE_LEDGER.md`
- task response-loss captures and metadata under `captures/`
- all 24 paths listed in `changed-files.json`

## exact evidence gaps and limitations

- This reviewer could see listeners on ports `8000` and `50084`, but sandboxed loopback
  GETs returned curl exit `7`; no HTTP success is attributed to those failed reads.
- Browser operation was intentionally left to the root's CUA session. This report does
  not claim direct browser actions by this reviewer.
- The full 1,088-test suite and production build were inspected from retained logs; the
  independent rerun was the focused 51-test runtime set.
- Approval can be reconsidered only after a replacement/final QA artifact supplies the
  missing interaction evidence on this exact source hash and a cleanup receipt shows the
  fixture listener and test-only helper removed.
