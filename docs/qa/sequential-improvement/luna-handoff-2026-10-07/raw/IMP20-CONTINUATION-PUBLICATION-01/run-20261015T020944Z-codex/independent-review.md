# IMP20 continuation stored-source review

codeQualityStatus: WATCH
recommendation: APPROVE
blockers: []

Scope: current continuation.py, collector_proxy.py, prepared-plan.json, handoff.md, start_soak_once.py and proxy-preparation-addendum.json under the two IMP20-CURRENT-CANDIDATE-* run-20261015T020000Z-codex directories. Read the directly referenced preparation checker, finalizer, controller harvest and collector schema to verify integration. Approval is limited to the inspected once-only continuation; it does not assert full23 or soak success.

## Findings

CRITICAL: none.

HIGH: none. No demonstrated blocker in full23 eligibility -> one guarded soak launch -> existing collector receipt -> final verification was found.

MEDIUM: `IMP20-CURRENT-CANDIDATE-CONTINUATION-01/run-20261015T020000Z-codex/validate_preparation.py:22-40` mostly checks source substrings/call counts. These checks mirror implementation spelling, not execution behavior: moving a predicate into an unused branch or pairing `exclusive=True` with the wrong write can leave them green. Their explicit static-only labeling avoids a false runtime success claim, but they are not regression coverage for orchestration. On future modification, replace behavioral claims with bounded fake-process/fake-clock scenarios covering denied eligibility, one dispatch, collector nonzero and timeout; retain actual hash/compile checks. No live rerun is needed for this review.

LOW: continuation.py:124 computes a wait result then immediately replaces that variable at :125. This is harmless but obscures that the first value is the manifest while the next is the result. A future cleanup can call wait_for without assignment.

## Inspected correctness

- continuation.py:114-130 checks frozen inputs, claim-to-plan hash, clean current and commit source, exact check names, actual gate/runner exits and unmerged eligible result before effectful launch.
- start_soak_once.py:66-105 independently validates exact23 manifest rows, report/result hashes, official verifier receipt, frozen source and measurement blobs.
- continuation.py:131-134 and launcher :65, :107 use fresh output and exclusive claims; the existing controller owns preflight and detached harvest. No new gate or duplicate manual collector is dispatched.
- collector_proxy.py:33-47 validates expected cwd/output/source and records the actual waited exit, including negative signal exits, before propagation. Controller's supported NX10_JUDGE invocation passes through the existing harvest pipeline.
- continuation.py:137-158 checks exact final verifier command, actual collector exit, six required scenario names, both measured and runner duration >=28800, source fingerprints and gate evidence hashes. Failures cannot become PASS through an omitted check.
- continuation.py:103-106, :162-166 preserves timeout as UNOBSERVED and normal errors as HOLD. An owned child may outlive a wait timeout, as explicitly documented; no retry follows. This review does not claim OS cleanup on that branch.
- Existing finalizer ownership assumes the documented cooperating parent does not concurrently finalize. No general cross-process lock guarantee is claimed.

## Skill perspective and limits

Consulted remove-ai-slops and programming skills. The preparation checker violates the implementation-mirroring test perspective noted above. Boundary JSON/hash checks in these evidence orchestration scripts are required by their purpose; no unnecessary production parsing, product abstraction or deletion-only tests were identified. The scripts use largely untyped JSON and functions, so this is not a strict typed-programming compliance approval. No production file was changed or executed. No test, gate, collector, verifier, HTTP, model, process launch/restart/kill was performed by this review.

Graph lookup returned project not indexed; prior indexing failure was supplied by the parent. Used exact supplied paths and narrow known dependency sections without another indexing attempt. `omo-agent-toolkit ulw-loop status --json` returned ULW_LOOP_PLAN_MISSING, so this report uses the required fallback path. This review artifact is the sole written file; no source or runtime evidence was modified.
