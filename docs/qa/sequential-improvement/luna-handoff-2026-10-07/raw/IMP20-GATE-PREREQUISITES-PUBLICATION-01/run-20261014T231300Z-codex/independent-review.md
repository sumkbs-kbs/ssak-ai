# Gate prerequisites review

recommendation: APPROVE
scopeRecommendation: APPROVE_SCOPED
blockers: []

## Original intent and desired outcome

The user requested continued prioritized repair, independent verification, and publication of completed improvements. This review covers only the immutable range `481a634195bd3924ed601f1b881958c75e5e6892..f3a42e6f` in `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`. The desired outcome is reviewable gate prerequisites with truthful scoped evidence, preserved sandbox denial and release policy, and restored historical files whose provenance limits remain explicit. It is not a release approval or completion of the user's entire backlog.

## User outcome review

The range satisfies its scoped brief. No blocking defect was found in the owned changes. Accessibility now has a required gate that owns its server, but the recorded browser failures remain visible and unresolved in this range. Restored documents are explicitly historical; current HEAD remains NOT_APPROVED. No new live inference or full-suite success is inferred.

## Direct review

- `src/antigravity_k/engine/sandbox.py:164-210`: argv adjustment is limited to actual pytest entry points, preserving script, `-c`, and delimiter arguments. Explicit caller configuration remains authoritative. The existing required sandbox, network denial, read allow paths and denied roots are unchanged. Saved real-process cases cover Python flags, standalone pytest, local/explicit/environment config, and canonical-path denial.
- `tests/test_execution_request_preservation.py:71`: guard extraction retains exact original conversation, images, MIME and feedback assertions. It checks role/marker/uniqueness/propagation rather than pinning full English prose. The MAX retry guard limitation is explicitly retained in the report, not claimed fixed.
- `tests/test_durable_memory_purge.py:39`: initialized stores replace invalid closed/uninitialized doubles. Real Chroma/GraphML close/reopen outcomes, idempotent clearing, and closed-store preservation are asserted. Synthetic embeddings avoid model execution. `tests/test_fr_context_end_to_end.py:303` preserves summary provenance and assistant authority rather than promoting remembered text to system authority.
- `config.yaml:577`: newly explicit search and browser-memory defaults are disabled and match packaged configuration. The CLI discovery test uses an explicit metadata transport fixture; subprocess smoke and live inference are not conflated.
- `scripts/run_dashboard_e2e_ambient.py:244-283` and manifest accessibility row: selected specs use the owned server and finally-cleanup, return the runner's status, and do not execute unrelated suites. Required gate count remains 23. Mock tests prove dispatch/cleanup; actual browser results remain failing.
- `tests/test_cr14_fence_movement_detection.py:197`: ARCHIVED binds to the recorded candidate and requires NOT_APPROVED for current HEAD. ACTIVE still requires candidate == HEAD and matching commit/worktree fingerprints; mutation cases reject dirty, committed, docs-only and malformed declaration changes. This is an explicit historical-status correction, not a GA bypass.
- `tests/test_docs_toolchain_contract.py:147-226`: clean-tree fallback uses tracked production/deployment/package paths. Existing dirty/untracked content rules remain in force. Synthetic tracked and changed-fixture secrets are detected. This remains a scoped pattern check, not a full secret audit.

## Evidence independently checked

All paths below are under `docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/` in the ROOT checkout.

1. `IMP20-SANDBOX-PYTEST-BOUNDARY-01/run-20261015-sandbox/`: original manifest 44 entries and `argv-revision/artifact-manifest.json` 34 entries have matching bytes/SHA. JUnit confirms 16 focused and 15 boundary cases on the preceding candidate, then 7 argv cases on final source. Final argv source hashes match the immutable commit's two files. All four final static receipts exit 0. Initial zero-collection attempt is retained and not counted as reproduction/pass.
2. `IMP20-RUNTIME-REGISTRY-RECHECK-01/run-20261015T004000Z-runtime/`: final manifest 96 entries matches bytes/SHA; repaired source binding 11 entries matches the immutable commit. JUnit confirms 2 repaired, 4 precedence and 9 API cases. Original runtime 40 passing cases are retained separately from its two failures; corrected API uses asyncio after the first guard could not observe uvloop listen. No single clean combined invocation or uvloop claim is inferred.
3. `IMP20-DASHBOARD-GATE-OWNERSHIP-01/run-20261014T224200Z-codex/`: corrected manifest 55 entries matches bytes/SHA; final three-file source binding matches the commit; JUnit has 24 tests, zero failures/errors/skips; four static receipts exit 0. `result.json` reports accessibility 33/2, witnesses 18/12 and ambient 11/5. These are not passing browser gates.
4. `IMP20-TEST-CONTRACT-FIXTURES-01/run-20261014T224233Z-contracts/`: v1 JUnit has 27 passes; revision-v2 JUnit has 10 passes. All eight v2 source-binding entries match the commit. The v1 request-test hash differs as expected because v2 replaces its full-prose assertion; the remaining v1 source entries match. Counts are not added as distinct coverage. Two HTTP cases were outside this scoped selection.
5. `IMP20-RELEASE-DOC-CONTRACTS-01/`: manifest 60 entries matches bytes/SHA. All seven owned source hashes match the commit. Source-bound JUnit has 102 tests, zero failure/error, one existing historical-report skip: 101 passed. All 14 restored committed blobs equal the existing ROOT originals byte for byte. `restored-files.json` explicitly marks historical byte verification false; this review does not upgrade that provenance.

In-memory unified-patch replay from baseline Git blobs reproduced final commit bytes for sandbox 2 files, dashboard 3, runtime 2, fixture v2 1, and document edits 7. No patch was applied to a checkout. The archive additions were compared directly with the existing original bytes. Manifest validation counts above are file references, not distinct test coverage or independent runtime executions.

## Programming and remove-ai-slops review

Consulted both skill entries and directly reviewed the diff, tests and changed production code for tautological assertions, implementation-only mirroring, deletion-only tests, unnecessary extraction/parsing/normalization, error suppression and scope drift. No criterion-blocking instance found. The narrow argv helper is necessary to preserve caller arguments while bounding pytest discovery. Purge tests observe persisted behavior, secret-scanner tests plant actual invalid patterns, and declaration tests mutate real Git states. Dispatcher mocks are limited to ownership wiring and supplemented by the preserved failing real browser observations; they do not stand in for product approval.

The fixture v2 report explicitly records programming review and removal of prompt-prose overfitting, including two pre-existing generic-exception audit findings. Other packets do not uniformly include a separately titled skill checklist. This direct pass supplies the missing review perspective; no missing checklist is treated as a blocker.

## Exact limitations and follow-up boundary

- Full 23 gates on this candidate and the new 8-hour soak are NOT_RUN; release remains NOT_APPROVED.
- Browser product failures remain open; the uncommitted UI changes owned by another agent were excluded.
- No tests, providers, inference, network, servers, or historical probes were rerun for this review. This is stored-evidence verification plus immutable source review.
- Historical report skip and unknown historical archive bytes remain unresolved. Current file identity is not execution provenance.
- Existing first-attempt failures, narrower subsequent selectors, and packaging corrections are retained. They must remain distinguished when publishing.
- `omo-agent-toolkit ulw-loop status --json` returned ULW_LOOP_PLAN_MISSING. The requested fallback report path was used; no loop was created.

Only this report file was written. ROOT staging and all candidate files were left untouched.
