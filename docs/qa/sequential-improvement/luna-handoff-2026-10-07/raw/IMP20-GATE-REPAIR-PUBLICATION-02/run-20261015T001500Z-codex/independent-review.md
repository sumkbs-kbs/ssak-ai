# Round 2 prerequisite gate review

recommendation: APPROVE
scope: Scoped prerequisite remediation only; not full-23 gate completion, soak completion, or release approval.
candidate: 1e9dfb87b185f3d20792d3f4bff4a25189947c15
base: 30233787
blockers: []

## Original intent and desired outcome

Continue the highest-priority release-gate repairs while preserving prior failures and evidence. This review asks whether the four committed repairs are justified and ready for a new same-candidate full gate run. It does not ask to renew historical live migration evidence or approve GA.

## User outcome review

APPROVE for that bounded purpose. Candidate tracked tree is clean. The diff replaces a stale successful-fallback API expectation with the existing strict unavailable-model contract, repairs one empty-state text color, updates only the affected migration reverification row and generated drift evidence, and regenerates the bundle with a real source revision. No gate threshold, required selector, production embedding behavior, or historical T12 pin was weakened.

## Criteria and direct findings

- C1, strict embedding behavior: inspected the changed test and existing engine/API path. The real EmbeddingEngine receives a controlled failing model factory. The test checks loader exactly once, fallback never called, typed 503 body, no vector, and no raw loader-error disclosure. Five final JUnit cases have no failures/errors. Receipt hashes of the changed test, adjacent contract test, engine and API match candidate bytes. Final diagnostic report retains the original 4 errors/156 warnings and records zero added diagnostics. This is not a clean whole-file type-check claim.
- C2, honest migration reverification: direct diff changes one migration registry entry and its corresponding generated drift row. Seven final binding hashes match candidate files, including migration source, both migration tests and historical T12 document. Stored JUnit independently shows 145 passed in attempt 2 and 36 passed in a separate supplemental invocation. Initial 145 setup errors remain in their original JUnit. The method explicitly excludes renewed historical 56,961-row/live validation and discloses absent old test-execution byte pins.
- C3, visible contrast repair: the only CSS change uses existing --text-muted for .model-empty-notice. I inspected the saved 1280x720 final screenshot: completed empty-state text is visible. Primary observations record rgb(160,160,160) over rgb(32,32,32), bound to the current CSS hash. The accessibility raw log records 35 passed, with matching CSS hash in its command receipt. Light/mobile primary manual observation is not claimed; accessibility has its separate desktop/mobile scope.
- C4, reproducible build provenance: final pin SHA matches all final build receipts. The pin names committed source 8585d8fbcac3589d7baeb614302ed184062095f8. Git shows no dashboard/src changes between that source commit and candidate HEAD. Independently compared all 106 final inventory paths, sizes and SHA-256 against the candidate bundle: no mismatch. Final provenance selector raw log reports 3 passed; both final build commands and corrected normal pre-commit receipt report exit 0. Earlier 1,244-unit pass belongs to its earlier metadata candidate, not a newly executed final full dashboard suite.
- C5, preservation and bounded claims: independently checked six artifact manifests, 255 entries total, with no missing file, size mismatch or SHA mismatch (45 original embedding, 30 embedding revision, 36 cognitive, 8 cognitive supplement, 127 initial build, 9 CSS packet). Prior failed attempts remain represented. New full23 and 8-hour soak are still unobserved.

## Programming and remove-ai-slops pass

Consulted both skills and directly inspected the complete handwritten diff plus the relevant existing embedding engine/API boundary. No new production abstraction, parsing/normalization layer, generic exception suppression, type-ignore, or speculative helper was introduced. The factory and fallback spy are meaningful fault-injection seams; they prove observable HTTP/error behavior and prevention of synthetic success, rather than restating implementation or merely asserting a removed name. The replacement test can fail under the historical fallback behavior. It is not a deletion-only, tautological, or excessive duplicate test. The exact structured error fields belong to the established contract. The CSS uses a shared token without an unnecessary component extraction. The documentation retains evidence limits rather than converting aggregate counts into release claims.

No separate code-review report explicitly covering both skill perspectives was supplied in these packets. This direct pass provides that coverage; it is not a completion blocker under the review instructions. Existing module size and preexisting type diagnostics are notes, not new violations of this bounded brief.

## Checked artifact paths

All paths below are relative to ROOT docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/ unless stated otherwise.

- IMP20-EMBEDDING-STRICT-FIXTURE-01/run-20261015T010000Z-embedding/artifact-manifest.json; revision-v2/{artifact-manifest.json,result.json,green/receipt.json,green/junit.xml}; original red/red-2/green JUnit.
- IMP20-COGNITIVE-REVERIFICATION-01/run-20261014T235000Z-codex/{artifact-manifest.json,result.json,final-binding.json,junit.xml,junit-attempt-2.xml,final-checks.json}; supplement-20261014T235420Z/{artifact-manifest.json,junit.xml}.
- IMP20-MODEL-EMPTY-CONTRAST-01/run-20261014T235534Z-model-empty/artifact-manifest.json.
- IMP20-MODEL-EMPTY-CONTRAST-VALIDATION-01/run-20261015T000000Z-codex/{checks.json,accessibility.stdout.txt,primary-current-ui/observations.json,primary-current-ui/models-dark-final.png}.
- IMP20-BUILD-PROVENANCE-SHA-01/run-20261014T235500Z-codex/{artifact-manifest.json,result.json,bundle-reproduction.json}.
- IMP20-GATE-REPAIR-PUBLICATION-02/run-20261015T001500Z-codex/final-pin/{checks.json,bundle-reproduction.json,commit.json,pre-commit-v2.json,provenance-tests.stdout.txt}.
- Candidate diff 30233787..1e9dfb87, clean status, dashboard source comparison 8585d8f..HEAD, existing embeddings.py and models_api.py strict branch.

## Exact limitations

No tests, server, HTTP, inference or builds were rerun by this reviewer. Verification used stored raw evidence, current source and byte/hash comparisons. No fresh full23, soak, live inference or overall IMP09 completion is inferred. The graph returned project-not-indexed; the previously failed 300-second indexing attempt was not repeated, and exact known paths were inspected. No ulw-loop plan exists, so this report uses the requested fallback evidence path. A reviewer-only first bundle lookup duplicated the path prefix and failed before comparing; the corrected read-only comparison checked all 106 entries successfully. A later optional packet read used candidate-relative paths absent there; it added no evidence and did not change the verdict.
