# Independent scoped gate review

recommendation: APPROVE
deliveryVerdict: APPROVE_SCOPED
blockers: []
reviewed: 2026-10-15

## Original intent and desired outcome

originalIntent: Continue priority-ordered repairs, review, and eventual commit/push. This assignment is the independent review of the startup project-root repair and a separate Doctor test-hermeticity change, not authorization to claim full release readiness.

desiredOutcome: The actual API lifespan passes configured absolute/relative roots to RAG and IDE and the default hook/audit directory; the unset PathConfig default and explicit hook override remain valid. Doctor's capability-output test uses a controlled real registry instead of depending on external catalog order.

userOutcomeReview: The four-file candidate satisfies that bounded outcome. The shared startup root is changed once, with no new production parsing, normalization, extraction, or alternate lifecycle. The six cold cases distinguish configured roots from fallback and explicit hook roots from defaults. Doctor's existing output assertions remain and its three representative profiles are explicit. The change does not fix downstream CWD-based project selection, five-second cold readiness, full gates, soak, or model quality.

## Scope and criteria

WT2: `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`

Base: `7360c78544abeea41e38c65faa6eba2610a8a33b`. Inspected current diff and status: exactly three modified tracked files and one new test.

Review criterion IDs below label the assignment's stated requirements, not newly invented product requirements:

- ROOT-1: Configured root reaches lifespan RAG/IDE/default hook/audit consumers.
- ROOT-2: Unset default and explicit hook override are preserved.
- DOC-1: Doctor test is hermetic to catalog contents/order and preserves capability-output coverage.
- EVID-1: Evidence binds the current four files and distinguishes scoped passes from raw failures and untested claims.
- SCOPE-1: No additional product changes or global readiness claim.

All five are supported. No criterion violation found.

## Checked artifacts and independent results

Packet aliases, relative to `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`:

- S = `docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-STARTUP-PROJECT-ROOT-01/run-20261015T011000Z-codex`
- D = `docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-DOCTOR-GATE-FIXTURE-01/run-20261015T011500Z-codex`

Read the exact four source/test files, their diff against base, surrounding lifespan consumers and PathConfig/default definitions. Current SHA-256 independently calculated:

| File | SHA-256 |
|---|---|
| src/antigravity_k/api/server.py | 0ffb369335863d266f56e2903067610ed3a2d67dea15dd4d746683b7333bb306 |
| tests/test_lifespan_agency_root_contract.py | 16b6d8cb74f013022648d12ae0bd7cb568ecb2559afca9522bff8f03a81039cf |
| tests/test_lifespan_configured_project_root.py | e6fd37b5b5379b1c0909b1ac26e748df149110717bbba22d753d1b99ea36321f |
| tests/test_doctor.py | 261e0b7a3b124b6668401bb1766d19244d6c23c6a540fffe25052ee22afb6e57 |

Independently rehashed every entry in S/artifact-manifest.json (158), S/primary-startup/supplemental-manifest.json (14), S/primary-startup/attempt-02/review-manifest.json (11), D/artifact-manifest.json (64), and D/order-preservation/artifact-manifest.json (10): no missing files or SHA mismatches. S/handoff-ko.md correctly discloses that it was added after the original manifest. Manifest verification is integrity evidence, not proof of program execution by itself.

Read S/result.json, source-binding.json, handoff-ko.md, red-01/junit.xml, green-01/junit.xml, green-02/junit.xml and all six green-02/captures/*/receipt.json. Parsed JUnit confirms red 6 tests/4 failures, final 35 tests/0 failures/errors/skips (JUnit time 6.674 seconds). The six receipts show selected roots, hook precedence, forbidden=[] and real_rag_chunks=1 in all four configured-root cases. Defaults intentionally do not scan the real checkout. Compared all three S/patch-replay/replay files directly with WT2: byte-identical. This checks the saved replay output; no patch was reapplied to the working tree.

Read S/static-02/type.stdout.txt and check metadata, D/candidate-01-static/type.stdout.txt and packet handoff. Stored type outputs show zero errors/warnings; stored lint/format/compile receipts report exit zero. These are verified stored artifacts, not newly rerun checks.

Read S/primary-startup/primary-manual-review.md, qa-correction.json, attempt-02/run_once.py, result.json, review-result.json, health.http.txt, server.stderr.txt, uvicorn-capture-signals.txt. Actual logs show one-file RAG indexing, configured hook/audit initialization, HTTP 200, HookEventBus shutdown and completed application shutdown. The actual process exit remains -15, with forced=false, reaped=true and group-empty=true in the raw receipt. The raw harness predicate explicitly requires returncode==0; its FAIL is retained. Installed Uvicorn server.py hashes to `7d7937fff1c17f583ea21ff8fce5c8a5bf2d9d3c9a7f1b9646211eb7a49012f3`, matching the review binding. Its captured source restores handlers then raises captured signals after cleanup. The separate scoped reconciliation is therefore justified; it does not manufacture exit zero or overwrite raw FAIL. The first timeout/forced -9 remains failed, including the correction that audit close was not observed. No five-second readiness or checkout-CWD fix is inferred.

Read D/handoff-ko.md, result.json, patch-reconstruction.json, order-preservation/receipt.json and verify_preimage.py. Parsed all six D JUnit artifacts: red-01 actually passes; red-02-ambient and red-03-full-env each fail once; green-01-full-env passes 3, green-02-ambient passes 1, order-preservation passes 1. Independently compared order-preservation/overlay/tests/test_doctor.py to base Git bytes: identical. The replay script explicitly uses sort_keys=False. Thus the evidence supports a test fixture repair, not a Doctor product bug. Original output assertions are retained; the three observed probe calls are checked with refresh=False.

## Direct programming and remove-ai-slops review

Consulted both installed SKILL.md files and programming/references/python/README.md. Applied the requested review criteria directly rather than running a cleanup or expanding scope.

- Excessive/useless tests: no blocker. Six parameter combinations exercise independent configured/default and override boundaries; four original-code failures establish sensitivity. The adjacent agency assertion changes because this task explicitly expands its former agency-only contract.
- Deletion-only/removal tests: none introduced.
- Tautological/implementation-mirroring tests: the root receipts inspect real lifespan arguments with distinct inputs and real tiny-RAG behavior; they are bounded seam tests, not proof of every collaborator. Doctor drives the CLI with a real ModelRegistry and retains rendered capability/status/remediation assertions. Its exact call-order assertion is narrower than a pure output test but matches the controlled fixture and is not the sole correctness oracle.
- Production extraction/parsing/normalization: none added. Existing typed Path configuration is reused with one string conversion at the existing consumer seam.
- Maintenance/false-confidence notes: the subprocess probe embeds dynamically typed Python and uses asyncio, so outer-file type success does not establish typing inside the string and the skill's stricter async preference is not met there. The existing server is oversized. These do not violate the assigned behavioral success criteria and do not justify unrelated refactoring. The many subsystem doubles are explicitly disclosed and complemented by stored real startup evidence; IDE listener remains untested.
- No prose pinning, test deletion to hide failure, new dependency, public API change, redundant production guard, or speculative abstraction found in the diff.

## Exact evidence gaps and limits

No separate code-review report with explicit skill-perspective/overfit coverage or notepad path was supplied or located in the two task evidence directories. The executor handoffs do not explicitly cover that checklist. This independent direct source/diff/test pass supplies the missing review coverage; absence of a separate report is not a behavioral blocker under this assignment.

No ULW-loop plan exists: `omo-agent-toolkit ulw-loop status --json` returns ULW_LOOP_PLAN_MISSING. This report uses the mandated fallback evidence location; the assignment-named review file points here.

No tests, HTTP, native/model work, or startup executions were repeated. No source/test/Git changes were made. Graph indexing was not retried; exact-path fallback followed the supplied prior unindexed/index-timeout evidence. Memory registry search produced no task-specific match and no historical memory fact was used.

The older full-gate result is excluded from approval. This report does not approve all 23 gates, a whole Python suite, eight-hour soak, GA, live inference quality, global zero provider calls, real IDE listener behavior, or CWD-independent downstream project selection. Stored client-side zero request counters cannot prove global zero inference. Subsequent commit/push and any broader gate remain the parent task's responsibility.

ROOT checkout divergence: directly read ROOT `src/antigravity_k/api/server.py:63`; it already contains `project_root = str(config.paths.project_root.resolve())`, whereas reviewed WT2 uses `str(config.paths.project_root)`. Approval binds WT2 only. ROOT absolute canonicalization and its broader unrelated/staged changes are not the tested candidate and must not inherit this approval. Parent states it will preserve that independent ROOT change; this review makes no ROOT overwrite or merge recommendation.
